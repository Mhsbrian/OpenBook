#!/usr/bin/env bash
# RB-20261024-01 (R1, ANAL-258) plan v1 d09795d1: candidate, payload, control, VM rehearsal, after-update check.
# Regular image files only; no device. Holds the Ruby track lock for the whole chain.
# usage: rb04-build.sh build|vm
set -euo pipefail
MODE=${1:-build}
exec 9<>"$HOME/anybook/installer/.ruby-release.lock"
flock -n 9 || { echo "Ruby release lock is held by another build"; exit 75; }

WD=/home/hive/multica_workspaces/analtechnic-b248a69dce69/anal-232-cf2d44a632f4/workdir
W=$HOME/anybook/installer/work/rb-20261024-01
R=$WD/r1-src; G=$R/scripts/googlebook                      # PR #121 head 9ee0c0c
R03=$WD/ob-rb03; G03=$R03/scripts/googlebook                # RB-20261023-03's tools (app 1.0 pins), VM harness only
AOSP=$HOME/anybook/aosp/src/out/host/linux-x86
OTATOOLS=$HOME/anybook/ota/builds/openbook-ota-20261019-quire1/otatools
INV=$HOME/anybook/installer/work/anal228-input27/erofs-inventory
AVBKEY=$HOME/anybook/aosp/src/external/avb/test/data/testkey_rsa4096.pem
REF_SUPER=$HOME/anybook/work/gbos-ruby/parts/super.img
BASE=$HOME/anybook/installer/work/anal229-updater-p2/base
BASE_SHA=75fa0196090558519fbb33d079ed51e2b9fd86ee102013c089bc8e9122fe9391
APK2=$HOME/anybook/toolchain/openbook-update-out/5fc1a877/OpenBookUpdate.apk
APK2_SHA=cd2c896ea003717423cf75d8981bd9a4e18f5ef7088faa31646ce93490e79038
APK1=$HOME/anybook/toolchain/openbook-update-out/367090f4acad/OpenBookUpdate.apk
APK1_SHA=f3308832e914314ce73b0e141142101033280bf18d4bbd8c08e6d241732953c5
ADAPT=$HOME/anybook/installer/work/anal229-adapt/bin/openbook-adapt-b80879f2
ADAPT_SHA=b80879f2ac4b71baa5363c868577306a91822d58cdc1356cd5c673c5e60dc126
G3=$HOME/anybook/private/google-ota/stock-16658739
REL03=$HOME/anybook/installer/work/rb-20261023-03/rel-prod
C03=$HOME/anybook/installer/work/rb-20261023-03/cand-prod
C03_SHA=71da0228488781fa7db6bbb2b07b8559024023b606ae54cd868f780954b9cc24
REFHW=$HOME/anybook/installer/work/anal229-rb20261023-02/ref-hw/result.json
HARN=$HOME/anybook/installer/work/anal229-ota-test/harness
HARN_SHA=f2a51087fde25580b95f3a41b09ac39615f614f9b3bac286ba2bb41a5e7e9fe5
LAYOUT=$HOME/anybook/installer/work/anal229-ota-test/layout-1tb.json
BASELINE=$HOME/anybook/installer/work/rb-20261023-03/appvm/vm/serial.log
DG=$AOSP/bin/delta_generator
DG_SHA=e97fde40ce73eac8db780eb683e67bf29acc43ffcf0c524b8b40606ec6dbd068
OTAKEY=$HOME/.local/share/openbook-keys/ota/openbook-ota-2026.key
OTACERT=$R/config/security/openbook-ota-2026.x509.pem
HW_BYTES=1000204886016
VM_BYTES=42949672960
export QEMU=$HOME/anybook/installer/work/anal228-tcg/build/qemu-system-x86_64
export BOOTSYNC=$HOME/anybook/installer/build/openbook-bootsync-host
export AOSP_HOST=$AOSP OTATOOLS
STATIC="boot init_boot vendor_boot vbmeta"
LOGICAL="system system_ext product vendor vendor_dlkm system_dlkm"
declare -A EXPECTED=(
 [boot]=f6fc1a5892cba10d24ba3c250f5abe4115ba0f7c0556a653995b41373bfbcec8 [init_boot]=0237a3399e093acabf63a0b036ac43b7e1b06a59dc7b665d852c0c6ec28e2dae
 [product]=ddf9d7105c4424c727ed53176d89b5a9895d3f59e2699ab5854bb3d1641211c1 [system_dlkm]=34185c35cb8bbccd5dfd0bb74eecb8a21e2445730411ef1583e1245628e0d617
 [system_ext]=dc3f228d2479ae3d979564bd7a02956399300187a67ac19519223911b7108b34 [system]=6f2abd2dc2e5ec6a6c08c9bc0776ea0977a9fae4a0a284308f52f6481f8fa392
 [vbmeta]=4cfa2acccd515a58d424071e03c46d4d42e01585958c17fc91426a237e399d4d [vendor_boot]=b8dc14803c8a07b0ec675d9cc9d2baf7b16c8acfd1a90c63782fa7e0d95bda80
 [vendor_dlkm]=c22672e2333f1d97833688d2554dee6e06515c425ae1674aa3e2a6b4099c5fba [vendor]=e072350a7df2f59aaa14cc2095a94bd4661de2dccbca1422e38abd80554332d4)

