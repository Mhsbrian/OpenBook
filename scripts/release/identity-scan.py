#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Find a private identity (an email address or a name) in release files without ever printing it (ANAL-341).

usage: identity-scan.py [--ids FILE] PATH...          scan files and directories; exit 1 on any hit
       identity-scan.py [--ids FILE] --add email|word  read one value from stdin and add its hash to FILE

The list holds SHA-256 hashes of lower-cased values, one "<kind> <hash> [<letters>]" per line, never the values
themselves. A word's length lets the scan hash only words of that length; without it every word is hashed (slow).
Default: $OPENBOOK_PRIVATE_IDS, else <data dir>/private/identity/ids.sha256 (outside Git). An "email" entry matches
an address anywhere; a "word" entry matches a whole word (letters only), and any part of an address.

What is opened, recursively: directories, tar (any compression), zip (apk, jar, apex), gzip, xz, bzip2, zstd and
lz4 streams, EROFS images (extracted with fsck.erofs, found on PATH or in $AOSP_HOST_BIN, at most 10 minutes each)
and an x86 bzImage's compressed payload. ext4 is not extracted: it stores file data uncompressed, so the raw search
covers it, and test suites ship deliberately broken ext4 images that hang debugfs. Every blob is also searched as
raw bytes, in ASCII and UTF-16LE, and every
name inside a container is searched too. A hit prints the container path, the entry's kind and line number in the
list, and a count. A path that itself matches is printed with that part redacted.
"""
import argparse
import bz2
import getpass
import gzip
import hashlib
import io
import lzma
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile

CHUNK = 16 << 20
OVERLAP = 512
# A decompressed stream stops here and is reported: test suites ship tiny files that expand to sparse disk images
# of many GB (e2fsprogs). Chunks of zeros are skipped without searching.
MAX_STREAM = 4 << 30
MAX_DEPTH = 10
# Addresses are found from each "@": a local part of at most 64 characters before it, a domain of at most 9 labels
# after it (RFC 5321). Sliding a whole-address pattern over every byte of plain text was ~64 steps per byte.
LOCAL = re.compile(rb"[A-Za-z0-9._%+\-]{1,64}\Z")
DOMAIN = re.compile(rb"[A-Za-z0-9\-]{1,63}(?:\.[A-Za-z0-9\-]{1,63}){1,8}")
LOCAL16 = re.compile(rb"(?:[A-Za-z0-9._%+\-]\x00){1,64}\Z")
DOMAIN16 = re.compile(rb"(?:[A-Za-z0-9\-]\x00){1,63}(?:\.\x00(?:[A-Za-z0-9\-]\x00){1,63}){1,8}")


def addresses(data, at=b"@", local=LOCAL, domain=DOMAIN, width=1):
    i = data.find(at)
    while i != -1:
        m = local.search(data, max(0, i - 64 * width), i)
        if m:
            d = domain.match(data, i + len(at))
            if d:
                yield data[m.start():d.end()]
        i = data.find(at, i + 1)


ALPHA = re.compile(rb"[A-Za-z]+")


def h(b):
    return hashlib.sha256(b.lower()).hexdigest()


def default_ids():
    if os.environ.get("OPENBOOK_PRIVATE_IDS"):
        return os.environ["OPENBOOK_PRIVATE_IDS"]
    home = os.environ.get("OPENBOOK_HOME") or os.environ.get("ANYBOOK_HOME") or os.path.expanduser("~/anybook")
    return os.path.join(home, "private", "identity", "ids.sha256")


class Ids:
    def __init__(self, path):
        self.email, self.word, lengths = {}, {}, set()
        for n, line in enumerate(open(path), 1):
            f = line.split()
            if len(f) in (2, 3) and f[0] in ("email", "word") and re.fullmatch(r"[0-9a-f]{64}", f[1]):
                getattr(self, f[0])[f[1]] = f"{f[0]}#{n}"
                if f[0] == "word":
                    lengths.add(int(f[2]) if len(f) == 3 else 0)
        if not self.email and not self.word:
            sys.exit(f"identity-scan: {path} lists no identities")
        # whole words of the listed lengths are hashed; a word listed without its length means every word of 3..40
        self.min, self.max = 3, 40
        if lengths and 0 not in lengths:
            self.min, self.max = min(lengths), max(lengths)
            self.words = re.compile(rb"(?<![A-Za-z])(?:" + b"|".join(b"[A-Za-z]{%d}" % n for n in sorted(lengths))
                                    + rb")(?![A-Za-z])")
        else:
            self.words = ALPHA

    def hits(self, data, out):
        for addr in addresses(data):
            self._email(addr, out)
        for addr in addresses(data, b"@\x00", LOCAL16, DOMAIN16, 2):
            self._email(addr[::2], out)
        if self.word:
            for m in self.words.finditer(data):
                w = m.group()
                if self.min <= len(w) <= self.max:
                    k = self.word.get(h(w))
                    if k:
                        out[k] = out.get(k, 0) + 1

    def _email(self, addr, out):
        if len(addr) > 254:
            return
        k = self.email.get(h(addr))
        if k:
            out[k] = out.get(k, 0) + 1
        if self.word:  # a listed name inside an address: every substring of the address's letter runs
            for run in ALPHA.findall(addr):
                run = run.lower()
                for i in range(len(run)):
                    for j in range(i + self.min, min(len(run), i + self.max) + 1):
                        k = self.word.get(hashlib.sha256(run[i:j]).hexdigest())
                        if k:
                            out[k] = out.get(k, 0) + 1


class Scanner:
    def __init__(self, ids, tools):
        self.ids, self.tools = ids, tools
        self.found, self.blobs, self.bytes, self.unopened = {}, 0, 0, {}

    def label(self, path):
        hits = {}
        self.ids.hits(path.encode("utf-8", "surrogateescape"), hits)
        return f"<redacted name matching {','.join(sorted(hits))}>" if hits else path

    def record(self, path, hits):
        if hits:
            r = self.found.setdefault(path, {})
            for k, v in hits.items():
                r[k] = r.get(k, 0) + v

    def name(self, container, name):
        hits = {}
        self.ids.hits(name.encode("utf-8", "surrogateescape"), hits)
        if hits:
            self.record(f"{container} (an entry's name)", hits)
        return f"{container}!{self.label(name)}"

    def raw(self, path, f, head=b"", limit=None):
        """Search a stream's raw bytes; returns how many bytes were read."""
        hits, tail, n = {}, b"", 0
        buf = head
        while True:
            chunk = f.read(CHUNK)
            if chunk:
                buf += chunk
            if not buf:
                break
            if buf.count(0) == len(buf):
                tail = b""
            else:
                data = tail + buf
                self.ids.hits(data, hits)
                tail = data[-OVERLAP:]
            n += len(buf)
            buf = b""
            if not chunk:
                break
            if limit and n >= limit:
                self.unopened["stream cut at 4 GiB"] = self.unopened.get("stream cut at 4 GiB", 0) + 1
                break
        # an overlap can count one hit twice; a count says "present", it is not a measurement
        self.record(path, hits)
        self.bytes += n
        return n

    def blob(self, path, f, depth, size=None, fspath=None, limit=None):
        """Scan one blob: raw bytes always, then whatever it contains."""
        self.blobs += 1
        head = f.read(4096)
        kind = sniff(head, size)
        if depth >= MAX_DEPTH:
            self.unopened[kind or "raw"] = self.unopened.get(kind or "raw", 0) + 1
            kind = None
        if kind in ("erofs", "zip", "bzimage"):
            # needs random access: work on the file itself, or a temporary copy
            if fspath is None:
                with tempfile.NamedTemporaryFile(dir=self.tools["tmp"], delete=False) as t:
                    t.write(head)
                    shutil.copyfileobj(f, t, CHUNK)
                    fspath = t.name
                try:
                    self.raw(path, open(fspath, "rb"))
                    self.open_random(path, fspath, kind, depth)
                finally:
                    os.unlink(fspath)
            else:
                self.raw(path, f, head)
                self.open_random(path, fspath, kind, depth)
            return
        if kind in ("gzip", "xz", "bzip2", "zstd", "lz4"):
            # compressed bytes say nothing; the stream is searched decompressed
            with decompress(kind, head, f) as d:
                self.blob(f"{path}|{kind}", d, depth + 1, limit=MAX_STREAM)
            return
        if kind == "tar":
            stream = Prefixed(head, f)
            self.tar(path, stream, depth)
            return
        self.raw(path, f, head, limit)

    def tar(self, path, stream, depth):
        with tarfile.open(fileobj=stream, mode="r|") as t:
            for m in t:
                p = self.name(path, m.name)
                if m.isfile() and m.issparse() and m.sparse:
                    # a sparse member (a 2 TB test disk image in exfatprogs): only its stored regions hold bytes
                    self.blobs += 1
                    self.raw(p, Stored(t, m))
                elif m.isfile():
                    self.blob(p, t.extractfile(m), depth + 1, size=m.size)
                elif m.issym() or m.islnk():
                    self.name(path, m.linkname)

    def open_random(self, path, fspath, kind, depth):
        if kind == "zip":
            try:
                z = zipfile.ZipFile(fspath)
            except zipfile.BadZipFile:
                return
            with z:
                for i in z.infolist():
                    p = self.name(path, i.filename)
                    if not i.is_dir():
                        try:
                            with z.open(i) as m:
                                self.blob(p, m, depth + 1, size=i.file_size)
                        except (NotImplementedError, zipfile.BadZipFile, RuntimeError, OSError, EOFError, lzma.LZMAError):
                            self.unopened["zip member"] = self.unopened.get("zip member", 0) + 1
        elif kind == "bzimage":
            with open(fspath, "rb") as b:
                hdr = b.read(0x260)
                setup = (hdr[0x1F1] or 4) + 1
                off = int.from_bytes(hdr[0x248:0x24C], "little")
                ln = int.from_bytes(hdr[0x24C:0x250], "little")
                start = setup * 512 + off
                if start + ln > os.path.getsize(fspath):  # not a real bzImage: the raw search was enough
                    return
                b.seek(start)
                payload = b.read(ln)
            self.blob(f"{path}|payload", io.BytesIO(payload), depth + 1, size=len(payload))
        else:
            d = tempfile.mkdtemp(dir=self.tools["tmp"])
            try:
                try:
                    r = subprocess.run([self.tools["fsck.erofs"], "--extract=" + d, "--no-preserve", fspath],
                                       capture_output=True, timeout=600)
                except subprocess.TimeoutExpired:
                    r = None
                if r is None or (r.returncode != 0 and not os.listdir(d)):
                    self.unopened[kind] = self.unopened.get(kind, 0) + 1
                    return
                self.tree(f"{path}|{kind}", d, depth + 1)
            finally:
                shutil.rmtree(d, ignore_errors=True)

    def tree(self, label, root, depth):
        for dp, dns, fns in os.walk(root):
            dns.sort()
            for fn in sorted(fns + [x for x in dns if os.path.islink(os.path.join(dp, x))]):
                full = os.path.join(dp, fn)
                rel = os.path.relpath(full, root)
                p = self.name(label, rel)
                st = os.lstat(full)
                if stat.S_ISLNK(st.st_mode):
                    self.name(label, os.readlink(full))
                elif stat.S_ISREG(st.st_mode):
                    with open(full, "rb") as f:
                        self.blob(p, f, depth, size=st.st_size, fspath=full)

    def path(self, p):
        st = os.lstat(p)
        if stat.S_ISDIR(st.st_mode):
            self.tree(self.label(p), p, 0)
        elif stat.S_ISREG(st.st_mode):
            with open(p, "rb") as f:
                self.blob(self.label(p), f, 0, size=st.st_size, fspath=p)


