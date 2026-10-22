#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Inspect (and optionally download) a captured Google OTA without fetching all of it.

Reads the OTA zip remotely with HTTP Range requests (or a local file): the zip's
central directory (ZIP64 aware: OTA packages pass 4 GB), Google's metadata
(META-INF/com/android/metadata: pre/post build, OTA type), payload_properties.txt,
and the payload's header and manifest. Then it reports what the update is: full or
incremental, from which build to which, which partitions with which old/new
sizes and hashes, and, given --stock (our stock images as <partition>.img),
whether every source partition of an incremental matches what we hold, which is
what reconstructing Google's new images on the host needs.

--download fetches the payload and verifies it against Google's own
payload_properties (FILE_SIZE, FILE_HASH = base64 SHA-256).

Everything is written under --out (mode 0700): the OTA is for the owner's own
device and is never redistributed. The printed summary redacts the URL.

usage: inspect-google-ota.py --offer OUT/offer.json | --url URL  --out DIR [--stock DIR] [--download]
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import urllib.request
import zlib

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fit", HERE / "check-ota-fit.py")
fit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fit)
WANTED = ("payload.bin", "payload_properties.txt", "META-INF/com/android/metadata")


class Source:
    """A remote (HTTP Range) or local file."""

    def __init__(self, where):
        self.where = where
        self.local = not str(where).startswith(("http://", "https://"))
        if self.local:
            self.size = Path(where).stat().st_size
        else:
            req = urllib.request.Request(where, method="HEAD")
            with urllib.request.urlopen(req, timeout=60) as r:
                self.size = int(r.headers["Content-Length"])

    def read(self, start, n):
        if n <= 0:
            return b""
        if self.local:
            with open(self.where, "rb") as f:
                f.seek(start)
                return f.read(n)
        req = urllib.request.Request(self.where, headers={"Range": f"bytes={start}-{start + n - 1}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        if len(data) != n:
            raise IOError(f"short range read at {start}: {len(data)} of {n}")
        return data

    def stream(self, start, n, out, chunk=8 << 20):
        h = hashlib.sha256()
        with open(out, "wb") as f:
            done = 0
            while done < n:
                piece = self.read(start + done, min(chunk, n - done))
                f.write(piece)
                h.update(piece)
                done += len(piece)
        return h.digest()


def central_directory(src):
    """{name: dict(method, csize, usize, local_offset)} from the zip's end (ZIP64 aware)."""
    tail = src.read(max(0, src.size - 66000), min(src.size, 66000))
    base = max(0, src.size - 66000)
    e = tail.rfind(b"PK\x05\x06")
    if e < 0:
        raise ValueError("no zip end-of-central-directory record")
    count, cd_size, cd_off = struct.unpack_from("<HII", tail, e + 10)
    loc = tail.rfind(b"PK\x06\x07", 0, e)
    if loc >= 0:  # ZIP64
        z64 = struct.unpack_from("<Q", tail, loc + 8)[0]
        rec = src.read(z64, 56)
        count, cd_size, cd_off = struct.unpack_from("<QQQ", rec, 32)
    cd = src.read(cd_off, cd_size)
    entries, i = {}, 0
    for _ in range(count):
        if cd[i:i + 4] != b"PK\x01\x02":
            raise ValueError("corrupt central directory")
        method, = struct.unpack_from("<H", cd, i + 10)
        csize, usize = struct.unpack_from("<II", cd, i + 20)
        nlen, xlen, clen = struct.unpack_from("<HHH", cd, i + 28)
        off, = struct.unpack_from("<I", cd, i + 42)
        name = cd[i + 46:i + 46 + nlen].decode()
        extra = cd[i + 46 + nlen:i + 46 + nlen + xlen]
        j = 0
        while j + 4 <= len(extra):  # ZIP64 extended information
            tag, sz = struct.unpack_from("<HH", extra, j)
            if tag == 1:
                vals, k = [], j + 4
                for present in (usize == 0xFFFFFFFF, csize == 0xFFFFFFFF, off == 0xFFFFFFFF):
                    if present:
                        vals.append(struct.unpack_from("<Q", extra, k)[0])
                        k += 8
                it = iter(vals)
                usize = next(it) if usize == 0xFFFFFFFF else usize
                csize = next(it) if csize == 0xFFFFFFFF else csize
                off = next(it) if off == 0xFFFFFFFF else off
            j += 4 + sz
        entries[name] = dict(method=method, csize=csize, usize=usize, local_offset=off)
        i += 46 + nlen + xlen + clen
    return entries


def data_offset(src, entry):
    head = src.read(entry["local_offset"], 30)
    if head[:4] != b"PK\x03\x04":
        raise ValueError("bad local file header")
    nlen, xlen = struct.unpack_from("<HH", head, 26)
    return entry["local_offset"] + 30 + nlen + xlen


def read_entry(src, entry):
    raw = src.read(data_offset(src, entry), entry["csize"])
    if entry["method"] == 0:
        return raw
    if entry["method"] == 8:
        return zlib.decompress(raw, -15)
    raise ValueError(f"unsupported zip method {entry['method']}")


def sha_prefix(path, n):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        left = n
        while left:
            b = f.read(min(left, 8 << 20))
            if not b:
                return None  # stock image shorter than the old partition
            h.update(b)
            left -= len(b)
    return h.hexdigest()


def inspect(src, stock=None):
    entries = central_directory(src)
    missing = [w for w in WANTED if w not in entries]
    if "payload.bin" in missing:
        raise ValueError("not an A/B OTA package (no payload.bin)")
    if entries["payload.bin"]["method"] != 0:
        raise ValueError("payload.bin is compressed; A/B OTAs store it")
    props = read_entry(src, entries["payload_properties.txt"]).decode() if "payload_properties.txt" in entries else ""
    meta_text = read_entry(src, entries["META-INF/com/android/metadata"]).decode(errors="replace") \
        if "META-INF/com/android/metadata" in entries else ""
    meta = dict(l.split("=", 1) for l in meta_text.splitlines() if "=" in l)
    poff = data_offset(src, entries["payload.bin"])
    head = src.read(poff, 24)
    if head[:4] != b"CrAU":
        raise ValueError("payload.bin is not an update_engine payload")
    major, msize = struct.unpack(">QQ", head[4:20])
    manifest = fit.parse_manifest(src.read(poff + 24, msize))
    parts = []
    for p in manifest["partitions"]:
        row = dict(name=p["name"], old_size=p["old_size"], new_size=p["new_size"], old_hash=p["old_hash"],
                   new_hash=p["new_hash"])
        if stock is not None and p["old_size"]:
            img = Path(stock) / f"{p['name']}.img"
            row["stock_matches"] = img.is_file() and sha_prefix(img, p["old_size"]) == p["old_hash"]
        parts.append(row)
    full = all(p["old_size"] == 0 for p in manifest["partitions"])
    return dict(
        schema="openbook-google-ota-inspection/1", zip_bytes=src.size,
        ota_type=meta.get("ota-type"), pre_build=meta.get("pre-build"), post_build=meta.get("post-build"),
        pre_build_incremental=meta.get("pre-build-incremental"), post_build_incremental=meta.get("post-build-incremental"),
        post_timestamp=meta.get("post-timestamp"), pre_device=meta.get("pre-device"),
        kind="full" if full else "incremental", payload_offset=poff,
        payload_bytes=entries["payload.bin"]["usize"], payload_properties=props, major_version=major,
        minor_version=manifest["minor_version"], vabc_compression=manifest["vabc_compression"],
        groups=manifest["groups"], partitions=parts,
        stock_source_matches=(all(r.get("stock_matches") for r in parts if r["old_size"]) if stock and not full
                              else None),
        zip_entries=sorted(entries))


def download(src, info, out):
    props = dict(l.split("=", 1) for l in info["payload_properties"].splitlines() if "=" in l)
    digest = src.stream(info["payload_offset"], info["payload_bytes"], out / "payload.bin")
    (out / "payload_properties.txt").write_text(info["payload_properties"])
    ok_size = str(info["payload_bytes"]) == props.get("FILE_SIZE")
    ok_hash = base64.b64encode(digest).decode() == props.get("FILE_HASH")
    return dict(payload=str(out / "payload.bin"), size_matches=ok_size, hash_matches=ok_hash,
                sha256=digest.hex())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--offer", type=Path, help="offer.json from capture-google-ota.py")
    g.add_argument("--url", help="OTA zip URL or local path")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--stock", type=Path, help="our stock images (<partition>.img) for the source-hash check")
    p.add_argument("--download", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    a.out.mkdir(mode=0o700, parents=True, exist_ok=True)
    url = json.loads(a.offer.read_text())["url"] if a.offer else a.url
    if not url:
        sys.exit("the offer has no URL")
    src = Source(url)
    info = inspect(src, a.stock)
    if a.download:
        info["download"] = download(src, info, a.out)
    (a.out / "inspection.json").write_text(json.dumps(info, indent=2) + "\n")
    summary = {k: info[k] for k in ("kind", "ota_type", "pre_build_incremental", "post_build_incremental",
                                    "post_build", "zip_bytes", "payload_bytes", "minor_version",
                                    "vabc_compression", "stock_source_matches")}
    summary["partitions"] = [(r["name"], r["old_size"], r["new_size"], r.get("stock_matches")) for r in info["partitions"]]
    if "download" in info:
        summary["download"] = {k: info["download"][k] for k in ("size_matches", "hash_matches")}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
