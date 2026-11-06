#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""The source bundle that goes with a released Linux environment image (ANAL-393, docs/quire-setup.md §7).

usage: linux-env-sources.py IMAGE_OUT BUNDLE_DIR [--aosp AOSP] [--fetch] [--limit N]
       linux-env-sources.py --check IMAGE_OUT BUNDLE_DIR

IMAGE_OUT is scripts/quire/linux-env-image.sh's output folder (images.tar.gz, image-info.txt). Everything comes from
the image's own records, so the bundle matches the bytes that ship:

  debian/packages.tsv     every installed package of the guest (dpkg status), with its source package and version
  debian/<src>_<ver>/     with --fetch: that source package's files (.dsc, original and Debian tarballs) from
                          snapshot.debian.org, checked against the archive's SHA-1, the kernel's included
  components/             ttyd and the libraries AOSP's builder links into it (ttyd/cross-build.sh), at their exact
                          versions, with AOSP's patch and build script; with --fetch, their source tarballs
  build/                  AOSP's guest builder at the tree's revision, OpenBook's patch to it, the image script and
                          quire/ (quired and its units), so the image can be rebuilt
  LICENSES/               every /usr/share/doc/*/copyright in the image, and each component's licence
  NOTICE, MANIFEST.tsv    what the bundle holds, and the sha256 of each file in it

--check fails when a source package the image lists has no files in the bundle, or a component has no source:
make-release.sh runs it before it signs a release that carries the image. Reads the image without mounting it
(debugfs). Writes only under BUNDLE_DIR and a scratch folder under it.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

R = Path(__file__).resolve().parents[2]
SNAPSHOT = "https://snapshot.debian.org"
UA = {"User-Agent": "openbook-linux-env-sources/1"}


def run(*cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout


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
    return sorted(out)


def copyrights(rp: Path, scratch: Path, dest: Path):
    """Every /usr/share/doc/<package>/copyright of the image, into LICENSES/debian/<package>/copyright."""
    docs = scratch / "doc"
    if docs.exists():
        shutil.rmtree(docs)
    docs.mkdir(parents=True)
    run("debugfs", "-R", f"rdump /usr/share/doc {docs}", str(rp))
    n = 0
    for c in sorted((docs / "doc").glob("*/copyright")):
        if c.is_symlink() or not c.is_file():
            continue
        t = dest / c.parent.name / "copyright"
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(c, t)
        n += 1
    shutil.rmtree(docs)
    return n


