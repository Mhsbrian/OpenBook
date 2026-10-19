#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Identify a locally supplied Ruby recovery; never download, extract, mount or install it.

stdout is a report, not an installer source manifest. Exit 0 means a reviewed hash
matched; it never means boot/install readiness, licensing or Google certification.
Exit 2 means the input was refused. Only regular files are opened, read-only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

PROFILE = Path(__file__).resolve().parents[2] / "config/image-bases/googlebook-ruby.json"


def inspect(path, kind, profile):
    # NONBLOCK prevents a substituted FIFO from hanging before fstat; NOFOLLOW
    # rejects a final symlink. Use the same descriptor for every read/check.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Input must be a regular recovery file, not a device or pipe")
        # ZIP can be smaller than raw, but not larger for this pinned profile.
        if not 0 < before.st_size <= profile["raw_bytes"]:
            raise ValueError("Recovery size is outside this profile")
        if kind == "raw" and before.st_size != profile["raw_bytes"]:
            raise ValueError("Raw recovery size does not match the reviewed profile")
        sha = hashlib.sha256()
        md5 = hashlib.md5(usedforsecurity=False)
        remaining = before.st_size
        while remaining:
            block = stream.read(min(8 << 20, remaining))
            if not block:
                raise ValueError("Recovery changed during the read")
            sha.update(block)
            md5.update(block)
            remaining -= len(block)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns
        ):
            raise ValueError("Recovery changed during the read")
    if sha.hexdigest() != profile[kind + "_sha256"]:
        raise ValueError("Recovery SHA-256 does not match the reviewed Ruby build")
    if kind == "zip" and md5.hexdigest() != profile["official_zip_md5"]:
        raise ValueError("Recovery ZIP does not match the recorded official manifest MD5")
    return {
        "schema": "openbook-recovery-preflight/1",
        "matched": True,
        "profile": profile["id"],
        "build": profile["build"],
        "format": kind,
        "bytes": before.st_size,
        "sha256": sha.hexdigest(),
        "installable": False,
        "blockers": profile["blockers"],
        "scope": "Byte identity only; no AVB signature, license, compatibility or boot validation",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--raw", type=Path)
    group.add_argument("--zip", type=Path)
    args = parser.parse_args()
    try:
        profile = json.loads(PROFILE.read_text())
        report = inspect(args.raw or args.zip, "raw" if args.raw else "zip", profile)
    except (OSError, ValueError) as error:
        print(json.dumps({"schema": "openbook-recovery-preflight/1", "matched": False,
                          "installable": False, "error": str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
