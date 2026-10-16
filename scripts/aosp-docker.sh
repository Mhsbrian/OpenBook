#!/usr/bin/env bash
# Run a command in the anybook-aosp container (Ubuntu 24.04, tools/Dockerfile.aosp) as the host uid/gid.
# Mounts: ~/anybook/aosp -> /aosp, ~/anybook/ccache -> /ccache, ~/anybook/logs/aosp -> /logs, this repo -> /repo (ro).
# Builds the image on first use.
#
# usage: aosp-docker.sh [-d NAME] CMD...
#   -d NAME  run detached as container NAME. `docker wait NAME` blocks until it exits, `docker logs NAME`
#            shows output, `docker stop NAME` cancels it. Use this for multi-hour syncs: one git fetch of a
#            multi-GB pack can't resume after a kill, so wrapping `repo sync` in a short `timeout` never finishes.
# e.g.   scripts/aosp-docker.sh /repo/scripts/aosp-sync.sh all
#        scripts/aosp-docker.sh -d anybook-aosp-sync /repo/scripts/aosp-sync.sh all && docker wait anybook-aosp-sync
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}; R=$(cd "$(dirname "$0")/.." && pwd)
RUN=(--rm -i)
if [ "${1:-}" = -d ]; then RUN=(--rm -d --name "$2"); shift 2; fi
mkdir -p "$A/aosp" "$A/ccache" "$A/logs/aosp"
docker image inspect anybook-aosp >/dev/null 2>&1 || docker build -t anybook-aosp -f "$R/tools/Dockerfile.aosp" \
  --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" "$R/tools"
# Soong runs the build inside nsjail. nsjail needs seccomp=unconfined (to clone user/mount/pid namespaces) and
# systempaths=unconfined (procfs can't be mounted under Docker's masked /proc). Without both, Soong prints
# "Build sandboxing disabled due to nsjail error" and builds unsandboxed. Still non-root, no added capabilities.
exec docker run "${RUN[@]}" --init -u "$(id -u):$(id -g)" \
  --security-opt seccomp=unconfined --security-opt systempaths=unconfined \
  -v "$A/aosp:/aosp" -v "$A/ccache:/ccache" -v "$A/logs/aosp:/logs" -v "$R:/repo:ro" \
  -e AOSP_JOBS -e AOSP_BRANCH -e AOSP_TARGET \
  -e ANYBOOK_REV="$(git -C "$R" describe --always --dirty 2>/dev/null || echo unknown)" anybook-aosp "$@"
