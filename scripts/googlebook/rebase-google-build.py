#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebase the OpenBook G14 layer onto a new Google Ruby build: the "patch" step of intercept -> patch -> update.

An OpenBook Ruby candidate keeps Google's framework partitions and changes only
`system` (trackpad correction, Digitalis ARM bridge, OTA certificate, owner OTA
policy); vendor, vendor_dlkm, system_dlkm and the boot chain are OpenBook's own.
Given the candidate's Google base build (OLD) and a newer Google build (NEW),
staged by stage-stock-source.py, this produces the same candidate on NEW:

  system      NEW's tree plus OpenBook's exact delta against OLD (every added,
              removed and changed path, with its inode metadata and xattrs);
  system_ext, product   NEW's images verbatim (the candidate must hold OLD's verbatim);
  the rest    the candidate's own images, unchanged.

It fails closed. A path OpenBook changed must be unchanged between OLD and NEW
(bytes and metadata), except text files in MERGEABLE, which take a line-level
three-way merge that refuses overlapping edits. Paths OpenBook adds must not
exist in NEW. The rebuilt image must match the expected inventory exactly
(build-input-candidate.rebuild_erofs), and the candidate is assembled by the
same path as every other OpenBook candidate (build-input-candidate.assemble).

usage: rebase-google-build.py --base STAGED_CANDIDATE --base-sha256 SHA --old-stock DIR --new-stock DIR
                              --tools AOSP_HOST_BIN --inventory erofs-inventory --key AVB_KEY --out DIR
Container only (inst-docker.sh). Regular image files; Google images stay private.
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


b = load("builder", "build-input-candidate.py")
p = b.p
FRAMEWORK_VERBATIM = ("system_ext", "product")
MERGEABLE = {"/system/build.prop"}


def by_path(rows):
    """erofs-inventory rows grouped by path: {path: sorted rows}."""
    out = {}
    for row in rows:
        out.setdefault(bytes.fromhex(row.split(" ")[1]).decode(), []).append(row)
    return {k: sorted(v) for k, v in out.items()}


def with_size(rows, size):
    out = []
    for row in rows:
        f = row.split(" ")
        if f[0] == "I":
            f[6] = str(size)
        out.append(" ".join(f))
    return sorted(out)


def entry(root, path):
    local = root / path.lstrip("/")
    if local.is_symlink():
        return ["symlink", os.readlink(local)]
    if local.is_file():
        return ["file", p.h.audit.sha(local)]
    return ["dir"] if local.is_dir() else None


def merge3(old, ours, new):
    """Apply ours' edits of old onto new, line by line. Refuses edits that touch lines new changed."""
    old_to_new = {}
    for i, j, n in difflib.SequenceMatcher(None, old, new, autojunk=False).get_matching_blocks():
        for k in range(n):
            old_to_new[i + k] = j + k
    out = list(new)
    hunks = [op for op in difflib.SequenceMatcher(None, old, ours, autojunk=False).get_opcodes() if op[0] != "equal"]
    for _tag, i1, i2, j1, j2 in reversed(hunks):
        # The replaced lines and one line of context each side must be unchanged upstream.
        span = range(max(i1 - 1, 0), min(i2 + 1, len(old)))
        if any(k not in old_to_new for k in span):
            raise ValueError(f"Edit at line {i1 + 1} overlaps an upstream change")
        mapped = [old_to_new[k] for k in span]
        if mapped != list(range(mapped[0], mapped[0] + len(mapped))):
            raise ValueError(f"Upstream moved the context of the edit at line {i1 + 1}")
        at = old_to_new[i1] if i1 < len(old) else len(new)
        if i1 == i2 and i1 > 0:
            at = old_to_new[i1 - 1] + 1
        out[at:at + (i2 - i1)] = ours[j1:j2]
    return out


