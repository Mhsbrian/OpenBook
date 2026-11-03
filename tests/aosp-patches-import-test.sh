#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Fixture test for aosp/patches/*/IMPORT in scripts/aosp-patches.sh (ANAL-356). A scratch tree holds one project at
# its pin; a local "fork" holds the IMPORT commit, and moving the fork away stands in for the build container, which
# can't reach a private fork. Checks that --fetch brings the commit in on the "host", is a no-op once it is there,
# and that the apply step then builds the reproducible import commit without the fork. Then aosp-docker.sh with a fake
# docker: it fetches on the host only under the lane lock, for aosp-patches.sh as for aosp-build.sh. Pure git, a few s.
# usage: aosp-patches-import-test.sh       one line per case, then "N/N passed"; non-zero on any failure
set -uo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
S=$(mktemp -d "${TMPDIR:-/tmp}/aosp-patches-import-test.XXXXXX")
trap 'rm -rf "$S"' EXIT
G=(git -c user.name=test -c user.email=test@example.invalid -c init.defaultBranch=main -c advice.detachedHead=false)
D=packages/apps/Example
pass=0 total=0 out=
ok() {
  total=$((total + 1))
  if [ "$1" = 0 ]; then pass=$((pass + 1)); echo "PASS $2"; else echo "FAIL $2"; tail -n 6 <<<"$out" | sed 's/^/     | /'; fi
}

# The checkout: the script under test, an IMPORT for $D, and a pin manifest naming $D.
mkdir -p "$S/repo/scripts" "$S/repo/aosp/patches/$D" "$S/repo/manifests/aosp"
cp "$R/scripts/aosp-patches.sh" "$R/scripts/aosp-docker.sh" "$S/repo/scripts/"
# Upstream at the pin, and the fork: the pin plus one commit.
"${G[@]}" init -q "$S/upstream"
echo upstream > "$S/upstream/file"; "${G[@]}" -C "$S/upstream" add file; "${G[@]}" -C "$S/upstream" commit -qm pin
PIN=$("${G[@]}" -C "$S/upstream" rev-parse HEAD)
"${G[@]}" clone -q --bare "$S/upstream" "$S/fork.git"
"${G[@]}" clone -q "$S/fork.git" "$S/fork-work"
echo fork > "$S/fork-work/file"; "${G[@]}" -C "$S/fork-work" commit -qam fork; "${G[@]}" -C "$S/fork-work" push -q
REV=$("${G[@]}" -C "$S/fork-work" rev-parse HEAD)
printf 'url file://%s\nrev %s\n' "$S/fork.git" "$REV" > "$S/repo/aosp/patches/$D/IMPORT"
printf '<manifest>\n  <project name="platform/%s" path="%s" revision="%s" upstream="main"/>\n</manifest>\n' \
  "$D" "$D" "$PIN" | gzip > "$S/repo/manifests/aosp/manifest-pinned.xml.gz"
# A fresh tree: the project cloned from upstream and detached at the pin, without the fork's commit.
"${G[@]}" clone -q "$S/upstream" "$S/src/$D"; "${G[@]}" -C "$S/src/$D" checkout -q --detach "$PIN"
patches() { AOSP_SRC=$S/src "$S/repo/scripts/aosp-patches.sh" "$@"; }
has_rev() { git -C "$S/src/$D" cat-file -e "$REV^{commit}" 2>/dev/null; }
hide_fork() { mv "$S/fork.git" "$S/fork.hidden"; }
show_fork() { mv "$S/fork.hidden" "$S/fork.git"; }

# 1. The bug: the tree lacks the commit and the fork can't be reached (the container). The apply step fails, says
#    to fetch on the host, and leaves the project alone.
! has_rev; ok $? "fresh tree lacks the IMPORT commit"
hide_fork
out=$(patches 2>&1); rc=$?
[ $rc != 0 ] && grep -q 'fetch it on the host with scripts/aosp-patches.sh --fetch' <<<"$out" &&
  [ "$(git -C "$S/src/$D" rev-parse HEAD)" = "$PIN" ]
ok $? "apply without the commit or the fork: fails (rc $rc) with the host hint, project untouched"
show_fork
# 2. The fix: --fetch on the host brings the commit in and touches no work tree.
out=$(patches --fetch 2>&1); rc=$?
[ $rc = 0 ] && has_rev && grep -q "fetching ${REV:0:12}" <<<"$out" &&
  [ "$(git -C "$S/src/$D" rev-parse HEAD)" = "$PIN" ] && [ "$(cat "$S/src/$D/file")" = upstream ]
ok $? "--fetch: fetches the missing commit, work tree still on the pin"
# 3. Run again with the fork gone: a no-op that needs no network.
hide_fork
out=$(patches --fetch 2>&1); rc=$?
[ $rc = 0 ] && ! grep -q fetching <<<"$out" && grep -q "has ${REV:0:12}" <<<"$out"
ok $? "--fetch again, fork unreachable: no-op, rc $rc"
# 4. The container's step, still without the fork: the import commit is the fork's tree on the pin, with the
#    script's fixed identity and date, so its SHA is the same in every tree.
out=$(patches 2>&1); rc=$?
head=$(git -C "$S/src/$D" rev-parse HEAD)
[ $rc = 0 ] && [ "$(git -C "$S/src/$D" rev-parse "HEAD^{tree}")" = "$(git -C "$S/src/$D" rev-parse "$REV^{tree}")" ] &&
  [ "$(git -C "$S/src/$D" rev-parse HEAD^)" = "$PIN" ] && [ "$(cat "$S/src/$D/file")" = fork ]
