#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarise background blur rounds (ANAL-203): scripts/ui/blur-check.sh output, from scripts/ui/blur-bench.sh
(Cuttlefish) or from the graphics add-on's "blur" part (the G14). Writes OUTDIR/summary.csv (one row per round and
scenario), OUTDIR/summary.md and OUTDIR/blur-report.json (medians per state, the on-minus-off difference, verdicts).

On and off rounds alternate, and each on round is paired with the off round next to it: on a shared host the load
moves between rounds far more than blur moves the numbers, so the on-minus-off differences are taken per pair (their
median is what the verdicts use), not between the medians of all on and all off rounds.

Verdicts (thresholds for the G14: 2880x1800 at 120 Hz, apps at 60 Hz; docs/googlebook-ui.md §2.3):
  blur_applied  blur on: SurfaceFlinger blurs at least one layer behind the open shade and Quick Settings, and SystemUI
                reports supportsBlursOnWindows: true; blur off: no layer blurred
  no_gpu_hang   no new amdgpu fault/reset line, and SurfaceFlinger, SystemUI and system_server kept their PIDs
  frame_cost    for shade and qs, medians with blur on: SystemUI janky frames <= 10 % and <= off + 5 points;
                SurfaceFlinger missed frames <= off + 2 % of its frames (both per pair); RenderEngine time per GPU-composed frame
                <= 6 ms on average and its p90 bucket <= 8 ms (one 120 Hz refresh is 8.3 ms)

usage: blur-report.py OUTDIR [--json-only]      prints the Markdown unless --json-only
"""
import csv
import json
import re
import statistics
import sys
from pathlib import Path

FIELDS = ["round", "state", "scenario", "frames", "janky", "janky_pct", "p50_ms", "p90_ms", "p95_ms", "p99_ms",
          "gpu_p50_ms", "gpu_p90_ms", "gpu_p99_ms", "sf_frames", "sf_missed", "sf_missed_pct", "sf_client",
          "sf_janky", "sf_frame_avg_ms", "sf_frame_p90_ms", "sf_re_avg_ms", "sf_re_p50_ms", "sf_re_p90_ms",
          "sf_re_p99_ms", "blurred_layers", "max_blur_radius", "elapsed_s"]
LIMITS = {"janky_pct_on": 10.0, "janky_pct_delta": 5.0, "sf_missed_pct_delta": 2.0, "re_avg_ms": 6.0, "re_p90_ms": 8}


def num(pattern, text, cast=float):
    m = re.search(pattern, text, re.M)
    return cast(m.group(1)) if m else None


def gfxinfo(text):
    pct = lambda p, gpu="": num(rf"^{p}{gpu} percentile: (\d+)ms", text, int)
    return {
        "frames": num(r"Total frames rendered: (\d+)", text, int),
        "janky": num(r"Janky frames: (\d+)", text, int),
        "janky_pct": num(r"Janky frames: \d+ \(([\d.]+)%\)", text),
        "p50_ms": pct("50th"), "p90_ms": pct("90th"), "p95_ms": pct("95th"), "p99_ms": pct("99th"),
        "gpu_p50_ms": pct("50th", " gpu"), "gpu_p90_ms": pct("90th", " gpu"), "gpu_p99_ms": pct("99th", " gpu"),
    }


def hist_pct(line, q):
    """Percentile from a TimeStats histogram line '0ms=12 1ms=3 ...' (bucket lower bounds, in ms)."""
    buckets = [(int(b), int(c)) for b, c in re.findall(r"(\d+)ms=(\d+)", line or "")]
    total = sum(c for _, c in buckets)
    if not total:
        return None
    acc = 0
    for b, c in buckets:
        acc += c
        if acc >= q * total:
            return b
    return buckets[-1][0]


def timestats(text):
    def hist(name):
        m = re.search(rf"^{name} histogram is as below:\n(.*)$", text, re.M)
        return m.group(1) if m else ""
    re_h, fd_h = hist("renderEngineTiming"), hist("frameDuration")
    # Global aggregated jank payload only (one block per refresh-rate bucket), not the per-layer stats after it.
    g = text.split("Global aggregated jank payload", 1)[-1].split("layerName =", 1)[0] if "Global aggregated" in text else ""
    janky = [int(x) for x in re.findall(r"^jankyFrames = (\d+)", g, re.M)]
    r = {
        "sf_frames": num(r"^totalFrames = (\d+)", text, int),
        "sf_missed": num(r"^missedFrames = (\d+)", text, int),
        "sf_client": num(r"^clientCompositionFrames = (\d+)", text, int),
        "sf_janky": sum(janky) if janky else None,
        "sf_frame_avg_ms": num(r"^averageFrameDuration = ([\d.]+) ms", text),
        "sf_frame_p90_ms": hist_pct(fd_h, 0.90),
        "sf_re_avg_ms": num(r"^averageRenderEngineTiming = ([\d.]+) ms", text),
        "sf_re_p50_ms": hist_pct(re_h, 0.50), "sf_re_p90_ms": hist_pct(re_h, 0.90), "sf_re_p99_ms": hist_pct(re_h, 0.99),
    }
    if r["sf_frames"] and r["sf_missed"] is not None:
        r["sf_missed_pct"] = round(100.0 * r["sf_missed"] / r["sf_frames"], 2)
    return r


def blur_layers(path):
    if not path.exists():
        return {}
    # SurfaceFlinger lists each layer snapshot more than once; count distinct ones.
    lines = sorted(set(l.strip() for l in path.read_text(errors="replace").splitlines() if "visible reason" in l))
    radii = [int(x) for l in lines for x in re.findall(r"backgroundBlurRadius=(\d+)", l)]
    names = sorted(set(re.sub(r"^Layer \[\d+\]\s*", "", l.strip()) for l in path.read_text(errors="replace").splitlines()
                       if l.startswith("Layer [")))
    return {"blurred_layers": len(lines), "max_blur_radius": max(radii) if radii else 0, "blurred_names": names}


def state_file(path):
    """before/after lines of state.txt: PIDs, system_server starts, amdgpu events; and SystemUI's BlurUtils."""
    t = path.read_text(errors="replace") if path.exists() else ""
    kv = lambda line: dict(re.findall(r"(\w+)=(\S*)", line))
    b = next((kv(l) for l in t.splitlines() if l.startswith("before:")), {})
    a = next((kv(l) for l in t.splitlines() if l.startswith("after:")), {})
    sup = re.search(r"supportsBlursOnWindows: (\w+)", t)
    closed = re.search(r"closed_blur_lines=(\d+)", t)
    return {"before": b, "after": a, "supportsBlursOnWindows": sup.group(1) if sup else None,
            "closed_blur_lines": int(closed.group(1)) if closed else None}


