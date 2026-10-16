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

# 3. A driver owns the dGPU (nouveau, later work): leave its power to the driver.
r=$T/nouveau
pci "$r" 0000:64:00.0 0x10de 0x030000 nouveau
pci "$r" 0000:64:00.1 0x10de 0x040300 snd_hda_intel
w "$r/sys/module/snd_hda_intel/parameters/power_save" 0
run "$r" dgpu-pm
check "nouveau: exit 0" "$r.rc" 0
check "nouveau: dGPU untouched" "$r/sys/devices/pci0000:00/0000:00:03.1/0000:64:00.0/power/control" on
check "nouveau: audio still bound" "$r/sys/bus/pci/drivers/snd_hda_intel/unbind" ""

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

echo "openbook-pc-setup-test: $fails failure(s)"
[ $fails = 0 ]
