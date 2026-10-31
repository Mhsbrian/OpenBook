#!/usr/bin/env bash
# Boot the AnyBook kernel (ANAL-171 dist) under our aosp_cf_x86_64_pc userspace (ANAL-168) in Cuttlefish,
# capture module state, tear down. Uses cvd's own kernel-swap path: --kernel_path=<bzImage> and
# --initramfs_path=<module tree from kernel-cf-modset.py>. assemble_cvd then rebuilds vendor_boot, vendor_dlkm,
# system_dlkm, super and the vbmeta images from that tree. Nothing under ~/anybook/aosp is modified: the product
# images and host package are snapshotted (reflink copies) into ~/anybook/kernel/cf once.
#
# usage: kernel-cf-boot.sh [anybook|board]   anybook (default): GKI + AnyBook vendor modules + compatible board modules
#                                            board: GKI + Cuttlefish board modules only (control)
# env: KCF_DIST        AnyBook dist (default ~/anybook/kernel/dist/anybook-amd-gbos-16302624)
#      KCF_BOARD       //common-modules/virtual-device:virtual_device_x86_64_dist built on the same GKI
#                      (default ~/anybook/kernel/dist/anybook-vdev-gbos-16302624)
#      KCF_VENDOR_LIST AnyBook vendor modules (default kernel/cuttlefish/vendor-modules.txt)
#      KCF_AOSP_OUT    AOSP out/ to snapshot (default ~/anybook/aosp/src/out); KCF_RESNAP=1 takes a new snapshot
#      KCF_LOGS        log dir (default ~/anybook/logs/kernel/cf-<mode>-<ts>)
#      KCF_BLOCK       AnyBook modules to blocklist in this VM image, probed by hand after boot instead
#                      (default: asus-nb-wmi.ko, which needs the ASUS WMI GUID that crosvm's ACPI lacks)
#      CF_*            passed to scripts/cf-boot.sh. Defaults here: CF_NAME=anybook-cf-kernel, CF_ADB_PORT=16572,
#                      CF_WEBRTC_PORT=11472, CF_BOOT_TIMEOUT=600, guest vsock CID 172 (vhost-vsock CIDs are global
#                      to the host, and other Cuttlefish runs use the default CID 3)
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
MODE=${1:-anybook}; case $MODE in anybook|board) ;; *) sed -n '2,20p' "$0"; exit 2 ;; esac
A=$HOME/anybook; KCF=$A/kernel/cf; DEV=vsoc_x86_64_only
DIST=${KCF_DIST:-$A/kernel/dist/anybook-amd-gbos-16302624}
BOARD=${KCF_BOARD:-$A/kernel/dist/anybook-vdev-gbos-16302624}
VLIST=${KCF_VENDOR_LIST:-$R/kernel/cuttlefish/vendor-modules.txt}
AOUT=${KCF_AOSP_OUT:-$A/aosp/src/out}
SNAP=$KCF/snapshot; SOUT=$SNAP/out; SPROD=$SOUT/target/product/$DEV
L=${KCF_LOGS:-$A/logs/kernel/cf-$MODE-$(date -u +%Y%m%dT%H%M%SZ)}; mkdir -p "$L" "$KCF/logs/aosp"
stamp(){ echo "=== $(date -u +%FT%TZ) $*" | tee -a "$L/kernel-cf-boot.log"; }

# cf-boot.sh settings: our own container, ports, staging dir and logs. ANYBOOK_HOME only moves its cf-latest
# link (and unused defaults) into our area, so ANAL-168/169's ~/anybook/logs/aosp/cf-latest is left alone. It is
# set only on the cf-boot.sh calls, because kernel-docker.sh derives its mounts from it.
export CF_OUT=$SOUT CF_STAGE=$KCF/product CF_LOGS=$L
export CF_NAME=${CF_NAME:-anybook-cf-kernel} CF_ADB_PORT=${CF_ADB_PORT:-16572} CF_WEBRTC_PORT=${CF_WEBRTC_PORT:-11472}
export CF_BOOT_TIMEOUT=${CF_BOOT_TIMEOUT:-600}
export CF_ARGS="--kernel_path=/cf/product/anybook-kernel --initramfs_path=/cf/product/anybook-initramfs.img --vsock_guest_cid=172 ${CF_ARGS:-}"
SERIAL=127.0.0.1:6520
adb_(){ docker exec -e PATH="/root/cvd-host/bin:/usr/bin:/bin" "$CF_NAME" adb -s "$SERIAL" "$@"; }

