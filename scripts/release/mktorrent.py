#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Make a BitTorrent hybrid v1 + v2 (BEP 3 + BEP 52) torrent for one file, with web seeds (BEP 19) and a tracker
list (BEP 12). Python 3 standard library only, and deterministic: the same file, name, piece size, trackers, web
seeds and --epoch give the same .torrent, byte for byte (docs/RELEASE.md).

Why hybrid: v1 clients (aria2, older Transmission) see an ordinary torrent; v2 clients (libtorrent 2, qBittorrent
4.4+, Transmission 4.1+) also check every 16 KiB block against a SHA-256 merkle tree. Both halves describe the same
single file, so there is no padding and the two swarms share one set of bytes.

usage: mktorrent.py FILE --out TORRENT [--name NAME] [--piece-kib N] [--tracker URL]... [--webseed URL]...
                    [--comment TEXT] [--epoch S] [--json]
  --piece-kib  piece size in KiB, a power of two from 16 (default: chosen from the file size, see piece_size())
  --webseed    full URL of the file itself (BEP 19 for a single-file torrent); give one per mirror
  --json       print the torrent's identity (info hashes, magnet, sizes) as JSON on stdout
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.parse

BLOCK = 16 * 1024  # BEP 52 leaf size


def bencode(v):
    """Bencode ints, bytes, str (UTF-8), lists and dicts (keys sorted as raw bytes, as BEP 3 requires)."""
    if isinstance(v, bool):
        raise TypeError("bool is not a bencode type")
    if isinstance(v, int):
        return b"i%de" % v
    if isinstance(v, str):
        v = v.encode()
    if isinstance(v, bytes):
        return b"%d:%s" % (len(v), v)
    if isinstance(v, list):
        return b"l" + b"".join(bencode(x) for x in v) + b"e"
    if isinstance(v, dict):
        items = sorted(((k.encode() if isinstance(k, str) else k), x) for k, x in v.items())
        keys = [k for k, _ in items]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate dict key")
        return b"d" + b"".join(bencode(k) + bencode(x) for k, x in items) + b"e"
    raise TypeError(f"cannot bencode {type(v).__name__}")


def bdecode(data):
    """Decode a whole bencoded byte string (used by the tests and by --check). Strings stay bytes."""
    def at(i):
        c = data[i:i + 1]
        if c == b"i":
            j = data.index(b"e", i)
            return int(data[i + 1:j]), j + 1
        if c == b"l":
            out, i = [], i + 1
            while data[i:i + 1] != b"e":
                x, i = at(i)
                out.append(x)
            return out, i + 1
        if c == b"d":
            out, i, last = {}, i + 1, None
            while data[i:i + 1] != b"e":
                k, i = at(i)
                if not isinstance(k, bytes) or (last is not None and k <= last):
                    raise ValueError("dict keys must be unique byte strings in sorted order")
                out[k], i, last = *at(i), k
            return out, i + 1
        if c.isdigit():
            j = data.index(b":", i)
            n = int(data[i:j])
            return data[j + 1:j + 1 + n], j + 1 + n
        raise ValueError(f"bad bencode at byte {i}")
    v, end = at(0)
    if end != len(data):
        raise ValueError("trailing data after bencoded value")
    return v


