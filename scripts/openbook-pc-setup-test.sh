#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Fixture tests for device/anybook/common/pc/bin/openbook-pc-setup.sh: fake sysfs trees for the G14's dGPU cases
# and for the EPP permission step. Runs on a Linux host (sh/bash) and on the device (mksh + toybox):
#   scripts/openbook-pc-setup-test.sh [SHELL] [SCRIPT]
# On OpenBook: sh /data/local/tmp/openbook-pc-setup-test.sh sh /vendor/bin/openbook-pc-setup
set -u
SH=${1:-sh}
HERE=$(cd "$(dirname "$0")" && pwd)
SCRIPT=${2:-$HERE/../device/anybook/common/pc/bin/openbook-pc-setup.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/pc-setup-test.XXXXXX")
trap 'rm -rf "$T"' EXIT
fails=0

w() { mkdir -p "$(dirname "$1")"; printf '%s\n' "$2" > "$1"; }
check() {  # check NAME FILE EXPECTED
  got=$(head -n 1 "$2" 2>/dev/null)
  if [ "$got" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: $2 is '$got', expected '$3'"; fails=$((fails + 1)); fi
}

# pci ROOT BDF VENDOR CLASS [DRIVER]: a PCI function under the G14's GPP bridge 00:03.1, as sysfs shows it
pci() {
  d=$1/sys/devices/pci0000:00/0000:00:03.1/$2
  w "$d/vendor" "$3"; w "$d/class" "$4"; w "$d/power/control" on; w "$d/power/runtime_status" active
  w "$d/power_state" D0
  mkdir -p "$1/sys/bus/pci/devices"
  ln -s "../../../devices/pci0000:00/0000:00:03.1/$2" "$1/sys/bus/pci/devices/$2"
  if [ -n "${5:-}" ]; then
    mkdir -p "$1/sys/bus/pci/drivers/$5"
    : > "$1/sys/bus/pci/drivers/$5/unbind"
    ln -s "../../../bus/pci/drivers/$5" "$d/driver"
    ln -s "../../../../devices/pci0000:00/0000:00:03.1/$2" "$1/sys/bus/pci/drivers/$5/$2"   # as sysfs links it back
  fi
}
run() { OPENBOOK_SYSFS_ROOT=$1 "$SH" "$SCRIPT" "$2" > "$1.log" 2>&1; echo $? > "$1.rc"; }

# 1. GA403WR with dgpu_disable=0: GB205M 10de:2f58 unbound, its HDMI audio 10de:2f80 held by snd_hda_intel.
r=$T/g14-d0
pci "$r" 0000:64:00.0 0x10de 0x030000
pci "$r" 0000:64:00.1 0x10de 0x040300 snd_hda_intel
w "$r/sys/module/snd_hda_intel/parameters/power_save" 0
run "$r" dgpu-pm
check "g14-d0: exit 0" "$r.rc" 0
check "g14-d0: HDMI audio unbound from snd_hda_intel" "$r/sys/bus/pci/drivers/snd_hda_intel/unbind" 0000:64:00.1
check "g14-d0: dGPU runtime PM auto" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.0/power/control" auto
check "g14-d0: HDMI audio runtime PM auto" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.1/power/control" auto
check "g14-d0: snd_hda_intel power_save" "$r/sys/module/snd_hda_intel/parameters/power_save" 10

# 1b. dgpu-hda (ANAL-322), at early init before the switcher's boot step: only the HDMI audio comes off
#     snd_hda_intel; runtime PM, power_save and the GPU function stay as they are (dgpu-pm does those later).
r=$T/g14-hda
pci "$r" 0000:64:00.0 0x10de 0x030000
pci "$r" 0000:64:00.1 0x10de 0x040300 snd_hda_intel
pci "$r" 0000:65:00.1 0x1022 0x040300 snd_hda_intel
w "$r/sys/module/snd_hda_intel/parameters/power_save" 0
run "$r" dgpu-hda
check "dgpu-hda: exit 0" "$r.rc" 0
check "dgpu-hda: NVIDIA HDMI audio unbound, AMD audio kept" "$r/sys/bus/pci/drivers/snd_hda_intel/unbind" 0000:64:00.1
check "dgpu-hda: dGPU runtime PM untouched" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.0/power/control" on
check "dgpu-hda: HDMI audio runtime PM untouched" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.1/power/control" on
check "dgpu-hda: power_save untouched" "$r/sys/module/snd_hda_intel/parameters/power_save" 0
r=$T/g14-hda-off
pci "$r" 0000:65:00.1 0x1022 0x040300 snd_hda_intel
run "$r" dgpu-hda
check "dgpu-hda without the dGPU (Eco): exit 0" "$r.rc" 0
check "dgpu-hda without the dGPU (Eco): nothing unbound" "$r/sys/bus/pci/drivers/snd_hda_intel/unbind" ""

# 2. dgpu_disable=1 (the default): the dGPU is not enumerated. Nothing may be written.
r=$T/g14-off
mkdir -p "$r/sys/bus/pci/devices"
pci "$r" 0000:65:00.1 0x1002 0x040300 snd_hda_intel   # the 890M's own HDMI/DP audio, AMD
w "$r/sys/module/snd_hda_intel/parameters/power_save" 0
run "$r" dgpu-pm
check "g14-off: exit 0" "$r.rc" 0
check "g14-off: AMD audio left alone" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:65:00.1/power/control" on
check "g14-off: power_save untouched" "$r/sys/module/snd_hda_intel/parameters/power_save" 0
check "g14-off: nothing unbound" "$r/sys/bus/pci/drivers/snd_hda_intel/unbind" ""

# 3. nouveau drives the dGPU (ANAL-239): its runtime PM is nouveau's, but snd_hda_intel must still come off the HDMI
#    audio function, which otherwise keeps the slot powered (no vga_switcheroo in the GKI).
r=$T/nouveau
pci "$r" 0000:64:00.0 0x10de 0x030000 nouveau
pci "$r" 0000:64:00.1 0x10de 0x040300 snd_hda_intel
w "$r/sys/module/snd_hda_intel/parameters/power_save" 0
w "$r/sys/module/nouveau/parameters/runpm" 1; w "$r/sys/module/nouveau/parameters/modeset" 2
w "$r/sys/module/nouveau/parameters/config" "(null)"   # unset, as the kernel shows it
run "$r" dgpu-pm
check "nouveau: exit 0" "$r.rc" 0
check "nouveau: dGPU control left to nouveau" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.0/power/control" on
check "nouveau: HDMI audio unbound from snd_hda_intel" "$r/sys/bus/pci/drivers/snd_hda_intel/unbind" 0000:64:00.1
check "nouveau: HDMI audio runtime PM auto" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.1/power/control" auto
check "nouveau: snd_hda_intel power_save" "$r/sys/module/snd_hda_intel/parameters/power_save" 10
grep -q '0000:64:00.0 is driven by nouveau; leaving its runtime PM to the driver' "$r.log" &&
  grep -q 'nouveau: runpm=1 modeset=2 bound=0000:64:00.0$' "$r.log" && ! grep -q 'runpm is not 1' "$r.log" &&
  echo "ok   nouveau: logs the driver and runpm=1 modeset=2" || { echo "FAIL nouveau log: $(cat "$r.log")"; fails=$((fails + 1)); }

# 3b. nouveau loaded without runpm=1 (its default -1): the dGPU would stay in D0. Say so; still unbind the audio.
r=$T/nouveau-norunpm
pci "$r" 0000:64:00.0 0x10de 0x030000 nouveau
pci "$r" 0000:64:00.1 0x10de 0x040300
w "$r/sys/module/nouveau/parameters/runpm" -1; w "$r/sys/module/nouveau/parameters/modeset" -1
w "$r/sys/module/nouveau/parameters/config" NvGspRm=1
run "$r" dgpu-pm
check "nouveau-norunpm: exit 0" "$r.rc" 0
check "nouveau-norunpm: HDMI audio runtime PM auto" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.1/power/control" auto
grep -q 'nouveau: runpm is not 1' "$r.log" && grep -q 'nouveau: runpm=-1 modeset=-1 config=NvGspRm=1 bound=0000:64:00.0$' "$r.log" &&
  echo "ok   nouveau-norunpm: warns, and shows a set config" ||
  { echo "FAIL nouveau-norunpm: $(cat "$r.log")"; fails=$((fails + 1)); }

# 4. perms: every policy's energy_performance_preference (chown needs root: on a host only the count is checked).
r=$T/epp
for i in 0 1 2 3; do w "$r/sys/devices/system/cpu/cpufreq/policy$i/energy_performance_preference" balance_performance; done
w "$r/sys/devices/system/cpu/amd_pstate/status" active
run "$r" perms
check "perms: exit 0" "$r.rc" 0
if [ "$(id -u)" = 0 ]; then
  grep -q 'energy_performance_preference: 4 policies' "$r.log" && echo "ok   perms: 4 policies" ||
    { echo "FAIL perms: $(cat "$r.log")"; fails=$((fails + 1)); }
else
  grep -q 'energy_performance_preference: [0-9]* policies' "$r.log" && echo "ok   perms: reports (not root: chown skipped)" ||
    { echo "FAIL perms: $(cat "$r.log")"; fails=$((fails + 1)); }
fi

# 5. kvm (ANAL-218): KVM's misc device registered (SVM on) -> vendor.openbook.kvm=1; absent (SVM off) -> 0.
for case in on off; do
  r=$T/kvm-$case
  mkdir -p "$r/sys"
  [ $case = on ] && w "$r/sys/devices/virtual/misc/kvm/dev" 10:232
  OPENBOOK_SYSFS_ROOT=$r OPENBOOK_SETPROP="echo setprop" "$SH" "$SCRIPT" kvm > "$r.log" 2>&1; echo $? > "$r.rc"
  check "kvm $case: exit 0" "$r.rc" 0
  want=1; [ $case = off ] && want=0
  grep -q "^setprop vendor.openbook.kvm $want\$" "$r.log" && echo "ok   kvm $case: vendor.openbook.kvm=$want" ||
    { echo "FAIL kvm $case: $(cat "$r.log")"; fails=$((fails + 1)); }
done

# 6-9. dgpu-report and dgpu-ctl (ANAL-238). The logd copy goes through a stub log command.
stub=$T/log-stub; printf '#!/bin/sh\necho "$*" >> "$LOGD_OUT"\n' > "$stub"; chmod +x "$stub"
runx() {  # runx ROOT ARGS...: run with the logd stub, no settle delay and an empty kernel log (or DMESG_STUB's)
  r=$1; shift
  LOGD_OUT=$r.logd OPENBOOK_LOGCMD=$stub OPENBOOK_SETTLE_S=0 OPENBOOK_DMESG=${DMESG_STUB:-true} OPENBOOK_SYSFS_ROOT=$r \
    "$SH" "$SCRIPT" "$@" > "$r.log" 2>&1
  echo $? > "$r.rc"
}
has() {  # has NAME FILE PATTERN: FILE has a line matching the grep -E PATTERN
  if grep -Eq -- "$3" "$2" 2>/dev/null; then echo "ok   $1"; else echo "FAIL $1: no /$3/ in $2: $(cat "$2" 2>/dev/null)"; fails=$((fails + 1)); fi
}
# g14_d3cold ROOT: both functions and the bridge in D3cold; the bridge's ACPI node lists PG00, which is off
g14_d3cold() {
  pci "$1" 0000:64:00.0 0x10de 0x030000; pci "$1" 0000:64:00.1 0x10de 0x040300
  b=$1/sys/devices/pci0000:00/0000:00:03.1
  w "$b/vendor" 0x1022; w "$b/class" 0x060400; w "$b/power_state" D3cold; w "$b/power/runtime_status" suspended
  w "$b/power/control" auto
  ln -s ../../../devices/pci0000:00/0000:00:03.1 "$1/sys/bus/pci/devices/0000:00:03.1"
  for f in 0 1; do
    w "$b/0000:64:00.$f/power_state" D3cold; w "$b/0000:64:00.$f/power/runtime_status" suspended
    w "$b/0000:64:00.$f/power/control" auto
  done
  a=$1/sys/devices/LNXSYSTM:00/LNXSYBUS:00/PNP0A08:00
  w "$a/device:13/path" '\_SB_.PCI0.GPP9'; w "$a/device:13/power_state" D3cold
  w "$a/LNXPOWER:0a/path" '\_SB_.PCI0.GPP9.PG00'; w "$a/LNXPOWER:0a/resource_in_use" 0
  mkdir -p "$a/device:13/power_resources_D0" "$a/device:13/power_resources_D3hot"
  ln -s ../../LNXPOWER:0a "$a/device:13/power_resources_D0/LNXPOWER:0a"
  ln -s ../../LNXPOWER:0a "$a/device:13/power_resources_D3hot/LNXPOWER:0a"
  ln -s ../../LNXSYSTM:00/LNXSYBUS:00/PNP0A08:00/device:13 "$b/firmware_node"
  w "$1/sys/devices/platform/asus-nb-wmi/dgpu_disable" 0; w "$1/sys/devices/platform/asus-nb-wmi/gpu_mux_mode" 1
  w "$1/sys/power/suspend_stats/success" 7; w "$1/sys/power/suspend_stats/total_hw_sleep" 0
}

r=$T/report-d3cold; g14_d3cold "$r"
runx "$r" dgpu-report boot
check "report d3cold: exit 0" "$r.rc" 0
has "report d3cold: verdict" "$r.log" 'dgpu-report: state=d3cold$'
has "report d3cold: GPU line" "$r.log" '0000:64:00.0 class=0x030000 .*driver=- power_state=D3cold runtime_status=suspended control=auto'
has "report d3cold: bridge and PG00 off" "$r.log" 'bridge 0000:00:03.1 driver=- power_state=D3cold .*acpi=\\_SB_.PCI0.GPP9 acpi_state=D3cold resources=PG00:0$'
has "report d3cold: asus read" "$r.log" 'asus-nb-wmi dgpu_disable=0 gpu_mux_mode=1'
has "report d3cold: suspend_stats" "$r.log" 'suspend_stats success=7 total_hw_sleep_us=0'
has "report d3cold: logd copy" "$r.logd" '^-t openbook-pc-setup -p i dgpu-report: state=d3cold$'
check "report d3cold: read-only" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.0/power/control" auto

r=$T/report-d0
pci "$r" 0000:64:00.0 0x10de 0x030000; pci "$r" 0000:64:00.1 0x10de 0x040300 snd_hda_intel
runx "$r" dgpu-report
has "report d0: verdict" "$r.log" 'state=d0-no-driver$'
has "report d0: HDA bound" "$r.log" '0000:64:00.1 .*driver=snd_hda_intel power_state=D0'
has "report d0: default reason" "$r.log" 'dgpu-report \(manual\)'

r=$T/report-absent; mkdir -p "$r/sys/bus/pci/devices"; pci "$r" 0000:65:00.1 0x1002 0x040300 snd_hda_intel
runx "$r" dgpu-report
has "report absent: verdict" "$r.log" 'state=absent$'

r=$T/report-nouveau; g14_d3cold "$r"
mkdir -p "$r/sys/bus/pci/drivers/nouveau"
ln -s ../../../../bus/pci/drivers/nouveau "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.0/driver"
ln -s ../../../../devices/pci0000:00/0000:00:03.1/0000:64:00.0 "$r/sys/bus/pci/drivers/nouveau/0000:64:00.0"
w "$r/sys/module/nouveau/parameters/runpm" 1; w "$r/sys/module/nouveau/parameters/modeset" 2
runx "$r" dgpu-report boot
has "report nouveau: verdict" "$r.log" 'dgpu-report: state=d3cold$'
has "report nouveau: GPU line" "$r.log" '0000:64:00.0 class=0x030000 .*driver=nouveau power_state=D3cold runtime_status=suspended'
has "report nouveau: parameters" "$r.log" 'nouveau: runpm=1 modeset=2 bound=0000:64:00.0$'
has "report nouveau: logd copy" "$r.logd" '^-t openbook-pc-setup -p i nouveau: runpm=1 modeset=2 bound=0000:64:00.0$'

# ANAL-297: NVIDIA's driver bound; its parameters and its own runtime-D3 report are logged.
r=$T/report-nvidia; g14_d3cold "$r"
mkdir -p "$r/sys/bus/pci/drivers/nvidia"
ln -s ../../../../bus/pci/drivers/nvidia "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.0/driver"
ln -s ../../../../devices/pci0000:00/0000:00:03.1/0000:64:00.0 "$r/sys/bus/pci/drivers/nvidia/0000:64:00.0"
w "$r/sys/module/nvidia/parameters/NVreg_DynamicPowerManagement" 2
w "$r/sys/module/nvidia_drm/parameters/modeset" Y
mkdir -p "$r/proc/driver/nvidia/gpus/0000:64:00.0"
printf 'Runtime D3 status:          Enabled (fine-grained)\nVideo Memory:               Off\n\nGPU Hardware Support:\n Video Memory Self Refresh: Supported\n' \
  > "$r/proc/driver/nvidia/gpus/0000:64:00.0/power"
runx "$r" dgpu-report boot
has "report nvidia: verdict" "$r.log" 'dgpu-report: state=d3cold$'
has "report nvidia: GPU line" "$r.log" '0000:64:00.0 class=0x030000 .*driver=nvidia power_state=D3cold'
has "report nvidia: parameters" "$r.log" 'nvidia: DynamicPowerManagement=2 drm.modeset=Y bound=0000:64:00.0$'
has "report nvidia: runtime D3 status" "$r.log" 'nvidia: 0000:64:00.0 Runtime D3 status: +Enabled \(fine-grained\)$'
has "report nvidia: video memory" "$r.log" 'nvidia: 0000:64:00.0 Video Memory: +Off$'
has "report nvidia: logd copy" "$r.logd" '^-t openbook-pc-setup -p i nvidia: DynamicPowerManagement=2'
has "report nvidia: health line, kernel log unreadable" "$r.log" \
  'dgpu-report: health state=d3cold driver=nvidia refs=- runtime_d3=enabled-fine-grained vram=off klog=unreadable$'

# ANAL-308: the health line counts NVIDIA's kernel messages and Xid kinds in the kernel log ring, and its span.
w "$r/sys/module/nvidia/refcnt" 3
cat > "$r.dmesg" <<'KLOG'
[38120.031524][ T4187] servicemanager: Caller(pid=1228,uid=1000) Tried to start aidl service
[38200.100000][ T8503] NVRM: GPU at PCI:0000:64:00: GPU-00000000-0000-0000-0000-000000000000
[38201.200000][ T8503] NVRM: Xid (PCI:0000:64:00): 13, pid=9001, name=deqp-vk, Graphics Exception: ESR 0x404600=0x80000002
[38201.300000][ T8503] NVRM: Xid (PCI:0000:64:00): 13, pid=9001, name=deqp-vk, Graphics Exception: ESR 0x405840=0x80000000
[38202.400000][ T8503] NVRM: Xid (PCI:0000:64:00): 31, pid=9002, name=deqp-vk, channel 0x00000010, intr 00000000. MMU Fault
[39133.101403][ T8503] nvidia 0000:64:00.0: Enabling HDA controller
KLOG
DMESG_STUB="cat $r.dmesg" runx "$r" dgpu-report app-session
has "report nvidia: health line counts NVRM lines and Xid kinds" "$r.log" \
  'dgpu-report: health state=d3cold driver=nvidia refs=3 runtime_d3=enabled-fine-grained vram=off nvrm=4 xid=3 xid_kinds=13:2,31:1 klog_s=38120-39133$'
printf '[    5.000000] NVRM: loading NVIDIA UNIX Open Kernel Module\n[  700.250000][ T1] init: ok\n' > "$r.dmesg.clean"
DMESG_STUB="cat $r.dmesg.clean" runx "$r" dgpu-report clean
has "report nvidia: health line without Xid has no kinds" "$r.log" 'nvrm=1 xid=0 klog_s=5-700$'
# ANAL-308 rev 2: a ring the G14's size (~250 KiB). R8 passed it to an external printf, which takes at most 128 KiB
# per argument (Android's mksh has no printf builtin), so every count read 0 and the span was empty on the laptop.
{ echo '[    4.000000][    T1] NVRM: loading NVIDIA UNIX Open Kernel Module for x86_64  615.78.08'
  i=0; while [ $i -lt 2200 ]; do
    echo "[  $((100 + i)).000000][  T812] avc:  denied  { find } for pid=1228 uid=1000 name=vendor.google.desktop.x/default"
    i=$((i + 1)); done
  echo '[ 2400.500000][ T8503] NVRM: Xid (PCI:0000:64:00): 13, pid=9001, name=deqp-vk, Graphics Exception'; } > "$r.dmesg.big"
DMESG_STUB="cat $r.dmesg.big" runx "$r" dgpu-report big
has "report nvidia: health line counts a ring over 128 KiB" "$r.log" 'nvrm=2 xid=1 xid_kinds=13:1 klog_s=4-2400$'
# The default read is syslog(2), never /dev/kmsg: the helper may not read /dev/kmsg, and toybox's dmesg tries it first.
mkdir -p "$T/fakebin"
printf '#!/bin/sh\necho "$*" > "%s"\ncat "%s"\n' "$r.dmesg-args" "$r.dmesg.clean" > "$T/fakebin/dmesg"
chmod +x "$T/fakebin/dmesg"
PATH=$T/fakebin:$PATH LOGD_OUT=$r.logd OPENBOOK_LOGCMD=$stub OPENBOOK_SETTLE_S=0 OPENBOOK_SYSFS_ROOT=$r \
  "$SH" "$SCRIPT" dgpu-report default > "$r.log" 2>&1
check "report nvidia: kernel log read with dmesg -S" "$r.dmesg-args" "-S"
has "report nvidia: health line from the default read" "$r.log" 'nvrm=1 xid=0 klog_s=5-700$'

r=$T/ctl-on
pci "$r" 0000:64:00.0 0x10de 0x030000; pci "$r" 0000:64:00.1 0x10de 0x040300
for f in 0 1; do w "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.$f/power/control" auto; done
runx "$r" dgpu-ctl on
check "ctl on: exit 0" "$r.rc" 0
check "ctl on: GPU held in D0" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.0/power/control" on
check "ctl on: HDMI audio held in D0" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.1/power/control" on
has "ctl on: reports after" "$r.log" 'dgpu-report \(dgpu-ctl on\)'
runx "$r" dgpu-ctl auto
check "ctl auto: GPU back to auto" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.0/power/control" auto

r=$T/ctl-bad; pci "$r" 0000:64:00.0 0x10de 0x030000
runx "$r" dgpu-ctl off
check "ctl bad value: exit 2" "$r.rc" 2
check "ctl bad value: nothing written" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.0/power/control" on

r=$T/ctl-nouveau
pci "$r" 0000:64:00.0 0x10de 0x030000 nouveau; pci "$r" 0000:64:00.1 0x10de 0x040300
for f in 0 1; do w "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.$f/power/control" auto; done
runx "$r" dgpu-ctl on
check "ctl with nouveau: exit 0" "$r.rc" 0
check "ctl with nouveau: audio untouched" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.1/power/control" auto

# lab (ANAL-257): a property store in files, and a stand-in for init that loads or unloads the module named by
# vendor.openbook.lab.mod in the fake sysfs (FAKE_INIT=0: init does nothing, so the helper must time out).
P=$T/props; mkdir -p "$P"
cat > "$T/getprop" <<'EOF'
#!/bin/sh
cat "$PROPS/$1" 2>/dev/null
EOF
cat > "$T/setprop" <<'EOF'
#!/bin/sh
printf '%s\n' "$2" > "$PROPS/$1"; echo "$1=$2" >> "$PROPS/.log"
[ "$1" = vendor.openbook.lab.mod ] && [ "${FAKE_INIT:-1}" = 1 ] || exit 0
m=$FAKE_SYS/sys/module
case $2 in
  nouveau-load) mkdir -p "$m/nouveau/parameters" "$m/drm_gpuvm"; echo live > "$m/nouveau/initstate"
                echo 1 > "$m/nouveau/parameters/runpm"; echo 2 > "$m/nouveau/parameters/modeset" ;;
  nouveau-unload) rm -rf "$m/nouveau" "$m/drm_gpuvm" ;;
  nvidia-load) for x in nvidia nvidia_modeset nvidia_drm; do mkdir -p "$m/$x"; echo live > "$m/$x/initstate"; done
               # FAKE_BIND=0: the driver loads but does not take the GPU.
               g=$FAKE_SYS/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.0
               if [ "${FAKE_BIND:-1}" = 1 ] && [ -d "$g" ] && [ ! -e "$g/driver" ]; then
                 mkdir -p "$FAKE_SYS/sys/bus/pci/drivers/nvidia"; ln -s ../../../../bus/pci/drivers/nvidia "$g/driver"
               fi ;;
  nvidia-unload) rm -rf "$m/nvidia" "$m/nvidia_modeset" "$m/nvidia_drm"
                 rm -f "$FAKE_SYS/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.0/driver" ;;
  diag-snapshot|diag-ptm-off)
    d=$m/openbook_sleep_diag/parameters; mkdir -p "$d"
    [ "$2" = diag-ptm-off ] && echo Y > "$d/ptm_off" || echo N > "$d/ptm_off"
    echo 2 > "$d/snapshot"; echo Y > "$d/usb4"; echo 8 > "$d/cycles"
    printf 's0i3-entry 1 (suspend 1):\n  0000:00:00.0 1022:1507 D0 -\ns0i3-entry 1: 39 PCI functions, 17 not in D3, 0 with PTM on (listed above)\n' > "$d/report" ;;
  diag-unload) rm -rf "$m/openbook_sleep_diag" ;;
