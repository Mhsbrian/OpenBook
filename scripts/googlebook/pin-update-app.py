#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Write device/anybook/common/updater/app-pins.json: the reviewed SHA-256 of OpenBook Update's system
integration files and of the signed APK (build.sh output, recorded in its build.json).

A pin change is a review decision: commit it with the change it pins. The APK is byte-reproducible, so a
reviewer can rebuild the commit with build.sh and compare the SHA-256.

A deployable pin needs a clean, reproducible build (build.sh --reproducible-check on a commit whose APK
inputs are unchanged). --development pins any build for disposable VM checks only: the candidate builder
refuses a development pin without --vm-check.

usage: pin-update-app.py [--development] BUILD_DIR      (build.sh output: OpenBookUpdate.apk and build.json)
"""
import hashlib
import json
from pathlib import Path
import sys

SRC = Path(__file__).resolve().parents[2] / "device/anybook/common/updater"
FILES = ("app-sepolicy.cil", "app-seapp_contexts", "privapp-permissions-org.openbook.update.xml",
         "default-permissions-org.openbook.update.xml", "sysconfig-org.openbook.update.xml", "openbook-update.x509.pem")


def main(build_dir, development=False):
    record = json.loads((build_dir / "build.json").read_text())
    if not development and not (record.get("worktree_clean") and record.get("reproducible_check")):
        raise SystemExit("A deployable pin needs a clean, reproducible build (or --development for VM checks)")
    apk = (build_dir / "OpenBookUpdate.apk").read_bytes()
    digest = hashlib.sha256(apk).hexdigest()
    if digest != record["release_signed_sha256"]:
        raise SystemExit("OpenBookUpdate.apk differs from its build.json")
    pins = {
        "schema": "openbook-update-app-pins/1",
        "note": "Reviewed SHA-256 of OpenBook Update's system integration and its signed APK. Rebuild the APK "
                "with device/anybook/common/updater/app/build.sh to compare (the build is reproducible).",
        "files": {n: hashlib.sha256((SRC / n).read_bytes()).hexdigest() for n in FILES},
        "apk": {"sha256": digest, "unsigned_sha256": record["release_unsigned_sha256"],
                "version_code": record.get("version_code", 1), "version_name": record.get("version_name", "1.0"),
                "engine_sha256": record["engine_sha256"], "signing_certificate_sha256": record["signing_certificate_sha256"],
                "development_build": development, "worktree_clean": bool(record.get("worktree_clean")),
                "reproducible_check": bool(record.get("reproducible_check")), "built_from_commit": record.get("commit")},
    }
    (SRC / "app-pins.json").write_text(json.dumps(pins, indent=2) + "\n")
    print(json.dumps(pins["apk"], indent=2))


if __name__ == "__main__":
    args = sys.argv[1:]
    dev = "--development" in args
    args = [x for x in args if x != "--development"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    main(Path(args[0]), dev)
