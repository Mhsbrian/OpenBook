#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Checks for build-dgpu-diag-candidate.py and dgpu-vm-judge.py (ANAL-238): fail-closed input choices, the CIL
derivation, the VM report's init script, and the judge on synthetic serial logs. No images or containers."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


c = module("dgpu_candidate", "build-dgpu-diag-candidate.py")
j = module("dgpu_judge", "dgpu-vm-judge.py")
sha = lambda data: hashlib.sha256(data).hexdigest()

TEMPLATE = (
    "(allow hal_power_stats_default sysfs_suspend_stats_202604 (dir (ioctl read getattr lock open watch watch_reads search)))\n"
    "(allow hal_power_stats_default sysfs_suspend_stats_202604 (file (ioctl read getattr lock map open watch watch_reads)))\n"
    "(allow hal_power_stats_default sysfs_suspend_stats_202604 (lnk_file (ioctl read getattr lock map open watch watch_reads)))\n")
CIL = "(type openbook_pc_setup)\n" + TEMPLATE + "(allow openbook_pc_setup sysfs_202604 (file (read)))\n"


class Cil(unittest.TestCase):
    def test_rule_derived_from_template(self):
        out, added = c.new_cil(CIL.encode())
        self.assertEqual(len(added), 3)
        self.assertTrue(all(l.startswith("(allow openbook_pc_setup sysfs_suspend_stats_202604 (") for l in added))
        self.assertEqual(out.decode(), CIL + "".join(l + "\n" for l in added))
        self.assertEqual([l.replace("openbook_pc_setup", "hal_power_stats_default", 1) for l in added],
                         TEMPLATE.splitlines())

    def test_refuses_missing_template_class(self):
        broken = CIL.replace(TEMPLATE.splitlines()[2] + "\n", "")
        with self.assertRaisesRegex(ValueError, "template rule"):
            c.new_cil(broken.encode())

    def test_refuses_existing_grant(self):
        with self.assertRaisesRegex(ValueError, "already grants"):
            c.new_cil((CIL + "(allow openbook_pc_setup sysfs_suspend_stats_202604 (file (read)))\n").encode())

    def test_refuses_missing_final_newline(self):
        with self.assertRaisesRegex(ValueError, "newline"):
            c.new_cil(CIL.rstrip("\n").encode())


class Inputs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.vendor = self.tmp / "vendor"
        files = {c.SETUP: b"old setup\n", c.RC: b"old rc\n", c.CIL: CIL.encode()}
        for path, data in files.items():
            (self.vendor / path.lstrip("/")).parent.mkdir(parents=True, exist_ok=True)
            (self.vendor / path.lstrip("/")).write_bytes(data)
        self.pins, self.sources = dict(c.BASE_PINS), dict(c.SOURCES)
        c.BASE_PINS.update({k: sha(v) for k, v in files.items()})
        (self.tmp / "setup.sh").write_bytes(b"new setup\n")
        (self.tmp / "init.rc").write_bytes(b"new rc\n")
        c.SOURCES.update({c.SETUP: self.tmp / "setup.sh", c.RC: self.tmp / "init.rc"})

    def tearDown(self):
        c.BASE_PINS.clear(); c.BASE_PINS.update(self.pins)
        c.SOURCES.clear(); c.SOURCES.update(self.sources)

    def test_replacements(self):
        out = c.replacements_for(self.vendor)
        self.assertEqual(set(out), {c.SETUP, c.RC, c.CIL})
        self.assertEqual(out[c.SETUP], b"new setup\n")
        self.assertTrue(out[c.CIL].startswith(CIL.encode()))

    def test_refuses_unreviewed_base(self):
        (self.vendor / c.RC.lstrip("/")).write_bytes(b"someone else's rc\n")
        with self.assertRaisesRegex(ValueError, "not the reviewed original"):
            c.replacements_for(self.vendor)

    def test_refuses_missing_file(self):
        (self.vendor / c.SETUP.lstrip("/")).unlink()
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            c.replacements_for(self.vendor)

    def test_refuses_unchanged_replacement(self):
        (self.tmp / "init.rc").write_bytes(b"old rc\n")
        with self.assertRaisesRegex(ValueError, "equal the base"):
            c.replacements_for(self.vendor)


class Pins(unittest.TestCase):
    def test_sources_are_the_repository_files(self):
        for path, src in c.SOURCES.items():
            self.assertTrue(src.is_file(), src)
            self.assertNotEqual(sha(src.read_bytes()), c.BASE_PINS[path])

    def test_uniform_mtime(self):
        rows = ["I  16877 0 2000 12 0 1792368000 0", "I 2f62696e 16873 0 2000 3 0 1792368000 0",
                "X 2f62696e 7365 7531"]
        self.assertEqual(c.uniform_mtime(rows), 1792368000)
        with self.assertRaisesRegex(ValueError, "different mtimes"):
            c.uniform_mtime(rows + ["I 2f78 33188 0 0 1 4 1230768000 0"])


