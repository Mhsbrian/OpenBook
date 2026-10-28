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
lab_root() {  # a G14 with the dGPU in D3cold, an RTC and the suspend files
  g14_d3cold "$1"
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
fresh() { rm -f "$P"/* "$P/.log"; : > "$P/.log"; }
nothing_asked() {  # nothing_asked NAME: init was never asked to load, and the package never offered
  if grep -Eq 'lab.mod=nvidia-load|dgpu.ready' "$P/.log"; then echo "FAIL $1: $(cat "$P/.log")"; fails=$((fails + 1))
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
check "dgpu-driver boot: package offered" "$P/vendor.openbook.dgpu.ready" nvidia
if [ "$(tail -n 1 "$P/.log")" = vendor.openbook.dgpu.ready=nvidia ]; then echo "ok   dgpu-driver boot: offered last"
else echo "FAIL dgpu-driver boot: offered last: $(cat "$P/.log")"; fails=$((fails + 1)); fi
has "dgpu-driver boot: said so" "$r.log" 'dgpu-driver: NVIDIA.s driver drives 0000:64:00.0; OpenBook NVK is offered'
has "dgpu-driver boot: report after" "$r.log" 'dgpu-report: '
# Already loaded (the lab, or a second start): no second load, offered.
: > "$P/.log"
drv "$r" boot
check "dgpu-driver already loaded: exit 0" "$r.rc" 0
grep -q 'lab.mod=nvidia-load' "$P/.log" && { echo "FAIL dgpu-driver already loaded: asked init again"; fails=$((fails + 1)); } ||
  echo "ok   dgpu-driver already loaded: init not asked again"
has "dgpu-driver already loaded: offered" "$P/.log" '^vendor.openbook.dgpu.ready=nvidia$'
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
check "dgpu-driver on, then boot: offered" "$P/vendor.openbook.dgpu.ready" nvidia

fresh; r=$T/drv-noinit; lab_root "$r"
FAKE_INIT=0 WAIT=1 drv "$r" boot
check "dgpu-driver module never came: exit 5" "$r.rc" 5
check "dgpu-driver module never came: failed" "$P/persist.vendor.openbook.dgpu_driver" failed
check "dgpu-driver module never came: request reset" "$P/vendor.openbook.lab.mod" idle
[ -e "$P/vendor.openbook.dgpu.ready" ] && { echo "FAIL dgpu-driver module never came: offered"; fails=$((fails + 1)); } ||
  echo "ok   dgpu-driver module never came: not offered"

fresh; r=$T/drv-nobind; lab_root "$r"
FAKE_BIND=0 WAIT=1 drv "$r" boot
check "dgpu-driver loaded but not bound: exit 5" "$r.rc" 5
check "dgpu-driver loaded but not bound: failed" "$P/persist.vendor.openbook.dgpu_driver" failed
has "dgpu-driver loaded but not bound: said so" "$r.log" "did not bind 0000:64:00.0"
[ -e "$P/vendor.openbook.dgpu.ready" ] && { echo "FAIL dgpu-driver not bound: offered"; fails=$((fails + 1)); } ||
  echo "ok   dgpu-driver not bound: not offered"

fresh; r=$T/drv-nouveau; lab_root "$r"; mkdir -p "$r/sys/module/nouveau"
drv "$r" boot
check "dgpu-driver with nouveau: exit 0" "$r.rc" 0
has "dgpu-driver with nouveau: said so" "$r.log" "nouveau is loaded and drives the same GPU"
nothing_asked "dgpu-driver with nouveau: nothing asked"

echo "openbook-pc-setup-test: $fails failure(s)"
[ $fails = 0 ]