ok $? "apply after --fetch, fork unreachable: HEAD is the import commit on the pin"
"${G[@]}" clone -q "$S/upstream" "$S/src2/$D"; "${G[@]}" -C "$S/src2/$D" fetch -q "$S/src/$D" "$REV"
"${G[@]}" -C "$S/src2/$D" checkout -q --detach "$PIN"
out=$(AOSP_SRC=$S/src2 "$S/repo/scripts/aosp-patches.sh" 2>&1)
[ "$(git -C "$S/src2/$D" rev-parse HEAD)" = "$head" ]; ok $? "import commit is reproducible: same SHA in a second tree"
show_fork
# 5. Errors: a project the tree doesn't have, and an IMPORT without a full SHA.
mkdir -p "$S/repo/aosp/patches/packages/apps/Missing"; cp "$S/repo/aosp/patches/$D/IMPORT" "$S/repo/aosp/patches/packages/apps/Missing/"
out=$(patches --fetch 2>&1); rc=$?
[ $rc != 0 ] && grep -q 'packages/apps/Missing is not a git project; sync the tree first' <<<"$out"
ok $? "--fetch, IMPORT for a project the tree lacks: fails (rc $rc)"
rm -r "$S/repo/aosp/patches/packages/apps/Missing"
printf 'url file://%s\nrev %s\n' "$S/fork.git" "${REV:0:12}" > "$S/repo/aosp/patches/$D/IMPORT"
out=$(patches --fetch 2>&1); rc=$?
[ $rc != 0 ] && grep -q "needs 'url URL' and 'rev <40-hex SHA>'" <<<"$out"
ok $? "--fetch, IMPORT with a short rev: fails (rc $rc)"

printf 'url file://%s\nrev %s\n' "$S/fork.git" "$REV" > "$S/repo/aosp/patches/$D/IMPORT"

# 6. aosp-docker.sh (ANAL-356 review): its host fetch and the container run under the lane lock. A fake docker records
#    each `docker run` and whether the lane lock was held then; a tree of its own ($S/home) lacks the commit again.
mkdir -p "$S/bin" "$S/home/aosp/src/.repo"; LOCK=$S/home/aosp/.lane.lock; : >> "$LOCK"
cat > "$S/bin/docker" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  image) exit 0 ;;
  run) if flock -n "$FAKE_LOCK" true; then echo "run, lock free" >> "$FAKE_LOG"; else echo "run, lock held" >> "$FAKE_LOG"; fi ;;
  *) echo "docker $*" >> "$FAKE_LOG" ;;
esac
EOF
chmod +x "$S/bin/docker"
fresh() {
  rm -rf "${S:?}/home/aosp/src/$D" "${S:?}/docker.log"
  "${G[@]}" clone -q "$S/upstream" "$S/home/aosp/src/$D"; "${G[@]}" -C "$S/home/aosp/src/$D" checkout -q --detach "$PIN"
}
docker_run() { PATH=$S/bin:$PATH FAKE_LOCK=$LOCK FAKE_LOG=$S/docker.log ANYBOOK_HOME=$S/home ANYBOOK_LANE_WAIT=2 \
  "$S/repo/scripts/aosp-docker.sh" "$@"; }
fetched() { git -C "$S/home/aosp/src/$D" cat-file -e "$REV^{commit}" 2>/dev/null; }
HOLDER=
# An unrelated holder. Its sleep gets no stdio, and is killed with it, so it can't keep a caller's pipe open.
hold() { flock -o "$LOCK" sleep 30 </dev/null >/dev/null 2>&1 & HOLDER=$!; until ! flock -n "$LOCK" true; do :; done; }
unhold() { pkill -P "$HOLDER" 2>/dev/null; kill "$HOLDER" 2>/dev/null; wait "$HOLDER" 2>/dev/null; HOLDER=; }
trap '[ -z "$HOLDER" ] || unhold; rm -rf "$S"' EXIT
hold
for cmd in aosp-patches.sh aosp-build.sh; do
  fresh; out=$(docker_run /repo/scripts/$cmd 2>&1); rc=$?
  [ $rc != 0 ] && grep -q "no AOSP lane lock after 2 s" <<<"$out" && ! fetched && [ ! -e "$S/docker.log" ]
  ok $? "aosp-docker.sh $cmd, lane held elsewhere: waits, gives up (rc $rc), no fetch, no docker run"
done
fresh; out=$(ANYBOOK_LANE_UNLOCKED=1 docker_run /repo/scripts/aosp-patches.sh 2>&1); rc=$?
[ $rc = 0 ] && fetched && [ "$(grep -c '^run' "$S/docker.log")" = 1 ]
ok $? "aosp-docker.sh aosp-patches.sh, ANYBOOK_LANE_UNLOCKED=1 (a tree of its own): fetches and runs"
unhold
fresh; out=$(docker_run /repo/scripts/aosp-patches.sh 2>&1); rc=$?
[ $rc = 0 ] && fetched && grep -qx "run, lock held" "$S/docker.log"
ok $? "aosp-docker.sh aosp-patches.sh, lane free: takes the lock, fetches, runs the container under it"

echo "$pass/$total passed"
[ "$pass" = "$total" ]
