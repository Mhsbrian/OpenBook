#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Is the NVIDIA dGPU powered down? Runs on the laptop under Linux (bash/dash) or OpenBook (Android mksh + toybox).
# Reads sysfs only. It never runs lspci or reads PCI config space, because that would wake a suspended dGPU.
# It never writes asus-wmi/asus-armoury attributes (dgpu_disable, gpu_mux_mode): those persist in firmware.
#
# usage: dgpu-power-check.sh [--sample SECONDS] [--try auto|remove] [--bridge BDF] [--out FILE]
#   --sample S    average the battery discharge power over S seconds (5 s steps) for each state; run on battery
#   --try MODE    root only, volatile (undone by a reboot): try to put a present dGPU into D3cold, then re-check
#                   auto    unbind snd_hda_intel from the dGPU's HDMI-audio function, set power/control=auto
#                   remove  detach every NVIDIA function from the PCI bus (the Arch wiki udev-rule method)
#   --bridge BDF  root port above the dGPU, when the dGPU is absent (default: from a per-board table)
#   --out FILE    also write the JSON result to FILE
# Output: one JSON object on stdout (schema openbook.dgpu-power-check/1); a summary on stderr.
# Exit: 0 PASS (dGPU off: absent with its slot unpowered, or in D3cold), 1 FAIL (powered), 2 WARN/unknown, 3 usage.
# Testing: DGPU_CHECK_ROOT=<dir> reads <dir>/sys and <dir>/etc instead of the live system.
set -u
R=${DGPU_CHECK_ROOT:-}
SYS=$R/sys
SAMPLE=0; TRY=none; BRIDGE_ARG=; OUT=
while [ $# -gt 0 ]; do
  case $1 in
    --sample) SAMPLE=${2:-}; shift 2 ;;
    --try) TRY=${2:-}; shift 2 ;;
    --bridge) BRIDGE_ARG=${2:-}; shift 2 ;;
    --out) OUT=${2:-}; shift 2 ;;
    -h|--help) sed -n '3,17p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 3 ;;
  esac
done
case $SAMPLE in ''|*[!0-9]*) echo "--sample needs whole seconds" >&2; exit 3 ;; esac
case $TRY in none|auto|remove) ;; *) echo "--try must be auto or remove" >&2; exit 3 ;; esac

rd() { [ -r "$1" ] && head -n 1 "$1" 2>/dev/null | tr -d '\n\r' ; }
je() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr -d '\n\r\t' ; }
js() { printf '"%s"' "$(je "$1")" ; }
log() { echo "dgpu-power-check: $*" >&2 ; }

# Root port above the dGPU when the dGPU is not enumerated. Board names come from DMI.
board_bridge() {
  case $1 in
    GA403WR|GA403WP|GA403WW|GA403WM) echo 0000:00:03.1 ;;   # G14 2025: GPP bridge 00:03.1 (evidence/2026-10-16-ga403wr-inventory)
  esac
}

nv_funcs() {
  for d in "$SYS"/bus/pci/devices/*; do
    [ "$(rd "$d/vendor")" = 0x10de ] && basename "$d"
  done
}

parent_bdf() {
  p=$(readlink -f "$SYS/bus/pci/devices/$1" 2>/dev/null) || return 0
  basename "$(dirname "$p")" | grep -E '^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$'
}

child_count() {
  p=$(readlink -f "$SYS/bus/pci/devices/$1" 2>/dev/null) || { echo 0; return; }
  n=0
  for c in "$p"/????:??:??.?; do [ -e "$c" ] && n=$((n + 1)); done
  echo $n
}

# Power resources of an ACPI node: JSON array of {stage, name, in_use}.
acpi_res_json() {
  first=1; printf '['
  for st in D0 D1 D2 D3hot; do
    for r in "$1/power_resources_$st"/*; do
      [ -e "$r" ] || continue
      [ $first = 1 ] || printf ','; first=0
      printf '{"stage":"%s","name":%s,"in_use":%s}' "$st" "$(js "$(basename "$r")")" "$(js "$(rd "$r/resource_in_use")")"
    done
  done
  printf ']'
}

acpi_node_json() {
  printf '{"path":%s,"power_state":%s,"real_power_state":%s,"power_resources":%s}' \
    "$(js "$(rd "$1/path")")" "$(js "$(rd "$1/power_state")")" "$(js "$(rd "$1/real_power_state")")" "$(acpi_res_json "$1")"
}

# Sum of resource_in_use over the bridge's ACPI node and its children: "none" if there are no power resources.
res_in_use() {
  n=0; on=0
  for node in "$1" "$1"/device:* "$1"/LNXVIDEO:*; do
    for r in "$node"/power_resources_*/*; do
      [ -e "$r" ] || continue
      n=$((n + 1)); [ "$(rd "$r/resource_in_use")" = 1 ] && on=$((on + 1))
    done
  done
  [ $n = 0 ] && echo none || echo "$on/$n"
}

