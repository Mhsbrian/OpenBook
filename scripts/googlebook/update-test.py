#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Synthetic trust/staging and init experiment tests. No Google payload or devices."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


s = module("update-stage")
q = module("update-quarantine")
i = module("update-inventory")


class StageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory()
        cls.key = Path(cls.keys.name) / "private.pem"
        cls.pub = Path(cls.keys.name) / "public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                        "-out", str(cls.key)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(cls.key), "-pubout", "-out", str(cls.pub)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.original = self.root / "original"
        self.original.write_bytes(b"authorized synthetic full recovery")
        self.candidate = self.root / "candidate"
        self.candidate.mkdir()
        for name in ("kernel", "system", "installer-pin", "evidence"):
            (self.candidate / name).write_bytes(("synthetic " + name).encode())
        self.profile = {
            "schema": "openbook-ruby-update-profile/1", "build": "fixture-1", "target": "synthetic-vm",
            "local_only": True, "hardware_eligible": False,
            "original": {"kind": "full-recovery", "url": "https://example.invalid/synthetic",
                         "sha256": s.digest(self.original)},
            "artifacts": {n: s.digest(self.candidate / n) for n in ("kernel", "system", "installer-pin")}}
        tuple_sha = s.hashlib.sha256(s.canonical({k: self.profile[k] for k in
                                                ("original", "artifacts", "target", "build")})).hexdigest()
        self.review = {"schema": "openbook-ruby-update-review/1", "stage": "rehearsal",
                       "tuple_sha256": tuple_sha, "expires_utc": "2100-01-01T00:00:00Z",
                       "checks": {g: {"passed": True, "report": "evidence",
                                      "sha256": s.digest(self.candidate / "evidence"),
                                      "tuple_sha256": tuple_sha}
                                  for gates in s.GATES.values() for g in gates}}
        self.p = self.root / "profile.json"
        self.r = self.root / "review.json"
        self.sig = self.root / "review.sig"
        self.out = self.root / "staged"
        self.sign()

    def tearDown(self):
        self.tmp.cleanup()

    def sign(self):
        self.p.write_bytes(s.canonical(self.profile))
        self.review["profile_sha256"] = s.digest(self.p)
        self.r.write_bytes(s.canonical(self.review))
        subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(self.key), "-out",
                        str(self.sig), str(self.r)], check=True, capture_output=True)

    def stage(self, stage="rehearsal"):
        return s.stage_files(self.original, self.candidate, self.p, self.r, self.sig, self.pub, stage, self.out)

    def test_positive_exact_tuple_staged_original_preserved(self):
        before = s.digest(self.original)
        result = self.stage()
        self.assertTrue(result["accepted_for_stage"])
        self.assertFalse(result["automatic_install_authorized"])
        self.assertEqual(s.digest(self.original), before)
        self.assertEqual(s.digest(self.out / "original"), before)
        self.assertEqual(s.digest(self.out / "artifacts/kernel"), s.digest(self.candidate / "kernel"))
        with self.assertRaisesRegex(ValueError, "Fresh"):
            self.stage()

    def test_unknown_original_refused_before_output(self):
        self.original.write_bytes(b"unfamiliar build")
        with self.assertRaisesRegex(ValueError, "Unknown original"):
            self.stage()
        self.assertFalse(self.out.exists())

    def test_bad_signature_and_unsigned_profile(self):
        self.r.write_bytes(self.r.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "signature"):
            self.stage()
        self.sign()
        self.p.write_bytes(self.p.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "profile"):
            self.stage()

    def test_incompatible_and_missing_gates(self):
        for gate in s.GATES["rehearsal"]:
            original = copy.deepcopy(self.review["checks"])
            self.review["checks"].pop(gate)
            self.sign()
            with self.subTest(gate=gate), self.assertRaisesRegex(ValueError, "Gate not passed"):
                self.stage()
            self.review["checks"] = original
        self.review["checks"]["vintf"]["passed"] = False
        self.sign()
        with self.assertRaisesRegex(ValueError, "Gate not passed: vintf"):
            self.stage()
        self.assertFalse(self.out.exists())

    def test_promotion_requires_every_prior_gate(self):
        self.profile["hardware_eligible"] = True
        self.review["stage"] = "promotion"
        for gate in s.GATES["trial"] + s.GATES["promotion"]:
            self.review["checks"][gate]["passed"] = False
            self.sign()
            with self.subTest(gate=gate), self.assertRaisesRegex(ValueError, "Gate not passed"):
                self.stage("promotion")
            self.review["checks"][gate]["passed"] = True
        self.sign()
        self.assertFalse(self.stage("promotion")["automatic_install_authorized"])

    def test_duplicate_json_key_refused(self):
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            s.json_bytes(b'{"passed":false,"passed":true}')

    def test_stale_or_wrong_tuple_report(self):
        self.review["checks"]["vintf"]["tuple_sha256"] = "0" * 64
        self.sign()
        with self.assertRaisesRegex(ValueError, "tuple mismatch"):
            self.stage()
        self.review["expires_utc"] = "2000-01-01T00:00:00Z"
        self.sign()
        with self.assertRaisesRegex(ValueError, "Expired"):
            self.stage()

    def test_changed_evidence_and_missing_boot_file(self):
        (self.candidate / "evidence").write_text("changed")
        with self.assertRaisesRegex(ValueError, "Evidence changed"):
            self.stage()
        (self.candidate / "kernel").unlink()
        with self.assertRaises(FileNotFoundError):
            self.stage()

    def test_scope_cannot_escalate_to_trial(self):
        with self.assertRaisesRegex(ValueError, "different stage"):
            self.stage("trial")
        self.review["stage"] = "trial"
        self.sign()
        with self.assertRaisesRegex(ValueError, "Research-only"):
            self.stage("trial")

    def test_devices_traversal_symlinks_and_incremental_refused(self):
        with self.assertRaisesRegex(ValueError, "Regular"):
            s.digest(Path("/dev/null"))
        self.profile["artifacts"]["../outside"] = "0" * 64
        self.sign()
        with self.assertRaisesRegex(ValueError, "Flat artifact"):
            self.stage()
        del self.profile["artifacts"]["../outside"]
        self.profile["original"]["kind"] = "incremental-ota"
        self.sign()
        with self.assertRaisesRegex(ValueError, "full recovery"):
            self.stage()
        link = self.root / "link"
        link.symlink_to(self.original)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            s.digest(link)

    def test_interrupted_copy_never_publishes(self):
        before = s.digest(self.original)
        with patch.object(s.shutil, "copyfileobj", side_effect=OSError("injected interrupted write")):
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.stage()
        self.assertFalse(self.out.exists())
        self.assertEqual(s.digest(self.original), before)

    def test_low_disk_refused(self):
        with patch.object(s.shutil, "disk_usage", return_value=s.shutil._ntuple_diskusage(1, 1, 0)):
            with self.assertRaisesRegex(ValueError, "disk space"):
                self.stage()


