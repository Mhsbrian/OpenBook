#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare a private system-only update of a fresh offline installed snapshot.

Regular files only. No A/B claims, device writes, GPT growth or userdata restore.
The CURRENT installed snapshot supplies all data, metadata, UUIDs and boot
identity. The fresh input candidate supplies only super/vbmeta and their digest.
Physical application requires a separately reviewed offline recovery workflow.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def load(name, filename):
    s = importlib.util.spec_from_file_location(name, HERE / filename)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


m = load("migration", "migrate.py")
p = load("preserve", "preserve-update.py")
b = load("candidate", "build-input-candidate.py")
INPUT27_IMAGE = "816e694848c146b84c661f46717cf113f5df9ae47c07556cbba4b2021f5f4bf9"


def validate_candidate(old, new):
    if old["image_sha256"] != b.CAMERA25:
        raise ValueError("Unreviewed installed baseline")
    if new["image_sha256"] != INPUT27_IMAGE:
        raise ValueError("Candidate is not the exact reviewed input27 artifact")
    if new.get("input_correction") != dict(source_sha256=b.patcher.SOURCE_SHA256,
        output_sha256="4752d1351dbed7f0b5cb5a1d31d409edbb91396c6627fd7b34e1e99a0e655148",
        offset=0x24cb58, bytes=8, hardware_validated=False):
        raise ValueError("Unreviewed input correction")
    # Existing compatibility checks must pass with only the reviewed system
    # logical image difference removed. No vendor/kernel/credential changes.
    check = copy.deepcopy(new)
    check["logical_sha256"]["system"] = old["logical_sha256"]["system"]
    p.compatible(old, check)
    if old["logical_sha256"]["vendor"] != new["logical_sha256"]["vendor"]:
        raise ValueError("Concurrent vendor change is not qualified")


