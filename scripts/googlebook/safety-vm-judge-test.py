#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit checks for safety-vm-judge.py (ANAL-251) on synthetic serial logs shaped like Ruby's."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("judge", Path(__file__).with_name("safety-vm-judge.py"))
j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(j)

COMMON = """[ 15.3][ T1] init: processing action (post-fs) from (/system/etc/init/gscutil.rc:7)
[ 15.4][ T1] init: ... started service 'android.system.desktop.security.gscd' has pid 312
[ 15.7][ T245] servicemanager: Caller(pid=322,uid=9999,sid=u:r:hal_keymint_default:s0) Found android.hardware.security.keymint.IKeyMintDevice/default in device VINTF manifest.
[ 23.1][ T1] init: Service 'exec 9 (/system/bin/check_tpm_clear)' (pid 430) exited with status 2 oneshot service took 0.07 seconds in background
[ 28.0][ T1] init: Service 'android.system.desktop.security.udsattestation' (pid 554) exited with status 1 oneshot service took 0.4 seconds in background
10-24 01:59:26.847  4657  4657 E AndroidRuntime: Process: com.google.android.desktop.repairmode, PID: 4657
"""
GSCUTIL = """[ 16.4][ T1] init: starting service 'exec 2 (/system/bin/gscutil --direct-gsc perform-os-startup --fw-zip-mp x)'...
[ 16.6][ T259] type=1400 audit(1:30): avc:  denied  { write } for  comm="gscutil" path=x dev="tmpfs" ino=2048 scontext=u:r:gscutil:s0
"""
REPORT = """FWS_VMCHECK begin
FWS_BOOT 1
FWS_PROP [init.svc.android.system.desktop.security.gscd]: [running]
FWS_PROP [init.svc.gatekeeperd]: [running]
FWS_PROP [init.svc.keystore2]: [running]
FWS_PROP [init.svc.update_engine]: [running]
FWS_SERVICE com.google.android.system.desktop.IGscutilExecutor/default not found
FWS_SERVICE android.system.desktop.security.gsc.IGsc/default found
FWS_SERVICE android.hardware.weaver.IWeaver/default found
FWS_SERVICE android.hardware.security.keymint.IKeyMintDevice/default not found
FWS_VMCHECK done
"""
BOOT = {"passed": True, "runtime_findings": {"system_server_fatal_signals": [], "zygote_exit_events": 0}}


class Judge(unittest.TestCase):
    def test_neutralised_boot_passes(self):
        r = j.judge(COMMON + REPORT, BOOT, COMMON + GSCUTIL)
        self.assertTrue(r["passed"], {k: v for k, v in r["checks"].items() if not v})

    def test_gscutil_running_fails(self):
        r = j.judge(COMMON + GSCUTIL + REPORT, BOOT, COMMON + GSCUTIL)
        self.assertFalse(r["checks"]["gscutil_not_started_at_boot"])
        self.assertFalse(r["checks"]["no_gscutil_denials"])
        self.assertFalse(r["passed"])

    def test_changed_tpm_tool_behaviour_fails(self):
        changed = COMMON.replace("exited with status 2", "exited with status 0")
        self.assertFalse(j.judge(changed + REPORT, BOOT, COMMON + GSCUTIL)["checks"]["check_tpm_clear_as_baseline"])

    def test_new_crashing_app_fails(self):
        crash = "10-24 02:00:00.000  6000  6000 E AndroidRuntime: Process: com.android.settings, PID: 6000\n"
        self.assertFalse(j.judge(COMMON + crash + REPORT, BOOT, COMMON + GSCUTIL)["checks"]["no_new_app_crash"])

    def test_baseline_must_show_the_old_behaviour(self):
        # A baseline without gscutil cannot show that anything changed.
        self.assertFalse(j.judge(COMMON + REPORT, BOOT, COMMON)["checks"]["baseline_started_gscutil_at_boot"])

    def test_incomplete_report_fails(self):
        self.assertFalse(j.judge(COMMON + REPORT.replace("FWS_VMCHECK done\n", ""), BOOT, COMMON + GSCUTIL)["passed"])


if __name__ == "__main__":
    unittest.main()
