#!/usr/bin/env bash
# Boot the Linux environment's Debian image (scripts/quire/linux-env-image.sh) on this host and check
# its side of Quire: the guest boots on its own kernel, cloud-init makes the user, quired serves on
# vsock and lists the agents installed in the guest, and a prompt crosses vsock and comes back.
#
#   scripts/quire/linux-env-qemu.sh IMAGES_TAR_GZ OUTDIR [--prompt AGENT TEXT] [--cid N] [--setup]
#   scripts/quire/linux-env-qemu.sh IMAGES_TAR_GZ OUTDIR --no-helper DEB [--cid N]
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
# --setup checks the setup wizard's guest side with the guest's real systemd units, no mocks
# (docs/quire-setup.md §8): from this host (CID 2, as Android), the admin worker on vsock 7691
# installs git from Debian and refuses a package off its list; from inside the guest (CID 1) it
# refuses the connection; it refuses an older quired, then updates quired to a newer test build
# while postinst restarts quired.service, and the update's result is read on a new connection;
# then opencode is installed by its catalog recipe through quired serve's _quire/install and
# answers one prompt. It needs the guest online (QEMU's user network).
#
# --no-helper DEB checks Quire setup's way out for a Linux environment without quired (ANAL-394,
# docs/quire-setup.md §4.4) on an image that has none, normally Google's: nothing answers on vsock
# 7690; DEB (the quired package Quire core carries) is put in the person's Downloads, which the
# guest sees as the Terminal app shares it (virtiofs, tag "android", at /mnt/shared); the wizard's
# command, built as SetupModel.helperCommand builds it, refuses a tampered copy and installs the
# real one; then quired and the admin worker answer from this host (CID 2), and a file the person
# had in the guest is still there.
#
# Writes OUTDIR/: console.log, timings.txt, agents-host.txt (through vsock), guest.txt (quired
# agents inside the guest, quired's journal, a refused loopback connection), prompt.ndjson, and
# with --setup setup-*.ndjson, setup-guest.txt and setup-summary.txt; with --no-helper
# nohelper-*.txt, nohelper-*.ndjson and nohelper-summary.txt.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
usage="usage: linux-env-qemu.sh IMAGES_TAR_GZ OUTDIR [--prompt AGENT TEXT] [--cid N] [--setup | --no-helper DEB]"
tar=${1:?$usage}
out=${2:?$usage}
shift 2
cid=218
prompt_agent= prompt_text= setup= nohelper_deb=
while [ $# -gt 0 ]; do
	case $1 in
		--prompt) prompt_agent=$2; prompt_text=$3; shift 3 ;;
		--cid) cid=$2; shift 2 ;;
		--setup) setup=1; shift ;;
		--no-helper) nohelper_deb=$(cd "$(dirname "$2")" && pwd)/$(basename "$2"); shift 2 ;;
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
qemu=(qemu-system-x86_64 -enable-kvm -cpu host -smp 4 -m 4096 -nographic -no-reboot
	-kernel /g/vmlinuz -initrd /g/initrd.img -append "$params"
	-drive file=/g/disk.img,if=virtio,format=raw -drive file=/g/cidata.iso,if=virtio,format=raw,readonly=on
	-device vhost-vsock-pci,guest-cid="$cid" -netdev user,id=n0 -device virtio-net-pci,netdev=n0
	-chardev socket,id=s0,host=127.0.0.1,port=$serial_port,server=on,wait=off,logfile=/g/console.log
	-serial chardev:s0 -monitor none -display none)
if [ -z "$nohelper_deb" ]; then
	docker run -d --name "$name" --network host --device /dev/kvm --device /dev/vhost-vsock -v "$g:/g" anybook-qemu \
		"${qemu[@]}" >/dev/null
