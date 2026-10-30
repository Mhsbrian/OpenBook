#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# ANAL-297: NVIDIA's open kernel modules in an Android guest with no NVIDIA GPU, on the kernel that carries their
# exports. Runs as root inside the kernel QEMU check (scripts/kernel-g14-qemu.py --guest-check), next to copies of
# openbook-pc-setup.sh, its fixture test, nouveau-guest-check.sh and lab-guest-check.sh:
#   - nvidia, nvidia-modeset and nvidia-drm are in vendor_dlkm and on its modules.blocklist, not in modules.load and
#     not live after boot; modules.options carries their options;
#   - each one's vermagic is the running kernel's, nvidia and nvidia-modeset import the GKI VFS namespace;
#   - the lab's load command (init.openbook.rc: modprobe nvidia-drm) gets as far as nvidia.ko's init, which ends with
#     -ENODEV and "NVRM: No NVIDIA GPU found." when there is no GPU, by NVIDIA's design. So symbol resolution, CRCs,
#     the namespace import, relocation, and the module's init and exit through NVIDIA's core (rm_init_rm and back)
#     run for real; nothing stays loaded. Three times;
#   - then ANAL-257's lab check still passes (nouveau and the sleep module, loaded and unloaded the lab's way);
#   - no unknown-symbol, CRC, namespace, CFI, BUG, Oops, WARNING or GPF line in the kernel log; SELinux enforcing,
#     every denial printed (normalized) for a host-side comparison with the same run on the baseline kernel.
# Prints ok/FAIL lines and the facts behind them; exits with the number of failures.
fails=0
chk() {  # chk NAME COMMAND...: the command's status decides
  n=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok   $n"; else echo "FAIL $n"; fails=$((fails + 1)); fi
}
M=/vendor/lib/modules
MP="/vendor/bin/modprobe -s -d $M"   # as init.openbook.rc's lab services run it
NV="nvidia nvidia-modeset nvidia-drm"
loaded() { grep -qE '^(nvidia|nvidia_modeset|nvidia_drm) ' /proc/modules; }

echo "== vendor_dlkm"
for m in $NV; do ls -l $M/$m.ko; done
grep -E 'nvidia' $M/modules.blocklist $M/modules.load $M/modules.dep
for m in $NV; do
  chk "$m.ko is in vendor_dlkm" test -f $M/$m.ko
  chk "$m.ko is blocklisted" grep -qx "blocklist $m.ko" $M/modules.blocklist
  chk "$m.ko is not in modules.load" sh -c "! grep -qx '$m.ko' $M/modules.load"
done
chk "none of them is live after boot" sh -c '! grep -qE "^(nvidia|nvidia_modeset|nvidia_drm) " /proc/modules'
echo "== modules.options"
grep -E '^options nvidia' $M/modules.options
chk "nvidia: NVreg_DynamicPowerManagement=0x02" grep -qx 'options nvidia NVreg_DynamicPowerManagement=0x02' $M/modules.options
chk "nvidia-drm: modeset=1" grep -qx 'options nvidia-drm modeset=1' $M/modules.options

echo "== modinfo"
rel=$(uname -r); echo "running kernel: $rel"
# toybox modinfo leaves out import_ns and scmversion, so those come straight from .modinfo.
for m in $NV; do
  modinfo $M/$m.ko | grep -E '^(vermagic|depends|license):' | sed "s/^/$m: /"
  grep -a -o -E '(import_ns|scmversion)=[A-Za-z0-9_.-]+' $M/$m.ko | sed "s/^/$m: /"
  chk "$m: vermagic is the running kernel's" sh -c "modinfo $M/$m.ko | grep -q '^vermagic: *$rel '"
done
chk "nvidia imports the GKI VFS namespace" grep -a -q 'import_ns=ANDROID_GKI_VFS_internal' $M/nvidia.ko
chk "nvidia-modeset imports the GKI VFS namespace" grep -a -q 'import_ns=ANDROID_GKI_VFS_internal' $M/nvidia-modeset.ko

echo "== the lab's load command, three times (no GPU: nvidia's init returns -ENODEV)"
dmesg -c > /dev/null 2>&1
i=1
while [ $i -le 3 ]; do
  $MP nvidia-drm; echo "run $i: modprobe nvidia-drm rc=$?"
  grep -E '^(nvidia|nvidia_modeset|nvidia_drm) ' /proc/modules
  i=$((i + 1))
done
dmesg > nvidia-dmesg.txt 2>&1
grep -E 'NVRM|nvidia|CFI|Unknown symbol|disagrees|namespace|BUG|Oops|WARNING' nvidia-dmesg.txt | head -40
chk "nvidia's init ran to its no-GPU exit (3 times)" sh -c "[ \$(grep -c 'NVRM: No NVIDIA GPU found' nvidia-dmesg.txt) = 3 ]"
chk "the rest of NVIDIA's init log is there (RM loaded its registry)" sh -c "! grep -q 'NVRM: failed to initialize module' nvidia-dmesg.txt"
chk "nothing NVIDIA's stays loaded" sh -c '! grep -qE "^(nvidia|nvidia_modeset|nvidia_drm) " /proc/modules'
chk "no unknown symbol, CRC or namespace error" sh -c "! grep -E 'Unknown symbol|disagrees about version|uses symbol .* from namespace|module verification|Invalid module format|exports duplicate' nvidia-dmesg.txt"
chk "no CFI failure" sh -c "! grep -E 'CFI failure|kCFI|CFI violation' nvidia-dmesg.txt"
chk "no kernel BUG, Oops, WARNING or GPF" sh -c "! grep -E 'kernel BUG at|BUG: (unable|kernel)|Oops:|WARNING: CPU:|general protection fault' nvidia-dmesg.txt"

echo "== ANAL-257's lab check after NVIDIA's attempts"
sh ./lab-guest-check.sh > lab-check.txt 2>&1; lrc=$?
grep -E '^(ok|FAIL) |failure' lab-check.txt
chk "lab-guest-check passes (nouveau and the sleep module, the lab's way)" test "$lrc" = 0

echo "== kernel log, whole boot"
chk "no kernel BUG, Oops, WARNING or GPF since boot" sh -c "! (cat nvidia-dmesg.txt; dmesg) | grep -E 'kernel BUG at|BUG: (unable|kernel)|Oops:|WARNING: CPU:|general protection fault'"
echo "tainted=$(cat /proc/sys/kernel/tainted)"
echo "== SELinux"
echo "getenforce: $(getenforce)"
denials=$( (cat nvidia-dmesg.txt; dmesg; logcat -d -b all 2>/dev/null) | grep 'avc:  denied' | sed 's/.*avc:/avc:/; s/ pid=[0-9]*//; s/ ino=[0-9]*//' | sort -u)
[ -n "$denials" ] && echo "$denials" | sed 's/^/DENIAL /'
echo "denials: $(echo -n "$denials" | grep -c .)"
chk "SELinux enforcing" sh -c 'getenforce | grep -q Enforcing'
chk "no denial names nvidia, its firmware or its device nodes" sh -c "! echo \"\$1\" | grep -iE 'nvidia|modules.options'" _ "$denials"
echo "nvidia-open-guest-check: $fails failure(s)"
exit "$fails"
