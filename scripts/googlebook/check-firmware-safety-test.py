#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit checks for check-firmware-safety.py and the committed rule file (ANAL-251).

Synthetic trees and a hand-encoded payload manifest; with AOSP's delta_generator present (OPENBOOK_AOSP_HOST
or ~/anybook/aosp/src/out/host/linux-x86), real payloads with and without a postinstall step too. The real
release's images are checked in evidence/2026-10-24-ruby-safety/."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("safety", Path(__file__).with_name("check-firmware-safety.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

GOOGLE_GSC = b"on post-fs\n    exec - hsm hsm -- /system/bin/gscutil --direct-gsc perform-os-startup --fw-zip-mp x\n"
OURS_GSC = b"# OpenBook\non post-fs\n    mkdir /metadata/gscutil 775 hsm hsm\n"
GSCD = b"service gscd /system/bin/gscd\n    class early_hal\n    user hsm\n"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def policy(safety):
    (safety / "gscutil.rc").write_bytes(OURS_GSC)
    p = json.loads(c.POLICY.read_text())
    p["neutralised"] = {"/system/etc/init/gscutil.rc": dict(replacement="gscutil.rc", sha256=sha(OURS_GSC),
                                                           google_sha256=sha(GOOGLE_GSC), why="test")}
    p["reviewed_rc"] = {"/system/etc/init/gscd.rc": dict(sha256=sha(GSCD), verdict="allowed", why="test")}
    p["reviewed_binaries"] = {"/system/bin/gscd": "test"}
    (safety / "firmware-safety.json").write_text(json.dumps(p))
    return c.load_policy(safety / "firmware-safety.json")


def tree(root, files):
    for path, data in files.items():
        local = root / path.lstrip("/")
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)


def encode_varint(n):
    out = bytearray()
    while True:
        byte, n = n & 0x7F, n >> 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def field(number, value):
    if isinstance(value, bool) or isinstance(value, int):
        return encode_varint(number << 3) + encode_varint(int(value))
    return encode_varint(number << 3 | 2) + encode_varint(len(value)) + value


def payload(parts):
    manifest = field(3, 4096)
    for name, run, path in parts:
        body = field(1, name.encode()) + (field(2, run) if run is not None else b"") + (field(3, path.encode()) if path else b"")
        manifest += field(13, body)
    return b"CrAU" + struct.pack(">QQI", 2, len(manifest), 0) + manifest


class Rules(unittest.TestCase):
    def test_committed_rules_load_and_pins_hold(self):
        p = c.load_policy()
        self.assertEqual(set(p["neutralised"]), {"/system/etc/init/gscutil.rc", "/system/etc/init/gscutil-executor.rc"})
        for runtime in p["neutralised"]:
            self.assertEqual(sha(c.replacement(p, runtime)), p["neutralised"][runtime]["sha256"])
        self.assertEqual(p["payload"]["postinstall"], "forbidden")

    def test_patterns_are_re2_compatible(self):
        # Go's regexp (RE2) has no lookaround or backreferences; the on-laptop adapter uses the same patterns.
        for key in ("rc_pattern", "binary_pattern"):
            pattern = json.loads(c.POLICY.read_text())[key]
            self.assertNotRegex(pattern, r"\(\?[=!<]|\\[1-9]")

    def test_replacements_contain_no_trigger(self):
        p = c.load_policy()
        for runtime in p["neutralised"]:
            code = [l.split() for l in c.replacement(p, runtime).decode().splitlines()
                    if l.strip() and not l.lstrip().startswith("#")]
            # At most "on post-fs" + "mkdir": no service, exec or start.
            self.assertTrue(all(words[0] in ("on", "mkdir") for words in code), code)

    def test_rc_hits_ignore_comments(self):
        r = re.compile(c.load_policy()["rc_pattern"])
        self.assertEqual(c.rc_hits("# /dev/tpm0 in a comment\n   # fwupd\non boot\n    write /x 1\n", r), [])
        self.assertEqual(c.rc_hits("service x /system/bin/fwupd\n    user hsm\n", r), ["fwupd", "hsm"])


