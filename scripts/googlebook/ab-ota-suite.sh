#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# One OTA, end to end, on a Ruby A/B disk in QEMU (ab-ota-qemu.py phases):
#   payload drive -> apply into slot B -> reboot into slot B (mark good, merge)
#   -> verify-ab-slot.py: merged slot B equals the release byte for byte
#   [--fallback] in parallel with the reboot: the post-apply copy with vbmeta_b corrupted
#                must fall back to slot A by itself
# Regular image files only; nothing touches a device. Results: OUT/summary.json.
#
# usage: ab-ota-suite.sh IMAGE_DIR SIGNED_PAYLOAD_DIR RELEASE_DIR OUT [--fallback]
#   IMAGE_DIR           build-ruby-ab-image.py output (an --apply-from-drive candidate)
#   SIGNED_PAYLOAD_DIR  build-ruby-ab-ota.py OUT/signed (payload.bin, payload_properties.txt)
#   RELEASE_DIR         the release's ten .img files the payload installs
# env: QEMU (GFNI/VNNI-emulating TCG build), BOOTSYNC (openbook-bootsync host build),
#      AOSP_HOST (out/host/linux-x86), OTATOOLS (has bin/lpunpack), APPLY_SECONDS, BOOT_SECONDS
set -euo pipefail
[ $# -ge 4 ] || { sed -n '3,16p' "$0"; exit 2; }
IMG=$(realpath "$1"); PAY=$(realpath "$2"); REL=$(realpath "$3"); OUT=$4; FALLBACK=${5:-}
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../.." && pwd)
QEMU=${QEMU:-$HOME/anybook/installer/work/anal228-tcg/build/qemu-system-x86_64}
BOOTSYNC=${BOOTSYNC:-$HOME/anybook/installer/build/openbook-bootsync-host}
AOSP_HOST=${AOSP_HOST:-$HOME/anybook/aosp/src/out/host/linux-x86}
OTATOOLS=${OTATOOLS:-$HOME/anybook/ota/builds/openbook-ota-20261019-quire1/otatools}
mkdir -m 700 "$OUT"; OUT=$(realpath "$OUT")
run() { "$REPO/scripts/installer/inst-docker.sh" "$@"; }
q() { run python3 "$HERE/ab-ota-qemu.py" --image-dir "$IMG" --qemu "$QEMU" --bootsync "$BOOTSYNC" "$@"; }

# payload drive: ext4 with the payload and its headers, world-readable (update_engine has no dac_override)
mkdir -m 700 "$OUT/drive-src"
cp "$PAY/payload.bin" "$PAY/payload_properties.txt" "$OUT/drive-src/"; chmod 0644 "$OUT/drive-src/"*
bytes=$(( $(stat -c %s "$PAY/payload.bin") + 512 * 1024 * 1024 ))
run sh -c "truncate -s $bytes '$OUT/payload.img' && mkfs.ext4 -q -L otapayload -d '$OUT/drive-src' '$OUT/payload.img'"
rm -rf "$OUT/drive-src"
sha=$(sha256sum "$PAY/payload.bin" | cut -d' ' -f1)

q --phase apply --payload "$OUT/payload.img" --payload-sha256 "$sha" --target-dir "$REL" \
  --tpm-state "$OUT/tpm" --out "$OUT/apply" --seconds "${APPLY_SECONDS:-14400}" > "$OUT/apply.log" 2>&1 || true
rm -f "$OUT/payload.img"
fb_pid=
if [ "$FALLBACK" = --fallback ]; then
  cp -r "$OUT/apply/tpm-after-apply" "$OUT/tpm-fallback"
  q --phase fallback --disk "$OUT/apply/disk-after-apply.img" --tpm-state "$OUT/tpm-fallback" \
    --out "$OUT/fallback" --attempts 4 --attempt-seconds 600 --seconds "${BOOT_SECONDS:-1800}" \
    > "$OUT/fallback.log" 2>&1 &
  fb_pid=$!
fi
q --phase boot --disk "$OUT/apply/disk.img" --tpm-state "$OUT/tpm" --out "$OUT/boot" \
  --seconds "${BOOT_SECONDS:-1800}" > "$OUT/boot.log" 2>&1 || true

mkdir -m 700 "$OUT/lp"; ln -s "$AOSP_HOST/bin/lpdump" "$OUT/lp/lpdump"; ln -s "$OTATOOLS/bin/lpunpack" "$OUT/lp/lpunpack"
LD_LIBRARY_PATH="$AOSP_HOST/lib64:$OTATOOLS/lib64" python3 "$HERE/verify-ab-slot.py" --disk "$OUT/apply/disk.img" \
  --layout "$IMG/result.json" --slot b --release "$REL" --lp-tools "$OUT/lp" --work "$OUT/verify-work" \
  --out "$OUT/verify-slot-b.json" > /dev/null || true
[ -n "$fb_pid" ] && wait "$fb_pid" || true

python3 - "$OUT" <<'EOF'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
def res(p):
    f = out / p
    return json.loads(f.read_text()) if f.exists() else {"passed": False, "missing": True}
phases = {"apply": res("apply/result.json"), "boot": res("boot/result.json"), "verify": res("verify-slot-b.json")}
if (out / "fallback").exists():
    phases["fallback"] = res("fallback/result.json")
summary = {k: dict(passed=v.get("passed"),
                   failed=[c for c, ok in v.get("checks", {}).items() if not ok]) for k, v in phases.items()}
summary["passed"] = all(v["passed"] for v in summary.values() if isinstance(v, dict))
(out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
EOF
