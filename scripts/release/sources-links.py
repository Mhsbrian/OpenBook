#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The last gate on a source offer's SOURCES.md (make-sources.sh): it is published to people who can't see the
owner's private repositories, so it must stand on its own.

Refused:
  - a link to a github.com/Mhsbrian repository that isn't public: only the repositories in PUBLIC may appear.
    OpenBook itself is public since 2026-11-05; its old history (OpenBook-archive) and the retired
    openbook-releases are private (ANAL-388);
  - a reference to a development document (docs/<name>.md): the reader has the tarballs, not the repository.

usage: sources-links.py SOURCES.md     prints each hit as LINE:TEXT; exit 1 on any hit, 0 when clean
"""
import re
import sys

# Public repositories of the owner's account that a source offer may link. GitHub names are case-insensitive.
PUBLIC = {"openbook", "openbooklauncher"}
REPO = re.compile(r"github\.com/Mhsbrian/([A-Za-z0-9._-]+)", re.IGNORECASE)
DOC = re.compile(r"\bdocs/[A-Za-z-]+\.md\b")


def hits(text):
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in REPO.finditer(line):
            name = m.group(1).rstrip(".")
            if name.endswith(".git"):
                name = name[:-4]
            if name.lower() not in PUBLIC:
                out.append((n, f"github.com/Mhsbrian/{name} is not a public repository"))
        for m in DOC.finditer(line):
            out.append((n, f"{m.group(0)} is a development document, not part of the offer"))
    return out


def main():
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    found = hits(open(sys.argv[1], encoding="utf-8").read())
    for n, why in found:
        print(f"{n}: {why}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