def plan_delta(old, ours, new, old_tree, ours_tree, new_tree):
    """OpenBook's delta against OLD, checked against NEW. Returns (expected rows by path, actions)."""
    added = sorted(set(ours) - set(old))
    removed = sorted(set(old) - set(ours))
    changed = sorted(k for k in set(old) & set(ours)
                     if old[k] != ours[k] or entry(old_tree, k) != entry(ours_tree, k))
    expected = dict(new)
    merged = {}
    for path in removed:
        if new.get(path) != old[path] or entry(new_tree, path) != entry(old_tree, path):
            raise ValueError(f"{path}: OpenBook removes it, but NEW changed it")
        del expected[path]
    for path in changed:
        if path in MERGEABLE:
            if path not in new or with_size(new[path], 0) != with_size(old[path], 0) \
                    or with_size(ours[path], 0) != with_size(old[path], 0):
                raise ValueError(f"{path}: merge needs unchanged ownership, mode and labels")
            lines = merge3(*((t / path.lstrip("/")).read_text().splitlines(keepends=True)
                             for t in (old_tree, ours_tree, new_tree)))
            merged[path] = "".join(lines).encode()
            expected[path] = with_size(new[path], len(merged[path]))
            continue
        if new.get(path) != old[path] or entry(new_tree, path) != entry(old_tree, path):
            raise ValueError(f"{path}: OpenBook changes it, but NEW changed it too")
        expected[path] = ours[path]
    for path in added:
        if path in new:
            raise ValueError(f"{path}: OpenBook adds it, but NEW already has it")
        expected[path] = ours[path]
    return expected, dict(added=added, removed=removed, changed=changed, merged=merged)


def apply_delta(source, ours_tree, actions):
    """Turn the extracted NEW tree into the rebased tree."""
    for path in sorted(actions["removed"], key=lambda k: -k.count("/")):
        local = source / path.lstrip("/")
        if local.is_dir() and not local.is_symlink():
            local.rmdir()
        else:
            local.unlink()
    for path in sorted(actions["added"] + actions["changed"], key=lambda k: k.count("/")):
        if path in actions["merged"]:
            continue
        src, dst = ours_tree / path.lstrip("/"), source / path.lstrip("/")
        if src.is_symlink():
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            os.symlink(os.readlink(src), dst)
        elif src.is_dir():
            dst.mkdir(exist_ok=True)
        else:
            shutil.copyfile(src, dst)
    for path, data in actions["merged"].items():
        (source / path.lstrip("/")).write_bytes(data)


def stock(directory, names):
    record = json.loads((directory / "stock.json").read_text())
    images = {}
    for name in names:
        image = p.regular(directory / f"{name}.img")
        if p.h.audit.sha(image) != record["partitions"][name]["sha256"]:
            raise ValueError(f"{directory.name}/{name}.img differs from its stock record")
        images[name] = image
    return record, images


