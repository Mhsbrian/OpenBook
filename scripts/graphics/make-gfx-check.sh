#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build the OpenBook graphics check (ANAL-177): an add-on for an OpenBook live USB stick that runs dEQP and ANGLE
# end2end on the laptop's GPU from the stick's own Android and saves the results on the stick. See
# scripts/graphics/mkaddon.py for what goes on the stick, scripts/graphics/gfx-run.sh for what runs, and
# docs/graphics-amd.md ("dEQP and CTS on the G14") for the owner steps.
# Image files only: this script never writes to a disk or USB stick. Adding it to a stick is
# scripts/graphics/add-to-live-stick.sh, which needs the owner's confirmation of the exact /dev/disk/by-id device.
#
# usage: make-gfx-check.sh [NAME]          NAME default openbook-gfxcheck-<UTC date>
#   GFX_APPS=0: leave out the dEQP and ANGLE end2end apps (no egl and angle parts; about 40 MB smaller on the stick)
# Inputs (built beforehand):
#   the G14 product's test modules: scripts/aosp-docker.sh -d NAME /repo/scripts/aosp-build.sh \
#     anybook_g14_x86_64-cp2a-userdebug deqp-binary com.drawelements.deqp AngleEnd2EndTestsHelper
#   RADV without android-strict: MESA_VARIANT=-nonstrict ANDROID_STRICT=false scripts/mesa-android-build.sh \
#     fetch setup build install verify -- upstream
#   deqp-runner: scripts/graphics/build-deqp-runner.sh (run here when missing)
# Output in <data dir>/installer/out/: NAME-addon/ (the ESP files, MANIFEST.sha256, EXPECT) and NAME-addon.json.
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); D=$R/scripts/installer/inst-docker.sh
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer; G=$A/gfx-cts
NAME=${1:-openbook-gfxcheck-$(date -u +%Y%m%d)}
case $NAME in *[!A-Za-z0-9._-]*) echo "name: letters, digits, . _ - only" >&2; exit 2 ;; esac
T=${AOSP_SRC:-$A/aosp/src}; P=${PRODUCT_OUT:-$T/out/target/product/anybook_g14}
NS=${NONSTRICT:-$A/mesa/out/upstream-nonstrict/vendor/lib64/hw/vulkan.radv.so}
# The second RADV (the vk14 part) is only for an image whose RADV is android-strict (Vulkan 1.1). Since ANAL-177 the
# default Mesa build reports 1.4 and the image declares it; then the payload carries none and vk14 skips itself.
VKXML=$P/vendor/etc/permissions/android.hardware.vulkan.version.xml
VK14=0; grep -q 'version="4198400"' "$VKXML" 2>/dev/null && VK14=1   # 4198400 = Vulkan 1.1
DQ=$P/data/nativetest64/deqp-binary
APK_DEQP=$P/testcases/com.drawelements.deqp/x86_64/com.drawelements.deqp.apk
APK_ANGLE=$P/testcases/AngleEnd2EndTestsHelper/x86_64/AngleEnd2EndTestsHelper.apk
for f in "$DQ/deqp-binary64" "$APK_DEQP" "$APK_ANGLE" "$VKXML" $([ $VK14 = 1 ] && echo "$NS"); do
  [ -f "$f" ] || { echo "missing $f (see the header for how to build it)" >&2; exit 2; }; done
W=$I/gfxcheck/$NAME; PL=$W/payload; O=$I/out
LOG=$A/logs/gfx-cts/gfxcheck-$NAME-$(date -u +%Y%m%dT%H%M%SZ).log
mkdir -p "$(dirname "$LOG")" "$O"
exec > >(tee -a "$LOG") 2>&1
echo "== make-gfx-check.sh $NAME ($(date -u +%FT%TZ)), repo $(git -C "$R" rev-parse --short HEAD)$(git -C "$R" diff --quiet HEAD -- scripts || echo '+dirty')"
rm -rf "$W"; mkdir -p "$PL"/{bin,lib,radv-nonstrict,apk,data,caselists,LICENSES}

# 1. deqp-runner (static musl), the NDK preload library, and the two static helpers built with the installer's gcc
[ -x "$G/bin/deqp-runner" ] || "$R/scripts/graphics/build-deqp-runner.sh"
cp "$G/bin/deqp-runner" "$PL/bin/"
docker run --rm -u "$(id -u):$(id -g)" -v "$R:/repo:ro" -v "$PL/lib:/b" anybook-mesa-android \
  /opt/android-ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android37-clang -shared -fPIC -O2 -Wall \
  /repo/scripts/graphics/deqp-stdout.c -ldl -o /b/libdeqp_stdout.so
"$D" gcc -static -O2 -Wall -o "$PL/bin/gfx-nsbind" "$R/scripts/graphics/gfx-nsbind.c"
"$D" gcc -static -O2 -Wall -Wextra -Wno-format-truncation -Wno-sign-compare -o "$W/openbook-gfx-init" \
  "$R/scripts/installer/live-init.c"
"$R/scripts/installer/live-init-test.sh" "$W/openbook-gfx-init" > "$W/live-init-test.txt" 2>&1 ||
  { cat "$W/live-init-test.txt"; echo "live-init host test failed" >&2; exit 1; }
