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
runx() {  # runx ROOT ARGS...: run with the logd stub and no settle delay
  r=$1; shift
  LOGD_OUT=$r.logd OPENBOOK_LOGCMD=$stub OPENBOOK_SETTLE_S=0 OPENBOOK_SYSFS_ROOT=$r "$SH" "$SCRIPT" "$@" > "$r.log" 2>&1
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

echo "openbook-pc-setup-test: $fails failure(s)"
[ $fails = 0 ]