def fetch(url: str, dest: Path, sha1: str | None = None, tries=3):
    if dest.exists() and (sha1 is None or hashlib.sha1(dest.read_bytes()).hexdigest() == sha1):
        return
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                data = r.read()
            if sha1 and hashlib.sha1(data).hexdigest() != sha1:
                raise IOError(f"sha1 mismatch for {url}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def fetch_source(src: str, ver: str, dest: Path):
    """A source package's files from snapshot.debian.org, by the archive's own SHA-1 of each."""
    url = f"{SNAPSHOT}/mr/package/{src}/{ver}/srcfiles?fileinfo=1"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        info = json.load(r)
    names = []
    for h in info.get("result", []):
        sha1 = h["hash"]
        name = info["fileinfo"][sha1][0]["name"]
        fetch(f"{SNAPSHOT}/file/{sha1}", dest / name, sha1)
        names.append(name)
    if not any(n.endswith(".dsc") for n in names):
        raise IOError(f"{src} {ver}: no .dsc on snapshot.debian.org")
    return names


def components(aosp: Path):
    """ttyd and the libraries AOSP's builder links into it, with the URLs the builder itself uses."""
    deb = aosp / "packages/modules/Virtualization/build/debian"
    cross = (deb / "ttyd/cross-build.sh").read_text()
    internal = (deb / "build_internal.sh").read_text()

    def v(name, text=cross):
        m = re.search(rf'{name}="\$\{{{name}:-([^}}]+)\}}"', text) or re.search(rf"{name}=([0-9.]+)", text)
        if not m:
            raise SystemExit(f"no {name} in AOSP's builder")
        return m.group(1)

    ttyd = re.search(r"ttyd_version=([0-9.]+)", internal).group(1)
    musl = re.search(r'MUSL_CC_URL="([^"]+)"', cross).group(1)
    return [
        ("ttyd", ttyd, f"https://github.com/tsl0922/ttyd/archive/refs/tags/{ttyd}.tar.gz", "MIT"),
        ("zlib", v("ZLIB_VERSION"), f"https://github.com/madler/zlib/archive/refs/tags/v{v('ZLIB_VERSION')}.tar.gz", "Zlib"),
        ("json-c", v("JSON_C_VERSION"),
         f"https://s3.amazonaws.com/json-c_releases/releases/json-c-{v('JSON_C_VERSION')}.tar.gz", "MIT"),
        ("mbedtls", v("MBEDTLS_VERSION"), f"https://github.com/ARMmbed/mbedtls/archive/v{v('MBEDTLS_VERSION')}.tar.gz",
         "Apache-2.0 OR GPL-2.0-or-later"),
        ("libuv", v("LIBUV_VERSION"), f"https://dist.libuv.org/dist/v{v('LIBUV_VERSION')}/libuv-v{v('LIBUV_VERSION')}.tar.gz",
         "MIT"),
        ("libwebsockets", v("LIBWEBSOCKETS_VERSION"),
         f"https://github.com/warmcat/libwebsockets/archive/v{v('LIBWEBSOCKETS_VERSION')}.tar.gz", "MIT"),
        # The musl cross toolchain the builder links ttyd with: musl libc (MIT) and GCC's runtime (GCC Runtime
        # Library Exception) end up in the binary.
        ("musl-cross-toolchain", musl.rsplit("/", 1)[-1], f"{musl}/x86_64-linux-musl-cross.tgz", "MIT (musl); GPL-3.0 with GCC RLE (libgcc)"),
    ]


LICENSE_NAMES = re.compile(r"(^|/)(LICENSE|LICENSE\.txt|LICENSE\.md|COPYING|COPYRIGHT|NOTICE|LICENSE-[A-Z0-9.]+)$")


def licences_from_tarball(tgz: Path, dest: Path):
    n = 0
    with tarfile.open(tgz) as t:
        for m in t.getmembers():
            if not m.isfile() or not LICENSE_NAMES.search(m.name):
                continue
            # Top-level and one level down only: a library's own licence, not its tests' fixtures.
            depth = m.name.count("/")
            if depth > 2:
                continue
            data = t.extractfile(m).read()
            target = dest / m.name.split("/", 1)[-1]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
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


def manifest(bundle: Path):
    rows = []
    for p in sorted(bundle.rglob("*")):
        if p.is_file() and p.name != "MANIFEST.tsv" and ".scratch" not in p.parts:
            rows.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}\t{p.relative_to(bundle)}")
    (bundle / "MANIFEST.tsv").write_text("\n".join(rows) + "\n")
    return len(rows)


