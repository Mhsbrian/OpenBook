#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Create the OpenBook app signing key for OpenBook Update, once, on the build host (never in a container).
# Same custody as the OpenBook OTA key (googlebook-ota-trust.md): owner-only files outside every repository,
# image, log and container mount, plus an encrypted backup for offline storage.
#
#   ~/.local/share/openbook-keys/app/openbook-update-2026.key         PRIVATE key, RSA-4096, PKCS#8 PEM (0600)
#   ~/.local/share/openbook-keys/app/openbook-update-2026.pk8         the same key, PKCS#8 DER, for apksigner (0600)
#   ~/.local/share/openbook-keys/app/openbook-update-2026.x509.pem    public certificate (30 years); its DER bytes
#                                                                     go into mac_permissions.xml (seinfo "openbook")
#   ~/.local/share/openbook-keys/app/backup/                          encrypted key + its passphrase (save, then delete)
# The certificate is also copied into the repository (device/anybook/common/updater/openbook-update.x509.pem).
# A lost key means the next OpenBook release must ship the app under a new certificate (its app data is reset).
#
# usage: make-app-key.sh            refuses to overwrite an existing key
set -euo pipefail
umask 077
D=${OPENBOOK_KEYS:-$HOME/.local/share/openbook-keys}/app
N=openbook-update-2026
[ -f /.dockerenv ] && { echo "run on the host, never in a container" >&2; exit 1; }
[ -e "$D/$N.key" ] && { echo "$D/$N.key exists; refusing to replace it" >&2; exit 1; }
mkdir -p "$D/backup"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$D/$N.key" 2>/dev/null
openssl pkcs8 -topk8 -nocrypt -inform PEM -outform DER -in "$D/$N.key" -out "$D/$N.pk8"
openssl req -new -x509 -sha256 -days 10957 -key "$D/$N.key" -out "$D/$N.x509.pem" \
  -subj "/C=US/O=OpenBook/OU=OpenBook Update/CN=OpenBook Update app key 2026"
pass=$(openssl rand -base64 33)
printf '%s\n' "$pass" > "$D/backup/PASSPHRASE-save-then-delete.txt"
openssl pkcs8 -topk8 -v2 aes-256-cbc -scrypt -in "$D/$N.key" -out "$D/backup/$N.key.enc.pem" \
  -passout file:"$D/backup/PASSPHRASE-save-then-delete.txt"
fp=$(openssl x509 -in "$D/$N.x509.pem" -noout -fingerprint -sha256 | cut -d= -f2)
cat > "$D/README.txt" <<TXT
OpenBook Update app signing key (created $(date -u +%Y-%m-%d), ANAL-229)

$N.key        PRIVATE signing key, RSA-4096, PKCS#8 PEM. Owner-only (0600).
$N.pk8        The same key as PKCS#8 DER (apksigner). Owner-only (0600).
              Never copy either into a repository, an image, a log, ~/anybook or a container mount.
$N.x509.pem   Public certificate. Its DER bytes are OpenBook's "openbook" seinfo signer in
              /system/etc/selinux/plat_mac_permissions.xml: the app's SELinux domain depends on it.
backup/$N.key.enc.pem             The same key, encrypted (scrypt + AES-256).
backup/PASSPHRASE-save-then-delete.txt Its passphrase.

To finish the offline backup:
  1. Copy backup/$N.key.enc.pem to offline media you keep (USB drive, safe).
  2. Save the passphrase from backup/PASSPHRASE-save-then-delete.txt in your password manager.
  3. Delete the passphrase file:  shred -u backup/PASSPHRASE-save-then-delete.txt
Keep the encrypted file and its passphrase in different places.

Certificate fingerprint (DER SHA-256): $fp
Sign the app with OpenBook device/anybook/common/updater/app/build.sh (on the host, never in a container).
TXT
chmod 600 "$D"/*.key "$D"/*.pk8 "$D"/*.pem "$D"/README.txt "$D"/backup/*
echo "created $D/$N.{key,pk8,x509.pem}; certificate SHA-256 $fp"
