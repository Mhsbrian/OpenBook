#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Sign an unsigned OpenBook update payload on the host, then verify it against the
# public certificate that images install as /system/etc/security/otacerts.zip.
#
# Uses delta_generator's hash-file mode: only the two `openssl pkeyutl` calls see
# the private key, so it can later move to a hardware token. Refuses to run in a
# container or with a key inside ~/anybook or a git work tree.
#
# usage: sign-ota-payload.sh DELTA_GENERATOR KEY CERT UNSIGNED_PAYLOAD OUT_DIR
#        sign-ota-payload.sh --self-test DELTA_GENERATOR KEY CERT
# The self-test signs an inert payload (partition "openbook_selftest",
# max_timestamp 1, so any device refuses it), verifies it, checks that a
# different key fails, and deletes everything it made.
set -euo pipefail

SELF_TEST=0
if [ "${1:-}" = "--self-test" ]; then SELF_TEST=1; shift; fi
DG=$1 KEY=$2 CERT=$3
[ ! -e /.dockerenv ] || { echo "Sign on the host, never in a container" >&2; exit 1; }
key_path=$(realpath -e "$KEY")
case "$key_path" in "$HOME"/anybook/*) echo "Key must not live under ~/anybook (container mount)" >&2; exit 1;; esac
if git -C "$(dirname "$key_path")" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Key must not live inside a git work tree" >&2; exit 1
fi
[ "$(stat -c %a "$key_path")" = 600 ] || { echo "Key must be mode 0600" >&2; exit 1; }
cert_pub=$(openssl x509 -in "$CERT" -noout -pubkey)
[ "$(openssl pkey -in "$key_path" -pubout)" = "$cert_pub" ] || { echo "Key does not match the certificate" >&2; exit 1; }
bits=$(openssl x509 -in "$CERT" -noout -text | sed -n 's/.*Public-Key: (\([0-9]*\) bit).*/\1/p')
case "$bits" in 2048|4096) SIG_SIZE=$((bits / 8));; *) echo "Unsupported key size" >&2; exit 1;; esac

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
umask 077
printf '%s\n' "$cert_pub" >"$T/pub.pem"

sign() { # UNSIGNED OUT_DIR
  local unsigned=$1 out=$2
  "$DG" --in_file="$unsigned" --signature_size="$SIG_SIZE" \
    --out_hash_file="$T/payload.hash" --out_metadata_hash_file="$T/metadata.hash" >"$T/hash.log" 2>&1
  openssl pkeyutl -sign -inkey "$key_path" -pkeyopt digest:sha256 -in "$T/payload.hash" -out "$T/payload.sig"
  openssl pkeyutl -sign -inkey "$key_path" -pkeyopt digest:sha256 -in "$T/metadata.hash" -out "$T/metadata.sig"
  mkdir -p "$out"
  "$DG" --in_file="$unsigned" --signature_size="$SIG_SIZE" --payload_signature_file="$T/payload.sig" \
    --metadata_signature_file="$T/metadata.sig" --out_file="$out/payload.bin" >"$T/insert.log" 2>&1
  "$DG" --in_file="$out/payload.bin" --public_key="$T/pub.pem" >"$T/verify.log" 2>&1 \
    || { echo "Signed payload does not verify against the certificate" >&2; exit 1; }
  "$DG" --in_file="$out/payload.bin" --properties_file="$out/payload_properties.txt" >>"$T/verify.log" 2>&1
}

if [ "$SELF_TEST" = 1 ]; then
  head -c 4096 /dev/zero >"$T/selftest.img"
  "$DG" --new_partitions="$T/selftest.img" --partition_names=openbook_selftest --major_version=2 \
    --minor_version=0 --max_timestamp=1 --out_file="$T/unsigned.bin" >"$T/generate.log" 2>&1
  sign "$T/unsigned.bin" "$T/signed"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 2>/dev/null | openssl pkey -pubout >"$T/other.pem"
  if "$DG" --in_file="$T/signed/payload.bin" --public_key="$T/other.pem" >"$T/other.log" 2>&1; then
    echo "Self-test FAILED: a different key verified the payload" >&2; exit 1
  fi
  echo "self-test passed: RSA-$bits signature verifies against the certificate and fails with another key; inert payload deleted"
  exit 0
fi

UNSIGNED=$4 OUT=$5
[ ! -e "$OUT" ] || { echo "New output directory required" >&2; exit 1; }
sign "$UNSIGNED" "$OUT"
sha256sum "$OUT/payload.bin"