def rebase(a):
    base = p.regular(a.base / "ruby-live.img")
    old_manifest = json.loads(p.regular(a.base / "manifest.json").read_text())
    if old_manifest["image_sha256"] != a.base_sha256 or p.h.audit.sha(base) != a.base_sha256:
        raise ValueError("Base image differs from its reviewed pin")
    logical = {n: p.regular(a.base / f"logical/{n}_a.img") for n in old_manifest["logical_sha256"]}
    for name, digest in old_manifest["logical_sha256"].items():
        if p.h.audit.sha(logical[name]) != digest:
            raise ValueError(f"Base logical image differs from manifest: {name}")
    old_rec, old_img = stock(a.old_stock, ("system",) + FRAMEWORK_VERBATIM)
    new_rec, new_img = stock(a.new_stock, ("system",) + FRAMEWORK_VERBATIM)
    for name in FRAMEWORK_VERBATIM:
        if old_manifest["logical_sha256"][name] != p.h.audit.sha(old_img[name]):
            raise ValueError(f"The candidate's {name} is not OLD's verbatim; cannot rebase it")
    w = a.out
    w.mkdir(mode=0o700, parents=True, exist_ok=False)
    run = p.h.run
    trees, rows = {}, {}
    for label, image in (("old", old_img["system"]), ("ours", logical["system"]), ("new", new_img["system"])):
        trees[label] = w / f"tree-{label}"
        run(a.tools / "fsck.erofs", f"--extract={trees[label]}", image)
        rows[label] = by_path(b.inventory(a.inventory, image))
    expected_rows, actions = plan_delta(rows["old"], rows["ours"], rows["new"],
                                        trees["old"], trees["ours"], trees["new"])
    source = w / "source"
    run(a.tools / "fsck.erofs", f"--extract={source}", new_img["system"])
    apply_delta(source, trees["ours"], actions)
    expected_metadata = sorted(r for v in expected_rows.values() for r in v)
    # Expected bytes come from the three inputs, independently of the tree just assembled.
    ours_paths = set(actions["added"]) | set(actions["changed"])
    expected_contents = {}
    for path in expected_rows:
        if path in actions["merged"]:
            e = ["file", hashlib.sha256(actions["merged"][path]).hexdigest()]
        else:
            e = entry(trees["ours"] if path in ours_paths else trees["new"], path)
        if e and e[0] != "dir":
            expected_contents[path] = e
    (w / "expected.metadata").write_text("\n".join(expected_metadata) + "\n")
    rebuilt, after = b.rebuild_erofs(a, w, source, expected_metadata, expected_contents)
    run(a.tools / "avbtool", "add_hashtree_footer", "--image", rebuilt, "--partition_name", "system",
        "--partition_size", new_img["system"].stat().st_size, "--do_not_generate_fec", "--hash_algorithm", "sha256")
    images = dict(logical, system=rebuilt, **{n: new_img[n] for n in FRAMEWORK_VERBATIM})
    props = {}
    for line in actions["merged"].get("/system/build.prop", b"").decode().splitlines():
        key, sep, value = line.partition("=")
        if sep and key in ("ro.build.id", "ro.build.version.incremental", "ro.build.version.security_patch",
                           "ro.system.build.fingerprint", "ro.dalvik.vm.native.bridge"):
            props[key] = value
    annotation = dict(
        old_build=old_rec["build"], new_build=new_rec["build"], build_properties=props,
        google_sha256={f"{n}_old": p.h.audit.sha(old_img[n]) for n in ("system",) + FRAMEWORK_VERBATIM}
        | {f"{n}_new": p.h.audit.sha(new_img[n]) for n in ("system",) + FRAMEWORK_VERBATIM},
        verbatim_from_new=list(FRAMEWORK_VERBATIM),
        system_delta=dict(added=len(actions["added"]), removed=len(actions["removed"]),
                          changed=len(actions["changed"]), merged=sorted(actions["merged"])),
        hardware_validated=False)
    details = dict(google_rebase=annotation, metadata_rows=len(expected_metadata),
                   all_inode_xattrs_as_expected=after == expected_metadata)
    b.assemble(a, w, base, old_manifest, a.base_sha256, images, {"google_rebase": annotation},
               "openbook-ruby-google-rebase/1", details)
    (w / "delta.json").write_text(json.dumps(dict(actions, merged=sorted(actions["merged"])), indent=1) + "\n")
    print(json.dumps(dict(new_build=new_rec["build"], properties=props, delta=annotation["system_delta"],
                          image_sha256=json.loads((w / "manifest.json").read_text())["image_sha256"]), indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("base", "old-stock", "new-stock", "tools", "inventory", "key", "out"):
        ap.add_argument("--" + name, type=Path, required=True)
    ap.add_argument("--base-sha256", required=True)
    args = ap.parse_args()
    if not Path("/.dockerenv").exists():
        ap.error("Use inst-docker.sh; regular images only")
    os.umask(0o077)
    rebase(args)
