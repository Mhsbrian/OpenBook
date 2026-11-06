#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""The source bundle that goes with a released Linux environment image (ANAL-393, docs/quire-setup.md §7).

usage: linux-env-sources.py IMAGE_OUT BUNDLE_DIR [--aosp AOSP] [--no-fetch]
       linux-env-sources.py --check IMAGE_OUT BUNDLE_DIR [--aosp AOSP]

IMAGE_OUT is scripts/quire/linux-env-image.sh's output folder (images.tar.gz, image-info.txt). Everything comes from
the image's own records, so the bundle matches the bytes that ship:

  IMAGE.json              the image it belongs to: images.tar.gz's sha256 and size, its build_id
  debian/packages.tsv     every installed package of the guest (dpkg status), its source package and version, and
                          where that source is: debian (snapshot.debian.org) or openbook (this repository)
  debian/<src>_<ver>/     each Debian source package's files (.dsc, original and Debian tarballs), the kernel's
                          included, checked against the archive's SHA-1 when fetched and the .dsc's SHA-256 after
  components/             ttyd, the libraries AOSP's builder links into it, and musl's source at the commit the
                          builder's toolchain was made from; each pinned by sha256 here (COMPONENTS), with AOSP's ttyd
                          patch and build script
  build/                  AOSP's guest builder and guest agent at the tree's revision; OpenBook's patch, scripts and
                          quire/ (quired, the image's one OpenBook package, and its units)
  LICENSES/               every /usr/share/doc/*/copyright of the image (LICENSES/debian/INDEX.tsv lists them), each
                          component's licence, and GCC's runtime library exception (libgcc is in ttyd)
  NOTICE, MANIFEST.tsv    what the bundle holds, and the sha256 of every file in it

--check fails, naming each problem, unless all of that is there and intact: the image's hash matches IMAGE.json; the
package list matches the image; every Debian source has a .dsc for that source and version whose listed files are all
present with their sizes and SHA-256; quired's source in build/ has the installed version; every component matches its
pin and holds its licence; every copyright file the image has is in LICENSES/; the build inputs hold what they should;
and MANIFEST.tsv matches the files. make-release.sh --linux-env runs it before it signs a release that carries the
image. Reads the image without mounting it (debugfs). Writes only under BUNDLE_DIR (its .scratch/ is removed).
"""
import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

R = Path(__file__).resolve().parents[2]
SNAPSHOT = "https://snapshot.debian.org"
UA = {"User-Agent": "openbook-linux-env-sources/1"}

# The image's own packages, built from this repository rather than fetched from Debian.
LOCAL = {"quired": "openbook"}

# Everything outside Debian that ends up in the image, at the versions AOSP's builder uses
# (packages/modules/Virtualization/build/debian: ttyd/cross-build.sh, build_internal.sh), pinned by sha256
# (fetched 2026-11-06). A changed upstream tarball fails the fetch instead of entering a release.
COMPONENTS = [
    # name, version, url, sha256, licence
    ("ttyd", "1.7.7", "https://github.com/tsl0922/ttyd/archive/refs/tags/1.7.7.tar.gz",
     "039dd995229377caee919898b7bd54484accec3bba49c118e2d5cd6ec51e3650", "MIT"),
    ("zlib", "1.3.1", "https://github.com/madler/zlib/archive/refs/tags/v1.3.1.tar.gz",
     "17e88863f3600672ab49182f217281b6fc4d3c762bde361935e436a95214d05c", "Zlib"),
    ("json-c", "0.17", "https://s3.amazonaws.com/json-c_releases/releases/json-c-0.17.tar.gz",
     "7550914d58fb63b2c3546f3ccfbe11f1c094147bd31a69dcd23714d7956159e6", "MIT"),
    ("mbedtls", "2.28.5", "https://github.com/ARMmbed/mbedtls/archive/v2.28.5.tar.gz",
     "849e86b626e42ded6bf67197b64aa771daa54e2a7e2868dc67e1e4711959e5e3", "Apache-2.0 OR GPL-2.0-or-later"),
    ("libuv", "1.44.2", "https://dist.libuv.org/dist/v1.44.2/libuv-v1.44.2.tar.gz",
     "ccfcdc968c55673c6526d8270a9c8655a806ea92468afcbcabc2b16040f03cb4", "MIT"),
    ("libwebsockets", "4.3.3", "https://github.com/warmcat/libwebsockets/archive/v4.3.3.tar.gz",
     "6fd33527b410a37ebc91bb64ca51bdabab12b076bc99d153d7c5dd405e4bdf90", "MIT"),
    # The builder links ttyd with the musl cross toolchain of tsl0922/musl-toolchains 2021-11-23 (its tarball:
    # sha256 c5d410d9f82a4f24c549fe5d24f988f85b2679b452413a9f7e5f7b956f2fe7ea). Its libc.so reports
    # "Version 1.2.2-git-50-gb76f37fd": musl's source is that commit.
    ("musl", "1.2.2-git-50-gb76f37fd",
     "https://git.musl-libc.org/cgit/musl/snapshot/musl-b76f37fd5625d038141b52184956fb4b7838e9a5.tar.gz",
     "b65870590770e068c41d6f19d04f65588d52c546360bba78a72d67ac17e62903", "MIT"),
]
# libgcc (GCC 11.2.1 in that toolchain) is linked into ttyd under the GCC Runtime Library Exception, which needs no
# source; its text goes into LICENSES/.
GCC_RLE = ("https://raw.githubusercontent.com/gcc-mirror/gcc/releases/gcc-11/COPYING.RUNTIME",
           "9d6b43ce4d8de0c878bf16b54d8e7a10d9bd42b75178153e3af6a815bdc90f74")

BUILD_TARS = {
    "aosp-build-debian.tar": ["build/debian/build.sh", "build/debian/ttyd/cross-build.sh"],
    "aosp-guest.tar": ["guest/"],
    "openbook-quire.tar": ["quire/quired/main.go", "quire/linux-env/image/build-debian.patch",
                           "quire/linux-env/build-deb.sh", "scripts/quire/linux-env-image.sh"],
}
LICENSE_NAMES = re.compile(r"(^|/)(LICENSE|LICENSE\.txt|LICENSE\.md|COPYING|COPYRIGHT|LICENSE-[A-Za-z0-9.]+)$")


def run(*cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def image_record(image_out: Path):
    img = image_out / "images.tar.gz"
    info = (image_out / "image-info.txt").read_text() if (image_out / "image-info.txt").exists() else ""
    m = re.search(r"^build_id=(.*)$", info, re.M)
    return {"images.tar.gz": {"sha256": sha256(img), "size": img.stat().st_size},
            "build_id": m.group(1) if m else ""}


def root_part(image_out: Path, scratch: Path) -> Path:
    """The guest's root file system, extracted from images.tar.gz once."""
    rp = scratch / "root_part"
    if not rp.exists():
        scratch.mkdir(parents=True, exist_ok=True)
        run("tar", "-xzf", str(image_out / "images.tar.gz"), "-C", str(scratch), "root_part")
    return rp


def dpkg_status(rp: Path):
    """(package, version, source, source_version) for every installed package."""
    text = run("debugfs", "-R", "cat /var/lib/dpkg/status", str(rp))
    out = []
    for block in text.split("\n\n"):
        f = {}
        for line in block.splitlines():
            m = re.match(r"^([A-Za-z-]+): (.*)$", line)
            if m:
                f[m.group(1)] = m.group(2)
        if "Package" not in f or "install ok installed" not in f.get("Status", ""):
            continue
        ver = f.get("Version", "")
        src, sver = f["Package"], ver
        if "Source" in f:
            m = re.match(r"^(\S+)(?: \((\S+)\))?$", f["Source"])
            if m:
                src, sver = m.group(1), m.group(2) or ver
        out.append((f["Package"], ver, src, sver))
    if not out:
        raise SystemExit("no installed packages in the image's dpkg status")
    return sorted(out)


def image_copyrights(rp: Path, scratch: Path):
    """{package: bytes} of every /usr/share/doc/<package>/copyright that is a regular file in the image."""
    docs = scratch / "doc"
    if docs.exists():
        shutil.rmtree(docs)
    docs.mkdir(parents=True)
    run("debugfs", "-R", f"rdump /usr/share/doc {docs}", str(rp))
    out = {}
    for c in sorted((docs / "doc").glob("*/copyright")):
        if c.is_file() and not c.is_symlink():
            out[c.parent.name] = c.read_bytes()
    shutil.rmtree(docs)
    return out


def get(url: str, tries=3) -> bytes:
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return r.read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def fetch_source(src: str, ver: str, dest: Path):
    """A Debian source package's files from snapshot.debian.org, by the archive's own SHA-1 of each."""
    info = json.loads(get(f"{SNAPSHOT}/mr/package/{src}/{ver}/srcfiles?fileinfo=1"))
    names = []
    for h in info.get("result", []):
        sha1 = h["hash"]
        name = info["fileinfo"][sha1][0]["name"]
        t = dest / name
        if not (t.exists() and hashlib.sha1(t.read_bytes()).hexdigest() == sha1):
            data = get(f"{SNAPSHOT}/file/{sha1}")
            if hashlib.sha1(data).hexdigest() != sha1:
                raise IOError(f"{src} {ver}: {name} doesn't match the archive's SHA-1")
            dest.mkdir(parents=True, exist_ok=True)
            t.write_bytes(data)
        names.append(name)
    if not any(n.endswith(".dsc") for n in names):
        raise IOError(f"{src} {ver}: no .dsc on snapshot.debian.org")
    return names


def dsc_files(dsc: Path):
    """The .dsc's Source, Version and its Checksums-Sha256 entries as (sha256, size, name)."""
    text = dsc.read_text(errors="replace")
    # A signed .dsc wraps the fields in a PGP block; the fields are the same.
    src = re.search(r"^Source: (\S+)", text, re.M)
    ver = re.search(r"^Version: (\S+)", text, re.M)
    m = re.search(r"^Checksums-Sha256:\n((?: .+\n?)+)", text, re.M)
    files = []
    if m:
        for line in m.group(1).splitlines():
            parts = line.split()
            if len(parts) == 3:
                files.append((parts[0], int(parts[1]), parts[2]))
    return (src.group(1) if src else None), (ver.group(1) if ver else None), files


def tar_members(p: Path):
    with tarfile.open(p) as t:
        return t.getnames()


def licences_from_tarball(tgz: Path, dest: Path):
    n = 0
    with tarfile.open(tgz) as t:
        for m in t.getmembers():
            if not m.isfile() or not LICENSE_NAMES.search(m.name) or m.name.count("/") > 2:
                continue
            target = dest / m.name.split("/", 1)[-1]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(t.extractfile(m).read())
            n += 1
    return n


def build_inputs(aosp: Path, dest: Path):
    virt = aosp / "packages/modules/Virtualization"
    rev = run("git", "-C", str(virt), "rev-parse", "HEAD").strip()
    dest.mkdir(parents=True, exist_ok=True)
    with open(dest / "aosp-build-debian.tar", "wb") as f:
        subprocess.run(["git", "-C", str(virt), "archive", "--prefix=build/debian/", f"{rev}:build/debian"],
                       stdout=f, check=True)
    # The guest agent in cidata.iso is AOSP's prebuilt from the same project (its source: guest/ in that revision).
    with open(dest / "aosp-guest.tar", "wb") as f:
        subprocess.run(["git", "-C", str(virt), "archive", "--prefix=guest/", f"{rev}:guest"], stdout=f, check=True)
    with tarfile.open(dest / "openbook-quire.tar", "w") as t:
        for p in ("quire/linux-env", "quire/quired", "scripts/quire/linux-env-image.sh",
                  "scripts/quire/unmount-build-loops.sh", "scripts/quire/linux-env-sources.py"):
            t.add(R / p, arcname=p)
    return rev


def write_manifest(bundle: Path):
    rows = [f"{sha256(p)}\t{p.relative_to(bundle)}" for p in sorted(bundle.rglob("*"))
            if p.is_file() and p.name != "MANIFEST.tsv" and ".scratch" not in p.parts]
    (bundle / "MANIFEST.tsv").write_text("\n".join(rows) + "\n")
    return len(rows)


def make(a):
    b = a.bundle
    scratch = b / ".scratch"
    b.mkdir(parents=True, exist_ok=True)
    (b / "IMAGE.json").write_text(json.dumps(image_record(a.image_out), indent=1) + "\n")
    rp = root_part(a.image_out, scratch)
    pkgs = dpkg_status(rp)
    (b / "debian").mkdir(parents=True, exist_ok=True)
    (b / "debian/packages.tsv").write_text("package\tversion\tsource\tsource_version\torigin\n" + "".join(
        f"{p}\t{v}\t{s}\t{sv}\t{LOCAL.get(p, 'debian')}\n" for p, v, s, sv in pkgs))
    sources = sorted({(s, sv) for p, _, s, sv in pkgs if p not in LOCAL})
    print(f"{len(pkgs)} packages, {len(sources)} Debian source packages, local: "
          f"{', '.join(p for p, *_ in pkgs if p in LOCAL) or 'none'}")
    lic = b / "LICENSES/debian"
    cr = image_copyrights(rp, scratch)
    for pkg, data in cr.items():
        (lic / pkg).mkdir(parents=True, exist_ok=True)
        (lic / pkg / "copyright").write_bytes(data)
    (lic / "INDEX.tsv").write_text("".join(f"{p}\t{hashlib.sha256(d).hexdigest()}\n" for p, d in sorted(cr.items())))
    print(f"{len(cr)} copyright files")
    if not a.no_fetch:
        # The kernel first: it is the source people ask for most.
        for i, (s, sv) in enumerate(sorted(sources, key=lambda x: x[0] != "linux"), 1):
            names = fetch_source(s, sv, b / "debian" / f"{s}_{sv}")
            print(f"[{i}/{len(sources)}] {s} {sv}: {len(names)} files")
    cdir = b / "components"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "components.tsv").write_text("name\tversion\turl\tsha256\tlicence\n" +
                                        "".join(f"{n}\t{v}\t{u}\t{h}\t{l}\n" for n, v, u, h, l in COMPONENTS))
    deb = a.aosp / "packages/modules/Virtualization/build/debian"
    shutil.copyfile(deb / "ttyd/cross-build.sh", cdir / "ttyd-cross-build.sh")
    shutil.copyfile(deb / "ttyd/xtermjs_a11y.patch", cdir / "ttyd-xtermjs_a11y.patch")
    if not a.no_fetch:
        for name, ver, url, pin, _ in COMPONENTS:
            t = cdir / name / url.rsplit("/", 1)[-1]
            if not (t.exists() and sha256(t) == pin):
                data = get(url)
                if hashlib.sha256(data).hexdigest() != pin:
                    raise SystemExit(f"{name} {ver}: {url} doesn't match its pinned sha256")
                t.parent.mkdir(parents=True, exist_ok=True)
                t.write_bytes(data)
            licences_from_tarball(t, b / "LICENSES/components" / name)
            print(f"component {name} {ver}")
        data = get(GCC_RLE[0])
        if hashlib.sha256(data).hexdigest() != GCC_RLE[1]:
            raise SystemExit("GCC's runtime library exception doesn't match its pinned sha256")
        (b / "LICENSES/components/libgcc").mkdir(parents=True, exist_ok=True)
        (b / "LICENSES/components/libgcc/COPYING.RUNTIME").write_bytes(data)
    rev = build_inputs(a.aosp, b / "build")
    rec = json.loads((b / "IMAGE.json").read_text())
    (b / "NOTICE").write_text(
        "OpenBook Linux environment image: corresponding source and licences.\n\n"
        f"Image: images.tar.gz sha256 {rec['images.tar.gz']['sha256']}, build_id {rec['build_id']}.\n"
        f"AOSP packages/modules/Virtualization revision: {rev}.\n"
        f"Debian packages: {len(pkgs)}, from {len(sources)} source packages (debian/packages.tsv, debian/).\n"
        "OpenBook's own package in the image, quired: its source is build/openbook-quire.tar (quire/quired).\n"
        f"Outside Debian: {', '.join(n + ' ' + v for n, v, *_ in COMPONENTS)} (components/), and libgcc from GCC "
        "11.2.1 under the GCC Runtime Library Exception (LICENSES/components/libgcc).\n"
        "Licences: LICENSES/debian/<package>/copyright from the image (INDEX.tsv), LICENSES/components/<name>/.\n"
        "The guest agent in cidata.iso is AOSP's prebuilt; its source is build/aosp-guest.tar at the revision above.\n"
        "The image carries no AI agent.\n")
    shutil.rmtree(scratch, ignore_errors=True)
    print(f"{write_manifest(b)} files in {b}")