esac
EOF
chmod 755 "$T/getprop" "$T/setprop"
labrun() {  # labrun ROOT ARGS...: the lab with the stubs; the property store is shared between calls
  r=$1; shift
  PROPS=$P FAKE_SYS=$r OPENBOOK_GETPROP=$T/getprop OPENBOOK_SETPROP=$T/setprop OPENBOOK_LAB_WAIT_S=${WAIT:-3} \
    OPENBOOK_SETTLE_S=0 OPENBOOK_SYSFS_ROOT=$r OPENBOOK_LOGCMD= "$SH" "$SCRIPT" "$@" > "$r.log" 2>&1
  echo $? > "$r.rc"
}
lab_root() {  # a G14 with the dGPU in D3cold, an RTC, the suspend files and NVIDIA's GSP firmware
  g14_d3cold "$1"
  w "$1/vendor/firmware/nvidia/615.78.08/gsp_ga10x.bin" stub
  w "$1/vendor/app/OpenBookNvk/OpenBookNvk.apk" stub   # the OpenBook NVK driver package (ANAL-327)
  w "$1/sys/class/rtc/rtc0/wakealarm" ""; w "$1/sys/power/state" ""
  w "$1/sys/power/suspend_stats/success" 7; w "$1/sys/power/suspend_stats/last_hw_sleep" 0
}

