#!/vendor/bin/sh
# SPDX-License-Identifier: Apache-2.0
# OpenBook PC boot-time sysfs setup, run by init as root (init.openbook.rc). Android mksh + toybox; also runs under
# bash/dash for the fixture test (scripts/openbook-pc-setup-test.sh).
#
# usage: openbook-pc-setup dgpu-pm | dgpu-report [REASON] | dgpu-ctl on|auto | lab ACTION[@N] | perms | kvm
#   dgpu-pm  Let an NVIDIA dGPU (10de) reach D3cold (docs/nvidia.md). snd_hda_intel holds the dGPU's HDMI-audio
#            function awake: without vga_switcheroo (off in the GKI) it never runtime-suspends, and with it awake
#            the root port cannot cut the slot's power, whether or not a driver drives the GPU. So:
#              - unbind snd_hda_intel from the dGPU's HDMI-audio function (that HDMI port is on the dGPU and dark);
#              - set power/control=auto on the dGPU's other functions, and on its display function when no driver
#                drives it (the PCI core keeps an unbound device in D0 until the root port powers the slot off);
#              - give snd_hda_intel a non-zero power_save (10 s, as desktop Linux does).
#            When a driver drives the display function (nouveau, ANAL-239) its runtime PM is the driver's: nouveau
#            allows it itself with nouveau.runpm=1 (modules.options); its state is logged, nothing is written.
#            Volatile: a reboot undoes it. Never touches asus-wmi (dgpu_disable, gpu_mux_mode), which persist in
#            firmware. Does nothing without an NVIDIA function.
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
#   lab ACTION[@N]
#            The G14 lab helper (ANAL-257, docs/googlebook-s0i3.md), from debug.openbook.lab: allow-listed
#            experiments for a user build's adb shell, which cannot load modules, write /sys or read the kernel log.
#            Everything but enable/disable is refused until "enable" sets persist.vendor.openbook.lab=1, which only
#            this root helper can set and which stays on across reboots until "disable". An @N suffix only makes a
#            repeated request a new property value. Every result goes to logcat (logcat -s openbook-pc-setup).
#              enable | disable     the switch
#              report               dgpu-report, the lab modules' state, openbook_sleep_diag's last S0i3 report
#              nouveau-load | nouveau-unload | diag-snapshot | diag-ptm-off | diag-unload
#                                   ask init (vendor.openbook.lab.mod) to run its fixed modprobe command for the
#                                   action in the module loader's own domain, wait for the module, then report
#              sleep-20 | sleep-60 | sleep-300
#                                   one suspend now, woken by the RTC after that many seconds, then report
#   perms    Hand amd-pstate's energy_performance_preference to the power HAL (user system). cpufreq policies send
#            no uevents, so ueventd.rc cannot do it.
#   kvm      Set vendor.openbook.kvm to 1 if KVM registered its device, else 0 (ANAL-218). KVM_AMD is built in, so
#            that happens exactly when the firmware has SVM on. init.openbook.rc turns 1 into the
#            ro.boot.hypervisor.* properties AVF reads, so the Linux environment is offered only where it can run.
#            It reads sysfs: only crosvm and ueventd may even stat /dev/kvm.
# Testing: OPENBOOK_SYSFS_ROOT=<dir> works on <dir>/sys instead of /sys; OPENBOOK_LOGCMD=<path> replaces
# /vendor/bin/log (empty: no logd copy); OPENBOOK_GETPROP/OPENBOOK_SETPROP replace getprop/setprop;
# OPENBOOK_LAB_WAIT_S bounds the wait for a module (default 30).
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
  gpus=; others=
  for d in "$SYS"/bus/pci/devices/*; do
    [ "$(rd "$d/vendor")" = 0x10de ] || continue
    case $(rd "$d/class") in
      0x03*) gpus="$gpus ${d##*/}" ;;
      *) others="$others ${d##*/}" ;;
    esac
  done
  nouveau_facts
  if [ -z "$gpus" ]; then
    log "no NVIDIA GPU enumerated; nothing to do"
    return 0
  fi
  # The display functions: a bound driver owns its runtime PM; an unbound one only needs auto.
  free=
  for g in $gpus; do
    drv=$(driver_of "$SYS/bus/pci/devices/$g")
    if [ -n "$drv" ]; then
      log "$g is driven by $drv; leaving its runtime PM to the driver"
    else
      free="$free $g"
    fi
  done
  # HDMI audio and any other function: off snd_hda_intel and auto in every case (ANAL-239: with nouveau bound too).
  hda=0
  for f in $others; do
    case $(rd "$SYS/bus/pci/devices/$f/class") in 0x0403*) hda=1 ;; esac
    if [ "$(driver_of "$SYS/bus/pci/devices/$f")" = snd_hda_intel ]; then
      wr "$SYS/bus/pci/drivers/snd_hda_intel/unbind" "$f" || rc=1
    fi
  done
  for f in $free $others; do
    wr "$SYS/bus/pci/devices/$f/power/control" auto || rc=1
  done
  if [ $hda = 1 ] && [ -e "$SYS/module/snd_hda_intel/parameters/power_save" ] &&
     [ "$(rd "$SYS/module/snd_hda_intel/parameters/power_save")" = 0 ]; then
    wr "$SYS/module/snd_hda_intel/parameters/power_save" $POWER_SAVE || rc=1
  fi
  for f in $gpus; do
    p=$SYS/bus/pci/devices/$f
    log "$f: driver=$(driver_of "$p" || echo -) power_state=$(rd "$p/power_state") runtime_status=$(rd "$p/power/runtime_status") control=$(rd "$p/power/control")"
  done
  return $rc
}