def check(image_out: Path, b: Path, aosp: Path) -> list:
    """Every problem with the bundle, as sentences; empty when it is complete and intact."""
    bad = []
    scratch = b / ".scratch"
    try:
        # The image it belongs to.
        try:
            rec = json.loads((b / "IMAGE.json").read_text())
            want = rec["images.tar.gz"]["sha256"]
        except Exception as e:
            return [f"no usable IMAGE.json ({e})"]
        have = sha256(image_out / "images.tar.gz")
        if have != want:
            return [f"the bundle is for another image: IMAGE.json names {want[:16]}, the image is {have[:16]}"]
        rp = root_part(image_out, scratch)
        pkgs = dpkg_status(rp)

        # The package list.
        try:
            rows = [l.split("\t") for l in (b / "debian/packages.tsv").read_text().splitlines()[1:] if l]
            listed = {(r[0], r[1], r[2], r[3]) for r in rows}
        except Exception as e:
            listed = set()
            bad.append(f"no usable debian/packages.tsv ({e})")
        if listed and listed != set(pkgs):
            bad.append(f"debian/packages.tsv doesn't match the image ({len(listed ^ set(pkgs))} differences)")

        # Debian sources: a .dsc for that source and version, and every file it lists, with size and SHA-256.
        for s, sv in sorted({(s, sv) for p, _, s, sv in pkgs if p not in LOCAL}):
            d = b / "debian" / f"{s}_{sv}"
            dscs = sorted(d.glob("*.dsc")) if d.is_dir() else []
            if not dscs:
                bad.append(f"no source for {s} {sv}")
                continue
            src, ver, files = dsc_files(dscs[0])
            if src != s or ver != sv:
                bad.append(f"{s} {sv}: its .dsc is for {src} {ver}")
                continue
            if not files:
                bad.append(f"{s} {sv}: its .dsc lists no files")
                continue
            for h, size, name in files:
                f = d / name
                if not f.is_file():
                    bad.append(f"{s} {sv}: {name} is missing")
                elif f.stat().st_size != size or sha256(f) != h:
                    bad.append(f"{s} {sv}: {name} doesn't match its .dsc")

        # OpenBook's own packages: their source is in build/, at the installed version.
        q = b / "build/openbook-quire.tar"
        for p, v, *_ in pkgs:
            if p != "quired":
                continue
            try:
                with tarfile.open(q) as t:
                    main = t.extractfile("quire/quired/main.go").read().decode()
                m = re.search(r'^var version = "([^"]+)"', main, re.M)
                if not m or m.group(1) != v:
                    bad.append(f"quired {v} is installed, but build/openbook-quire.tar has {m.group(1) if m else 'no version'}")
            except Exception as e:
                bad.append(f"quired {v}: no source in build/openbook-quire.tar ({e})")

        # Components: each one at its pin, readable, with its licence.
        for name, ver, url, pin, _ in COMPONENTS:
            t = b / "components" / name / url.rsplit("/", 1)[-1]
            if not t.is_file():
                bad.append(f"no source for {name} {ver}")
                continue
            if sha256(t) != pin:
                bad.append(f"{name} {ver}: {t.name} doesn't match its pinned sha256")
                continue
            try:
                if not any(LICENSE_NAMES.search(n) for n in tar_members(t)):
                    bad.append(f"{name} {ver}: its tarball has no licence file")
            except Exception as e:
                bad.append(f"{name} {ver}: its tarball can't be read ({e})")
            if not any((b / "LICENSES/components" / name).glob("**/*")):
                bad.append(f"{name}: no licence in LICENSES/components/{name}")
        rle = b / "LICENSES/components/libgcc/COPYING.RUNTIME"
        if not rle.is_file() or sha256(rle) != GCC_RLE[1]:
            bad.append("GCC's runtime library exception is missing from LICENSES/components/libgcc")
        deb = aosp / "packages/modules/Virtualization/build/debian/ttyd"
        for got, src in (("ttyd-cross-build.sh", "cross-build.sh"), ("ttyd-xtermjs_a11y.patch", "xtermjs_a11y.patch")):
            f = b / "components" / got
            if not f.is_file() or f.stat().st_size == 0:
                bad.append(f"components/{got} is missing")
            elif (deb / src).is_file() and sha256(f) != sha256(deb / src):
                bad.append(f"components/{got} isn't AOSP's {src}")

        # Every copyright file the image has.
        lic = b / "LICENSES/debian"
        for pkg, data in image_copyrights(rp, scratch).items():
            f = lic / pkg / "copyright"
            if not f.is_file() or f.read_bytes() != data:
                bad.append(f"LICENSES/debian/{pkg}/copyright is missing or differs from the image's")

        # The build inputs.
        for tar, need in BUILD_TARS.items():
            p = b / "build" / tar
            try:
                names = tar_members(p)
            except Exception as e:
                bad.append(f"build/{tar} can't be read ({e})")
                continue
            for n in need:
                if not any(x == n or x.startswith(n) for x in names):
                    bad.append(f"build/{tar} has no {n}")
        notice = (b / "NOTICE").read_text() if (b / "NOTICE").is_file() else ""
        if want not in notice:
            bad.append("NOTICE is missing or doesn't name the image")

        # The manifest: every file, and nothing else.
        try:
            rows = {name: h for h, name in (l.split("\t", 1) for l in (b / "MANIFEST.tsv").read_text().splitlines() if l)}
            files = {str(p.relative_to(b)): p for p in b.rglob("*")
                     if p.is_file() and p.name != "MANIFEST.tsv" and ".scratch" not in p.parts}
            for name in sorted(set(rows) ^ set(files)):
                bad.append(f"MANIFEST.tsv and the files disagree about {name}")
            for name in sorted(set(rows) & set(files)):
                if sha256(files[name]) != rows[name]:
                    bad.append(f"{name} doesn't match MANIFEST.tsv")
        except Exception as e:
            bad.append(f"no usable MANIFEST.tsv ({e})")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image_out", type=Path)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--aosp", type=Path, default=Path.home() / "anybook/aosp/src")
    ap.add_argument("--no-fetch", action="store_true", help="only the records and build inputs (for a look; --check fails)")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        bad = check(a.image_out, a.bundle, a.aosp)
        for p in bad[:200]:
            print(f"check: {p}", file=sys.stderr)
        print(f"check: {len(bad)} problem(s)")
        sys.exit(1 if bad else 0)
    make(a)


if __name__ == "__main__":
    main()