r=$T/lab-off; lab_root "$r"
labrun "$r" lab report
check "lab off: report refused (exit 3)" "$r.rc" 3
has "lab off: says how to switch on" "$r.log" "refused: the lab switch is off"
labrun "$r" lab 'rm -rf /'
check "lab: unknown action refused (exit 2)" "$r.rc" 2
has "lab: unknown action named" "$r.log" "'rm -rf /' is not an allowed action"
check "lab: nothing set by refused requests" "$P/.log" ""

r=$T/lab-on; lab_root "$r"
labrun "$r" lab enable
check "lab enable: exit 0" "$r.rc" 0
check "lab enable: switch persisted" "$P/persist.vendor.openbook.lab" 1
labrun "$r" lab report@1
check "lab report: exit 0" "$r.rc" 0
has "lab report: header with switch" "$r.log" 'lab-report \(report@1\): switch=1$'
has "lab report: dGPU state" "$r.log" 'dgpu-report: state=d3cold$'
has "lab report: nouveau not loaded" "$r.log" 'lab: module nouveau not loaded$'

: > "$P/.log"
labrun "$r" lab nouveau-load
check "lab nouveau-load: exit 0" "$r.rc" 0
check "lab nouveau-load: idle first, then the action, then idle" "$P/.log" "vendor.openbook.lab.mod=idle"
has "lab nouveau-load: asked init" "$P/.log" '^vendor.openbook.lab.mod=nouveau-load$'
check "lab nouveau-load: request reset" "$P/vendor.openbook.lab.mod" idle
has "lab nouveau-load: present" "$r.log" 'lab: nouveau-load: nouveau present$'
has "lab nouveau-load: nouveau's options reported" "$r.log" 'nouveau: runpm=1 modeset=2'
has "lab nouveau-load: module state" "$r.log" 'lab: module nouveau loaded state=live'
labrun "$r" lab nouveau-load@2
check "lab nouveau-load twice: refused (exit 4)" "$r.rc" 4
# ANAL-297: NVIDIA's driver and nouveau exclude each other.
labrun "$r" lab nvidia-load
check "lab nvidia-load while nouveau is loaded: refused (exit 4)" "$r.rc" 4
has "lab nvidia-load while nouveau is loaded: said why" "$r.log" 'nvidia-load refused: nouveau is loaded and drives the same GPU'
grep -q '=nvidia-load$' "$P/.log" && { echo "FAIL lab nvidia-load refused: init was asked"; fails=$((fails + 1)); } ||
  echo "ok   lab nvidia-load refused: init not asked"
