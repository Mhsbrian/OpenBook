#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail closed when a Ruby image or payload could reach PC firmware, the TPM or the EC (ANAL-251).

Googlebook images assume Google hardware: init scripts start security chip (GSC) firmware tools, and
Google's update postinstall installs GSC, AP (BIOS flash) and EC firmware. The rules are
device/anybook/common/safety/firmware-safety.json; the on-laptop adapter (ANAL-229 phase 3) applies the
same file. This checks:

  tree     extracted partitions (NAME=DIR; system is the system-as-root image, mounted at /):
           - every neutralised path holds OpenBook's replacement (not Google's original, not anything else);
           - every *.rc file whose non-comment lines match rc_pattern is neutralised or reviewed at its
             exact SHA-256 (APEX rc files too, with --tools);
           - every bin/xbin file matching binary_pattern is reviewed by path;
           - no file has a forbidden name (fwupd, flashrom, futility, ...).
  images   the same for erofs/ext4 partition images (NAME=IMAGE), extracted with --tools into --work.
  payload  an update_engine payload (payload.bin, or an OTA zip holding one): no partition may run a
           postinstall step.

Exit status: 0 passed, 1 findings (review needed), 2 usage or unreadable input.
usage: check-firmware-safety.py tree   [--policy JSON] [--tools OTATOOLS_BIN --work DIR] NAME=DIR...
       check-firmware-safety.py images [--policy JSON] --tools OTATOOLS_BIN --work DIR NAME=IMAGE...
       check-firmware-safety.py payload [--policy JSON] PAYLOAD
       (each takes --output RESULT.json)
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
SAFETY = HERE.parents[1] / "device/anybook/common/safety"
POLICY = SAFETY / "firmware-safety.json"
SCHEMA = "openbook-firmware-safety/1"
RESULT_SCHEMA = "openbook-firmware-safety-result/1"
# Where each partition image is mounted; system is system-as-root.
MOUNTS = {"system": "/", "system_ext": "/system_ext", "product": "/product", "vendor": "/vendor", "odm": "/odm",
          "vendor_dlkm": "/vendor_dlkm", "system_dlkm": "/system_dlkm", "odm_dlkm": "/odm_dlkm"}
HEX64 = re.compile(r"[0-9a-f]{64}")


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_policy(path=POLICY, safety_dir=None):
    """The rules, with OpenBook's replacement files checked against their pins."""
    policy = json.loads(Path(path).read_text())
    if policy.get("schema") != SCHEMA:
        raise ValueError(f"{path}: not a {SCHEMA} file")
    for key in ("rc_pattern", "binary_pattern"):
        re.compile(policy[key])
    safety_dir = Path(safety_dir) if safety_dir else Path(path).parent
    for runtime, rule in policy["neutralised"].items():
        if not (HEX64.fullmatch(rule["sha256"]) and HEX64.fullmatch(rule["google_sha256"])):
            raise ValueError(f"{runtime}: neutralised rule needs sha256 and google_sha256")
        if sha_file(safety_dir / rule["replacement"]) != rule["sha256"]:
            raise ValueError(f"{rule['replacement']} differs from its pin in {Path(path).name}")
    for runtime, rule in policy["reviewed_rc"].items():
        if not HEX64.fullmatch(rule["sha256"]) or rule.get("verdict") not in ("allowed", "inert", "openbook"):
            raise ValueError(f"{runtime}: reviewed rc rule needs sha256 and a verdict")
    overlap = set(policy["neutralised"]) & set(policy["reviewed_rc"])
    if overlap:
        raise ValueError(f"Paths both neutralised and reviewed: {sorted(overlap)}")
    return policy


def replacement(policy, runtime, safety_dir=SAFETY):
    """OpenBook's replacement bytes for a neutralised path (pinned)."""
    data = (Path(safety_dir) / policy["neutralised"][runtime]["replacement"]).read_bytes()
    if sha_bytes(data) != policy["neutralised"][runtime]["sha256"]:
        raise ValueError(f"Replacement for {runtime} differs from its pin")
    return data


