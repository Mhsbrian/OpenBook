#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gpu-diag.sh's pending clean-up (PR #156 review), through the real dispatcher, g14-lock.sh and g14-adb.sh with a
fake adb that records every call and simulates the device: the helper, a sampler's work dir, a worker still alive,
and whether `device.sh reap` manages to stop it. No device or network is contacted.

While a <lock>.pending-cleanup record exists:
  - idle, snapshot and restore are refused with 75 before any adb call, and the device's records stay;
  - reap that can't confirm the worker stopped exits 4 and keeps the record, so the G14 stays held;
  - run tries the reap first, exits 4 when it fails, and pushes, sets or launches nothing;
  - a reap that stops the worker clears the record; then the lock is free and idle works again.
python3 tests/gpu-diag/pending-cleanup-test.py (tests/run.sh runs it)"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

R = Path(__file__).resolve().parents[2]
D = "/data/local/tmp/openbook-gpu-diag"

FAKE_ADB = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
p = Path(os.environ["FAKE_ADB_STATE"]); s = json.loads(p.read_text())
a = sys.argv[1:]; s["calls"].append(a)
if a[:1] == ["-s"]: a = a[2:]
out = ""
if a[:1] == ["get-state"]: out = "device\n"
elif a[:1] == ["connect"]: out = "connected to " + a[1] + "\n"
elif a[:1] == ["push"]: s["helper"] = True
elif a[:1] == ["shell"]:
    q = " ".join(a[1:])
    if q.endswith("device.sh idle"):
        out = "user_activity_uptime_ms=1000 idle_ms=600000\nwakefulness=Awake\nkeyguard_showing=false\naudio_started=0\n"
    elif q.startswith("rm -rf " + os.environ["D"]):
        s["helper"] = False; s["records"] = False
    elif q.endswith("device.sh ] && echo present"):
        out = "present\n" if s["helper"] else ""
    elif "device.sh reap;" in q:
        if not s["helper"]:
            out = "@rc=6\n" if s["records"] else "@rc=0\n"
        elif s["records"] and s["reap_works"]:
            s["alive"] = False; s["records"] = False; out = "@reaped " + os.environ["D"] + "/sampler.4242\n@rc=0\n"
        elif s["records"]:
            out = "@left " + os.environ["D"] + "/sampler.4242 4243\n@rc=6\n"
        else:
            out = "@rc=0\n"
p.write_text(json.dumps(s)); sys.stdout.write(out)
'''


class PendingCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Path(self.tmp.name)
        adb = self.t / "adb"
        adb.write_text(FAKE_ADB)
        adb.chmod(0o755)
        self.state = self.t / "state.json"
        self.state.write_text(json.dumps(dict(helper=True, records=True, alive=True, reap_works=False, calls=[])))
        self.lock = self.t / "g14.lock"
        self.pending = Path(str(self.lock) + ".pending-cleanup")
        self.pending.write_text(D + "\n")
        self.env = {k: v for k, v in os.environ.items() if k != "OPENBOOK_G14_LOCK_OWNER"}
        self.env.update(ADB=str(adb), FAKE_ADB_STATE=str(self.state), D=D, OPENBOOK_G14_ADDR="192.0.2.11",
                        OPENBOOK_G14_LOCK=str(self.lock), ANDROID_ADB_SERVER_PORT="5299")

    def tearDown(self):
        self.tmp.cleanup()

    def gpu_diag(self, *args):
        self.s0 = len(self.device()["calls"])
        return subprocess.run([str(R / "scripts/gpu-diag.sh"), *args], env=self.env, capture_output=True, text=True,
                              timeout=30)

    def device(self):
        return json.loads(self.state.read_text())

    def calls(self):  # this command's adb calls, flattened
        return [" ".join(c) for c in self.device()["calls"][self.s0:]]

    def status(self):
        return subprocess.run([str(R / "scripts/g14-lock.sh"), "status"], env=self.env, capture_output=True, text=True)

    def assert_untouched(self, r, want=75):
        self.assertEqual(r.returncode, want, r.stderr)
        d = self.device()
        self.assertTrue(d["helper"] and d["records"] and d["alive"], d)
        self.assertTrue(self.pending.exists())
        self.assertEqual(self.status().returncode, 75)

    def test_other_commands_are_refused_before_any_adb_call(self):
        for args in (["idle", "0"], ["snapshot", str(self.t / "snap")], ["restore"]):
            r = self.gpu_diag(*args)
            self.assert_untouched(r)
            self.assertIn("gpu-diag.sh reap", r.stderr)
            self.assertEqual(self.calls(), [], args)
        self.assertFalse((self.t / "snap").exists())

    def test_failed_reap_keeps_the_record_and_the_hold(self):
        r = self.gpu_diag("reap")
        self.assert_untouched(r, want=4)
        self.assertFalse(any(c.endswith(f"rm -rf {D}") or " push " in f" {c} " for c in self.calls()), self.calls())

    def test_run_reaps_first_and_stops_when_it_cannot(self):
        r = self.gpu_diag("run", str(self.t / "run"), "org.example.game", "--gpu", "nvidia", "--seconds", "60")
        self.assert_untouched(r, want=4)
        self.assertIn("not starting", r.stderr)
        calls = self.calls()
        self.assertTrue(any("device.sh reap;" in c for c in calls), calls)
        for bad in (" push ", "settings put", "am start", f"rm -rf {D}"):
            self.assertFalse(any(bad in f" {c} " for c in calls), (bad, calls))

    def test_successful_reap_clears_the_record_and_frees_the_g14(self):
        s = self.device(); s["reap_works"] = True; self.state.write_text(json.dumps(s))
        r = self.gpu_diag("reap")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("@reaped", r.stdout)
        self.assertFalse(self.device()["alive"])
        self.assertFalse(self.pending.exists())
        self.assertEqual(self.status().stdout.strip(), "free")
        self.assertEqual(self.gpu_diag("idle", "0").returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
