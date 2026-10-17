#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run the live stick's "save logs" fact collection (COLLECT in scripts/installer/live-init.c, as it is in this
# checkout) inside Android 17 in QEMU, on a COPY of a live image booted with its serial-console entry, so the
# sections added for power and input (ANAL-178) are checked on Android's own mksh, toybox, dumpsys and getevent
# without rebuilding the image. Writes collect.txt (the "===NAME===" sections live-report.py reads) and
# sections.json (lines per section, and lines that look like shell errors) to
# <data dir>/installer/powercheck/collect-RUN/. Image files only.
#
# usage: collect-qemu.sh RUN [LIVE_IMAGE]
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); S=$R/scripts/installer; D=$S/inst-docker.sh
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer
RUN=${1:?usage: collect-qemu.sh RUN [LIVE_IMAGE]}; SRC=${2:-$I/out/openbook-live-20261017-desktop2.img}
W=$I/powercheck/collect-$RUN
rm -rf "$W"; mkdir -p "$W"
cp --reflink=auto "$SRC" "$W/stick.img"
printf 'timeout 0\ndefault openbook-vm.conf\nconsole-mode keep\neditor no\n' > "$W/loader.conf"
"$D" mcopy -o -i "$W/stick.img@@1M" "$W/loader.conf" ::/loader/loader.conf
# COLLECT, decoded from the C source (adjacent string literals, C escapes), typed into the console as a file.
python3 - "$S/live-init.c" "$W/expect.json" <<'EOF'
import json, re, sys
src = open(sys.argv[1]).read()
body = src[src.index("static const char COLLECT[] ="):]
body = body[:body.index(";\n")]
body = re.sub(r"//[^\n]*", "", body)  # C comments may quote text too
lits = re.findall(r'"((?:[^"\\]|\\.)*)"', body)
script = "".join(bytes(l, "utf-8").decode("unicode_escape") for l in lits)
assert "OBEOF" not in script
prompt = {"wait": "console:/ \\$ ", "timeout": 120}
steps = [{"wait": "init: init second stage started", "timeout": 300}, {"send": "\n"}, prompt,
         {"send": "su 0 dmesg -n 1\n"}, prompt,
         {"send": "i=0; while [ \"$(getprop sys.boot_completed)\" != 1 ] && [ $i -lt 600 ]; do sleep 3; "
                  "i=$((i+3)); done; echo BOOT\"\"DONE=$(getprop sys.boot_completed)\n"},
         {"wait": "BOOTDONE=1", "timeout": 660}, prompt, {"send": "sleep 20\n"}, prompt,
         {"send": "export TMPDIR=/data/local/tmp\n"}, prompt,  # mksh keeps heredocs in $TMPDIR
         {"send": "cat > /data/local/tmp/collect.sh <<'OBEOF'\n" + script + "OBEOF\n"}, {**prompt, "timeout": 300},
         {"send": "su 0 timeout 240 sh /data/local/tmp/collect.sh > /data/local/tmp/collect.txt 2>&1; echo COLLECTRC=$?; "
                  "grep -n '^===' /data/local/tmp/collect.txt | tail -n 2\n"},
         {"wait": "COLLECTRC=\\d+", "timeout": 300}, prompt,
         {"send": "echo ===B64-\"\"BEGIN===; gzip -c /data/local/tmp/collect.txt | base64; echo ===B64-\"\"END===\n"},
         {"wait": "\n===B64-END===", "timeout": 300}, prompt, {"send": "su 0 reboot -p\n"}]
json.dump(steps, open(sys.argv[2], "w"), indent=1)
EOF
"$D" python3 "$S/qemu-run.py" --usb "$W/stick.img" --out "$W/run" --expect "$W/expect.json" \
  --gpu virtio-vga,xres=1920,yres=1200 --usb-input --tpm --mem 6144 --smp 6 --timeout 1500 --linger 5 || true
python3 - "$W" <<'EOF'
import base64, gzip, json, re, sys
w = sys.argv[1]
log = open(f"{w}/run/serial.log", "rb").read().decode("utf-8", "replace").replace("\r", "")
m = re.findall(r"\n===B64-BEGIN===\n(.*?)\n===B64-END===", log, re.S)
if not m:
    sys.exit("no collect.txt in the serial log (see run/serial.log)")
blob = "".join(l.strip() for l in m[-1].splitlines() if re.fullmatch(r"[A-Za-z0-9+/=]+", l.strip()))
text = gzip.decompress(base64.b64decode(blob)).decode("utf-8", "replace")
open(f"{w}/collect.txt", "w").write(text)
secs, cur = {}, None
for line in text.splitlines():
    h = re.fullmatch(r"===([A-Z]+)===", line)
    if h:
        cur = h.group(1); secs[cur] = []
    elif cur and line.strip():
        secs[cur].append(line)
errs = {k: [l for l in v if re.search(r"not found|syntax error|No such file|Permission denied|unknown option", l)]
        for k, v in secs.items()}
out = {"collectrc": re.findall(r"COLLECTRC=(\d+)", log)[-1:], "lines": {k: len(v) for k, v in secs.items()},
       "errors": {k: v[:5] for k, v in errs.items() if v}}
json.dump(out, open(f"{w}/sections.json", "w"), indent=1)
print(json.dumps(out, indent=1))
for k in ("SUSPEND", "POWERSTATE", "EPP", "SENSORS", "BAT", "LEDS"):
    print(f"--- {k}"); print("\n".join(secs.get(k, ["(missing)"])[:12]))
print("--- GETEVENT (head)"); print("\n".join(secs.get("GETEVENT", ["(missing)"])[:15]))
EOF
