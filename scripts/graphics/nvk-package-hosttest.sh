#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# OpenBook NVK on this build host's NVIDIA GPU, from an image's driver package (ANAL-327, docs/nvk-openbook.md §6).
# The libraries are taken out of the image's /vendor/app/OpenBookNvk/OpenBookNvk.apk exactly as Android loads them
# (lib/x86_64, stored uncompressed and page-aligned: checked), compared with device/anybook/common/nvk/tested-bytes.txt,
# and run the way ANAL-326 (stage 2b) ran the build it tested: NVK's own HAL entry through libvk_hal_shim.so
# (scripts/graphics/vk-hal-shim.c: it opens the HAL as Android's libvulkan does), the same test package, case lists,
# skips and dEQP settings. What runs around them is the image's own: its bionic, /system and APEX libraries, in a
# container that sees only NVIDIA's device nodes and the GPU's render node, with no network and no capabilities.
# Then every case is compared with stage 2b's results, and the kernel log is read for Xid and NVRM lines.
#
# usage: nvk-package-hosttest.sh [--product-out DIR] [--testpkg TAR] [--baseline DIR] [--out DIR] [--jobs N]
#                                [PART ...]
#   PARTs: vulkaninfo queues vk (default: all three; vk is the 66,226-case dEQP-VK list, ~6 min on the RTX 4090)
#   --product-out  the image's PRODUCT_OUT (default: <data dir>/aosp/src/out/target/product/anybook_g14)
#   --testpkg      ANAL-240's test package (default nvk-test-20261025-anal240.tar under <data dir>/gfx-cts/nvk-test)
#   --baseline     stage 2b's host run (default <data dir>/evidence/openbook/2026-11-01-anal326-nvk-clean-test/
#                  host4090-clean), with vk/run/results.csv and queues/run/results.csv
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
P=$A/aosp/src/out/target/product/anybook_g14
TP=$A/gfx-cts/nvk-test/nvk-test-20261025-anal240/nvk-test-20261025-anal240.tar
BASE=$A/evidence/openbook/2026-11-01-anal326-nvk-clean-test/host4090-clean
OUT=$A/logs/nvk-hosttest/$(date -u +%Y%m%dT%H%M%SZ); JOBS=8; PARTS=()
while [ $# -gt 0 ]; do
  case $1 in
    --product-out) P=$2; shift 2 ;;
    --testpkg) TP=$2; shift 2 ;;
    --baseline) BASE=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --jobs) JOBS=$2; shift 2 ;;
    -*) echo "unknown option $1" >&2; exit 2 ;;
    *) PARTS+=("$1"); shift ;;
  esac