else
	# The person's shared storage, as the Terminal app gives it: virtiofs, tag "android", which the guest mounts at
	# /mnt/shared. virtiofsd runs beside QEMU in anybook-qemu-vfs (tools/Dockerfile.qemu-vfs, built once), as this
	# host's user, who owns the folder: as root in the container it can't set its capabilities.
	docker image inspect anybook-qemu-vfs >/dev/null 2>&1 ||
		docker build -q -t anybook-qemu-vfs -f "$repo/tools/Dockerfile.qemu-vfs" "$repo/tools" >/dev/null
	mkdir -p "$g/shared/Download"
	docker run -d --name "$name" --network host --device /dev/kvm --device /dev/vhost-vsock -v "$g:/g" anybook-qemu-vfs \
		sh -c 'setpriv --reuid=$0 --regid=$0 --clear-groups /usr/lib/virtiofsd --socket-path=/g/vfs.sock --shared-dir=/g/shared --sandbox=none \
			--announce-submounts > /g/virtiofsd.log 2>&1 & for i in $(seq 1 50); do [ -S /g/vfs.sock ] && break; sleep 0.1; done; exec "$@"' \
		"$(id -u)" "${qemu[@]}" -object memory-backend-memfd,id=mem,size=4096M,share=on -numa node,memdev=mem \
		-chardev socket,id=vfs,path=/g/vfs.sock -device vhost-user-fs-pci,chardev=vfs,tag=android >/dev/null
fi