class Stored(io.RawIOBase):
    """A sparse tar member's stored bytes: its data regions, back to back in the archive right after its header."""

    def __init__(self, t, m):
        self.fo, self.left = t.fileobj, sum(n for _, n in m.sparse)
        if self.fo.tell() < m.offset_data:
            self.fo.seek(m.offset_data)

    def readable(self):
        return True

    def read(self, n=-1):
        if self.left <= 0:
            return b""
        d = self.fo.read(self.left if n is None or n < 0 else min(n, self.left))
        self.left -= len(d)
        return d


class Prefixed(io.RawIOBase):
    """A stream with bytes already read put back in front."""

    def __init__(self, head, f):
        self.head, self.f = head, f

    def readable(self):
        return True

    def readinto(self, b):
        if self.head:
            n = min(len(b), len(self.head))
            b[:n] = self.head[:n]
            self.head = self.head[n:]
            return n
        d = self.f.read(len(b))
        b[:len(d)] = d
        return len(d)

    def read(self, n=-1):
        if n is None or n < 0:
            d, self.head = self.head + self.f.read(), b""
            return d
        if self.head:
            d, self.head = self.head[:n], self.head[n:]
            if len(d) < n:
                d += self.f.read(n - len(d))
            return d
        return self.f.read(n)


class decompress:
    def __init__(self, kind, head, f):
        src = Prefixed(head, f)
        self.proc = None
        if kind == "gzip":
            self.s = gzip.GzipFile(fileobj=io.BufferedReader(src, CHUNK))
        elif kind == "xz":
            self.s = lzma.LZMAFile(io.BufferedReader(src, CHUNK))
        elif kind == "bzip2":
            self.s = bz2.BZ2File(io.BufferedReader(src, CHUNK))
        else:  # zstd, lz4: the command-line tools, fed from a thread-free pipe through a temporary file
            self.tmp = tempfile.TemporaryFile()
            shutil.copyfileobj(src, self.tmp, CHUNK)
            self.tmp.seek(0)
            self.proc = subprocess.Popen([kind, "-dc"], stdin=self.tmp, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL)
            self.s = self.proc.stdout

    def __enter__(self):
        return Tolerant(self.s)

    def __exit__(self, *a):
        self.s.close()
        if self.proc:
            self.proc.wait()
            self.tmp.close()