done
[ ${#PARTS[@]} -gt 0 ] || PARTS=(vulkaninfo queues vk)
APK=$P/vendor/app/OpenBookNvk/OpenBookNvk.apk
for f in "$APK" "$TP" "$P/system/build.prop"; do [ -e "$f" ] || { echo "missing: $f" >&2; exit 2; }; done
for d in /dev/nvidiactl /dev/nvidia0; do [ -c "$d" ] || { echo "no $d: is NVIDIA's open kernel driver loaded?" >&2; exit 2; }; done
NODE=
for n in /sys/class/drm/renderD*; do
  [ "$(basename "$(readlink -f "$n/device/driver")")" = nvidia ] && { NODE=/dev/dri/${n##*/}; break; }
done
[ -n "$NODE" ] || { echo "no render node of NVIDIA's driver (nvidia-drm)" >&2; exit 2; }
mkdir -p "$OUT"; W=$OUT/work; mkdir -p "$W"
exec > >(tee -a "$OUT/hosttest.log") 2>&1
echo "== nvk-package-hosttest.sh ${PARTS[*]} ($(date -u +%FT%TZ)), OpenBook $(git -C "$R" rev-parse --short HEAD), jobs $JOBS"

# 1. The package's libraries, as Android finds them in the APK.
python3 -I - "$APK" "$W/pkg" "$R/device/anybook/common/nvk/tested-bytes.txt" > "$OUT/package-libs.txt" <<'EOF'
import hashlib, os, struct, sys, zipfile
apk, dest, pin = sys.argv[1:4]
want = {}
for line in open(pin):
    if line.startswith("#") or not line.strip():
        continue
    sha, _, name = line.rstrip("\n").split("\t")
    want[name] = sha
os.makedirs(dest, exist_ok=True)
bad = 0
with open(apk, "rb") as raw, zipfile.ZipFile(apk) as z:
    libs = [i for i in z.infolist() if i.filename.startswith("lib/")]
    for i in libs:
        raw.seek(i.header_offset)
        h = raw.read(30)
        n, e = struct.unpack("<HH", h[26:30])
        data_off = i.header_offset + 30 + n + e
        data = z.read(i)
        name = os.path.basename(i.filename)
        open(os.path.join(dest, name), "wb").write(data)
        sha = hashlib.sha256(data).hexdigest()
        stored = i.compress_type == zipfile.ZIP_STORED
        aligned = data_off % 4096 == 0
        tested = want.get(name)
        verdict = "tested" if tested == sha else ("NOT-TESTED" if tested else "other")
        if not stored or not aligned or (tested and tested != sha):
            bad += 1
        print(f"{sha}  {i.filename}  {'stored' if stored else 'COMPRESSED'} {'page-aligned' if aligned else 'UNALIGNED'} {verdict}")
    missing = sorted(set(want) - {os.path.basename(i.filename) for i in libs})
    for m in missing:
        print(f"MISSING  lib/x86_64/{m}"); bad += 1
print(f"apk: {apk} ({hashlib.sha256(open(apk, 'rb').read()).hexdigest()})")
print(f"result: {'OK' if bad == 0 else f'{bad} problem(s)'}")
sys.exit(1 if bad else 0)
EOF
cat "$OUT/package-libs.txt"

# 2. The test package (ANAL-240's), unpacked once, and the image's library search path.
PKGN=$(basename "$TP" .tar); TPD=$A/gfx-cts/nvk-test/unpacked
[ -d "$TPD/$PKGN" ] || { mkdir -p "$TPD"; tar -xf "$TP" -C "$TPD"; }
LP=/pkg:/system/lib64
for d in "$P"/apex/*/lib64; do [ -d "$d" ] && LP=$LP:/apex/${d#"$P"/apex/}; done
{ echo "image: $P ($(grep -m1 -E '^ro(.system)?.build.fingerprint=' "$P/system/build.prop" | cut -d= -f2))"
  echo "package: $(sha256sum "$APK" | cut -d' ' -f1)  vendor/app/OpenBookNvk/OpenBookNvk.apk"
  echo "test package: $TP ($(sha256sum "$TP" | cut -d' ' -f1))"
  echo "hal: /pkg/vulkan.radv.so through /p/lib/libvk_hal_shim.so"
  echo "node: $NODE ($(grep PCI_SLOT_NAME "/sys/class/drm/$(basename "$NODE")/device/uevent"))"
  head -1 /proc/driver/nvidia/version; uname -r; date -u +%FT%TZ; } > "$OUT/versions.txt"
cat "$OUT/versions.txt"

run() {  # run NAME CMD...: in the container
  local name=$1; shift
  docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges -u "$(id -u):$(id -g)" \
    --device /dev/nvidiactl --device /dev/nvidia0 --device /dev/nvidia-modeset --device "$NODE" \
    -v "$P/system:/system:ro" -v "$P/apex:/apex:ro" -v "$W/pkg:/pkg:ro" -v "$TPD/$PKGN:/p:ro" -v "$OUT:/out" -w /out \
    -e HOME=/tmp -e TMPDIR=/tmp -e LD_LIBRARY_PATH="$LP" -e OPENBOOK_VK_HAL=/pkg/vulkan.radv.so alpine:3.21 "$@"
}
klog_since() { journalctl -k --since "@$1" --no-pager -o short-iso 2>/dev/null | grep -E 'NVRM|Xid' || true; }

rc_all=0
for part in "${PARTS[@]}"; do
  t0=$(date +%s); echo "== $part ($(date -u +%FT%TZ))"
  mkdir -p "$OUT/$part"
  set +e
  case $part in
    vulkaninfo)
      run vulkaninfo env LD_LIBRARY_PATH="/p/lib/loader:$LP" /p/bin/vulkaninfo > "$OUT/vulkaninfo/vulkaninfo.txt" 2>&1
      rc=$?
      run vulkaninfo env LD_LIBRARY_PATH="/p/lib/loader:$LP" /p/bin/vulkaninfo --summary > "$OUT/vulkaninfo/summary.txt" 2>&1
      grep -m1 'deviceName' "$OUT/vulkaninfo/vulkaninfo.txt" ;;
    queues|vk)
      cl=/p/caselists/$part.txt
      printf '[[deqp]]\ndeqp = "/out/%s/deqp-binary64"\ncaselists = ["%s"]\nskips = ["/p/skips/nvk.txt"]\ntests_per_group = 100\nrenderer_check = "NVK"\ndeqp_args = ["--deqp-archive-dir=/p/data", "--deqp-vk-library-path=/p/lib/libvk_hal_shim.so", "--deqp-log-images=disable", "--deqp-log-shader-sources=disable", "--deqp-shadercache=disable"]\n[deqp.env]\nLD_PRELOAD = "/p/lib/libdeqp_stdout.so"\nLD_LIBRARY_PATH = "%s"\nOPENBOOK_VK_HAL = "/pkg/vulkan.radv.so"\nHOME = "/tmp"\n' \
        "$part" "$cl" "$LP" > "$OUT/$part/suite.toml"
      # dEQP runs in its binary's directory (deqp-runner starts it there), and some cases read their data relative to
      # it (copy_memory_indirect: "Error opening file!" otherwise). So, as in stage 2b, the binary and the test data are
      # linked into the part's writable directory.
      run "$part" sh -c "cd /out/$part && ln -sfn /p/bin/deqp-binary64 deqp-binary64 && ln -sfn /p/data/vulkan vulkan && /p/bin/deqp-runner suite --suite /out/$part/suite.toml --output /out/$part/run --jobs $JOBS --summary-limit 30" \
        > "$OUT/$part/deqp-runner.txt" 2>&1
      rc=$?; tail -n 3 "$OUT/$part/deqp-runner.txt" ;;
    *) echo "unknown part $part" >&2; rc=2 ;;
  esac
  set -e
  k=$(klog_since "$t0"); printf '%s\n' "$k" | grep -v '^$' > "$OUT/$part/kernel-nvrm.txt" || true
  echo "$part: rc=$rc, $(( $(date +%s) - t0 )) s, kernel log: $(grep -c Xid "$OUT/$part/kernel-nvrm.txt" || true) Xid, $(grep -c NVRM "$OUT/$part/kernel-nvrm.txt" || true) NVRM"
  [ "$part" = vulkaninfo ] && [ "$rc" != 0 ] && rc_all=1
done

# 3. Every case against stage 2b's run of the same bytes.
python3 -I - "$OUT" "$BASE" "${PARTS[@]}" > "$OUT/compare.txt" <<'EOF'
import csv, os, sys
out, base, parts = sys.argv[1], sys.argv[2], sys.argv[3:]
def load(p):
    r = {}
    with open(p) as f:
        for row in csv.reader(f):
            if row:
                r[row[0]] = row[1]
    return r
for part in parts:
    if part == "vulkaninfo":
        continue
    a, b = f"{base}/{part}/run/results.csv", f"{out}/{part}/run/results.csv"
    if not (os.path.exists(a) and os.path.exists(b)):
        print(f"{part}: no comparison ({'baseline' if not os.path.exists(a) else 'this run'} missing)")
        continue
    old, new = load(a), load(b)
    count = lambda d: {s: list(d.values()).count(s) for s in sorted(set(d.values()))}
    changed = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
    print(f"{part}: baseline {len(old)} cases {count(old)}")
    print(f"{part}: this run {len(new)} cases {count(new)}")
    print(f"{part}: {len(changed)} case(s) differ")
    for k in changed[:50]:
        print(f"  {k}: {old.get(k)} -> {new.get(k)}")
EOF
cat "$OUT/compare.txt"
echo "nvk-package-hosttest: $OUT"
exit $rc_all