if [ -n "$nohelper_deb" ]; then
	sum=$out/nohelper-summary.txt
	: > "$sum"
	pass=0 fail=0
	check() { # NAME CONDITION...: records PASS or FAIL
		local name=$1; shift
		if "$@"; then echo "PASS $name" | tee -a "$sum"; pass=$((pass + 1)); else echo "FAIL $name" | tee -a "$sum"; fail=$((fail + 1)); fi
	}
	gsh() { python3 "$repo/scripts/quire/serial-shell.py" 127.0.0.1 "$serial_port" droid droid "$@"; }
	# The guest is up once the serial console takes droid's login (cloud-init made the user).
	up=
	for _ in $(seq 1 60); do
		if gsh 'cat /etc/debian_version' > "$out/nohelper-login.txt" 2>&1; then up=$(date +%s.%N); break; fi
		sleep 3
	done
	cp "$g/console.log" "$out/console.log" 2>/dev/null || true
	check "the guest boots and droid logs in on the serial console" test -n "$up"
	[ -n "$up" ] || { echo "no-helper checks: $pass passed, $fail failed" | tee -a "$sum"; exit 1; }
	awk -v a="$t0" -v b="$up" 'BEGIN { printf "qemu start -> serial login: %.1f s\n", b - a }' | tee "$out/timings.txt"

	# (a) What Quire meets: an image that isn't OpenBook's, and nothing on vsock 7690.
	tar -xzOf "$tar" build_id > "$out/nohelper-build_id.txt"
	echo "build_id: $(cat "$out/nohelper-build_id.txt")" | tee -a "$sum"
	check "the image isn't OpenBook's (build_id)" bash -c '! grep -q "^openbook_" "$1"' _ "$out/nohelper-build_id.txt"
	sleep 20  # systemd has started whatever it starts by now
	"$quired" agents --connect "vsock:$cid:7690" > "$out/nohelper-7690-before.txt" 2>&1 && rc=0 || rc=$?
	check "nothing answers on vsock 7690 (exit $rc)" test "$rc" -ne 0
	key=keep-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')
	gsh 'cat /etc/os-release | head -3' 'systemctl --version | head -1' 'command -v quired; echo quired-present=$?' \
		'systemctl is-enabled quired.service 2>&1; true' "printf '%s\\n' $key > ~/keep-me.txt && sha256sum ~/keep-me.txt" \
		'command -v curl wget python3' > "$out/nohelper-guest-before.txt" 2>&1 || true
	check "no quired in the guest" grep -q 'quired-present=1' "$out/nohelper-guest-before.txt"

	# (b) Downloads as the guest sees it, filled from this host: a tampered copy first, then the real one.
	# A field of DEB's control file: dpkg-deb where there is one, else bsdtar (the host may not be Debian's).
	deb_field() {
		if command -v dpkg-deb >/dev/null; then dpkg-deb -f "$nohelper_deb" "$1"; else
			bsdtar -xOf "$nohelper_deb" 'control.tar.*' | bsdtar -xOf - ./control | sed -n "s/^$1: //p"; fi
	}
	version=$(deb_field Version)
	debname=$(deb_field Package)_${version}_$(deb_field Architecture).deb
	sha=$(sha256sum "$nohelper_deb" | cut -d' ' -f1)
	# SetupModel.helperCommand, character for character.
	cmd="cp /mnt/shared/Download/$debname /tmp/ && echo \"$sha  /tmp/$debname\" | sha256sum -c && sudo dpkg -i /tmp/$debname"
	printf '%s\n' "$cmd" > "$out/nohelper-command.txt"
	srv=$work/nohelper-srv
	rm -rf "$srv"
	mkdir -p "$srv/good" "$srv/bad"
	cp "$nohelper_deb" "$srv/good/$debname"
	{ cat "$nohelper_deb"; printf 'x'; } > "$srv/bad/$debname"
	# What Quire core does on Android: the package in Downloads, which the guest sees through the share.
	fetch() { cp "$srv/$1/$debname" "$g/shared/Download/$debname" && echo "ls -l /mnt/shared/Download/ && echo fetched-$1"; }
	gsh "$(fetch bad)" "$cmd; echo command=\$?" 'command -v quired; echo quired-present=$?' \
		> "$out/nohelper-tampered.txt" 2>&1 || true
	check "the tampered copy reached Downloads" grep -q 'fetched-bad' "$out/nohelper-tampered.txt"
	check "the command refuses the tampered copy (sha256sum FAILED)" grep -q 'FAILED' "$out/nohelper-tampered.txt"
	check "the command stops before dpkg on the tampered copy" grep -Eq 'command=[1-9]' "$out/nohelper-tampered.txt"
	check "nothing was installed from the tampered copy" grep -q 'quired-present=1' "$out/nohelper-tampered.txt"
	t1=$(date +%s.%N)
	gsh "$(fetch good)" "$cmd; echo command=\$?" > "$out/nohelper-install.txt" 2>&1 || true
	check "the real copy reached Downloads" grep -q 'fetched-good' "$out/nohelper-install.txt"
	check "sha256sum accepts the real copy" grep -q ": OK" "$out/nohelper-install.txt"
	check "the command installs quired (exit 0)" grep -q 'command=0' "$out/nohelper-install.txt"

	# (c) Quire's side, from this host as Android: quired answers with the setup catalog, and the
	# admin worker's socket unit works on this image's systemd.
	ans=
	for _ in $(seq 1 30); do
		if "$quired" setup --connect "vsock:$cid:7690" _quire/catalog > "$out/nohelper-catalog.ndjson" 2>&1; then ans=$(date +%s.%N); break; fi
		sleep 1
	done
	[ -z "$ans" ] || awk -v a="$t1" -v b="$ans" 'BEGIN { printf "command -> quired answering the catalog: %.1f s\n", b - a }' | tee -a "$out/timings.txt"
	check "quired answers the setup catalog on vsock 7690, as $version" grep -q "\"quired\":\"$version\"" "$out/nohelper-catalog.ndjson"
	"$quired" admin call --connect "vsock:$cid:7691" version > "$out/nohelper-admin.ndjson" 2>&1 || true
	check "the admin worker answers on vsock 7691" grep -q '"version":"' "$out/nohelper-admin.ndjson"
	gsh 'systemctl is-active quired.service quire-admin.socket' 'dpkg-query -W quired' 'sha256sum ~/keep-me.txt' \
		'journalctl -u quired.service -b --no-pager -o short-monotonic | tail -15' \
		> "$out/nohelper-guest-after.txt" 2>&1 || true
	check "quired.service and quire-admin.socket are active" bash -c '[ "$(grep -cx active "$1")" -ge 2 ]' _ "$out/nohelper-guest-after.txt"
	keysha=$(printf '%s\n' "$key" | sha256sum | cut -d' ' -f1)
	check "the person's file is still there, unchanged" grep -q "$keysha  /home/droid/keep-me.txt" "$out/nohelper-guest-after.txt"
	cp "$g/console.log" "$out/console.log"
	echo "no-helper checks: $pass passed, $fail failed" | tee -a "$sum"
	[ "$fail" -eq 0 ]
	exit
fi

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