def rounds(out):
    for d in sorted(out.glob("r*-*"), key=lambda p: int(re.match(r"r(\d+)", p.name).group(1))):
        m = re.match(r"r(\d+)-(on|off)$", d.name)
        if m:
            yield int(m.group(1)), m.group(2), d


def host_load(out):
    """{round: (load at start, load at end)} from blur-bench.sh's bench.log (Cuttlefish runs only)."""
    t = (out / "bench.log").read_text(errors="replace") if (out / "bench.log").exists() else ""
    start = {int(n): float(l) for n, l in re.findall(r"round (\d+): blur \w+, host load ([\d.]+)", t)}
    end = {int(n): float(l) for n, l in re.findall(r"round (\d+) end: host load ([\d.]+)", t)}
    return {n: (start.get(n), end.get(n)) for n in start}


def pairs(out):
    """Adjacent (on round, off round) pairs, in order: r1-on with r2-off, r3-on with r4-off, ..."""
    rs = list(rounds(out))
    out_pairs, i = [], 0
    while i + 1 < len(rs):
        a, b = rs[i], rs[i + 1]
        if {a[1], b[1]} == {"on", "off"}:
            out_pairs.append((a[0], b[0]) if a[1] == "on" else (b[0], a[0]))
            i += 2
        else:
            i += 1
    return out_pairs


def rows(out):
    for rnd, state, d in rounds(out):
        for sc in ("shade", "qs"):
            g, t, m = d / sc / "gfxinfo.txt", d / sc / "timestats.txt", d / sc / "meta.txt"
            if not g.exists():
                continue
            r = {"round": rnd, "state": state, "scenario": sc, **gfxinfo(g.read_text(errors="replace"))}
            if t.exists():
                r.update(timestats(t.read_text(errors="replace")))
            r.update(blur_layers(d / sc / "sf-blur-layers.txt"))
            if m.exists():
                r["elapsed_s"] = num(r"elapsed_s=([\d.]+)", m.read_text())
            yield r
        b = d / "settings" / "gfx-bench.csv"
        if b.exists():
            for line in [l for l in csv.DictReader(b.open()) if l.get("frames") not in (None, "", "0")][-1:]:
                yield {"round": rnd, "state": state, "scenario": "settings-scroll",
                       **{k: (float(line[k]) if line.get(k) not in (None, "") else None)
                          for k in ("frames", "janky", "janky_pct", "p50_ms", "p90_ms", "p95_ms", "p99_ms",
                                    "gpu_p50_ms", "gpu_p90_ms")}}


