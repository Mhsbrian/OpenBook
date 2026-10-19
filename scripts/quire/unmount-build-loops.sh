#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Undo a desktop automounter's mounts of one Linux environment image build's loop devices, and nothing else.
# scripts/quire/linux-env-image.sh runs it while AOSP's builder runs.
#
#   unmount-build-loops.sh WORKDIR [--once] [--dry-run]
#
# A desktop automounter (udiskie, GNOME's) mounts the builder's loop devices on the host, which keeps them attached
# after the builder unmounts them, and the build then fails. A loop device is this build's only if its backing file is
# exactly WORKDIR/root_part or WORKDIR/debian_cloud_image/disk.raw: WORKDIR is the builder's work folder
# (build.sh -W), which linux-env-image.sh makes for each build and mounts at the same path in the builder's container,
# so the host reads the same path in /sys/block/loopN/loop/backing_file. (Without -W the builder works in a mktemp
# folder inside its container, and the host reads that container path, /tmp/tmp.XXXX/..., which can't be told apart
# from the host's own files.) Of those devices and their partitions, only mounts under /run/media/ (the
# automounter's) are unmounted, with udisksctl.
# It checks every second until killed, or once with --once. --dry-run prints what it would unmount instead.
# SYS (default /sys) and MOUNTS (default /proc/mounts) are for unmount-build-loops-test.sh.
set -u
usage="usage: unmount-build-loops.sh WORKDIR [--once] [--dry-run]"
w=${1:?$usage}
shift
once=0
dry=0
for a; do
	case $a in
		--once) once=1 ;;
		--dry-run) dry=1 ;;
		*) echo "$usage" >&2; exit 2 ;;
	esac
done
case $w in /?*) ;; *) echo "WORKDIR must be an absolute path: $w" >&2; exit 2 ;; esac
w=${w%/}
SYS=${SYS:-/sys}
MOUNTS=${MOUNTS:-/proc/mounts}

# ours BACKING_FILE: one of this build's two loop-backed files (the kernel appends " (deleted)" once it is removed).
# Quoted patterns match literally, whatever WORKDIR contains.
ours() {
	case $1 in
		"$w/root_part" | "$w/root_part (deleted)" | \
			"$w/debian_cloud_image/disk.raw" | "$w/debian_cloud_image/disk.raw (deleted)") return 0 ;;
	esac
	return 1
}

while :; do
	for b in "$SYS"/block/loop*; do
		f=$(cat "$b/loop/backing_file" 2>/dev/null) || continue
		ours "$f" || continue
		n=${b##*/}
		while read -r dev mnt _; do
			case $dev in "/dev/$n" | "/dev/${n}p"[0-9]*) ;; *) continue ;; esac
			case $mnt in /run/media/*) ;; *) continue ;; esac
			if [ $dry = 1 ]; then
				echo "would unmount $dev ($mnt; backing $f)"
			else
				echo "$(date +%T) unmount $dev ($mnt; backing $f)"
				udisksctl unmount -b "$dev"
			fi
		done < "$MOUNTS"
	done
	[ $once = 1 ] && break
	sleep 1
done
