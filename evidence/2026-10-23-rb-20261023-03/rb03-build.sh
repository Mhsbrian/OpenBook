#!/usr/bin/env bash
# RB-20261023-03 (ANAL-256) plan v1 d6b1633d: build candidate C, its release images, payloads, VM rehearsal.
# Regular image files only; no device is touched. Holds the Ruby track lock for the whole chain.
# usage: rb03-build.sh build|vm|vm2|all   (vm2: attempt 2 of the slot-A stages with the variant harness)
set -euo pipefail
MODE=${1:-all}
exec 9<>"$HOME/anybook/installer/.ruby-release.lock"
flock -n 9 || { echo "Ruby release lock is held by another build"; exit 75; }

W=$HOME/anybook/installer/work/rb-20261023-03
R=/home/hive/multica_workspaces/analtechnic-b248a69dce69/anal-232-cf2d44a632f4/workdir/ob-rb03
G=$R/scripts/googlebook
AOSP=$HOME/anybook/aosp/src/out/host/linux-x86
OTATOOLS=$HOME/anybook/ota/builds/openbook-ota-20261019-quire1/otatools
INV=$HOME/anybook/installer/work/anal228-input27/erofs-inventory
AVBKEY=$HOME/anybook/aosp/src/external/avb/test/data/testkey_rsa4096.pem
REF_SUPER=$HOME/anybook/work/gbos-ruby/parts/super.img
BASE=$HOME/anybook/installer/work/anal229-updater-p2/base
BASE_SHA=75fa0196090558519fbb33d079ed51e2b9fd86ee102013c089bc8e9122fe9391
APK=$HOME/anybook/toolchain/openbook-update-out/367090f4acad/OpenBookUpdate.apk
APK_SHA=f3308832e914314ce73b0e141142101033280bf18d4bbd8c08e6d241732953c5
REFHW=$HOME/anybook/installer/work/anal229-rb20261023-02/ref-hw/result.json
HARN=$HOME/anybook/installer/work/anal229-ota-test/harness
HARN_SHA=f2a51087fde25580b95f3a41b09ac39615f614f9b3bac286ba2bb41a5e7e9fe5
REL02=$HOME/anybook/installer/work/anal229-ota-test/rel-r2
SUMS02=/home/hive/multica_workspaces/analtechnic-b248a69dce69/anal-232-cf2d44a632f4/workdir/rel-r2.sha256
BASE_CAND=$HOME/anybook/installer/work/anal229-rebase-16658739/candidate   # unstaged (has vbmeta.img)
LAYOUT=$HOME/anybook/installer/work/anal229-ota-test/layout-1tb.json
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

