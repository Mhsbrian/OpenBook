#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Tests for check-hygiene.py on throwaway Git repositories."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("hygiene", Path(__file__).resolve().parents[2] / "scripts/ci/check-hygiene.py")
hygiene = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hygiene)

# Built at run time so this file doesn't trip the check it tests.
HOME_ADDR = ".".join(["192", "168", "1", "20"])
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]


class Hygiene(unittest.TestCase):
    def repo(self, files, root=None):
        if root is None:
            root = Path(self.enterContext(tempfile.TemporaryDirectory()))
            subprocess.run(["git", "init", "-q", str(root)], check=True)
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        subprocess.run(["git", "-C", str(root), "add", "-f", "."], check=True)
        return root

    def reasons(self, files):
        return {name: reason for name, reason in hygiene.findings(self.repo(files))}

    def test_code_and_docs_pass(self):
        self.assertEqual(self.reasons({
            "scripts/x.py": b"print('hi')\n",
            "docs/x.md": b"Example: adb connect 192.0.2.10:5555\n",
            "scripts/qemu-test/run-ap.sh": b"ip addr add 192.168.77.1/24 dev wlan1\n",
            "docs/hw.md": b"TPM firmware 10.6.0.4\n",
            "device/fonts/Big.ttf": b"\0" * (hygiene.MAX_BYTES + 1),
            "assets/bootanimation/bootanimation.zip": b"\0" * (hygiene.MAX_BYTES + 1),
            "assets/readme/hero.jpg": b"\xff\xd8",
            "scripts/t.py": b'x = b"-----BEGIN PRIVATE KEY-----another key"\n',
        }), {})

    def test_evidence_logs_images_keys_and_home_addresses_are_refused(self):
        key = b"-----BEGIN RSA PRIVATE KEY-----\n" + b"A" * 64 + b"\n-----END RSA PRIVATE KEY-----\n"
        found = self.reasons({
            "evidence/2026-10-24-x/SUMMARY.md": b"results\n",
            "build.log": b"log\n",
            "out.img": b"\0",
            "release.pk8": b"\0",
            "docs/shot.png": b"\x89PNG",
            "scripts/huge.bin.txt": b"x" * (hygiene.MAX_BYTES + 1),
            "config/secret.pem": key,
            "scripts/g14.sh": f"D=${{ADDR:-{HOME_ADDR}}}\n".encode(),
        })
        self.assertEqual(set(found), {"evidence/2026-10-24-x/SUMMARY.md", "build.log", "out.img",
                                      "release.pk8", "docs/shot.png", "scripts/huge.bin.txt",
                                      "config/secret.pem", "scripts/g14.sh"})
        self.assertIn("private key", found["config/secret.pem"])
        self.assertIn(HOME_ADDR, found["scripts/g14.sh"])

    def test_changed_since_checks_only_new_work(self):
        root = self.repo({"evidence/old/log.txt": b"old\n", "README.md": b"hi\n"})
        subprocess.run([*GIT, "-C", str(root), "commit", "-qm", "base"], check=True)
        base = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
        self.repo({"scripts/ok.sh": b"echo ok\n", "evidence/new/log.txt": b"new\n"}, root)
        subprocess.run([*GIT, "-C", str(root), "commit", "-qm", "change"], check=True)
        found = {name for name, _ in hygiene.findings(root, base)}
        self.assertEqual(found, {"evidence/new/log.txt"})
        self.assertIn("evidence/old/log.txt", {name for name, _ in hygiene.findings(root)})


if __name__ == "__main__":
    unittest.main()
