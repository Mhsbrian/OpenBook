#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# ANAL-239: what the nouveau vendor modules did in an Android guest with no NVIDIA GPU. Runs as root inside the kernel
# QEMU check (scripts/kernel-g14-qemu.py --guest-check), next to copies of openbook-pc-setup.sh and its fixture test:
#   - nouveau and drm_gpuvm are live, with the options from vendor_dlkm's modules.options;
#   - nouveau registered its PCI driver and bound nothing, and no DRM node is nouveau's (card0/renderD128 unchanged);
#   - no nouveau error in the kernel log; SELinux enforcing, every denial printed as a DENIAL line (normalized) for a
#     host-side comparison with the same check on the kernel the laptop runs, since the test userspace has its own;
#   - openbook-pc-setup dgpu-pm and dgpu-report run here as root on the real sysfs, logging to logd;
#   - the hook's fixture tests pass under this guest's sh (mksh) and toybox.
# Prints ok/FAIL lines and the facts behind them; exits with the number of failures.
fails=0
chk() {  # chk NAME COMMAND...: the command's status decides
  n=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok   $n"; else echo "FAIL $n"; fails=$((fails + 1)); fi
}
P=/sys/module/nouveau/parameters
echo "== modules (/proc/modules)"
grep -E '^(nouveau|drm_gpuvm|amdgpu|virtio_gpu|drm_exec|drm_ttm_helper|drm_display_helper|wmi|video) ' /proc/modules
chk "nouveau is live" grep -q '^nouveau .* Live ' /proc/modules
chk "drm_gpuvm is live and used by nouveau" grep -q '^drm_gpuvm .*nouveau' /proc/modules
chk "amdgpu is live" grep -q '^amdgpu .* Live ' /proc/modules
echo "== modules.options and parameters"
cat /vendor/lib/modules/modules.options 2>&1 | grep -v '^#'
echo "runpm=$(cat $P/runpm) modeset=$(cat $P/modeset)"
chk "runpm=1 (modules.options)" grep -qx 1 $P/runpm
chk "modeset=2 (modules.options)" grep -qx 2 $P/modeset
echo "== nouveau PCI driver"
ls /sys/bus/pci/drivers/nouveau/
chk "nouveau registered a PCI driver" test -d /sys/bus/pci/drivers/nouveau
bound=$(ls /sys/bus/pci/drivers/nouveau/ | grep -c ':')
echo "bound devices: $bound"
chk "nouveau bound nothing" test "$bound" = 0
chk "no NVIDIA PCI function in this guest" sh -c '! grep -lx 0x10de /sys/bus/pci/devices/*/vendor'
echo "== DRM nodes"
for c in /sys/class/drm/card[0-9]* /sys/class/drm/renderD*; do
  [ -e "$c/device/driver" ] && echo "${c##*/} $(basename "$(readlink "$c/device/driver")")"
done
chk "no DRM node belongs to nouveau" sh -c '! for c in /sys/class/drm/*/device/driver; do readlink $c; done | grep -q nouveau'
# With a virtio-gpu device (the VM variant loads virtio-gpu in first stage): it must keep card0 and renderD128.
if [ -e /sys/class/drm/card0 ]; then
  chk "card0 is virtio_gpu's" sh -c 'readlink /sys/class/drm/card0/device/driver | grep -q virtio'
  chk "renderD128 is virtio_gpu's" sh -c 'readlink /sys/class/drm/renderD128/device/driver | grep -q virtio'
  chk "no card1 or renderD129 appeared" sh -c '! ls -d /sys/class/drm/card1 /sys/class/drm/renderD129'
fi
echo "== kernel log"
dmesg | grep -iE 'nouveau|drm_gpuvm|mxm' | tail -20
chk "no nouveau error or warning in the kernel log" sh -c "! dmesg | grep -iE 'nouveau.*(error|fail|warn)|warning:.*nouveau'"
chk "no kernel BUG, Oops, WARNING or GPF in the kernel log" sh -c "! dmesg | grep -E 'kernel BUG at|BUG: (unable|kernel)|Oops:|WARNING: CPU:|general protection fault'"
echo "tainted=$(cat /proc/sys/kernel/tainted)"
echo "== SELinux"
echo "getenforce: $(getenforce)"
denials=$( (dmesg; logcat -d -b all 2>/dev/null) | grep 'avc:  denied' | sed 's/.*avc:/avc:/; s/ pid=[0-9]*//; s/ ino=[0-9]*//' | sort -u)
[ -n "$denials" ] && echo "$denials" | sed 's/^/DENIAL /'
echo "denials: $(echo -n "$denials" | grep -c .)"
chk "SELinux enforcing" sh -c 'getenforce | grep -q Enforcing'
chk "no denial names nouveau, the GSP firmware or openbook-pc-setup" sh -c "! echo \"\$1\" | grep -iE 'nouveau|nvidia|openbook|vendor_firmware|modules.options'" _ "$denials"
echo "== openbook-pc-setup on this guest's sysfs (root)"
OPENBOOK_LOGCMD=/system/bin/log sh ./openbook-pc-setup.sh dgpu-pm; echo "dgpu-pm rc=$?"
OPENBOOK_LOGCMD=/system/bin/log OPENBOOK_SETTLE_S=0 sh ./openbook-pc-setup.sh dgpu-report qemu; echo "dgpu-report rc=$?"
logcat -d -s openbook-pc-setup | tail -12
chk "dgpu-pm reports nouveau's parameters to logd" sh -c "logcat -d -s openbook-pc-setup | grep -q 'nouveau: runpm=1 modeset=2 bound=\$'"
chk "dgpu-pm finds no NVIDIA GPU" sh -c "logcat -d -s openbook-pc-setup | grep -q 'no NVIDIA GPU enumerated'"
chk "dgpu-report says absent" sh -c "logcat -d -s openbook-pc-setup | grep -q 'dgpu-report: state=absent'"
echo "== fixture tests under this guest's sh and toybox"
TMPDIR=/data/local/tmp sh ./openbook-pc-setup-test.sh sh ./openbook-pc-setup.sh > fixtures.txt 2>&1; frc=$?
grep -v '^ok' fixtures.txt; echo "$(grep -c '^ok' fixtures.txt) ok"
chk "fixture tests pass under the guest's sh" test "$frc" = 0
echo "guest-check: $fails failure(s)"
exit "$fails"
