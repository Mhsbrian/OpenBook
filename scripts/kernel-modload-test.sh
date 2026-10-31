#!/usr/bin/env bash
# Boot a dist's bzImage under QEMU/KVM with a busybox initramfs holding the GKI and vendor modules, modprobe
# every vendor module, and log the result. Shows on a running kernel that vermagic, symbol CRCs, module
# signatures and the KMI symbol list line up. No hardware is emulated beyond a q35 PC with an AMD IOMMU,
# virtio-gpu and virtio input, so drivers for absent devices register and stay idle; a module whose init
# returns -ENODEV without its hardware is reported as such, separately from symbol or format errors.
#
# usage: kernel-modload-test.sh DIST VENDOR_MODULES_LIST [OUT_LOG] [timeout_s]
#   DIST                 dist dir with bzImage, System.map, linux_banner.txt and the .ko files
#   VENDOR_MODULES_LIST  one module file name per line (amdgpu.ko ...); the other .ko files are GKI modules
#   OUT_LOG              default DIST/modload-kvm.log
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
D=$(realpath "$1"); V=$(realpath "$2"); LOG=$(realpath -m "${3:-$D/modload-kvm.log}"); TMO=${4:-240}
W=$(mktemp -d "${TMPDIR:-/tmp}/modload.XXXXXX"); trap 'rm -rf "$W"' EXIT
REL=$(sed -n 's/.*Linux version \([^ ]*\).*/\1/p' "$D/linux_banner.txt" | head -1)
docker image inspect anybook-modtest >/dev/null 2>&1 || docker build -q -t anybook-modtest -f "$R/tools/Dockerfile.modtest" "$R/tools"

mkdir -p "$W/root/bin" "$W/root/lib/modules/$REL/kernel" "$W/root/proc" "$W/root/sys" "$W/root/dev" "$W/root/tmp"
cp "$D"/*.ko "$W/root/lib/modules/$REL/kernel/"
cp "$D/modules.builtin" "$D/modules.builtin.modinfo" "$W/root/lib/modules/$REL/"
grep -v '^#' "$V" | sed 's/\.ko$//' > "$W/root/vendor.list"
cat > "$W/root/init" <<'EOF'
#!/bin/busybox sh
/bin/busybox --install -s /bin
mount -t proc proc /proc; mount -t sysfs sys /sys
# The GKI has no devtmpfs, so /dev holds static nodes. GKI also puts console=ttynull first on the
# command line; the kernel log reaches the serial port either way.
exec >/dev/kmsg 2>&1
echo "### modload start $(uname -r) $(cat /proc/cmdline)"
# GKI virtio transport, so virtio-gpu and virtio-input find the emulated devices and actually probe
modprobe virtio_pci && echo "GKI-OK virtio_pci"
ok=0; nodev=0; bad=0
for m in $(cat /vendor.list); do
  if modprobe "$m" 2>/tmp/err; then ok=$((ok + 1)); echo "LOAD-OK $m"
  elif grep -q 'No such device' /tmp/err; then nodev=$((nodev + 1)); echo "LOAD-NODEV $m: $(cat /tmp/err)"
  else bad=$((bad + 1)); echo "LOAD-FAIL $m: $(cat /tmp/err)"; fi
done
echo "### lsmod: $(wc -l < /proc/modules) modules"; cut -d' ' -f1,3 /proc/modules | sort
ls /sys/class/drm /dev/dri 2>/dev/null | sed 's/^/drm: /'
echo "### tainted=$(cat /proc/sys/kernel/tainted)"
echo "### modload done: ok=$ok nodev=$nodev fail=$bad"
poweroff -f
EOF
chmod +x "$W/root/init"
mkdir -p "$(dirname "$LOG")"
# Runs as root inside the container only to create the /dev nodes; outputs are handed back to the caller.
docker run --rm --device /dev/kvm -v "$W:/w" -v "$D:/d:ro" anybook-modtest sh -c "
  set -e
  cp -a /w/root /tmp/root && cp /bin/busybox.static /tmp/root/bin/busybox
  mknod -m 600 /tmp/root/dev/console c 5 1; mknod -m 644 /tmp/root/dev/kmsg c 1 11; mknod -m 666 /tmp/root/dev/null c 1 3
  depmod -b /tmp/root -F /d/System.map $REL
  cd /tmp/root && find . | cpio -o -H newc --quiet | gzip -1 > /w/initramfs.cpio.gz
  chown -R $(id -u):$(id -g) /w
  timeout $TMO qemu-system-x86_64 -enable-kvm -cpu host -smp 4 -m 4G \
    -machine q35,kernel-irqchip=split -device amd-iommu,intremap=on \
    -device virtio-gpu-pci -device virtio-keyboard-pci -device virtio-tablet-pci \
    -kernel /d/bzImage -initrd /w/initramfs.cpio.gz \
    -append 'console=ttyS0,115200 earlycon=uart8250,io,0x3f8,115200 printk.devkmsg=on panic=-1 loglevel=7' \
    -nographic -no-reboot -serial mon:stdio </dev/null || true
" > "$LOG" 2>&1
grep -m1 -o 'Linux version [^ ]*' "$LOG" || true
grep -E '### (modload done|tainted)' "$LOG" || { echo "no modload result in $LOG"; exit 1; }
grep -E 'LOAD-(FAIL|NODEV)' "$LOG" || true
