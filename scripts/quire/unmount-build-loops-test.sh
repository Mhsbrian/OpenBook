#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Fixture test for unmount-build-loops.sh: a fake /sys/block and /proc/mounts with this build's loop devices, other
# images with the same file names, and look-alike paths; only this build's automounts may be selected.
# usage: unmount-build-loops-test.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d "${TMPDIR:-/tmp}/unmount-build-loops-test.XXXXXX")
trap 'rm -rf "$T"' EXIT
W=$T/home/me/anybook/quire/linux-env/work
SYS=$T/sys
MOUNTS=$T/mounts
: > "$MOUNTS"

# loop N BACKING_FILE [DEV MOUNTPOINT]...: a loop device, and mounts of it or its partitions
loop() {
	mkdir -p "$SYS/block/loop$1/loop"
	printf '%s\n' "$2" > "$SYS/block/loop$1/loop/backing_file"
	shift 2
	while [ $# -gt 1 ]; do
		printf '%s %s ext4 rw,nosuid,nodev 0 0\n' "$1" "$2" >> "$MOUNTS"
		shift 2
	done
}
mkdir -p "$SYS/block/loop9"                                    # detached: no backing file
loop 0 "$W/root_part" /dev/loop0 /run/media/me/rootfs                      # ours
loop 1 "$W/debian_cloud_image/disk.raw" /dev/loop1p1 /run/media/me/disk1   # ours, a partition
loop 2 "$W/root_part (deleted)" /dev/loop2 /run/media/me/rootfs1           # ours, removed meanwhile
loop 3 /some/other/project/root_part /dev/loop3 /run/media/me/a
loop 4 /some/other/project/disk.raw /dev/loop4p1 /run/media/me/b
loop 5 "/some/other/project/root_part (deleted)" /dev/loop5 /run/media/me/c
loop 6 /tmp/tmp.Ab12/debian_cloud_image/disk.raw /dev/loop6p1 /run/media/me/d  # another build, no -W
loop 7 "$W/other.img" /dev/loop7 /run/media/me/e                           # in WORKDIR, not the builder's
loop 8 "${W}2/root_part" /dev/loop8 /run/media/me/f                        # WORKDIR is a prefix of its folder
loop 10 /some/other/normal.img /dev/loop10 /run/media/me/g                 # /dev/loop1's prefix
loop 11 "$W/root_part" /dev/loop11 /mnt/manual /dev/loop11p2 /run/media/me/h  # ours: only the automount
loop 12 "$W/debian_cloud_image/disk.raw.bak" /dev/loop12 /run/media/me/i

fails=0
want="would unmount /dev/loop0 (/run/media/me/rootfs; backing $W/root_part)
would unmount /dev/loop1p1 (/run/media/me/disk1; backing $W/debian_cloud_image/disk.raw)
would unmount /dev/loop11p2 (/run/media/me/h; backing $W/root_part)
would unmount /dev/loop2 (/run/media/me/rootfs1; backing $W/root_part (deleted))"
want=$(echo "$want" | LC_ALL=C sort)
got=$(SYS=$SYS MOUNTS=$MOUNTS bash "$HERE/unmount-build-loops.sh" "$W/" --once --dry-run | LC_ALL=C sort)
if [ "$got" = "$want" ]; then
	echo "PASS only this build's automounts selected (4 of 12 mounted loop devices)"
else
	echo "FAIL selection"; diff <(echo "$want") <(echo "$got"); fails=$((fails + 1))
fi
# Another build's work folder selects nothing here.
got=$(SYS=$SYS MOUNTS=$MOUNTS bash "$HERE/unmount-build-loops.sh" "$T/elsewhere" --once --dry-run)
if [ -z "$got" ]; then echo "PASS another work folder selects nothing"; else echo "FAIL another work folder: $got"; fails=$((fails + 1)); fi
for bad in "" relative /; do
	if SYS=$SYS MOUNTS=$MOUNTS bash "$HERE/unmount-build-loops.sh" "$bad" --once --dry-run > /dev/null 2>&1; then
		echo "FAIL WORKDIR '$bad' accepted"; fails=$((fails + 1))
	else
		echo "PASS WORKDIR '$bad' refused"
	fi
done
echo "$fails failure(s)"
exit $fails
