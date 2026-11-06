#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""scripts/release/sources-links.py: public repositories pass; private ones and development documents are refused."""
import os
import subprocess
import sys
import tempfile

CHECK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts", "release", "sources-links.py")

CLEAN = [
    "The release files are at https://github.com/Mhsbrian/OpenBook/releases/tag/v0.1.0-preview.3.",
    "If something is missing, tell us at https://github.com/Mhsbrian/OpenBook/issues and we will publish it.",
    "git clone https://github.com/Mhsbrian/OpenBook.git",
    "The launcher is https://github.com/mhsbrian/openbooklauncher (any case).",
    "Upstream: https://github.com/DigitalisX64/platform_frameworks_libs_binary_translation.git",
    "systemd: https://github.com/systemd/systemd/archive/refs/tags/v262.tar.gz",
]
REFUSED = [
    "tell us at https://github.com/Mhsbrian/openbook-releases/issues",
    "The release files are at https://github.com/Mhsbrian/openbook-releases.",
    "old history: https://github.com/Mhsbrian/OpenBook-archive",
    "https://github.com/Mhsbrian/OPENBOOK-ARCHIVE.git",
    "see https://github.com/Mhsbrian/GoodBook",
    "the site's repository github.com/Mhsbrian/openbook.page",
    "The method is in docs/RELEASE.md.",
]


def run(text):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(text + "\n")
    try:
        return subprocess.run([sys.executable, CHECK, f.name], capture_output=True, text=True)
    finally:
        os.unlink(f.name)


def main():
    fails = []
    for line in CLEAN:
        r = run(line)
        if r.returncode != 0:
            fails.append(f"refused a clean line: {line!r}: {r.stdout.strip()}")
    for line in REFUSED:
        r = run(line)
        if r.returncode != 1 or not r.stdout.strip():
            fails.append(f"passed a line it must refuse: {line!r}")
    r = run("\n".join(CLEAN + REFUSED[:2]))
    if r.returncode != 1 or [l.split(":")[0] for l in r.stdout.splitlines()] != [str(len(CLEAN) + 1), str(len(CLEAN) + 2)]:
        fails.append(f"line numbers wrong: {r.stdout!r}")
    for f in fails:
        print("FAIL", f)
    print(f"{len(CLEAN) + len(REFUSED) + 1 - len(fails)}/{len(CLEAN) + len(REFUSED) + 1} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