def med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def fmt(v):
    if v is None:
        return "–"
    return f"{v:.1f}" if isinstance(v, float) and not v.is_integer() else f"{int(v)}"


def verdicts(out, data, medians, paired):
    v = {}
    # blur_applied: the first round of each state recorded the open panels' layers
    applied, why = True, []
    for st in ("on", "off"):
        for sc in ("shade", "qs"):
            rs = [r for r in data if r["state"] == st and r["scenario"] == sc and r.get("blurred_layers") is not None]
            if not rs:
                applied = None if applied is not False else False
                why.append(f"{sc}/{st}: no layer dump")
                continue
            n = rs[0]["blurred_layers"]
            if (st == "on") != (n > 0):
                applied = False
            why.append(f"{sc}/{st}: {n} blurred layer(s), radius up to {rs[0].get('max_blur_radius', 0)}")
    sup = [state_file(d / "state.txt")["supportsBlursOnWindows"] for _, st, d in rounds(out) if st == "on"]
    if sup and any(s != "true" for s in sup):
        applied = False
    why.append(f"SystemUI supportsBlursOnWindows with blur on: {', '.join(s or '?' for s in sup) or 'not recorded'}")
    stuck = [f"r{rnd}-{st}" for rnd, st, d in rounds(out) if state_file(d / "state.txt")["closed_blur_lines"]]
    if stuck:
        why.append(f"a layer was still blurred with the panels closed before: {', '.join(stuck)}")
    v["blur_applied"] = {"ok": applied, "detail": why}
    # no_gpu_hang
    hang, why = True, []
    for rnd, st, d in rounds(out):
        s = state_file(d / "state.txt")
        b, a = s["before"], s["after"]
        if not a:
            hang = False
            why.append(f"r{rnd}-{st}: no 'after' line (cut short)")
            continue
        ev = int(a.get("amdgpu_events") or 0) - int(b.get("amdgpu_events") or 0)
        moved = [k for k in ("surfaceflinger", "systemui", "system_server", "system_server_starts") if b.get(k) != a.get(k)]
        if ev or moved:
            hang = False
            why.append(f"r{rnd}-{st}: {ev} new amdgpu line(s); changed: {', '.join(moved) or 'none'}")
    v["no_gpu_hang"] = {"ok": hang, "detail": why or ["no amdgpu fault/reset line, no restart in any round"]}
    # frame_cost
    cost, why = True, []
    L = LIMITS
    for sc in ("shade", "qs"):
        on, off = medians.get((sc, "on")), medians.get((sc, "off"))
        if not on or not off or not paired.get(sc):
            cost = None
            why.append(f"{sc}: needs adjacent rounds with blur on and off")
            continue
        pd = lambda k: med([p.get(k) for p in paired[sc]])
        checks = [
            ("SystemUI janky % (on)", on["janky_pct"], L["janky_pct_on"]),
            ("SystemUI janky % on − off (paired)", pd("janky_pct"), L["janky_pct_delta"]),
            ("SF missed % on − off (paired)", pd("sf_missed_pct"), L["sf_missed_pct_delta"]),
            ("RenderEngine avg ms (on)", on["sf_re_avg_ms"], L["re_avg_ms"]),
            ("RenderEngine p90 bucket ms (on)", on["sf_re_p90_ms"], L["re_p90_ms"]),
        ]
        for name, val, lim in checks:
            if val is None:
                cost = None if cost is not False else False
                why.append(f"{sc}: {name}: not recorded")
            elif val > lim:
                cost = False
                why.append(f"{sc}: {name} = {fmt(float(val))} > {lim}: FAIL")
            else:
                why.append(f"{sc}: {name} = {fmt(float(val))} <= {lim}")
    v["frame_cost"] = {"ok": cost, "detail": why}
    return v