class InitScripts(unittest.TestCase):
    HIV = Path(os.environ.get("AOSP_HOST", Path.home() / "anybook/aosp/src/out/host/linux-x86")) / "bin/host_init_verifier"

    def verify(self, data):
        if not self.HIV.is_file():
            self.skipTest("no host_init_verifier")
        with tempfile.TemporaryDirectory() as tmp:
            rc = Path(tmp) / "test.rc"
            rc.write_bytes(data)
            r = subprocess.run([str(self.HIV), str(rc)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_vm_check_rc(self):
        self.verify(c.VM_CHECK_RC)

    def test_vendor_rc(self):
        self.verify(c.SOURCES[c.RC].read_bytes())


def report(reason, state="absent", stats=True):
    lines = [f"dgpu-report ({reason})"]
    if stats:
        lines.append("dgpu-report: suspend_stats success=0 fail=0 total_hw_sleep_us=0")
    return lines + [f"dgpu-report: state={state}"]


def serial(boot=None, extra_denial=False, ctl_exit=0):
    boot = report("boot") if boot is None else boot
    rows = ["[   11.4][ T44] audit: type=1400 audit(1792791906.135:7): avc:  denied  { write } for  pid=218 "
            'comm="openbook-pc-set" path="/dev/kmsg_debug" dev="tmpfs" ino=6 scontext=u:r:openbook_pc_setup:s0 '
            "tcontext=u:object_r:tmpfs:s0 tclass=chr_file permissive=0"]
    if extra_denial:
        rows.append("[   40.1][ T44] audit: type=1400 audit(1792791930.1:9): avc:  denied  { read } for  pid=900 "
                    'comm="cat" name="success" dev="sysfs" ino=7 scontext=u:r:openbook_pc_setup:s0 '
                    "tcontext=u:object_r:sysfs_suspend_stats:s0 tclass=file permissive=0")
    for svc, code in (("dgpu-report", 0), ("dgpu-report", 0), ("dgpu-ctl", ctl_exit), ("dgpu-ctl", 0)):
        rows.append(f"[   50.0][ T1] init: Service 'vendor.openbook.{svc}' (pid 1) exited with status {code} oneshot")
    rows += ["DGR_VMCHECK begin", "DGR_BOOT 1"] + [f"DGR_LOG boot {l}" for l in boot]
    rows += [f"DGR_LOG report {l}" for l in boot + report("vm-1")]
    rows += [f"DGR_LOG ctl-on {l}" for l in ["dgpu-ctl: no NVIDIA function enumerated; nothing to do"]
             + report("dgpu-ctl on")]
    rows += [f"DGR_LOG ctl-auto {l}" for l in ["no NVIDIA GPU enumerated; nothing to do"] + report("dgpu-ctl auto")]
    rows += ["DGR_VMCHECK done"]
    return "\n".join(rows) + "\n"


BASELINE = serial().split("DGR_VMCHECK begin")[0]
BOOT = {"passed": True, "runtime_findings": {"system_server_fatal_signals": 0, "zygote_exit_events": 0}}


class Judge(unittest.TestCase):
    def test_pass(self):
        r = j.judge(serial(), BOOT, BASELINE)
        self.assertTrue(r["passed"], r["checks"])

    def test_stats_unreadable_fails(self):
        r = j.judge(serial(boot=report("boot", stats=False)), BOOT, BASELINE)
        self.assertFalse(r["checks"]["suspend_stats_readable"])
        self.assertFalse(r["passed"])

    def test_wrong_state_fails(self):
        r = j.judge(serial(boot=report("boot", state="d0-no-driver")), BOOT, BASELINE)
        self.assertFalse(r["checks"]["boot_report_in_logcat"])

    def test_new_denial_fails(self):
        r = j.judge(serial(extra_denial=True), BOOT, BASELINE)
        self.assertFalse(r["checks"]["no_new_openbook_pc_setup_denials"])

    def test_nonzero_exit_fails(self):
        r = j.judge(serial(ctl_exit=2), BOOT, BASELINE)
        self.assertFalse(r["checks"]["services_exit_0"])

    def test_missing_report_fails(self):
        r = j.judge(serial().replace("DGR_VMCHECK done\n", ""), BOOT, BASELINE)
        self.assertFalse(r["checks"]["report_complete"])


if __name__ == "__main__":
    unittest.main()