if [ -n "$setup" ]; then
	sum=$out/setup-summary.txt
	: > "$sum"
	pass=0 fail=0
	check() { # NAME CONDITION...: records PASS or FAIL
		local name=$1; shift
		if "$@"; then echo "PASS $name" | tee -a "$sum"; pass=$((pass + 1)); else echo "FAIL $name" | tee -a "$sum"; fail=$((fail + 1)); fi
	}
	admin() { "$quired" admin call --connect "vsock:$cid:7691" "$@"; }
	serve() { "$quired" setup --connect "vsock:$cid:7690" "$@"; }
	result_has() { grep -q "$2" "$1"; }

	# (a) The worker answers the host, installs a package on its list and refuses one off it.
	admin version > "$out/setup-admin-version.ndjson" 2>&1 || true
	check "worker answers the host on vsock 7691" result_has "$out/setup-admin-version.ndjson" '"version":"'
	admin debian-install '{"packages":["git"]}' > "$out/setup-debian-git.ndjson" 2>&1 || true
	check "worker installs git from Debian" result_has "$out/setup-debian-git.ndjson" '"quired":"result","result"'
	admin debian-install '{"packages":["vim"]}' > "$out/setup-debian-vim.ndjson" 2>&1 || true
	check "worker refuses a package off its list" result_has "$out/setup-debian-vim.ndjson" '"code":-32602'

	# (b) From inside the guest (vsock loopback, CID 1) the worker refuses the connection, and
	# git is there.
	python3 "$repo/scripts/quire/serial-shell.py" 127.0.0.1 "$serial_port" droid droid \
		'sudo modprobe vsock_loopback; quired admin call --connect vsock:1:7691 version; echo loopback=$?' \
		'git --version' \
		'systemctl show -p ActiveEnterTimestampMonotonic -p MainPID quired.service' \
		> "$out/setup-guest-before.txt" 2>&1 || true
	check "worker refuses a guest-local peer (CID 1)" grep -Eq 'loopback=[1-9]' "$out/setup-guest-before.txt"
	check "git is installed in the guest" grep -Eq '(^|\$ )git version' "$out/setup-guest-before.txt"

	# (c) Updates: an older quired is refused; a newer one is installed by its own unit while
	# postinst restarts quired.service, and its result is read on a new connection.
	debs=$work/debs
	rm -rf "$debs"
	mkdir -p "$debs"
	# The newer build is the source's version plus a suffix, so it sorts after an image built from the same tree.
	newer=$(sed -n 's/^var version = "\(.*\)"/\1/p' "$repo/quire/quired/main.go")+setupcheck
	QUIRED_VERSION=0.3.9 "$repo/quire/linux-env/build-deb.sh" "$debs/old" amd64 > /dev/null
	QUIRED_VERSION=$newer "$repo/quire/linux-env/build-deb.sh" "$debs/new" amd64 > /dev/null
	params() { python3 -c 'import base64, hashlib, json, sys; b = open(sys.argv[1], "rb").read(); print(json.dumps({"deb": base64.b64encode(b).decode(), "sha256": hashlib.sha256(b).hexdigest()}))' "$1"; }
	params "$debs/old/"quired_*.deb > "$debs/old.json"
	params "$debs/new/"quired_*.deb > "$debs/new.json"
	admin quired-update "@$debs/old.json" > "$out/setup-update-old.ndjson" 2>&1 || true
	check "worker refuses an older quired" result_has "$out/setup-update-old.ndjson" "isn't newer than the installed"
	admin quired-update "@$debs/new.json" > "$out/setup-update-new.ndjson" 2>&1 || true
	job=$(python3 -c 'import json, sys
for l in open(sys.argv[1]):
    m = json.loads(l)
    if m.get("quired") == "result" and "result" in m: print(m["result"]["job"])' "$out/setup-update-new.ndjson" 2>/dev/null || true)
	check "worker starts the update and names its job" test -n "$job"
	state=
	if [ -n "$job" ]; then
		for _ in $(seq 1 90); do
			admin job "{\"id\":\"$job\"}" > "$out/setup-update-job.ndjson" 2>&1 || true
			state=$(python3 -c 'import json, sys
for l in open(sys.argv[1]):
    m = json.loads(l)
    if m.get("quired") == "result" and "result" in m: print(m["result"]["state"])' "$out/setup-update-job.ndjson" 2>/dev/null || true)
			[ "$state" = running ] || [ -z "$state" ] || break
			sleep 1
		done
	fi
	check "the update's job is done, read on a new connection" test "$state" = done
	ready2=
	for _ in $(seq 1 30); do
		if serve _quire/catalog > "$out/setup-catalog.ndjson" 2>&1; then ready2=1; break; fi
		sleep 1
	done
	check "quired serves again after the update, as $newer" result_has "$out/setup-catalog.ndjson" "\"quired\":\"$newer\""
	python3 "$repo/scripts/quire/serial-shell.py" 127.0.0.1 "$serial_port" droid droid \
		'systemctl show -p ActiveEnterTimestampMonotonic -p MainPID quired.service' \
		'dpkg-query -W quired' \
		'systemctl list-units --all --no-pager "quire-update-*" "quire-admin*"' \
		'sudo journalctl -b --no-pager -o short-monotonic -u quired.service -u quire-admin.socket -u "quire-admin@*" -u "quire-update-*" | tail -60' \
		'echo refused-local=$(sudo journalctl -b --no-pager -u "quire-admin@*" | grep -c "admin: refused vsock:1:")' \
		> "$out/setup-guest-after.txt" 2>&1 || true
	check "the worker's journal shows the CID 1 refusal" grep -Eq 'refused-local=[1-9]' "$out/setup-guest-after.txt"
	before=$(sed -n 's/^ActiveEnterTimestampMonotonic=//p' "$out/setup-guest-before.txt" | head -1)
	after=$(sed -n 's/^ActiveEnterTimestampMonotonic=//p' "$out/setup-guest-after.txt" | head -1)
	check "postinst restarted quired.service during the update" test -n "$before" -a -n "$after" -a "${after:-0}" -gt "${before:-0}"

	# (d) opencode by its recipe: its Debian prerequisites from the worker, then _quire/install,
	# then one prompt through vsock.
	admin debian-install '{"packages":["ca-certificates","curl"]}' > "$out/setup-debian-curl.ndjson" 2>&1 || true
	check "worker provides curl and CA certificates" result_has "$out/setup-debian-curl.ndjson" '"quired":"result","result"'
	t2=$(date +%s.%N)
	serve _quire/install '{"agent":"opencode","job":"qemu-opencode"}' > "$out/setup-install-opencode.ndjson" 2>&1 || true
	awk -v a="$t2" -v b="$(date +%s.%N)" 'BEGIN { printf "_quire/install opencode: %.1f s\n", b - a }' | tee -a "$out/timings.txt"
	check "_quire/install opencode finds it after its recipe" result_has "$out/setup-install-opencode.ndjson" '"result":{"version":"'
	check "_quire/install sent progress" result_has "$out/setup-install-opencode.ndjson" '"method":"_quire/progress"'
	serve _quire/signin '{"agent":"opencode"}' > "$out/setup-signin-opencode.ndjson" 2>&1 || true
	check "opencode needs no sign-in" result_has "$out/setup-signin-opencode.ndjson" '"signedIn":true'
	"$quired" run --connect "vsock:$cid:7690" --approve none --json --timeout 240s opencode "Reply with exactly: QUIRE OK" \
		> "$out/setup-prompt.ndjson" 2> "$out/setup-prompt.stderr" || true
	answer=$(python3 -c 'import json, sys
t = []
for l in open(sys.argv[1]):
    try: m = json.loads(l)
    except ValueError: continue
    u = m.get("params", {}).get("update", {})
    if u.get("sessionUpdate") == "agent_message_chunk": t.append(u.get("content", {}).get("text", ""))
print("".join(t))' "$out/setup-prompt.ndjson")
	echo "opencode answered: $answer" | tee -a "$sum"
	check "opencode answers a prompt through vsock" test -n "$answer"
	echo "setup checks: $pass passed, $fail failed" | tee -a "$sum"
fi
cp "$g/console.log" "$out/console.log"
[ -z "$setup" ] || [ "$fail" -eq 0 ]
