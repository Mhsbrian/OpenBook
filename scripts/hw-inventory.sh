#!/usr/bin/env bash
# Hardware inventory for an AnyBook target laptop (run it ON the laptop, under any Linux, as your normal user).
# By default it installs the read-only tools it uses, then collects everything, including dmesg, dmidecode
# and the ACPI tables through sudo (it asks for your password). Apart from installing those packages it
# changes nothing on the machine. Serial numbers, UUIDs and MAC addresses are redacted, and the MSDM/SLIC
# ACPI tables, which hold the Windows product key, are skipped.
#
# usage: hw-inventory.sh [--no-install] [--no-root]
#   --no-install  don't install packages; use the tools that are already there
#   --no-root     no sudo at all: skip dmesg, dmidecode, the ACPI tables and the package install
# Output: ./anybook-hw-<board>-<date>.tar.gz   (attach it to the Multica issue)
set -uo pipefail
ROOT=1; INSTALL=1
for a in "$@"; do case $a in
  --no-root) ROOT=0; INSTALL=0 ;; --no-install) INSTALL=0 ;; --with-root) ;;
  *) echo "usage: $0 [--no-install] [--no-root]" >&2; exit 2 ;; esac; done
SUDO=sudo; [ "$(id -u)" = 0 ] && SUDO=
dmi(){ cat "/sys/class/dmi/id/$1" 2>/dev/null || echo unknown; }
BOARD=$(dmi board_name | tr -c 'A-Za-z0-9._\n-' '_' | head -c 40)
OUT=anybook-hw-${BOARD}-$(date +%Y%m%d-%H%M%S); mkdir -p "$OUT"
redact(){ sed -E -e 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/XX:XX:XX:XX:XX:XX/g' \
  -e 's/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/<uuid>/g' \
  -e 's/((Serial|serial|SERIAL)[ _-]?([Nn]umber|NUMBER|No)?[[:space:]]*[:=][[:space:]]*).*/\1<redacted>/'; }
run(){ local f=$1; shift; { echo "\$ $*"; "$@" 2>&1; } | redact > "$OUT/$f.txt" || true; }
have(){ command -v "$1" >/dev/null 2>&1; }

if [ -n "$SUDO" ] && [ $((ROOT + INSTALL)) -gt 0 ]; then
  echo "sudo is used to install the inventory tools and to read dmesg, dmidecode and the ACPI tables."
  sudo -v || { echo "no sudo: continuing without installing tools or the root-only parts"; ROOT=0; INSTALL=0; }
fi

# Tools: pacman (Arch), apt-get (Debian/Ubuntu live USBs) or dnf (Fedora). A package that fails to
# install is skipped; the inventory still runs with whatever tools are there.
pkg_install(){ "$@" $PKGS && return; for p in $PKGS; do "$@" "$p" >/dev/null 2>&1 || echo "  could not install $p; skipping it"; done; return 1; }
if [ $INSTALL = 1 ]; then
  if have pacman; then
    PKGS="pciutils usbutils alsa-utils iw dmidecode vulkan-tools mesa-utils v4l-utils acpica fwupd"
    pkg_install $SUDO pacman -S --needed --noconfirm \
      || echo "  (if pacman could not find or download packages, its package lists are out of date: run 'sudo pacman -Syu', then rerun this script)"
  elif have apt-get; then
    PKGS="pciutils usbutils alsa-utils iw dmidecode vulkan-tools mesa-utils edid-decode acpica-tools fwupd"
    $SUDO apt-get update -qq; pkg_install $SUDO apt-get install -y -qq
  elif have dnf; then
    PKGS="pciutils usbutils alsa-utils iw dmidecode vulkan-tools glx-utils edid-decode acpica-tools fwupd"
    pkg_install $SUDO dnf install -y -q
  else echo "no pacman, apt-get or dnf: continuing with the tools already installed"; fi
fi

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
# Panel EDID. sysfs reports its size as 0, so copy it out before testing it. Only a redacted decode is kept:
# --replace-unique-ids swaps serial numbers and dates for fixed values, in the hex dump as well.
edid_id(){ local a b c d v; read -r a b c d < <(od -An -tu1 -j8 -N4 "$1"); v=$((a << 8 | b))
  printf 'manufacturer=%b%b%b product_code=0x%04x (install edid-decode, part of v4l-utils on Arch, for the full EDID)\n' \
    "\\0$(printf %o $(((v >> 10 & 31) + 64)))" "\\0$(printf %o $(((v >> 5 & 31) + 64)))" "\\0$(printf %o $(((v & 31) + 64)))" $((d << 8 | c)); }
for c in /sys/class/drm/card*-eDP-*; do
  e="$OUT/edid-$(basename "$c")"; cat "$c/edid" > "$e.raw" 2>/dev/null
  if [ -s "$e.raw" ]; then
    if have edid-decode && [[ $(edid-decode --help 2>&1) == *--replace-unique-ids* ]]; then
      edid-decode --replace-unique-ids "$e.raw" > "$e.txt" 2>&1
    else edid_id "$e.raw" > "$e.txt"; fi
  fi
  rm -f "$e.raw"
done
have vulkaninfo && run vulkaninfo vulkaninfo --summary
have glxinfo && run glxinfo glxinfo -B
{ for b in /sys/class/backlight/*; do [ -e "$b" ] && echo "$(basename "$b") type=$(cat "$b/type" 2>/dev/null) max=$(cat "$b/max_brightness" 2>/dev/null) actual=$(cat "$b/actual_brightness" 2>/dev/null) device=$(readlink -f "$b/device" 2>/dev/null)"; done; } > "$OUT/backlight.txt" 2>&1
have supergfxctl && { run supergfx-mode supergfxctl -g; run supergfx-power supergfxctl -S; }
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

[ $ROOT = 1 ] && [ -n "$SUDO" ] && { sudo -v || ROOT=0; }
if [ $ROOT = 1 ]; then
  $SUDO dmesg 2>&1 | redact > "$OUT/dmesg.txt"
  have dmidecode && $SUDO dmidecode 2>&1 | grep -viE 'serial|uuid|asset tag' > "$OUT/dmidecode.txt"
  # Raw ACPI tables, minus MSDM and SLIC: those carry the OEM Windows product key / licence.
  mkdir -p "$OUT/acpi"
  for t in /sys/firmware/acpi/tables/* /sys/firmware/acpi/tables/dynamic/*; do
    [ -f "$t" ] || continue
    case "$(basename "$t")" in MSDM*|SLIC*) continue ;; esac
    $SUDO cat "$t" > "$OUT/acpi/$(basename "$t").dat" 2>/dev/null
  done
  # Decoded tables (.dsl). The DSDT is decoded again with the SSDTs loaded so cross-table references resolve.
  have iasl && ( cd "$OUT/acpi" && { iasl -d ./*.dat; [ -f DSDT.dat ] && iasl -e SSDT*.dat -d DSDT.dat; } > ../iasl.log 2>&1 )
else
  dmesg 2>/dev/null | redact > "$OUT/dmesg.txt" || echo "dmesg needs root: skipped (no sudo, or --no-root)" > "$OUT/dmesg.txt"
fi

tar -czf "$OUT.tar.gz" "$OUT" && rm -rf "$OUT"
[ -z "$SUDO" ] && [ -n "${SUDO_USER:-}" ] && chown "$SUDO_USER": "$OUT.tar.gz"
echo
echo "wrote $OUT.tar.gz  (board: $BOARD)"
echo "Attach that file to the Multica issue (ANAL-175)."
