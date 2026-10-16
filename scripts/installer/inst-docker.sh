#!/usr/bin/env bash
# Run a command in the anybook-installer container (tools/Dockerfile.installer), building the image if needed.
# Mounts: ~/anybook read-only (kernel dist, AOSP out/ host tools), ~/anybook/installer and ~/anybook/logs/installer
# writable, this repo read-only, all at their host paths. /dev/kvm is passed in. No disk or USB device is ever
# passed in: everything here works on image files.
#
# usage: inst-docker.sh CMD [ARGS...]
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}; I=$A/installer; L=$A/logs/installer
R=$(cd "$(dirname "$0")/../.." && pwd)
IMG=${ANYBOOK_INSTALLER_IMAGE:-anybook-installer}
mkdir -p "$I" "$L"
docker image inspect "$IMG" >/dev/null 2>&1 || docker build -t "$IMG" -f "$R/tools/Dockerfile.installer" "$R/tools"
TTY=(-i); [ -t 0 ] && TTY=(-it)
exec docker run --rm "${TTY[@]}" -u "$(id -u):$(id -g)" --device /dev/kvm \
  -e HOME="$I/home" -e ANYBOOK_HOME="$A" -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$A:$A:ro" -v "$I:$I" -v "$L:$L" -v "$R:$R:ro" -w "$I" "$IMG" "$@"