def prepare(snapshot, expected_sha, base, candidate, out):
    snapshot = p.regular(snapshot)
    source = p.regular(candidate / "ruby-live.img")
    baseline_image = p.regular(base / "ruby-live.img")
    old = json.loads(p.regular(base / "manifest.json").read_text())
    new = json.loads(p.regular(candidate / "manifest.json").read_text())
    validate_candidate(old, new)
    m.require(p.h.audit.sha(baseline_image) == b.CAMERA25, "Baseline artifact hash mismatch")
    p.verify_manifest(old, p.read_gpt(baseline_image), baseline_image.stat().st_size)
    m.require(p.h.audit.sha(snapshot) == expected_sha, "Fresh installed backup hash mismatch")
    m.require(p.h.audit.sha(source) == new["image_sha256"], "Candidate hash mismatch")
    p.verify_manifest(new, p.read_gpt(source), source.stat().st_size)
    with snapshot.open("rb") as f:
        gpt = m.read_gpt(f.fileno())
    rows = gpt["rows"]
    m.require(gpt["used_bytes"] == snapshot.stat().st_size, "Backup must include final GPT")
    m.require([(r["name"], *m.extent(r)) for r in rows] ==
              [(r["name"], *m.extent(r)) for r in old["gpt"]],
              "Unsupported installed layout; review expanded data separately")
    for row in rows:
        if row["name"] in m.STATIC:
            expected = old["payload_readback"][row["name"]]
            m.require(p.digest_range(baseline_image, *m.extent(row)) == expected,
                      "Baseline manifest payload mismatch")
            m.require(p.digest_range(snapshot, *m.extent(row)) == expected,
                      f"Installed baseline differs: {row['name']}")
            m.require(p.digest_range(source, *m.extent(row)) == new["payload_readback"][row["name"]],
                      "Candidate payload readback mismatch")
    w = out
    w.mkdir(mode=0o700, parents=True, exist_ok=False)
    esp = w / "esp.img"
    p.live.copy_range(snapshot, esp, *m.extent(rows[0]))
    m.run("fsck.fat", "-n", esp)
    tree = w / "esp-before"; tree.mkdir()
    m.run("mcopy", "-s", "-i", esp, "::*", tree)
    installed = json.loads((tree / "ruby/RESEARCH.json").read_text())
    m.require(installed.get("schema") == "openbook-ruby-installed/1", "Requires installed Ruby manifest")
    m.require(installed.get("gpt") == rows and installed.get("same_machine_only") is True,
              "Installed disk identity mismatch")
    m.require(installed["kernel_sha256"] == old["kernel_sha256"] ==
              p.h.audit.sha(tree / "ruby/kernel"), "Installed kernel mismatch")
    reference_kernel = w / "candidate-kernel"
    m.run("mcopy", "-i", f"{source}@@{m.extent(new['gpt'][0])[0]}", "::/ruby/kernel", reference_kernel)
    m.require(p.h.audit.sha(reference_kernel) == old["kernel_sha256"], "Unreviewed EFI kernel")
    changed = {"ruby/RESEARCH.json"}
    for mode in m.MODES:
        name = f"ruby/initrd-{mode}.img"
        body, params = m.parse_initrd((tree / name).read_bytes())
        expected = dict(old["entries"][mode])
        expected.update({"androidboot.boot_part_uuid":rows[0]["partuuid"],
                         "androidboot.openbook.ruby_installed":"1"})
        m.require(params == expected == installed["entries"][mode], "Boot identity/security drift")
        reference = w / f"candidate-initrd-{mode}.img"
        m.run("mcopy", "-i", f"{source}@@{m.extent(new['gpt'][0])[0]}", f"::/{name}", reference)
        new_body, new_params = m.parse_initrd(reference.read_bytes())
        m.require(body == new_body and new_params == new["entries"][mode],
                  "Candidate initrd changed")
        params["androidboot.vbmeta.digest"] = new_params["androidboot.vbmeta.digest"]
        reference.write_bytes(body + m.bootconfig(params, len(body)))
        m.run("mcopy", "-o", "-i", esp, reference, f"::/{name}")
        installed["entries"][mode] = params
        changed.add(name)
    installed["payload_readback"].update({n:new["payload_readback"][n] for n in ("super","vbmeta_a")})
    installed["input_correction"] = new["input_correction"]
    installed["system_update"] = "input27"
    embedded = w / "RESEARCH.json"
    embedded.write_text(json.dumps(installed, indent=2) + "\n")
    m.run("mcopy", "-o", "-i", esp, embedded, "::/ruby/RESEARCH.json")
    m.run("fsck.fat", "-n", esp)
    after = w / "esp-after"; after.mkdir()
    m.run("mcopy", "-s", "-i", esp, "::*", after)
    m.require({k:v for k,v in p.tree_hashes(tree).items() if k not in changed} ==
              {k:v for k,v in p.tree_hashes(after).items() if k not in changed},
              "Unrelated EFI files changed")
    for mode in m.MODES:
        m.require(m.parse_initrd((after / f"ruby/initrd-{mode}.img").read_bytes())[1] ==
                  installed["entries"][mode], "Bootconfig readback failed")
    m.require((after / "ruby/RESEARCH.json").read_bytes() == embedded.read_bytes(), "Manifest readback failed")
    output = w / "installed.img"
    m.run("cp", "--reflink=auto", snapshot, output)
    writes = []
    with output.open("r+b") as f:
        for name in ("super","vbmeta_a","EFI"):
            row = next(r for r in rows if r["name"] == name)
            start, size = m.extent(row)
            src, offset = (esp,0) if name == "EFI" else (source,start)
            wanted = p.digest_range(src,offset,size)
            with src.open("rb") as inp:
                inp.seek(offset); f.seek(start); left=size
                while left:
                    data=inp.read(min(left,4<<20))
                    m.require(bool(data), "Truncated payload")
                    f.write(data); left-=len(data)
            f.flush(); os.fsync(f.fileno())
            m.require(p.digest_range(output,start,size)==wanted,"System update readback failed")
            writes.append(dict(name=name,offset=start,length=size,sha256=wanted))
    protected=[]
    for start,size in p.protected_ranges(rows,snapshot.stat().st_size):
        digest=p.digest_range(snapshot,start,size)
        m.require(p.digest_range(output,start,size)==digest,"Data/identity/GPT changed")
        protected.append(dict(offset=start,length=size,sha256=digest))
    m.require(p.h.audit.sha(snapshot)==expected_sha and p.h.audit.sha(source)==new["image_sha256"],
              "Input changed")
    report=dict(schema="openbook-ruby-installed-update/1",complete=True,
        baseline_backup_sha256=expected_sha,candidate_sha256=new["image_sha256"],
        image_sha256=p.h.audit.sha(output),writes=writes,protected=protected,
        sources_unchanged=True,physical_device_written=False,userdata_written=False,
        layout_expanded=False,automatic_rollback=False,physical_unlock_validated=False)
    (w/"update.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot","base","candidate","out"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--snapshot-sha256",required=True)
    a=parser.parse_args()
    if not Path("/.dockerenv").exists(): parser.error("Use inst-docker.sh; no physical devices")
    os.umask(0o077)
    result=prepare(a.snapshot,a.snapshot_sha256,a.base,a.candidate,a.out)
    print(json.dumps({k:result[k] for k in ("complete","userdata_written","physical_device_written")}))
