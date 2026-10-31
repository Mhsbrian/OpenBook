#!/usr/bin/env bash
# Boot the given GKI bzImage in a throwaway QEMU guest with openbook_sleep_diag.ko and run ./init (ANAL-257).
# usage: run-vm-test.sh BZIMAGE MODULE.ko OUTDIR
#   (inside OPENBOOK_INSTALLER_IMAGE=openbook-installer:anal178 scripts/installer/inst-docker.sh, which has iasl;
#    BUSYBOX must point to a static busybox)
# The guest gets the power check's LPS0 fixture (scripts/power/lps0-test.asl) so the s2idle LPS0 hooks run as on the
# laptop, and a PCIe root port with an e1000e behind it. QEMU's RTC does not wake s2idle, so the host presses the
# ACPI power button over QMP every 4 s; S3 is woken by the RTC. Results: OUTDIR/serial.log, checked by
# check-vm-log.py.
set -euo pipefail
K=$1; M=$2; O=$3; T=$(cd "$(dirname "$0")" && pwd); R=$(cd "$T/../../../../.." && pwd)
mkdir -p "$O/root/bin" "$O/root/proc" "$O/root/sys" "$O/root/dev" "$O/acpi"
iasl -p "$O/acpi/lps0-test" "$R/scripts/power/lps0-test.asl" >/dev/null
cp "${BUSYBOX:?set BUSYBOX to a static busybox}" "$O/root/bin/busybox"
cp "$T/init" "$O/root/init"; chmod 755 "$O/root/init" "$O/root/bin/busybox"
cp "$M" "$O/root/openbook_sleep_diag.ko"
(cd "$O/root" && find . | cpio -o -H newc --quiet | gzip -9n) > "$O/initramfs.cpio.gz"
rm -f "$O/qmp.sock"
timeout 240 qemu-system-x86_64 -machine q35 -accel kvm -cpu host -smp 2 -m 1024 -nographic -no-reboot \
  -global ICH9-LPC.disable_s3=0 -acpitable file="$O/acpi/lps0-test.aml" \
  -device pcie-root-port,id=rp1,chassis=1 -device e1000e,bus=rp1,netdev=n0 -netdev user,id=n0,restrict=on \
  -qmp unix:"$O/qmp.sock",server=on,wait=off \
  -kernel "$K" -initrd "$O/initramfs.cpio.gz" \
  -append "console=ttyS0,115200 8250.nr_uarts=1 rdinit=/init loglevel=7 pm_debug_messages mem_sleep_default=s2idle" \
  > "$O/serial.log" 2>&1 &
QEMU=$!
python3 - "$O/qmp.sock" "$QEMU" <<'EOF'
import json, os, socket, sys, time
path, pid = sys.argv[1], int(sys.argv[2])
for _ in range(100):
    if os.path.exists(path):
        break
    time.sleep(0.1)
s = socket.socket(socket.AF_UNIX)
s.connect(path)
f = s.makefile("rw")
f.readline()
for cmd in ({"execute": "qmp_capabilities"},):
    f.write(json.dumps(cmd) + "\n"); f.flush(); f.readline()
presses = 0
while True:
    time.sleep(4)
    try:
        os.kill(pid, 0)
        f.write(json.dumps({"execute": "system_powerdown"}) + "\n"); f.flush()
        presses += 1
    except (OSError, BrokenPipeError):
        break
print(f"QMP power-button presses: {presses}")
EOF
wait "$QEMU" || true
grep -aE '^(==|PARAM|KLOG|KBAD)' "$O/serial.log" || true
