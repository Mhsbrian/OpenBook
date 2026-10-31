#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Ask each UDP tracker for a BEP 15 connection id, to check the trackers in a release are alive before it ships.
Sends only the 16-byte connect request: no info hash and no announce, so nothing is registered anywhere.
usage: tracker-probe.py URL...      (default: make-release.sh's default trackers)
Prints one line per tracker and exits 1 if none answered.
"""
import os
import random
import socket
import struct
import sys
import time
import urllib.parse

DEFAULT = ["udp://tracker.opentrackr.org:1337/announce", "udp://open.stealth.si:80/announce",
           "udp://tracker.torrent.eu.org:451/announce"]


def probe(url, timeout=4.0, tries=2):
    u = urllib.parse.urlsplit(url)
    if u.scheme != "udp":
        return False, "only udp:// trackers are probed"
    try:
        addrs = socket.getaddrinfo(u.hostname, u.port, type=socket.SOCK_DGRAM)
    except OSError as e:
        return False, f"DNS: {e}"
    for fam, _, _, _, addr in addrs:
        with socket.socket(fam, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            for _ in range(tries):
                tid = random.getrandbits(32)
                t0 = time.time()
                try:
                    s.sendto(struct.pack(">QII", 0x41727101980, 0, tid), addr)
                    data, _ = s.recvfrom(64)
                except OSError:
                    continue
                if len(data) >= 16 and struct.unpack(">II", data[:8]) == (0, tid):
                    return True, f"{addr[0]} answered in {int((time.time() - t0) * 1000)} ms"
    return False, "no answer"


def main():
    urls = sys.argv[1:] or DEFAULT
    alive = 0
    for url in urls:
        ok, why = probe(url)
        alive += ok
        print(f"{'OK  ' if ok else 'DOWN'} {url}: {why}")
    print(f"{alive}/{len(urls)} trackers answered")
    sys.exit(0 if alive else 1)


if __name__ == "__main__":
    main()
