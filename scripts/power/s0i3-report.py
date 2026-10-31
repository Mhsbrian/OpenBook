#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare S0i3 results (ANAL-178): OpenBook's hardware-check JSONs (hwcheck-NNN.json, schema openbook-hwcheck/5
or /6, from the power check on the live stick) and summaries from the laptop's own Linux (summary.json, schema
openbook-linux-s2idle/1, scripts/power/linux-s2idle.py). Prints a Markdown report and writes JSON (--json):

  - every cycle: where it ran, the change made before it, S0i3 yes/no, hardware sleep, the SMU's verdict, the idle
    mask amd_pmc logged at S0i3 entry, the deepest cpuidle state all CPUs used, PCI functions not in D3 at entry;
  - the first OpenBook step that reached S0i3, if any (the change that fixed it);
  - against the first Linux cycle that reached S0i3: idle-mask bits that differ from each failing OpenBook cycle,
    and PCI functions awake at S0i3 entry on one side only (by vendor:device and driver, so bus numbers may differ).

usage: s0i3-report.py FILE [FILE...] [--json OUT]
"""
import argparse
import json
import os
import re
import sys


def mask(v):
    try:
        return int(v, 16) if v else None
    except ValueError:
        return None


def deepest(cpuidle):
    used = [c for c in cpuidle or [] if c.get("entries", 0) > 0]
    if not used:
        return None
    top = max(used, key=lambda c: (c.get("latency_us") or 0))
    return f"{top.get('name')} on {top.get('cpus')} CPU(s)"


def awake_key(entry):
    """'0000:65:00.2 1022:17e0 D0 - skip_bus_pm' (probe) or the snapshot module's raw line (Linux)."""
    parts = entry.split()
    ident = next((p for p in parts if re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{4}", p)), "?")
    drv = parts[parts.index("driver") + 1] if "driver" in parts else (parts[3] if len(parts) > 3 else "?")
    return f"{ident} {drv}"


def load(path):
    j = json.load(open(path))
    out = []
    if j.get("schema", "").startswith("openbook-hwcheck/"):
        cycles = j.get("sleep_cycles") or []
        if not cycles and isinstance(j.get("sleep_test"), dict) and j["sleep_test"].get("ran"):
            st = j["sleep_test"]  # schema 5 and older: one cycle, residency only
            cycles = [{"cycle": 0, "step": "baseline", "s0i3": (st.get("s0ix_residency_us") or 0) > 0,
                       "s0ix_residency_us": st.get("s0ix_residency_us")}]
        dm = path[:-5] + "-dmesg.txt" if path.endswith(".json") else None
        masks = re.findall(r"SMU idlemask s0i3: (0x[0-9a-fA-F]+)", open(dm, errors="replace").read()) \
            if dm and os.path.exists(dm) else []
        for c in cycles:
            if not c.get("idlemask_entry") and len(masks) == len(cycles):  # older JSON: the cycle's mask from dmesg
                c["idlemask_entry"] = masks[c.get("cycle", 0)]
            out.append({"source": f"OpenBook {path.split('/')[-1]}", "kind": "openbook", "change": c.get("step"),
                        "detail": c.get("bound") or [], "s0i3": c.get("s0i3"),
                        "hw_sleep_us": c.get("last_hw_sleep_us"), "smu": (c.get("smu") or {}).get("last_s0i3"),
                        "idlemask": c.get("idlemask_entry") or None, "deepest_cstate": deepest(c.get("cpuidle")),
                        "not_met_us": (c.get("smu") or {}).get("not_met_us") or {},
                        "awake": (c.get("snapshot") or {}).get("not_in_d3") or [],
                        "awake_summary": (c.get("snapshot") or {}).get("summary")})
    elif j.get("schema") == "openbook-linux-s2idle/1":
        for p in j.get("phases", []):
            for i, c in enumerate(p.get("cycles", [])):
                out.append({"source": f"Linux {j.get('facts', {}).get('kernel', '')}", "kind": "linux",
                            "change": p["phase"] + (f" #{i}" if i else ""), "detail": p.get("unloaded") or [],
                            "s0i3": c.get("s0i3"), "hw_sleep_us": c.get("last_hw_sleep_us"),
                            "smu": (c.get("smu") or {}).get("last_s0i3"), "idlemask": c.get("idlemask_entry"),
                            "deepest_cstate": deepest(c.get("cpuidle")),
                            "not_met_us": (c.get("smu") or {}).get("not_met_us") or {},
                            "awake": c.get("snapshot_not_in_d3") or [], "awake_summary": c.get("snapshot_summary")})
    else:
        sys.exit(f"{path}: unknown schema {j.get('schema')!r}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json")
    a = ap.parse_args()
    cycles = [c for f in a.files for c in load(f)]
    ob = [c for c in cycles if c["kind"] == "openbook"]
    lx = [c for c in cycles if c["kind"] == "linux"]
    fixed = next((c for c in ob if c["s0i3"]), None)
    ref = next((c for c in lx if c["s0i3"]), None)
    comparisons = []
    if ref:
        rm, rk = mask(ref["idlemask"]), {awake_key(e) for e in ref["awake"]}
        for c in ob:
            if c["s0i3"] is not False:  # only cycles that ran on AMD hardware and missed S0i3
                continue
            cm, ck = mask(c["idlemask"]), {awake_key(e) for e in c["awake"]}
            comparisons.append({
                "openbook": f"{c['source']} / {c['change']}", "linux": f"{ref['source']} / {ref['change']}",
                "idlemask_xor": f"{cm ^ rm:#010x}" if cm is not None and rm is not None else None,
                "bits_only_openbook": [b for b in range(32) if cm is not None and rm is not None and (cm >> b) & 1 and not (rm >> b) & 1],
                "bits_only_linux": [b for b in range(32) if cm is not None and rm is not None and (rm >> b) & 1 and not (cm >> b) & 1],
                "awake_only_openbook": sorted(ck - rk) if ref["awake"] and c["awake"] else None,
                "awake_only_linux": sorted(rk - ck) if ref["awake"] and c["awake"] else None})
    verdict = {"openbook_reached_s0i3": bool(fixed), "first_fixing_step": fixed and fixed["change"],
               "linux_reached_s0i3": bool(ref) if lx else None,
               "linux_phases_without_s0i3": [c["change"] for c in lx if c["s0i3"] is False]}
    rep = {"schema": "openbook-s0i3-report/1", "cycles": cycles, "verdict": verdict, "comparisons": comparisons}
    if a.json:
        json.dump(rep, open(a.json, "w"), indent=1)
    yn = {True: "yes", False: "NO", None: "?"}
    print("| Where | Change before the cycle | S0i3 | HW sleep (us) | SMU | Idle mask at entry | Deepest C-state | Not in D3 at entry |")
    print("|---|---|---|---|---|---|---|---|")
    for c in cycles:
        print(f"| {c['source']} | {c['change']}{': ' + ', '.join(c['detail']) if c['detail'] else ''} | {yn[c['s0i3']]} | "
              f"{c['hw_sleep_us']} | {c['smu']} | {c['idlemask']} | {c['deepest_cstate']} | {c['awake_summary'] or '-'} |")
    print(f"\nVerdict: {json.dumps(verdict)}")
    for x in comparisons:
        print(f"\n{x['openbook']} vs {x['linux']}: idle mask XOR {x['idlemask_xor']} (bits only OpenBook "
              f"{x['bits_only_openbook']}, only Linux {x['bits_only_linux']}); awake only on OpenBook: "
              f"{x['awake_only_openbook']}; only on Linux: {x['awake_only_linux']}")


if __name__ == "__main__":
    main()