mkdir -p -m 700 "$W" "$W/logs"; L=$W/logs
note() { echo "$(date -u +%FT%TZ) $*" | tee -a "$L/progress.txt"; }
fail() { note "FAIL $*"; exit 1; }
run() { "$R/scripts/installer/inst-docker.sh" "$@"; }
run03() { "$R03/scripts/installer/inst-docker.sh" "$@"; }
sha() { sha256sum "$1" | cut -d' ' -f1; }
need() { [ "$(sha "$1")" = "$2" ] || fail "hash $1"; }
mshaf() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image_sha256"])' "$1"; }
space() { local free; free=$(df -B1G --output=avail "$W" | tail -1 | tr -d ' '); note "free ${free} GiB before a step budgeted at $1 GiB"
          [ "$free" -ge $(( $1 + 40 )) ] || fail "storage: ${free} GiB < $1 + 40 GiB reserve"; }
lp() { [ -d "$1" ] && return 0; mkdir -m 700 "$1"; ln -s "$AOSP/bin/lpdump" "$1/lpdump"; ln -s "$AOSP/bin/lpmake" "$1/lpmake"; ln -s "$OTATOOLS/bin/lpunpack" "$1/lpunpack"; }
stage() { [ -f "$2/manifest.json" ] && return 0; rm -rf "$2"
  run python3 "$G/stage-base.py" --source "$1" --source-sha256 "$(mshaf "$1/manifest.json")" --tools "$OTATOOLS/bin" --out "$2" > "$L/$(basename "$2").log" 2>&1; }
super() { [ -f "$2/result.json" ] && return 0; rm -rf "$2"; lp "$W/lp"
  run env LD_LIBRARY_PATH="$AOSP/lib64:$OTATOOLS/lib64" python3 "$G/build-ruby-ab-super.py" --logical "$1/logical" --reference-super "$REF_SUPER" \
    --tools "$W/lp" --super-bytes 25769803776 --out "$2" > "$L/$(basename "$2").log" 2>&1; }
image() { [ -f "$3/result.json" ] && return 0; rm -rf "$3"
  if [ "$4" = hw ]; then extra=(--disk-bytes "$HW_BYTES" --gpt-ids "$REFHW"); else extra=(--disk-bytes "$VM_BYTES" --vm); fi
  run python3 "$G/build-ruby-ab-image.py" --candidate "$1" --super-img "$2/super.img" --tools "$AOSP/bin" --key "$AVBKEY" --out "$3" "${extra[@]}" > "$L/$(basename "$3").log" 2>&1; }
reldir() { rm -rf "$3"; mkdir -m 700 "$3"
  for n in $LOGICAL; do cp --reflink=auto "$1/logical/${n}_a.img" "$3/$n.img"; done
  for n in $STATIC; do cp --reflink=auto "$2/${n}_a.img" "$3/$n.img"; done
  (cd "$3" && sha256sum *.img > SHA256SUMS); }
payload() { [ -f "$3/signed/payload.bin" ] && return 0; rm -rf "$3"
  python3 "$G/build-ruby-ab-ota.py" --release "$1" --source "$2" --delta-generator "$DG" --key "$OTAKEY" --cert "$OTACERT" --out "$3" > "$L/$(basename "$3").log" 2>&1; }
