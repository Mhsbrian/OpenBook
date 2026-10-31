#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# End-to-end download test for a release folder from scripts/release/make-release.sh, on an isolated Docker network
# (docs/RELEASE.md §6). Three containers: nginx as the web mirror (it also answers a GitHub-style 302 redirect),
# openbook-seeder (tools/release/seeder, with the same hardening as the compose file), and a libtorrent 2 client.
#   0. the seeder refuses a release whose release.json is not public;
#   1. web seed only: the client has no peers, and gets the whole image through the redirect;
#   2. peer only: the same info hashes without web seeds; the client gets it all from the seeder (Transmission);
#   3. the seeder's swarm.json counts the upload and its health check passes.
# Every download is checked against the release's sha256. Writes <data dir>/release-test/swarm-<UTC>/RESULTS.json.
# usage: swarm-test.sh [RELEASE_DIR]   (default: the newest folder in <data dir>/release/out)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
REL=${1:-$(ls -td "$A"/release/out/*/ | head -1)}; REL=${REL%/}
[ -f "$REL/release.json" ] || { echo "$REL has no release.json" >&2; exit 2; }
VER=$(jq -r .version "$REL/release.json"); FILE=$(jq -r '.artifacts[0].file' "$REL/release.json")
SHA=$(jq -r '.artifacts[0].sha256' "$REL/release.json")
W=$A/release-test/swarm-$(date -u +%Y%m%dT%H%M%SZ); NET=obswarm-$$; WEB=obs-web-$$; SEED=obs-seed-$$
mkdir -p "$W/releases/$VER" "$W/leech-web" "$W/leech-peer" "$A/logs/release"
exec > >(tee -a "$W/swarm-test.log") 2>&1
cleanup() { docker rm -f "$WEB" "$SEED" "$SEED-gate" > /dev/null 2>&1 || true; docker network rm "$NET" > /dev/null 2>&1 || true; }
trap cleanup EXIT
FAILS=0
check() { if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; FAILS=$((FAILS + 1)); fi; }
rc_of() { if "$@"; then echo 0; else echo 1; fi; }   # rc_of CMD...: 0 or 1, for check
echo "== swarm-test.sh $VER ($(date -u +%FT%TZ)), repo $(git -C "$R" rev-parse --short HEAD)"

# torrents with the same info dict and different web seeds (url-list is outside the info hash)
ln "$REL/$FILE" "$W/releases/$VER/$FILE" 2>/dev/null || cp --reflink=auto "$REL/$FILE" "$W/releases/$VER/$FILE"
cp "$REL/release.json" "$W/releases/$VER/"
E=$(jq -r '.date' "$REL/release.json"); E=$(date -u -d "$E" +%s)
MK="python3 $R/scripts/release/mktorrent.py $W/releases/$VER/$FILE --epoch $E --json"
$MK --out "$W/releases/$VER/$FILE.torrent" --webseed "http://web/gh/$FILE" > "$W/seeded.json"
cp "$W/releases/$VER/$FILE.torrent" "$W/web-only.torrent"
$MK --out "$W/peer-only.torrent" > "$W/peer-only.json"
set +e   # from here on every step is a check: count failures instead of stopping
cmp -s <(jq -r '.infohash_v1, .infohash_v2' "$W/seeded.json") <(jq -r '.infohash_v1, .infohash_v2' "$W/peer-only.json")
check $? "web-seeded and peer-only torrents share info hashes ($(jq -r .infohash_v1 "$W/seeded.json"))"
cmp -s <(jq -r '.infohash_v1, .infohash_v2' "$W/seeded.json") \
  <(jq -r '.artifacts[0].torrent.infohash_v1, .artifacts[0].torrent.infohash_v2' "$REL/release.json")
check $? "and match the release's own torrent"

cat > "$W/nginx.conf" <<EOF
server {
  listen 80; server_name web cdn;
  location /releases/ { root /srv; }
  location /gh/ { rewrite ^/gh/(.*)\$ http://cdn/releases/$VER/\$1 redirect; }
}
EOF
docker network create --internal "$NET" > /dev/null
docker run -d --name "$WEB" --network "$NET" --network-alias web --network-alias cdn \
  -v "$W/releases:/srv/releases:ro" -v "$W/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine > /dev/null
HARD=(--read-only --tmpfs /tmp:size=16m --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 64
      --memory 256m -v "$W/releases:/releases:ro" -e SYNC_SECONDS=3)

# 0. the gate
docker run -d --name "$SEED-gate" --network "$NET" "${HARD[@]}" openbook-seeder > /dev/null
for _ in $(seq 30); do docker exec "$SEED-gate" test -f /status/swarm.json 2>/dev/null && break; sleep 1; done
n=$(docker exec "$SEED-gate" openbook-seeder status | jq '.torrents | length')
docker logs "$SEED-gate" 2>&1 | grep -q "not seeding $VER/$FILE.torrent: its release.json is not public"
check $(( $? + n )) "the seeder refuses a release that is not public (torrents: $n)"
docker rm -f "$SEED-gate" > /dev/null

# the seeder, tests-only override on
docker run -d --name "$SEED" --network "$NET" --network-alias seed "${HARD[@]}" -e SEED_UNPUBLISHED=1 \
  openbook-seeder > /dev/null
t0=$(date +%s); state=
while [ $(( $(date +%s) - t0 )) -lt 300 ]; do
  state=$(docker exec "$SEED" sh -c 'cat /status/swarm.json 2>/dev/null' | jq -r '.torrents[0].state // empty' || true)
  [ "$state" = seeding ] && break; sleep 2
done
check "$(rc_of [ "$state" = seeding ])" "the seeder verifies the read-only image and seeds it in $(( $(date +%s) - t0 )) s"

LEECH=(docker run --rm --network "$NET" --user "$(id -u):$(id -g)" -v "$R/scripts/release:/s:ro" -v "$W:/w"
       openbook-release-test python3 /s/swarm-leech.py)
# 1. web seed only, through the redirect
"${LEECH[@]}" /w/web-only.torrent /w/leech-web "$SHA" > "$W/web.json"; rc=$?
cat "$W/web.json"
jq -e '.sources == ["web_seed"]' "$W/web.json" > /dev/null; check $(( rc + $? )) "web seed only (302 to the mirror): complete, sha256 ok, no peers used"
# 2. peer only
"${LEECH[@]}" /w/peer-only.torrent /w/leech-peer "$SHA" --peer seed:51413 > "$W/peer.json"; rc=$?
cat "$W/peer.json"
jq -e '.sources == ["peer"]' "$W/peer.json" > /dev/null; check $(( rc + $? )) "peer only (the seeder): complete, sha256 ok, no web seed used"

# 3. what the website would show
sleep 4
docker exec "$SEED" openbook-seeder status > "$W/swarm.json"; cat "$W/swarm.json"
up=$(jq '.torrents[0].uploaded_bytes' "$W/swarm.json"); size=$(jq '.torrents[0].size_bytes' "$W/swarm.json")
check "$(rc_of [ "$up" -ge "$size" ])" "swarm.json counts the upload ($up of $size bytes)"
docker exec "$SEED" openbook-seeder health > /dev/null; check $? "the seeder's health check passes"
docker logs "$SEED" > "$W/seeder.log" 2>&1
docker exec "$SEED" sh -c 'touch /releases/x 2>&1; touch /usr/x 2>&1' > "$W/readonly.txt" 2>&1 || true
check "$(rc_of [ "$(grep -c 'Read-only file system' "$W/readonly.txt")" = 2 ])" "the seeder can write neither the releases nor its own root file system"

jq -n --arg v "$VER" --arg f "$FILE" --argjson fails $FAILS --slurpfile web "$W/web.json" --slurpfile peer "$W/peer.json" \
  --slurpfile swarm "$W/swarm.json" '{version: $v, file: $f, fails: $fails, web_seed_only: $web[0],
  peer_only: $peer[0], swarm: $swarm[0]}' > "$W/RESULTS.json"
rm -f "$W/leech-web/$FILE" "$W/leech-peer/$FILE" "$W/releases/$VER/$FILE"
echo "$([ $FAILS = 0 ] && echo ALL PASS || echo "$FAILS FAILED"); results: $W/RESULTS.json"
exit $(( FAILS > 0 ))
