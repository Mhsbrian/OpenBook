#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage a reviewed Ruby image as a reassembler base: image, manifest and logical images.

The source is a candidate directory (ruby-live.img + manifest.json) pinned by
SHA-256. Super is unpacked with lpunpack into logical/<name>_a.img, and every
logical image must match the manifest. Regular files only; the source is
re-hashed at the end to prove it did not change.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("preserve", HERE / "preserve-update.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def stage(source, source_sha256, tools, out):
    image = p.regular(source / "ruby-live.img")
    manifest = json.loads(p.regular(source / "manifest.json").read_text())
    if manifest["image_sha256"] != source_sha256 or p.h.audit.sha(image) != source_sha256:
        raise ValueError("Source image differs from its pin")
    out.mkdir(mode=0o700)
    p.h.run("cp", "--reflink=auto", "--sparse=always", image, out / "ruby-live.img")
    shutil.copyfile(source / "manifest.json", out / "manifest.json")
    rows = {row["name"]: row for row in p.read_gpt(image)}
    work = out / "unpack"
    work.mkdir()
    p.live.copy_range(image, work / "super.img", *p.extent(rows["super"]))
    env = dict(os.environ, LD_LIBRARY_PATH=str(tools.parent / "lib64"))
    subprocess.run([str(tools / "lpunpack"), str(work / "super.img"), str(work)], check=True, env=env,
                   stdout=subprocess.DEVNULL)
    (work / "super.img").unlink()
    logical = out / "logical"
    logical.mkdir()
    expected = {f"{name}_a.img" for name in manifest["logical_sha256"]}
    if {f.name for f in work.iterdir()} != expected:
        raise ValueError("Super partitions differ from the manifest's logical set")
    for name, digest in manifest["logical_sha256"].items():
        unpacked = work / f"{name}_a.img"
        if p.h.audit.sha(unpacked) != digest:
            raise ValueError(f"Unpacked {name} differs from the manifest")
        unpacked.rename(logical / f"{name}_a.img")
    work.rmdir()
    if p.h.audit.sha(image) != source_sha256:
        raise ValueError("Source changed")
    print(json.dumps(dict(base_sha256=source_sha256, logical=sorted(manifest["logical_sha256"]))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "tools", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    a = parser.parse_args()
    if not Path("/.dockerenv").exists():
        parser.error("Use inst-docker.sh; regular images only")
    os.umask(0o077)
    stage(a.source, a.source_sha256, a.tools, a.out)
