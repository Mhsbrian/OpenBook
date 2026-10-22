#!/vendor/bin/sh
# SPDX-License-Identifier: Apache-2.0
# OpenBook PC boot-time sysfs setup, run by init as root (init.openbook.rc). Android mksh + toybox; also runs under
# bash/dash for the fixture test (scripts/openbook-pc-setup-test.sh).
#
# usage: openbook-pc-setup dgpu-pm | dgpu-report [REASON] | dgpu-ctl on|auto | perms | kvm
#   dgpu-pm  An NVIDIA dGPU (10de) is enumerated but no driver drives its display function, which is the
#            OpenBook default (docs/nvidia.md). The PCI core keeps an unbound device in D0, and snd_hda_intel
#            holds the HDMI-audio function awake: without vga_switcheroo it never runtime-suspends. So:
#              - unbind snd_hda_intel from the dGPU's HDMI-audio function (that HDMI port is on the dGPU and dark);
#              - set power/control=auto on every function of the dGPU, so the root port can take it to D3cold;
#              - give snd_hda_intel a non-zero power_save (10 s, as desktop Linux does).
#            Volatile: a reboot undoes it. Never touches asus-wmi (dgpu_disable, gpu_mux_mode), which persist in
#            firmware. Does nothing without an NVIDIA function, or when a driver (nouveau, later) binds the GPU.
#   dgpu-report [REASON]
#            Log the dGPU's power state as root (ANAL-238): each NVIDIA function's driver, power_state,
#            runtime_status, control and runtime-PM times; the root port above it and its ACPI power resources;
#            asus-wmi's dgpu_disable and gpu_mux_mode (read only); /sys/power/suspend_stats; then a verdict named as
#            scripts/dgpu-power-check.sh names it (d3cold, d3hot, d0-no-driver, d0-driver, absent). Read-only, and
#            it never reads PCI config space, which would wake a suspended dGPU. A user build's shell can read
#            none of this, so init runs it at boot completion and whenever debug.openbook.dgpu_report changes;
#            read it with `logcat -d -s openbook-pc-setup`.
#   dgpu-ctl on|auto
#            Volatile power hold for battery comparisons (ANAL-238), from debug.openbook.dgpu_pm. "on" keeps every
#            NVIDIA function in D0 (power/control=on); "auto" is dgpu-pm again. Refused while a driver drives the
#            GPU. Then logs a dgpu-report. A reboot returns to the boot default (dgpu-pm).
#   perms    Hand amd-pstate's energy_performance_preference to the power HAL (user system). cpufreq policies send
#            no uevents, so ueventd.rc cannot do it.
#   kvm      Set vendor.openbook.kvm to 1 if KVM registered its device, else 0 (ANAL-218). KVM_AMD is built in, so
#            that happens exactly when the firmware has SVM on. init.openbook.rc turns 1 into the
#            ro.boot.hypervisor.* properties AVF reads, so the Linux environment is offered only where it can run.
#            It reads sysfs: only crosvm and ueventd may even stat /dev/kvm.
# Testing: OPENBOOK_SYSFS_ROOT=<dir> works on <dir>/sys instead of /sys; OPENBOOK_LOGCMD=<path> replaces
# /vendor/bin/log (empty: no logd copy).
set -u
SYS=${OPENBOOK_SYSFS_ROOT:-}/sys
POWER_SAVE=10
LOGCMD=${OPENBOOK_LOGCMD-/vendor/bin/log}

# Every line goes to stdout (init's stdio_to_kmsg) and to logd. stdio_to_kmsg writes to /dev/kmsg_debug, which
# Ruby's user platform policy leaves labelled tmpfs, so there every line was denied and lost (ANAL-238).
log() {
  echo "openbook-pc-setup: $*"
  [ -n "$LOGCMD" ] && [ -x "$LOGCMD" ] && "$LOGCMD" -t openbook-pc-setup -p i "$*" 2>/dev/null
  return 0
}
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

kv() { v=$(rd "$1"); [ -n "$v" ] && printf ' %s=%s' "$2" "$v"; return 0; }  # kv FILE KEY: " KEY=value"

# pm_facts DIR: a PCI function's runtime-PM state. These attributes are cached by the kernel: reading them does not
# touch the device.
pm_facts() {
  kv "$1/power_state" power_state; kv "$1/power/runtime_status" runtime_status; kv "$1/power/control" control
  kv "$1/d3cold_allowed" d3cold_allowed
  kv "$1/power/runtime_active_time" active_ms; kv "$1/power/runtime_suspended_time" suspended_ms
}

# acpi_facts NODE: an ACPI node's path and power state, and its power resources as NAME:resource_in_use.
acpi_facts() {
  [ -e "$1/path" ] || return 0
  kv "$1/path" acpi; kv "$1/power_state" acpi_state; kv "$1/real_power_state" acpi_real
  res=
  for r in "$1"/power_resources_D0/* "$1"/power_resources_D3hot/*; do
    [ -e "$r" ] || continue
    n=$(rd "$r/path"); n=${n:-${r##*/}}; n=${n##*.}
    case " $res " in *" $n:"*) continue ;; esac
    res="$res $n:$(rd "$r/resource_in_use")"
  done
  [ -n "$res" ] && printf ' resources=%s' "$(echo $res | tr ' ' ',')"
  return 0
}