def rc_hits(text, pattern):
    """Sorted distinct matches on non-comment lines (init treats a line whose first non-blank is # as a comment)."""
    hits = set()
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            hits.update(m.group(0).lower() for m in pattern.finditer(s))
    return sorted(hits)


def walk(roots):
    """(runtime path, local path) for every regular file and symlink under each partition root."""
    for name, root in roots.items():
        mount = MOUNTS[name]
        root = Path(root)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for f in sorted(filenames):
                local = Path(dirpath) / f
                rel = local.relative_to(root).as_posix()
                yield ("/" + rel) if mount == "/" else f"{mount}/{rel}", local


def apex_rc_files(roots, tools, work):
    """(runtime path, bytes) of the init scripts inside every APEX (apex_payload.img, erofs or ext4)."""
    out = []
    work = Path(work)
    for runtime, local in walk(roots):
        if not runtime.endswith(".apex") or local.is_symlink():
            continue
        name = local.name[:-5]
        dest = work / "apex" / name
        payload = dest.with_suffix(".payload.img")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(local) as z:
            if "apex_payload.img" not in z.namelist():
                continue
            payload.write_bytes(z.read("apex_payload.img"))
        extract(payload, dest, tools)
        payload.unlink()
        for path in sorted(dest.rglob("*.rc")):
            if path.is_file() and not path.is_symlink():
                out.append((f"/apex/{name}/{path.relative_to(dest).as_posix()}", path.read_bytes()))
    return out


