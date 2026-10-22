#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise installer replacement on synthetic FAT/GPT regular-file images."""
import importlib.util
import json
from pathlib import Path
import unittest


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


p = module("migration-package")
fixture = module("migration-test")


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.MigrationTests()
        self.f.setUp()
        self.root = self.f.root
        # Remove the migration fixture's intentionally incomplete installer entry.
        p.m.run("mdel", "-i", f"{self.f.src}@@{p.m.extent(self.f.gpt['rows'][0])[0]}",
                "::/loader/entries/ruby-install.conf")
        self.manifest = dict(schema="openbook-ruby-live-research/1", module_variant="bm",
                             installable=False, image_bytes=self.f.src.stat().st_size,
                             gpt=self.f.pin["gpt"], payload_readback=self.f.pin["payload_readback"])
        self.manifest_path = self.root / "base.json"
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.before = p.u.h.audit.sha(self.f.src)

    def tearDown(self):
        self.f.tearDown()

    def installer(self, version, laptop_update=None):
        root = self.root / version
        root.mkdir()
        (root / "source.json").write_text(json.dumps(self.f.pin))
        for name in ("kernel", "initrd.img", "package-versions.txt"):
            (root / name).write_text(version + "-" + name)
        names = ["source.json", "kernel", "initrd.img", "package-versions.txt"]
        if laptop_update is not None:
            (root / "laptop-update.json").write_text(json.dumps(laptop_update))
            names.append("laptop-update.json")
        build = {"schema": "openbook-ruby-offline-installer/1",
                 "source_pin_sha256": p.u.h.audit.sha(root / "source.json"),
                 "files": {name: p.u.h.audit.sha(root / name) for name in names}}
        (root / "build.json").write_text(json.dumps(build))
        return root

    def laptop_update(self):
        portable = {k: {n: v for n, v in e.items() if n != "androidboot.boot_part_uuid"}
                    for k, e in self.f.pin["entries"].items()}
        return dict(schema="openbook-ruby-laptop-update/1",
                    previous=dict(build="previous", payload_readback=dict(self.f.pin["payload_readback"],
                                  super="0" * 64), entries=portable, kernel_sha256=self.f.pin["kernel_sha256"]),
                    new=dict(build=self.f.pin["build"], payload_readback=self.f.pin["payload_readback"],
                             entries=portable), changed_logical=["system"], data_compatible_rollback=True)

    def test_laptop_update_entries_are_added_reviewed_and_retained(self):
        old = self.installer("old", self.laptop_update())
        added, replaced = self.root / "added", self.root / "replaced"
        p.add(self.f.src, self.before, self.manifest_path, old, added)
        entries = p.update_entries()
        self.assertEqual(len(entries), 4)
        for name, text in entries.items():
            self.assertEqual((added / "efi-after" / name).read_text(), text)
        self.assertIn("openbook.install=update console=tty0", entries["loader/entries/ruby-update.conf"])
        self.assertIn("openbook.install=restore console=ttyS0", entries["loader/entries/ruby-restore-serial.conf"])
        plan = json.loads((added / "update.json").read_text())
        self.assertEqual(plan["laptop_update_entries"], sorted(entries))
        for row in self.f.gpt["rows"][1:]:
            self.assertEqual(p.u.digest_range(self.f.src, *p.m.extent(row)),
                             p.u.digest_range(added / "ruby-live.img", *p.m.extent(row)))
        module("apply-preserved-update").validate_plan(added, self.f.src)
        expected = p.u.h.audit.sha(old / "build.json")
        p.add(added / "ruby-live.img", p.u.h.audit.sha(added / "ruby-live.img"), added / "manifest.json",
              self.installer("new", self.laptop_update()), replaced, expected)
        with self.assertRaisesRegex(ValueError, "requires a laptop update record"):
            p.add(added / "ruby-live.img", p.u.h.audit.sha(added / "ruby-live.img"), added / "manifest.json",
                  self.installer("plain"), self.root / "downgrade", expected)
        drifted = self.root / "drifted"
        p.m.run("mcopy", "-s", "-i", added / "esp.img", "::*", drifted.mkdir() or drifted)
        (drifted / "loader/entries/ruby-update.conf").write_text("title tampered\n")
        with self.assertRaisesRegex(ValueError, "menu changed"):
            p.replacement_contract(drifted, expected)

    def test_laptop_update_record_must_match_installer_pin(self):
        record = self.laptop_update()
        record["new"]["build"] = "another system"
        with self.assertRaisesRegex(ValueError, "does not match this USB"):
            p.add(self.f.src, self.before, self.manifest_path, self.installer("mismatched", record),
                  self.root / "refused")
        self.assertFalse((self.root / "refused").exists())

    def test_add_replace_preserves_android_and_unrelated_efi(self):
        old, new = self.installer("old"), self.installer("new")
        added, replaced = self.root / "added", self.root / "replaced"
        p.add(self.f.src, self.before, self.manifest_path, old, added)
        p.add(added / "ruby-live.img", p.u.h.audit.sha(added / "ruby-live.img"),
              added / "manifest.json", new, replaced, p.u.h.audit.sha(old / "build.json"))
        self.assertEqual(p.u.h.audit.sha(self.f.src), self.before)
        for row in self.f.gpt["rows"][1:]:
            self.assertEqual(p.u.digest_range(self.f.src, *p.m.extent(row)),
                             p.u.digest_range(replaced / "ruby-live.img", *p.m.extent(row)))
        self.assertEqual((replaced / "efi-after/openbook/logs/old.txt").read_text(), "keep old logs")
        self.assertEqual((replaced / "efi-after/ruby-installer/initrd.img").read_bytes(),
                         (new / "initrd.img").read_bytes())
        plan = json.loads((replaced / "update.json").read_text())
        self.assertEqual(plan["replaced_installer_sha256"], p.u.h.audit.sha(old / "build.json"))
        self.assertFalse(plan["physical_device_written"])
        # The existing apply validator independently accepts the output contract.
        applier = module("apply-preserved-update")
        applier.validate_plan(replaced, added / "ruby-live.img")

    def test_existing_installer_requires_exact_review_and_complete_manifest(self):
        old, new = self.installer("old"), self.installer("new")
        added = self.root / "added"
        p.add(self.f.src, self.before, self.manifest_path, old, added)
        for expected, error in ((None, "already present"), ("0" * 64, "pin mismatch")):
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, error):
                p.replacement_contract(added / "efi-after", expected)
        (added / "efi-after/ruby-installer/initrd.img").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "file changed"):
            p.replacement_contract(added / "efi-after", p.u.h.audit.sha(old / "build.json"))
        build = json.loads((new / "build.json").read_text())
        del build["files"]["kernel"]
        (new / "build.json").write_text(json.dumps(build))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            p.add(self.f.src, self.before, self.manifest_path, new, self.root / "bad")

    def test_unrecognized_installer_file_and_menu_rejected(self):
        old = self.installer("old")
        added = self.root / "added"
        p.add(self.f.src, self.before, self.manifest_path, old, added)
        tree = added / "efi-after"
        extra = tree / "ruby-installer/unreviewed"
        extra.write_text("unknown")
        with self.assertRaisesRegex(ValueError, "unfamiliar"):
            p.replacement_contract(tree, p.u.h.audit.sha(old / "build.json"))
        extra.unlink()
        (tree / p.INSTALLER_ENTRIES[0]).write_text("linux /unreviewed")
        with self.assertRaisesRegex(ValueError, "menu changed"):
            p.replacement_contract(tree, p.u.h.audit.sha(old / "build.json"))

    def test_legacy_upgrade_and_fresh_menu_drift(self):
        old = self.installer("old")
        added = self.root / "added"
        p.add(self.f.src, self.before, self.manifest_path, old, added)
        tree = added / "efi-after"
        expected = p.u.h.audit.sha(old / "build.json")
        original = (tree / p.FRESH_ENTRIES[0]).read_text()
        (tree / p.FRESH_ENTRIES[0]).write_text("unreviewed erase")
        with self.assertRaisesRegex(ValueError, "menu changed"):
            p.replacement_contract(tree, expected)
        (tree / p.FRESH_ENTRIES[0]).unlink()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            p.replacement_contract(tree, expected)
        (tree / p.FRESH_ENTRIES[1]).unlink()
        managed = p.replacement_contract(tree, expected)
        self.assertEqual(managed, {f"ruby-installer/{n}" for n in p.INSTALLER_FILES} | set(p.LEGACY_ENTRIES))
        self.assertEqual(original, p.installer_entry("", fresh=True))

    def test_disposable_guard_cannot_get_installer(self):
        self.manifest["experimental_ota_guard"] = {"deployment_eligible": False}
        self.manifest_path.write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, "Disposable OTA experiment"):
            p.add(self.f.src, self.before, self.manifest_path, self.installer("new"), self.root / "bad")
        self.assertFalse((self.root / "bad").exists())
        base = self.root / "experiment"; base.mkdir()
        (base / "ruby-live.img").write_bytes(b"synthetic")
        (base / "manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, "Disposable OTA experiment"):
            p.make_pin(base, self.root / "bad-pin", "test", "synthetic")
        self.assertFalse((self.root / "bad-pin").exists())

    def test_any_experimental_marker_blocks_installer_packaging(self):
        self.manifest["experimental_ota_trust_test"] = {"deployment_eligible": False}
        self.manifest_path.write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, "Disposable OTA experiment"):
            p.add(self.f.src, self.before, self.manifest_path, self.installer("new"), self.root / "bad")
        self.assertFalse((self.root / "bad").exists())


if __name__ == "__main__":
    unittest.main()
