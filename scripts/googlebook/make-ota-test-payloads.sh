#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Disposable payloads for build-ota-trust-candidate.py --vm-test.
#
# Creates two throwaway RSA-4096 signers: "openbook-test" stands in for the
# OpenBook update key, "foreign-test" for Google's. Partition contents are
# random. max_timestamp is 2100-01-01, so update_engine's anti-downgrade check
# passes as it would for a newer stock build. Three full payloads:
#   foreign-static   boot + vbmeta, signed by foreign-test
#   openbook-static  boot + vbmeta, signed by openbook-test
#   openbook-vab     system (Virtual A/B, compressed) + boot + vbmeta, signed by
#                    openbook-test; the shape of a stock OTA
# Private keys stay in OUT/keys (mode 0600). Never commit or reuse them.
#
# usage: make-ota-test-payloads.sh DELTA_GENERATOR OUT
set -euo pipefail
DG=$1 OUT=$2
[ ! -e "$OUT" ] || { echo "New output directory required" >&2; exit 1; }
umask 077
mkdir -p "$OUT/keys" "$OUT/parts" "$OUT/payloads"
for k in openbook-test foreign-test; do
  openssl req -x509 -newkey rsa:4096 -nodes -days 3650 -subj "/CN=$k OTA (disposable VM test only)" \
    -keyout "$OUT/keys/$k.key" -out "$OUT/keys/$k.x509.pem" 2>/dev/null
done
head -c 1048576 /dev/urandom >"$OUT/parts/boot.img"
head -c 65536 /dev/urandom >"$OUT/parts/vbmeta.img"
head -c 1048576 /dev/urandom >"$OUT/parts/system.img"
cat >"$OUT/parts/dynamic.txt" <<'EOF'
super_partition_groups=ruby_probe
ruby_probe_size=1073741824
ruby_probe_partition_list=system
virtual_ab=true
virtual_ab_compression=true
EOF

payload() { # NAME KEY PARTITIONS NAMES [EXTRA...]
  local name=$1 key=$2 parts=$3 names=$4; shift 4
  "$DG" --new_partitions="$parts" --partition_names="$names" --major_version=2 --minor_version=0 \
    --max_timestamp=4102444800 --private_key="$OUT/keys/$key.key" --out_file="$OUT/payloads/$name.bin" "$@" >"$OUT/payloads/$name.log" 2>&1
  "$DG" --in_file="$OUT/payloads/$name.bin" --properties_file="$OUT/payloads/$name.properties" >>"$OUT/payloads/$name.log" 2>&1
  for k in openbook-test foreign-test; do
    openssl pkey -in "$OUT/keys/$k.key" -pubout -out "$OUT/keys/$k.pub.pem" 2>/dev/null
    if "$DG" --in_file="$OUT/payloads/$name.bin" --public_key="$OUT/keys/$k.pub.pem" >>"$OUT/payloads/$name.log" 2>&1; then
      echo "$name verifies with $k"
    fi
  done
}

P=$OUT/parts
payload foreign-static foreign-test "$P/boot.img:$P/vbmeta.img" boot:vbmeta
payload openbook-static openbook-test "$P/boot.img:$P/vbmeta.img" boot:vbmeta
payload openbook-vab openbook-test "$P/system.img:$P/boot.img:$P/vbmeta.img" system:boot:vbmeta \
  --dynamic_partition_info_file="$P/dynamic.txt"
sha256sum "$OUT"/keys/*.x509.pem "$OUT"/payloads/*.bin