# nouveau_facts: the module parameters that decide nouveau's runtime PM and display, when it is loaded (ANAL-239).
# runpm must be 1: nouveau's own Optimus detection needs vga_switcheroo, which the GKI lacks, so its default (-1)
# leaves runtime PM off and the dGPU in D0.
nouveau_facts() {
  n=$SYS/module/nouveau/parameters
  [ -d "$n" ] || return 0
  bound=
  for d in "$SYS"/bus/pci/drivers/nouveau/????:??:??.?; do [ -e "$d" ] && bound="$bound,${d##*/}"; done
  cfg=$(rd "$n/config"); [ "$cfg" = "(null)" ] && cfg=   # an unset string parameter reads "(null)"
  log "nouveau:$(kv "$n/runpm" runpm)$(kv "$n/modeset" modeset)${cfg:+ config=$cfg} bound=${bound#,}"
  [ "$(rd "$n/runpm")" = 1 ] || log "nouveau: runpm is not 1, so a bound dGPU stays in D0 (modules.options)"
  return 0
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
  nouveau_facts
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

LAB_SWITCH=persist.vendor.openbook.lab
LAB_ACTIONS="enable disable report nouveau-load nouveau-unload diag-snapshot diag-ptm-off diag-unload sleep-20 sleep-60 sleep-300"
getp() { ${OPENBOOK_GETPROP:-getprop} "$@"; }
setp() { ${OPENBOOK_SETPROP:-setprop} "$@"; }

# lab_modules: the lab modules' state from sysfs, and openbook_sleep_diag's report of the last S0i3 attempt.
lab_modules() {
  for m in nouveau drm_gpuvm openbook_sleep_diag; do
    if [ -d "$SYS/module/$m" ]; then
      log "lab: module $m loaded$(kv "$SYS/module/$m/initstate" state)$(kv "$SYS/module/$m/refcnt" refcnt)"
    else
      log "lab: module $m not loaded"
    fi
  done
  p=$SYS/module/openbook_sleep_diag/parameters
  [ -d "$p" ] || return 0
  log "lab: openbook_sleep_diag$(kv "$p/ptm_off" ptm_off)$(kv "$p/snapshot" snapshot)$(kv "$p/usb4" usb4)$(kv "$p/cycles" cycles)"
  [ -r "$p/report" ] || return 0
  while IFS= read -r line; do log "lab: diag $line"; done < "$p/report"
  return 0
}

lab_report() {
  log "lab-report (${1:-manual}): switch=$(getp $LAB_SWITCH)"
  dgpu_report "lab ${1:-report}"
  lab_modules
}

# lab_wait NAME present|absent: until /sys/module/NAME appears or goes, at most OPENBOOK_LAB_WAIT_S seconds.
lab_wait() {
  i=0
  while :; do
    if [ -d "$SYS/module/$1" ]; then [ "$2" = present ] && return 0; else [ "$2" = absent ] && return 0; fi
    [ $i -ge "${OPENBOOK_LAB_WAIT_S:-30}" ] && return 1
    sleep 1; i=$((i + 1))
  done
}

# lab_sleep SECONDS: one suspend now, woken by the RTC. Writing "mem" to /sys/power/state blocks until the resume;
# a pending wakeup source makes the kernel refuse it, as it does for Android's own suspends.
lab_sleep() {
  w=$SYS/class/rtc/rtc0/wakealarm; s=$SYS/power/suspend_stats
  [ -e "$w" ] || { log "lab: no RTC wakealarm ($w): no sleep"; return 1; }
  wr "$w" 0 || return 1
  wr "$w" "+$1" || return 1
  log "lab: suspending for $1 s$(kv "$s/success" success_before)$(kv "$s/fail" fail_before)"
  if printf 'mem\n' > "$SYS/power/state" 2>/dev/null; then
    log "lab: resumed"
  else
    log "lab: the suspend was refused or aborted (a wakeup source was active)"
  fi
  printf '0\n' > "$w" 2>/dev/null
  log "lab: suspend_stats$(kv "$s/success" success)$(kv "$s/fail" fail)$(kv "$s/last_hw_sleep" last_hw_sleep_us)$(kv "$s/total_hw_sleep" total_hw_sleep_us)"
  return 0
}

lab() {
  req=${1:-}; act=${req%%@*}
  case " $LAB_ACTIONS " in
    *" $act "*) ;;
    *) log "lab: '$req' is not an allowed action ($LAB_ACTIONS)"; return 2 ;;
  esac
  case $act in
    enable) setp $LAB_SWITCH 1 && log "lab: switched on ($LAB_SWITCH=1, kept across reboots); 'disable' switches it off"; return 0 ;;
    disable) setp $LAB_SWITCH 0 && log "lab: switched off ($LAB_SWITCH=0)"; return 0 ;;
  esac
  if [ "$(getp $LAB_SWITCH)" != 1 ]; then
    log "lab: '$req' refused: the lab switch is off (setprop debug.openbook.lab enable)"
    return 3
  fi
  rc=0
  case $act in
    report) lab_report "$req" ;;
    nouveau-*|diag-*)
      case $act in nouveau-*) m=nouveau ;; *) m=openbook_sleep_diag ;; esac
      case $act in *-unload) want=absent ;; *) want=present ;; esac
      if [ $want = present ] && [ -d "$SYS/module/$m" ]; then
        log "lab: $act refused: $m is already loaded (unload it first)"; lab_report "$req"; return 4
      fi
      # init runs the fixed command for this value (init.openbook.rc); idle first, so a repeat is a change too.
      setp vendor.openbook.lab.mod idle; setp vendor.openbook.lab.mod "$act"
      if lab_wait $m $want; then log "lab: $act: $m $want"; else log "lab: $act: $m not $want after ${OPENBOOK_LAB_WAIT_S:-30} s"; rc=5; fi
      setp vendor.openbook.lab.mod idle
      sleep "${OPENBOOK_SETTLE_S:-5}"
      lab_report "$req" ;;
    sleep-*) lab_sleep "${act#sleep-}" || rc=1; lab_report "$req" ;;
  esac
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
  lab) lab "${2:-}" ;;
  perms) perms ;;
  kvm) kvm ;;
  *) echo "usage: openbook-pc-setup dgpu-pm|dgpu-report [REASON]|dgpu-ctl on|auto|lab ACTION[@N]|perms|kvm" >&2; exit 2 ;;
esac
