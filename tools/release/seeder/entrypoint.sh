#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# openbook-seeder run | health | status
#   run     write Transmission's settings from the environment, start it, then every SYNC_SECONDS:
#           add each published torrent (data from its own folder, read-only), drop torrents whose release is gone
#           or no longer published (never their data), and write /status/swarm.json for the website.
#           Published means: in a release folder (/releases/<version>/), its release.json says "public": true;
#           in the site's flat folder (/releases/*.torrent), /releases/releases.json lists it and not "hidden".
#   health  exit 0 when the RPC answers, swarm.json is fresh and no seeded torrent is in error.
#   status  print swarm.json.
# Environment: PEER_PORT (51413), SEED_UP_KBPS (0 = no limit), PEER_LIMIT (200), SYNC_SECONDS (60),
#              SEED_UNPUBLISHED (0; 1 seeds every release that has a torrent: tests only).
set -eu
CONF=/state/transmission
RPC=http://127.0.0.1:9091/transmission/rpc
SID=/tmp/openbook-seeder.sid
STATUS=/status/swarm.json
log() { echo "openbook-seeder: $*"; }

num() { case $2 in ''|*[!0-9]*) log "$1 must be a number, got '$2'"; exit 2 ;; esac; }

rpc() { # rpc JSON -> response on stdout; handles Transmission's session-id handshake
  for _ in 1 2; do
    code=$(curl -s -o /tmp/rpc.out -D /tmp/rpc.hdr -w '%{http_code}' -H "X-Transmission-Session-Id: $(cat "$SID" 2>/dev/null)" \
      --data-binary "$1" "$RPC" || true)
    if [ "$code" = 409 ]; then
      sed -n 's/^[Xx]-[Tt]ransmission-[Ss]ession-[Ii]d: *\([^[:space:]]*\).*/\1/p' /tmp/rpc.hdr > "$SID"; continue
    fi
    [ "$code" = 200 ] || return 1
    cat /tmp/rpc.out; return 0
  done
  return 1
}

settings() {
  num PEER_PORT "$PEER_PORT"; num SEED_UP_KBPS "$SEED_UP_KBPS"; num PEER_LIMIT "$PEER_LIMIT"
  mkdir -p "$CONF"
  jq -n --argjson port "$PEER_PORT" --argjson up "$SEED_UP_KBPS" --argjson peers "$PEER_LIMIT" '{
    "download-dir": "/releases", "incomplete-dir-enabled": false, "watch-dir-enabled": false,
    "rpc-enabled": true, "rpc-bind-address": "127.0.0.1", "rpc-port": 9091,
    "rpc-whitelist-enabled": true, "rpc-whitelist": "127.0.0.1",
    "rpc-host-whitelist-enabled": true, "rpc-host-whitelist": "127.0.0.1,localhost",
    "rpc-authentication-required": false, "anti-brute-force-enabled": true,
    "peer-port": $port, "peer-port-random-on-start": false, "port-forwarding-enabled": false,
    "dht-enabled": true, "pex-enabled": true, "lpd-enabled": false, "utp-enabled": true, "encryption": 1,
    "peer-limit-global": $peers, "peer-limit-per-torrent": $peers,
    "speed-limit-up": $up, "speed-limit-up-enabled": ($up > 0), "alt-speed-enabled": false,
    "ratio-limit-enabled": false, "idle-seeding-limit-enabled": false, "queue-stalled-enabled": false,
    "seed-queue-enabled": false, "download-queue-enabled": false,
    "start-added-torrents": true, "trash-original-torrent-files": false, "rename-partial-files": false,
    "blocklist-enabled": false, "cache-size-mb": 16, "message-level": 4, "umask": "022"
  }' > "$CONF/settings.json"
}

public() { # public TORRENT: this torrent may be seeded
  [ "$SEED_UNPUBLISHED" = 1 ] && return 0
  if [ -f "${1%/*}/release.json" ]; then
    jq -e '.public == true' "${1%/*}/release.json" > /dev/null 2>&1; return
  fi
  [ -f /releases/releases.json ] && jq -e --arg t "${1#/releases/}" \
    '[.releases[]? | select(.hidden != true) | .torrent] | index($t) != null' /releases/releases.json > /dev/null 2>&1
}