labrun "$r" lab nouveau-unload
check "lab nouveau-unload: exit 0" "$r.rc" 0
has "lab nouveau-unload: absent" "$r.log" 'lab: nouveau-unload: nouveau absent$'
: > "$P/.log"
labrun "$r" lab nvidia-load
check "lab nvidia-load: exit 0" "$r.rc" 0
has "lab nvidia-load: asked init" "$P/.log" '^vendor.openbook.lab.mod=nvidia-load$'
has "lab nvidia-load: nvidia_drm present" "$r.log" 'lab: nvidia-load: nvidia_drm present$'
has "lab nvidia-load: all three reported" "$r.log" 'lab: module nvidia_modeset loaded state=live'
labrun "$r" lab nouveau-load@3
check "lab nouveau-load while nvidia is loaded: refused (exit 4)" "$r.rc" 4
has "lab nouveau-load while nvidia is loaded: said why" "$r.log" 'nouveau-load refused: nvidia is loaded and drives the same GPU'
labrun "$r" lab nvidia-load@2
check "lab nvidia-load twice: refused (exit 4)" "$r.rc" 4
labrun "$r" lab nvidia-unload
check "lab nvidia-unload: exit 0" "$r.rc" 0
has "lab nvidia-unload: nvidia absent" "$r.log" 'lab: nvidia-unload: nvidia absent$'
has "lab nvidia-unload: nvidia_drm gone too" "$r.log" 'lab: module nvidia_drm not loaded$'

labrun "$r" lab diag-ptm-off
check "lab diag-ptm-off: exit 0" "$r.rc" 0
has "lab diag-ptm-off: parameters" "$r.log" 'lab: openbook_sleep_diag ptm_off=Y snapshot=2 usb4=Y cycles=8$'
has "lab diag-ptm-off: report relayed" "$r.log" 'lab: diag s0i3-entry 1: 39 PCI functions, 17 not in D3, 0 with PTM on'
has "lab diag-ptm-off: report lines keep their indent" "$r.log" 'lab: diag   0000:00:00.0 1022:1507 D0 -$'
labrun "$r" lab diag-unload
has "lab diag-unload: absent" "$r.log" 'lab: diag-unload: openbook_sleep_diag absent$'

FAKE_INIT=0 WAIT=1 labrun "$r" lab diag-snapshot
check "lab: init did nothing: exit 5" "$r.rc" 5
has "lab: init did nothing: said so" "$r.log" 'diag-snapshot: openbook_sleep_diag not present after 1 s'
check "lab: request reset after a timeout" "$P/vendor.openbook.lab.mod" idle

labrun "$r" lab sleep-20
check "lab sleep-20: exit 0" "$r.rc" 0
has "lab sleep-20: alarm armed" "$r.log" 'wakealarm <- \+20$'
check "lab sleep-20: suspended through /sys/power/state" "$r/sys/power/state" mem
check "lab sleep-20: alarm cleared after" "$r/sys/class/rtc/rtc0/wakealarm" 0
has "lab sleep-20: resumed and counted" "$r.log" 'lab: suspend_stats success=7 last_hw_sleep_us=0'
labrun "$r" lab sleep-45
check "lab: sleep length outside the list refused (exit 2)" "$r.rc" 2
r2=$T/lab-busy; lab_root "$r2"; rm -f "$r2/sys/power/state"; mkdir -p "$r2/sys/power/state"
labrun "$r2" lab sleep-20
has "lab sleep refused by the kernel: said so" "$r2.log" 'the suspend was refused or aborted'

