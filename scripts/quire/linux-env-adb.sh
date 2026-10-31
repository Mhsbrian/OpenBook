#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The Linux environment (Quire Q4, ANAL-218) on an installed OpenBook, over adb: put the guest image where the Terminal
# app installs from, and run Q4's acceptance check there. Since ANAL-223 the G14 has OpenBook installed and is reached
# with adb over the network (scripts/g14-adb.sh), so no stick is needed; Cuttlefish works the same way.
#
# usage: linux-env-adb.sh [-s SERIAL] COMMAND [ARGS]
#   preflight             read-only facts: a debuggable build (the Terminal app installs a local image only there), AVF
#                         (the feature, crosvm and virtmgr, the Terminal app and whether it is on), KVM (KVM's device,
#                         kvm_amd, ro.boot.hypervisor.vm.supported), whether a Linux environment is installed, and free
#                         space in /data
#   push IMAGE [--replace-installed]
#                         IMAGE (images.tar.gz from scripts/quire/linux-env-image.sh) to /sdcard/linux/images.tar.gz,
#                         where the Terminal app installs from on a debuggable build, then the copy's sha256 on the device
#                         must match IMAGE.sha256 (or IMAGE). Refuses while a Linux environment is installed: the Terminal
#                         app keeps it, and replacing it deletes the guest's files, which is the person's choice (Terminal
#                         > Settings > Recovery). --replace-installed does that here: it clears the Terminal app's data
#                         (pm clear), the installed guest included. For test devices
#   check IMAGE OUTDIR [PROMPT] [--replace-installed]
#                         push, then Q4's acceptance on the device as root (scripts/quire/q4-device-check.sh): KVM, AVF,
#                         the person's steps (the Terminal app on, Install), the guest's boot time, the agents in the
#                         guest listed by Quire core, and PROMPT (default "Reply with exactly: QUIRE OK") answered.
#                         Results and logs are pulled into OUTDIR (results.tsv, checks.log, guest-console.log,
#                         terminal.png, logcat-all.txt, selinux-denials.txt)
#
# SERIAL: adb's serial, ADDR:PORT for adb over the network (the G14: its address and port 5555, from
# `scripts/g14-adb.sh find`; a bare address gets port 5555. Cuttlefish from scripts/cf-boot.sh: 127.0.0.1:16520).
# Default: $OPENBOOK_G14_ADDR.
# Env: ADB (default <data dir>/android-sdk/platform-tools/adb, else adb in PATH), ANDROID_ADB_SERVER_PORT (default 5222,
#      the private adb server scripts/g14-adb.sh uses, so other runs' servers are untouched), Q4_WIFI (passed to
#      q4-device-check.sh: an open network to join first; Cuttlefish: VirtWifi. On a laptop its Wi-Fi is already on).
# Writes on the device: /sdcard/linux/images.tar.gz; for check also /data/local/tmp/openbook-q4/ (the check and its
# results), and what q4-device-check.sh does (turns the Terminal app on, grants it the permissions a person grants at its
# first start, installs and starts the Linux environment). adbd is made root for the checks and put back afterwards if
# this run made it root. Nothing reboots, flashes or remounts.
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
ADB=${ADB:-$A/android-sdk/platform-tools/adb}
[ -x "$ADB" ] || ADB=$(command -v adb) || { echo "no adb (set ADB=)" >&2; exit 2; }
export ANDROID_ADB_SERVER_PORT=${ANDROID_ADB_SERVER_PORT:-5222}
SERIAL=${OPENBOOK_G14_ADDR:-}
[ "${1:-}" = -s ] && { SERIAL=$2; shift 2; }
usage="usage: linux-env-adb.sh [-s SERIAL] preflight | push IMAGE [--replace-installed] | check IMAGE OUTDIR [PROMPT] [--replace-installed]"
CMD=${1:?$usage}; shift
[ -n "$SERIAL" ] || { echo "no device: pass -s SERIAL or set OPENBOOK_G14_ADDR" >&2; exit 2; }
# An address without a port is adbd's network port, as in g14-adb.sh.
case $SERIAL in *:*) ;; [0-9]*.[0-9]*.[0-9]*.[0-9]*) SERIAL=$SERIAL:5555 ;; esac
T=com.android.virtualization.terminal
DEST=/sdcard/linux/images.tar.gz
D=/data/local/tmp/openbook-q4
die() { echo "linux-env-adb: $*" >&2; exit 1; }
a() { "$ADB" -s "$SERIAL" "$@"; }
sh_() { a shell "$@" | tr -d '\r'; }

