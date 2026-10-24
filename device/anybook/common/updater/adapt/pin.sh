#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Pin an openbook-adapt build for the image (adapter-pins.json, read by build-update-app-candidate.py): only
# a static build from a clean worktree whose second clean build was byte-identical (build.sh
# --reproducible-check). The pin names the binary's SHA-256, the toolchain and the commit.
#
# usage: pin.sh BUILD_DIR
set -euo pipefail
B=$1
HERE=$(cd "$(dirname "$0")" && pwd)
python3 - "$B/build.json" "$B/openbook-adapt" "$HERE/adapter-pins.json" <<'EOF'
import hashlib, json, sys
build, binary, out = json.load(open(sys.argv[1])), open(sys.argv[2], "rb").read(), sys.argv[3]
if hashlib.sha256(binary).hexdigest() != build["sha256"]:
    sys.exit("the binary differs from its build record")
if not (build["worktree_clean"] and build["reproducible_check"] is True and build["static"]):
    sys.exit("only a static build from a clean worktree with a passed reproducible check can be pinned")
pin = dict(schema="openbook-adapter-pins/1",
           note="openbook-adapt for the image. Rebuild with adapt/build.sh at the commit to compare (reproducible).",
           sha256=build["sha256"], go=build["go"], go_archive_sha256=build["go_archive_sha256"],
           source_sha256=build["source_sha256"], commit=build["commit"], worktree_clean=True,
           reproducible_check=True, static=True)
open(out, "w").write(json.dumps(pin, indent=2) + "\n")
print(json.dumps(pin, indent=2))
EOF
