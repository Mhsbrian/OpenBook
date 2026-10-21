#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("preserve_vm", Path(__file__).with_name("preserve-bridge-vm.py"))
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)


class PreserveTests(unittest.TestCase):
    def setUp(self):
        self.old = {
            "gpt": [{"name": "super", "first_lba": 10, "last_lba": 20}],
            "kernel_sha256": "kernel", "vendor_cmdline": "bootconfig",
            "logical_sha256": {"system": "old", "system_ext": "same", "vendor": "old-probe"},
            "payload_readback": {name: name for name in v.p.BOOT},
            "entries": {name: {"androidboot.selinux": "enforcing", "androidboot.veritymode": "enforcing",
                "androidboot.vbmeta.digest": "old", "androidboot.vbmeta.size": "4032"}
                for name in ["live", "logs", "safe-logs", "serial", "serial-logs"]}}
        self.new = copy.deepcopy(self.old)
        self.new.update(vm_instrumentation={"not_for_release": True},
                        bridge_correction={"selected": "libberberis_arm64.so"})
        self.new["logical_sha256"].update(system="new", vendor="new-probe")
        self.guard = patch.object(v, "BASE_MANIFEST", v.p.manifest_fingerprint(self.old))
        self.guard.start(); self.addCleanup(self.guard.stop)

    def check(self): v.compatible(self.old, self.new, v.EXPERIMENT)

    def test_exact_synthetic_fixture_accepts_instrumented_system(self): self.check()

    def test_other_base_manifest_rejected(self):
        self.old["unknown"] = "different"
        with self.assertRaises(ValueError): self.check()

    def test_uninstrumented_candidate_rejected(self):
        self.new["vm_instrumentation"]["not_for_release"] = False
        with self.assertRaises(ValueError): self.check()

    def test_other_bridge_rejected(self):
        self.new["bridge_correction"]["selected"] = "libhoudini.so"
        with self.assertRaises(ValueError): self.check()

    def test_kernel_change_rejected(self):
        self.new["kernel_sha256"] = "different"
        with self.assertRaises(ValueError): self.check()

    def test_unrelated_framework_change_rejected(self):
        self.new["logical_sha256"]["system_ext"] = "different"
        with self.assertRaises(ValueError): self.check()

    def test_permissive_boot_rejected(self):
        self.new["entries"]["logs"]["androidboot.selinux"] = "permissive"
        with self.assertRaises(ValueError): self.check()

    def test_missing_explicit_experiment_rejected(self):
        with self.assertRaises(ValueError): v.compatible(self.old, self.new)


if __name__ == "__main__": unittest.main()
