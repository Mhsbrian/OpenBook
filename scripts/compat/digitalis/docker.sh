#!/usr/bin/env bash
# Run a command in the anybook-aosp container (tools/Dockerfile.aosp) for the Digitalis tree (ANAL-181).
# Paths are mounted at their host paths, so repo's absolute git alternates work on both sides:
#   ~/anybook/digitalis       read-write (tree, ccache, out/)
#   ~/anybook/aosp/mirror     read-only  (the shared AOSP source mirror from ANAL-167; never written)
#   ~/anybook/logs/digitalis  read-write
#   this repo                 read-only at /repo
# usage: docker.sh [-d NAME] CMD...    (-d: detached as container NAME; `docker wait NAME` blocks on it,
#                                       `docker stop NAME` cancels it)
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}; R=$(cd "$(dirname "$0")/../../.." && pwd)
RUN=(--rm -i)
if [ "${1:-}" = -d ]; then RUN=(--rm -d --name "$2"); shift 2; fi
mkdir -p "$A/digitalis/aosp16" "$A/digitalis/ccache" "$A/logs/digitalis"
docker image inspect anybook-aosp >/dev/null 2>&1 || docker build -t anybook-aosp -f "$R/tools/Dockerfile.aosp" \
  --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" "$R/tools"
# seccomp/systempaths=unconfined: Soong's nsjail sandbox needs them (docs/aosp-build.md). Still non-root.
exec docker run "${RUN[@]}" --init -u "$(id -u):$(id -g)" \
  --security-opt seccomp=unconfined --security-opt systempaths=unconfined \
  -v "$A/digitalis:$A/digitalis" -v "$A/aosp/mirror:$A/aosp/mirror:ro" -v "$A/logs/digitalis:$A/logs/digitalis" \
  -v "$R:/repo:ro" -w "$A/digitalis/aosp16" \
  -e ANYBOOK_HOME="$A" -e DIGITALIS_JOBS -e DIGITALIS_TARGET \
  -e CCACHE_DIR="$A/digitalis/ccache" anybook-aosp "$@"