labrun "$r" lab disable
check "lab disable: switch off" "$P/persist.vendor.openbook.lab" 0
labrun "$r" lab report
check "lab disable: report refused again (exit 3)" "$r.rc" 3

# dgpu-driver (ANAL-247): NVIDIA's driver at boot in Hybrid, through the lab's fixed nvidia-load command, and the
# guard in persist.vendor.openbook.dgpu_driver. Each case starts from an empty property store.
drv() {  # drv ROOT ARGS...: dgpu-driver with the stubs and no settle delay
  r=$1; shift
  PROPS=$P FAKE_SYS=$r OPENBOOK_GETPROP=$T/getprop OPENBOOK_SETPROP=$T/setprop OPENBOOK_LAB_WAIT_S=${WAIT:-3} \
    OPENBOOK_SETTLE_S=0 OPENBOOK_DRIVER_SETTLE_S=0 OPENBOOK_SYSFS_ROOT=$r OPENBOOK_LOGCMD= "$SH" "$SCRIPT" dgpu-driver "$@" \
    > "$r.log" 2>&1
  echo $? > "$r.rc"
}
fresh() { rm -f "$P"/* "$P/.log"; : > "$P/.log"; echo radv > "$P/ro.hardware.vulkan"; }   # the Radeon's Vulkan name
nothing_asked() {  # nothing_asked NAME: init was never asked to load, and the package never offered
  if grep -Eq 'lab.mod=nvidia-load|dgpu.ready|nvk.offer' "$P/.log"; then echo "FAIL $1: $(cat "$P/.log")"; fails=$((fails + 1))
  else echo "ok   $1"; fi
}

fresh; r=$T/drv-none; mkdir -p "$r/sys/bus/pci/devices"; pci "$r" 0000:65:00.0 0x1002 0x030000 amdgpu
drv "$r" boot
check "dgpu-driver no NVIDIA GPU: exit 0" "$r.rc" 0
has "dgpu-driver no NVIDIA GPU: said so" "$r.log" 'no NVIDIA GPU enumerated; nothing to load'
nothing_asked "dgpu-driver no NVIDIA GPU: nothing asked"

fresh; r=$T/drv-load; lab_root "$r"
drv "$r" boot
check "dgpu-driver boot: exit 0" "$r.rc" 0
check "dgpu-driver boot: guard, load, offer in order" "$P/.log" "persist.vendor.openbook.dgpu_driver=loading"
has "dgpu-driver boot: asked init for the lab's nvidia-load" "$P/.log" '^vendor.openbook.lab.mod=nvidia-load$'
check "dgpu-driver boot: request reset" "$P/vendor.openbook.lab.mod" idle
check "dgpu-driver boot: guard cleared" "$P/persist.vendor.openbook.dgpu_driver" on
check "dgpu-driver boot: NVIDIA's driver ready" "$P/vendor.openbook.dgpu.ready" nvidia
check "dgpu-driver boot: package offered" "$P/vendor.openbook.nvk.offer" 1
if [ "$(tail -n 1 "$P/.log")" = vendor.openbook.nvk.offer=1 ]; then echo "ok   dgpu-driver boot: offered last"
else echo "FAIL dgpu-driver boot: offered last: $(cat "$P/.log")"; fails=$((fails + 1)); fi
has "dgpu-driver boot: said so" "$r.log" 'dgpu-driver: NVIDIA.s driver drives 0000:64:00.0; OpenBook NVK \(org.openbook.nvk\) is offered'
has "dgpu-driver boot: report after" "$r.log" 'dgpu-report: '
# Already loaded (the lab, or a second start): no second load, offered.
: > "$P/.log"
drv "$r" boot
check "dgpu-driver already loaded: exit 0" "$r.rc" 0
grep -q 'lab.mod=nvidia-load' "$P/.log" && { echo "FAIL dgpu-driver already loaded: asked init again"; fails=$((fails + 1)); } ||
  echo "ok   dgpu-driver already loaded: init not asked again"
has "dgpu-driver already loaded: offered" "$P/.log" '^vendor.openbook.nvk.offer=1$'
# The lab's nvidia-unload warns once the package is offered.
w "$P/persist.vendor.openbook.lab" 1
labrun "$r" lab nvidia-unload
has "lab nvidia-unload while offered: warns" "$r.log" 'apps opted in to it fail to start until'

fresh; r=$T/drv-off; lab_root "$r"
drv "$r" off
check "dgpu-driver off: exit 0" "$r.rc" 0
check "dgpu-driver off: persisted" "$P/persist.vendor.openbook.dgpu_driver" off
drv "$r" boot
check "dgpu-driver boot while off: exit 0" "$r.rc" 0
has "dgpu-driver boot while off: said how to turn on" "$r.log" "boot load off .*debug.openbook.dgpu_driver on"
nothing_asked "dgpu-driver boot while off: nothing asked"
drv "$r" maybe
check "dgpu-driver bad value: exit 2" "$r.rc" 2
check "dgpu-driver bad value: choice kept" "$P/persist.vendor.openbook.dgpu_driver" off

fresh; r=$T/drv-crash; lab_root "$r"; w "$P/persist.vendor.openbook.dgpu_driver" loading
drv "$r" boot
check "dgpu-driver after an unfinished load: exit 0" "$r.rc" 0
check "dgpu-driver after an unfinished load: failed" "$P/persist.vendor.openbook.dgpu_driver" failed
has "dgpu-driver after an unfinished load: said why" "$r.log" "never finished"
nothing_asked "dgpu-driver after an unfinished load: nothing asked"
drv "$r" boot
nothing_asked "dgpu-driver while failed: nothing asked"
has "dgpu-driver while failed: said how to retry" "$r.log" "earlier boot load failed .*debug.openbook.dgpu_driver on"
drv "$r" on
check "dgpu-driver on: clears failed" "$P/persist.vendor.openbook.dgpu_driver" on
drv "$r" boot
check "dgpu-driver on, then boot: offered" "$P/vendor.openbook.nvk.offer" 1

# The package is offered only when the image has it (ANAL-327; the G14 found the offer without it on 2026-11-02,
# ANAL-331), and only when Android's loader asks for the name its library has (ro.hardware.vulkan=radv).
fresh; r=$T/drv-nopkg; lab_root "$r"; rm "$r/vendor/app/OpenBookNvk/OpenBookNvk.apk"
drv "$r" boot
check "dgpu-driver without the package: exit 0" "$r.rc" 0
check "dgpu-driver without the package: NVIDIA's driver ready" "$P/vendor.openbook.dgpu.ready" nvidia
[ -e "$P/vendor.openbook.nvk.offer" ] && { echo "FAIL dgpu-driver without the package: offered"; fails=$((fails + 1)); } ||
  echo "ok   dgpu-driver without the package: not offered"
has "dgpu-driver without the package: said so" "$r.log" 'this image has no OpenBook NVK package .*every app uses the Radeon'
grep -q 'NVK (org.openbook.nvk) is offered' "$r.log" && { echo "FAIL dgpu-driver without the package: log says offered"; fails=$((fails + 1)); } ||
  echo "ok   dgpu-driver without the package: log does not say offered"
fresh; r=$T/drv-vk; lab_root "$r"; echo pastel > "$P/ro.hardware.vulkan"
drv "$r" boot
[ -e "$P/vendor.openbook.nvk.offer" ] && { echo "FAIL dgpu-driver with another Vulkan name: offered"; fails=$((fails + 1)); } ||
  echo "ok   dgpu-driver with another Vulkan name: not offered"
has "dgpu-driver with another Vulkan name: said so" "$r.log" "ro.hardware.vulkan is 'pastel', not radv"

fresh; r=$T/drv-noinit; lab_root "$r"
FAKE_INIT=0 WAIT=1 drv "$r" boot
check "dgpu-driver module never came: exit 5" "$r.rc" 5
check "dgpu-driver module never came: failed" "$P/persist.vendor.openbook.dgpu_driver" failed
check "dgpu-driver module never came: request reset" "$P/vendor.openbook.lab.mod" idle
[ -e "$P/vendor.openbook.nvk.offer" ] || [ -e "$P/vendor.openbook.dgpu.ready" ] && { echo "FAIL dgpu-driver module never came: offered"; fails=$((fails + 1)); } ||
  echo "ok   dgpu-driver module never came: not offered"

fresh; r=$T/drv-nobind; lab_root "$r"
FAKE_BIND=0 WAIT=1 drv "$r" boot
check "dgpu-driver loaded but not bound: exit 5" "$r.rc" 5
check "dgpu-driver loaded but not bound: failed" "$P/persist.vendor.openbook.dgpu_driver" failed
has "dgpu-driver loaded but not bound: said so" "$r.log" "did not bind 0000:64:00.0"
[ -e "$P/vendor.openbook.nvk.offer" ] || [ -e "$P/vendor.openbook.dgpu.ready" ] && { echo "FAIL dgpu-driver not bound: offered"; fails=$((fails + 1)); } ||
  echo "ok   dgpu-driver not bound: not offered"

fresh; r=$T/drv-nouveau; lab_root "$r"; mkdir -p "$r/sys/module/nouveau"
drv "$r" boot
check "dgpu-driver with nouveau: exit 0" "$r.rc" 0
has "dgpu-driver with nouveau: said so" "$r.log" "nouveau is loaded and drives the same GPU"
nothing_asked "dgpu-driver with nouveau: nothing asked"

# ANAL-320: a public image has NVIDIA's modules but not its GSP firmware. No load, no offer, and the guard untouched.
fresh; r=$T/drv-nofw; lab_root "$r"; rm -rf "$r/vendor/firmware/nvidia"
drv "$r" boot
check "dgpu-driver without GSP firmware: exit 0" "$r.rc" 0
has "dgpu-driver without GSP firmware: said why" "$r.log" "no GSP firmware for NVIDIA's driver in this image"
nothing_asked "dgpu-driver without GSP firmware: nothing asked"
[ -e "$P/persist.vendor.openbook.dgpu_driver" ] && { echo "FAIL dgpu-driver without GSP firmware: guard written"; fails=$((fails + 1)); } ||
  echo "ok   dgpu-driver without GSP firmware: guard untouched"

# dgpu-driver shutdown (ANAL-322): init's shutdown trigger, reached only by an orderly restart or power-off. A guard
# still "loading" with NVIDIA's driver bound is no crash; one whose load never bound stays for the next boot.
fresh; r=$T/drv-shutdown; lab_root "$r"
FAKE_SYS=$r PROPS=$P "$T/setprop" vendor.openbook.lab.mod nvidia-load   # the boot load bound the GPU...
w "$P/persist.vendor.openbook.dgpu_driver" loading                        # ...and is still in its settle time
drv "$r" shutdown
check "dgpu-driver shutdown in the settle time: exit 0" "$r.rc" 0
check "dgpu-driver shutdown in the settle time: guard cleared" "$P/persist.vendor.openbook.dgpu_driver" on
has "dgpu-driver shutdown in the settle time: said why" "$r.log" "not a crash; guard cleared"
drv "$r" boot
check "dgpu-driver shutdown, next boot: loads again" "$P/vendor.openbook.dgpu.ready" nvidia
fresh; r=$T/drv-shutdown-unbound; lab_root "$r"; w "$P/persist.vendor.openbook.dgpu_driver" loading
drv "$r" shutdown
check "dgpu-driver shutdown before the bind: guard kept" "$P/persist.vendor.openbook.dgpu_driver" loading
has "dgpu-driver shutdown before the bind: said so" "$r.log" "guard stays 'loading'"
fresh; r=$T/drv-shutdown-idle; lab_root "$r"; w "$P/persist.vendor.openbook.dgpu_driver" failed
drv "$r" shutdown
check "dgpu-driver shutdown, guard failed: exit 0" "$r.rc" 0
check "dgpu-driver shutdown, guard failed: kept" "$P/persist.vendor.openbook.dgpu_driver" failed

# klog (ANAL-402): the kernel log's GPU lines for one run, with proof that none is missing. The fake kernel log is a
# file of /dev/kmsg records ("PRIO,SEQ,T_US,FLAGS;TEXT", a dictionary as lines that start with a space); kmsg-mark does
# what the kernel does with a write to /dev/kmsg: one more record, with the next sequence number.
cat > "$T/kmsg-mark" <<'MARK'
#!/bin/sh
f=$1; shift
last=$(sed -n 's/^[0-9]*,\([0-9]*\),.*/\1/p' "$f" 2>/dev/null | tail -n 1)
t=$(sed -n 's/^[0-9]*,[0-9]*,\([0-9]*\),.*/\1/p' "$f" 2>/dev/null | tail -n 1)
echo "12,$(( ${last:--1} + 1 )),$(( ${t:-0} + 1000 )),-;$*" >> "$f"
MARK
chmod +x "$T/kmsg-mark"
rec() { echo "6,$2,$3,-;$4" >> "$1"; }   # rec KMSG SEQ T_US TEXT
kl() {  # kl ROOT KMSG REQUEST [NAME=VALUE...]: the helper's klog on the fake kernel log
  r=$1; k=$2; q=$3; shift 3
  env LOGD_OUT="$r.logd" OPENBOOK_LOGCMD="$stub" OPENBOOK_SYSFS_ROOT="$r" OPENBOOK_KMSG="$k" \
    OPENBOOK_KMSG_MARK="$T/kmsg-mark $k" "$@" "$SH" "$SCRIPT" klog "$q" > "$r.log" 2>&1
  echo $? > "$r.rc"
}
hasnt() {  # hasnt NAME FILE PATTERN
  if grep -Eq -- "$3" "$2" 2>/dev/null; then echo "FAIL $1: /$3/ in $2: $(cat "$2")"; fails=$((fails + 1)); else echo "ok   $1"; fi
}
ID=a1b2c3d4e5f60718
BOOT=7f0c2a9e-52d1-4b7e-9a64-0d1f3c5b8e21
SUM='sum=[0-9a-f]{64}'            # every line of an answer ends with, or (a "line") carries, its SHA-256
LF="fl=- len=[0-9]+ $SUM"         # a whole record handed over: its flags, its text's length, its sum
# whole NAME FILE PATTERN: the one line of FILE matching PATTERN arrived as the helper made it: the SHA-256 of the
# line without its sum field (and a newline) is its sum, and a "line"'s len is its text's length.
whole() {
  wl=$(grep -E -- "$3" "$2" 2>/dev/null | head -n 1); wl=${wl#openbook-pc-setup: klog: }
  case $wl in
    line\ *) wb=${wl%% sum=*}; wr=${wl#* sum=}; wh=${wr%% *}; wt=${wr#* }; wn=${wb##* len=}
             want=$(printf '%s %s\n' "$wb" "$wt" | sha256sum); [ "$wn" = "${#wt}" ] || want=bad-length ;;
    *) wb=${wl% sum=*}; wh=${wl##* sum=}; want=$(printf '%s\n' "$wb" | sha256sum) ;;
  esac
  if [ -n "$wl" ] && [ "$wh" = "${want%% *}" ]; then echo "ok   $1"; else echo "FAIL $1: '$wl' sum should be ${want%% *}"; fails=$((fails + 1)); fi
}
XID='NVRM: Xid (PCI:0000:64:00): 13, pid=9001, name=deqp-vk, Graphics Exception: ESR 0x404600=0x80000002'
RING='amdgpu 0000:65:00.0: [drm] *ERROR* ring gfx_0.0.0 timeout, signaled seq=1215, emitted seq=1217'
# klog_begin ROOT KMSG: a ring that already holds one of NVIDIA's lines from before the run, then the checkpoint (102).
klog_begin() {
  mkdir -p "$1/proc/sys/kernel/random"; echo $BOOT > "$1/proc/sys/kernel/random/boot_id"; : > "$2"
  rec "$2" 100 5000000 'NVRM: loading NVIDIA UNIX Open Kernel Module for x86_64  615.78.08'
  rec "$2" 101 6000000 'init: starting service vendor.openbook.klog'
  kl "$1" "$2" begin@$ID
}

# Clean coverage: every record from the checkpoint to the end marker was read, and none is a GPU line. The old NVIDIA
# line in the ring is before the checkpoint, so it says nothing about this run. A record's dictionary is not a record.
r=$T/klog-clean; k=$r.kmsg; klog_begin "$r" "$k"
check "klog begin: exit 0" "$r.rc" 0
has "klog begin: the marker's sequence number, tied to the request" "$r.log" \
  "klog: begin id=$ID status=ok boot=$BOOT seq=102 t_us=6001000 first_seq=100 $SUM\$"
whole "klog begin: the answer's sum is its SHA-256" "$r.log" "klog: begin id=$ID status=ok"
has "klog begin: logd copy" "$r.logd" "^-t openbook-pc-setup -p i klog: begin id=$ID status=ok"
has "klog begin: the marker is in the kernel log" "$k" "^12,102,6001000,-;openbook-pc-setup: klog begin id=$ID tok=[0-9-]+\$"
rec "$k" 104 7000000 'binder: 1228:1228 transaction failed 29189/-22, size 0-0 line 3095'
rec "$k" 105 8000000 'pci 0000:65:00.0: enabling device (0006 -> 0007)'
printf ' SUBSYSTEM=pci\n DEVICE=+pci:0000:65:00.0\n DRIVER=amdgpu\n' >> "$k"
kl "$r" "$k" end@$ID@102
check "klog end, clean: exit 0" "$r.rc" 0
has "klog end, clean: complete, no lines" "$r.log" \
  "klog: end id=$ID status=complete boot=$BOOT begin_seq=102 end_seq=106 first_seq=100 records=5 lines=0 sent=0 cut=0 cont=0 filter=gpu1 $SUM\$"
hasnt "klog end, clean: no line handed over" "$r.log" 'klog: line '
whole "klog end, clean: the closing line's sum is its SHA-256" "$r.log" "klog: end id=$ID status=complete"

# An error from each GPU, whichever drew, and records in the same microsecond: two Xid reports with the same time and
# text are two records, told apart by their sequence numbers.
r=$T/klog-errors; k=$r.kmsg; klog_begin "$r" "$k"
rec "$k" 104 9000000 "$XID"
rec "$k" 105 9000000 "$RING"
rec "$k" 106 9000000 "$XID"
rec "$k" 107 9000000 'NVRM: GPU 0000:64:00.0: GPU has fallen off the bus.'
rec "$k" 108 9000000 'healthd: battery l=80 v=15800 t=31.0 h=2 st=3'
kl "$r" "$k" end@$ID@102
check "klog end, errors: exit 0 (the coverage is complete)" "$r.rc" 0
has "klog end, errors: NVIDIA's Xid, with its sequence number and time" "$r.log" \
  "klog: line id=$ID n=1/4 seq=104 t_us=9000000 fl=- len=99 $SUM NVRM: Xid \\(PCI:0000:64:00\\): 13, pid=9001, name=deqp-vk, Graphics Exception: ESR 0x404600=0x80000002\$"
whole "klog end, errors: a line's sum covers its header and its text, and len is the text's length" "$r.log" "klog: line id=$ID n=2/4 "
has "klog end, errors: amdgpu's ring timeout" "$r.log" \
  "klog: line id=$ID n=2/4 seq=105 t_us=9000000 $LF amdgpu 0000:65:00.0: \\[drm\\] \\*ERROR\\* ring gfx_0.0.0 timeout"
has "klog end, errors: the same Xid text in the same microsecond is its own record" "$r.log" \
  "klog: line id=$ID n=3/4 seq=106 t_us=9000000 $LF NVRM: Xid "
has "klog end, errors: off the bus" "$r.log" "klog: line id=$ID n=4/4 seq=107 t_us=9000000 $LF NVRM: GPU 0000:64:00.0: GPU has fallen off the bus.\$"
has "klog end, errors: complete, four lines" "$r.log" \
  "klog: end id=$ID status=complete boot=$BOOT begin_seq=102 end_seq=109 first_seq=100 records=8 lines=4 sent=4 cut=0 cont=0 filter=gpu1 $SUM\$"
hasnt "klog end, errors: the line from before the checkpoint is not handed over" "$r.log" 'klog: line .*loading NVIDIA'
has "klog end, errors: logd copy of a line" "$r.logd" "^-t openbook-pc-setup -p i klog: line id=$ID n=2/4 seq=105 t_us=9000000 $LF amdgpu "

# Ring eviction: the ring's oldest record is newer than the checkpoint. What is left was logged after it, so it is
# still handed over (it can fail a run), but the answer is not "complete".
r=$T/klog-evicted; k=$r.kmsg; klog_begin "$r" "$k"
rec "$k" 104 9000000 "$XID"
rec "$k" 105 9100000 'init: processing action (sys.boot_completed=1)'
rec "$k" 106 9200000 "$RING"
sed -n '/^6,105,/,$p' "$k" > "$k.new" && mv "$k.new" "$k"
kl "$r" "$k" end@$ID@102
check "klog end, ring eviction: exit 1" "$r.rc" 1
has "klog end, ring eviction: evicted, and it says where the ring begins" "$r.log" \
  "klog: end id=$ID status=evicted boot=$BOOT begin_seq=102 end_seq=107 first_seq=105 records=3 lines=1 sent=1 cut=0 cont=0 filter=gpu1 $SUM\$"
has "klog end, ring eviction: what is left is handed over" "$r.log" "klog: line id=$ID n=1/1 seq=106 t_us=9200000 $LF amdgpu "

# A restart between the two requests: this boot's log has no record 102 yet, or its record 102 is something else.
r=$T/klog-reboot; k=$r.kmsg; klog_begin "$r" "$k"
: > "$k"; echo 0c6d7e1a-0000-4000-8000-9b1d2f3a4c5e > "$r/proc/sys/kernel/random/boot_id"
rec "$k" 0 100 'Linux version 6.18.21-android17-5'; rec "$k" 1 200 "$XID"
kl "$r" "$k" end@$ID@102
check "klog end, restarted (a short log): exit 1" "$r.rc" 1
has "klog end, restarted (a short log): other-boot, the new boot's id" "$r.log" \
  "klog: end id=$ID status=other-boot boot=0c6d7e1a-0000-4000-8000-9b1d2f3a4c5e begin_seq=102 end_seq=2 first_seq=0 records=0 lines=0 sent=0 cut=0 cont=0 filter=gpu1 $SUM\$"
hasnt "klog end, restarted (a short log): no line handed over" "$r.log" 'klog: line '
: > "$k"; i=0; while [ $i -lt 120 ]; do rec "$k" $i $((i * 1000)) "init: boot step $i"; i=$((i + 1)); done
kl "$r" "$k" end@$ID@102
has "klog end, restarted (record 102 is another line): other-boot" "$r.log" "klog: end id=$ID status=other-boot .* end_seq=120 "
# A line that only quotes a marker is not the marker, and neither is another run's.
: > "$k"; i=0; while [ $i -lt 102 ]; do rec "$k" $i $((i * 1000)) "init: boot step $i"; i=$((i + 1)); done
rec "$k" 102 102000 "audit: msg='x;openbook-pc-setup: klog begin id=$ID tok=1-1-1'"
kl "$r" "$k" end@$ID@102
has "klog end, a quoted marker at that number: other-boot" "$r.log" "klog: end id=$ID status=other-boot "
: > "$k"; i=0; while [ $i -lt 102 ]; do rec "$k" $i $((i * 1000)) "init: boot step $i"; i=$((i + 1)); done
rec "$k" 102 102000 'openbook-pc-setup: klog begin id=ffffffff00000000 tok=1-1-1'
kl "$r" "$k" end@$ID@102
has "klog end, another run's marker at that number: other-boot" "$r.log" "klog: end id=$ID status=other-boot "

# A sequence number between the two markers that was not read (the ring overwrote records while it was read).
r=$T/klog-gap; k=$r.kmsg; klog_begin "$r" "$k"
rec "$k" 104 9000000 'init: a'; rec "$k" 106 9000002 "$RING"; rec "$k" 107 9000003 'init: b'
kl "$r" "$k" end@$ID@102
check "klog end, a missing record: exit 1" "$r.rc" 1
has "klog end, a missing record: gap" "$r.log" \
  "klog: end id=$ID status=gap boot=$BOOT begin_seq=102 end_seq=108 first_seq=100 records=6 lines=1 sent=1 cut=0 cont=0 filter=gpu1 $SUM\$"

# A line the kernel printed in pieces and could not join (another message came in between): the second piece is its
# own record, flagged "c". Here the error is split over the two, and neither piece reads as one. The helper doesn't
# join them, so the answer is not "complete"; both pieces are handed over for a person to read.
r=$T/klog-fragment; k=$r.kmsg; klog_begin "$r" "$k"
rec "$k" 104 9000000 'amdgpu 0000:65:00.0: [drm] *ERROR* ring gfx_0.0.0 '
rec "$k" 105 9000001 'healthd: battery l=80 v=15800 t=31.0 h=2 st=3'
echo '6,106,9000002,c;timeout, signaled seq=1215, emitted seq=1217' >> "$k"
kl "$r" "$k" end@$ID@102
check "klog end, an error split over a continuation fragment: exit 1" "$r.rc" 1
has "klog end, an error split over a continuation fragment: fragmented, never complete" "$r.log" \
  "klog: end id=$ID status=fragmented boot=$BOOT begin_seq=102 end_seq=107 first_seq=100 records=6 lines=2 sent=2 cut=0 cont=1 filter=gpu1 $SUM\$"
has "klog end, an error split over a continuation fragment: the first piece" "$r.log" \
  "klog: line id=$ID n=1/2 seq=104 t_us=9000000 fl=- len=50 $SUM amdgpu 0000:65:00.0: \\[drm\\] \\*ERROR\\* ring gfx_0.0.0 \$"
has "klog end, an error split over a continuation fragment: the fragment, though it names no GPU" "$r.log" \
  "klog: line id=$ID n=2/2 seq=106 t_us=9000002 fl=c len=44 $SUM timeout, signaled seq=1215, emitted seq=1217\$"
whole "klog end, an error split over a continuation fragment: a text ending in a space keeps its length" "$r.log" "klog: line id=$ID n=1/2 "
# A fragment that names no GPU, after lines that do: still not complete. Older kernels flag "+", and the caller id
# of CONFIG_PRINTK_CALLER follows the flags.
r=$T/klog-fragment2; k=$r.kmsg; klog_begin "$r" "$k"
echo '6,104,9000000,+;x86/split lock detection: warn' >> "$k"
echo '6,105,9000001,c,caller=T812;failed' >> "$k"
kl "$r" "$k" end@$ID@102
has "klog end, fragments flagged + and c,caller=: fragmented, both counted" "$r.log" \
  "klog: end id=$ID status=fragmented .* records=5 lines=2 sent=2 cut=0 cont=2 filter=gpu1 $SUM\$"
has "klog end, fragments flagged + and c,caller=: the caller id is not part of the flags" "$r.log" "n=2/2 seq=105 t_us=9000001 fl=c len=6 $SUM failed\$"
# Whole lines from a kernel that names each record's caller are not fragments.
r=$T/klog-caller; k=$r.kmsg; klog_begin "$r" "$k"
echo '6,104,9000000,-,caller=T812;init: starting service' >> "$k"
echo "3,105,9000001,-,caller=C3;$RING" >> "$k"
kl "$r" "$k" end@$ID@102
check "klog end, records with caller ids: exit 0" "$r.rc" 0
has "klog end, records with caller ids: complete, no fragment" "$r.log" \
  "klog: end id=$ID status=complete boot=$BOOT begin_seq=102 end_seq=106 first_seq=100 records=5 lines=1 sent=1 cut=0 cont=0 filter=gpu1 $SUM\$"
has "klog end, records with caller ids: the line" "$r.log" "klog: line id=$ID n=1/1 seq=105 t_us=9000001 fl=- len=[0-9]+ $SUM amdgpu "
# An evicted ring that also holds a fragment stays "evicted": either way it is not complete.
r=$T/klog-evicted-fragment; k=$r.kmsg; klog_begin "$r" "$k"
rec "$k" 104 9000000 'init: a'; echo '6,105,9000001,c;b' >> "$k"
sed -n '/^6,104,/,$p' "$k" > "$k.new" && mv "$k.new" "$k"
kl "$r" "$k" end@$ID@102
has "klog end, evicted and fragmented: not complete" "$r.log" "klog: end id=$ID status=evicted .* cont=1 filter=gpu1 $SUM\$"

# A truncated answer: more matching lines than one answer carries. It says how many matched and how many it sent.
r=$T/klog-truncated; k=$r.kmsg; klog_begin "$r" "$k"
rec "$k" 104 9000000 "$XID"; rec "$k" 105 9000001 "$RING"; rec "$k" 106 9000002 'nouveau 0000:64:00.0: fifo: fault 01'
kl "$r" "$k" end@$ID@102 OPENBOOK_KLOG_MAX=2
check "klog end, truncated: exit 1" "$r.rc" 1
has "klog end, truncated: says so" "$r.log" \
  "klog: end id=$ID status=truncated boot=$BOOT begin_seq=102 end_seq=107 first_seq=100 records=6 lines=3 sent=2 cut=0 cont=0 filter=gpu1 $SUM\$"
has "klog end, truncated: the first two lines" "$r.log" "klog: line id=$ID n=2/2 seq=105 t_us=9000001 $LF amdgpu "
hasnt "klog end, truncated: not the third" "$r.log" 'klog: line .* seq=106 '

# A line longer than one answer line carries is cut, and the answer says so: its end may have held the error.
r=$T/klog-cut; k=$r.kmsg; klog_begin "$r" "$k"
rec "$k" 104 9000000 "NVRM: $(printf '%01300d' 7) failed"
kl "$r" "$k" end@$ID@102
check "klog end, a line cut short: exit 1" "$r.rc" 1
has "klog end, a line cut short: says so" "$r.log" \
  "klog: end id=$ID status=truncated boot=$BOOT begin_seq=102 end_seq=105 first_seq=100 records=4 lines=1 sent=1 cut=1 cont=0 filter=gpu1 $SUM\$"

# A ring the G14's size (~250 KiB), the run's lines at both ends of it.
r=$T/klog-big; k=$r.kmsg; klog_begin "$r" "$k"
rec "$k" 104 9000000 "$XID"
i=105; while [ $i -lt 2405 ]; do
  rec "$k" $i $((9000000 + i)) "avc:  denied  { find } for pid=1228 uid=1000 name=vendor.google.desktop.x/default scontext=u:r:system_app:s0"
  i=$((i + 1)); done
rec "$k" 2405 9900000 "$RING"
kl "$r" "$k" end@$ID@102
has "klog end, a ring over 128 KiB: complete" "$r.log" \
  "klog: end id=$ID status=complete boot=$BOOT begin_seq=102 end_seq=2406 first_seq=100 records=2305 lines=2 sent=2 cut=0 cont=0 filter=gpu1 $SUM\$"
has "klog end, a ring over 128 KiB: the last line" "$r.log" "klog: line id=$ID n=2/2 seq=2405 t_us=9900000 $LF amdgpu "

# The marker can't be written or read back (the kernel drops writes to /dev/kmsg, or the read ends early), or the
# kernel log can't be read at all: no answer that could pass for coverage.
r=$T/klog-nomark; k=$r.kmsg; klog_begin "$r" "$k"
kl "$r" "$k" end@$ID@102 OPENBOOK_KMSG_MARK=true
check "klog end, no marker: exit 1" "$r.rc" 1
has "klog end, no marker: says so" "$r.log" "klog: end id=$ID status=no-marker boot=$BOOT $SUM\$"
kl "$r" "$k" begin@$ID OPENBOOK_KMSG_MARK=true
has "klog begin, no marker: says so" "$r.log" "klog: begin id=$ID status=no-marker boot=$BOOT $SUM\$"
kl "$r" "$r.absent" begin@$ID
check "klog begin, no kernel log: exit 1" "$r.rc" 1
has "klog begin, no kernel log: unreadable" "$r.log" "klog: begin id=$ID status=unreadable boot=$BOOT $SUM\$"

# Requests are the shell user's: anything but begin@ID and end@ID@SEQ is refused before the kernel log is touched.
r=$T/klog-bad; k=$r.kmsg; klog_begin "$r" "$k"; cp "$k" "$k.before"
for q in begin "begin@" begin@short begin@a1b2-c3d4e5f6 "begin@$ID@102" "end@$ID" "end@$ID@12x" "end@$ID@1234567890" \
         "end@$ID@1@2" "report@$ID" "begin@a1b2c3d4e5f60718a1b2c3d4e5f60718a" 'begin@a1b2c3d4$(id)'; do
  kl "$r" "$k" "$q"
  check "klog '$q': refused (exit 2)" "$r.rc" 2
done
has "klog: a refused request says what it takes" "$r.log" 'is neither begin@ID nor end@ID@SEQ'
cmp -s "$k" "$k.before" && echo "ok   klog: a refused request writes no marker" ||
  { echo "FAIL klog: a refused request wrote to the kernel log"; fails=$((fails + 1)); }

echo "openbook-pc-setup-test: $fails failure(s)"
[ $fails = 0 ]