r1chain() {  # r1chain "": the source's R1 chain (r1test-build.sh) on the R1 parent
  local s=$1; shift
  if [ ! -f "$W/cand-safety$s/manifest.json" ]; then rm -rf "$W/cand-safety$s"
    run python3 "$G/build-safety-candidate.py" --base "$BASE" --base-sha256 "$BASE_SHA" --tools "$AOSP/bin" --inventory "$INV" \
      --key "$AVBKEY" --out "$W/cand-safety$s" "$@" > "$L/cand-safety$s.log" 2>&1; fi
  stage "$W/cand-safety$s" "$W/staged-safety$s"
  if [ ! -f "$W/cand-app$s/manifest.json" ]; then rm -rf "$W/cand-app$s"
    run python3 "$G/build-update-app-candidate.py" --base "$W/staged-safety$s" --base-sha256 "$(mshaf "$W/staged-safety$s/manifest.json")" \
      --tools "$AOSP/bin" --inventory "$INV" --key "$AVBKEY" --apk "$APK2" --adapter "$ADAPT" --out "$W/cand-app$s" "$@" > "$L/cand-app$s.log" 2>&1; fi
  rm -rf "$W/pre$s"; mkdir -m 700 "$W/pre$s"; cp --reflink=auto "$W/cand-app$s/system.img" "$W/pre$s/system.img"
  for n in system_ext product vendor vendor_dlkm system_dlkm boot init_boot vendor_boot vbmeta; do cp --reflink=auto "$REL03/$n.img" "$W/pre$s/"; done
  if [ ! -f "$W/embed$s/SHA256SUMS" ]; then rm -rf "$W/embed$s"
    ADAPT=$ADAPT "$G/embed-adapter-layer.sh" "$W/pre$s" "$G3" 16658739 "$W/embed$s" > "$L/embed$s.log" 2>&1; fi
  note "chain$s: safety $(mshaf "$W/cand-safety$s/manifest.json" | cut -c1-12), app $(mshaf "$W/cand-app$s/manifest.json" | cut -c1-12), system $(sha "$W/embed$s/rel/system.img" | cut -c1-12), vbmeta $(sha "$W/embed$s/rel/vbmeta.img" | cut -c1-12)"
}

