#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit checks for build-safety-candidate.py (ANAL-251).

The full image build and its firmware safety check run on the real release candidate
(evidence/2026-10-24-ruby-safety/); these cover the fail-closed choices and the disposable VM report."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("safety_candidate", Path(__file__).with_name("build-safety-candidate.py"))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
c = s.check

GOOGLE = b"on post-fs\n    exec - hsm hsm -- /system/bin/gscutil --direct-gsc perform-os-startup\n"
OURS = b"# OpenBook\non post-fs\n    mkdir /metadata/gscutil 775 hsm hsm\n"
RC = "/system/etc/init/gscutil.rc"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Replacements(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.safety, self.source = d / "safety", d / "source"
        self.safety.mkdir()
        (self.safety / "gscutil.rc").write_bytes(OURS)
        self.policy = dict(neutralised={RC: dict(replacement="gscutil.rc", sha256=sha(OURS), google_sha256=sha(GOOGLE))})
        (self.source / "system/etc/init").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, data):
        (self.source / RC.lstrip("/")).write_bytes(data)

    def test_google_original_is_replaced(self):
        self.put(GOOGLE)
        self.assertEqual(s.replacements_for(self.source, self.policy, self.safety), {RC: OURS})

    def test_already_neutralised_refused(self):
        self.put(OURS)
        with self.assertRaisesRegex(ValueError, "already OpenBook's replacement"):
            s.replacements_for(self.source, self.policy, self.safety)

    def test_changed_google_file_refused(self):
        self.put(GOOGLE + b"    # Google changed this file\n")
        with self.assertRaisesRegex(ValueError, "Google changed it"):
            s.replacements_for(self.source, self.policy, self.safety)

    def test_missing_file_refused(self):
        with self.assertRaisesRegex(ValueError, "moved or removed"):
            s.replacements_for(self.source, self.policy, self.safety)

    def test_replacement_pin_is_enforced(self):
        self.put(GOOGLE)
        (self.safety / "gscutil.rc").write_bytes(OURS + b"\n")
        with self.assertRaisesRegex(ValueError, "differs from its pin"):
            s.replacements_for(self.source, self.policy, self.safety)

    def test_committed_rules_cover_both_files(self):
        policy = c.load_policy()
        self.assertEqual(sorted(policy["neutralised"]), ["/system/etc/init/gscutil-executor.rc", RC])


class VmCheck(unittest.TestCase):
    def test_report_script_parses(self):
        with tempfile.NamedTemporaryFile(suffix=".sh") as f:
            f.write(s.VM_CHECK_SH)
            f.flush()
            subprocess.run(["sh", "-n", f.name], check=True)
        text = s.VM_CHECK_SH.decode()
        for tag in ("FWS_VMCHECK begin", "FWS_BOOT", "FWS_SERVICE", "FWS_PIDOF", "FWS_VMCHECK done"):
            self.assertIn(tag, text)

    def test_init_scripts_verify(self):
        host = Path(os.environ.get("OPENBOOK_AOSP_HOST", Path.home() / "anybook/aosp/src/out/host/linux-x86"))
        tool = host / "bin/host_init_verifier"
        if not tool.exists():
            self.skipTest("host_init_verifier not available")
        with tempfile.TemporaryDirectory() as d:
            # Single-script mode: one file per run.
            for name, data in (("vmcheck.rc", s.VM_CHECK_RC),
                               ("gscutil.rc", (c.SAFETY / "gscutil.rc").read_bytes()),
                               ("gscutil-executor.rc", (c.SAFETY / "gscutil-executor.rc").read_bytes())):
                (Path(d) / name).write_bytes(data)
                out = subprocess.run([str(tool), str(Path(d) / name)], capture_output=True, text=True,
                                     env=dict(os.environ, LD_LIBRARY_PATH=str(host / "lib64")))
                self.assertEqual(out.returncode, 0, f"{name}: {out.stderr}")


if __name__ == "__main__":
    unittest.main()