dgpu_report() {
  log "dgpu-report (${1:-manual})"
  funcs=; gpus=; bridge=
  for p in "$SYS"/bus/pci/devices/*; do
    [ "$(rd "$p/vendor")" = 0x10de ] || continue
    funcs="$funcs ${p##*/}"
    case $(rd "$p/class") in 0x03*) gpus="$gpus ${p##*/}" ;; esac
  done
  any_d0=0; all_d3cold=1; unknown=0; gpu_drv=
  for f in $funcs; do
    p=$SYS/bus/pci/devices/$f
    drv=$(driver_of "$p"); ps=$(rd "$p/power_state")
    case " $gpus " in *" $f "*) [ -n "$drv" ] && gpu_drv=$drv ;; esac
    case $ps in D0) any_d0=1; all_d3cold=0 ;; D3cold) ;; '') unknown=1; all_d3cold=0 ;; *) all_d3cold=0 ;; esac
    log "dgpu-report: $f$(kv "$p/class" class)$(kv "$p/device" device) driver=${drv:--}$(pm_facts "$p")$(acpi_facts "$p/firmware_node")"
    if [ -z "$bridge" ]; then
      bridge=$(basename "$(dirname "$(readlink -f "$p")")")
      case $bridge in ????:??:??.?) ;; *) bridge= ;; esac
    fi
  done
  bps=
  if [ -n "$bridge" ] && [ -e "$SYS/bus/pci/devices/$bridge" ]; then
    b=$SYS/bus/pci/devices/$bridge; bps=$(rd "$b/power_state"); drv=$(driver_of "$b")
    log "dgpu-report: bridge $bridge driver=${drv:--}$(pm_facts "$b")$(acpi_facts "$b/firmware_node")"
  fi
  a=$SYS/devices/platform/asus-nb-wmi   # read only: writing these changes the firmware
  [ -e "$a/dgpu_disable" ] && log "dgpu-report: asus-nb-wmi$(kv "$a/dgpu_disable" dgpu_disable)$(kv "$a/gpu_mux_mode" gpu_mux_mode)"
  s=$SYS/power/suspend_stats
  [ -d "$s" ] && log "dgpu-report: suspend_stats$(kv "$s/success" success)$(kv "$s/fail" fail)$(kv "$s/last_hw_sleep" last_hw_sleep_us)$(kv "$s/total_hw_sleep" total_hw_sleep_us)$(kv "$s/max_hw_sleep" max_hw_sleep_us)"
  if [ -z "$funcs" ]; then state=absent
  elif [ $any_d0 = 1 ]; then if [ -n "$gpu_drv" ]; then state=d0-driver; else state=d0-no-driver; fi
  elif [ $all_d3cold = 1 ] || [ "$bps" = D3cold ]; then state=d3cold
  elif [ $unknown = 1 ]; then state=unknown
  else state=d3hot; fi
  log "dgpu-report: state=$state"
  return 0
}

dgpu_ctl() {
  case ${1:-} in
    on|auto) ;;
    *) log "dgpu-ctl: '${1:-}' is neither on nor auto; nothing changed"; return 2 ;;
  esac
  rc=0
  if [ "$1" = auto ]; then
    dgpu_pm || rc=1
  else
    n=0
    for p in "$SYS"/bus/pci/devices/*; do
      [ "$(rd "$p/vendor")" = 0x10de ] || continue
      case $(rd "$p/class") in
        0x03*) drv=$(driver_of "$p")
               if [ -n "$drv" ]; then log "dgpu-ctl: ${p##*/} is driven by $drv; leaving its power to the driver"; return 0; fi ;;
      esac
      n=$((n + 1))
    done
    [ $n = 0 ] && log "dgpu-ctl: no NVIDIA function enumerated; nothing to do"
    for p in "$SYS"/bus/pci/devices/*; do
      [ "$(rd "$p/vendor")" = 0x10de ] && { wr "$p/power/control" on || rc=1; }
    done
  fi
  sleep "${OPENBOOK_SETTLE_S:-5}"   # let runtime PM settle before reporting
  dgpu_report "dgpu-ctl $1"
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

kvm() {
  if [ -e "$SYS/devices/virtual/misc/kvm/dev" ]; then
    v=1; log "KVM is available ($(rd "$SYS/devices/virtual/misc/kvm/dev")): AVF can run the Linux environment"
  else
    v=0; log "no KVM device (is SVM off in the firmware?): no Linux environment"
  fi
  ${OPENBOOK_SETPROP:-setprop} vendor.openbook.kvm $v
}

case ${1:-} in
  dgpu-pm) dgpu_pm ;;
  dgpu-report) shift; dgpu_report "$*" ;;
  dgpu-ctl) dgpu_ctl "${2:-}" ;;
  perms) perms ;;
  kvm) kvm ;;
  *) echo "usage: openbook-pc-setup dgpu-pm|dgpu-report [REASON]|dgpu-ctl on|auto|perms|kvm" >&2; exit 2 ;;
esac
