#!/usr/bin/env bash
# Sync AOSP android-latest-release (Android 17) into /aosp (= ~/anybook/aosp). Runs inside anybook-aosp:
#   scripts/aosp-docker.sh /repo/scripts/aosp-sync.sh [mirror|tree|all|relink]      (default: all)
#
#   /aosp/mirror  repo --mirror of the manifest's *source* projects, full history (~100 GB). Seeded from
#                 the clone.bundle files on storage.googleapis.com, which spares the googlesource git quota.
#   /aosp/src     build tree. Source projects borrow objects from the mirror (repo --reference = git
#                 alternates, so don't delete the mirror). Prebuilt/binary projects are shallow (depth 1).
# Why not a full mirror: the history of this manifest alone is 748 GB, 87% of it prebuilt binaries
# (docs/aosp-build.md). Resumable: re-run after any failure or interruption.
set -euo pipefail
MODE=${1:-all}
U=${AOSP_MANIFEST_URL:-https://android.googlesource.com/platform/manifest}
B=${AOSP_BRANCH:-android-latest-release}
J=${AOSP_JOBS:-8}
M=/aosp/mirror; T=/aosp/src; L=/logs; H=$(cd "$(dirname "$0")" && pwd)
LM=.repo/local_manifests/anybook-split.xml
mkdir -p "$L"
exec > >(tee -a "$L/sync-$MODE-$(date -u +%Y%m%dT%H%M%SZ).log") 2>&1
stamp(){ echo "=== $(date -u +%FT%TZ) $*"; }

# repo sync, retried: a failed project fails the whole sync, and the next pass only fetches what's missing.
sync_retry(){
  for i in 1 2 3 4 5; do
    stamp "repo sync attempt $i: $*"
    if repo sync "$@"; then return 0; fi
    sleep $((60 * i))
  done
  return 1
}

split(){  # write the local manifest from the upstream manifest (`repo manifest` doesn't work in a mirror)
  if grep -q '<include' .repo/manifests/default.xml; then echo "default.xml has <include>; teach split() to expand it" >&2; exit 1; fi
  mkdir -p .repo/local_manifests
  python3 -I "$H/aosp-local-manifest.py" "$1" .repo/manifests/default.xml "$LM"
}

mirror(){
  mkdir -p "$M"; cd "$M"; stamp "mirror: init $U -b $B"
  [ -d .repo/manifests.git ] || repo init --mirror -u "$U" -b "$B"   # init is one-shot; sync updates the manifest
  split mirror
  # -c: fetch only the manifest branch (+ tags). The clone bundles already carry every branch's history, and
  # an all-heads fetch fails upstream: external/curl's refs/heads/android17-security-release is a tag object.
  sync_retry -c -j"$J" --optimized-fetch --retry-fetches=5
  stamp "mirror: done"; du -sh "$M"
}

relink(){  # make the tree's alternates relative: repo writes /aosp/mirror/..., which only exists in the container
  python3 -I - "$T/.repo" <<'PY'
import os, sys
n = 0
for root, dirs, files in os.walk(sys.argv[1]):
    dirs[:] = [d for d in dirs if d != "pack"]
    if root.endswith("/objects/info") and "alternates" in files:
        f, base = os.path.join(root, "alternates"), os.path.dirname(root)
        old = open(f).read().splitlines()
        new = [os.path.relpath(l, base) if l.startswith("/") else l for l in old]
        if new != old:
            open(f, "w").write("\n".join(new) + "\n"); n += 1
print(f"relink: {n} alternates made relative")
PY
}

tree(){
  mkdir -p "$T"; cd "$T"; stamp "tree: init $U -b $B --reference=$M"
  [ -d .repo/manifests.git ] || repo init -u "$U" -b "$B" -c --no-tags --no-use-superproject --reference="$M"
  split tree
  sync_retry -c -j"$J" --no-tags --optimized-fetch --retry-fetches=5
  relink
  stamp "tree: done"
  repo manifest -r -o "$L/manifest-pinned.xml"
  git -C .repo/manifests log -1 --format='manifest %H %cd %s' | tee "$L/manifest-revision.txt"
  du -sh "$T"; du -sh "$T/.repo"
}

df -h /aosp
case $MODE in
  mirror) mirror ;;
  tree) tree ;;
  relink) relink ;;
  all) mirror; tree ;;
  *) echo "usage: $0 [mirror|tree|all|relink]" >&2; exit 2 ;;
esac
stamp "aosp-sync $MODE finished"; df -h /aosp
