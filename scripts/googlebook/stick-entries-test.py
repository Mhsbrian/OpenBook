#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Boot-entry additions on synthetic FAT/GPT regular-file images."""
import importlib.util
import json
from pathlib import Path
import unittest


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


s = module("stick-entries")
fixture = module("migration-test")
LOGS = ("title Googlebook - save detailed logs to USB (10 minutes)\nlinux /ruby/kernel\n"
        "initrd /ruby/initrd-logs.img\noptions firmware_class.path=/vendor/firmware bootconfig loglevel=7\n")


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.MigrationTests()
        self.f.setUp()
        self.root = self.f.root
        conf = self.root / "ruby-logs.conf"
        conf.write_text(LOGS)
        s.m.run("mcopy", "-i", f"{self.f.src}@@{s.m.extent(self.f.gpt['rows'][0])[0]}",
                conf, "::/loader/entries/ruby-logs.conf")
        self.manifest = dict(schema="openbook-ruby-live-research/1", module_variant="bm",
                             installable=False, image_bytes=self.f.src.stat().st_size,
                             gpt=self.f.pin["gpt"], payload_readback=self.f.pin["payload_readback"])
        self.manifest_path = self.root / "base.json"
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.before = s.u.h.audit.sha(self.f.src)

    def tearDown(self):
        self.f.tearDown()

    def spec(self, **entry):
        value = dict(name="ruby-sleep-diag.conf", base="ruby-logs.conf",
                     title="Googlebook - sleep diagnostics, save logs to USB (10 minutes)",
                     add_options=["pm_debug_messages", "acpi.debug_layer=0x4", "acpi.debug_level=0x4"])
        value.update(entry)
        path = self.root / f"spec-{len(list(self.root.glob('spec-*')))}.json"
        path.write_text(json.dumps(dict(schema="openbook-ruby-stick-entries/1", entries=[value])))
        return path

    def add(self, spec, out="out"):
        return s.add(self.f.src, self.before, self.manifest_path, spec, self.root / out)

    def test_adds_only_the_new_entry_and_keeps_every_other_byte(self):
        plan = self.add(self.spec())
        out = self.root / "out"
        text = (out / "efi-after/loader/entries/ruby-sleep-diag.conf").read_text()
        self.assertEqual(text, "title Googlebook - sleep diagnostics, save logs to USB (10 minutes)\n"
                         "linux /ruby/kernel\ninitrd /ruby/initrd-logs.img\n"
                         "options firmware_class.path=/vendor/firmware bootconfig loglevel=7 "
                         "pm_debug_messages acpi.debug_layer=0x4 acpi.debug_level=0x4\n")
        self.assertEqual((out / "efi-after/loader/entries/ruby-logs.conf").read_text(), LOGS)
        self.assertEqual((out / "efi-after/openbook/logs/old.txt").read_text(), "keep old logs")
        for row in self.f.gpt["rows"][1:]:
            self.assertEqual(s.u.digest_range(self.f.src, *s.m.extent(row)),
                             s.u.digest_range(out / "ruby-live.img", *s.m.extent(row)))
        self.assertEqual(s.u.h.audit.sha(self.f.src), self.before)
        self.assertEqual(plan["added_entries"], ["loader/entries/ruby-sleep-diag.conf"])
        module("apply-preserved-update").validate_plan(out, self.f.src)

    def test_refuses_parameters_outside_the_allowlist(self):
        for bad in (["androidboot.selinux=permissive"], ["init=/bin/sh"], ["pm_debug_messages", "rdinit=/x"],
                    ["button.lid_init_state=disabled"], ["acpi.debug_layer=0x4;reboot"]):
            with self.assertRaisesRegex(ValueError, "allowlist"):
                self.add(self.spec(add_options=bad), out=f"bad-{len(bad)}-{bad[0][:4]}")

    def test_refuses_existing_name_missing_base_and_duplicate_parameter(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.add(self.spec(name="ruby-logs.conf"), out="exists")
        with self.assertRaisesRegex(ValueError, "Base entry missing"):
            self.add(self.spec(base="ruby-missing.conf"), out="missing")
        with self.assertRaisesRegex(ValueError, "Duplicate kernel parameter"):
            self.add(self.spec(add_options=["button.lid_init_state=ignore", "button.lid_init_state=open"]), out="dup")

    def test_refuses_unsafe_names_titles_and_changed_system(self):
        with self.assertRaisesRegex(ValueError, "entry name"):
            self.add(self.spec(name="../loader.conf"), out="name")
        with self.assertRaisesRegex(ValueError, "title"):
            self.add(self.spec(title="x\ninitrd /evil"), out="title")
        self.manifest["payload_readback"] = dict(self.manifest["payload_readback"], super="0" * 64)
        self.manifest_path.write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, "system differs"):
            self.add(self.spec(), out="system")


if __name__ == "__main__":
    unittest.main()