def extract(image, dest, tools):
    """Extract an erofs (fsck.erofs) or ext4 (debugfs) image into dest."""
    tools = Path(tools)
    env = dict(os.environ, LD_LIBRARY_PATH=str(tools.parent / "lib64"))
    with open(image, "rb") as f:
        head = f.read(2048)
    if head[1024:1028] == b"\xe2\xe1\xf5\xe0":
        subprocess.run([str(tools / "fsck.erofs"), f"--extract={dest}", "--no-preserve", str(image)], check=True,
                       env=env, stdout=subprocess.DEVNULL)
    elif head[1024 + 56:1024 + 58] == b"\x53\xef":
        Path(dest).mkdir(parents=True, exist_ok=True)
        subprocess.run([str(tools / "debugfs_static"), "-R", f"rdump / {dest}", str(image)], check=True,
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        raise ValueError(f"{image}: neither erofs nor ext4")


def check_tree(policy, roots, apex_rc=()):
    """Findings and an inventory for extracted partitions."""
    rc_re, bin_re = re.compile(policy["rc_pattern"]), re.compile(policy["binary_pattern"])
    forbidden = set(policy["forbidden_names"])
    findings, rc_seen, binaries, neutralised = [], {}, [], {}
    files = {}
    for runtime, local in walk(roots):
        files[runtime] = local
        base = runtime.rsplit("/", 1)[1]
        if base in forbidden:
            findings.append(dict(kind="forbidden", path=runtime, detail=f"{base} must not be in an OpenBook image"))
        if local.is_symlink() or not local.is_file():
            continue
        parts = runtime.split("/")
        if any(p in ("bin", "xbin") for p in parts[:-1]) and bin_re.search(base):
            binaries.append(runtime)
            if runtime not in policy["reviewed_binaries"]:
                findings.append(dict(kind="unreviewed-binary", path=runtime,
                                     detail="a firmware/TPM/EC tool by name; review it and list it in reviewed_binaries"))
        if base.endswith(".rc"):
            data = local.read_bytes()
            hits = rc_hits(data.decode("utf-8", "replace"), rc_re)
            if hits or runtime in policy["neutralised"] or runtime in policy["reviewed_rc"]:
                rc_seen[runtime] = dict(sha256=sha_bytes(data), matches=hits)
    for runtime, data in apex_rc:
        hits = rc_hits(data.decode("utf-8", "replace"), rc_re)
        if hits or runtime in policy["reviewed_rc"]:
            rc_seen[runtime] = dict(sha256=sha_bytes(data), matches=hits)
    for runtime, rule in policy["neutralised"].items():
        seen = rc_seen.get(runtime)
        state = ("missing" if seen is None else "neutralised" if seen["sha256"] == rule["sha256"]
                 else "google" if seen["sha256"] == rule["google_sha256"] else "changed")
        neutralised[runtime] = state
        if state != "neutralised" and roots.get("system") is not None and runtime.startswith("/system/"):
            detail = {"missing": "absent: Google removed or moved it; review the rule",
                      "google": "still Google's original: it runs on this image",
                      "changed": "neither OpenBook's replacement nor the reviewed Google original"}[state]
            findings.append(dict(kind="not-neutralised", path=runtime, detail=detail))
    reviewed = {}
    for runtime, seen in sorted(rc_seen.items()):
        if runtime in policy["neutralised"]:
            continue
        rule = policy["reviewed_rc"].get(runtime)
        if rule is None:
            findings.append(dict(kind="unreviewed-rc", path=runtime, detail=f"matches {seen['matches']}"))
        elif rule["sha256"] != seen["sha256"]:
            findings.append(dict(kind="changed-rc", path=runtime,
                                 detail=f"reviewed at {rule['sha256'][:12]}, now {seen['sha256'][:12]}; matches {seen['matches']}"))
        else:
            reviewed[runtime] = rule["verdict"]
    mounts = {MOUNTS[n] for n in roots}
    absent = sorted(r for r in policy["reviewed_rc"]
                    if r not in rc_seen and not r.startswith("/apex/") and mount_of(r) in mounts)
    return findings, dict(neutralised=neutralised, reviewed_rc=reviewed, absent_reviewed_rc=absent,
                          rc_matches={k: v for k, v in sorted(rc_seen.items())}, binaries=sorted(binaries),
                          partitions=sorted(roots), apex_rc_files=len(apex_rc))


def mount_of(runtime):
    for mount in sorted(MOUNTS.values(), key=len, reverse=True):
        if mount != "/" and (runtime == mount or runtime.startswith(mount + "/")):
            return mount
    return "/"


def varint(buf, i):
    shift = value = 0
    while True:
        if i >= len(buf):
            raise ValueError("truncated varint")
        byte = buf[i]
        i += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, i
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def fields(buf):
    """(field number, wire type, value) of a protobuf message; value is int or bytes."""
    i = 0
    while i < len(buf):
        key, i = varint(buf, i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, i = varint(buf, i)
        elif wire == 1:
            value, i = buf[i:i + 8], i + 8
        elif wire == 2:
            n, i = varint(buf, i)
            value, i = buf[i:i + n], i + n
            if i > len(buf):
                raise ValueError("truncated field")
        elif wire == 5:
            value, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
        yield number, wire, value


def payload_manifest(data):
    """The DeltaArchiveManifest bytes of a major-version-2 payload (update_engine's update_metadata.proto)."""
    if data[:4] != b"CrAU":
        raise ValueError("not an update_engine payload (no CrAU magic)")
    version, size = struct.unpack_from(">QQ", data, 4)
    if version != 2:
        raise ValueError(f"payload major version {version}; only 2 is supported")
    return data[24:24 + size]


def payload_partitions(manifest):
    """[{name, run_postinstall, postinstall_path, postinstall_optional}] from manifest field 13 (partitions):
    PartitionUpdate 1 partition_name, 2 run_postinstall, 3 postinstall_path, 9 postinstall_optional."""
    out = []
    for number, wire, value in fields(manifest):
        if number != 13 or wire != 2:
            continue
        part = dict(name=None, run_postinstall=False, postinstall_path="", postinstall_optional=False)
        for n, w, v in fields(value):
            if n == 1 and w == 2:
                part["name"] = v.decode()
            elif n == 2 and w == 0:
                part["run_postinstall"] = bool(v)
            elif n == 3 and w == 2:
                part["postinstall_path"] = v.decode()
            elif n == 9 and w == 0:
                part["postinstall_optional"] = bool(v)
        out.append(part)
    return out


def read_payload(path):
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z, z.open("payload.bin") as f:
            head = f.read(24)
            _, size = struct.unpack_from(">QQ", head, 4) if head[:4] == b"CrAU" else (0, 0)
            return head + f.read(size)
    with open(path, "rb") as f:
        head = f.read(24)
        _, size = struct.unpack_from(">QQ", head, 4) if head[:4] == b"CrAU" else (0, 0)
        return head + f.read(size)


def check_payload(policy, path):
    parts = payload_partitions(payload_manifest(read_payload(path)))
    if not parts:
        raise ValueError("payload manifest lists no partitions")
    findings = []
    if policy["payload"]["postinstall"] == "forbidden":
        for part in parts:
            if part["run_postinstall"] or part["postinstall_path"]:
                findings.append(dict(kind="postinstall", path=part["name"],
                                     detail=f"runs postinstall {part['postinstall_path'] or '(default path)'}"))
    return findings, dict(partitions=[p["name"] for p in parts],
                          postinstall=[p for p in parts if p["run_postinstall"] or p["postinstall_path"]])


def named(values, kind):
    out = {}
    for item in values:
        name, sep, path = item.partition("=")
        if not sep or name not in MOUNTS or name in out:
            raise ValueError(f"Expected NAME={kind} with NAME one of {sorted(MOUNTS)}, each once: {item!r}")
        out[name] = Path(path)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("tree", "images", "payload"))
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--policy", type=Path, default=POLICY)
    ap.add_argument("--tools", type=Path, help="otatools bin (fsck.erofs, debugfs_static); also scans APEX rc files")
    ap.add_argument("--work", type=Path, help="scratch directory for extraction (must not exist)")
    ap.add_argument("--output", type=Path)
    a = ap.parse_args(argv)
    try:
        policy = load_policy(a.policy)
        if a.mode == "payload":
            if len(a.inputs) != 1:
                raise ValueError("payload takes one file")
            findings, inventory = check_payload(policy, a.inputs[0])
            subject = dict(payload=str(a.inputs[0]), payload_sha256=sha_file(a.inputs[0]))
        else:
            if (a.tools is None) != (a.work is None) or (a.mode == "images" and a.tools is None):
                raise ValueError("--tools and --work go together (and images needs both)")
            if a.work:
                a.work.mkdir(mode=0o700, parents=True)
            if a.mode == "images":
                images = named(a.inputs, "IMAGE")
                roots = {}
                for name, image in images.items():
                    roots[name] = a.work / name
                    extract(image, roots[name], a.tools)
                subject = dict(images={n: sha_file(p) for n, p in images.items()})
            else:
                roots = named(a.inputs, "DIR")
                subject = dict(trees={n: str(p) for n, p in roots.items()})
            apex = apex_rc_files(roots, a.tools, a.work) if a.tools else ()
            findings, inventory = check_tree(policy, roots, apex)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as e:
        print(f"check-firmware-safety: {e}", file=sys.stderr)
        return 2
    result = dict(schema=RESULT_SCHEMA, mode=a.mode, passed=not findings, policy_sha256=sha_file(a.policy),
                  **subject, findings=findings, inventory=inventory)
    text = json.dumps(result, indent=2) + "\n"
    if a.output:
        a.output.write_text(text)
    for f in findings:
        print(f"FINDING {f['kind']}: {f['path']}: {f['detail']}")
    print(f"firmware safety ({a.mode}): {'PASS' if not findings else 'FAIL'}, {len(findings)} finding(s)")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