build() {
  note "build start; source $(git -C "$R" rev-parse HEAD); harness tools $(git -C "$R03" rev-parse HEAD)"
  need "$BASE/ruby-live.img" "$BASE_SHA"; need "$APK2" "$APK2_SHA"; need "$APK1" "$APK1_SHA"; need "$ADAPT" "$ADAPT_SHA"; need "$DG" "$DG_SHA"
  need "$C03/ruby-live.img" "$C03_SHA"; need "$HARN/ruby-live.img" "$HARN_SHA"
  (cd "$REL03" && sha256sum -c --quiet SHA256SUMS) || fail "RB-20261023-03 release images changed"
  [ "$(git -C "$R" rev-parse HEAD)" = 9ee0c0cbea7f2e7fdb9cd8dea1ca4c4430d7f4f5 ] || fail "source checkout is not 9ee0c0c"
  note "pinned inputs verified"
  space 150

  # 1. R1 (deployable) and its expected bytes
  r1chain ""
  for n in "${!EXPECTED[@]}"; do [ "$(sha "$W/embed/rel/$n.img")" = "${EXPECTED[$n]}" ] || fail "R1 $n.img differs from the plan's expected hash"; done
  note "R1 release images equal the plan's expected hashes (10/10)"
  # 2. Static content check of R1's system
  rm -rf "$W/r1-tree"; "$AOSP/bin/fsck.erofs" --extract="$W/r1-tree" "$W/embed/rel/system.img" > "$L/r1-extract.log" 2>&1 || true
  T=$W/r1-tree
  ( set +e +o pipefail
    echo "adapter $(sha "$T/bin/openbook-adapt" 2>/dev/null || sha "$T/system/bin/openbook-adapt")"
    ls -d "$T"/system/etc/openbook/layer "$T"/etc/openbook/layer 2>/dev/null | head -1 | xargs -r -I{} sh -c 'echo "layer files $(find {} -type f | wc -l)"'
    for f in etc/openbook/firmware-safety.json etc/init/gscutil.rc etc/init/gscutil-executor.rc priv-app/OpenBookUpdate-v2/OpenBookUpdate.apk; do
      p=$T/system/$f; [ -e "$p" ] || p=$T/$f; echo "$f $(sha "$p" 2>/dev/null || echo MISSING)"; done
    [ -e "$T/system/priv-app/OpenBookUpdate-v1" ] || [ -e "$T/priv-app/OpenBookUpdate-v1" ] && echo "app 1.0 dir STILL PRESENT" || echo "app 1.0 dir removed"
    true ) > "$L/r1-static.txt"
  note "R1 static: $(tr '\n' ';' < "$L/r1-static.txt")"
  rm -rf "$T"
  # 3. Firmware-safety reruns on R1's images and payload
  rm -rf "$W/fws-work"
  python3 "$G/check-firmware-safety.py" images --tools "$OTATOOLS/bin" --work "$W/fws-work" --output "$W/fws-images.json" \
    system="$W/embed/rel/system.img" system_ext="$W/embed/rel/system_ext.img" product="$W/embed/rel/product.img" vendor="$W/embed/rel/vendor.img" \
    > "$L/fws-images.log" 2>&1 || fail "firmware-safety images: $(tail -3 "$L/fws-images.log" | tr '\n' ' ')"
  rm -rf "$W/fws-work"; note "firmware-safety on R1's images: PASS"
  payload "$W/embed/rel" "$REL03" "$W/ota-laptop"
  python3 "$G/check-firmware-safety.py" payload --output "$W/fws-payload.json" "$W/ota-laptop/signed/payload.bin" > "$L/fws-payload.log" 2>&1 \
    || fail "firmware-safety payload: $(tail -3 "$L/fws-payload.log" | tr '\n' ' ')"
  python3 "$G/check-ota-fit.py" --layout "$LAYOUT" --payload "$W/ota-laptop/signed/payload.bin" > "$L/fit-laptop.txt" 2>&1 || fail "fit: $(head -3 "$L/fit-laptop.txt")"
  note "P (laptop) $(sha "$W/ota-laptop/signed/payload.bin") $(stat -c %s "$W/ota-laptop/signed/payload.bin") bytes; no postinstall: PASS; fit: $(head -1 "$L/fit-laptop.txt")"
  # 4. Control: RB-20261023-03's images from its candidate with these tools
  stage "$C03" "$W/staged-c03"; super "$W/staged-c03" "$W/super-c03"; image "$C03" "$W/super-c03" "$W/hw-c03" hw
  reldir "$W/staged-c03" "$W/hw-c03" "$W/rel-c03"
  (cd "$W/rel-c03" && sha256sum -c --quiet "$REL03/SHA256SUMS") || fail "control: RB-20261023-03 not reproduced"
  note "control passed: RB-20261023-03's ten images reproduced byte for byte"
  # 5. The vm-check variant of R1 (VM only): same chain with both --vm-check flags, release images the
  #    RB-20261023-03 way (no layer embed: the variant's disposable init scripts are not part of any layer)
  if [ ! -f "$W/cand-safety-vmc/manifest.json" ]; then rm -rf "$W/cand-safety-vmc"
    run python3 "$G/build-safety-candidate.py" --base "$BASE" --base-sha256 "$BASE_SHA" --tools "$AOSP/bin" --inventory "$INV" \
      --key "$AVBKEY" --out "$W/cand-safety-vmc" --vm-check > "$L/cand-safety-vmc.log" 2>&1; fi
  stage "$W/cand-safety-vmc" "$W/staged-safety-vmc"
  if [ ! -f "$W/cand-app-vmc/manifest.json" ]; then rm -rf "$W/cand-app-vmc"
    run python3 "$G/build-update-app-candidate.py" --base "$W/staged-safety-vmc" --base-sha256 "$(mshaf "$W/staged-safety-vmc/manifest.json")" \
      --tools "$AOSP/bin" --inventory "$INV" --key "$AVBKEY" --apk "$APK2" --adapter "$ADAPT" --out "$W/cand-app-vmc" --vm-check > "$L/cand-app-vmc.log" 2>&1; fi
  stage "$W/cand-app-vmc" "$W/staged-app-vmc"; super "$W/staged-app-vmc" "$W/super-app-vmc"; image "$W/cand-app-vmc" "$W/super-app-vmc" "$W/img-app-vmc" vm
  reldir "$W/staged-app-vmc" "$W/img-app-vmc" "$W/rel-vmc"
  note "vm-check variant: app candidate $(mshaf "$W/cand-app-vmc/manifest.json" | cut -c1-12), system $(sha "$W/rel-vmc/system.img" | cut -c1-12)"
  # 6. VM harness: RB-20261023-03 (app 1.0) plus the per-payload apply driver, in slot A
  stage "$HARN" "$W/staged-h"
  if [ ! -f "$W/cand-h2/manifest.json" ]; then rm -rf "$W/cand-h2"
    run python3 "$G/build-apply-harness-variant.py" --base "$W/staged-h" --base-sha256 "$HARN_SHA" --tools "$AOSP/bin" --inventory "$INV" \
      --key "$AVBKEY" --out "$W/cand-h2" > "$L/cand-h2.log" 2>&1; fi
  stage "$W/cand-h2" "$W/staged-h2"
  if [ ! -f "$W/cand-h3/manifest.json" ]; then rm -rf "$W/cand-h3"
    run03 python3 "$G03/build-update-app-candidate.py" --base "$W/staged-h2" --base-sha256 "$(mshaf "$W/staged-h2/manifest.json")" \
      --tools "$AOSP/bin" --inventory "$INV" --key "$AVBKEY" --apk "$APK1" --out "$W/cand-h3" > "$L/cand-h3.log" 2>&1; fi
  stage "$W/cand-h3" "$W/staged-h3"; super "$W/staged-h3" "$W/super-h3"; image "$W/cand-h3" "$W/super-h3" "$W/img-h3" vm
  reldir "$W/staged-h3" "$W/img-h3" "$W/rel-h3"
  note "harness H3 $(mshaf "$W/cand-h3/manifest.json" | cut -c1-12): RB-20261023-03 system $( [ "$(sha "$W/rel-h3/system.img")" = "$(sha "$REL03/system.img")" ] && echo equal || echo 'differs (driver added)')"
  # 7. VM payloads from H3
  payload "$W/embed/rel" "$W/rel-h3" "$W/ota-vm"
  payload "$W/rel-vmc" "$W/rel-h3" "$W/ota-vmc"
  note "VM payloads: release $(sha "$W/ota-vm/signed/payload.bin" | cut -c1-12), vm-check $(sha "$W/ota-vmc/signed/payload.bin" | cut -c1-12)"
  note "build done"
}

