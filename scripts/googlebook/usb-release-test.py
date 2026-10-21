#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""USB release transition, installer replacement and recovery failure tests."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


f = load("finalize", "finalize-usb-release.py")
u, p = f.u, f.p
guards = load("guards", "preserve-update-test.py")


class ReleaseTests(unittest.TestCase):
    def test_reviewed_transition_keeps_default_refusal_and_rejects_any_drift(self):
        old = guards.PreserveGuards().manifest()
        for e in old["entries"].values():
            e["androidboot.vbmeta.size"] = "4352"
        new = copy.deepcopy(old)
        new["logical_sha256"]["system"] = "reviewed-input-fix"
        for e in new["entries"].values():
            e["androidboot.vbmeta.size"] = "4032"
        with self.assertRaisesRegex(ValueError, "framework"):
            u.compatible(old, new)
        with patch.object(u, "RB01_BASES", {u.manifest_fingerprint(old)}), patch.object(u, "RB01_INPUT", u.manifest_fingerprint(new)):
            u.compatible(old, new, "RB-20261020-01")
            for section, key in (("logical_sha256", "system"), ("logical_sha256", "vendor"),
                                 ("payload_readback", "boot_a")):
                bad = copy.deepcopy(new); bad[section][key] = "unreviewed"
                with self.subTest(section=section, key=key), self.assertRaisesRegex(ValueError, "Unreviewed"):
                    u.compatible(old, bad, "RB-20261020-01")
            bad = copy.deepcopy(new); bad["entries"]["live"]["androidboot.selinux"] = "permissive"
            with self.assertRaisesRegex(ValueError, "Unreviewed"):
                u.compatible(old, bad, "RB-20261020-01")
            bad = copy.deepcopy(old); bad["kernel_sha256"] = "other"
            with self.assertRaisesRegex(ValueError, "Unreviewed"):
                u.compatible(bad, new, "RB-20261020-01")

    def installer(self, root):
        d = root / "ruby-installer"; d.mkdir()
        for n in p.INSTALLER_FILES - {"build.json"}:
            (d / n).write_text("old " + n)
        build = dict(files={n: u.h.audit.sha(d / n) for n in p.INSTALLER_FILES - {"build.json"}})
        (d / "build.json").write_text(json.dumps(build))
        return d, {"offline_migration_installer": build}, u.h.audit.sha(d / "build.json")

    def test_replacement_requires_exact_installer_and_explicit_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); d, manifest, digest = self.installer(root)
            with self.assertRaisesRegex(ValueError, "explicit"):
                p.replacement_files(root, manifest, None)
            with self.assertRaisesRegex(ValueError, "identity"):
                p.replacement_files(root, manifest, "0" * 64)
            allowed = p.replacement_files(root, manifest, digest)
            self.assertNotIn("loader/loader.conf", allowed)
            self.assertNotIn("openbook/logs/old.txt", allowed)
            self.assertNotIn("ruby/kernel", allowed)
            (d / "initrd.img").write_text("changed")
            with self.assertRaisesRegex(ValueError, "changed"):
                p.replacement_files(root, manifest, digest)

    def test_replacement_rejects_unknown_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); d, manifest, digest = self.installer(root)
            (d / "owner-file").write_text("preserve this")
            with self.assertRaisesRegex(ValueError, "file set"):
                p.replacement_files(root, manifest, digest)

    def test_stage_chain_rejects_wrong_input_or_protection(self):
        stage = dict(reviewed_release="RB-20261020-01", complete=False, requires_installer_rebind=True,
                     image_sha256="stage", backup_sha256="original", candidate_sha256="candidate", protected=[{"range": 1}])
        package = dict(complete=True, backup_sha256="stage", protected=stage["protected"], image_sha256="final")
        self.assertEqual(f.compose(stage, package)["backup_sha256"], "original")
        for key, value in (("backup_sha256", "wrong"), ("protected", []), ("complete", False)):
            bad = dict(package); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                f.compose(stage, bad)
        bad = dict(stage); bad["complete"] = True
        with self.assertRaises(ValueError):
            f.compose(bad, package)

    def test_partial_system_write_can_be_restored_without_touching_other_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup = root / "backup"; device = root / "synthetic-device"
            original = b"P" * 8192
            backup.write_bytes(original); device.write_bytes(original)
            # Simulate loss of power during the first system partition write.
            with device.open("r+b") as out:
                out.seek(4096); out.write(b"NEW" * 100)
            writes = [dict(name=name, offset=offset, length=512)
                      for name, offset in (("EFI", 512), ("vbmeta_a", 3072), ("super", 4096))]
            f.a.write_ranges(backup, device, writes)
            self.assertEqual(device.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