snapshot(){
  if docker ps --format '{{.Names}}' | grep -qx anybook-aosp-build; then
    echo "an AOSP build (anybook-aosp-build) is running; its out/ may be half-written. Snapshot later." >&2; exit 1
  fi
  stamp "snapshot $AOUT/target/product/$DEV -> $SPROD (reflink)"
  rm -rf "$SOUT"; mkdir -p "$SPROD" "$SOUT/host/linux-x86"
  find "$AOUT/target/product/$DEV" -maxdepth 1 -type f -exec cp --reflink=auto --preserve=timestamps -t "$SPROD" {} +
  cp --reflink=auto --preserve=timestamps "$AOUT/host/linux-x86/cvd-host_package.tar.gz" "$SOUT/host/linux-x86/"
  cp "$AOUT/../device/google/cuttlefish/shared/modules.blocklist" "$SNAP/modules.blocklist"
  { echo "source: $AOUT (snapshot $(date -u +%FT%TZ))"
    # PRODUCT_OUT (vsoc_x86_64_only) is shared by every Cuttlefish x86_64-only product built in that tree, so name
    # each fingerprint file and its mtime. The device's ro.*.build.fingerprint/date (getprop.txt) is the final word.
    for f in "$SPROD"/build_fingerprint-*.txt; do
      echo "fingerprint file $(basename "$f") ($(date -u -r "$f" +%FT%TZ)): $(cat "$f")"; done
    n=$(find "$SPROD" -maxdepth 1 -name 'build_fingerprint-*.txt' | wc -l)
    [ "$n" -le 1 ] || echo "WARNING: $n products have built into this PRODUCT_OUT; check getprop ro.*.build.fingerprint"
    echo "device/google/cuttlefish: $(git -C "$AOUT/../device/google/cuttlefish" rev-parse HEAD 2>/dev/null)"
    (cd "$SOUT" && sha256sum target/product/$DEV/*.img host/linux-x86/cvd-host_package.tar.gz)
    (cd "$SNAP" && sha256sum modules.blocklist)
  } > "$SNAP/provenance.txt"
  touch "$SNAP/.done"
}

[ -f "$SNAP/.done" ] && [ -z "${KCF_RESNAP:-}" ] || snapshot
cp "$SNAP/provenance.txt" "$L/snapshot-provenance.txt"

BLOCK=(); [ "$MODE" = anybook ] && read -ra BLOCK <<< "${KCF_BLOCK-asus-nb-wmi.ko}"
stamp "module set ($MODE${BLOCK[*]:+, VM blocklist: ${BLOCK[*]}})"
MS=$KCF/modset-$MODE
"$R/scripts/kernel-docker.sh" python3 "$R/scripts/kernel-cf-modset.py" --mode "$MODE" --gki "$DIST" --board "$BOARD" \
  --vendor-list "$VLIST" --blocklist "$SNAP/modules.blocklist" --out "$MS" \
  "${BLOCK[@]/#/--block=}" > "$L/modset-build.log"
cp "$MS/modset.md" "$MS/modset.tsv" "$MS/depmod.log" "$L/"
cp --reflink=auto "$DIST/bzImage" "$SPROD/anybook-kernel"
cp --reflink=auto "$MS/initramfs.img" "$SPROD/anybook-initramfs.img"
{ sha256sum "$DIST/bzImage" "$MS/initramfs.img"; cat "$DIST/linux_banner.txt"; } > "$L/kernel-inputs.txt"

stamp "cf-boot.sh all ($CF_NAME, adb 127.0.0.1:$CF_ADB_PORT, WebRTC 127.0.0.1:$CF_WEBRTC_PORT)"
rc=0; ANYBOOK_HOME=$KCF CF_KEEP=1 "$R/scripts/cf-boot.sh" all || rc=$?
stamp "cf-boot.sh exit $rc"

# Module and driver state, guest side (only if adb answers).
if timeout 30 docker exec -e PATH="/root/cvd-host/bin:/usr/bin:/bin" "$CF_NAME" adb -s "$SERIAL" wait-for-device 2>/dev/null; then
  adb_ root >/dev/null 2>&1 || true; sleep 2
  adb_ shell cat /proc/modules > "$L/proc-modules.txt" 2>&1 || true
  adb_ shell 'cat /proc/cmdline; echo; cat /proc/bootconfig' > "$L/cmdline-bootconfig.txt" 2>&1 || true
  for p in /vendor/lib/modules /system/lib/modules; do
    adb_ shell "cd $p && find . -name '*.ko' | sort; echo '--- modules.load'; cat modules.load; echo '--- modules.blocklist'; cat modules.blocklist 2>/dev/null"
  done > "$L/dlkm-contents.txt" 2>&1 || true
  # shellcheck disable=SC2016  # expanded in the guest
  adb_ shell 'echo "tainted=$(cat /proc/sys/kernel/tainted)"
    for m in /sys/module/*/taint; do t=$(cat $m); [ -n "$t" ] && echo "${m%/taint}: $t"; done
    echo "vendor.dlkm.modules.ready=$(getprop vendor.dlkm.modules.ready)"
    echo "--- cpufreq"; ls /sys/devices/system/cpu/cpufreq/ 2>&1
    cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver 2>&1
    cat /sys/devices/system/cpu/amd_pstate/status 2>&1
    echo "--- drm"; ls -l /dev/dri 2>&1
    for c in /sys/class/drm/card?; do echo "$c driver=$(basename $(readlink $c/device/driver))"; done
    echo "--- amdgpu"; cat /sys/module/amdgpu/initstate 2>&1; ls /sys/bus/pci/drivers/amdgpu 2>&1
    echo "--- pci"; for d in /sys/bus/pci/devices/*; do
      echo "$(basename $d) $(cat $d/vendor):$(cat $d/device) class=$(cat $d/class) driver=$(basename $(readlink $d/driver) 2>/dev/null)"; done' \
    > "$L/drivers.txt" 2>&1 || true
  # The VM-blocklisted AnyBook modules, loaded by hand: the result is the evidence for leaving them out.
  for m in "${BLOCK[@]}"; do
    echo "\$ modprobe -d /vendor/lib/modules $m"
    adb_ shell "/vendor/bin/modprobe -d /vendor/lib/modules $m 2>&1; echo exit=\$?; dmesg | grep -i '${m%.ko}' | tail -5"
  done > "$L/probe-blocklisted.txt" 2>&1 || true
else
  stamp "adb not reachable; host-side logs only"
fi
ANYBOOK_HOME=$KCF "$R/scripts/cf-boot.sh" down
for f in dmesg.txt logcat.txt kernel.log; do [ -s "$L/$f" ] && gzip -kf "$L/$f"; done
python3 -I "$R/scripts/kernel-cf-modstatus.py" "$L" > "$L/modload-status.md" || true
stamp "done: exit $rc, logs in $L"
exit "$rc"
