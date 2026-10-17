#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarise an OpenBook graphics run (ANAL-177): the G14's (openbook/logs/live-NNN/addon-gfx-out.tar from the graphics
check, or the folder it unpacks to) or the build host's pre-check (scripts/graphics/pre-check.sh). Writes
gfx-report.json (schema openbook-gfx-report/1) and gfx-report.md into the run folder and prints the markdown.

Per part (vk, vk14, gles-angle, gles-mesa, egl, angle): the counts per result (deqp-runner's names: Pass, Fail, Crash,
Timeout, Skip = not supported or skipped, Warn = quality or compatibility warning, Flake = failed, then passed on a
retry), the renderer the run saw, the failing cases with dEQP's own status and message, grouped by message, and a
comparison with Mesa CI's expectation files for the closest GPU (--mesa-ci src/amd/ci of the Mesa tree, --radv-gpu,
--radeonsi-gpu): which of our failures Mesa CI also lists, which are new, and how many listed failures we pass. Mesa CI
runs a different dEQP version (VK-GL-CTS) on Linux, so the comparison is a guide, not a verdict.

usage: gfx-report.py DIR [--mesa-ci DIR] [--radv-gpu GPU] [--radeonsi-gpu GPU] [--label TEXT]
  DIR: a live-NNN folder (its addon-gfx-out.tar is unpacked to addon-gfx/), an unpacked run, or a pre-check folder
