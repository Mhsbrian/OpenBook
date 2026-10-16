#!/usr/bin/env bash
# Read-only hardware inventory for an AnyBook target laptop (run it ON the laptop, under any Linux).
# Changes nothing on the machine. Serial numbers, UUIDs and MAC addresses are redacted.
#
# usage: hw-inventory.sh [--with-root]
#   --with-root  also collect dmesg, dmidecode and the ACPI tables through sudo (prompts for your password);
#                the MSDM/SLIC tables, which hold the Windows product key, are skipped
# Output: ./anybook-hw-<board>-<date>.tar.gz   (attach it to the Multica issue)
set -uo pipefail
ROOT=0; [ "${1:-}" = "--with-root" ] && ROOT=1
dmi(){ cat "/sys/class/dmi/id/$1" 2>/dev/null || echo unknown; }
BOARD=$(dmi board_name | tr -c 'A-Za-z0-9._\n-' '_' | head -c 40)
OUT=anybook-hw-${BOARD}-$(date +%Y%m%d-%H%M%S); mkdir -p "$OUT"
redact(){ sed -E -e 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/XX:XX:XX:XX:XX:XX/g' \
  -e 's/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/<uuid>/g' \
  -e 's/((Serial|serial|SERIAL)[ _-]?([Nn]umber|NUMBER|No)?[[:space:]]*[:=][[:space:]]*).*/\1<redacted>/'; }
run(){ local f=$1; shift; { echo "\$ $*"; "$@" 2>&1; } | redact > "$OUT/$f.txt" || true; }
have(){ command -v "$1" >/dev/null 2>&1; }

# Identity (serials, UUIDs and asset tags are skipped on purpose)
for k in sys_vendor product_name product_family product_version board_vendor board_name board_version bios_vendor bios_version bios_date; do
  printf '%s=%s\n' "$k" "$(dmi $k)"; done > "$OUT/dmi.txt"
run uname uname -a
run os-release cat /etc/os-release
run cmdline cat /proc/cmdline
run cpuinfo cat /proc/cpuinfo
for fl in avx_vnni avx512f avx512_vnni avx512_bf16 gfni vaes sha_ni; do
  grep -m1 -qw "$fl" /proc/cpuinfo && echo "$fl yes" || echo "$fl no"; done > "$OUT/cpu-isa-summary.txt"
run meminfo cat /proc/meminfo

# Buses and drivers
have lspci && { run lspci-nnk lspci -nnk; run lspci-tree lspci -tv; run lspci-vvv lspci -vvv; }
have lsusb && { run lsusb lsusb; run lsusb-tree lsusb -t; }
run lsmod lsmod
run input-devices cat /proc/bus/input/devices
{ for d in /sys/bus/i2c/devices/*; do printf '%s name=%s modalias=%s driver=%s\n' "$(basename "$d")" "$(cat "$d/name" 2>/dev/null)" "$(cat "$d/modalias" 2>/dev/null)" "$(basename "$(readlink "$d/driver" 2>/dev/null)" 2>/dev/null)"; done; } > "$OUT/i2c-devices.txt" 2>&1
{ for d in /sys/bus/platform/devices/*; do printf '%s driver=%s\n' "$(basename "$d")" "$(basename "$(readlink "$d/driver" 2>/dev/null)" 2>/dev/null)"; done; } > "$OUT/platform-devices.txt" 2>&1
ls /sys/firmware/acpi/tables/ > "$OUT/acpi-table-names.txt" 2>&1
{ for d in /sys/bus/acpi/devices/*; do printf '%s hid=%s status=%s\n' "$(basename "$d")" "$(cat "$d/hid" 2>/dev/null)" "$(cat "$d/status" 2>/dev/null)"; done; } > "$OUT/acpi-devices.txt" 2>&1

# Display and GPUs
{ for c in /sys/class/drm/card*-*; do echo "== $(basename "$c") status=$(cat "$c/status" 2>/dev/null) enabled=$(cat "$c/enabled" 2>/dev/null)"; cat "$c/modes" 2>/dev/null | head -5; done; } > "$OUT/drm-connectors.txt" 2>&1
for c in /sys/class/drm/card*-eDP-*; do [ -s "$c/edid" ] && { cp "$c/edid" "$OUT/edid-$(basename "$c").bin"; have edid-decode && edid-decode "$c/edid" > "$OUT/edid-$(basename "$c").txt" 2>&1; }; done
have vulkaninfo && run vulkaninfo vulkaninfo --summary
have glxinfo && run glxinfo glxinfo -B
have nvidia-smi && run nvidia-smi nvidia-smi --query-gpu=name,driver_version,pci.bus_id,pstate,power.draw,vbios_version --format=csv
{ for g in /sys/bus/pci/devices/*; do [ "$(cat "$g/class" 2>/dev/null | cut -c1-4)" = "0x03" ] && echo "$(basename "$g") vendor=$(cat "$g/vendor") device=$(cat "$g/device") power=$(cat "$g/power_state" 2>/dev/null) runtime=$(cat "$g/power/runtime_status" 2>/dev/null)"; done; } > "$OUT/gpus.txt" 2>&1

# ASUS platform controls (asus-armoury / asus-wmi)
{ for a in /sys/class/firmware-attributes/asus-armoury/attributes/*; do echo "$(basename "$a")=$(cat "$a/current_value" 2>/dev/null)"; done
  for f in /sys/devices/platform/asus-nb-wmi/{dgpu_disable,gpu_mux_mode,egpu_enable,panel_od,throttle_thermal_policy}; do [ -e "$f" ] && echo "$(basename "$f")=$(cat "$f" 2>/dev/null)"; done; } > "$OUT/asus-platform.txt" 2>&1

# Audio, network, power
run asound-cards cat /proc/asound/cards
for c in /proc/asound/card*/codec#*; do [ -r "$c" ] && cp "$c" "$OUT/$(echo "$c" | tr '/#' '__').txt"; done
have aplay && { run aplay-l aplay -l; run arecord-l arecord -l; }
have ip && run ip-link ip -br link
have rfkill && run rfkill rfkill list
have iw && run iw-dev iw dev
{ for p in /sys/class/power_supply/*; do echo "== $(basename "$p")"; grep -vE 'SERIAL' "$p/uevent" 2>/dev/null; done; } > "$OUT/power-supply.txt" 2>&1
run suspend-modes cat /sys/power/mem_sleep
have fwupdmgr && run fwupd fwupdmgr get-devices --no-unreported-check
have bootctl && run bootctl bootctl status --no-pager
have mokutil && run secureboot mokutil --sb-state
run tpm ls -l /dev/tpm0 /dev/tpmrm0

if [ $ROOT = 1 ]; then
  sudo dmesg 2>&1 | redact > "$OUT/dmesg.txt"
  have dmidecode && sudo dmidecode 2>&1 | grep -viE 'serial|uuid|asset tag' > "$OUT/dmidecode.txt"
  # Raw ACPI tables, minus MSDM and SLIC: those carry the OEM Windows product key / licence.
  mkdir -p "$OUT/acpi"
  for t in /sys/firmware/acpi/tables/* /sys/firmware/acpi/tables/dynamic/*; do
    [ -f "$t" ] || continue
    case "$(basename "$t")" in MSDM*|SLIC*) continue ;; esac
    sudo cat "$t" > "$OUT/acpi/$(basename "$t").dat" 2>/dev/null
  done
else
  dmesg 2>/dev/null | redact > "$OUT/dmesg.txt" || echo "dmesg needs root; rerun with --with-root" > "$OUT/dmesg.txt"
fi

tar -czf "$OUT.tar.gz" "$OUT" && rm -rf "$OUT"
echo "wrote $OUT.tar.gz  (board: $BOARD; check cpu-isa-summary.txt for avx_vnni)"
