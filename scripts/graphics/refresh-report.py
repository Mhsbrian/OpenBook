#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarise a refresh-qemu.sh run (ANAL-212): the sections expect-refresh.json printed on the serial console.
Writes refresh.json and refresh.md into DIR and prints refresh.md.

  config        the desktop framework RRO is on and config_defaultRefreshRate resolves to 0 (no default render cap);
                also config_defaultPeakRefreshRate and DisplayModeDirector's default and peak votes
  policy        after the scroll: the display runs its fastest mode and DisplayManager's primary render range reaches it
                (live-report.py's refresh_rate verdict on the SF1 dump)
  scroll        while Settings scrolls: SurfaceFlinger's render-rate samples, and the time it spent at each render
                rate between the SF0 and SF1 dumps; ok when the fastest mode's rate is the most common sample

usage: refresh-report.py DIR
"""
import importlib.util
import json
import os
import re
import sys


def sections(text):
    return {m.group(1): m.group(2).replace("\r", "")
            for m in re.finditer(r"\n===([A-Z0-9-]+)-BEGIN===\r?\n(.*?)\n===\1-END===", text, re.S)}


def main():
    d = sys.argv[1]
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("live_report",
                                                  os.path.join(here, "..", "installer", "live-report.py"))
    lr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lr)
    sec = sections(open(f"{d}/serial.log", "rb").read().decode("utf-8", "replace"))
    v = {}
    cfg = sec.get("CONFIG", "")
    vals = dict(re.findall(r"android:integer/(config_default\w*RefreshRate)\s*->\s*(\S+)", cfg))
    if not vals:  # `cmd overlay lookup` prints only the value, one line per lookup
        lines = [l.strip() for l in cfg.splitlines() if re.fullmatch(r"-?\d+", l.strip())]
        vals = dict(zip(("config_defaultRefreshRate", "config_defaultPeakRefreshRate"), lines))
    v["config"] = {"ok": ("[x] dev.anybook.overlay.desktop.framework" in cfg
                          and vals.get("config_defaultRefreshRate") == "0") if cfg else None,
                   "fingerprint": (cfg.splitlines() or [None])[0], "values": vals,
                   "overlays": [l.strip() for l in cfg.splitlines() if l.startswith("[")],
                   "dmd": [l.strip() for l in sec.get("DMD", "").splitlines()
                           if re.search(r"mDefault|PRIORITY_DEFAULT|PRIORITY_USER_SETTING_PEAK", l)][:12]}
    ok, facts = lr.refresh_rate(sec.get("SF1", ""))
    v["policy"] = {"ok": ok, **facts}
    samples = [float(x) for x in re.findall(r"renderRate=([\d.]+) Hz", sec.get("SAMPLES", ""))]
    h0 = lr.refresh_rate(sec.get("SF0", ""))[1].get("seconds_by_render_hz", {})
    h1 = facts.get("seconds_by_render_hz", {})
    delta = {k: round(h1[k] - h0.get(k, 0), 1) for k in h1 if h1[k] - h0.get(k, 0) > 0.05}
    top = facts.get("fastest_mode_hz")
    common = max(set(samples), key=samples.count) if samples else None
    v["scroll"] = {"ok": (abs(common - top) < 0.5) if samples and top else None, "samples_hz": samples,
                   "most_common_hz": common, "seconds_by_render_hz_during": delta}
    run = os.path.basename(os.path.dirname(os.path.abspath(d)))  # <logs>/<RUN>/refresh
    json.dump({"schema": "openbook-refresh-qemu/1", "run": run, "verdicts": v},
              open(f"{d}/refresh.json", "w"), indent=1)
    lines = [f"# Refresh rate in QEMU: {run}", "",
             "| Check | Verdict | Facts |", "|---|---|---|"]
    for k, x in v.items():
        mark = {True: "yes", False: "NO", None: "unknown"}[x["ok"]]
        facts = json.dumps({f: y for f, y in x.items() if f != "ok"})[:400].replace("|", "/")
        lines.append(f"| {k} | {mark} | {facts} |")
    open(f"{d}/refresh.md", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