class Tolerant(io.RawIOBase):
    """Decompressed bytes up to the first error: trailing padding after a kernel's payload is not an error."""

    def __init__(self, s):
        self.s, self.done = s, False

    def readable(self):
        return True

    def read(self, n=-1):
        if self.done:
            return b""
        try:
            return self.s.read(n)
        except (EOFError, OSError, lzma.LZMAError, ValueError):
            self.done = True
            return b""

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)


def sniff(head, size):
    if head.startswith(b"\x1f\x8b"):
        return "gzip"
    if head.startswith(b"\xfd7zXZ\x00"):
        return "xz"
    if head.startswith(b"BZh") and len(head) > 4 and head[3:4].isdigit():
        return "bzip2"
    if head.startswith(b"\x28\xb5\x2f\xfd"):
        return "zstd"
    if head.startswith(b"\x02\x21\x4c\x18") or head.startswith(b"\x04\x22\x4d\x18"):
        return "lz4"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "zip"
    if len(head) >= 265 and head[257:262] == b"ustar":
        return "tar"
    if len(head) >= 0x250 and head[0x202:0x206] == b"HdrS" and int.from_bytes(head[0x24C:0x250], "little"):
        return "bzimage"
    if len(head) >= 1028 and head[1024:1028] == b"\xe2\xe1\xf5\xe0":
        return "erofs"
    if len(head) >= 1082 and head[1080:1082] == b"\x53\xef":
        return "ext4"
    return None


