#!/usr/bin/env python3
"""Convert G14 getevent -lt DEVICE to offline gestures frames (never injects input).

Capture only the touchpad, not the keyboard. Start before fingers land. For a
capture begun mid-contact, discard it through the first complete release.
Hardware facts below are G14 04f3:3315 only, verified with getevent -lp.
Select the timestamp policy and effective tapping settings of the runtime being
investigated. The defaults describe patched OpenBook, not the retained Ruby
input converter. No option modifies the device or removes repeat frames.
"""
import argparse
import json
import re
from pathlib import Path


def convert(text, *, msc_policy="preserve", tap_to_click=True, tap_dragging=True):
    if msc_policy not in ("preserve", "reset-on-sync"):
        raise ValueError("unknown MSC timestamp policy")
    slots = [dict(id=-1, x=0, y=0, palm=False) for _ in range(5)]
    slot = 0
    keys = {}
    msc = 0
    frames = []
    synced = False
    origin = None
    tools = {"BTN_TOOL_FINGER": 1, "BTN_TOOL_DOUBLETAP": 2,
             "BTN_TOOL_TRIPLETAP": 3, "BTN_TOOL_QUADTAP": 4, "BTN_TOOL_QUINTTAP": 5}
    for line in text.splitlines():
        match = re.fullmatch(r"\[\s*([\d.]+)\]\s+(EV_\w+)\s+(\w+)\s+(\w+)\s*", line)
        if not match:
            if line.strip():
                raise ValueError(f"not a single-device getevent -lt line: {line[:120]}")
            continue
        time, kind, code, raw = match.groups()
        value = {"UP": 0, "DOWN": 1, "REPEAT": 2,
                 "MT_TOOL_FINGER": 0, "MT_TOOL_PEN": 1, "MT_TOOL_PALM": 2}.get(raw)
        if value is None:
            value = int(raw, 16)
            if value >= 2**31:
                value -= 2**32
        if code == "SYN_DROPPED":
            raise ValueError("SYN_DROPPED: capture cannot be replayed faithfully")
        if kind == "EV_ABS":
            if code == "ABS_MT_SLOT":
                if not 0 <= value < len(slots):
                    raise ValueError("not a five-slot G14 touchpad")
                slot = value
            elif code == "ABS_MT_TRACKING_ID":
                slots[slot]["id"] = value
            elif code in ("ABS_MT_POSITION_X", "ABS_MT_POSITION_Y"):
                slots[slot]["x" if code.endswith("_X") else "y"] = value
            elif code == "ABS_MT_TOOL_TYPE":
                slots[slot]["palm"] = value == 2
        elif kind == "EV_KEY":
            keys[code] = value
        elif code == "MSC_TIMESTAMP":
            msc = value / 1e6
        elif code == "SYN_REPORT":
            frame_msc = msc
            if msc_policy == "reset-on-sync":
                msc = 0
            if not synced:
                if keys.get("BTN_TOUCH") != 0:
                    continue
                # A release guarantees that no unknown pre-capture slot remains down.
                for finger in slots:
                    finger["id"] = -1
                synced = True
                origin = float(time) - 1
            frames.append(dict(time=float(time) - origin, msc=frame_msc,
                               buttons=1 if keys.get("BTN_MOUSE", 0) else 0,
                               touch_count=max((n for k, n in tools.items() if keys.get(k, 0)), default=0),
                               fingers=[dict(f) for f in slots if f["id"] >= 0]))
    if not frames:
        raise ValueError("no complete all-fingers-up boundary; recapture")
    return dict(hardware=dict(right=3905, bottom=2382, res_x=31, res_y=31,
                             max_finger_cnt=5, max_touch_cnt=5, reports_pressure=False),
                properties={"Tap Enable": tap_to_click, "Tap Drag Enable": tap_dragging,
                            "Tap Drag Lock Enable": False},
                conversion={"msc_policy": msc_policy}, frames=frames)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--msc-policy", choices=("preserve", "reset-on-sync"), default="preserve",
                        help="Patched OpenBook preserves MSC; inspected Ruby resets it after sync")
    parser.add_argument("--tap-to-click", choices=("on", "off"), default="on",
                        help="Match the effective mapper setting captured with this motion")
    parser.add_argument("--tap-dragging", choices=("on", "off"), default="on")
    args = parser.parse_args()
    result = convert(args.capture.read_text(), msc_policy=args.msc_policy,
                     tap_to_click=args.tap_to_click == "on", tap_dragging=args.tap_dragging == "on")
    args.output.write_text(json.dumps(result, indent=2) + "\n")
