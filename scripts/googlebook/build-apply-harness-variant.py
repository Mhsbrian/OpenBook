#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""A disposable apply-harness variant that can apply two updates in a row (RB-20261023-03, VM only).

The --apply-from-drive harness (build-ota-trust-candidate.py) runs its driver once per data partition:
the first apply leaves /data/local/tmp/openbook-ota-apply.done, and every later boot exits on it. The
G14 runs slot B after its first wireless update, so the next release goes into slot A; rehearsing that
needs a second update on the same /data. This variant replaces only the driver script of an existing
harness candidate: its done marker names the payload's SHA-256, so each payload drive is applied once.
No payload drive: nothing happens and no marker is written. Everything else is the base harness.

The output keeps the base's experimental_ota_apply_test marker and adds its own; installer packaging
refuses both. Never deploy it.

usage: build-apply-harness-variant.py --base STAGED_HARNESS --base-sha256 SHA --tools AOSP_HOST_BIN
                                      --inventory erofs-inventory --key AVB_KEY --out DIR
Container only (inst-docker.sh); regular image files.
"""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


b = load("builder", "build-input-candidate.py")
t = load("trust", "build-ota-trust-candidate.py")
DRIVER = f"{t.TEST_DIR}/apply.sh"
OLD_HEAD = """DONE=/data/local/tmp/openbook-ota-apply.done
[ -e $DONE ] && exit 0
touch $DONE
"""
NEW_HEAD = """# Once per payload (RB-20261023-03 variant): a later boot of the same /data with another payload
# drive applies that payload too. No payload drive: nothing to do, and no marker.
P=$(sha256sum /mnt/otapayload/payload.bin 2>/dev/null | cut -d' ' -f1)
[ -n "$P" ] || exit 0
DONE=/data/local/tmp/openbook-ota-apply.$P.done
[ -e $DONE ] && exit 0
touch $DONE
"""


def driver():
    if t.APPLY_SCRIPT.count(OLD_HEAD) != 1:
        raise ValueError("The base harness driver changed; review this variant")
    return t.APPLY_SCRIPT.replace(OLD_HEAD, NEW_HEAD).encode()


def build(a):
    new = driver()

    def transform(source):
        current = (source / DRIVER.lstrip("/")).read_bytes()
        if current != t.APPLY_SCRIPT.encode():
            raise ValueError("The base is not the reviewed --apply-from-drive harness")
        annotations = {"experimental_ota_apply_variant": dict(
            deployment_eligible=False, hardware_validated=False, unattended_safe=False,
            scope="VM only: the apply driver's done marker names the payload's SHA-256 (two updates in a row)",
            files={DRIVER: hashlib.sha256(new).hexdigest()}, replaced_sha256=hashlib.sha256(current).hexdigest())}
        return {DRIVER: new}, annotations

    b.build_system(a, transform, "openbook-ruby-ota-apply-test/1")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "tools", "inventory", "key", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--base-sha256", required=True)
    a = p.parse_args()
    if not Path("/.dockerenv").exists():
        p.error("Run in the openbook-installer container (scripts/installer/inst-docker.sh)")
    os.umask(0o077)
    build(a)