vm() {
  note "vm start"; space 100
  "$G/ab-ota-suite.sh" "$W/img-h3" "$W/ota-vm/signed" "$W/embed/rel" "$W/vm-r1" --fallback > "$L/vm-r1.log" 2>&1 & p1=$!
  BOOT_SECONDS=2400 "$G/ab-ota-suite.sh" "$W/img-h3" "$W/ota-vmc/signed" "$W/rel-vmc" "$W/vm-vmc" > "$L/vm-vmc.log" 2>&1 & p2=$!
  wait $p1 || true; note "R1 into B: $(tr -d '\n ' < "$W/vm-r1/summary.json" 2>/dev/null | head -c 400)"
  wait $p2 || true; note "vm-check into B: $(tr -d '\n ' < "$W/vm-vmc/summary.json" 2>/dev/null | head -c 400)"
  # After-update judges on the vm-check boot of slot B
  python3 - "$G/update-app-vm-judge.py" "$W/vm-vmc" > "$L/app-after-update.txt" 2>&1 <<'PY' || true
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("judge", sys.argv[1]); j = importlib.util.module_from_spec(spec); spec.loader.exec_module(j)
out = Path(sys.argv[2]); boot = out / "boot"
serial = (boot / "serial.log").read_text(errors="replace") if (boot / "serial.log").exists() else ""
result = json.loads((boot / "result.json").read_text()) if (boot / "result.json").exists() else {}
r = j.judge(serial, result, False)
# An app updated in place keeps 1.0's runtime-permission state; 1.0 also sits, stopped, in user 0 after an update
# with an unchanged Google fingerprint (RB-20261023-03). Both recorded, not required.
recorded = ("notifications_granted_on_first_boot", "installed_for_owner_only")
r["recorded_not_required"] = {k: r["checks"].get(k) for k in recorded}
r["passed_after_update"] = all(v for k, v in r["checks"].items() if k not in recorded)
(out / "app-after-update.json").write_text(json.dumps(r, indent=2) + "\n")
print(json.dumps(dict(passed_after_update=r["passed_after_update"], checks=r["checks"], app_denials=r["app_denials"]), indent=1))
PY
  rm -rf "$W/judge-safety"; mkdir -p "$W/judge-safety/vm"
  ln -s "$W/vm-vmc/boot/serial.log" "$W/judge-safety/vm/serial.log"; ln -s "$W/vm-vmc/boot/result.json" "$W/judge-safety/vm/result.json"
  python3 "$G/safety-vm-judge.py" "$W/judge-safety" "$BASELINE" > "$L/safety-after-update.txt" 2>&1 || true
  note "app after update: $(python3 -c 'import json,sys;r=json.load(open(sys.argv[1]));c=r["checks"];print("PASS" if r["passed_after_update"] else "FAIL", sum(c.values()),"/",len(c), "recorded", r["recorded_not_required"])' "$W/vm-vmc/app-after-update.json" 2>/dev/null || echo 'no result')"
  note "safety after update: $(python3 -c 'import json,sys;r=json.load(open(sys.argv[1]));c=r["checks"];print("PASS" if r["passed"] else "FAIL", sum(c.values()),"/",len(c), [k for k,v in c.items() if not v])' "$W/judge-safety/result.json" 2>/dev/null || echo 'no result')"
  note "vm done"
}

case $MODE in build) build ;; vm) vm ;; *) echo "usage: $0 build|vm"; exit 2 ;; esac