battery_mw() {
  for b in "$SYS"/class/power_supply/*; do
    [ "$(rd "$b/type")" = Battery ] || continue
    p=$(rd "$b/power_now")
    if [ -n "$p" ] && [ "$p" != 0 ]; then echo $((p / 1000)); return; fi
    i=$(rd "$b/current_now"); v=$(rd "$b/voltage_now")
    # mA * mV / 1000 = mW; stays inside mksh's 32-bit arithmetic
    [ -n "$i" ] && [ -n "$v" ] && { i=${i#-}; echo $(( (i / 1000) * (v / 1000) / 1000 )); }
    return
  done
}

on_ac() {
  for a in "$SYS"/class/power_supply/*; do
    [ "$(rd "$a/type")" = Mains ] && [ "$(rd "$a/online")" = 1 ] && { echo true; return; }
  done
  echo false
}

battery_json() {
  if [ "$SAMPLE" -eq 0 ]; then
    printf '{"on_ac":%s,"now_mw":%s}' "$(on_ac)" "$(js "$(battery_mw)")"; return
  fi
  n=0; sum=0; min=; max=; t=0
  while [ $t -lt "$SAMPLE" ]; do
    m=$(battery_mw); [ -n "$m" ] || break
    n=$((n + 1)); sum=$((sum + m))
    { [ -z "$min" ] || [ "$m" -lt "$min" ]; } && min=$m
    { [ -z "$max" ] || [ "$m" -gt "$max" ]; } && max=$m
    sleep 5; t=$((t + 5))
  done
  [ $n -gt 0 ] && avg=$((sum / n)) || avg=
  printf '{"on_ac":%s,"interval_s":5,"samples":%d,"avg_mw":%s,"min_mw":%s,"max_mw":%s}' \
    "$(on_ac)" "$n" "$(js "$avg")" "$(js "$min")" "$(js "$max")"
}

# One state snapshot as JSON; also sets STATE and REASON for the verdict.
snapshot() {
  label=$1
  funcs=$(nv_funcs)
  bridge=; bsrc=none
  for f in $funcs; do bridge=$(parent_bdf "$f"); [ -n "$bridge" ] && { bsrc=parent; break; }; done
  [ -z "$bridge" ] && [ -n "$BRIDGE_ARG" ] && { bridge=$BRIDGE_ARG; bsrc=argument; }
  [ -z "$bridge" ] && { bridge=$(board_bridge "$BOARD"); [ -n "$bridge" ] && bsrc=board-table; }

  printf '{"label":%s,"nvidia_functions":[' "$(js "$label")"
  first=1; any_d0=0; any_unknown=0; all_d3cold=1; vga_driver=
  for f in $funcs; do
    d=$SYS/bus/pci/devices/$f
    drv=; [ -e "$d/driver" ] && drv=$(basename "$(readlink "$d/driver")")
    ps=$(rd "$d/power_state"); cls=$(rd "$d/class")
    case $ps in D0) any_d0=1; all_d3cold=0 ;; D3cold) ;; D3hot|D1|D2) all_d3cold=0 ;; *) any_unknown=1; all_d3cold=0 ;; esac
    case $cls in 0x03*) vga_driver=$drv ;; esac
    [ $first = 1 ] || printf ','; first=0
    printf '{"bdf":%s,"device":%s,"class":%s,"driver":%s,"power_state":%s,"runtime_status":%s,"control":%s,"d3cold_allowed":%s}' \
      "$(js "$f")" "$(js "$(rd "$d/device")")" "$(js "$cls")" "$(js "$drv")" "$(js "$ps")" \
      "$(js "$(rd "$d/power/runtime_status")")" "$(js "$(rd "$d/power/control")")" "$(js "$(rd "$d/d3cold_allowed")")"
  done
  printf ']'

  bps=; brt=; res=none
  if [ -n "$bridge" ] && [ -e "$SYS/bus/pci/devices/$bridge" ]; then
    b=$SYS/bus/pci/devices/$bridge
    bps=$(rd "$b/power_state"); brt=$(rd "$b/power/runtime_status")
    # Hotplug slots are listed by secondary-bus address, which sysfs does not tie to the bridge; report them all.
    slots=$(for s in "$SYS"/bus/pci/slots/*; do [ -e "$s/address" ] && printf '%s=%s ' "$(basename "$s")" "$(rd "$s/address")"; done)
    printf ',"bridge":{"bdf":%s,"source":%s,"power_state":%s,"runtime_status":%s,"control":%s,"d3cold_allowed":%s,"pci_children":%s,"hotplug_slots":%s' \
      "$(js "$bridge")" "$(js "$bsrc")" "$(js "$bps")" "$(js "$brt")" "$(js "$(rd "$b/power/control")")" \
      "$(js "$(rd "$b/d3cold_allowed")")" "$(child_count "$bridge")" "$(js "$slots")"
    fn=$b/firmware_node
    if [ -e "$fn" ]; then
      res=$(res_in_use "$fn")
      printf ',"acpi":%s,"acpi_children":[' "$(acpi_node_json "$fn")"
      first=1
      for c in "$fn"/device:* "$fn"/LNXVIDEO:*; do
        [ -e "$c/path" ] || continue
        [ $first = 1 ] || printf ','; first=0
        acpi_node_json "$c"
      done
      printf ']'
    fi
    printf ',"power_resources_in_use":%s}' "$(js "$res")"
  else
    printf ',"bridge":null'
  fi
  printf ',"battery":%s' "$(battery_json)"

  # Verdict for this snapshot
  if [ -n "$funcs" ]; then
    if [ $any_d0 = 1 ]; then
      if [ -n "$vga_driver" ]; then STATE=d0-driver; REASON="dGPU in D0 with $vga_driver bound (the driver owns its power)"
      else STATE=d0-no-driver; REASON="dGPU powered in D0 with no driver: nothing will power it down"; fi
    elif [ $all_d3cold = 1 ] || [ "$bps" = D3cold ]; then STATE=d3cold; REASON="dGPU enumerated but in D3cold"
    elif [ $any_unknown = 1 ]; then STATE=unknown; REASON="dGPU power_state not readable"
    else STATE=d3hot; REASON="dGPU in D3hot: link idle, board power still on"; fi
  else
    case $res in
      none) if [ "$ASUS_DGPU_DISABLE" = 1 ]; then STATE=absent-off; REASON="not enumerated; firmware dgpu_disable=1"
            elif [ "$bps" = D3cold ]; then STATE=absent-off; REASON="not enumerated; root port in D3cold"
            else STATE=absent-unknown; REASON="not enumerated; no ACPI power resources visible to confirm the slot is off"; fi ;;
      0/*) STATE=absent-off; REASON="not enumerated; slot power resources off ($res in use)" ;;
      *) if [ "$ASUS_DGPU_DISABLE" = 1 ]; then STATE=absent-off; REASON="not enumerated; firmware dgpu_disable=1 (power resources $res in use)"
         else STATE=absent-powered; REASON="not enumerated but slot power resources on ($res in use): removed by the OS, not powered off"; fi ;;
    esac
  fi
  printf ',"dgpu_state":%s,"reason":%s}' "$(js "$STATE")" "$(js "$REASON")"
}

try_power_down() {
  for f in $(nv_funcs | sort -r); do   # functions 1..n before function 0
    d=$SYS/bus/pci/devices/$f
    if [ "$TRY" = remove ]; then
      log "remove $f"; echo 1 > "$d/remove" 2>/dev/null || log "remove $f failed"
      continue
    fi
    if [ -e "$d/driver" ] && [ "$(basename "$(readlink "$d/driver")")" = snd_hda_intel ]; then
      log "unbind snd_hda_intel from $f"; echo "$f" > "$d/driver/unbind" 2>/dev/null || log "unbind $f failed"
    fi
    log "power/control=auto on $f"; echo auto > "$d/power/control" 2>/dev/null || log "control $f failed"
  done
}

# ---- main
OS=linux; [ -e "${R:-}/system/build.prop" ] && OS=android
BOARD=$(rd "$SYS/class/dmi/id/board_name"); BIOS=$(rd "$SYS/class/dmi/id/bios_version")
KREL=; [ -z "$R" ] && KREL=$(uname -r)

ASUS_SRC=; ASUS_DGPU_DISABLE=; ASUS_MUX=; ASUS_EGPU=
p=$SYS/devices/platform/asus-nb-wmi
if [ -e "$p/dgpu_disable" ]; then
  ASUS_SRC=asus-nb-wmi; ASUS_DGPU_DISABLE=$(rd "$p/dgpu_disable"); ASUS_MUX=$(rd "$p/gpu_mux_mode"); ASUS_EGPU=$(rd "$p/egpu_enable")
fi
A=$SYS/class/firmware-attributes/asus-armoury/attributes
if [ -z "$ASUS_SRC" ] && [ -e "$A/dgpu_disable/current_value" ]; then
  ASUS_SRC=asus-armoury; ASUS_DGPU_DISABLE=$(rd "$A/dgpu_disable/current_value"); ASUS_MUX=$(rd "$A/gpu_mux_mode/current_value"); ASUS_EGPU=$(rd "$A/egpu_enable/current_value")
fi

SG_MODE=; SG_CONF_MODE=; SG_HOTPLUG=
[ -z "$R" ] && command -v supergfxctl >/dev/null 2>&1 && SG_MODE=$(timeout 3 supergfxctl -g 2>/dev/null)
if [ -r "$R/etc/supergfxd.conf" ]; then
  SG_CONF_MODE=$(sed -n 's/.*"mode"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$R/etc/supergfxd.conf" | head -n 1)
  SG_HOTPLUG=$(sed -n 's/.*"hotplug_type"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$R/etc/supergfxd.conf" | head -n 1)
fi

mods=
for m in nvidia nouveau nova_core nova_drm snd_hda_intel vfio_pci; do [ -e "$SYS/module/$m" ] && mods="$mods$m "; done

if [ "$TRY" != none ] && [ -z "$R" ] && [ "$(id -u)" != 0 ]; then echo "--try needs root" >&2; exit 3; fi

TMP=${TMPDIR:-/data/local/tmp}; [ -d "$TMP" ] || TMP=/tmp
J=$TMP/dgpu-power-check.$$.json
# A redirected brace group runs in this shell, so STATE, REASON, V and RC stay set after it.
{
  printf '{"schema":"openbook.dgpu-power-check/1","time":%s,"os":%s,"kernel":%s,"board":%s,"bios":%s' \
    "$(js "$(date -u +%Y-%m-%dT%H:%M:%SZ)")" "$(js "$OS")" "$(js "$KREL")" "$(js "$BOARD")" "$(js "$BIOS")"
  printf ',"asus":{"source":%s,"dgpu_disable":%s,"gpu_mux_mode":%s,"egpu_enable":%s}' \
    "$(js "$ASUS_SRC")" "$(js "$ASUS_DGPU_DISABLE")" "$(js "$ASUS_MUX")" "$(js "$ASUS_EGPU")"
  printf ',"supergfx":{"mode":%s,"conf_mode":%s,"hotplug_type":%s}' "$(js "$SG_MODE")" "$(js "$SG_CONF_MODE")" "$(js "$SG_HOTPLUG")"
  printf ',"modules_loaded":%s,"try":%s,"states":[' "$(js "${mods% }")" "$(js "$TRY")"
  snapshot initial
  S0=$STATE
  if [ "$TRY" != none ] && [ -n "$(nv_funcs)" ]; then
    try_power_down >&2
    sleep 15
    printf ','; snapshot "after-$TRY"
  fi
  case $STATE in absent-off|d3cold) V=PASS; RC=0 ;; d0-no-driver|absent-powered) V=FAIL; RC=1 ;; *) V=WARN; RC=2 ;; esac
  printf '],"initial_state":%s,"dgpu_state":%s,"reason":%s,"verdict":%s}\n' "$(js "$S0")" "$(js "$STATE")" "$(js "$REASON")" "$(js "$V")"
} > "$J"
cat "$J"
[ -n "$OUT" ] && cp "$J" "$OUT"
rm -f "$J"
log "$V: $STATE ($REASON)"
exit "$RC"
