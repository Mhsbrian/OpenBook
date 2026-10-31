#!/usr/bin/env bash
# Run a command in the openbook-installer container (tools/Dockerfile.installer), building the image if needed.
# Mounts: the host data dir (~/anybook until the repo-wide rename) read-only (kernel dist, AOSP out/ host tools), ~/anybook/installer and ~/anybook/logs/installer
# writable, this repo read-only, all at their host paths. /dev/kvm is passed in. No disk or USB device is ever
# passed in: everything here works on image files.
#
# usage: inst-docker.sh CMD [ARGS...]
# Env: OPENBOOK_INSTALLER_NET=host  the host's network (the OTA rehearsal's QEMU forwards adb to a port on 127.0.0.1)
#      OPENBOOK_INSTALLER_NAME=NAME the container's name (so a run can stop exactly its own container)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer; L=$A/logs/installer
R=$(cd "$(dirname "$0")/../.." && pwd)
IMG=${OPENBOOK_INSTALLER_IMAGE:-openbook-installer}
mkdir -p "$I" "$L"
docker image inspect "$IMG" >/dev/null 2>&1 || docker build -t "$IMG" -f "$R/tools/Dockerfile.installer" "$R/tools"
TTY=(-i); [ -t 0 ] && TTY=(-it)
[ -z "${OPENBOOK_INSTALLER_NET:-}" ] || TTY+=(--network "$OPENBOOK_INSTALLER_NET")
[ -z "${OPENBOOK_INSTALLER_NAME:-}" ] || TTY+=(--name "$OPENBOOK_INSTALLER_NAME")
exec docker run --rm "${TTY[@]}" -u "$(id -u):$(id -g)" --device /dev/kvm \
  -e HOME="$I/home" -e OPENBOOK_HOME="$A" -e ANYBOOK_HOME="$A" -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$A:$A:ro" -v "$I:$I" -v "$L:$L" -v "$R:$R:ro" -w "$I" "$IMG" "$@"