mkdir -p -m 700 "$W" "$W/logs"
L=$W/logs
note() { echo "$(date -u +%FT%TZ) $*" | tee -a "$L/progress.txt"; }
run() { "$R/scripts/installer/inst-docker.sh" "$@"; }
sha() { sha256sum "$1" | cut -d' ' -f1; }
need() { [ "$(sha "$1")" = "$2" ] || { note "FAIL hash $1 != $2"; exit 1; }; }
space() {  # space NEED_GIB: stop before an allocation that would cut into the 40 GiB reserve
  local free; free=$(df -B1G --output=avail "$W" | tail -1 | tr -d ' ')
  note "free ${free} GiB before a step budgeted at $1 GiB"
  [ "$free" -ge $(( $1 + 40 )) ] || { note "FAIL storage: ${free} GiB free < $1 + 40 GiB reserve"; exit 1; }
}
lp() {  # lp DIR: the lp tool links build-ruby-ab-super.py expects
  [ -d "$1" ] && return 0
  mkdir -m 700 "$1"; ln -s "$AOSP/bin/lpdump" "$1/lpdump"; ln -s "$AOSP/bin/lpmake" "$1/lpmake"
  ln -s "$OTATOOLS/bin/lpunpack" "$1/lpunpack"
}
mshaf() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image_sha256"])' "$1"; }
stage() {  # stage CANDIDATE OUT
  [ -f "$2/manifest.json" ] && return 0; rm -rf "$2"
  run python3 "$G/stage-base.py" --source "$1" --source-sha256 "$(mshaf "$1/manifest.json")" \
    --tools "$OTATOOLS/bin" --out "$2" > "$L/$(basename "$2").log" 2>&1
}
super() {  # super STAGED OUT
  [ -f "$2/result.json" ] && return 0; rm -rf "$2"; lp "$W/lp"
  run env LD_LIBRARY_PATH="$AOSP/lib64:$OTATOOLS/lib64" python3 "$G/build-ruby-ab-super.py" \
    --logical "$1/logical" --reference-super "$REF_SUPER" --tools "$W/lp" --super-bytes 25769803776 \
    --out "$2" > "$L/$(basename "$2").log" 2>&1
}
image() {  # image CANDIDATE SUPER OUT hw|vm
  [ -f "$3/result.json" ] && return 0; rm -rf "$3"
  if [ "$4" = hw ]; then extra=(--disk-bytes "$HW_BYTES" --gpt-ids "$REFHW"); else extra=(--disk-bytes "$VM_BYTES" --vm); fi
  run python3 "$G/build-ruby-ab-image.py" --candidate "$1" --super-img "$2/super.img" --tools "$AOSP/bin" \
    --key "$AVBKEY" --out "$3" "${extra[@]}" > "$L/$(basename "$3").log" 2>&1
}
reldir() {  # reldir STAGED IMAGE OUT: the release's ten partition images, as payloads install them
  rm -rf "$3"; mkdir -m 700 "$3"
  for n in $LOGICAL; do cp --reflink=auto "$1/logical/${n}_a.img" "$3/$n.img"; done
  for n in $STATIC; do cp --reflink=auto "$2/${n}_a.img" "$3/$n.img"; done
  (cd "$3" && sha256sum *.img > SHA256SUMS)
}
payload() {  # payload RELEASE SOURCE OUT
  [ -f "$3/signed/payload.bin" ] && return 0; rm -rf "$3"
  python3 "$G/build-ruby-ab-ota.py" --release "$1" --source "$2" --delta-generator "$DG" --key "$OTAKEY" \
    --cert "$OTACERT" --out "$3" > "$L/$(basename "$3").log" 2>&1
}

build() {
  note "build start; repo $(git -C "$R" rev-parse HEAD)"
  # 0. Pinned inputs
  need "$BASE/ruby-live.img" "$BASE_SHA"; need "$APK" "$APK_SHA"; need "$DG" "$DG_SHA"
  need "$HARN/ruby-live.img" "$HARN_SHA"
  (cd "$REL02" && sha256sum -c --quiet "$SUMS02") || { note "FAIL RB-20261023-02 release images changed"; exit 1; }
  need "$BASE_CAND/ruby-live.img" "$BASE_SHA"
  note "pinned inputs verified (base, APK, delta_generator, harness, RB-20261023-02 release images)"
  space 120

  # 1. Candidate C (deployable)
  if [ ! -f "$W/cand-prod/manifest.json" ]; then
    rm -rf "$W/cand-prod"
    run python3 "$G/build-update-app-candidate.py" --base "$BASE" --base-sha256 "$BASE_SHA" --tools "$AOSP/bin" \
      --inventory "$INV" --key "$AVBKEY" --apk "$APK" --out "$W/cand-prod" > "$L/cand-prod.log" 2>&1
  fi
  note "C built: $(mshaf "$W/cand-prod/manifest.json")"

  # 2. Control: the method must reproduce RB-20261023-02's installed images exactly
  super "$BASE" "$W/super-base"
  image "$BASE_CAND" "$W/super-base" "$W/hw-base" hw
  reldir "$BASE" "$W/hw-base" "$W/rel-base"
  if (cd "$W/rel-base" && sha256sum -c --quiet "$SUMS02"); then
    note "control passed: rebuilt RB-20261023-02 release images equal the installed ones (10/10)"
  else
    note "FAIL control: rebuilt RB-20261023-02 release images differ"; exit 1
  fi

  # 3. C's release images (hardware build: the laptop's GUIDs)
  stage "$W/cand-prod" "$W/staged-prod"
  super "$W/staged-prod" "$W/super-prod"
  image "$W/cand-prod" "$W/super-prod" "$W/hw-prod" hw
  reldir "$W/staged-prod" "$W/hw-prod" "$W/rel-prod"
  note "C release images: $(cd "$W/rel-prod" && sha256sum system.img vbmeta.img | tr '\n' ' ')"

  # 4. The VM apply harness (RB-20261023-02 + disposable apply driver), its disk and release images
  stage "$HARN" "$W/staged-h"
  super "$W/staged-h" "$W/super-h"
  image "$HARN" "$W/super-h" "$W/img-h" vm
  reldir "$W/staged-h" "$W/img-h" "$W/rel-h"
  note "harness disk and release images ready"

  # 5. Payloads: P for the laptop (from the installed RB-20261023-02), P1/P2 for the VM chain
  payload "$W/rel-prod" "$REL02" "$W/ota-laptop"
  payload "$W/rel-h" "$W/rel-h" "$W/ota-vm1"
  payload "$W/rel-prod" "$W/rel-h" "$W/ota-vm2"
  note "P (laptop) $(sha "$W/ota-laptop/signed/payload.bin"); P1 $(sha "$W/ota-vm1/signed/payload.bin"); P2 $(sha "$W/ota-vm2/signed/payload.bin")"
  python3 "$G/check-ota-fit.py" --layout "$LAYOUT" --payload "$W/ota-laptop/signed/payload.bin" > "$L/fit-laptop.txt" 2>&1 \
    && note "fit: $(head -1 "$L/fit-laptop.txt")" || { note "FAIL fit: $(head -3 "$L/fit-laptop.txt")"; exit 1; }
  note "build done"
}

