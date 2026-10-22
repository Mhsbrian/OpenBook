#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Sleep and battery history of a Ruby laptop from a bugreport, without root (ANAL-238).

Reads the human-readable "Battery History" of `dumpsys batterystats` (in an `adb
bugreport` zip or a saved text file) and reports, per boot:

- suspends and time suspended (`-running` .. `+running`);
- the S0i3 residency the OpenBook PowerStats HAL reported (`SubsystemPowerState
  ... name=S0i3 time=<total_hw_sleep ms> count=<suspend_stats success>`);
- kernel wake reasons, counted.

It also reports battery-only spans of at least --min-minutes with a constant
screen state: charge drop (mAh), mean voltage and average power. Charge is
reported in whole mAh, so short spans are not meaningful.

Only counts, kernel wake-reason names and battery figures are written: no app,
account, network or device identifiers.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

LINE = re.compile(r"^  (\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)\.(\d{3}) (.*)$")
TIME = re.compile(r"TIME: (\d{4})-")
EVENT = re.compile(r"^(\d{3}) [0-9a-f]{8} (.*)$")
TOKEN = re.compile(r'([+-]?[A-Za-z_][A-Za-z0-9_]*)(?:=((?:-?\d+:)?"[^"]*"|\S+))?')
S0I3 = re.compile(r"name=SoC state_0 name=S0i3 time=(\d+) count=(\d+)")


def history_lines(path):
    """The lines of the first "Battery History" block."""
    data = Path(path).read_bytes()
    if data[:2] == b"PK":
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist()
                     if re.fullmatch(r"bugreport-.*\.txt", n) and "dumpstate_log" not in n]
            if not names:
                raise SystemExit(f"{path}: no bugreport text in the zip")
            data = z.read(names[0])
    text = data.decode("utf-8", "replace").splitlines()
    for i, s in enumerate(text):
        if s.startswith("Battery History ["):
            out = []
            for t in text[i + 1:]:
                if not t.strip() or not t.startswith(" "):
                    break
                out.append(t)
            return hashlib.sha256(data).hexdigest(), out
    raise SystemExit(f"{path}: no Battery History block")


class Boot:
    def __init__(self, start, started_here):
        self.start = start
        self.started_here = started_here  # False: the history begins inside this boot
        self.end = None
        self.suspends = 0
        self.suspended_s = 0.0
        self.s0i3 = None  # (time_ms, count) of the last record in this boot
        self.s0i3_max_ms = 0
        self.wake = {}

    def json(self):
        return {"start": self.start.isoformat(timespec="seconds"),
                "start_in_history": self.started_here,
                "end": self.end.isoformat(timespec="seconds") if self.end else None,
                "suspends": self.suspends,
                "suspended_s": round(self.suspended_s, 1),
                "s0i3_records": None if self.s0i3 is None else
                {"last_time_ms": self.s0i3[0], "last_count": self.s0i3[1], "max_time_ms": self.s0i3_max_ms},
                "wake_reasons": dict(sorted(self.wake.items(), key=lambda kv: -kv[1]))}


def wake_name(v):
    v = v.strip('"')
    v = re.sub(r'^-?\d+:"', "", v).strip('"')
    if v.startswith("Abort"):
        return re.sub(r"\s+", " ", v)[:80]
    return v


