#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Negative gates and exact-build checks; paths refer only to local licensed inputs."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

s=importlib.util.spec_from_file_location("installed",Path(__file__).with_name("installed-update.py"))
u=importlib.util.module_from_spec(s); s.loader.exec_module(u)
p=argparse.ArgumentParser()
p.add_argument("--library",type=Path,required=True)
p.add_argument("--base-manifest",type=Path,required=True)
p.add_argument("--candidate-manifest",type=Path,required=True)
a=p.parse_args()


class Gates(unittest.TestCase):
    def setUp(self):
        self.old=json.loads(a.base_manifest.read_text())
        self.new=json.loads(a.candidate_manifest.read_text())

    def test_reviewed_candidate(self):
        u.validate_candidate(self.old,self.new)

    def test_baseline_manifest_matches_pinned_artifact(self):
        image=u.p.regular(a.base_manifest.parent/"ruby-live.img")
        self.assertEqual(u.p.h.audit.sha(image),u.b.CAMERA25)
        rows=u.p.read_gpt(image)
        u.p.verify_manifest(self.old,rows,image.stat().st_size)
        for row in rows:
            if row["name"] in u.m.STATIC:
                self.assertEqual(u.p.digest_range(image,*u.m.extent(row)),
                                 self.old["payload_readback"][row["name"]])

    def test_unknown_artifact(self):
        self.new["image_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"exact reviewed"):
            u.validate_candidate(self.old,self.new)

    def test_kernel_boot_vendor_and_identity_drift(self):
        variants=[]
        for key in ("kernel_sha256","vendor_cmdline"):
            c=copy.deepcopy(self.new); c[key]="unexpected"; variants.append(c)
        c=copy.deepcopy(self.new); c["logical_sha256"]["vendor"]="0"*64; variants.append(c)
        c=copy.deepcopy(self.new); c["payload_readback"]["boot_a"]="0"*64; variants.append(c)
        c=copy.deepcopy(self.new); c["entries"]["live"]["androidboot.serialno"]="different"; variants.append(c)
        c=copy.deepcopy(self.new); c["entries"]["live"]["androidboot.selinux"]="permissive"; variants.append(c)
        for c in variants:
            with self.subTest(candidate=c.get("kernel_sha256")):
                with self.assertRaises(ValueError): u.validate_candidate(self.old,c)

    def test_wrong_patch_profile(self):
        self.new["input_correction"]["bytes"]=9
        with self.assertRaises(ValueError): u.validate_candidate(self.old,self.new)

    def test_device_and_symlink_refused(self):
        with self.assertRaises(ValueError): u.p.regular(Path("/dev/null"))
        with tempfile.TemporaryDirectory() as tmp:
            link=Path(tmp)/"alias"; link.symlink_to(a.library.resolve())
            with self.assertRaises(ValueError): u.p.regular(link)

    def test_patch_changes_exactly_instruction(self):
        before=a.library.read_bytes()
        after,off=u.b.patcher.patch(before)
        self.assertEqual(after[:off],before[:off])
        self.assertEqual(after[off+8:],before[off+8:])
        self.assertEqual(after[off:off+8],b"\x90"*8)
        self.assertEqual(u.p.hashlib.sha256(after).hexdigest(),
                         self.new["input_correction"]["output_sha256"])

    def test_patch_refuses_modified_or_already_patched_library(self):
        before=a.library.read_bytes(); after,_=u.b.patcher.patch(before)
        for data in (before[:-1],before+b"\0",after,bytes([before[0]^1])+before[1:]):
            with self.assertRaises(ValueError): u.b.patcher.patch(data)


unittest.main(argv=["input-candidate-test"],verbosity=2)
