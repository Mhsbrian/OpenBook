#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""scripts/quire/linux-env-sources.py on a synthetic image (ANAL-393; the Checker's Hold 3 on PR #15).

usage: tests/quire/linux-env-sources-test.py

Builds a small guest image (ext4 root with a dpkg status, one Debian source, quired, a copyright file), a fake AOSP
builder tree, and serves the "network" from memory: snapshot.debian.org's API and files, and each component's tarball.
A complete bundle must pass --check; each missing, empty or corrupt part must fail it, naming that part. Needs
mke2fs, debugfs and git. Writes only under a temporary folder.
"""
import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from types import SimpleNamespace

R = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("les", R / "scripts/quire/linux-env-sources.py")
les = importlib.util.module_from_spec(spec)
spec.loader.exec_module(les)

passed, failed = 0, []


def ok(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print(f"PASS {name}")
    else:
        failed.append(name)
        print(f"FAIL {name} {detail}")


def tgz(files: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in files.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def sh(*cmd, cwd=None):
    subprocess.run(cmd, check=True, cwd=cwd, capture_output=True)


def image(root: Path, out: Path, quired_version: str):
    (root / "var/lib/dpkg").mkdir(parents=True)
    (root / "var/lib/dpkg/status").write_text(
        "Package: hello\nStatus: install ok installed\nVersion: 1.0-1\n\n"
        "Package: libhello1\nStatus: install ok installed\nSource: hello\nVersion: 1.0-1\n\n"
        f"Package: quired\nStatus: install ok installed\nVersion: {quired_version}\n\n"
        "Package: gone\nStatus: deinstall ok config-files\nVersion: 9\n")
    (root / "usr/share/doc/hello").mkdir(parents=True)
    (root / "usr/share/doc/hello/copyright").write_text("hello: GPL-3+\n")
    out.mkdir(parents=True)
    sh("mke2fs", "-q", "-t", "ext4", "-d", str(root), str(out / "root_part"), "8M")
    sh("tar", "-czf", "images.tar.gz", "root_part", cwd=out)
    (out / "root_part").unlink()
    (out / "image-info.txt").write_text("build_id=synthetic-1\n")


def aosp(tree: Path):
    v = tree / "packages/modules/Virtualization"
    (v / "build/debian/ttyd").mkdir(parents=True)
    (v / "guest").mkdir(parents=True)
    (v / "build/debian/build.sh").write_text("#!/bin/sh\n")
    (v / "build/debian/ttyd/cross-build.sh").write_text("#!/bin/sh\n# cross\n")
    (v / "build/debian/ttyd/xtermjs_a11y.patch").write_text("--- a\n+++ b\n")
    (v / "guest/README").write_text("guest agent\n")
    sh("git", "init", "-q", cwd=v)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t.invalid", "add", "-A", cwd=v)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-qm", "base", cwd=v)


def network():
    """The responses, by URL, and the patched component pins."""
    orig = b"hello source " * 100
    deb = b"hello debian " * 10
    sums = "".join(f" {hashlib.sha256(d).hexdigest()} {len(d)} {n}\n"
                   for n, d in (("hello_1.0.orig.tar.gz", orig), ("hello_1.0-1.debian.tar.xz", deb)))
    dsc = ("Format: 3.0 (quilt)\nSource: hello\nVersion: 1.0-1\nChecksums-Sha256:\n" + sums).encode()
    files = {"hello_1.0-1.dsc": dsc, "hello_1.0.orig.tar.gz": orig, "hello_1.0-1.debian.tar.xz": deb}
    web = {}
    info = {"result": [], "fileinfo": {}}
    for n, d in files.items():
        h = hashlib.sha1(d).hexdigest()
        info["result"].append({"hash": h})
        info["fileinfo"][h] = [{"name": n}]
        web[f"{les.SNAPSHOT}/file/{h}"] = d
    web[f"{les.SNAPSHOT}/mr/package/hello/1.0-1/srcfiles?fileinfo=1"] = json.dumps(info).encode()
    comps = []
    for name, ver, *_ in les.COMPONENTS:
        data = tgz({f"{name}-{ver}/LICENSE": f"{name} licence\n".encode(), f"{name}-{ver}/src.c": b"int x;\n"})
        url = f"https://components.invalid/{name}-{ver}.tar.gz"
        web[url] = data
        comps.append((name, ver, url, hashlib.sha256(data).hexdigest(), "MIT"))
    rle = b"GCC RUNTIME LIBRARY EXCEPTION\n"
    web["https://gcc.invalid/COPYING.RUNTIME"] = rle
    return web, comps, ("https://gcc.invalid/COPYING.RUNTIME", hashlib.sha256(rle).hexdigest())


def problems(img, bundle, tree):
    return les.check(img, bundle, tree)


def has(bad, pattern):
    return any(re.search(pattern, p) for p in bad)


def main():
    for tool in ("mke2fs", "debugfs", "git"):
        if not shutil.which(tool):
            print(f"SKIP: no {tool}")
            return 0
    version = re.search(r'^var version = "([^"]+)"', (R / "quire/quired/main.go").read_text(), re.M).group(1)
    with tempfile.TemporaryDirectory(prefix="les-test.") as d:
        d = Path(d)
        image(d / "root", d / "img", version)
        aosp(d / "aosp")
        web, comps, rle = network()
        les.get = lambda url, tries=3: web[url]
        les.COMPONENTS = comps
        les.GCC_RLE = rle
        good = d / "bundle"
        les.make(SimpleNamespace(image_out=d / "img", bundle=good, aosp=d / "aosp", no_fetch=False))
        bad = problems(d / "img", good, d / "aosp")
        ok("a complete bundle passes", not bad, "; ".join(bad))
        rows = (good / "debian/packages.tsv").read_text()
        ok("quired is listed as OpenBook's, not fetched from Debian", "quired\t" in rows and "\topenbook" in rows
           and not (good / "debian" / f"quired_{version}").exists())
        ok("a removed package's config files are not listed", "gone\t" not in rows)

        def case(name, change, pattern):
            b = d / f"case-{len(failed) + passed}"
            shutil.copytree(good, b)
            change(b)
            got = problems(d / "img", b, d / "aosp")
            ok(name, has(got, pattern), "; ".join(got) or "no problem reported")
            shutil.rmtree(b)

        src = "debian/hello_1.0-1"
        case("an empty .dsc fails", lambda b: (b / src / "hello_1.0-1.dsc").write_bytes(b""), r"hello 1\.0-1: its \.dsc")
        case("a missing original tarball fails", lambda b: (b / src / "hello_1.0.orig.tar.gz").unlink(),
             r"hello_1\.0\.orig\.tar\.gz is missing")
        case("a corrupt original tarball fails", lambda b: (b / src / "hello_1.0.orig.tar.gz").write_bytes(b"x"),
             r"orig\.tar\.gz doesn't match its \.dsc")
        case("no Debian source at all fails", lambda b: shutil.rmtree(b / src), r"no source for hello 1\.0-1")

        def empty_components(b):
            for name, ver, url, *_ in comps:
                (b / "components" / name / url.rsplit("/", 1)[-1]).write_bytes(b"")
        case("empty component tarballs fail (the Checker's case)", empty_components,
             r"ttyd 1\.7\.7: .* doesn't match its pinned sha256")

        def checker_case(b):
            (b / src / "hello_1.0-1.dsc").write_bytes(b"")
            empty_components(b)
        case("an empty .dsc and empty tarballs report both", checker_case, r"its \.dsc")
        case("missing musl source fails", lambda b: shutil.rmtree(b / "components/musl"), r"no source for musl")
        case("a missing component licence fails", lambda b: shutil.rmtree(b / "LICENSES/components/zlib"),
             r"zlib: no licence")
        case("a missing copyright file fails", lambda b: (b / "LICENSES/debian/hello/copyright").unlink(),
             r"LICENSES/debian/hello/copyright")
        case("a missing GCC runtime exception fails", lambda b: (b / "LICENSES/components/libgcc/COPYING.RUNTIME").unlink(),
             r"runtime library exception")
        case("an empty build tarball fails", lambda b: (b / "build/openbook-quire.tar").write_bytes(b""),
             r"build/openbook-quire\.tar")
        case("a missing ttyd patch fails", lambda b: (b / "components/ttyd-xtermjs_a11y.patch").unlink(),
             r"ttyd-xtermjs_a11y\.patch is missing")
        case("a bundle for another image fails", lambda b: (b / "IMAGE.json").write_text(
            json.dumps({"images.tar.gz": {"sha256": "0" * 64, "size": 1}, "build_id": "x"})), r"for another image")
        case("an extra file not in the manifest fails", lambda b: (b / "extra.txt").write_text("x"), r"extra\.txt")
        case("a changed package list fails", lambda b: (b / "debian/packages.tsv").write_text(
            rows.replace("1.0-1\thello\t1.0-1", "1.0-2\thello\t1.0-2", 1)), r"packages\.tsv doesn't match")

        # quired's source must be the installed version.
        other = d / "img2"
        image(d / "root2", other, "9.9.9")
        b2 = d / "bundle2"
        les.make(SimpleNamespace(image_out=other, bundle=b2, aosp=d / "aosp", no_fetch=False))
        got = problems(other, b2, d / "aosp")
        ok("quired's source at another version fails", has(got, r"quired 9\.9\.9 is installed"), "; ".join(got))

        # The fetch refuses a component that doesn't match its pin.
        web[comps[0][2]] = b"changed upstream"
        try:
            les.make(SimpleNamespace(image_out=d / "img", bundle=d / "bundle3", aosp=d / "aosp", no_fetch=False))
            ok("a changed upstream tarball stops the fetch", False)
        except SystemExit as e:
            ok("a changed upstream tarball stops the fetch", "pinned sha256" in str(e), str(e))
    print(f"{passed} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
