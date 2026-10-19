#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Behavior checks of the offline replay, with explicitly SYNTHETIC gestures.

These verify the harness and distinguish tap-drag on/off. They do not reproduce
the owner's complaint or certify the physical device. Usage: replay-test.py BIN
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("convert", Path(__file__).with_name("getevent-to-frames.py"))
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)
REPLAY = str(Path(sys.argv.pop(1)).resolve()) if len(sys.argv) > 1 else None
HARDWARE = dict(right=3905, bottom=2382, res_x=31, res_y=31,
                max_finger_cnt=5, max_touch_cnt=5, reports_pressure=False)


class Motion:
    def __init__(self):
        self.time = 1.0
        self.frames = []

    def add(self, contacts, frames=1):
        for _ in range(frames):
            self.time += .0041
            fingers = [dict(id=i, x=x, y=y, palm=palm) for i, x, y, palm in contacts]
            self.frames.append(dict(time=self.time, msc=self.time - 1, buttons=0,
                                    touch_count=len(fingers), fingers=fingers))

    def run(self, **properties):
        settings = {"Tap Enable": True, "Tap Drag Enable": True, "Tap Drag Lock Enable": False}
        settings.update(properties)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text(json.dumps(dict(hardware=HARDWARE, properties=settings, frames=self.frames)))
            proc = subprocess.run([REPLAY, str(path)], check=True, capture_output=True, text=True)
            if proc.stderr:
                raise AssertionError(proc.stderr)
            return json.loads(proc.stdout)


class ReplayTests(unittest.TestCase):
    def test_converter_palm_and_missing_msc(self):
        text = """[ 10.000000] EV_KEY BTN_TOUCH UP
[ 10.000000] EV_SYN SYN_REPORT 00000000
[ 10.100000] EV_ABS ABS_MT_TRACKING_ID 00000001
[ 10.100000] EV_ABS ABS_MT_POSITION_X 00000500
[ 10.100000] EV_ABS ABS_MT_POSITION_Y 00000400
[ 10.100000] EV_ABS ABS_MT_TOOL_TYPE MT_TOOL_PALM
[ 10.100000] EV_KEY BTN_TOUCH DOWN
[ 10.100000] EV_KEY BTN_TOOL_FINGER DOWN
[ 10.100000] EV_MSC MSC_TIMESTAMP 00001004
[ 10.100000] EV_SYN SYN_REPORT 00000000
[ 10.104100] EV_ABS ABS_MT_TRACKING_ID ffffffff
[ 10.104100] EV_KEY BTN_TOUCH UP
[ 10.104100] EV_KEY BTN_TOOL_FINGER UP
[ 10.104100] EV_SYN SYN_REPORT 00000000
"""
        frames = converter.convert(text)["frames"]
        self.assertTrue(frames[1]["fingers"][0]["palm"])
        self.assertEqual(frames[-1]["msc"], frames[1]["msc"])
        self.assertEqual(frames[-1]["fingers"], [])

    def test_converter_rejects_lost_events(self):
        with self.assertRaisesRegex(ValueError, "SYN_DROPPED"):
            converter.convert("[ 1.000000] EV_SYN SYN_DROPPED 00000000")

    def test_converter_rejects_incomplete_contact(self):
        with self.assertRaisesRegex(ValueError, "all-fingers-up"):
            converter.convert("[ 1.000000] EV_SYN SYN_REPORT 00000000")

    def test_tap(self):
        m = Motion(); m.add([], 10); m.add([(1, 1800, 1000, False)], 20); m.add([])
        buttons = [x for x in m.run() if "down" in x]
        self.assertEqual([(x["down"], x["up"]) for x in buttons], [(1, 1)])

    def test_tap_drag_setting_controls_held_button(self):
        m = Motion(); m.add([], 10); m.add([(1, 1800, 1000, False)], 20); m.add([], 20)
        m.add([(2, 1800, 1000, False)], 70)
        for i in range(40):
            m.add([(2, 1800 + i * 4, 1000, False)])
        m.add([])
        enabled = [x for x in m.run() if "down" in x]
        disabled = [x for x in m.run(**{"Tap Drag Enable": False}) if "down" in x]
        self.assertEqual([(x["down"], x["up"]) for x in enabled], [(1, 0), (0, 1)])
        self.assertGreater(enabled[-1]["delivered_at"] - enabled[0]["delivered_at"], .2)
        self.assertEqual([(x["down"], x["up"]) for x in disabled], [(1, 1)])

    def test_scroll_staggered_fingers(self):
        for stagger in (0, 12, 24):  # simultaneous, 49 ms, 98 ms
            with self.subTest(stagger=stagger):
                m = Motion(); m.add([], 10)
                m.add([(1, 1500, 1000, False)], stagger)
                for i in range(80):
                    m.add([(1, 1500, 1000 + i * 5, False), (2, 2200, 1000 + i * 5, False)])
                m.add([])
                events = m.run()
                self.assertTrue(any("type: scroll" in x["description"] for x in events))
                self.assertFalse(any("down" in x for x in events))

    def test_palm_does_not_tap(self):
        m = Motion(); m.add([], 10); m.add([(1, 1800, 1000, True)], 20); m.add([])
        self.assertFalse(any("down" in x for x in m.run()))

    def test_three_finger_swipe(self):
        m = Motion(); m.add([], 10)
        for i in range(100):
            m.add([(j, 1200 + j * 550, 1000 + i * 5, False) for j in range(3)])
        m.add([])
        self.assertTrue(any("type: swipe" in x["description"] for x in m.run()))


if __name__ == "__main__":
    unittest.main()