sync_once() {
  have=$(rpc '{"method":"torrent-get","arguments":{"fields":["id","hashString","downloadDir","name"]}}') || return 1
  # add what should be seeded
  for t in /releases/*.torrent /releases/*/*.torrent; do
    [ -f "$t" ] || continue
    d=${t%/*}
    if ! public "$t"; then
      grep -qxF "$t" /tmp/openbook-seeder.skipped 2>/dev/null \
        || { log "not seeding ${t#/releases/}: not published"; echo "$t" >> /tmp/openbook-seeder.skipped; }
      continue
    fi
    echo "$have" | jq -e --arg d "$d" --arg n "$(basename "$t" .torrent)" \
      '.arguments.torrents | any(.downloadDir == $d and .name == $n)' > /dev/null && continue
    r=$(rpc "$(jq -nc --arg f "$t" --arg d "$d" '{"method":"torrent-add","arguments":{"filename":$f,"download-dir":$d,"paused":false}}')") \
      || { log "could not add ${t#/releases/}"; continue; }
    log "seeding ${t#/releases/}: $(echo "$r" | jq -r '.result')"
  done
  # drop what should not be seeded any more (the data is never touched)
  echo "$have" | jq -r '.arguments.torrents[] | "\(.id)\t\(.downloadDir)\t\(.name)"' | while IFS="$(printf '\t')" read -r id d n; do
    if [ ! -f "$d/$n.torrent" ] || ! public "$d/$n.torrent"; then
      rpc "{\"method\":\"torrent-remove\",\"arguments\":{\"ids\":[$id],\"delete-local-data\":false}}" > /dev/null \
        && log "stopped seeding $n (release gone or not public)"
    fi
  done
  # status for the website: counts and totals only, no peer addresses
  rpc '{"method":"torrent-get","arguments":{"fields":["name","hashString","status","error","errorString","percentDone","peersConnected","peersGettingFromUs","rateUpload","uploadedEver","totalSize","downloadDir"]}}' \
    | jq --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --argjson port "$PEER_PORT" '{
        schema: "openbook-swarm/1", updated: $now, peer_port: $port,
        torrents: [.arguments.torrents[] | {
          version: (if .downloadDir == "/releases" then null else (.downloadDir | split("/") | last) end), name, infohash: .hashString,
          state: (if .error != 0 then "error" elif (.status == 1 or .status == 2) then "checking"
                  elif .percentDone < 1 then "incomplete" elif .status == 6 then "seeding" else "stopped" end),
          error: (if .error != 0 then .errorString else null end),
          peers: .peersConnected, uploading_to: .peersGettingFromUs, upload_bps: .rateUpload,
          uploaded_bytes: .uploadedEver, size_bytes: .totalSize }]
      }' > "$STATUS.tmp" && mv "$STATUS.tmp" "$STATUS"
}

case ${1:-run} in
  run)
    num SYNC_SECONDS "$SYNC_SECONDS"
    settings
    log "Transmission $(transmission-daemon -V 2>&1 | head -1 | sed 's/^transmission-daemon //'), peer port $PEER_PORT, upload limit ${SEED_UP_KBPS} KB/s (0 = none)"
    [ "$SEED_UNPUBLISHED" = 1 ] && log "SEED_UNPUBLISHED=1: seeding releases that are not public (tests only)"
    transmission-daemon -f -g "$CONF" &
    TD=$!
    trap 'kill -TERM $TD 2>/dev/null; wait $TD; exit 0' TERM INT
    i=0; until rpc '{"method":"session-get","arguments":{"fields":["version"]}}' > /dev/null; do
      i=$((i + 1)); [ $i -lt 60 ] || { log "Transmission's RPC did not come up"; exit 1; }
      kill -0 $TD 2>/dev/null || { log "transmission-daemon exited"; exit 1; }
      sleep 1
    done
    while kill -0 $TD 2>/dev/null; do
      sync_once || log "sync failed; retrying in ${SYNC_SECONDS}s"
      sleep "$SYNC_SECONDS" & wait $! || true
    done
    log "transmission-daemon exited"; exit 1 ;;
  health)
    rpc '{"method":"session-get","arguments":{"fields":["version"]}}' > /dev/null || { echo "rpc down"; exit 1; }
    [ -f "$STATUS" ] || { echo "no status yet"; exit 1; }
    age=$(( $(date +%s) - $(date -r "$STATUS" +%s) ))
    [ $age -le $(( SYNC_SECONDS * 3 + 30 )) ] || { echo "status is ${age}s old"; exit 1; }
    jq -e '[.torrents[] | select(.state == "error")] | length == 0' "$STATUS" > /dev/null || { echo "a torrent is in error"; exit 1; }
    echo ok ;;
  status) cat "$STATUS" ;;
  *) echo "usage: openbook-seeder run|health|status" >&2; exit 2 ;;
esac
