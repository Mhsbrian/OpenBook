#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The G14 touchpad's clock in QEMU (ANAL-178): boot a COPY of a live image with its serial-console entry, create the
# ELAN touchpad as a uhid device (elan-uhid.c: the laptop's own report descriptor, so the kernel's hid-multitouch
# binds as on the G14), play one-finger strokes, and count what the laptop showed: BTN_TOOL_FINGER autorepeat frames
# (no MSC_TIMESTAMP) in the touchpad's events, and the gestures library's "Clock changed backwards" errors. The
# test binary reaches the guest on a raw NVMe disk image. Image files only.
# Results in <data dir>/installer/powercheck/touchpad-RUN/: run/serial.log, events.txt (getevent -lt), devices.txt,
# input.txt (dumpsys input, the test device), result.json.
#
# usage: touchpad-qemu.sh RUN [LIVE_IMAGE]
#   TP_MODE=plain|palm|sticky: how each stroke ends or pauses (elan-uhid.c); default plain
set -euo pipefail
R=$(cd "$(dirname "$0")/../../.." && pwd); S=$R/scripts/installer; D=$S/inst-docker.sh; H=$(cd "$(dirname "$0")" && pwd)
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer
RUN=${1:?usage: touchpad-qemu.sh RUN [LIVE_IMAGE]}; SRC=${2:-$I/out/openbook-live-20261017-anal178c.img}
W=$I/powercheck/touchpad-$RUN
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
cp --reflink=auto "$SRC" "$W/stick.img"
printf 'timeout 0\ndefault openbook-vm.conf\nconsole-mode keep\neditor no\n' > "$W/loader.conf"
"$D" mcopy -o -i "$W/stick.img@@1M" "$W/loader.conf" ::/loader/loader.conf
python3 - "$W/expect.json" "$N" "${TP_MODE:-plain}" <<'EOF'
import json, sys
n = int(sys.argv[2]); mode = sys.argv[3]; T = "/data/local/tmp"
p = {"wait": "console:/ \\$ ", "timeout": 120}
def mark(name):  # markers split with "" so the echoed command line does not match
    return f"echo ===TP-{name[:1]}\"\"{name[1:]}==="
steps = [{"wait": "init: init second stage started", "timeout": 300}, {"send": "\n"}, p,
         {"send": "su 0 dmesg -n 1\n"}, p,
         {"send": "i=0; while [ \"$(getprop sys.boot_completed)\" != 1 ] && [ $i -lt 600 ]; do sleep 3; "
                  "i=$((i+3)); done; echo BOOT\"\"DONE=$(getprop sys.boot_completed)\n"},
         {"wait": "BOOTDONE=1", "timeout": 660}, p, {"send": "sleep 20\n"}, p,
         {"send": f"su 0 sh -c 'head -c {n} /dev/block/nvme0n1 > {T}/elan-uhid && chmod 755 {T}/elan-uhid'; "
                  f"echo COPY\"\"RC=$?\n"}, {"wait": "COPYRC=\\d+", "timeout": 60}, p,
         {"send": "su 0 logcat -b all -c\n"}, p,
         {"send": f"su 0 sh -c 'timeout 40 getevent -lt > {T}/tp-events.txt 2>&1 &'; sleep 1\n"}, p,
         {"send": f"su 0 sh -c '{T}/elan-uhid 4 2000 1500 {mode} > {T}/tp-elan.txt 2>&1 &'; sleep 5; "
                  f"{mark('DEVICES')}; su 0 cat /proc/bus/input/devices; "
                  f"{mark('INPUT')}; su 0 dumpsys input | grep -A 40 'OpenBook test ELAN 04F3:3315 Touchpad' | head -n 60; "
                  f"{mark('WAIT')}\n"}, {"wait": "\n===TP-WAIT===", "timeout": 120}, p,
         {"send": f"sleep 30; {mark('ELAN')}; su 0 cat {T}/tp-elan.txt; {mark('COUNTS')}; "
                  "echo clock_changed_backwards=$(su 0 logcat -d -b all | grep -c 'Clock changed backwards'); "
                  "su 0 logcat -d -b all -v monotonic | grep -B 6 -A 1 'Clock changed backwards' | "
                  "grep -E 'Clock changed|EventHub|InputReader|Gestures|Touchpad|input' | head -n 40; "
                  f"{mark('B64BEGIN')}; su 0 sh -c 'gzip -c {T}/tp-events.txt | base64'; {mark('B64END')}\n"},
         {"wait": "\n===TP-B64END===", "timeout": 300}, p, {"send": "su 0 reboot -p\n"}]