def check(image_out: Path, bundle: Path, aosp: Path) -> int:
    pk = bundle / "debian/packages.tsv"
    if not pk.exists():
        print("check: no debian/packages.tsv", file=sys.stderr)
        return 1
    rp = root_part(image_out, bundle / ".scratch")
    now = {(s, sv) for _, _, s, sv in dpkg_status(rp)}
    listed = {tuple(l.split("\t")[2:4]) for l in pk.read_text().splitlines()[1:] if l}
    bad = 0
    if now != listed:
        print(f"check: packages.tsv doesn't match the image ({len(now ^ listed)} differences)", file=sys.stderr)
        bad += 1
    for s, sv in sorted(now):
        d = bundle / "debian" / f"{s}_{sv}"
        if not any(d.glob("*.dsc")):
            print(f"check: no source for {s} {sv}", file=sys.stderr)
            bad += 1
    for name, ver, _, _ in components(aosp):
        if name == "musl-cross-toolchain":
            continue
        if not any((bundle / "components" / name).glob("*.tar.gz")):
            print(f"check: no source for {name} {ver}", file=sys.stderr)
            bad += 1
    shutil.rmtree(bundle / ".scratch", ignore_errors=True)
    print(f"check: {len(now)} source packages, {bad} problem(s)")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image_out", type=Path)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--aosp", type=Path, default=Path.home() / "anybook/aosp/src")
    ap.add_argument("--fetch", action="store_true", help="download the sources (several GB)")
    ap.add_argument("--limit", type=int, default=0, help="with --fetch: only the first N source packages (a test)")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        sys.exit(check(a.image_out, a.bundle, a.aosp))

    b = a.bundle
    scratch = b / ".scratch"
    rp = root_part(a.image_out, scratch)
    pkgs = dpkg_status(rp)
    (b / "debian").mkdir(parents=True, exist_ok=True)
    (b / "debian/packages.tsv").write_text("package\tversion\tsource\tsource_version\n" +
                                          "".join(f"{p}\t{v}\t{s}\t{sv}\n" for p, v, s, sv in pkgs))
    sources = sorted({(s, sv) for _, _, s, sv in pkgs})
    kernel = [p for p in pkgs if p[0].startswith("linux-image-")]
    print(f"{len(pkgs)} packages from {len(sources)} source packages; kernel: {', '.join(p[0] + ' ' + p[1] for p in kernel)}")
    n = copyrights(rp, scratch, b / "LICENSES/debian")
    print(f"{n} copyright files")

    if a.fetch:
        todo = sources[: a.limit] if a.limit else sources
        # The kernel first: it is the source people ask for most.
        todo.sort(key=lambda x: x[0] != "linux")
        for i, (s, sv) in enumerate(todo, 1):
            names = fetch_source(s, sv, b / "debian" / f"{s}_{sv}")
            print(f"[{i}/{len(todo)}] {s} {sv}: {len(names)} files")

    comps = components(a.aosp)
    cdir = b / "components"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "components.tsv").write_text("name\tversion\turl\tlicence\n" +
                                        "".join(f"{n}\t{v}\t{u}\t{l}\n" for n, v, u, l in comps))
    deb = a.aosp / "packages/modules/Virtualization/build/debian"
    shutil.copyfile(deb / "ttyd/cross-build.sh", cdir / "ttyd-cross-build.sh")
    shutil.copyfile(deb / "ttyd/xtermjs_a11y.patch", cdir / "ttyd-xtermjs_a11y.patch")
    if a.fetch:
        for name, ver, url, _ in comps:
            if name == "musl-cross-toolchain":
                continue
            t = cdir / name / url.rsplit("/", 1)[-1]
            fetch(url, t)
            licences_from_tarball(t, b / "LICENSES/components" / name)
            print(f"component {name} {ver}")
    rev = build_inputs(a.aosp, b / "build")
    info = (a.image_out / "image-info.txt").read_text() if (a.image_out / "image-info.txt").exists() else ""
    (b / "NOTICE").write_text(
        "OpenBook Linux environment image: corresponding source and licences.\n\n"
        f"Image record (image-info.txt):\n{info}\n"
        f"AOSP packages/modules/Virtualization revision: {rev}\n"
        f"Debian packages: {len(pkgs)} from {len(sources)} source packages (debian/packages.tsv).\n"
        f"Components outside Debian: {', '.join(n + ' ' + v for n, v, _, _ in comps)} (components/).\n"
        "Licences: LICENSES/debian/<package>/copyright from the image, LICENSES/components/<name>/.\n"
        "The guest agent in cidata.iso is AOSP's prebuilt; its source is build/aosp-guest.tar at the revision above.\n"
        "The image carries no AI agent.\n")
    shutil.rmtree(scratch, ignore_errors=True)
    print(f"{manifest(b)} files in {b}")


if __name__ == "__main__":
    main()