def find_tool(name):
    for d in [os.environ.get("AOSP_HOST_BIN", "")] + os.environ.get("PATH", "").split(":"):
        p = os.path.join(d, name)
        if d and os.access(p, os.X_OK):
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ids", default=default_ids())
    ap.add_argument("--add", choices=("email", "word"))
    ap.add_argument("--tmp", default=None, help="scratch for extracted images (default: $TMPDIR)")
    ap.add_argument("paths", nargs="*")
    a = ap.parse_args()
    if a.add:
        v = (getpass.getpass(f"{a.add} (not shown): ") if sys.stdin.isatty() else sys.stdin.readline()).strip()
        if not v:
            sys.exit("identity-scan: empty value")
        os.makedirs(os.path.dirname(a.ids), mode=0o700, exist_ok=True)
        fd = os.open(a.ids, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        os.write(fd, (f"{a.add} {h(v.encode())}" + (f" {len(v)}" if a.add == "word" else "") + "\n").encode())
        os.close(fd)
        print(f"identity-scan: added one {a.add} to {a.ids}")
        return
    if not a.paths:
        ap.error("nothing to scan")
    if not os.path.exists(a.ids):
        sys.exit(f"identity-scan: no identity list at {a.ids} (add entries with --add email|word)")
    tools = {"tmp": a.tmp or tempfile.gettempdir()}
    for t in ("fsck.erofs",):
        tools[t] = find_tool(t) or t
    s = Scanner(Ids(a.ids), tools)
    for p in a.paths:
        s.path(p)
    for p, hits in sorted(s.found.items()):
        print("HIT", p, " ".join(f"{k} x{v}" for k, v in sorted(hits.items())))
    left = ", ".join(f"{k} {v}" for k, v in sorted(s.unopened.items()))
    print(f"identity-scan: {len(s.found)} hit(s); {s.blobs} blobs, {s.bytes / 1e9:.2f} GB searched"
          + (f"; not opened: {left}" if left else ""))
    sys.exit(1 if s.found else 0)


if __name__ == "__main__":
    main()