def piece_size(length):
    """Smallest power of two from 256 KiB to 16 MiB that keeps the torrent at or under 1024 pieces. For the
    ~0.9 GB live image that is 1 MiB: 845 pieces, a ~45 KB .torrent, and web-seed requests of a sensible size."""
    p = 256 * 1024
    while p < 16 * 1024 * 1024 and -(-length // p) > 1024:
        p *= 2
    return p


def _pad_hashes(levels):
    """pad[h] = root of a subtree of height h whose leaves are all zero hashes (BEP 52: leaves past the end of the
    file are 32 zero bytes)."""
    pad = [bytes(32)]
    for _ in range(levels):
        pad.append(hashlib.sha256(pad[-1] + pad[-1]).digest())
    return pad


def _merkle(nodes, height, pad):
    """Reduce a layer to its root: pad the layer with pad[height] up to a power of two, then hash pairs."""
    n = 1
    while n < len(nodes):
        n *= 2
    nodes = nodes + [pad[height]] * (n - len(nodes))
    while len(nodes) > 1:
        nodes = [hashlib.sha256(nodes[i] + nodes[i + 1]).digest() for i in range(0, len(nodes), 2)]
        height += 1
    return nodes[0]


def hash_file(path, plen):
    """One pass over the file: v1 SHA-1 piece hashes, and v2's piece layer (one SHA-256 subtree root per piece)."""
    if plen < BLOCK or plen & (plen - 1):
        raise ValueError("piece size must be a power of two, at least 16 KiB")
    per_piece = plen // BLOCK
    height = per_piece.bit_length() - 1
    pad = _pad_hashes(64)
    v1, layer, length = [], [], 0
    with open(path, "rb") as f:
        while True:
            piece = f.read(plen)
            if not piece:
                break
            length += len(piece)
            v1.append(hashlib.sha1(piece).digest())
            leaves = [hashlib.sha256(piece[i:i + BLOCK]).digest() for i in range(0, len(piece), BLOCK)]
            # The last piece's subtree is still per_piece leaves wide; the missing leaves are zero hashes.
            layer.append(_merkle(leaves + [pad[0]] * (per_piece - len(leaves)), 0, pad) if per_piece > 1
                         else leaves[0])
    if length == 0:
        raise ValueError("empty file: nothing to share")
    if length <= plen:
        # One piece: the root is the merkle root over that piece's blocks only (no piece layer is stored).
        with open(path, "rb") as f:
            data = f.read()
        leaves = [hashlib.sha256(data[i:i + BLOCK]).digest() for i in range(0, len(data), BLOCK)]
        root = _merkle(leaves, 0, pad)
    else:
        root = _merkle(layer, height, pad)
    return length, b"".join(v1), layer, root


def make(path, name=None, plen=None, trackers=(), webseeds=(), comment=None, epoch=None):
    """Return (torrent bytes, identity dict)."""
    name = name or os.path.basename(path)
    if "/" in name or name in ("", ".", ".."):
        raise ValueError("name must be a plain file name")
    size = os.path.getsize(path)
    plen = plen or piece_size(size)
    length, pieces, layer, root = hash_file(path, plen)
    info = {
        "name": name,
        "piece length": plen,
        # v1 half (BEP 3, single-file mode)
        "length": length,
        "pieces": pieces,
        # v2 half (BEP 52)
        "meta version": 2,
        "file tree": {name: {"": {"length": length, "pieces root": root}}},
    }
    t = {"info": info, "created by": "OpenBook scripts/release/mktorrent.py"}
    if length > plen:
        t["piece layers"] = {root: b"".join(layer)}
    trackers = list(dict.fromkeys(trackers))
    if trackers:
        t["announce"] = trackers[0]
        t["announce-list"] = [[u] for u in trackers]  # one tier per tracker: clients try each in turn
    webseeds = list(dict.fromkeys(webseeds))
    if webseeds:
        t["url-list"] = webseeds
    if comment:
        t["comment"] = comment
    if epoch is not None:
        t["creation date"] = int(epoch)
    raw_info = bencode(info)
    ih1 = hashlib.sha1(raw_info).hexdigest()
    ih2 = hashlib.sha256(raw_info).hexdigest()
    q = [("xt", f"urn:btih:{ih1}"), ("xt", f"urn:btmh:1220{ih2}"), ("dn", name), ("xl", str(length))]
    q += [("tr", u) for u in trackers] + [("ws", u) for u in webseeds]
    magnet = "magnet:?" + "&".join(f"{k}={urllib.parse.quote(v, safe=':')}" for k, v in q)
    ident = {
        "name": name, "length": length, "piece_length": plen, "pieces": len(pieces) // 20,
        "infohash_v1": ih1, "infohash_v2": ih2, "pieces_root": root.hex(),
        "trackers": trackers, "webseeds": webseeds, "magnet": magnet,
    }
    return bencode(t), ident


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name")
    ap.add_argument("--piece-kib", type=int)
    ap.add_argument("--tracker", action="append", default=[])
    ap.add_argument("--webseed", action="append", default=[])
    ap.add_argument("--comment")
    ap.add_argument("--epoch", type=int, default=int(os.environ["SOURCE_DATE_EPOCH"])
                    if os.environ.get("SOURCE_DATE_EPOCH") else None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    for u in a.tracker + a.webseed:
        if urllib.parse.urlsplit(u).scheme not in ("http", "https", "udp", "wss"):
            ap.error(f"not a tracker or web seed URL: {u}")
    data, ident = make(a.file, a.name, a.piece_kib * 1024 if a.piece_kib else None, a.tracker, a.webseed,
                       a.comment, a.epoch)
    tmp = a.out + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, a.out)
    ident["torrent_bytes"] = len(data)
    ident["torrent_sha256"] = hashlib.sha256(data).hexdigest()
    if a.json:
        json.dump(ident, sys.stdout, indent=1)
        print()
    else:
        print(f"{a.out}: {ident['pieces']} pieces of {ident['piece_length'] // 1024} KiB, "
              f"v1 {ident['infohash_v1']}, v2 {ident['infohash_v2']}")


if __name__ == "__main__":
    main()
