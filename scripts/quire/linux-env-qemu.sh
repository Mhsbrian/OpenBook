#!/usr/bin/env bash
# Boot the Linux environment's Debian image (scripts/quire/linux-env-image.sh) on this host and check
# its side of Quire: the guest boots on its own kernel, cloud-init makes the user, quired serves on
# vsock and lists the agents installed in the guest, and a prompt crosses vsock and comes back.
#
#   scripts/quire/linux-env-qemu.sh IMAGES_TAR_GZ OUTDIR [--prompt AGENT TEXT] [--cid N]
#
# The guest runs as AVF runs it: direct kernel boot (vmlinuz, initrd.img, root=/dev/vda1 on a GPT
# disk whose partition keeps the image's GUID), AOSP's cidata.iso as the second disk, virtio-net,
# and a vsock device. Here QEMU's vhost-vsock gives this host CID 2 towards the guest, the CID
# Android has under AVF, so quired accepts it as it would accept Android. QEMU runs in the
# anybook-qemu container (tools/Dockerfile.qemu) with /dev/kvm and /dev/vhost-vsock.
#
# --prompt sends one prompt through `quired run --connect` (the same ACP path Quire core uses)
# with --approve none, so the agent may not change anything. It uses whatever account the agent
# in the guest has: opencode's free models need none.
#
# Writes OUTDIR/: console.log, timings.txt, agents-host.txt (through vsock), guest.txt (quired
# agents inside the guest, quired's journal, a refused loopback connection), prompt.ndjson.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
tar=${1:?usage: linux-env-qemu.sh IMAGES_TAR_GZ OUTDIR [--prompt AGENT TEXT] [--cid N]}
out=${2:?usage: linux-env-qemu.sh IMAGES_TAR_GZ OUTDIR [--prompt AGENT TEXT] [--cid N]}
shift 2
cid=218
prompt_agent= prompt_text=
while [ $# -gt 0 ]; do
	case $1 in
		--prompt) prompt_agent=$2; prompt_text=$3; shift 3 ;;
		--cid) cid=$2; shift 2 ;;
		*) echo "unknown option $1" >&2; exit 2 ;;
	esac
done
AOSP=${AOSP:-$HOME/anybook/aosp/src}
work=${WORK:-$HOME/anybook/quire/linux-env/qemu}
serial_port=$((16000 + cid))
name=quire-linux-env-$cid
mkdir -p "$out" "$work"
out=$(cd "$out" && pwd)

quired=$work/quired-host
(cd "$repo/quire/quired" && go build -o "$quired" .)

rm -rf "$work/g"
mkdir -p "$work/g"
tar -xzf "$tar" -C "$work/g"
g=$work/g
guid=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['disks'][0]['partitions'][0]['guid'])" "$g/vm_config.json")
sz=$(stat -c %s "$g/root_part")
truncate -s $((sz + 4 * 1024 * 1024)) "$g/disk.img"
printf 'label: gpt\nfirst-lba: 2048\nstart=2048, size=%d, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=%s, name=ROOT\n' \
	$((sz / 512)) "$guid" | sfdisk -q "$g/disk.img"
dd if="$g/root_part" of="$g/disk.img" bs=1M seek=1 conv=sparse,notrunc status=none
rm "$g/root_part"
cp "$AOSP/packages/modules/Virtualization/android/TerminalApp/assets-x86_64/cidata.iso" "$g/"
params=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['params'])" "$g/vm_config.json")

docker rm -f "$name" >/dev/null 2>&1 || true
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
t0=$(date +%s.%N)
docker run -d --name "$name" --network host --device /dev/kvm --device /dev/vhost-vsock -v "$g:/g" anybook-qemu \
	qemu-system-x86_64 -enable-kvm -cpu host -smp 4 -m 4096 -nographic -no-reboot \
	-kernel /g/vmlinuz -initrd /g/initrd.img -append "$params" \
	-drive file=/g/disk.img,if=virtio,format=raw -drive file=/g/cidata.iso,if=virtio,format=raw,readonly=on \
	-device vhost-vsock-pci,guest-cid="$cid" -netdev user,id=n0 -device virtio-net-pci,netdev=n0 \
	-chardev socket,id=s0,host=127.0.0.1,port=$serial_port,server=on,wait=off,logfile=/g/console.log \
	-serial chardev:s0 -monitor none -display none >/dev/null

# quired answers once the guest has booted, cloud-init has made the user and systemd started it.
ready=
for _ in $(seq 1 180); do
	if "$quired" agents --connect "vsock:$cid:7690" > "$out/agents-host.txt" 2>"$out/agents-host.err"; then
		ready=$(date +%s.%N)
		break
	fi
	sleep 1
done
cp "$g/console.log" "$out/console.log" 2>/dev/null || true
if [ -z "$ready" ]; then
	echo "quired did not answer on vsock:$cid:7690 within 180 s" | tee "$out/timings.txt"
	exit 1
fi
kernel_up=$(grep -a -m1 -o 'Linux version [^ ]*' "$g/console.log" | head -1)
{
	echo "guest: $kernel_up"
	awk -v a="$t0" -v b="$ready" 'BEGIN { printf "qemu start -> quired answering on vsock: %.1f s\n", b - a }'
} | tee "$out/timings.txt"
cat "$out/agents-host.txt"

# Inside the guest: quired's own listing, its journal, and a connection from the guest itself
# (vsock loopback, CID 1), which quired must refuse.
python3 "$repo/scripts/quire/serial-shell.py" 127.0.0.1 "$serial_port" droid droid \
	'systemctl is-active quired.service' \
	'quired version' \
	'quired agents' \
	'sudo modprobe vsock_loopback; timeout 5 socat -u /dev/null VSOCK-CONNECT:1:7690; echo socat=$?' \
	'journalctl -u quired.service -b --no-pager -o short-monotonic | tail -20' \
	'systemd-analyze' \
	> "$out/guest.txt" 2>&1 || true
cat "$out/guest.txt"

if [ -n "$prompt_agent" ]; then
	t1=$(date +%s.%N)
	"$quired" run --connect "vsock:$cid:7690" --approve none --json --timeout 180s "$prompt_agent" "$prompt_text" \
		> "$out/prompt.ndjson" 2> "$out/prompt.stderr" && rc=0 || rc=$?
	awk -v a="$t1" -v b="$(date +%s.%N)" -v ag="$prompt_agent" -v rc="$rc" \
		'BEGIN { printf "prompt through vsock (%s): exit %s in %.1f s\n", ag, rc, b - a }' | tee -a "$out/timings.txt"
	python3 - "$out/prompt.ndjson" <<'EOF' | tee "$out/prompt.summary.txt"
import json, sys
text, stop = [], None
for line in open(sys.argv[1]):
    try:
        m = json.loads(line)
    except ValueError:
        continue
    u = m.get("params", {}).get("update", {})
    if u.get("sessionUpdate") == "agent_message_chunk":
        text.append(u.get("content", {}).get("text", ""))
    if m.get("quired") == "result":
        stop = m.get("stopReason"), m.get("error")
print("answer:", repr("".join(text)))
print("stop:", stop)
EOF
fi
cp "$g/console.log" "$out/console.log"
