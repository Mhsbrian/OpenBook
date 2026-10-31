#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# ANAL-257: the G14 lab's module commands on the new kernel, in an Android guest with no NVIDIA GPU. Runs as root
# inside the kernel QEMU check (scripts/kernel-g14-qemu.py --guest-check), next to copies of nouveau-guest-check.sh,
# openbook-pc-setup.sh and its fixture test:
#   - nouveau, drm_gpuvm and openbook_sleep_diag are in vendor_dlkm and on its modules.blocklist, and none of them
#     is live after boot (the boot loader uses modprobe -b);
#   - the exact commands of init.openbook.rc's lab services load and unload them (modprobe without -b), with
#     nouveau's options from modules.options; while nouveau is loaded, ANAL-239's nouveau-guest-check.sh passes;
#   - openbook_sleep_diag loads with the lab's parameters, its report reads back, and `openbook-pc-setup lab report`
#     relays it under this guest's sh (mksh) and toybox;
#   - nothing is left loaded, and the kernel log has no BUG, Oops, WARNING or GPF.
# Prints ok/FAIL lines and the facts behind them; exits with the number of failures.
fails=0
chk() {  # chk NAME COMMAND...: the command's status decides
  n=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok   $n"; else echo "FAIL $n"; fails=$((fails + 1)); fi
}
live() { grep -q "^$1 .* Live " /proc/modules; }
M=/vendor/lib/modules
MP="/vendor/bin/modprobe -s -d $M"   # as init.openbook.rc's lab services run it

echo "== vendor_dlkm"
ls -l $M/nouveau.ko $M/drm_gpuvm.ko $M/openbook_sleep_diag.ko
grep -E 'nouveau|drm_gpuvm|openbook_sleep_diag' $M/modules.blocklist $M/modules.load
for m in nouveau drm_gpuvm openbook_sleep_diag; do
  chk "$m.ko is in vendor_dlkm" test -f $M/$m.ko
  chk "$m.ko is blocklisted" grep -qx "blocklist $m.ko" $M/modules.blocklist
  chk "$m.ko is not in modules.load" sh -c "! grep -qx '$m.ko' $M/modules.load"
  chk "$m is not live after boot" sh -c "! grep -q '^$m ' /proc/modules"
done

echo "== nouveau: load as vendor.openbook.lab-nouveau-load does"
$MP nouveau; echo "modprobe rc=$?"
grep -E '^(nouveau|drm_gpuvm) ' /proc/modules
chk "nouveau live after the lab load" live nouveau
chk "drm_gpuvm live after the lab load" live drm_gpuvm
echo "== ANAL-239's nouveau-guest-check.sh, nouveau loaded by the lab command"
sh ./nouveau-guest-check.sh > nouveau-check.txt 2>&1; nrc=$?
grep -E '^(ok|FAIL) ' nouveau-check.txt
chk "nouveau-guest-check passes with the lab-loaded nouveau" test "$nrc" = 0
echo "== nouveau: unload as vendor.openbook.lab-nouveau-unload does"
$MP -r nouveau; echo "modprobe -r rc=$?"
chk "nouveau gone after the lab unload" sh -c "! grep -q '^nouveau ' /proc/modules"
chk "drm_gpuvm gone with it (no other user)" sh -c "! grep -q '^drm_gpuvm ' /proc/modules"

echo "== openbook_sleep_diag: load as vendor.openbook.lab-diag-snapshot does"
$MP openbook_sleep_diag snapshot=2 usb4=1 cycles=8; echo "modprobe rc=$?"
P=/sys/module/openbook_sleep_diag/parameters
chk "openbook_sleep_diag live" live openbook_sleep_diag
echo "ptm_off=$(cat $P/ptm_off) snapshot=$(cat $P/snapshot) usb4=$(cat $P/usb4) cycles=$(cat $P/cycles)"
chk "lab parameters applied" sh -c "[ \"\$(cat $P/snapshot)\" = 2 ] && [ \"\$(cat $P/usb4)\" = Y ] && [ \"\$(cat $P/cycles)\" = 8 ] && [ \"\$(cat $P/ptm_off)\" = N ]"
cat $P/report
chk "report readable before any suspend" grep -q 'no S0i3 attempt yet' $P/report
chk "report is read-only" sh -c "! echo x > $P/report"
printf '#!/system/bin/sh\necho 1\n' > ./getprop-on; chmod 755 ./getprop-on
OPENBOOK_GETPROP=./getprop-on OPENBOOK_LOGCMD=/system/bin/log OPENBOOK_SETTLE_S=0 sh ./openbook-pc-setup.sh lab report@qemu
echo "lab report rc=$?"
logcat -d -s openbook-pc-setup | grep 'lab' | tail -8
chk "lab report relays the module state" sh -c "logcat -d -s openbook-pc-setup | grep -q 'lab: module openbook_sleep_diag loaded state=live'"
chk "lab report relays the parameters" sh -c "logcat -d -s openbook-pc-setup | grep -q 'lab: openbook_sleep_diag ptm_off=N snapshot=2 usb4=Y cycles=8'"
chk "lab report relays the S0i3 report" sh -c "logcat -d -s openbook-pc-setup | grep -q 'lab: diag no S0i3 attempt yet'"
echo "== openbook_sleep_diag: unload, then the PTM-off variant"
$MP -r openbook_sleep_diag; echo "modprobe -r rc=$?"
chk "openbook_sleep_diag gone after the lab unload" sh -c "! grep -q '^openbook_sleep_diag ' /proc/modules"
$MP openbook_sleep_diag ptm_off=1 snapshot=1 usb4=1 cycles=8; echo "modprobe rc=$?"
chk "PTM-off variant live with ptm_off=Y" sh -c "grep -q '^openbook_sleep_diag .* Live ' /proc/modules && [ \"\$(cat $P/ptm_off)\" = Y ]"
$MP -r openbook_sleep_diag; echo "modprobe -r rc=$?"
chk "nothing left loaded" sh -c "! grep -qE '^(nouveau|drm_gpuvm|openbook_sleep_diag) ' /proc/modules"

echo "== kernel log"
dmesg | grep -E 'openbook_sleep_diag' | tail -12
chk "no kernel BUG, Oops, WARNING or GPF in the kernel log" sh -c "! dmesg | grep -E 'kernel BUG at|BUG: (unable|kernel)|Oops:|WARNING: CPU:|general protection fault'"
echo "lab-guest-check: $fails failure(s)"
exit "$fails"