tail -n 2 "$W/live-init-test.txt"

# 2. dEQP, its archive, the apps, RADV 1.4, the case lists
cp "$DQ/deqp-binary64" "$PL/bin/"
for d in gles2 gles3 gles31 vulkan internal; do cp -r "$DQ/$d" "$PL/data/"; done
[ "${GFX_APPS:-1}" = 0 ] || cp "$APK_DEQP" "$APK_ANGLE" "$PL/apk/"
if [ $VK14 = 1 ]; then cp "$NS" "$PL/radv-nonstrict/vulkan.radv.so"; else rmdir "$PL/radv-nonstrict"; fi
echo "image declares $(sed -n 's/.*version="\([0-9]*\)".*/\1/p' "$VKXML") (android.hardware.vulkan.version); second RADV in the payload: $([ $VK14 = 1 ] && echo yes || echo no)"
python3 "$R/scripts/graphics/mkcaselists.py" "$T/external/deqp/android/cts/main" "$PL/caselists" \
  --angle-expectations "$T/external/angle/android/cts/angle_end2end_tests_expectations.txt"
cp "$R/scripts/graphics/gfx-run.sh" "$PL/run.sh"
"$R/scripts/graphics/mkskips.sh" "$A/mesa/src/upstream" "$PL/skips"

# 3. licences: dEQP (VK-GL-CTS, Apache-2.0, with glslang, SPIRV-Tools, Amber), ANGLE (BSD-3-Clause), Mesa (MIT),
# deqp-runner (MIT), AOSP's test apps (Apache-2.0, with AndroidX)
cp "$T/external/deqp/LICENSE" "$PL/LICENSES/deqp-LICENSE"
cp "$T/external/angle/LICENSE" "$PL/LICENSES/angle-LICENSE"
cp "$A/mesa/src/upstream/docs/license.rst" "$PL/LICENSES/mesa-license.rst"
cp "$G/src/deqp-runner/LICENSE" "$PL/LICENSES/deqp-runner-LICENSE"
cat > "$PL/LICENSES/README.txt" <<EOF
OpenBook graphics check payload (ANAL-177): components, licences, sources
- bin/deqp-binary64, data/, apk/com.drawelements.deqp.apk: dEQP (Khronos VK-GL-CTS) as shipped in AOSP
  external/deqp ($(git -C "$T/external/deqp" rev-parse HEAD)), Apache-2.0 (deqp-LICENSE); it statically includes
  glslang, SPIRV-Tools and Amber (their licences are in that tree). Built for anybook_g14_x86_64 from AOSP.
- apk/AngleEnd2EndTestsHelper.apk: ANGLE's end2end tests as Android 17's CTS builds them, AOSP external/angle
  ($(git -C "$T/external/angle" rev-parse HEAD)), BSD-3-Clause (angle-LICENSE), with AndroidX test libraries
  (Apache-2.0).
- radv-nonstrict/vulkan.radv.so: Mesa 26.2.5 RADV with OpenBook's patches (mesa/patches/upstream in the OpenBook
  repo), built without android-strict, MIT (mesa-license.rst).
- bin/deqp-runner: Mesa's deqp-runner 0.23.2, MIT (deqp-runner-LICENSE), https://gitlab.freedesktop.org/mesa/deqp-runner
- bin/gfx-nsbind, lib/libdeqp_stdout.so, run.sh, caselists/: OpenBook, Apache-2.0 (scripts/graphics in the OpenBook repo).
EOF

# 4. what this payload is
python3 - "$PL/VERSION.json" <<EOF
import hashlib, json, os, sys
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
props = dict(l.strip().split("=", 1) for l in open("$P/system/build.prop") if "=" in l and not l.startswith("#"))
cl = json.load(open("$PL/caselists/caselists.json"))
json.dump({"schema": "openbook-gfx-payload/1", "name": "$NAME", "repo": "$(git -C "$R" rev-parse HEAD)",
  "product_fingerprint": props.get("ro.system.build.fingerprint"),
  "deqp": "$(git -C "$T/external/deqp" rev-parse HEAD)", "angle": "$(git -C "$T/external/angle" rev-parse HEAD)",
  "deqp_binary64": sha("$PL/bin/deqp-binary64"),
  "radv_nonstrict": sha("$PL/radv-nonstrict/vulkan.radv.so") if os.path.exists("$PL/radv-nonstrict/vulkan.radv.so") else None,
  "apps": {f: sha("$PL/apk/" + f) for f in sorted(os.listdir("$PL/apk"))},
  "deqp_runner": open("$G/bin/deqp-runner.txt").readline().strip(),
  "caselists": {k: {"cases": v["cases"], "stride": v["stride"], "sha256": v["sha256"]} for k, v in cl["suites"].items()}},
  open(sys.argv[1], "w"), indent=1)
EOF

# 5. the add-on
"$D" env SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1792195200}" python3 "$R/scripts/graphics/mkaddon.py" \
  --payload "$PL" --live-init "$W/openbook-gfx-init" --out "$O/$NAME-addon" --name "$NAME"
du -sh "$O/$NAME-addon"
echo "add-on: $O/$NAME-addon ($O/$NAME-addon.json); log: $LOG"