def parse(lines, min_minutes):
    year = None
    for s in lines:
        m = TIME.search(s)
        if m:
            year = int(m.group(1))
            break
    if year is None:
        raise SystemExit("no TIME: line to date the history")
    boots, segs = [], []
    boot = None
    running, screen, plugged = True, None, None
    charge = volt = None
    seg = None  # open battery-only segment
    prev_t = None
    susp_at = None

    def close_seg(t):
        nonlocal seg
        if seg and charge is not None and seg["charge0"] is not None:
            minutes = (t - seg["t0"]).total_seconds() / 60
            if minutes >= min_minutes:
                drop = seg["charge0"] - charge
                v = sum(seg["volts"]) / len(seg["volts"]) if seg["volts"] else None
                hours = minutes / 60
                segs.append({"start": seg["t0"].isoformat(timespec="seconds"),
                             "minutes": round(minutes, 1),
                             "screen": "on" if seg["screen"] else "off",
                             "suspended_share": round(seg["susp_s"] / (minutes * 60), 3),
                             "charge_drop_mah": drop,
                             "mean_mv": round(v) if v else None,
                             "avg_mw": round(drop * v / hours / 1000) if v and hours else None})
        seg = None

    for s in lines:
        m = LINE.match(s)
        if not m:
            r = S0I3.search(s)
            if r and boot:
                ms, count = int(r.group(1)), int(r.group(2))
                boot.s0i3 = (ms, count)
                boot.s0i3_max_ms = max(boot.s0i3_max_ms, ms)
            continue
        mo, d, hh, mi, ss, ms_, rest = m.groups()
        t = dt.datetime(year, int(mo), int(d), int(hh), int(mi), int(ss), int(ms_) * 1000)
        if prev_t and t < prev_t - dt.timedelta(days=200):  # December -> January
            year += 1
            t = t.replace(year=year)
        if seg and not running and prev_t:
            seg["susp_s"] += (t - max(prev_t, seg["t0"])).total_seconds()
        prev_t = t
        if rest.startswith("TIME:") or rest.startswith("RESET:TIME:"):
            mt = TIME.search(rest)
            if mt:
                year = int(mt.group(1))
            if boot is None:
                boot = Boot(t, False)
                boots.append(boot)
            continue
        if rest == "START":
            close_seg(t)
            if boot and boot.end is None:
                boot.end = t
            boot = Boot(t, True)
            boots.append(boot)
            running, screen, plugged, susp_at = True, None, None, None
            continue
        if rest == "SHUTDOWN":
            close_seg(t)
            if boot:
                boot.end = t
            continue
        me = EVENT.match(rest)
        if not me:
            continue
        if boot is None:
            boot = Boot(t, False)
            boots.append(boot)
        was = (plugged, screen)
        for k, v in TOKEN.findall(me.group(2)):
            if k == "plug":
                plugged = v != "none"
            elif k in ("+plugged", "-plugged"):
                plugged = k == "+plugged"
            elif k in ("+screen", "-screen"):
                screen = k == "+screen"
            elif k == "-running":
                running = False
                susp_at = t
                boot.suspends += 1
            elif k == "+running":
                running = True
                if susp_at:
                    boot.suspended_s += (t - susp_at).total_seconds()
                susp_at = None
            elif k == "wake_reason" and v:
                n = wake_name(v)
                boot.wake[n] = boot.wake.get(n, 0) + 1
            elif k == "charge" and v.isdigit():
                charge = int(v)
                if seg and seg["charge0"] is None:
                    seg["charge0"] = charge
            elif k == "volt" and v.isdigit():
                volt = int(v)
                if seg:
                    seg["volts"].append(volt)
        if (plugged, screen) != was:
            close_seg(t)
        if seg is None and plugged is False and screen is not None:
            seg = {"t0": t, "screen": screen, "charge0": charge, "volts": [volt] if volt else [], "susp_s": 0.0}
    if prev_t:
        close_seg(prev_t)
    return boots, segs


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", help="adb bugreport zip, or a text file holding dumpsys batterystats")
    ap.add_argument("--min-minutes", type=float, default=10.0, help="shortest battery span to report (default 10)")
    ap.add_argument("--out", help="also write the JSON here")
    a = ap.parse_args()
    sha, lines = history_lines(a.source)
    boots, segs = parse(lines, a.min_minutes)
    off = [s for s in segs if s["screen"] == "off" and s["avg_mw"] is not None]
    on = [s for s in segs if s["screen"] == "on" and s["avg_mw"] is not None]

    def total(xs):
        mins = sum(s["minutes"] for s in xs)
        mwh = sum(s["avg_mw"] * s["minutes"] / 60 for s in xs)
        return {"spans": len(xs), "minutes": round(mins, 1), "avg_mw": round(mwh / mins * 60) if mins else None}

    out = {"schema": "openbook-ruby-sleep-history/1",
           "source_sha256": sha,
           "history_lines": len(lines),
           "boots": [b.json() for b in boots],
           "battery_spans": segs,
           "battery_totals": {"screen_off": total(off), "screen_on": total(on)},
           "s0i3_ever_nonzero": any(b.s0i3_max_ms > 0 for b in boots),
           "suspends_with_s0i3_record": sum(b.s0i3[1] for b in boots if b.s0i3)}
    text = json.dumps(out, indent=1) + "\n"
    sys.stdout.write(text)
    if a.out:
        Path(a.out).write_text(text)


if __name__ == "__main__":
    main()
