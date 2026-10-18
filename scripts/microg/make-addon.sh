#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build the "Google services compatibility (microG)" add-on (ANAL-210, docs/gapps.md section 6): the files an OpenBook
# disk's EFI partition carries in openbook/addons/microg/ for openbook-addons to install (device/anybook/common/addons).
#   openbook/addons/microg/<the catalogue's APKs>   microG's signed release APKs, unchanged (fetch.sh verified them)
#   openbook/addons/microg/addon.json               the catalogue they were checked against
#   openbook/addons/microg/README.txt, LICENSE      what this is, where the source is, how to take it off; Apache-2.0
# plus MANIFEST.sha256 (every file, relative to the EFI partition) and EXPECT (files any OpenBook live image has),
# which add-to-image.sh uses. Image files only: neither script writes a disk or a stick.
#
# usage: make-addon.sh [NAME]         NAME default openbook-microg-<version>
# Inputs: <data dir>/dl/microg/<version>/ from fetch.sh. Output: <data dir>/installer/out/NAME-addon/, NAME-addon.json.
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer
CAT=$R/device/anybook/common/addons/microg.json
VER=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$CAT")
NAME=${1:-openbook-microg-$VER}
case $NAME in *[!A-Za-z0-9._-]*) echo "name: letters, digits, . _ - only" >&2; exit 2 ;; esac
SRC=$A/dl/microg/$VER
[ -f "$SRC/VERIFIED.txt" ] || { echo "$SRC/VERIFIED.txt missing: run scripts/microg/fetch.sh" >&2; exit 2; }
OUT=$I/out/$NAME-addon; mkdir -p "$I/out"
COMMIT=$(git -C "$R" rev-parse HEAD); DIRTY=$( [ -z "$(git -C "$R" status --porcelain)" ] && echo false || echo true)
"$R/scripts/installer/inst-docker.sh" python3 -I - "$CAT" "$SRC" "$OUT" "$NAME" "$COMMIT" "$DIRTY" <<'EOF'
import hashlib, json, os, shutil, sys
cat_path, src, out, name, commit, dirty = sys.argv[1:]
cat = json.load(open(cat_path))
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()
shutil.rmtree(out, ignore_errors=True)
d = f"{out}/openbook/addons/{cat['name']}"
os.makedirs(d)
for f in cat["files"]:
    if sha(f"{src}/{f['file']}") != f["sha256"]:
        sys.exit(f"{src}/{f['file']} does not match the catalogue: run scripts/microg/fetch.sh again")
    shutil.copyfile(f"{src}/{f['file']}", f"{d}/{f['file']}")
shutil.copyfile(cat_path, f"{d}/addon.json")
shutil.copyfile("/usr/share/licenses/spdx/Apache-2.0.txt", f"{d}/LICENSE")
lines = "\n".join(f"  {f['file']:40} {f['label']}, sha256 {f['sha256']}" for f in cat["files"])
sources = "\n".join(f"  {f['label']}: {f['source']}" for f in cat["files"])
with open(f"{d}/README.txt", "w") as r:
    r.write(f"""{cat['title']} for OpenBook ({cat['version']})
{'=' * 72}
An optional add-on. OpenBook installs these apps as normal apps on the first start of a system that has this folder on
its boot disk: the live stick, or a disk installed with the add-on ticked. They are microG's own signed release APKs,
unchanged, and OpenBook checks each one against the sha256 its image pins before installing anything:
{lines}

microG is free software by the microG Project, Apache-2.0 (LICENSE here). Source code:
{sources}
Website: {cat['homepage']}. Releases are signed by microG's release key (certificate SHA-256
{cat['files'][0]['cert_sha256']}) and with OpenPGP key {cat['gpg_fingerprint']}.

microG is not Google software and does not make this device Play Protect certified; apps that require Play Integrity
(for example Google Wallet tap to pay) still will not work. Updates come from microG's own F-Droid repository
(https://microg.org/fdroid.html), or a newer OpenBook add-on.

To take it off: uninstall the apps in Settings > Apps (they stay uninstalled), and delete this folder.
""")
files = sorted(os.path.relpath(os.path.join(p, f), out) for p, _, fs in os.walk(out) for f in fs)
with open(f"{out}/MANIFEST.sha256", "w") as m:
    for f in files:
        m.write(f"{sha(f'{out}/{f}')}  {f}\n")
with open(f"{out}/EXPECT", "w") as e:
    e.write("openbook/MANIFEST.json\nloader/entries/openbook-live.conf\n")
size = sum(os.path.getsize(f"{out}/{f}") for f in files)
json.dump({"schema": "openbook-addon-bundle/1", "name": name, "addon": cat["name"], "version": cat["version"],
           "catalogue_sha256": sha(cat_path), "repo_commit": commit, "repo_dirty": dirty == "true",
           "bytes": size, "files": {f: sha(f"{out}/{f}") for f in files}},
          open(f"{out}.json", "w"), indent=1)
print(f"{out}: {len(files)} files, {size} bytes")
EOF
echo "add-on: $OUT ($(du -sh "$OUT" | cut -f1)); put it on an image with scripts/microg/add-to-image.sh"