appvm() {  # T2: the app on a fresh boot of the vm-check variant (also builds C', staged, image)
  "$G/update-app-vm.sh" "$W/appvm" "$APK" "$BASE" "$BASE_SHA" > "$L/appvm.log" 2>&1 || true
  note "T2 fresh-boot app VM finished: $(python3 -c 'import json,sys;r=json.load(open(sys.argv[1]));print("passed" if r["passed"] else "FAILED", sum(r["checks"].values()), "/", len(r["checks"]))' "$W/appvm/result.json" 2>/dev/null || echo 'no result')"
}

vm() {
  note "vm start"
  space 80
  appvm & app_pid=$!
  # P2': the vm-check variant into slot A, once update-app-vm.sh has built C' and its image
  # First update: into slot B (as on the laptop), then the release into slot A from B
  [ -f "$W/first/summary.json" ] || "$G/ab-ota-suite.sh" "$W/img-h" "$W/ota-vm1/signed" "$W/rel-h" "$W/first" > "$L/first.log" 2>&1 || true
  note "first (into B): $(tr -d '\n ' < "$W/first/summary.json" 2>/dev/null | head -c 300)"
  python3 -c 'import json,sys; s=json.load(open(sys.argv[1])); sys.exit(0 if all(s[k]["passed"] for k in ("apply","boot","verify")) else 1)' "$W/first/summary.json" \
    || { note "FAIL first stage; stopping before slot A"; wait $app_pid; exit 1; }
  while [ ! -f "$W/appvm/img/result.json" ] && kill -0 $app_pid 2>/dev/null; do sleep 30; done
  [ -f "$W/appvm/img/result.json" ] || { note "FAIL C' image missing"; wait $app_pid; exit 1; }
  reldir "$W/appvm/staged" "$W/appvm/img" "$W/rel-vmc"
  payload "$W/rel-vmc" "$W/rel-h" "$W/ota-vm2c"
  note "P2' $(sha "$W/ota-vm2c/signed/payload.bin")"
  "$G/ab-ota-suite-slot-a.sh" "$W/img-h" "$W/ota-vm2/signed" "$W/rel-prod" "$W/first" "$W/second-prod" --fallback \
    > "$L/second-prod.log" 2>&1 & p1=$!
  BOOT_SECONDS=2400 "$G/ab-ota-suite-slot-a.sh" "$W/img-h" "$W/ota-vm2c/signed" "$W/rel-vmc" "$W/first" "$W/second-vmc" \
    > "$L/second-vmc.log" 2>&1 & p2=$!
  wait $p1 || true; note "second-prod (B -> A, release): $(tr -d '\n ' < "$W/second-prod/summary.json" 2>/dev/null | head -c 400)"
  wait $p2 || true; note "second-vmc (B -> A, vm-check): $(tr -d '\n ' < "$W/second-vmc/summary.json" 2>/dev/null | head -c 400)"
  wait $app_pid || true
  note "vm done"
}