# adb over the network loses its transport when adbd restarts (adb root) or Wi-Fi sleeps: connect again.
connect() {
	case $SERIAL in
		*:*)
			for _ in 1 2 3 4 5; do
				"$ADB" disconnect "$SERIAL" > /dev/null 2>&1 || true
				timeout 20 "$ADB" connect "$SERIAL" > /dev/null 2>&1 || true
				[ "$(timeout 20 "$ADB" -s "$SERIAL" get-state 2>/dev/null)" = device ] && return 0
				sleep 3
			done
			die "can't reach $SERIAL with adb (adb server port $ANDROID_ADB_SERVER_PORT)" ;;
		*) timeout 60 "$ADB" -s "$SERIAL" wait-for-device || die "no device $SERIAL" ;;
	esac
}
ROOTED=0
become_root() {
	[ "$(sh_ id -u)" = 0 ] && return 0
	a root > /dev/null 2>&1 || true
	sleep 3
	connect
	[ "$(sh_ id -u)" = 0 ] || die "adbd can't run as root on $SERIAL (a user build?); the Terminal app installs a local image only on a debuggable build"
	ROOTED=1
}
unroot() { [ $ROOTED = 1 ] || return 0; a unroot > /dev/null 2>&1 || true; sleep 3; connect; }
trap unroot EXIT

installed() { [ "$(sh_ "[ -e /data/user/0/$T/files/linux/completed ] && echo yes")" = yes ]; }

preflight() {
	local fail=0 v
	row() { printf '%-34s %s\n' "$1" "$2"; }
	v=$(sh_ getprop ro.debuggable)
	row "build" "$(sh_ getprop ro.build.fingerprint)"
	row "debuggable" "$v"
	[ "$v" = 1 ] || { echo "  the Terminal app installs a local image only on a debuggable build"; fail=1; }
	if sh_ pm list features | grep -q virtualization_framework; then v=yes; else v=no; fail=1; fi
	row "AVF feature" "$v"
	v=$(sh_ ls /apex/com.android.virt/bin 2>/dev/null | grep -E -x 'crosvm|virtmgr' | tr '\n' ' ') || true
	row "crosvm, virtmgr" "${v:-missing}"
	case $v in *crosvm*virtmgr*|*virtmgr*crosvm*) ;; *) fail=1 ;; esac
	if [ -n "$(sh_ pm path $T)" ]; then
		if sh_ pm list packages -d $T | grep -q "$T\$"; then v="installed, off"; else v="installed, on"; fi
	else
		v=missing; fail=1
	fi
	row "Terminal app" "$v"
	row "KVM's device (sysfs)" "$(sh_ cat /sys/devices/virtual/misc/kvm/dev 2>/dev/null || echo missing)"
	row "kvm_amd (npt, nested)" "$(sh_ "cat /sys/module/kvm_amd/parameters/npt /sys/module/kvm_amd/parameters/nested 2>/dev/null | tr '\n' ' '" || true)"
	v=$(sh_ getprop ro.boot.hypervisor.vm.supported)
	row "ro.boot.hypervisor.vm.supported" "${v:-unset}"
	[ "$v" = 1 ] || echo "  no KVM: the Linux environment can't start here; Quire says so and names a paired computer"
	if installed; then v="yes (files/linux/completed)"; else v=no; fi
	row "Linux environment installed" "$v"
	row "free in /data" "$(sh_ df -k /data | awk 'NR == 2 {printf "%.1f GiB", $4 / 1048576}')"
	return $fail
}

