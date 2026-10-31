#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render-rate timeline of each boot in a logcat (ANAL-212): DisplayManager logs every render-rate change of the
built-in screen ("DisplayDeviceRepository: Display device changed render timings: ..., renderFrameRate=60.000153").
Summing the time between changes gives the time at each render rate for a whole session, which SurfaceFlinger's own
histogram (dumpsys, the live capture) only covers for the boot that was captured. Time with the screen off is left
out ("Display device changed state: ..., OFF" until "ON").
An approximation: a change too brief to reach DisplayManager is not logged. On G14 `anal192d`'s "save logs" boot,
SurfaceFlinger counted 4.1 s at 120 Hz that this log does not show.

usage: render-rate-timeline.py [--json] LOGCAT_OR_LOGD_DIR...
  a logd directory (e.g. a stick's live-NNN/prior/misc/logd): logcat.NN, oldest first, then logcat
"""
import collections
import glob
import json
import os
import re
import sys

TS = re.compile(r"^\d\d-\d\d (\d\d):(\d\d):(\d\d\.\d+)")
RATE = re.compile(r'changed render timings: "Built-in Screen", renderFrameRate=([\d.]+)')
STATE = re.compile(r'Display device changed state: "Built-in Screen", (\w+)')


def files(args):
    for a in args:
        if os.path.isdir(a):
            rot = sorted(glob.glob(f"{a}/logcat.[0-9]*"), key=lambda f: -int(f.rsplit(".", 1)[1]))
            yield from rot + [f for f in [f"{a}/logcat"] if os.path.exists(f)]
        else:
            yield a


def boots(lines):
    cur = []
    for l in lines:
        if "SystemServer: Entered the Android system server" in l and any(RATE.search(x) for x in cur):
            yield cur
            cur = []
        cur.append(l)
    yield cur


def summarise(b):
    t = lambda m: int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])  # noqa: E731 (no day roll-over in a session)
    ev, stamps = [], []
    for l in b:
        m = TS.match(l)
        if not m:
            continue
        s = t(m)
        stamps.append(s)
        if r := RATE.search(l):
            ev.append((s, "rate", round(float(r[1]))))
        elif st := STATE.search(l):
            ev.append((s, "state", st[1]))
    rates = [e for e in ev if e[1] == "rate"]
    if not rates:
        return None
    end = max(stamps)
    acc, eps, on, rate, last = collections.Counter(), [], True, None, None
    for s, kind, v in ev + [(end, "end", None)]:
        if rate is not None and on and last is not None:
            acc[rate] += s - last
            if eps and eps[-1][0] == rate and eps[-1][2] == last:
                eps[-1][1] += s - last
                eps[-1][2] = s
            else:
                eps.append([rate, s - last, s])
        if kind == "rate":
            rate = v
        elif kind == "state":
            on = v != "OFF"
        last = s
    tot = sum(acc.values())
    hms = lambda s: "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)  # noqa: E731
    top = max(acc)
    d = sorted(e[1] for e in eps if e[0] == top)
    return {"log_start": hms(min(stamps)), "log_end": hms(end), "minutes": round((end - min(stamps)) / 60, 1),
            "rate_changes": len(rates), "screen_on_seconds": round(tot, 1),
            "seconds_by_render_hz": {k: round(v, 1) for k, v in sorted(acc.items(), reverse=True)},
            "percent_by_render_hz": {k: round(100 * v / tot, 1) for k, v in sorted(acc.items(), reverse=True)},
            "top_hz": top, "top_hz_stretches": len(d), "top_hz_median_s": round(d[len(d) // 2], 2) if d else None,
            "top_hz_longest_s": round(d[-1], 1) if d else None}


def main():
    args = [a for a in sys.argv[1:] if a != "--json"]
    if not args:
        sys.exit(__doc__)
    lines = []
    for f in files(args):
        lines += open(f, errors="replace").read().splitlines()
    out = [s for s in map(summarise, boots(lines)) if s]
    if "--json" in sys.argv:
        print(json.dumps(out, indent=1))
        return
    for i, s in enumerate(out, 1):
        pct = ", ".join(f"{k} Hz {v} s ({s['percent_by_render_hz'][k]} %)" for k, v in s["seconds_by_render_hz"].items())
        print(f"boot {i}: {s['log_start']}-{s['log_end']} ({s['minutes']} min), {s['rate_changes']} render-timing "
              f"changes; screen on {s['screen_on_seconds']} s: {pct}; {s['top_hz']} Hz in {s['top_hz_stretches']} "
              f"stretches, median {s['top_hz_median_s']} s, longest {s['top_hz_longest_s']} s")


if __name__ == "__main__":
    main()
