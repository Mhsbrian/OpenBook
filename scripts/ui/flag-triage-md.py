#!/usr/bin/env python3
"""Render the ANAL-204 flag triage TSV as Markdown tables, one per decision, for docs/googlebook-flags.md.

  scripts/ui/flag-triage-md.py device/anybook/common/desktop/release/googlebook-triage.tsv > table.md
"""
import sys
from collections import Counter

GROUPS = {"1": "window shadows and resizing", "2": "blur", "3": "taskbar and desktop behaviour",
          "4": "SystemUI, Launcher and Settings polish", "5": "remaining applicable bugfixes",
          "6": "internal refactors and performance"}


def main():
    lines = open(sys.argv[1]).read().splitlines()
    ix = {h: i for i, h in enumerate(lines[0].split("\t"))}
    rows = [l.split("\t") for l in lines[1:]]
    c = Counter((r[ix["decision"]], r[ix["group"]]) for r in rows)
    print(f"{len(rows)} flags: " + ", ".join(f"{n} {d}" + (f" (group {g})" if g != "-" else "")
                                            for (d, g), n in sorted(c.items())) + ".\n")
    for dec, title in [("enable", "Enabled"), ("defer", "Deferred"), ("skip", "Skipped")]:
        sel = [r for r in rows if r[ix["decision"]] == dec]
        print(f"### {title} ({len(sel)})\n")
        print("| Group | Flag | Category | Readers | Reason |\n|---|---|---|---|---|")
        for r in sorted(sel, key=lambda r: (r[ix["group"]], r[ix["category"]], r[0])):
            g = r[ix["group"]]
            print(f"| {g if g != '-' else ''} | `{r[0]}` | {r[ix['category']]} | {r[ix['readers']]} | {r[ix['reason']]} |")
        print()


if __name__ == "__main__":
    main()
