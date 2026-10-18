#!/usr/bin/env python3
"""For each aconfig flag in a list, print what our AOSP tree says about it: the declaration (namespace,
purpose, description, bug) and the non-test source files that read it. Input for the ANAL-204 triage
(docs/googlebook-flags.md).

usage: flag-facts.py FLAGS_TSV AOSP_SRC > facts.tsv
  FLAGS_TSV: evidence/2026-10-17-gbos-ui/flags/googlebook-on-openbook-off.tsv (only rows marked `declared`
  are read) or any TSV whose first column is <package>.<flag> and fourth column the declaring .aconfig.

A flag is read through its Java/Kotlin accessor (`Flags.enableFoo()`), a wrapper enum such as
DesktopExperienceFlags.ENABLE_FOO, or the C++/Rust accessor (`flags::enable_foo()`). The search is by
name, so two packages that declare the same flag name share their readers; check those by hand.
`gating` counts readers outside the flag registries (REGISTRY); 0 means nothing in this tree acts on the flag.
"""
import re
import subprocess
import sys
from pathlib import Path

SEARCH = ["frameworks", "packages", "system", "hardware", "build/make", "external/perfetto"]
# Files that list or wrap flags without gating behaviour on them.
REGISTRY = {"DesktopExperienceFlags.java", "DesktopModeFlags.java", "FlagManager.cpp", "FlagManager.h",
            "FlagDependencies.kt"}
TEST = re.compile(r"(^|/)(tests?|testing|testutils|robolectric|multivalentTests|benchmarks?)(/|$)"
                  r"|Test[A-Za-z]*\.(java|kt)$|_test\.(cpp|cc|rs)$|/fakes?/|Fake[A-Z]\w*\.kt$")


def camel(snake):
    p = snake.split("_")
    return p[0] + "".join(w[:1].upper() + w[1:] for w in p[1:])


def decl(src, path, pkg, name):
    text = (Path(src) / path).read_text()
    if not re.search(rf'^package: "{re.escape(pkg)}"', text, re.M):
        return None
    body = next((b for b in re.findall(r"^flag\s*\{(.*?)^\}", text, re.S | re.M)
                 if re.search(rf'^\s*name: "{re.escape(name)}"', b, re.M)), None)
    if body is None:
        return None
    get = lambda k: (re.search(rf'^\s*{k}: "((?:[^"\\]|\\.)*)"', body, re.M) or [None, ""])[1]
    desc = " ".join(re.findall(r'description:\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', body, re.S))
    desc = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', desc))
    purpose = (re.search(r"purpose:\s*(\w+)", body) or [None, "PURPOSE_FEATURE(default)"])[1]
    fixed = "yes" if re.search(r"is_fixed_read_only:\s*true", body) else ""
    exported = "yes" if re.search(r"is_exported:\s*true", body) else ""
    return dict(namespace=get("namespace"), bug=get("bug"), desc=desc.replace("\t", " "),
                purpose=purpose.replace("PURPOSE_", ""), fixed=fixed, exported=exported)


def main():
    tsv, src = sys.argv[1], sys.argv[2]
    rows = []
    for line in Path(tsv).read_text().splitlines()[1:]:
        f = line.split("\t")
        if len(f) >= 4 and f[2] == "declared":
            pkg, name = f[0].rsplit(".", 1)
            rows.append((f[0], pkg, name, f[1], f[3]))
    pats = {}
    for full, pkg, name, *_ in rows:
        for p in (camel(name), name.upper(), name):
            pats.setdefault(p, set()).add(name)
    alt = "|".join(sorted(map(re.escape, pats), key=len, reverse=True))
    r = subprocess.run(["rg", "-o", "--no-heading", "-n", "-tjava", "-tkotlin", "-tcpp", "-trust", "-tc",
                        rf"\b({alt})\b", *SEARCH], cwd=src, capture_output=True, text=True)
    readers = {}
    for line in r.stdout.splitlines():
        path, _, tok = line.split(":", 2)
        if TEST.search(path):
            continue
        for name in pats.get(tok, ()):
            readers.setdefault(name, set()).add(path)
    print("flag\tcontainer\tdecl\tnamespace\tpurpose\tfixed_ro\texported\tbug\tdescription\treaders\tgating\treader_files")
    for full, pkg, name, cont, path in rows:
        d = decl(src, path, pkg, name) or dict(namespace="?", bug="", desc="(declaration not parsed)",
                                               purpose="?", fixed="", exported="")
        files = sorted(readers.get(name, ()))
        gating = [f for f in files if f.rsplit("/", 1)[-1] not in REGISTRY]
        print("\t".join([full, cont, path, d["namespace"], d["purpose"], d["fixed"], d["exported"], d["bug"],
                         d["desc"], str(len(files)), str(len(gating)), " ".join(files)]))


if __name__ == "__main__":
    main()
