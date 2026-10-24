#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Checks for sleep-history.py and dgpu-power-adb.py's report parser (ANAL-238), on synthetic input."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


hist = module("sleep_history", "sleep-history.py")
dgpu = module("dgpu_power_adb", "dgpu-power-adb.py")

S0I3 = "                          /proc/stat=1 usr, SubsystemPowerState subsystem_0 name=SoC state_0 name=S0i3 time={} count={} last entry=0"
HISTORY = "\n".join([
    "DUMP OF SERVICE batterystats:",
    "Battery History [Format: 2] (1% used):",
    "  10-20 16:45:17.058 TIME: 2026-10-20-16-45-17",
    "  10-20 16:45:17.058 099 80010004 status=discharging health=good plug=none temp=0 volt=16000 charge=4000 +running +screen",
    "  10-20 16:46:00.000 099 80010004 -screen",
    "  10-20 16:46:10.000 099 04010004 -running",
    "  10-20 16:56:10.000 098 84010004 volt=15900 charge=3950 +running wake_reason=0:\"9 acpi\"",
    "                 Details: cpu=1u+1s",
    S0I3.format(0, 1),
    "  10-20 16:56:20.000 098 04010004 -running",
    "  10-20 17:16:00.000 097 84010004 charge=3900 +running wake_reason=0:\"9 acpi:38 PCIe PME\"",
    S0I3.format(0, 2),
    "  10-20 17:16:05.000 097 84010004 +screen",
    "  10-20 17:20:00.000 097 84010004 SHUTDOWN",
    "  10-20 17:20:01.000 START",
    "  10-20 17:21:00.000 TIME: 2026-10-20-17-21-00",
    "  10-20 17:21:00.000 097 84010004 status=charging plug=ac volt=16500 charge=3900 +running +screen +plugged",
    "  10-20 17:22:00.000 097 04010004 -running",
    "  10-20 17:22:30.000 097 84010004 +running wake_reason=0:\"Abort: Pending Wakeup Sources: mmc0\"",
    S0I3.format(0, 1),
    "",
    "Per-PID Stats:",
])


class SleepHistory(unittest.TestCase):
    def run_on(self, text, min_minutes=10):
        with tempfile.TemporaryDirectory() as tmp:
            z = Path(tmp) / "bugreport.zip"
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("bugreport-ruby-X-2026-10-21-21-50-17.txt", text)
                f.writestr("bugreport-ruby-X-2026-10-21-21-50-17-dumpstate_log-1.txt", "noise")
            r = subprocess.run([sys.executable, "-I", str(HERE / "sleep-history.py"), str(z),
                                "--min-minutes", str(min_minutes)], capture_output=True, text=True, check=True)
            return json.loads(r.stdout)

    def test_boots_suspends_and_s0i3(self):
        out = self.run_on(HISTORY)
        self.assertEqual(len(out["boots"]), 2)
        b0, b1 = out["boots"]
        self.assertFalse(b0["start_in_history"])
        self.assertTrue(b1["start_in_history"])
        self.assertEqual(b0["suspends"], 2)
        self.assertAlmostEqual(b0["suspended_s"], 600 + 1180, places=1)
        self.assertEqual(b0["s0i3_records"], {"last_time_ms": 0, "last_count": 2, "max_time_ms": 0})
        self.assertEqual(b0["wake_reasons"], {"9 acpi": 1, "9 acpi:38 PCIe PME": 1})
        self.assertEqual(b1["wake_reasons"], {"Abort: Pending Wakeup Sources: mmc0": 1})
        self.assertFalse(out["s0i3_ever_nonzero"])
        self.assertEqual(out["suspends_with_s0i3_record"], 3)

    def test_battery_span(self):
        out = self.run_on(HISTORY)
        spans = out["battery_spans"]
        # screen off 16:46:00 -> 17:16:05 on battery: 100 mAh at ~15.95 V over 30.1 min
        off = [s for s in spans if s["screen"] == "off"]
        self.assertEqual(len(off), 1)
        self.assertEqual(off[0]["charge_drop_mah"], 100)
        self.assertAlmostEqual(off[0]["minutes"], 30.1, places=1)
        self.assertGreater(off[0]["suspended_share"], 0.9)
        self.assertAlmostEqual(off[0]["avg_mw"], 100 * 15950 / (30.083 / 60) / 1000, delta=15)
        # plugged in after the restart: no battery span there
        self.assertTrue(all(s["start"] < "2026-10-20T17:20" for s in spans))

    def test_s0i3_nonzero_detected(self):
        out = self.run_on(HISTORY.replace("time=0 count=2", "time=1234 count=2"))
        self.assertTrue(out["s0i3_ever_nonzero"])
        self.assertEqual(out["boots"][0]["s0i3_records"]["max_time_ms"], 1234)

    def test_no_history_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "x.txt"; f.write_text("nothing here\n")
            r = subprocess.run([sys.executable, "-I", str(HERE / "sleep-history.py"), str(f)],
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)


class DgpuReportParse(unittest.TestCase):
    def test_parse(self):
        block = [
            "dgpu-report (adb-1)",
            "dgpu-report: 0000:64:00.0 class=0x030000 device=0x2f58 driver=- power_state=D3cold "
            "runtime_status=suspended control=auto d3cold_allowed=1 active_ms=6900 suspended_ms=2000000",
            "dgpu-report: 0000:64:00.1 class=0x040300 device=0x2f80 driver=- power_state=D3cold "
            "runtime_status=suspended control=auto",
            "dgpu-report: bridge 0000:00:03.1 driver=pcieport power_state=D3cold runtime_status=suspended "
            "control=auto acpi=\\_SB_.PCI0.GPP9 acpi_state=D3cold resources=PG00:0",
            "dgpu-report: asus-nb-wmi dgpu_disable=0 gpu_mux_mode=1",
            "dgpu-report: suspend_stats success=7 fail=0 total_hw_sleep_us=0",
            "dgpu-report: state=d3cold",
        ]
        out = dgpu.parse(block)
        self.assertEqual(out["state"], "d3cold")
        self.assertEqual([f["bdf"] for f in out["functions"]], ["0000:64:00.0", "0000:64:00.1"])
        self.assertEqual(out["functions"][0]["power_state"], "D3cold")
        self.assertEqual(out["bridge"]["bdf"], "0000:00:03.1")
        self.assertEqual(out["bridge"]["resources"], "PG00:0")
        self.assertEqual(out["asus"]["dgpu_disable"], "0")
        self.assertEqual(out["suspend_stats"]["total_hw_sleep_us"], "0")


if __name__ == "__main__":
    unittest.main()
