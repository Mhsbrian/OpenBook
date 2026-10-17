#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Test the power check add-on (ANAL-178) in QEMU/OVMF on a COPY of a live image, the way the owner's stick will
# look: the add-on's files go onto the copy's ESP next to the live image's own. Then one of these runs:
#   vm    a VM-only entry: the LPS0 fixture SSDT (lps0-test.asl, through the kernel's ACPI table upgrade) and
#         mem_sleep_default=s2idle, so the s2idle LPS0 hooks run as on the laptop; openbook_s0i3_snapshot registers and
#         logs at the "S0i3 attempt"; step 1 binds openbook_pci_pm to the virtio-rng behind a root port
#         (qemu-run.py --detach-test-device), step 2 loads the ASUS modules (no ASUS WMI in a VM). All steps run.
#   real  the add-on's own "OpenBook power check: S0i3" entry, unchanged (QEMU: no LPS0 device, so the snapshot
#         module reports that it has nothing to hook into, and the sleeps are S3).
# The copy is never a stick: image files only. Logs and the stick's report land in
# <data dir>/installer/powercheck/NAME/qemu-RUN/ (serial.log, result.json, logs/).
#
# usage: power-check-qemu.sh NAME RUN [LIVE_IMAGE]    NAME: a make-power-check.sh output name; RUN: vm or real
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); S=$R/scripts/installer; D=$S/inst-docker.sh
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer
NAME=${1:?usage: power-check-qemu.sh NAME vm|real [LIVE_IMAGE]}; RUN=${2:?vm or real}
SRC=${3:-$I/out/openbook-live-20261017-desktop2.img}
ADD=$I/out/$NAME-addon; W=$I/powercheck/$NAME/qemu-$RUN
[ -d "$ADD" ] || { echo "no add-on $ADD: run make-power-check.sh $NAME first" >&2; exit 2; }
case $RUN in vm|real) ;; *) echo "RUN is vm or real" >&2; exit 2 ;; esac
rm -rf "$W"; mkdir -p "$W"
cp --reflink=auto "$SRC" "$W/stick.img"
E="$W/stick.img@@1M"   # the ESP starts at 1 MiB in every OpenBook image
BASE=$(sed -n 's/^options //p' "$ADD/loader/entries/openbook-check-s0i3.conf" | sed 's/ openbook.probe.sleep=1.*//')
# The add-on goes on with the owner's applier (its --image mode: same checks, mtools instead of a mounted stick).
"$D" "$R/scripts/power/add-to-live-stick.sh" --image "$W/stick.img" "$ADD"
"$D" bash -s <<EOF
set -euo pipefail
if [ $RUN = vm ]; then
  cd "$W"
  iasl -p lps0-test "$R/scripts/power/lps0-test.asl" >/dev/null
  mkdir -p fx/kernel/firmware/acpi && cp lps0-test.aml fx/kernel/firmware/acpi/LPS0TEST.aml
  (cd fx && find kernel | cpio -o -H newc --quiet) > lps0-test.cpio
  mcopy -o -i "$E" lps0-test.cpio ::/openbook/check/lps0-test.cpio
  printf '%s\n' "title OpenBook power check: VM test (LPS0 fixture, s2idle)" "sort-key openbook-99" \
    "linux /openbook/check/kernel" "initrd /openbook/check/lps0-test.cpio" "initrd /openbook/check/hwcheck.img" \
    "initrd /openbook/a/bootconfig-live.img" \
    "options $BASE mem_sleep_default=s2idle openbook.probe.sleep=1 openbook.probe.s0i3_snapshot=1 openbook.probe.sleep_s=10 openbook.probe.s0i3_steps=pm:1af4:1044+1af4:1005,asus openbook.probe.s0i3_all=1" \
    > openbook-check-vmtest.conf
  mcopy -o -i "$E" openbook-check-vmtest.conf ::/loader/entries/openbook-check-vmtest.conf
  DEF=openbook-check-vmtest.conf
else
  DEF=openbook-check-s0i3.conf
fi
printf 'timeout 0\ndefault %s\nconsole-mode keep\neditor no\n' "\$DEF" > "$W/loader.conf"
mcopy -o -i "$E" "$W/loader.conf" ::/loader/loader.conf
mdir -i "$E" -b ::/loader/entries ::/openbook/check
EOF
# vm: each cycle is woken by the ACPI power button (QEMU's RTC alarm does not end a guest's suspend-to-idle).
# real: S3 in QEMU, woken by the RTC as on the hardware-check stick's VM runs.
python3 - "$W/expect.json" "$RUN" <<'EOF'
import json, sys
out, run = sys.argv[1:]
steps = [{"wait": "hwcheck: OpenBook hardware check v7", "timeout": 120}]
for i in range(3 if run == "vm" else 4):  # baseline + one cycle per step
    steps.append({"wait": r"sleep: RTC alarm in \d+ s; suspending", "timeout": 240})
    if run == "vm":
        steps += [{"pause": 14}, {"monitor": "system_powerdown"}]
    steps.append({"wait": rf"sleep\[{i}\]: (REACHED|did NOT|S0i3 unknown)", "timeout": 150})
steps.append({"wait": "hwcheck: report saved; powering off", "timeout": 240})
json.dump(steps, open(out, "w"), indent=1)
EOF
"$D" python3 "$S/qemu-run.py" --usb "$W/stick.img" --out "$W/run" --timeout 900 --expect "$W/expect.json" \
  --detach-test-device --vga none || true
"$D" bash -c "rm -rf '$W/logs' && mcopy -s -o -i '$E' ::/openbook/logs '$W/' && ls -la '$W/logs'"
J=$(ls "$W"/logs/hwcheck-*.json 2>/dev/null | tail -n 1)
[ -n "$J" ] && python3 -c "import json,sys; j=json.load(open(sys.argv[1])); print(json.dumps({k: j[k] for k in ('schema','s0i3_snapshot','sleep_test')}, indent=1)); [print(json.dumps({k: c[k] for k in ('cycle','step','bound','s0i3','s0ix_residency_us','last_hw_sleep_us','smu','idlemask_entry','cpuidle','snapshot')})) for c in j['sleep_cycles']]" "$J"
grep -aE "PROBE (hwcheck|sleep|step|kmod|cpuidle)|openbook_s0i3_snapshot|openbook_pci_pm" "$W/run/serial.log" | sed 's/^.*PROBE /PROBE /' | head -80
