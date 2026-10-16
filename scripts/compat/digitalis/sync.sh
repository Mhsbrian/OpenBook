#!/usr/bin/env bash
# Sync the Digitalis source tree (ANAL-181): AOSP android16-qpr2-release plus the DigitalisX64 projects, into
# ~/anybook/digitalis/aosp16. Runs inside the container:
#   scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/sync.sh
# - Manifest: github.com/DigitalisX64/manifest pinned at MANIFEST_REV (AOSP android16-qpr2-release + include
#   digitalis.xml). manifests/digitalis/digitalis-pinned.xml pins the four DigitalisX64 projects over https.
# - AOSP source projects borrow objects from the shared mirror (repo --reference, read-only); prebuilts are
#   shallow (scripts/aosp-local-manifest.py tree), as in the Android 17 tree.
# Resumable: re-run after any failure.
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}; T=$A/digitalis/aosp16; M=$A/aosp/mirror; L=$A/logs/digitalis
U=https://github.com/DigitalisX64/manifest.git
MANIFEST_REV=3969040d9ea562e8c874a57f545beeaf88975bc9
J=${DIGITALIS_JOBS:-8}
mkdir -p "$T" "$L"; cd "$T"
exec > >(tee -a "$L/sync-$(date -u +%Y%m%dT%H%M%SZ).log") 2>&1
stamp(){ echo "=== $(date -u +%FT%TZ) $*"; }
df -h "$T"
if [ ! -d .repo/manifests.git ]; then
  stamp "repo init $U --reference=$M"
  repo init -u "$U" -b android-latest-release -c --no-tags --no-use-superproject --reference="$M"
fi
git -C .repo/manifests fetch -q origin
git -C .repo/manifests checkout -q "$MANIFEST_REV"
stamp "manifest $(git -C .repo/manifests log -1 --format='%H %cd %s')"
mkdir -p .repo/local_manifests
python3 -I /repo/scripts/aosp-local-manifest.py tree .repo/manifests/default.xml .repo/local_manifests/anybook-split.xml
cp /repo/manifests/digitalis/digitalis-pinned.xml .repo/local_manifests/digitalis-pinned.xml
for i in 1 2 3 4 5; do
  stamp "repo sync attempt $i"
  if repo sync -c -j"$J" --no-tags --optimized-fetch --retry-fetches=5 --no-manifest-update; then ok=1; break; fi
  sleep $((60 * i))
done
[ "${ok:-}" = 1 ] || { stamp "repo sync failed"; exit 1; }
repo manifest -r -o "$L/manifest-pinned.xml"
stamp "tree done"; du -sh "$T" "$T/.repo"; df -h "$T"
