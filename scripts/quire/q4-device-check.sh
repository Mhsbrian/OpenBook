#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Quire Q4 (ANAL-218) on the device itself, as root on a userdebug OpenBook: the same checks as q4-cf-check.py,
# for the G14, where no host drives adb. Android's mksh and toybox only.
#
#   sh q4-device-check.sh IMAGE OUTDIR [PROMPT]
#
# IMAGE is the Linux environment's images.tar.gz (scripts/quire/linux-env-image.sh). It is copied to
# /sdcard/linux/images.tar.gz, where the Terminal app installs from on debuggable builds. OUTDIR gets results.tsv
# (check, PASS/FAIL/INFO, detail) and the logs. Steps:
#   1. KVM: the CPU's svm flag, KVM's device, /dev/kvm, kvm_amd in the kernel log, vendor.openbook.kvm and the
#      ro.boot.hypervisor.* properties init.openbook.rc derives from it.
#   2. AVF: the feature, crosvm and virtmgr, the Terminal app (off by default) and Quire's permission.
#   3. Without KVM, Quire must say the Linux environment can't run and name the fallback; the check stops there.
#   4. The person's steps: Terminal on, Install. Then the guest's boot time (its console) and VM start to quired.
#   5. Quire core lists the agents in the guest and sends PROMPT (default "Reply with exactly: QUIRE OK").
set -u
IMAGE=${1:?usage: q4-device-check.sh IMAGE OUTDIR [PROMPT]}
OUT=${2:?usage: q4-device-check.sh IMAGE OUTDIR [PROMPT]}
PROMPT=${3:-Reply with exactly: QUIRE OK}
T=com.android.virtualization.terminal
BRIDGE=content://com.android.virtualization.terminal.agentbridge
LAB=dev.openbook.quire/.control.LabActivity
mkdir -p "$OUT"
: > "$OUT/results.tsv"
fails=0

log() { echo "$(date +%H:%M:%S) $*" | tee -a "$OUT/checks.log"; }
result() {  # result NAME PASS|FAIL|INFO DETAIL
  printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$OUT/results.tsv"
  log "$2 $1: $3"
  [ "$2" = FAIL ] && fails=$((fails + 1))
  return 0
}
check() { if [ "$2" = 0 ]; then result "$1" PASS "$3"; else result "$1" FAIL "$3"; fi; }
mark() { tag="q4-device $1 $(date +%s)"; /system/bin/log -t Quire -p i "$tag"; echo "$tag"; }
lab() { a=$1; shift; am start -n $LAB -a dev.openbook.quire.lab.$a "$@" >/dev/null 2>&1; }
since() { logcat -d -v time -s Quire:I | sed -n "/$1/,\$p"; }
wait_line() {  # wait_line TAG REGEX SECONDS: prints the first matching Quire line after TAG
  n=0
  while [ $n -lt "$3" ]; do
    l=$(since "$1" | grep -E "$2" | head -n 1)
    [ -n "$l" ] && { echo "$l"; return 0; }
    sleep 1; n=$((n + 1))
  done
  return 1
}
state() { content call --uri $BRIDGE --method status 2>&1 | sed -n 's/.*state=\([a-z_]*\).*/\1/p'; }

log "== kvm"
svm=$(grep -c -w svm /proc/cpuinfo)
result "CPU svm flag (cores)" INFO "$svm"
[ -e /sys/devices/virtual/misc/kvm/dev ]; check "KVM registered its device" $? "$(cat /sys/devices/virtual/misc/kvm/dev 2>/dev/null)"
ls -l /dev/kvm > "$OUT/dev-kvm.txt" 2>&1; check "/dev/kvm" $? "$(cat "$OUT/dev-kvm.txt")"
dmesg | grep -i -E 'kvm|svm' > "$OUT/kernel-kvm.txt" 2>&1
grep -q -i 'kvm_amd' "$OUT/kernel-kvm.txt"; check "kvm_amd in the kernel log" $? "$(head -n 2 "$OUT/kernel-kvm.txt" | tr '\n' ' ')"
getprop | grep -E 'hypervisor|openbook.kvm' > "$OUT/props.txt"
result "properties" INFO "$(tr '\n' ' ' < "$OUT/props.txt")"
kvm=0; [ "$(getprop ro.boot.hypervisor.vm.supported)" = 1 ] && kvm=1