push() {
	local img=$1 replace=$2 want got size free
	[ -f "$img" ] || die "no image $img"
	if [ -f "$img.sha256" ]; then want=$(cut -d' ' -f1 "$img.sha256"); else want=$(sha256sum "$img" | cut -d' ' -f1); fi
	[ "$(sh_ getprop ro.debuggable)" = 1 ] || die "not a debuggable build: the Terminal app would not install a local image"
	[ -n "$(sh_ pm path $T)" ] || die "no Terminal app: the image has no AVF (device/anybook/common/linux-env/linux-env.mk)"
	if installed; then
		[ "$replace" = 1 ] || die "a Linux environment is already installed and the Terminal app keeps it. Replacing it deletes the guest's files: the person does that in Terminal > Settings > Recovery, or pass --replace-installed (pm clear $T)"
		echo "replacing the installed Linux environment: pm clear $T (the guest's files are deleted)"
		sh_ am force-stop $T
		sh_ pm clear $T
	fi
	# The archive, and the Terminal app unpacking it (root_part is about 3 GiB), with 1 GiB to spare.
	size=$(stat -c %s "$img")
	free=$(sh_ df -k /data | awk 'NR == 2 {print $4 * 1024}')
	[ "$free" -gt $((size + 4 * 1024 * 1024 * 1024)) ] || die "only $((free / 1048576)) MiB free in /data; need $(((size >> 20) + 4096)) MiB"
	sh_ mkdir -p /sdcard/linux
	echo "pushing $(basename "$img") ($((size >> 20)) MiB) to $SERIAL:$DEST"
	a push "$img" "$DEST"
	got=$(sh_ sha256sum "$DEST" | cut -d' ' -f1)
	[ "$got" = "$want" ] || die "sha256 on the device $got, want $want"
	echo "$DEST: sha256 $got matches"
}

case $CMD in
preflight)
	connect; become_root; preflight ;;
push | check)
	img=${1:?$usage}; shift
	out= prompt="Reply with exactly: QUIRE OK" replace=0 n=0
	for x; do
		case $x in
			--replace-installed) replace=1 ;;
			-*) die "unknown option $x" ;;
			*) n=$((n + 1)); if [ $n = 1 ]; then out=$x; else prompt=$x; fi ;;
		esac
	done
	[ "$CMD" = push ] && [ $n -gt 0 ] && die "$usage"
	[ "$CMD" = check ] && [ -z "$out" ] && die "$usage"
	case $prompt in *\'*) die "PROMPT may not contain a single quote" ;; esac
	connect; become_root
	if [ "$CMD" = push ]; then
		push "$img" $replace
		echo "next, the person's steps: Settings > System > Developer options > Linux development environment on, then Terminal > Install"
		exit 0
	fi
	mkdir -p "$out"
	{ preflight || true; } | tee "$out/preflight.txt"
	push "$img" $replace
	sh_ "rm -rf $D && mkdir -p $D"
	a push "$R/scripts/quire/q4-device-check.sh" "$D/" > /dev/null
	# Run it detached on the device, so a dropped network adb doesn't stop it; poll for its exit status.
	echo "q4-device-check.sh on $SERIAL (install, boot, agents, prompt: about 5 minutes)"
	wifi=${Q4_WIFI:+Q4_WIFI=$Q4_WIFI }
	sh_ "cd $D && nohup sh -c '${wifi}sh q4-device-check.sh $DEST $D/out \"\$0\" > $D/run.log 2>&1; echo \$? > $D/exit' '$prompt' > /dev/null 2>&1 &"
	t0=$(date +%s) st=
	while [ $(($(date +%s) - t0)) -lt 1800 ]; do
		sleep 10
		st=$(sh_ "cat $D/exit 2>/dev/null; true" 2>/dev/null) || { connect; continue; }
		[ -n "$st" ] && break
	done
	[ -n "$st" ] || echo "q4-device-check.sh still running after 30 min; pulling what it has" >&2
	a pull "$D/out/." "$out/" > /dev/null
	a pull "$D/run.log" "$out/device-run.log" > /dev/null || true
	cat "$out/results.tsv"
	echo "results in $out; q4-device-check.sh exit ${st:-none} (its failure count)"
	[ "$st" = 0 ] ;;
*)
	die "$usage" ;;
esac
