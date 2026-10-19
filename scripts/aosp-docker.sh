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
#
# The AOSP lane (ANAL-176): lanes share ~/anybook/aosp/src and its out/, so aosp-build.sh and aosp-sync.sh (or any
# command, with ANYBOOK_LANE=1) run under the lane lock <data dir>/aosp/.lane.lock. It is taken here before the
# container starts and kept until the container exits: by docker run itself, or with -d by a `docker wait` in the
# background. Someone else holding it is waited for, up to ANYBOOK_LANE_WAIT seconds (default 4 h). A caller that holds
# it already is not waited for: an ancestor process that locked it (`flock <lock> sh -c 'aosp-docker.sh ...'`, found in
# /proc/locks), or ANYBOOK_LANE_LOCK_HELD=1 for a lock held through an inherited fd. Such a caller has to keep it until
# the container exits (with -d: `&& docker wait NAME` inside its flock). The container gets a token that
# is also written to <data dir>/aosp/.lane.owner, so aosp-build.sh can tell its own lane lock from someone else's.
# ANYBOOK_LANE_UNLOCKED=1: no lane at all (a tree of your own).
# BUILD_NUMBER is passed through: a build meant as an update needs its own (it is in the fingerprint), see g14-adb.sh ota.
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}; R=$(cd "$(dirname "$0")/.." && pwd)
RUN=(--rm -i); NAME=
if [ "${1:-}" = -d ]; then NAME=$2; RUN=(--rm -d --name "$2"); shift 2; fi
mkdir -p "$A/aosp" "$A/ccache" "$A/logs/aosp"

LOCK=$A/aosp/.lane.lock; LANE=()
held_by_ancestor() {  # /proc/locks: "N: FLOCK ADVISORY WRITE <pid> <maj:min:inode> ..." (btrfs: match the inode only)
  local ino pid p
  ino=$(stat -c %i "$LOCK")
  for pid in $(awk -v ino="$ino" '$2 == "FLOCK" { n = split($6, f, ":"); if (f[n] == ino) print $5 }' /proc/locks); do
    p=$$
    while [ -n "$p" ] && [ "$p" -gt 1 ]; do
      [ "$p" = "$pid" ] && return 0
      p=$(awk '/^PPid:/ { print $2 }' "/proc/$p/status" 2>/dev/null || true)
    done
  done
  return 1
}
case "${ANYBOOK_LANE_UNLOCKED:-0}:${ANYBOOK_LANE:-0}:${1:-}" in
  1:*) ;;
  *:1:* | *:*/aosp-build.sh | *:*/aosp-sync.sh)
    exec {LFD}>>"$LOCK"  # a new fd: a lock the caller passes in on some fd must stay open
    if [ "${ANYBOOK_LANE_LOCK_HELD:-0}" = 1 ] || held_by_ancestor; then
      echo "aosp-docker.sh: the caller holds the AOSP lane lock" >&2
    elif ! flock -n "$LFD"; then
      echo "aosp-docker.sh: waiting for the AOSP lane lock ($LOCK), held by another process" >&2
      flock -w "${ANYBOOK_LANE_WAIT:-14400}" "$LFD" ||
        { echo "aosp-docker.sh: no AOSP lane lock after ${ANYBOOK_LANE_WAIT:-14400} s" >&2; exit 1; }
    fi
    T=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
    printf '%s\n' "$T" > "$LOCK.owner.$$" && mv -f "$LOCK.owner.$$" "$A/aosp/.lane.owner"
    LANE=(-e ANYBOOK_LANE_TOKEN="$T")
    ;;
esac
docker image inspect anybook-aosp >/dev/null 2>&1 || docker build -t anybook-aosp -f "$R/tools/Dockerfile.aosp" \
  --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" "$R/tools"
# Soong runs the build inside nsjail. nsjail needs seccomp=unconfined (to clone user/mount/pid namespaces) and
# systempaths=unconfined (procfs can't be mounted under Docker's masked /proc). Without both, Soong prints
# "Build sandboxing disabled due to nsjail error" and builds unsandboxed. Still non-root, no added capabilities.
C=(docker run "${RUN[@]}" --init -u "$(id -u):$(id -g)"
  --security-opt seccomp=unconfined --security-opt systempaths=unconfined
  -v "$A/aosp:/aosp" -v "$A/ccache:/ccache" -v "$A/logs/aosp:/logs" -v "$R:/repo:ro"
  -e AOSP_JOBS -e AOSP_BRANCH -e AOSP_TARGET -e ANYBOOK_LANE_UNLOCKED -e BUILD_NUMBER "${LANE[@]}"
  -e ANYBOOK_REV="$(git -C "$R" describe --always --dirty 2>/dev/null || echo unknown)" anybook-aosp "$@")
[ -n "$NAME" ] || exec "${C[@]}"  # the lane lock's fd stays open in docker run until the container exits
"${C[@]}"
# Detached: a `docker wait` in its own session keeps the lock's fd, so the lane lock lasts until the container exits.
[ ${#LANE[@]} -eq 0 ] || setsid docker wait "$NAME" >/dev/null 2>&1 </dev/null &
