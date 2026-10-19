#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise base selection through the real CLI/daemon and source FAT manifest.

Run inside inst-docker.sh with --engine BIN --image LIVE.img --run NEW_DIR.
Only copies of regular image files and a sparse fixture target are used.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import time

spec = importlib.util.spec_from_file_location("fixtures", Path(__file__).with_name("engine-test.py"))
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--run", required=True)
    a = parser.parse_args()
    assert stat.S_ISREG(os.stat(a.image).st_mode), "regular source file required"
    work = Path(a.run).resolve()
    work.mkdir(parents=True, exist_ok=False)
    stick, target = work / "stick.img", work / "target.img"
    subprocess.run(["cp", "--reflink=auto", "--sparse=always", a.image, stick], check=True)
    with target.open("xb") as stream:
        stream.truncate(64 * f.GiB)
    before = target.stat()
    meta = json.loads(Path(a.image + ".json").read_text())
    esp = next(p for p in meta["partitions"] if p["name"] == "EFI")["start"] * 512
    manifest_path = work / "manifest.json"
    assert f.esp_get(str(stick), esp, "openbook/MANIFEST.json", str(manifest_path))
    original = json.loads(manifest_path.read_text())
    root = f.make_root(str(work), "base", str(stick), str(target))
    engine = f.Engine(a.engine, root, meta["esp_partuuid"], str(work / "cli"))
    checks = []

    def check(name, ok):
        checks.append({"check": name, "passed": bool(ok)})
        (work / "results.json").write_text(json.dumps(checks, indent=2) + "\n")
        if not ok:
            raise AssertionError(name)

    target_id = "nvme-QEMU_NVMe_Ctrl_internal0"
    rc, legacy, _ = engine.run("plan", "--target", target_id)
    check("legacy AOSP plan works", rc == 0 and bool(legacy.get("plan_sha256")))
    rc, plan, _ = engine.run("plan", "--target", target_id, "--image-base", "openbook-aosp")
    check("explicit AOSP plan records base", rc == 0 and plan["request"]["image_base"] == "openbook-aosp")
    explicit = work / "aosp-plan.json"
    explicit.write_text(json.dumps(plan))
    rc, reply, _ = engine.run("apply", "--plan", str(explicit), "--confirm-disk", "/dev/disk/by-id/" + target_id)
    check("explicit AOSP plan replays with same digest", rc != 0 and reply.get("code") == "confirm_mismatch")
    for base in ("googlebook-recovery", "unknown-base"):
        rc, reply, _ = engine.run("plan", "--target", target_id, "--image-base", base)
        check("CLI refuses " + base, rc != 0 and reply.get("code") == "image_base_unavailable")
    # A valid plan edited after review cannot be applied as another base.
    tampered = copy.deepcopy(plan)
    tampered["request"]["image_base"] = "googlebook-recovery"
    path = work / "tampered-plan.json"
    path.write_text(json.dumps(tampered))
    confirm = "/dev/disk/by-id/" + target_id
    rc, reply, _ = engine.run("apply", "--plan", str(path), "--confirm-disk", confirm,
                              env={"OPENBOOK_INSTALL_ERASE": confirm})
    check("apply refuses foreign base before writing", rc != 0 and reply.get("code") == "image_base_unavailable")

    # The socket stays under the UNIX path length limit, and its child is always reaped.
    with tempfile.TemporaryDirectory(prefix="ob-base-") as td:
        sock = td + "/daemon"
        with (work / "daemon.log").open("w") as log:
            proc = subprocess.Popen([a.engine, "--root", root, "--boot-part-uuid", meta["esp_partuuid"],
                                     "daemon", "--socket", sock], stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 5
                while not os.path.exists(sock) and proc.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(10)
                    client.connect(sock)
                    stream = client.makefile("rwb")
                    for base, code in (("googlebook-recovery", "image_base_unavailable"),
                                       ("other", "image_base_unavailable"), (None, "bad_request"),
                                       ([], "bad_request"), ("", "bad_request"), ("x" * 32, "bad_request"),
                                       ("openbook-aosp", None)):
                        stream.write((json.dumps(dict(id=1, cmd="plan", target=target_id, image_base=base)) + "\n").encode())
                        stream.flush()
                        reply = json.loads(stream.readline())
                        check("daemon base " + repr(base), reply.get("code") == code and reply.get("ok") == (code is None))
                    stream.close()
            finally:
                proc.terminate()
                proc.wait(timeout=5)

    for marker in ("googlebook-recovery", "other", None, "", "openbook-aosp"):
        manifest = dict(original, image_base=marker)
        manifest_path.write_text(json.dumps(manifest))
        subprocess.run(["mcopy", "-o", "-i", f"{stick}@@{esp}", str(manifest_path),
                        "::/openbook/MANIFEST.json"], check=True)
        rc, reply, _ = engine.run("plan", "--target", target_id)
        check("source marker " + repr(marker), rc == 0 if marker == "openbook-aosp" else
              rc != 0 and reply.get("code") == "no_source")
    after = target.stat()
    check("target never opened for writes", (before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_blocks) ==
          (after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_blocks))
    print(f"{len(checks)}/{len(checks)} image-base checks passed; fixture target unchanged")


if __name__ == "__main__":
    main()