json.dump(steps, open(sys.argv[1], "w"), indent=1)
EOF
"$D" python3 "$S/qemu-run.py" --usb "$W/stick.img" --nvme "$W/test-disk.img" --out "$W/run" --expect "$W/expect.json" \
  --gpu virtio-vga,xres=1920,yres=1200 --usb-input --tpm --mem 6144 --smp 6 --timeout 1200 --linger 5 || true
python3 - "$W" "$R/scripts/installer" "$SRC" <<'EOF'
import base64, gzip, json, re, sys
w = sys.argv[1]; sys.path.insert(0, sys.argv[2])
import importlib.util
spec = importlib.util.spec_from_file_location("lr", f"{sys.argv[2]}/live-report.py"); lr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lr)
log = open(f"{w}/run/serial.log", "rb").read().decode("utf-8", "replace").replace("\r", "")
def sec(name, nxt):
    m = re.findall(rf"\n===TP-{name}===\n(.*?)\n===TP-{nxt}===", log, re.S)
    return m[-1] if m else ""
devices, inp, elan, counts = sec("DEVICES", "INPUT"), sec("INPUT", "WAIT"), sec("ELAN", "COUNTS"), sec("COUNTS", "B64BEGIN")
b64 = sec("B64BEGIN", "B64END")
events = gzip.decompress(base64.b64decode("".join(l.strip() for l in b64.splitlines()
                                                  if re.fullmatch(r"[A-Za-z0-9+/=]+", l.strip())))).decode() if b64 else ""
open(f"{w}/devices.txt", "w").write(devices); open(f"{w}/input.txt", "w").write(inp); open(f"{w}/events.txt", "w").write(events)
# the test touchpad's own event lines: getevent names it in its "add device" block
node = re.search(r"add device \d+: (/dev/input/event\d+)\s+name:\s+\"OpenBook test ELAN 04F3:3315 Touchpad\"", events)
mine = "\n".join(re.sub(r"^(\[\s*[\d.]+\]) \S+: ", r"\1 ", l) for l in events.splitlines()
                 if node and f"{node.group(1)}:" in l)
block = next((b for b in devices.split("\n\n") if "OpenBook test ELAN 04F3:3315 Touchpad" in b), "")
ev = re.search(r"B: EV=(\S+)", block)
c = dict(re.findall(r"(\w+)=(\d+)", counts))
res = {"image": sys.argv[3].rsplit("/", 1)[-1], "mode": __import__("os").environ.get("TP_MODE", "plain"), "elan_uhid": elan.strip().splitlines()[-1:] if elan.strip() else None,
       "touchpad_node": node.group(1) if node else None, "ev_bits": ev.group(1) if ev else None,
       "ev_rep": bool(ev and int(ev.group(1), 16) >> 20 & 1),
       "classes": (re.search(r"Classes: (.*)", inp) or [None, None])[1],
       "repeat_frames": len(re.findall(r"BTN_TOOL_FINGER\s+REPEAT", mine)),
       "clock_changed_backwards": int(c["clock_changed_backwards"]) if "clock_changed_backwards" in c else None,
       "touchpad_clock": lr.touchpad_clock(mine)}
json.dump(res, open(f"{w}/result.json", "w"), indent=1)
print(json.dumps(res, indent=1))
EOF
