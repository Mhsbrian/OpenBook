#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check scripts/release/mktorrent.py against libtorrent 2, an independent implementation of BEP 3 and BEP 52.
Runs in the openbook-release-test container (scripts/release/torrent-test.sh). For each case (file sizes around the
16 KiB block, piece and power-of-two edges, and optionally a real release file):
  1. our torrent loads in libtorrent, which checks the v2 piece layers against the pieces root;
  2. libtorrent's own hybrid torrent of the same file and piece size has the same v1 and v2 info hashes as ours;
  3. libtorrent rechecks the file against our torrent (v1 SHA-1 pieces and v2 SHA-256 tree) and finds every piece;
  4. one flipped byte makes the recheck fail (the check is real);
  5. the same inputs give the same .torrent bytes (determinism), and bdecode(bencode(x)) == x.
usage: torrent-test.py WORKDIR [REAL_FILE PIECE_KIB]
"""
import hashlib
import os
import sys
import time
from importlib.machinery import SourceFileLoader

import libtorrent as lt

HERE = os.path.dirname(os.path.abspath(__file__))
mk = SourceFileLoader("mktorrent", f"{HERE}/mktorrent.py").load_module()
KiB = 1024
fails = 0


def check(cond, what):
    global fails
    print(("PASS " if cond else "FAIL ") + what, flush=True)
    fails += 0 if cond else 1


def lt_reference(path, plen):
    fs = lt.file_storage()
    lt.add_files(fs, path)
    ct = lt.create_torrent(fs, plen)  # libtorrent 2 default: hybrid v1 + v2
    lt.set_piece_hashes(ct, os.path.dirname(path))
    ti = lt.torrent_info(ct.generate())
    ih = ti.info_hashes()
    return str(ih.v1), str(ih.v2)


def recheck(torrent, save_path):
    s = lt.session({"enable_dht": False, "enable_lsd": False, "enable_upnp": False, "enable_natpmp": False,
                    "listen_interfaces": "127.0.0.1:0",
                    "alert_mask": lt.alert_category.status | lt.alert_category.error})
    p = lt.add_torrent_params()
    p.ti = lt.torrent_info(torrent)
    p.save_path = save_path
    p.flags &= ~(lt.torrent_flags.auto_managed | lt.torrent_flags.paused)  # libtorrent never checks a paused torrent
    p.flags |= lt.torrent_flags.upload_mode  # no peers are reachable; never write to the file
    h = s.add_torrent(p)  # no resume data: libtorrent checks the existing file against the torrent
    deadline, done = time.time() + 300, False
    while not done and time.time() < deadline:
        s.wait_for_alert(1000)
        for a in s.pop_alerts():
            if isinstance(a, lt.torrent_checked_alert):
                done = True
            elif isinstance(a, (lt.file_error_alert, lt.torrent_error_alert)):
                print("  libtorrent:", a.message())
    have = h.status().num_pieces
    s.remove_torrent(h)
    return (have if done else -1), p.ti.num_pieces()


def case(work, name, size, plen, real=None):
    d = os.path.join(work, name)
    os.makedirs(d, exist_ok=True)
    path = real or os.path.join(d, "data.bin")
    if not real:
        rnd = hashlib.shake_256(name.encode()).digest(size) if size else b""
        with open(path, "wb") as f:
            f.write(rnd)
    data, ident = mk.make(path, os.path.basename(path), plen, ["udp://tracker.example:1337/announce"],
                          ["https://dl.example/" + os.path.basename(path)], None, 1767225600)
    tpath = os.path.join(d, "ours.torrent")
    with open(tpath, "wb") as f:
        f.write(data)
    label = f"{name} ({size} B, {plen // KiB} KiB pieces)"
    try:
        ti = lt.torrent_info(tpath)
        ih = ti.info_hashes()
        check(str(ih.v1) == ident["infohash_v1"] and str(ih.v2) == ident["infohash_v2"],
              f"{label}: libtorrent loads it; info hashes agree ({ident['infohash_v1'][:12]}…, "
              f"{ident['infohash_v2'][:12]}…)")
        check(ti.num_pieces() == ident["pieces"] and ti.total_size() == size, f"{label}: pieces and size agree")
    except RuntimeError as e:
        check(False, f"{label}: libtorrent rejected the torrent: {e}")
        return
    r1, r2 = lt_reference(path, plen)
    check((r1, r2) == (ident["infohash_v1"], ident["infohash_v2"]),
          f"{label}: same info hashes as libtorrent's own hybrid torrent")
    have, total = recheck(tpath, os.path.dirname(path))
    check(have == total, f"{label}: recheck finds {have}/{total} pieces")
    if not real and size:
        with open(path, "r+b") as f:
            f.seek(size // 2)
            b = f.read(1)
            f.seek(size // 2)
            f.write(bytes([b[0] ^ 1]))
        have, total = recheck(tpath, os.path.dirname(path))
        check(have == total - 1, f"{label}: one flipped byte fails exactly one piece ({have}/{total})")
    again, _ = mk.make(path if not real else real, os.path.basename(path), plen,
                       ["udp://tracker.example:1337/announce"], ["https://dl.example/" + os.path.basename(path)],
                       None, 1767225600)
    if not real and size:
        check(again != data, f"{label}: the changed file gives a different torrent")
    else:
        check(again == data, f"{label}: deterministic (same bytes twice)")
    check(mk.bencode(mk.bdecode(data)) == data, f"{label}: bdecode/bencode round trip")


def main():
    work = sys.argv[1]
    print(f"libtorrent {lt.__version__}")
    for name, size, plen in [
        ("one-byte", 1, 16 * KiB), ("one-block", 16 * KiB, 16 * KiB), ("block-plus-one", 16 * KiB + 1, 16 * KiB),
        ("under-one-piece", 200 * KiB + 7, 256 * KiB), ("exact-piece", 256 * KiB, 256 * KiB),
        ("piece-plus-one", 256 * KiB + 1, 256 * KiB), ("three-pieces-odd", 3 * 256 * KiB - 5, 256 * KiB),
        ("five-pieces-1m", 5 * 1024 * KiB + 12345, 1024 * KiB), ("pow2-pieces", 8 * 64 * KiB, 64 * KiB),
        ("seventeen-pieces-plus-one", 17 * 32 * KiB + 1, 32 * KiB),
    ]:
        case(work, name, size, plen)
    if len(sys.argv) > 3:
        real, plen = sys.argv[2], int(sys.argv[3]) * KiB
        case(work, "real-" + os.path.basename(real), os.path.getsize(real), plen, real=real)
    check(mk.piece_size(885136268) == 1024 * KiB, "piece_size: the 0.9 GB live image gets 1 MiB pieces")
    check(mk.piece_size(10) == 256 * KiB and mk.piece_size(100 * 1024 ** 3) == 16 * 1024 * KiB,
          "piece_size: clamped to 256 KiB .. 16 MiB")
    print(f"{'ALL PASS' if not fails else f'{fails} FAILED'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
