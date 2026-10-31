#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build the OpenBook ARM-apps check (ANAL-200): an add-on for an OpenBook live USB stick that runs the bridge's
# self-check, the compat probe (arm64 through the bridge, x86_64 as the control) and CoreMark on the laptop's own
# CPU from the stick's own Android, and saves the results on the stick. See mkaddon.py for what goes on the stick,
# run.sh for what runs, and docs/digitalis.md ("On the G14") for the steps.
# Image files only: neither this script nor add-to-image.sh ever writes to a disk or USB stick.
#
# usage: make-bridge-check.sh [NAME]          NAME default openbook-bridgecheck-<UTC date>
# Inputs: the probe APKs and CoreMark binaries from scripts/compat/build-probes.sh (~/anybook/compat/out/probes).
# Output in <data dir>/installer/out/: NAME-addon/ (the ESP files, MANIFEST.sha256, EXPECT) and NAME-addon.json.
set -euo pipefail
R=$(cd "$(dirname "$0")/../../../.." && pwd)
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer; P=$A/compat/out/probes
NAME=${1:-openbook-bridgecheck-$(date -u +%Y%m%d)}
case $NAME in *[!A-Za-z0-9._-]*) echo "name: letters, digits, . _ - only" >&2; exit 2 ;; esac
for f in anybook-probe-arm64.apk anybook-probe-x86_64.apk bench/coremark-arm64 bench/coremark-x86_64 SHA256SUMS TOOLCHAIN; do
  [ -f "$P/$f" ] || { echo "missing $P/$f: run scripts/compat/build-probes.sh" >&2; exit 2; }; done
(cd "$P" && sha256sum -c --quiet SHA256SUMS) || { echo "$P does not match its SHA256SUMS" >&2; exit 1; }
CM=$A/compat/src/coremark/LICENSE.md
[ -f "$CM" ] || { echo "missing $CM (CoreMark's license; build-probes.sh fetches the source)" >&2; exit 2; }

W=$I/work/$NAME-payload; rm -rf "$W"; mkdir -p "$W/apk" "$W/bench" "$W/LICENSES"
install -m 0755 "$R/scripts/compat/digitalis/stick/run.sh" "$W/run.sh"
for s in arm64 x86_64; do
  cp "$P/anybook-probe-$s.apk" "$W/apk/"
  install -m 0755 "$P/bench/coremark-$s" "$W/bench/"
done
cp "$CM" "$W/LICENSES/coremark-LICENSE.md"
printf 'OpenBook probe (scripts/compat/probe): Apache-2.0, The OpenBook Authors.\nCoreMark: Apache-2.0 code; CoreMark(R) is a trademark of EEMBC (coremark-LICENSE.md). Our own measurements, not certified scores.\n' \
  > "$W/LICENSES/README.txt"
python3 -I - "$W/VERSION.json" "$R" "$P" "$NAME" <<'EOF'
import json, subprocess, sys
out, repo, p, name = sys.argv[1:]
git = lambda *a: subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout.strip()
sums = {l.split()[1]: l.split()[0] for l in open(f"{p}/SHA256SUMS") if l.strip()}
json.dump({"name": name, "repo_commit": git("rev-parse", "HEAD"), "repo_dirty": bool(git("status", "--porcelain")),
           "toolchain": open(f"{p}/TOOLCHAIN").read().strip().splitlines(),
           "probes": {k: v for k, v in sums.items() if k.split("/")[-1] in (
               "anybook-probe-arm64.apk", "anybook-probe-x86_64.apk", "coremark-arm64", "coremark-x86_64")}},
          open(out, "w"), indent=1)
EOF
python3 -I "$R/scripts/compat/digitalis/stick/mkaddon.py" --payload "$W" --out "$I/out/$NAME-addon" --name "$NAME"
echo "add-on: $I/out/$NAME-addon ($(du -sh "$I/out/$NAME-addon" | cut -f1)); put it on an image with add-to-image.sh"
