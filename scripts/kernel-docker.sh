#!/usr/bin/env bash
# Run a command inside the anybook-kernel container (tools/Dockerfile.kernel), building the image if needed.
# Mounts ~/anybook/kernel, ~/anybook/logs/kernel and this repo (read-only) at the same paths as on the host,
# so logs and outputs name real host paths. HOME inside is ~/anybook/kernel/home (git/repo/bazel state).
#
# usage: kernel-docker.sh CMD [ARGS...]
# env: KERNEL_DETACH=NAME  run as a detached container named NAME instead, so a long sync/build survives the
#                          calling shell. Collect it with `docker wait NAME; docker rm NAME` (logs are in ~/anybook/logs/kernel).
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}; K=$A/kernel; L=$A/logs/kernel
R=$(cd "$(dirname "$0")/.." && pwd)
IMG=${ANYBOOK_KERNEL_IMAGE:-anybook-kernel}
mkdir -p "$K/home" "$L"
docker image inspect "$IMG" >/dev/null 2>&1 || docker build -t "$IMG" -f "$R/tools/Dockerfile.kernel" "$R/tools"
RUN=(--rm -i); [ -n "${KERNEL_DETACH:-}" ] && RUN=(-d --name "$KERNEL_DETACH")
exec docker run "${RUN[@]}" -u "$(id -u):$(id -g)" \
  -e HOME="$K/home" -e USER="$(id -un)" -e ANYBOOK_HOME="$A" -e ANYBOOK_IN_KERNEL_CONTAINER=1 \
  -e ANYBOOK_KERNEL_JOBS="${ANYBOOK_KERNEL_JOBS:-}" -e BUILD_NUMBER="${BUILD_NUMBER:-}" -e KERNEL_TARGET="${KERNEL_TARGET:-}" -e BAZEL_ARGS="${BAZEL_ARGS:-}" -e BUILD_TIMEOUT="${BUILD_TIMEOUT:-}" \
  -v "$K:$K" -v "$L:$L" -v "$R:$R:ro" -w "$K" "$IMG" "$@"