class Tree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "safety").mkdir()
        self.policy = policy(self.dir / "safety")
        self.system = self.dir / "system"
        tree(self.system, {"/system/etc/init/gscutil.rc": OURS_GSC, "/system/etc/init/gscd.rc": GSCD,
                           "/system/etc/init/hw/init.rc": b"on boot\n    mount pstore pstore /sys/fs/pstore\n",
                           "/system/bin/gscd": b"\x7fELF", "/system/bin/sh": b"\x7fELF"})

    def tearDown(self):
        self.tmp.cleanup()

    def findings(self, **roots):
        found, inventory = c.check_tree(self.policy, {"system": self.system, **roots})
        return [(f["kind"], f["path"]) for f in found], inventory

    def test_neutralised_tree_passes(self):
        found, inventory = self.findings()
        self.assertEqual(found, [])
        self.assertEqual(inventory["neutralised"], {"/system/etc/init/gscutil.rc": "neutralised"})
        self.assertEqual(inventory["reviewed_rc"], {"/system/etc/init/gscd.rc": "allowed"})

    def test_google_original_fails(self):
        tree(self.system, {"/system/etc/init/gscutil.rc": GOOGLE_GSC})
        self.assertEqual(self.findings()[0], [("not-neutralised", "/system/etc/init/gscutil.rc")])

    def test_changed_or_missing_neutralised_path_fails(self):
        tree(self.system, {"/system/etc/init/gscutil.rc": GOOGLE_GSC + b"# new\n"})
        self.assertEqual(self.findings()[0], [("not-neutralised", "/system/etc/init/gscutil.rc")])
        (self.system / "system/etc/init/gscutil.rc").unlink()
        self.assertEqual(self.findings()[0], [("not-neutralised", "/system/etc/init/gscutil.rc")])

    def test_new_trigger_in_any_partition_fails(self):
        vendor = self.dir / "vendor"
        tree(vendor, {"/etc/init/fw.rc": b"on boot\n    exec -- /vendor/bin/futility update --mode=autoupdate\n"})
        tree(self.system, {"/system/etc/init/new.rc": b"service n /system/bin/n\n    user hsm\n"})
        found, _ = self.findings(vendor=vendor)
        self.assertEqual(sorted(found), [("unreviewed-rc", "/system/etc/init/new.rc"), ("unreviewed-rc", "/vendor/etc/init/fw.rc")])
        # A tool the init scripts do not name is still caught by its name.
        tree(vendor, {"/bin/hw/flash_ec": b"\x7fELF"})
        found, _ = self.findings(vendor=vendor)
        self.assertIn(("unreviewed-binary", "/vendor/bin/hw/flash_ec"), found)

    def test_changed_reviewed_rc_fails(self):
        tree(self.system, {"/system/etc/init/gscd.rc": GSCD + b"    group hsm misc\n"})
        self.assertEqual(self.findings()[0], [("changed-rc", "/system/etc/init/gscd.rc")])

    def test_forbidden_name_anywhere_fails(self):
        tree(self.system, {"/system/xbin/futility": b"\x7fELF", "/system/etc/fwupd/fwupd": b"x"})
        found, _ = self.findings()
        self.assertIn(("forbidden", "/system/xbin/futility"), found)
        self.assertIn(("forbidden", "/system/etc/fwupd/fwupd"), found)
        self.assertIn(("unreviewed-binary", "/system/xbin/futility"), found)

    def test_apex_rc_is_checked(self):
        found, _ = c.check_tree(self.policy, {"system": self.system},
                                [("/apex/com.x/etc/x.rc", b"service x /apex/com.x/bin/x\n    user hsm\n")])
        self.assertEqual([(f["kind"], f["path"]) for f in found], [("unreviewed-rc", "/apex/com.x/etc/x.rc")])

    def test_partition_mounts(self):
        vendor = self.dir / "v"
        tree(vendor, {"/etc/init/ok.rc": b"on boot\n    write /proc/x 1\n"})
        runtime = sorted(r for r, _ in c.walk({"vendor": vendor, "system": self.system}))
        self.assertIn("/vendor/etc/init/ok.rc", runtime)
        self.assertIn("/system/etc/init/gscd.rc", runtime)


class Payload(unittest.TestCase):
    def test_postinstall_found_or_absent(self):
        p = c.load_policy()
        with tempfile.TemporaryDirectory() as d:
            clean, dirty = Path(d) / "clean.bin", Path(d) / "dirty.bin"
            clean.write_bytes(payload([("system", None, ""), ("vendor", False, "")]))
            dirty.write_bytes(payload([("system", True, "system/bin/updater-wrapper-system"), ("vendor", None, "")]))
            found, inventory = c.check_payload(p, clean)
            self.assertEqual((found, inventory["partitions"]), ([], ["system", "vendor"]))
            found, _ = c.check_payload(p, dirty)
            self.assertEqual([(f["kind"], f["path"]) for f in found], [("postinstall", "system")])

    def test_rejects_non_payload(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "x.bin"
            bad.write_bytes(b"PK\x03\x04 not a payload")
            with self.assertRaises(ValueError):
                c.check_payload(c.load_policy(), bad)

    def test_real_payloads_from_delta_generator(self):
        host = Path(os.environ.get("OPENBOOK_AOSP_HOST", Path.home() / "anybook/aosp/src/out/host/linux-x86"))
        dg = host / "bin/delta_generator"
        if not dg.exists():
            self.skipTest("delta_generator not available")
        env = dict(os.environ, LD_LIBRARY_PATH=str(host / "lib64"))
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "system.img").write_bytes(bytes(4096 * 16))
            (d / "pi.txt").write_text("RUN_POSTINSTALL_system=true\nPOSTINSTALL_PATH_system=system/bin/updater-wrapper-system\n"
                                      "FILESYSTEM_TYPE_system=erofs\nPOSTINSTALL_OPTIONAL_system=false\n")
            base = [str(dg), f"--new_partitions={d / 'system.img'}", "--partition_names=system", "--major_version=2"]
            subprocess.run(base + [f"--out_file={d / 'plain.bin'}"], check=True, env=env, capture_output=True)
            subprocess.run(base + [f"--new_postinstall_config_file={d / 'pi.txt'}", f"--out_file={d / 'pi.bin'}"],
                           check=True, env=env, capture_output=True)
            self.assertEqual(c.check_payload(c.load_policy(), d / "plain.bin")[0], [])
            self.assertEqual([f["detail"] for f in c.check_payload(c.load_policy(), d / "pi.bin")[0]],
                             ["runs postinstall system/bin/updater-wrapper-system"])


if __name__ == "__main__":
    unittest.main()
