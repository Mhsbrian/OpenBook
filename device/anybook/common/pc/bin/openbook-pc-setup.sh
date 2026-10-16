#!/vendor/bin/sh
# SPDX-License-Identifier: Apache-2.0
# OpenBook PC boot-time sysfs setup, run by init as root (init.openbook.rc). Android mksh + toybox; also runs under
# bash/dash for the fixture test (scripts/openbook-pc-setup-test.sh).
#
# usage: openbook-pc-setup dgpu-pm | perms
#   dgpu-pm  An NVIDIA dGPU (10de) is enumerated but no driver drives its display function, which is the
#            OpenBook default (docs/nvidia.md). The PCI core keeps an unbound device in D0, and snd_hda_intel
#            holds the HDMI-audio function awake: without vga_switcheroo it never runtime-suspends. So:
#              - unbind snd_hda_intel from the dGPU's HDMI-audio function (that HDMI port is on the dGPU and dark);
#              - set power/control=auto on every function of the dGPU, so the root port can take it to D3cold;
#              - give snd_hda_intel a non-zero power_save (10 s, as desktop Linux does).
#            Volatile: a reboot undoes it. Never touches asus-wmi (dgpu_disable, gpu_mux_mode), which persist in
#            firmware. Does nothing without an NVIDIA function, or when a driver (nouveau, later) binds the GPU.
#   perms    Hand amd-pstate's energy_performance_preference to the power HAL (user system). cpufreq policies send
#            no uevents, so ueventd.rc cannot do it.
# Testing: OPENBOOK_SYSFS_ROOT=<dir> works on <dir>/sys instead of /sys.
set -u
SYS=${OPENBOOK_SYSFS_ROOT:-}/sys
POWER_SAVE=10

log() { echo "openbook-pc-setup: $*"; }
rd() { [ -r "$1" ] && head -n 1 "$1" 2>/dev/null | tr -d '\n\r'; }
wr() {  # wr FILE VALUE: write and report
  if printf '%s\n' "$2" > "$1" 2>/dev/null; then log "$1 <- $2"; else log "FAILED $1 <- $2"; return 1; fi
}
driver_of() { d=$(readlink "$1/driver" 2>/dev/null) && basename "$d"; }

dgpu_pm() {
  rc=0
  # The display functions decide: a bound driver means someone owns the GPU's power.
  gpus=; others=
  for d in "$SYS"/bus/pci/devices/*; do
    [ "$(rd "$d/vendor")" = 0x10de ] || continue
    case $(rd "$d/class") in
      0x03*) gpus="$gpus ${d##*/}" ;;
      *) others="$others ${d##*/}" ;;
    esac
  done
  if [ -z "$gpus" ]; then
    log "no NVIDIA GPU enumerated; nothing to do"
    return 0
  fi
  for g in $gpus; do
    drv=$(driver_of "$SYS/bus/pci/devices/$g")
    if [ -n "$drv" ]; then
      log "$g is driven by $drv; leaving its power to the driver"
      return 0
    fi
  done
  hda=0
  for f in $others; do
    case $(rd "$SYS/bus/pci/devices/$f/class") in 0x0403*) hda=1 ;; esac
    if [ "$(driver_of "$SYS/bus/pci/devices/$f")" = snd_hda_intel ]; then
      wr "$SYS/bus/pci/drivers/snd_hda_intel/unbind" "$f" || rc=1
    fi
  done
  for f in $gpus $others; do
    wr "$SYS/bus/pci/devices/$f/power/control" auto || rc=1
  done
  if [ $hda = 1 ] && [ -e "$SYS/module/snd_hda_intel/parameters/power_save" ] &&
     [ "$(rd "$SYS/module/snd_hda_intel/parameters/power_save")" = 0 ]; then
    wr "$SYS/module/snd_hda_intel/parameters/power_save" $POWER_SAVE || rc=1
  fi
  for f in $gpus; do
    log "$f: power_state=$(rd "$SYS/bus/pci/devices/$f/power_state") runtime_status=$(rd "$SYS/bus/pci/devices/$f/power/runtime_status")"
  done
  return $rc
}

perms() {
  n=0
  for f in "$SYS"/devices/system/cpu/cpufreq/policy*/energy_performance_preference; do
    [ -e "$f" ] || continue
    chown system:system "$f" && chmod 0664 "$f" && n=$((n + 1))
  done
  log "energy_performance_preference: $n policies handed to the power HAL"
  [ "$(rd "$SYS/devices/system/cpu/amd_pstate/status")" ] && log "amd_pstate status: $(rd "$SYS/devices/system/cpu/amd_pstate/status")"
  return 0
}

case ${1:-} in
  dgpu-pm) dgpu_pm ;;
  perms) perms ;;
  *) echo "usage: openbook-pc-setup dgpu-pm|perms" >&2; exit 2 ;;
esac
