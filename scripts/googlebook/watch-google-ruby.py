#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Watch Google's public recovery-image listing for a new Googlebook Ruby build.

Google offers updates to the G14 per device (capture-google-ota.py reads those);
when Google also publishes a build as a recovery image, this is the full release,
downloadable with scripts/fetch-gbos-recovery.sh for the owner's own use. This
lists the manifest's Ruby entries and reports any build not in --known.
Exit 10 when a new build is listed, 0 when not.

usage: watch-google-ruby.py [--known 16452207] [--device ruby] [--manifest URL|FILE]
"""
import argparse
import json
from pathlib import Path
import sys
import urllib.request

MANIFEST = "https://dl.google.com/dl/edgedl/device/recovery/production_recovery.json"


def entries(data, device):
    rows = data if isinstance(data, list) else data.get("devices", [])
    return [dict(build=e.get("buildidentifier", ""), channel=e.get("channel"), date=e.get("dateupdated"),
                 url=e.get("url"), bytes=e.get("filesize"), md5=e.get("md5"))
            for e in rows if e.get("device") == device]


def new_builds(rows, known):
    return [r for r in rows if r["build"].split("_")[0] not in known]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--known", nargs="*", default=["16452207"])
    p.add_argument("--device", default="ruby")
    p.add_argument("--manifest", default=MANIFEST)
    a = p.parse_args()
    if a.manifest.startswith("http"):
        with urllib.request.urlopen(a.manifest, timeout=60) as r:
            data = json.load(r)
    else:
        data = json.loads(Path(a.manifest).read_text())
    rows = entries(data, a.device)
    new = new_builds(rows, set(a.known))
    print(json.dumps(dict(device=a.device, listed=[(r["build"], r["channel"], r["date"]) for r in rows],
                          new=[(r["build"], r["date"], r["bytes"]) for r in new]), indent=1))
    return 10 if new else 0


if __name__ == "__main__":
    sys.exit(main())