harness2() {  # the apply harness whose driver applies each payload drive once (two updates on one /data)
  if [ ! -f "$W/cand-h2/manifest.json" ]; then
    rm -rf "$W/cand-h2"
    run python3 "$G/build-apply-harness-variant.py" --base "$W/staged-h" --base-sha256 "$HARN_SHA" \
      --tools "$AOSP/bin" --inventory "$INV" --key "$AVBKEY" --out "$W/cand-h2" > "$L/cand-h2.log" 2>&1
  fi
  stage "$W/cand-h2" "$W/staged-h2"
  super "$W/staged-h2" "$W/super-h2"
  image "$W/cand-h2" "$W/super-h2" "$W/img-h2" vm
  reldir "$W/staged-h2" "$W/img-h2" "$W/rel-h2"
  payload "$W/rel-h2" "$W/rel-h" "$W/ota-vm1v"
  payload "$W/rel-prod" "$W/rel-h2" "$W/ota-vm2v"
  payload "$W/rel-vmc" "$W/rel-h2" "$W/ota-vm2cv"
  note "harness variant $(mshaf "$W/cand-h2/manifest.json"); P1v $(sha "$W/ota-vm1v/signed/payload.bin"); P2v $(sha "$W/ota-vm2v/signed/payload.bin"); P2v' $(sha "$W/ota-vm2cv/signed/payload.bin")"
}

vm2() {
  note "vm2 start (attempt 2: variant harness in slot B)"
  space 80
  harness2
  [ -f "$W/first2/summary.json" ] || "$G/ab-ota-suite.sh" "$W/img-h" "$W/ota-vm1v/signed" "$W/rel-h2" "$W/first2" > "$L/first2.log" 2>&1 || true
  note "first2 (into B): $(tr -d '\n ' < "$W/first2/summary.json" 2>/dev/null | head -c 300)"
  python3 -c 'import json,sys; s=json.load(open(sys.argv[1])); sys.exit(0 if all(s[k]["passed"] for k in ("apply","boot","verify")) else 1)' "$W/first2/summary.json" \
    || { note "FAIL first2 stage; stopping before slot A"; exit 1; }
  "$G/ab-ota-suite-slot-a.sh" "$W/img-h" "$W/ota-vm2v/signed" "$W/rel-prod" "$W/first2" "$W/second2-prod" --fallback \
    > "$L/second2-prod.log" 2>&1 & p1=$!
  BOOT_SECONDS=2400 "$G/ab-ota-suite-slot-a.sh" "$W/img-h" "$W/ota-vm2cv/signed" "$W/rel-vmc" "$W/first2" "$W/second2-vmc" \
    > "$L/second2-vmc.log" 2>&1 & p2=$!
  wait $p1 || true; note "second2-prod (B -> A, release): $(tr -d '\n ' < "$W/second2-prod/summary.json" 2>/dev/null | head -c 500)"
  wait $p2 || true; note "second2-vmc (B -> A, vm-check): $(tr -d '\n ' < "$W/second2-vmc/summary.json" 2>/dev/null | head -c 500)"
  python3 - "$G/update-app-vm-judge.py" "$W/second2-vmc" <<'PY' > "$L/app-after-update.txt" 2>&1 || true
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("judge", sys.argv[1]); j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(j)
out = Path(sys.argv[2]); boot = out / "boot"
serial = (boot / "serial.log").read_text(errors="replace") if (boot / "serial.log").exists() else ""
result = json.loads((boot / "result.json").read_text()) if (boot / "result.json").exists() else {}
r = j.judge(serial, result, False)
# An app that arrives by update keeps Android's runtime-permission state for existing users: the
# default grant applies on a first boot only, so the app asks once (expected, recorded, not a pass).
expected_after_update = {"notifications_granted_on_first_boot": False}
r["expected_after_update"] = expected_after_update
r["passed_after_update"] = all(v for k, v in r["checks"].items() if k not in expected_after_update)
r["boot_checks"] = result.get("checks")
(out / "app-after-update.json").write_text(json.dumps(r, indent=2) + "\n")
print(json.dumps(dict(passed_after_update=r["passed_after_update"], checks=r["checks"], app_denials=r["app_denials"]), indent=1))
PY
  note "app after update: $(python3 -c 'import json,sys;r=json.load(open(sys.argv[1]));c=r["checks"];print("passed" if r["passed_after_update"] else "FAILED", sum(c.values()), "/", len(c), "notifications", c.get("notifications_granted_on_first_boot"))' "$W/second2-vmc/app-after-update.json" 2>/dev/null || echo 'no result')"
  note "vm2 done"
}

case $MODE in
  build) build ;;
  vm) vm ;;
  vm2) vm2 ;;
  all) build; vm ;;
  *) echo "usage: $0 build|vm|all"; exit 2 ;;
esac