log "== avf"
pm list features | grep -q virtualization_framework; check "feature android.software.virtualization_framework" $? ""
ls /apex/com.android.virt/bin > "$OUT/virt-apex.txt" 2>&1
grep -q crosvm "$OUT/virt-apex.txt" && grep -q virtmgr "$OUT/virt-apex.txt"; check "crosvm and virtmgr" $? ""
pm path $T > /dev/null; check "Terminal app installed" $? "$(pm list packages -d $T | grep -c $T) disabled"
dumpsys package dev.openbook.quire | grep -q 'ACCESS_AGENT_BRIDGE: granted=true'; check "Quire holds ACCESS_AGENT_BRIDGE" $? ""

if [ $kvm = 0 ]; then
  log "== nokvm"
  tag=$(mark nokvm)
  lab AGENTS_LIST
  l=$(wait_line "$tag" 'agents: unavailable' 30)
  echo "$l" | grep -q "no hardware virtualization" && echo "$l" | grep -q "none is paired"
  check "no KVM: Quire says so and names the fallback" $? "$l"
  since "$tag" > "$OUT/quire.txt"
  log "== $fails failure(s)"
  exit $fails
fi

log "== install"
pm enable $T > /dev/null
for p in ACCESS_LOCAL_NETWORK POST_NOTIFICATIONS RECORD_AUDIO; do pm grant $T android.permission.$p 2>/dev/null; done
mkdir -p /sdcard/linux
cp "$IMAGE" /sdcard/linux/images.tar.gz; check "image copied" $? "$(ls -l /sdcard/linux/images.tar.gz)"
am start -n $T/.LauncherActivity > /dev/null
tapped=1; n=0
while [ $n -lt 40 ]; do
  uiautomator dump /data/local/tmp/q4-ui.xml > /dev/null 2>&1
  b=$(tr '>' '\n' < /data/local/tmp/q4-ui.xml | grep 'text="Install"' | sed -n 's/.*bounds="\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]".*/\1 \2 \3 \4/p' | head -n 1)
  if [ -n "$b" ]; then
    set -- $b
    input tap $((($1 + $3) / 2)) $((($2 + $4) / 2)); tapped=0; break
  fi
  sleep 1; n=$((n + 1))
done
check "Install tapped" $tapped ""
t0=$(date +%s); started=; n=0; s=
while [ $n -lt 600 ]; do
  s=$(state)
  [ "$s" = starting ] && [ -z "$started" ] && started=$(date +%s)
  [ "$s" = running ] || [ "$s" = error ] && break
  sleep 1; n=$((n + 1))
done
[ "$s" = running ]; check "Linux environment running" $? "state=$s after $(($(date +%s) - t0)) s"
[ -n "$started" ] || started=$t0

log "== guest"
ok=1; n=0
while [ $n -lt 60 ]; do
  tag=$(mark list-$n)
  lab AGENTS_LIST
  if l=$(wait_line "$tag" 'agents: (agent |unavailable)' 30) && echo "$l" | grep -q 'agents: agent'; then ok=0; break; fi
  sleep 3; n=$((n + 1))
done
since "$tag" > "$OUT/quire-agents.txt"
check "Quire core lists the agents in the guest" $ok "$(grep 'agents: agent' "$OUT/quire-agents.txt" | sed 's/.*agents: //' | tr '\n' ';')"
result "VM start -> quired answering (s)" INFO "$(($(date +%s) - started))"
cat /data/data/$T/files/*.log/* > "$OUT/guest-console.log" 2>/dev/null
result "guest boot (systemd)" INFO "$(grep -o 'Startup finished in .*' "$OUT/guest-console.log" | head -n 1)"

log "== prompt"
tag=$(mark prompt)
lab AGENTS_PROMPT --es agent opencode --es text "$PROMPT" --es approve none
l=$(wait_line "$tag" 'agents: (answer|error prompt)' 300)
echo "$l" | grep -q 'stop=end_turn' && echo "$l" | grep -q 'QUIRE OK'; check "a prompt from Quire core is answered in the guest" $? "$l"
since "$tag" > "$OUT/quire-prompt.txt"

logcat -d -v time -b all > "$OUT/logcat-all.txt"
logcat -d -b all | grep 'avc:  denied' | sed -E 's/.*avc:  denied/avc: denied/; s/ pid=[0-9]+//; s/ ino=[0-9]+//' | sort | uniq -c > "$OUT/selinux-denials.txt"
result "SELinux denials (distinct)" INFO "$(wc -l < "$OUT/selinux-denials.txt")"
log "== $fails failure(s)"
exit $fails
