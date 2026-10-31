#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Write RELEASES_DIR/index.json for openbook.page from every RELEASES_DIR/<version>/release.json
(scripts/release/make-release.sh). Only releases with "public": true are listed, so an unpublished or private build
never reaches the site, even if its folder is on the server. Newest first; "latest" is the newest per channel.
usage: release-index.py RELEASES_DIR
"""
import json
import os
import sys


def main():
    root = sys.argv[1]
    rels = []
    for v in sorted(os.listdir(root)):
        p = os.path.join(root, v, "release.json")
        if not os.path.isfile(p):
            continue
        r = json.load(open(p))
        if r.get("schema") != "openbook-release/1" or r.get("version") != v:
            print(f"skipping {v}: not an openbook-release/1 record for this folder", file=sys.stderr)
            continue
        if r.get("public") is not True:
            print(f"not listing {v}: {r.get('audience')}; blocking {', '.join(r.get('blocking', [])) or '-'}",
                  file=sys.stderr)
            continue
        a = r["artifacts"][0]
        rels.append({"version": v, "channel": r["channel"], "date": r["date"], "path": f"{v}/release.json",
                     "file": a["file"], "bytes": a["bytes"], "sha256": a["sha256"],
                     "magnet": a.get("torrent", {}).get("magnet"), "urls": a["urls"]})
    rels.sort(key=lambda x: (x["date"], x["version"]), reverse=True)
    latest = {}
    for r in rels:
        latest.setdefault(r["channel"], r["version"])
    out = {"schema": "openbook-releases/1", "latest": latest, "releases": rels}
    tmp = os.path.join(root, "index.json.tmp")
    with open(tmp, "w") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, os.path.join(root, "index.json"))
    print(f"index.json: {len(rels)} public release(s); latest {latest or '-'}")


if __name__ == "__main__":
    main()
