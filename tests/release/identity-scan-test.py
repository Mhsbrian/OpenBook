#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""scripts/release/identity-scan.py on made-up identities: hits are found inside containers and never printed."""
import gzip
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile

SCAN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts", "release", "identity-scan.py")
ADDR, WORD = "pat.example@mail.example.invalid", "Zyxwvutsq"  # made up; never a real identity


def run(*args, stdin=None):
    return subprocess.run([sys.executable, SCAN, *args], input=stdin, capture_output=True, text=True)


def tar_xz(path, members):
    with tarfile.open(path, "w:xz", format=tarfile.GNU_FORMAT) as t:
        for name, data in members.items():
            i = tarfile.TarInfo(name)
            i.size = len(data)
            t.addfile(i, io.BytesIO(data))


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        ids = os.path.join(d, "ids.sha256")
        for kind, value in (("email", ADDR), ("word", WORD)):
            r = run("--ids", ids, "--add", kind, stdin=value + "\n")
            assert r.returncode == 0, r.stderr
        listed = open(ids).read()
        if ADDR.lower() in listed or WORD.lower() in listed:
            fails.append("the list holds a value, not only its hash")

        dirty, clean = os.path.join(d, "dirty"), os.path.join(d, "clean")
        os.makedirs(dirty); os.makedirs(clean)
        tar_xz(f"{dirty}/patches.tar.xz", {"0001.patch": f"From: Pat <{ADDR}>\nSubject: x\n".encode()})
        with zipfile.ZipFile(f"{dirty}/app.apk", "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("res/raw/about.txt", f"Made by Pat {WORD}.".encode())
        open(f"{dirty}/res.gz", "wb").write(gzip.compress(f"<{ADDR}>".encode("utf-16le")))
        open(f"{dirty}/{WORD}.txt", "w").write("a file whose name is the identity\n")
        tar_xz(f"{clean}/ok.tar.xz", {"README": b"upstream@example.org wrote this\n", "zeros": bytes(1 << 20)})

        r = run("--ids", ids, dirty)
        if r.returncode != 1:
            fails.append(f"dirty: exit {r.returncode}, not 1")
        for needle in ("patches.tar.xz|xz!0001.patch", "app.apk!res/raw/about.txt", "res.gz|gzip", "(an entry's name)"):
            if needle not in r.stdout:
                fails.append(f"dirty: no hit reported for {needle}")
        if ADDR.lower() in r.stdout.lower() or WORD.lower() in r.stdout.lower():
            fails.append("the output printed the identity")

        r = run("--ids", ids, clean)
        if r.returncode != 0 or "0 hit(s)" not in r.stdout:
            fails.append(f"clean: exit {r.returncode}: {r.stdout.strip()}")

        r = run("--ids", os.path.join(d, "missing"), clean)
        if r.returncode == 0:
            fails.append("a missing list passed")
    for f in fails:
        print("FAIL", f)
    print("identity-scan: " + ("ok" if not fails else f"{len(fails)} failures"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
