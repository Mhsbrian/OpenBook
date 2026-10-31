#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Download one torrent with libtorrent 2 and check the result, for scripts/release/swarm-test.sh.
DHT, local discovery, UPnP and NAT-PMP are off, so the only sources are the torrent's web seeds and --peer.
usage: swarm-leech.py TORRENT SAVE_DIR SHA256 [--peer HOST:PORT] [--timeout S]
Prints one JSON line: complete, seconds, bytes, MB/s, the kinds of sources seen, sha256 match.
"""
import argparse
import hashlib
import json
import os
import socket
import sys
import time

import libtorrent as lt

# libtorrent 2 numbers these as bit flags (1, 2, 4); use the binding's names, never the numbers
KIND = {int(lt.peer_info.standard_bittorrent): "peer", int(lt.peer_info.web_seed): "web_seed",
        int(lt.peer_info.http_seed): "http_seed"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("torrent")
    ap.add_argument("save")
    ap.add_argument("sha256")
    ap.add_argument("--peer")
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()
    s = lt.session({"enable_dht": False, "enable_lsd": False, "enable_upnp": False, "enable_natpmp": False,
                    "listen_interfaces": "0.0.0.0:6881", "alert_mask": lt.alert_category.error,
                    "connections_limit": 50})
    p = lt.add_torrent_params()
    p.ti = lt.torrent_info(a.torrent)
    p.save_path = a.save
    h = s.add_torrent(p)
    if a.peer:
        host, port = a.peer.rsplit(":", 1)
        peer = (socket.gethostbyname(host), int(port))
    seen, t0, last = set(), time.time(), 0
    while time.time() - t0 < a.timeout:
        if a.peer and time.time() - last > 5:
            h.connect_peer(peer)
            last = time.time()
        for pi in h.get_peer_info():
            seen.add(KIND.get(int(pi.connection_type), str(pi.connection_type)))
        for al in s.pop_alerts():
            print("libtorrent:", al.message(), file=sys.stderr)
        st = h.status()
        if st.is_seeding:
            break
        time.sleep(0.25)
    secs = time.time() - t0
    st = h.status()
    path = os.path.join(a.save, p.ti.name())
    got = None
    if st.is_seeding:
        hh = hashlib.sha256()
        with open(path, "rb") as f:
            for c in iter(lambda: f.read(1 << 20), b""):
                hh.update(c)
        got = hh.hexdigest()
    out = {"complete": st.is_seeding, "seconds": round(secs, 1), "bytes": st.total_wanted_done,
           "MBps": round(st.total_wanted_done / secs / 1e6, 1), "sources": sorted(seen),
           "sha256_ok": got == a.sha256, "progress": round(st.progress, 4)}
    print(json.dumps(out), flush=True)
    sys.exit(0 if out["complete"] and out["sha256_ok"] else 1)


if __name__ == "__main__":
    main()
