#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Fixture tests for dgpu-power-check.sh: builds fake sysfs trees for the G14 cases and checks each verdict.
# usage: dgpu-power-check-test.sh [SHELL]   e.g. bash, or AOSP's mksh with toybox first in PATH
set -u
SH=${1:-sh}
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d "${TMPDIR:-/tmp}/dgpu-check-test.XXXXXX")
trap 'rm -rf "$T"' EXIT
fails=0

w() { mkdir -p "$(dirname "$1")"; printf '%s\n' "$2" > "$1"; }

# base ROOT BOARD DGPU_DISABLE BRIDGE_STATE
base() {
  r=$1
  w "$r/sys/class/dmi/id/board_name" "$2"
  w "$r/sys/class/dmi/id/bios_version" "$2.309"
  w "$r/sys/devices/platform/asus-nb-wmi/dgpu_disable" "$3"
  w "$r/sys/devices/platform/asus-nb-wmi/gpu_mux_mode" 1
  w "$r/sys/devices/platform/asus-nb-wmi/egpu_enable" 0
  b=$r/sys/devices/pci0000:00/0000:00:03.1
  w "$b/vendor" 0x1022; w "$b/class" 0x060400; w "$b/power_state" "$4"
  w "$b/power/runtime_status" suspended; w "$b/power/control" auto; w "$b/d3cold_allowed" 1
  mkdir -p "$r/sys/bus/pci/devices" "$r/sys/class/power_supply"
  ln -s ../../../devices/pci0000:00/0000:00:03.1 "$r/sys/bus/pci/devices/0000:00:03.1"
  w "$r/sys/class/power_supply/BAT1/type" Battery
  w "$r/sys/class/power_supply/BAT1/current_now" 1064000
  w "$r/sys/class/power_supply/BAT1/voltage_now" 16344000
  w "$r/sys/class/power_supply/ACAD/type" Mains
  w "$r/sys/class/power_supply/ACAD/online" 0
}

# acpi ROOT IN_USE: GPP bridge node with one D0 and one D3hot power resource, plus a PEGP child
acpi() {
  a=$1/sys/devices/LNXSYSTM:00/LNXSYBUS:00/PNP0A08:00
  w "$a/device:0b/path" '\_SB_.PCI0.GPP0'
  w "$a/device:0b/power_state" D0
  w "$a/device:0b/device:0c/path" '\_SB_.PCI0.GPP0.PEGP'
  w "$a/LNXPOWER:0a/resource_in_use" "$2"
  mkdir -p "$a/device:0b/power_resources_D0" "$a/device:0b/power_resources_D3hot"
  ln -s ../../LNXPOWER:0a "$a/device:0b/power_resources_D0/LNXPOWER:0a"
  ln -s ../../LNXPOWER:0a "$a/device:0b/power_resources_D3hot/LNXPOWER:0a"
  ln -s ../../LNXSYSTM:00/LNXSYBUS:00/PNP0A08:00/device:0b "$1/sys/devices/pci0000:00/0000:00:03.1/firmware_node"
}

# func ROOT FN CLASS DEVICE POWER_STATE [DRIVER]
func() {
  d=$1/sys/devices/pci0000:00/0000:00:03.1/0000:01:00.$2
  w "$d/vendor" 0x10de; w "$d/class" "$3"; w "$d/device" "$4"; w "$d/power_state" "$5"
  w "$d/power/runtime_status" active; w "$d/power/control" on; w "$d/d3cold_allowed" 1
  ln -s "../../../devices/pci0000:00/0000:00:03.1/0000:01:00.$2" "$1/sys/bus/pci/devices/0000:01:00.$2"
  if [ -n "${6:-}" ]; then
    mkdir -p "$1/sys/bus/pci/drivers/$6"
    ln -s "../../../../bus/pci/drivers/$6" "$d/driver"
  fi
}

# check NAME EXPECTED_STATE EXPECTED_RC ROOT [ARGS]
check() {
  name=$1; want=$2; wantrc=$3; root=$4; shift 4
  out=$(DGPU_CHECK_ROOT=$root "$SH" "$HERE/dgpu-power-check.sh" "$@" 2>/dev/null); rc=$?
  got=$(printf '%s' "$out" | sed -n 's/.*"dgpu_state":"\([^"]*\)".*/\1/p')
  ok=1; [ "$got" = "$want" ] && [ "$rc" = "$wantrc" ] || ok=0
  if [ "$wantrc" != 3 ] && command -v python3 >/dev/null 2>&1; then
    printf '%s' "$out" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null || { ok=0; got="$got (invalid JSON)"; }
  fi
  if [ $ok = 1 ]; then echo "ok   $name: $got rc=$rc"; else echo "FAIL $name: got '$got' rc=$rc, want '$want' rc=$wantrc"; fails=$((fails + 1)); fi
  LAST=$out
}

r=$T/1; base "$r" GA403WR 1 D0
check "firmware dgpu_disable=1, not enumerated" absent-off 0 "$r"

r=$T/2; base "$r" GA403WR 0 D3cold; acpi "$r" 0
check "removed by the OS, port in D3cold, power resource off" absent-off 0 "$r"

r=$T/3; base "$r" GA403WR 0 D0; acpi "$r" 1
check "removed by the OS, port awake, power resource on" absent-powered 1 "$r"

r=$T/4; base "$r" GA403WR 0 D0
check "not enumerated, nothing to confirm power" absent-unknown 2 "$r"

r=$T/5; base "$r" GA403WR 0 D0; acpi "$r" 1
func "$r" 0 0x030000 0x2d58 D0; func "$r" 1 0x040300 0x22eb D0 snd_hda_intel
check "enumerated, no GPU driver, HDA bound (OpenBook today)" d0-no-driver 1 "$r"

r=$T/6; base "$r" GA403WR 0 D3cold; acpi "$r" 0
func "$r" 0 0x030200 0x2d58 D3cold; func "$r" 1 0x040300 0x22eb D3cold
check "enumerated, runtime PM reached D3cold" d3cold 0 "$r"

r=$T/7; base "$r" GA403WR 0 D0
func "$r" 0 0x030000 0x2d58 D0 nouveau
check "nouveau bound and awake" d0-driver 2 "$r"

r=$T/8; base "$r" GA403WR 1 D0; w "$r/system/build.prop" ro.build.version.sdk=37
check "Android, battery power from current x voltage" absent-off 0 "$r"
printf '%s' "$LAST" | grep -q '"os":"android"' || { echo "FAIL android detection"; fails=$((fails + 1)); }
printf '%s' "$LAST" | grep -q '"now_mw":"17390"' || { echo "FAIL battery mW (want 17390)"; fails=$((fails + 1)); }

r=$T/9; base "$r" GA403WR 0 D0
check "bad argument" "" 3 "$r" --try sideways

[ $fails = 0 ] && echo "all passed ($SH)" || echo "$fails failed ($SH)"
[ $fails = 0 ]
