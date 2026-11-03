#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Refuse what OpenBook never commits: evidence, logs, disk images, keys, home-network addresses and big files.

usage: check-hygiene.py [--root DIR] [--changed-since REF]

Without --changed-since, checks every file Git tracks in DIR (default: this checkout). CI runs it that way.
With --changed-since REF, checks only files added or modified since REF, e.g. to check a branch of your own quickly.
Exit 0 when clean, 1 with one line per finding.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 1024 * 1024
# Large files the build needs: fonts the product installs and the boot animation it copies.
LARGE_OK = re.compile(r"\.(ttf|otf)$|(^|/)bootanimation\.zip$")
FORBIDDEN_DIRS = re.compile(r"^(evidence|logs|out|dist)/")
FORBIDDEN_NAMES = re.compile(
    r"\.(log|img|iso|qcow2|raw|vmdk|tar|tgz|xz|zst|pk8|key|p12|jks|keystore)$|\.tar\.[a-z0-9]+$", re.I)
# README and brand images live in assets/; captures and screenshots belong on the issue.
DOC_IMAGES = re.compile(r"^docs/.*\.(png|jpe?g|gif|webp)$", re.I)
PRIVATE_KEY = re.compile(rb"^-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----\r?\n[A-Za-z0-9+/=\r\n]{64,}", re.M)
# A home-network address points at somebody's own machines: a laptop, a NAS, a router. Examples use the
# documentation ranges (192.0.2.0/24, RFC 5737). 192.168.77.0/24 is the QEMU Wi-Fi test network in
# scripts/qemu-test/, which exists only inside the test VM.
HOME_LAN_IPV4 = re.compile(rb"(?<![\d.])192\.168\.(?!77\.)\d{1,3}\.\d{1,3}(?![\d.])")
TEXT_LIMIT = 4 * MAX_BYTES


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout


def tracked(root, changed_since=None):
    if changed_since:
        out = git(root, "diff", "-z", "--name-only", "--diff-filter=AMR", f"{changed_since}...HEAD")
    else:
        out = git(root, "ls-files", "-z")
    return [p for p in out.decode().split("\0") if p]


def findings(root, changed_since=None):
    for name in tracked(root, changed_since):
        path = root / name
        if FORBIDDEN_DIRS.search(name):
            yield name, "evidence, logs and build output stay outside the repository"
            continue
        if FORBIDDEN_NAMES.search(name):
            yield name, "disk images, archives, logs and keys are never committed"
            continue
        if DOC_IMAGES.search(name):
            yield name, "screenshots and captures go on the issue; README and brand images go in assets/"
        if path.is_symlink() or not path.is_file():
            continue
        size = path.stat().st_size
        if size > MAX_BYTES and not LARGE_OK.search(name):
            yield name, f"{size} bytes is over the {MAX_BYTES}-byte limit"
        with path.open("rb") as handle:
            head = handle.read(TEXT_LIMIT)
        if PRIVATE_KEY.search(head):
            yield name, "contains a private key"
        if b"\0" not in head[:8192]:
            match = HOME_LAN_IPV4.search(head)
            if match:
                yield name, f"contains a home-network address ({match.group().decode()}); use 192.0.2.x in examples"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--changed-since", metavar="REF", help="check only files added or modified since REF")
    args = parser.parse_args()
    problems = list(findings(args.root.resolve(), args.changed_since))
    for name, reason in problems:
        print(f"{name}: {reason}")
    if problems:
        print(f"{len(problems)} file(s) refused. See CONTRIBUTING.md, \"What goes in this repository\".",
              file=sys.stderr)
        return 1
    print("hygiene: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