"""
import argparse
import collections
import glob
import gzip
import html
import json
import os
import re
import sys
import tarfile

PARTS = ("vk", "vk14", "gles-angle", "gles-mesa", "egl", "angle")
STATUSES = ("Pass", "Fail", "Crash", "Timeout", "Skip", "Warn", "Flake", "Missing")
QPA_STATUS = {"Pass": "Pass", "NotSupported": "Skip", "QualityWarning": "Warn", "CompatibilityWarning": "Warn",
              "Fail": "Fail", "InternalError": "Fail", "ResourceError": "Fail", "Crash": "Crash", "Timeout": "Timeout",
              "Waiver": "Skip"}
ANGLE_STATUS = {"PASS": "Pass", "FAIL": "Fail", "SKIP": "Skip", "CRASH": "Crash", "TIMEOUT": "Timeout",
                "FLAKE": "Flake", "NOTRUN": "Missing"}


def opener(path):
    return gzip.open(path, "rt", errors="replace") if path.endswith(".gz") else open(path, errors="replace")


def first(*paths):
    return next((p for p in paths if p and os.path.exists(p)), None)


def qpa_cases(text):
    """{case: (status, code, message)} from a dEQP test log; a case begun but never ended is a crash."""
    out, cur, code, msg = {}, None, None, ""
    for line in text.splitlines():
        if line.startswith("#beginTestCaseResult "):
            if cur:
                out[cur] = ("Crash", "Crash", "the process ended during this case")
            cur, code, msg = line.split(" ", 1)[1].strip(), None, ""
        elif line.startswith("#endTestCaseResult") and cur:
            out[cur] = (QPA_STATUS.get(code, "Fail"), code, msg)
            cur = None
        elif line.startswith("#terminateTestCaseResult") and cur:
            why = line.split(" ", 1)[1].strip() if " " in line else ""
            out[cur] = ("Timeout" if "timeout" in why.lower() else "Crash", "Terminated", why)
            cur = None
        elif cur:
            m = re.search(r'<Result StatusCode="([^"]+)">(.*?)</Result>', line)
            if m:
                code, msg = m.group(1), html.unescape(m.group(2))
    if cur:
        out[cur] = ("Crash", "Crash", "the process ended during this case")
    return out


def qpa_reason(run_dir, case):
    p = first(os.path.join(run_dir, f"{case}.qpa"), os.path.join(run_dir, f"{case}.qpa.gz"))
    if not p:
        return None, None
    c = qpa_cases(opener(p).read()).get(case)
    return (c[1], re.sub(r"\s+", " ", c[2]).strip()[:200]) if c else (None, None)


def mesa_list(paths, regex=False):
    names, pats = {}, []
    for p in paths:
        if not p or not os.path.exists(p):
            continue
        for line in open(p):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if regex:
                pats.append(re.compile(line))
            else:
                name, _, status = line.partition(",")
                names[name] = status or "Fail"
    return names, pats


def renderer_of(text):
    for pat in (r"deviceName: (.*)", r"GL_RENDERER: (.*)", r"renderer: (.*)"):
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return None


def deqp_part(pdir, name, mesa):
    run = os.path.join(pdir, "run")
    res = first(os.path.join(run, "results.csv"), os.path.join(run, "results.csv.gz"))
    console = first(os.path.join(pdir, "console.txt"), os.path.join(pdir, "deqp-runner.txt"))
    ctext = open(console, errors="replace").read() if console else ""
    r = {"part": name, "ran": bool(res), "renderer": renderer_of(ctext)}
    m = re.search(r"Running dEQP on (\d+) threads", ctext)
    r["threads"] = int(m.group(1)) if m else None
    if not res:
        r["note"] = "no results.csv (not run, cut short or failed to start)"
        r["console_tail"] = ctext.strip().splitlines()[-8:]
        return r, {}
    results = {}
    for line in opener(res):
        f = line.rstrip("\n").split(",")
        if len(f) >= 2:
            results[f[0]] = f[1]
    return r, results


def egl_part(pdir):
    logs = sorted(glob.glob(os.path.join(pdir, "egl-*.qpa*")), key=lambda p: int(re.search(r"egl-(\d+)", p).group(1)))
    r = {"part": "egl", "ran": bool(logs), "restarts": max(len(logs) - 1, 0)}
    results, reasons = {}, {}
    for p in logs:
        for case, (st, code, msg) in qpa_cases(opener(p).read()).items():
            results[case] = st
            reasons[case] = (code, re.sub(r"\s+", " ", msg).strip()[:200])
    inst = " ".join(open(p, errors="replace").read() for p in glob.glob(os.path.join(pdir, "instrument-*.txt")))
    m = re.search(r"Renderer: ?(.*)", inst)
    r["renderer"] = m.group(1) if m else None
    if not logs:
        r["note"] = "no dEQP-EGL log"
    return r, results, reasons


def gtest_out(text, stopped):
    """{test: status} from gtest's console output; a test started but never finished timed out (the runner stopped
    the app) or crashed."""
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"\[ RUN      \] (\S+)", line)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"\[ +(OK|FAILED|SKIPPED) +\] (\S+) \(", line)
        if m:
            out[m.group(2)] = {"OK": "Pass", "FAILED": "Fail", "SKIPPED": "Skip"}[m.group(1)]
            if m.group(2) == cur:
                cur = None
    if cur and cur not in out:
        out[cur] = "Timeout" if stopped else "Crash"
    return out


def angle_part(pdir):
    """ANGLE end2end, merged over gfx-run.sh's rounds: a round's output-<n>.json if it finished, else its gtest output
    out-<n>.txt. Only the tests our expectations subset marks PASS count (exp-0.txt); a test's result is the first real
    one in round order, and one that never ran is Missing."""
    rounds = sorted({int(m.group(1)) for p in glob.glob(os.path.join(pdir, "*-*.*"))
                     for m in [re.search(r"/(?:output|out)-(\d+)\.", p)] if m})
    legacy = first(os.path.join(pdir, "output.json"), os.path.join(pdir, "output.json.gz"))
    r = {"part": "angle", "ran": bool(rounds or legacy), "rounds": len(rounds)}
    if not r["ran"]:
        r["note"] = "no output.json or gtest output"
        inst = first(os.path.join(pdir, "instrument-0.txt"), os.path.join(pdir, "instrument.txt"))
        r["instrument_tail"] = open(inst, errors="replace").read().strip().splitlines()[-6:] if inst else []
        return r, {}
    console = first(os.path.join(pdir, "console.txt"))
    ctext = open(console, errors="replace").read() if console else ""
    per_round = []
    for n in rounds or [None]:
        js = first(os.path.join(pdir, f"output-{n}.json"), os.path.join(pdir, f"output-{n}.json.gz")) if n is not None \
            else legacy
        if js:
            j = json.load(opener(js))
            r["interrupted"] = r.get("interrupted", False) or bool(j.get("interrupted"))
            res = {}
            for name, t in j.get("tests", {}).items():
                a = t.get("actual", "").split()
                res[name] = ANGLE_STATUS.get(a[-1] if a else "", "Fail")
        else:
            o = first(os.path.join(pdir, f"out-{n}.txt"), os.path.join(pdir, f"out-{n}.txt.gz"))
            res = gtest_out(opener(o).read(), f"round {n}: " in ctext and "stopped:" in
                            next((l for l in ctext.splitlines() if l.startswith(f"round {n}: ")), "")) if o else {}
        per_round.append(res)
    exp = first(os.path.join(pdir, "exp-0.txt"))
    wanted = None
    if exp:
        wanted = [re.sub(r" = PASS$", "", l.strip().split(": ", 1)[1]) for l in open(exp) if l.rstrip().endswith("= PASS")]
    results, keep = {}, set(wanted or [])
    for res in per_round:
        for name, st in res.items():
            if wanted is not None and name not in keep:
                continue
            if results.get(name) in (None, "Missing") and st != "Missing":
                results[name] = st
    for name in wanted or []:
        results.setdefault(name, "Missing")
    if wanted is not None:
        r["subset"] = len(wanted)
    return r, results


def summarise(r, results, reasons, mesa_fails=None, mesa_flakes=None, mesa_files=()):
    counts = collections.Counter(results.values())
    r["counts"] = {s: counts.get(s, 0) for s in STATUSES if counts.get(s, 0) or s in ("Pass", "Fail", "Crash")}
    r["total"] = len(results)
    bad = sorted(c for c, s in results.items() if s in ("Fail", "Crash", "Timeout"))
    r["failing"] = [{"case": c, "status": results[c], "code": reasons.get(c, (None, None))[0],
                     "message": reasons.get(c, (None, None))[1]} for c in bad[:300]]
    by_msg = collections.Counter((reasons.get(c, (None, None))[1] or results[c]) for c in bad)
    r["failing_by_message"] = [{"message": m, "cases": n} for m, n in by_msg.most_common(25)]
    r["flakes"] = sorted(c for c, s in results.items() if s == "Flake")
    if mesa_fails is not None:
        listed = {c for c in mesa_fails if c in results}
        r["mesa_ci"] = {
            "files": list(mesa_files),
            "our_failures_listed_by_mesa_ci": sorted(c for c in bad if c in mesa_fails),
            "our_failures_not_listed": sorted(c for c in bad if c not in mesa_fails and
                                              not any(p.match(c) for p in (mesa_flakes or []))),
            "mesa_ci_listed_failures_in_our_list": len(listed),
            "mesa_ci_listed_failures_we_pass": sorted(c for c in listed if results[c] == "Pass"),
        }
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--mesa-ci", help="src/amd/ci of the Mesa tree")
    ap.add_argument("--radv-gpu", default="navi31")
    ap.add_argument("--radeonsi-gpu", default="vangogh")
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    d = a.dir
    tar = os.path.join(d, "addon-gfx-out.tar")
    if os.path.exists(tar):
        dest = os.path.join(d, "addon-gfx")
        os.makedirs(dest, exist_ok=True)
        try:
            with tarfile.open(tar) as t:
                t.extractall(dest, filter="data")
        except (tarfile.TarError, EOFError) as e:
            print(f"note: {tar} is cut or damaged ({e}); unpacked what it holds", file=sys.stderr)
        d = dest
    parts_meta = {}
    for line in open(os.path.join(d, "parts.jsonl")) if os.path.exists(os.path.join(d, "parts.jsonl")) else []:
        try:
            o = json.loads(line)
            parts_meta[o["part"]] = o
        except ValueError:
            pass
    for p in glob.glob(os.path.join(d, "*", "part.json")):
        o = json.load(open(p))
        parts_meta[o["part"]] = o
    ci = a.mesa_ci
    radv_fail, _ = mesa_list([ci and f"{ci}/radv-fails.txt", ci and f"{ci}/radv-{a.radv_gpu}-fails.txt"])
    _, radv_flake = mesa_list([ci and f"{ci}/radv-{a.radv_gpu}-flakes.txt"], regex=True)
    si_fail, _ = mesa_list([ci and f"{ci}/radeonsi-{a.radeonsi_gpu}-fails.txt"])
    _, si_flake = mesa_list([ci and f"{ci}/radeonsi-{a.radeonsi_gpu}-flakes.txt"], regex=True)
    ang_fail, _ = mesa_list([ci and f"{ci}/angle-radv-stoney-fails.txt"])
    _, ang_flake = mesa_list([ci and f"{ci}/angle-radv-stoney-flakes.txt"], regex=True)
    report = {"schema": "openbook-gfx-report/1", "dir": os.path.abspath(a.dir), "label": a.label, "parts": {}}
    facts = os.path.join(d, "facts.txt")
    if os.path.exists(facts):
        report["facts"] = open(facts, errors="replace").read().splitlines()[:60]
    all_results = {}
    for name in PARTS:
        pdir = os.path.join(d, name)
        meta = parts_meta.get(name, {})
        if not os.path.isdir(pdir) and not meta:
            continue
        if meta.get("skipped"):
            report["parts"][name] = {"part": name, "ran": False, "skipped": meta["skipped"]}
            continue
        if name == "egl":
            r, results, reasons = egl_part(pdir)
            r = summarise(r, results, reasons)
        elif name == "angle":
            r, results = angle_part(pdir)
            r = summarise(r, results, {})
        else:
            r, results = deqp_part(pdir, name, ci)
            run = os.path.join(pdir, "run")
            reasons = {c: qpa_reason(run, c) for c, s in results.items() if s in ("Fail", "Crash", "Timeout")}
            if name in ("vk", "vk14"):
                base = (radv_fail, radv_flake, [f"radv-fails.txt", f"radv-{a.radv_gpu}-fails.txt"])
            elif name == "gles-mesa":
                base = (si_fail, si_flake, [f"radeonsi-{a.radeonsi_gpu}-fails.txt"])
            else:
                base = (ang_fail, ang_flake, ["angle-radv-stoney-fails.txt"])
            r = summarise(r, results, reasons, *(base if ci else (None, None, ())))
        for k in ("rc", "seconds", "jobs", "amdgpu_events", "quick", "fraction"):
            if k in meta:
                r[k] = meta[k]
        report["parts"][name] = r
        all_results[name] = results
    if "vk" in all_results and "vk14" in all_results:
        v, w = all_results["vk"], all_results["vk14"]
        bad = ("Fail", "Crash", "Timeout")
        report["vk_vs_vk14"] = {
            "fail_only_in_vk11": sorted(c for c in v if v[c] in bad and w.get(c) not in bad),
            "fail_only_in_vk14": sorted(c for c in w if w[c] in bad and v.get(c) not in bad),
            "pass_only_in_vk14": sum(1 for c in w if w[c] == "Pass" and v.get(c) != "Pass"),
            "pass_only_in_vk11": sum(1 for c in v if v[c] == "Pass" and w.get(c) != "Pass"),
        }
    out = os.path.join(d, "gfx-report.json")
    json.dump(report, open(out, "w"), indent=1)
    lines = [f"# Graphics run: {a.label or os.path.basename(os.path.normpath(a.dir))}", ""]
    if ci:
        lines += [f"Mesa CI expectations: `{ci}` (RADV: {a.radv_gpu}, radeonsi: {a.radeonsi_gpu}, ANGLE: stoney).", ""]
    lines += ["| Part | Renderer | Cases | Pass | Fail | Crash | Timeout | Skip | Warn | Flake | Not run | Time | Mesa CI: our fails listed / new |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in report["parts"].items():
        if not r.get("ran"):
            lines.append(f"| {name} | | | | | | | | | | | | {r.get('skipped') or r.get('note', 'not run')} |")
            continue
        c = r.get("counts", {})
        mc = r.get("mesa_ci")
        mcs = f"{len(mc['our_failures_listed_by_mesa_ci'])} / {len(mc['our_failures_not_listed'])}" if mc else ""
        t = f"{r['seconds']} s" if "seconds" in r else ""
        lines.append(f"| {name} | {(r.get('renderer') or '')[:60]} | {r.get('total', 0)} | " +
                     " | ".join(str(c.get(s, 0)) for s in ("Pass", "Fail", "Crash", "Timeout", "Skip", "Warn", "Flake", "Missing"))
                     + f" | {t} | {mcs} |")
    for name, r in report["parts"].items():
        if r.get("failing_by_message"):
            lines += ["", f"## {name}: failures by message", ""]
            lines += [f"- {m['cases']} × {m['message']}" for m in r["failing_by_message"][:15]]
            if not r.get("mesa_ci"):
                lines += ["", "Failing cases:", ""] + [f"- `{f['case']}`: {f['status']}" for f in r["failing"][:40]]
            mc = r.get("mesa_ci")
            if mc:
                lines += ["", f"Mesa CI ({', '.join(mc['files'])}) lists {mc['mesa_ci_listed_failures_in_our_list']} "
                          f"failures among our cases; we pass {len(mc['mesa_ci_listed_failures_we_pass'])} of them."]
            if mc and mc["our_failures_not_listed"]:
                lines += ["", f"Not in Mesa CI's lists ({len(mc['our_failures_not_listed'])}):", ""]
                lines += [f"- `{c}`" for c in mc["our_failures_not_listed"][:40]]
    if "vk_vs_vk14" in report:
        x = report["vk_vs_vk14"]
        lines += ["", "## Vulkan 1.1 (android-strict, shipped) vs 1.4 (non-strict)", "",
                  f"- failing only with 1.1: {len(x['fail_only_in_vk11'])}; failing only with 1.4: "
                  f"{len(x['fail_only_in_vk14'])}",
                  f"- passing only with 1.4: {x['pass_only_in_vk14']}; passing only with 1.1: {x['pass_only_in_vk11']}"]
        lines += [f"- 1.4 only: `{c}`" for c in x["fail_only_in_vk14"][:20]]
    open(os.path.join(d, "gfx-report.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