def report(out):
    """Write OUTDIR's summary.csv, blur-report.json and summary.md; return (report dict, Markdown)."""
    out = Path(out)
    data = list(rows(out))
    with (out / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(data)
    keys = [k for k in FIELDS if k not in ("round", "state", "scenario")]
    medians = {}
    for sc in ("shade", "qs", "settings-scroll"):
        for st in ("on", "off"):
            rs = [r for r in data if r["scenario"] == sc and r["state"] == st]
            if rs:
                medians[(sc, st)] = {k: med([r.get(k) for r in rs]) for k in keys}
                medians[(sc, st)]["rounds"] = len(rs)
    load = host_load(out)
    by = {(r["round"], r["scenario"]): r for r in data}
    pkeys = ("janky_pct", "p90_ms", "sf_missed_pct", "sf_frame_avg_ms", "sf_re_avg_ms")
    paired = {}
    for sc in ("shade", "qs", "settings-scroll"):
        for on_r, off_r in pairs(out):
            a, b = by.get((on_r, sc)), by.get((off_r, sc))
            if not a or not b:
                continue
            d = {"on_round": on_r, "off_round": off_r,
                 "host_load": [x for n in (on_r, off_r) for x in load.get(n, (None, None)) if x is not None]}
            for k in pkeys:
                d[f"{k}_on"], d[f"{k}_off"] = a.get(k), b.get(k)
                d[k] = None if a.get(k) is None or b.get(k) is None else round(a[k] - b[k], 2)
            paired.setdefault(sc, []).append(d)
    v = verdicts(out, data, medians, paired)
    report = {"schema": "openbook-blur-report/1", "dir": str(out.resolve()), "limits": LIMITS, "verdicts": v,
              "medians": {f"{sc}/{st}": m for (sc, st), m in medians.items()}, "paired": paired, "rounds": data}
    (out / "blur-report.json").write_text(json.dumps(report, indent=1))
    cols = [("frames", "frames"), ("janky_pct", "janky %"), ("p50_ms", "p50"), ("p90_ms", "p90"),
            ("gpu_p50_ms", "GPU p50"), ("gpu_p90_ms", "GPU p90"), ("sf_frames", "SF frames"),
            ("sf_missed_pct", "SF missed %"), ("sf_frame_avg_ms", "SF frame avg"), ("sf_re_avg_ms", "RE avg"),
            ("sf_re_p90_ms", "RE p90"), ("max_blur_radius", "blur radius")]
    lines = ["| Scenario | Blur | Rounds | " + " | ".join(c[1] for c in cols) + " |",
             "|---|---|---|" + "---|" * len(cols)]
    for sc in ("shade", "qs", "settings-scroll"):
        for st in ("on", "off"):
            m = medians.get((sc, st))
            if m:
                lines.append(f"| {sc} | {st} | {m['rounds']} | " + " | ".join(fmt(m[k]) for k, _ in cols) + " |")
        on, off = medians.get((sc, "on")), medians.get((sc, "off"))
        if on and off:
            diff = [None if on[k] is None or off[k] is None else on[k] - off[k] for k, _ in cols]
            lines.append(f"| {sc} | on − off | | " + " | ".join(
                "–" if d is None else ("+" if d > 0 else "") + fmt(float(d)) for d in diff) + " |")
    plines = ["| Scenario | Rounds (on, off) | Host load | janky % on / off | p90 ms on / off | SF missed % on / off "
              "| SF frame avg ms on / off | RE avg ms (on) |", "|---|---|---|---|---|---|---|---|"]
    for sc, ps in paired.items():
        for d in ps:
            hl = f"{min(d['host_load']):.0f}–{max(d['host_load']):.0f}" if d["host_load"] else "–"
            pr = lambda k: f"{fmt(d[k + '_on'])} / {fmt(d[k + '_off'])}"
            plines.append(f"| {sc} | r{d['on_round']}, r{d['off_round']} | {hl} | {pr('janky_pct')} | {pr('p90_ms')} | "
                          f"{pr('sf_missed_pct')} | {pr('sf_frame_avg_ms')} | {fmt(d['sf_re_avg_ms_on'])} |")
    word = {True: "PASS", False: "FAIL", None: "INCOMPLETE"}
    vl = [f"- **{k}: {word[x['ok']]}.** " + "; ".join(x["detail"]) for k, x in v.items()]
    md = ("Medians over rounds; times in ms. HWUI columns are SystemUI's `dumpsys gfxinfo` (Settings' for the scroll). "
          "SF columns are SurfaceFlinger TimeStats over the same cycles: RE = RenderEngine time per GPU-composed frame "
          "(p90 = histogram bucket); blur radius = the largest `backgroundBlurRadius` behind the open panel.\n\n"
          + "\n".join(lines) + "\n\nPer pair of adjacent rounds (host load: blur-bench.sh's readings at each round's "
          "start and end, Cuttlefish only):\n\n" + "\n".join(plines)
          + "\n\nVerdicts (G14 thresholds):\n\n" + "\n".join(vl) + "\n")
    (out / "summary.md").write_text(md)
    return report, md


def main():
    _, md = report(sys.argv[1])
    if "--json-only" not in sys.argv:
        print(md)


if __name__ == "__main__":
    main()
