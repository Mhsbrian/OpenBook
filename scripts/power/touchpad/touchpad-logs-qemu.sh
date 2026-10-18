#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The touchpad capture of a "save logs" boot in QEMU (ANAL-178). Boots a COPY of a live image with its VM-only
# "console + save logs" entry. While Android boots, the G14's touchpad appears on uhid (elan-uhid.c, the laptop's
# own descriptor), so it is there when sys.boot_completed=1 is reached, as on the laptop. 40 s later it plays strokes:
# a finger used right after the desktop appears, which is what the owner's checklist asks for. The logs helper then
# finishes and powers off, and the boot's report is read from the copy's ESP. Expected: TOUCHPADEV holds those
# strokes (openbook-live-init's TOUCHPAD_EARLY capture), and live-report's touchpad_clock has frames. Image files only.
# Results in <data dir>/installer/powercheck/touchpad-logs-RUN/: run/serial.log, logs/live-001/, result.json.
#
# usage: touchpad-logs-qemu.sh RUN [LIVE_IMAGE]        TP_MODE=plain|palm|sticky as in touchpad-qemu.sh
set -euo pipefail
R=$(cd "$(dirname "$0")/../../.." && pwd); S=$R/scripts/installer; D=$S/inst-docker.sh; H=$(cd "$(dirname "$0")" && pwd)
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer
RUN=${1:?usage: touchpad-logs-qemu.sh RUN [LIVE_IMAGE]}; SRC=$(realpath "${2:-$I/out/openbook-live-20261018-anal192d.img}")
[ -d "${SRC%.img}.vm" ] || { echo "${SRC%.img}.vm (the image's VM bundle) is needed" >&2; exit 2; }
W=$I/powercheck/touchpad-logs-$RUN
rm -rf "$W"; mkdir -p "$W/gen"
python3 - "$H/elan-04f3-3315.rdesc.hex" "$W/gen/elan_rdesc.h" <<'EOF'
import sys
b = bytes.fromhex(open(sys.argv[1]).read().strip())
rows = ",\n".join("    " + ", ".join(f"0x{x:02x}" for x in b[i:i + 16]) for i in range(0, len(b), 16))
open(sys.argv[2], "w").write(f"// generated from elan-04f3-3315.rdesc.hex\nstatic const unsigned char RDESC[] = {{\n{rows}\n}};\n")
EOF
"$D" gcc -O2 -static -Wall -Werror -I"$W/gen" -o "$W/elan-uhid" "$H/elan-uhid.c" -lm
N=$(stat -c %s "$W/elan-uhid")
cp "$W/elan-uhid" "$W/test-disk.img"; truncate -s $(( (N / 1048576 + 1) * 1048576 )) "$W/test-disk.img"
cp --reflink=auto "$SRC" "$W/stick.img"; truncate -s 16G "$W/stick.img"
E="$W/stick.img@@1M"   # the ESP starts at 1 MiB in every OpenBook image
printf 'timeout 0\ndefault openbook-vm-logs.conf\nconsole-mode keep\neditor no\n' > "$W/loader.conf"
"$D" bash -c "mcopy -o -s -m -i '$E' '${SRC%.img}.vm/loader' '${SRC%.img}.vm/openbook' ::/ && mcopy -o -i '$E' '$W/loader.conf' ::/loader/loader.conf"
python3 - "$W/expect.json" "$N" "${TP_MODE:-plain}" <<'EOF'
import json, sys
n = int(sys.argv[2]); mode = sys.argv[3]; T = "/data/local/tmp"
p = {"wait": "console:/ \\$ ", "timeout": 120}
start = (f"su 0 sh -c 'until [ -d {T} ]; do sleep 1; done; head -c {n} /dev/block/nvme0n1 > {T}/elan-uhid && "
         f"chmod 755 {T}/elan-uhid && ({T}/elan-uhid 4 2000 1500 {mode} 40000 > {T}/tp-elan.txt 2>&1 &)'; "
         "echo START\"\"RC=$?\n")
steps = [{"wait": "init: init second stage started", "timeout": 300}, {"send": "\n"}, p,
         {"send": start}, {"wait": "STARTRC=\\d+", "timeout": 300},
         {"wait": "openbook-live: logs: sys.boot_completed=1", "timeout": 900},
         {"wait": "openbook-live: logs: done: ", "timeout": 1500}]
json.dump(steps, open(sys.argv[1], "w"), indent=1)
EOF
set +e
"$D" python3 "$S/qemu-run.py" --usb "$W/stick.img" --nvme "$W/test-disk.img" --out "$W/run" --expect "$W/expect.json" \
  --gpu virtio-vga,xres=1920,yres=1200 --usb-input --tpm --mem 6144 --smp 6 --timeout 2400 --linger 60
echo "qemu-run exit $?"
set -e
"$D" bash -c "rm -rf '$W/logs' && mcopy -s -o -i '$E' ::/openbook/logs '$W/'"
L=$(ls -d "$W"/logs/live-[0-9]* | tail -n 1)
python3 "$S/live-report.py" "$L" --expect g14 > /dev/null
python3 - "$L" "$SRC" <<'EOF'
import json, re, sys
d = sys.argv[1]
col = open(f"{d}/collect-final.txt", errors="replace").read()
m = re.search(r"^===TOUCHPADEV===\n(.*?)^===", col, re.S | re.M)
sec = m.group(1) if m else ""
v = json.load(open(f"{d}/report.json")); v = v.get("verdicts", v)
res = {"image": sys.argv[2].rsplit("/", 1)[-1], "touchpadev_lines": len(sec.splitlines()),
       "from_boot_completed": sec.startswith("# from sys.boot_completed"),
       "touchpad_clock": v.get("touchpad_clock"), "touchpad_clock_warnings": v.get("touchpad_clock_warnings")}
json.dump(res, open(f"{d}/../../result.json", "w"), indent=1)
print(json.dumps(res, indent=1))
EOF
grep -aE 'openbook-live: logs: (sys.boot|done)|elan-uhid' "$W/run/serial.log" | sed 's/^.*\] //' | tail -n 8
