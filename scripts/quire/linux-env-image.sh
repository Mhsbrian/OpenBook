#!/usr/bin/env bash
# Build the Linux environment's Debian image (the AVF Terminal's guest) for OpenBook.
#
#   scripts/quire/linux-env-image.sh OUTDIR [--arch x86_64|aarch64] [--test-agent opencode]
#
# It runs AOSP's own builder, packages/modules/Virtualization/build/debian/build.sh, from our
# pinned tree, with quire/linux-env/image/build-debian.patch applied to a copy:
#   - the guest boots Debian's own kernel and initrd from the image, instead of a kernel
#     downloaded from Google's CI;
#   - quired (quire/linux-env/build-deb.sh) is installed and enabled, and socat (which AOSP's
#     ttyd bridge needs) is added.
# Nothing is downloaded from Google: the base is Debian's genericcloud image (checksummed by
# AOSP's script), and ttyd and its libraries are built from their upstream sources.
#
# --test-agent opencode puts a pinned, checksummed opencode release (MIT) in /usr/local/bin, so a
# test can show an agent answering. A product image ships no agent.
#
# Needs Docker with --privileged (the builder uses loop devices) and about 10 GB in WORK.
# Output: OUTDIR/images.tar.gz, ready for /sdcard/linux/images.tar.gz on a debuggable build,
# with its sha256, kernel version and kernel config beside it.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
AOSP=${AOSP:-$HOME/anybook/aosp/src}
WORK=${WORK:-$HOME/anybook/quire/linux-env}
out=${1:?usage: linux-env-image.sh OUTDIR [--arch x86_64|aarch64] [--test-agent opencode]}
shift
arch=x86_64
agent=
while [ $# -gt 0 ]; do
	case $1 in
		--arch) arch=$2; shift 2 ;;
		--test-agent) agent=$2; shift 2 ;;
		*) echo "unknown option $1" >&2; exit 2 ;;
	esac
done
case $arch in x86_64) debarch=amd64 ;; aarch64) debarch=arm64 ;; *) echo "bad arch $arch" >&2; exit 2 ;; esac
mkdir -p "$out"
out=$(cd "$out" && pwd)

# Pinned test agents: name, URL, sha256 (from the release's own digest).
declare -A AGENT_URL=(
	[opencode-x86_64]=https://github.com/anomalyco/opencode/releases/download/v1.19.3/opencode-linux-x64.tar.gz
)
declare -A AGENT_SHA=(
	[opencode-x86_64]=13a8fb2978302071b86f9d7e00da9c8895f9cd846978379c3bdc6a5333536c9b
)

src=$WORK/src/Virtualization
# The builder runs as root in its container, so some leftovers are root's.
rm -rf "$src" 2>/dev/null || docker run --rm -v "$WORK:/w" debian:trixie-slim rm -rf /w/src/Virtualization
mkdir -p "$src/build"
cp -a "$AOSP/packages/modules/Virtualization/build/debian" "$src/build/"
virt_head=$(git -C "$AOSP/packages/modules/Virtualization" rev-parse --short=12 HEAD)
patch -d "$src" -p1 --no-backup-if-mismatch < "$repo/quire/linux-env/image/build-debian.patch"

deb=$("$repo/quire/linux-env/build-deb.sh" "$src/build/debian/localdebs" "$debarch" | tail -1)
: > "$src/build/debian/openbook-agents"
if [ -n "$agent" ]; then
	key=$agent-$arch
	[ -n "${AGENT_URL[$key]:-}" ] || { echo "no pinned test agent $key" >&2; exit 2; }
	echo "$agent ${AGENT_URL[$key]} ${AGENT_SHA[$key]}" > "$src/build/debian/openbook-agents"
fi

# AOSP's InstalledImage parses build_id as TARGET-NUMBER-DATE; a number of 5106 or more selects
# ttyd over vsock.
build_id="openbook_${arch}-$(date -u +%y%m%d%H)-$(date -u +'%a %b %d %H:%M:%S %Z %Y')"
log=$out/build.log
echo "Virtualization $virt_head, build_id '$build_id', test agent '${agent:-none}'" | tee "$log"

# A desktop automounter (udiskie, GNOME's) mounts the builder's loop devices on the host, which
# keeps them attached after the builder unmounts them. While the build runs, unmount the build's
# own loop devices (backing file root_part or disk.raw) and nothing else.
unmount_build_loops() {
	while :; do
		for b in /sys/block/loop*; do
			f=$(cat "$b/loop/backing_file" 2>/dev/null) || continue
			case $f in */root_part|*/root_part" (deleted)"|*/disk.raw|*/disk.raw" (deleted)") ;; *) continue ;; esac
			for dev in "/dev/${b##*/}" "/dev/${b##*/}"p*; do
				[ -e "$dev" ] && grep -q "^$dev /run/media/" /proc/mounts &&
					udisksctl unmount -b "$dev" >> "$log.unmount" 2>&1
			done
		done
		sleep 1
	done
}
watch_pid=
if command -v udisksctl >/dev/null; then
	unmount_build_loops &
	watch_pid=$!
fi
trap '[ -z "$watch_pid" ] || kill "$watch_pid" 2>/dev/null' EXIT
(cd "$src/build/debian" && ./build.sh -a "$arch" -b "$build_id" -t "$src") 2>&1 | tee -a "$log"

mv "$src/build/debian/images.tar.gz" "$out/images.tar.gz"
mv "$src/build/debian/kernel_version" "$src/build/debian/kernel_config" "$out/"
(cd "$out" && sha256sum images.tar.gz > images.tar.gz.sha256)
{
	echo "virtualization=$virt_head"
	echo "build_id=$build_id"
	echo "kernel=$(cat "$out/kernel_version")"
	echo "quired_deb=$(basename "$deb") $(sha256sum "$deb" | cut -d' ' -f1)"
	echo "test_agent=${agent:-none}"
	echo "images.tar.gz=$(cut -d' ' -f1 "$out/images.tar.gz.sha256") $(stat -c %s "$out/images.tar.gz") bytes"
	for opt in CONFIG_VIRTIO_VSOCKETS CONFIG_VIRTIO_FS CONFIG_VIRTIO_BLK CONFIG_VIRTIO_NET CONFIG_SERIAL_8250 CONFIG_DRM_VIRTIO_GPU; do
		grep -E "^$opt=" "$out/kernel_config" || echo "$opt not set"
	done
} | tee "$out/image-info.txt"
