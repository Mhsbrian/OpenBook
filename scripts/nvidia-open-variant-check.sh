#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# ANAL-297: what NVIDIA's shipped nvidia-modeset.ko and nvidia-drm.ko do on top of nvidia.ko in an Android guest with
# no NVIDIA GPU. The shipped nvidia.ko leaves at the end of its init there (scripts/nvidia-open-guest-check.sh), so
# this loads the QEMU-only test build of it (scripts/kernel-nvidia-open-qemu-variant.sh: one test patch, never
# shipped) from the guest data disk, an extra NVMe disk with serial ANYBOOKGUESTDATA holding guest-data.tar. Then:
#   - the shipped nvidia-modeset and nvidia-drm from vendor_dlkm load on top with the lab's command (their inits call
#     NVIDIA's cores through kCFI-checked function pointers: nvidia-modeset's timers, nvidia-drm's NvKmsKapi table);
#   - /dev/nvidiactl and /dev/nvidia-modeset appear through uevents (kernel/patches/nvidia-open/0004), class
#     directories nvidia and nvidia-modeset exist, no per-GPU node (there is no GPU);
#   - nvidiactl-smoke: open, the RM API version check, an RM client allocated and freed, /dev/nvidia-modeset opened;
#   - everything unloads and the nodes go away; twice;
#   - no CFI failure, BUG, Oops, WARNING or GPF; SELinux enforcing, denials printed for the host-side comparison.
# Prints ok/FAIL lines and the facts behind them; exits with the number of failures.
fails=0
chk() {  # chk NAME COMMAND...: the command's status decides
  n=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok   $n"; else echo "FAIL $n"; fails=$((fails + 1)); fi
}
M=/vendor/lib/modules
MP="/vendor/bin/modprobe -s -d $M"
live() { grep -q "^$1 .* Live " /proc/modules; }

echo "== guest data disk"
dev=
for b in /sys/block/nvme*; do
  s=$(cat "$b/device/serial" 2>/dev/null | tr -d ' ')
  [ "$s" = ANYBOOKGUESTDATA ] && dev=/dev/block/${b##*/}
done
echo "disk: ${dev:-none}"
chk "guest data disk present" test -n "$dev"
mkdir -p data && tar -xf "$dev" -C data && ls -l data && sha256sum data/*
chk "test nvidia.ko and nvidiactl-smoke unpacked" test -f data/nvidia-qemu-test.ko -a -f data/nvidiactl-smoke
chmod 755 data/nvidiactl-smoke

dmesg -c > /dev/null 2>&1
round=1
while [ $round -le 2 ]; do
  echo "== round $round: load"
  insmod data/nvidia-qemu-test.ko NVreg_DynamicPowerManagement=0x02; echo "insmod nvidia (test build) rc=$?"
  $MP nvidia-drm; echo "modprobe nvidia-drm (shipped, lab command) rc=$?"
  grep -E '^(nvidia|nvidia_modeset|nvidia_drm) ' /proc/modules
  chk "round $round: nvidia (test build) live" live nvidia
  chk "round $round: nvidia_modeset live (shipped)" live nvidia_modeset
  chk "round $round: nvidia_drm live (shipped)" live nvidia_drm
  echo "nvidia_drm modeset=$(cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null)"
  chk "round $round: nvidia-drm modeset=1 from modules.options" grep -qx Y /sys/module/nvidia_drm/parameters/modeset
  sleep 2   # let ueventd create the nodes
  ls -lZ /dev/nvidia* 2>&1
  ls /sys/class/nvidia /sys/class/nvidia-modeset 2>&1
  chk "round $round: /dev/nvidiactl is 195:255" sh -c 'stat -c "%t:%T" /dev/nvidiactl | grep -qx "c3:ff"'
  chk "round $round: /dev/nvidia-modeset is 195:254" sh -c 'stat -c "%t:%T" /dev/nvidia-modeset | grep -qx "c3:fe"'
  chk "round $round: no per-GPU node without a GPU" sh -c '! ls /dev/nvidia[0-9]*'
  echo "== round $round: first ioctls"
  ./data/nvidiactl-smoke; src=$?
  chk "round $round: nvidiactl-smoke passes" test "$src" = 0
  echo "== round $round: unload"
  $MP -r nvidia-drm; echo "modprobe -r nvidia-drm rc=$?"
  grep -q '^nvidia ' /proc/modules && { rmmod nvidia; echo "rmmod nvidia rc=$?"; }
  sleep 2
  chk "round $round: nothing NVIDIA's loaded" sh -c '! grep -qE "^(nvidia|nvidia_modeset|nvidia_drm) " /proc/modules'
  chk "round $round: the nodes are gone" sh -c '! ls /dev/nvidiactl /dev/nvidia-modeset'
  round=$((round + 1))
done
dmesg > variant-dmesg.txt 2>&1
echo "== kernel log"
grep -E 'NVRM|nvidia|CFI|BUG|Oops|WARNING|general protection' variant-dmesg.txt | head -40
# nv_drm_probe_devices(): nvKms->enumerateGpus() is a kCFI-checked call from nvidia-drm into nvidia-modeset's core,
# which has type hashes but no checks of its own; this line is printed only after it returned.
chk "nvidia-drm's kCFI-checked call into NVIDIA's core returned (2 rounds)" sh -c "[ \$(grep -c 'nvidia-drm\\] No NVIDIA GPUs found' variant-dmesg.txt) = 2 ]"
chk "no CFI failure" sh -c "! grep -E 'CFI failure|kCFI|CFI violation' variant-dmesg.txt"
chk "no kernel BUG, Oops, WARNING or GPF" sh -c "! grep -E 'kernel BUG at|BUG: (unable|kernel)|Oops:|WARNING: CPU:|general protection fault' variant-dmesg.txt"
echo "tainted=$(cat /proc/sys/kernel/tainted)"
echo "== SELinux"
echo "getenforce: $(getenforce)"
denials=$( (cat variant-dmesg.txt; dmesg; logcat -d -b all 2>/dev/null) | grep 'avc:  denied' | sed 's/.*avc:/avc:/; s/ pid=[0-9]*//; s/ ino=[0-9]*//' | sort -u)
[ -n "$denials" ] && echo "$denials" | sed 's/^/DENIAL /'
echo "denials: $(echo -n "$denials" | grep -c .)"
chk "SELinux enforcing" sh -c 'getenforce | grep -q Enforcing'
echo "nvidia-open-variant-check: $fails failure(s)"
exit "$fails"
