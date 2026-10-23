#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The second update of a Ruby A/B disk in QEMU, in the direction the G14 takes after its first wireless
# update (RB-20261023-03): the disk runs slot B, the payload goes into slot A.
#   start   FIRST_OUT from ab-ota-suite.sh (apply into B, boot B, verify B): its disk now runs slot B,
#           FIRST_OUT/tpm holds that boot's TPM state. Both are copied, never changed.
#   payload drive -> apply into slot A -> reboot into slot A (mark good, merge)
#   -> verify-ab-slot.py: merged slot A equals the release byte for byte
#   [--fallback] in parallel with the reboot: the post-apply copy with vbmeta_a corrupted
#                must fall back to slot B by itself
# Regular image files only; nothing touches a device. Results: OUT/summary.json.
#
# usage: ab-ota-suite-slot-a.sh IMAGE_DIR SIGNED_PAYLOAD_DIR RELEASE_DIR FIRST_OUT OUT [--fallback]
#   IMAGE_DIR           the build-ruby-ab-image.py output FIRST_OUT started from (its layout)
#   SIGNED_PAYLOAD_DIR  build-ruby-ab-ota.py OUT/signed, built with --source = the images slot B holds
#   RELEASE_DIR         the release's ten .img files the payload installs
# env: as ab-ota-suite.sh (QEMU, BOOTSYNC, AOSP_HOST, OTATOOLS, APPLY_SECONDS, BOOT_SECONDS)
set -euo pipefail
[ $# -ge 5 ] || { sed -n '3,19p' "$0"; exit 2; }
IMG=$(realpath "$1"); PAY=$(realpath "$2"); REL=$(realpath "$3"); FIRST=$(realpath "$4"); OUT=$5; FALLBACK=${6:-}
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../.." && pwd)
QEMU=${QEMU:-$HOME/anybook/installer/work/anal228-tcg/build/qemu-system-x86_64}
BOOTSYNC=${BOOTSYNC:-$HOME/anybook/installer/build/openbook-bootsync-host}
AOSP_HOST=${AOSP_HOST:-$HOME/anybook/aosp/src/out/host/linux-x86}
OTATOOLS=${OTATOOLS:-$HOME/anybook/ota/builds/openbook-ota-20261019-quire1/otatools}
[ -f "$FIRST/apply/disk.img" ] && [ -d "$FIRST/tpm" ] || { echo "FIRST_OUT has no disk running slot B" >&2; exit 2; }
python3 - "$FIRST/summary.json" <<'EOF'
import json, sys
s = json.load(open(sys.argv[1]))
if not all(s.get(k, {}).get("passed") for k in ("apply", "boot", "verify")):
    raise SystemExit("FIRST_OUT did not pass apply/boot/verify into slot B")
EOF
mkdir -m 700 "$OUT"; OUT=$(realpath "$OUT")
run() { "$REPO/scripts/installer/inst-docker.sh" "$@"; }
q() { run python3 "$HERE/ab-ota-qemu.py" --image-dir "$IMG" --qemu "$QEMU" --bootsync "$BOOTSYNC" --slot a "$@"; }

mkdir -m 700 "$OUT/drive-src"
cp "$PAY/payload.bin" "$PAY/payload_properties.txt" "$OUT/drive-src/"; chmod 0644 "$OUT/drive-src/"*
bytes=$(( $(stat -c %s "$PAY/payload.bin") + 512 * 1024 * 1024 ))
run sh -c "truncate -s $bytes '$OUT/payload.img' && mkfs.ext4 -q -L otapayload -d '$OUT/drive-src' '$OUT/payload.img'"
rm -rf "$OUT/drive-src"
sha=$(sha256sum "$PAY/payload.bin" | cut -d' ' -f1)
cp -r "$FIRST/tpm" "$OUT/tpm"

q --phase apply --disk "$FIRST/apply/disk.img" --payload "$OUT/payload.img" --payload-sha256 "$sha" \
  --target-dir "$REL" --tpm-state "$OUT/tpm" --out "$OUT/apply" --seconds "${APPLY_SECONDS:-14400}" \
  > "$OUT/apply.log" 2>&1 || true
rm -f "$OUT/payload.img"
fb_pid=
if [ "$FALLBACK" = --fallback ] && [ -f "$OUT/apply/disk-after-apply.img" ]; then
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
  --layout "$IMG/result.json" --slot a --release "$REL" --lp-tools "$OUT/lp" --work "$OUT/verify-work" \
  --out "$OUT/verify-slot-a.json" > /dev/null || true
[ -n "$fb_pid" ] && wait "$fb_pid" || true

python3 - "$OUT" "$FALLBACK" <<'EOF'
import json, sys
from pathlib import Path
out, fallback = Path(sys.argv[1]), sys.argv[2] == "--fallback"
def res(p):
    f = out / p
    return json.loads(f.read_text()) if f.exists() else {"passed": False, "missing": True}
phases = {"apply": res("apply/result.json"), "boot": res("boot/result.json"), "verify": res("verify-slot-a.json")}
if fallback:
    phases["fallback"] = res("fallback/result.json")
summary = {k: dict(passed=v.get("passed"), missing=v.get("missing", False),
                   failed=[c for c, ok in v.get("checks", {}).items() if not ok]) for k, v in phases.items()}
summary["direction"] = "slot B -> slot A"
summary["passed"] = all(v["passed"] for v in summary.values() if isinstance(v, dict))
(out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
EOF