class QuarantineTests(unittest.TestCase):
    def test_known_contract_and_unknown_definition(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rc = root / "ruby/fs/system_a/system/etc/init/update_engine.rc"
            rc.parent.mkdir(parents=True)
            rc.write_text(q.STOCK_RC)
            out = root / "out"
            (out / "etc/init").mkdir(parents=True)
            result = q.prepare(root / "ruby", out)
            self.assertFalse(result["unattended_safe"])
            with self.assertRaises(FileExistsError):
                q.prepare(root / "ruby", out)
            rc.write_text(q.STOCK_RC + "# drift\n")
            with self.assertRaisesRegex(ValueError, "Unknown"):
                q.prepare(root / "ruby", out)

    def test_apk_component_attributes_not_nested_intent_attributes(self):
        text = """            E: service (line=0)
              A: http://schemas.android.com/apk/res/android:name(0x1)="com.google.android.gms.update.Job"
              A: http://schemas.android.com/apk/res/android:enabled(0x2)=true
                E: intent-filter (line=0)
                    E: action (line=0)
                      A: http://schemas.android.com/apk/res/android:name(0x1)="WRONG"
            E: activity (line=0)
              A: http://schemas.android.com/apk/res/android:name(0x1)="com.example.Unrelated"
"""
        self.assertEqual(i.components(text), [{"kind": "service", "name": "com.google.android.gms.update.Job",
                                               "enabled": "true"}])


if __name__ == "__main__":
    unittest.main()
