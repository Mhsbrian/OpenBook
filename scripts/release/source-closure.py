#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that OpenBook's build files in a source offer are closed (ANAL-341).

usage: source-closure.py REPO COMMIT FILES_LIST EXCLUDED_LIST

FILES_LIST is scripts/release/source-build-files.txt: git pathspecs packed from COMMIT. Every repository path that a
packed file names (a file or a directory of COMMIT) must be packed too, unless:
  - it is named only in comments, docstrings or prose (reported, not a failure), or
  - EXCLUDED_LIST (source-build-excluded.txt) lists it, as "<path><TAB><reason>", or a directory above it.
Prints one line per finding and exits 1 on any reference that is neither packed, comment-only nor excluded, and on
an exclusion nothing refers to any more. The match is textual on purpose: a path in a string is a dependency.
"""
import os
import re
import subprocess
import sys

TOKEN = re.compile(r"[A-Za-z0-9_.${}/-]*[A-Za-z0-9_-]/[A-Za-z0-9_./-]+")
PREFIX = re.compile(r"^(?:\$\{?(?:R|repo|REPO)\}?|/repo|\.)/")


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True).stdout


def comment_mask(name, text):
    """For each line: True when the whole line is comment or docstring/prose."""
    lines = text.split("\n")
    mask, in_doc, in_c = [], False, False
    py = name.endswith(".py")
    c = name.endswith((".c", ".h", ".cpp", ".bazel", ".bzl"))
    for line in lines:
        s = line.strip()
        is_c = False
        if py:
            q = s.count('"""') + s.count("'''")
            if in_doc:
                is_c = True
                if q % 2:
                    in_doc = False
            elif s.startswith(('"""', "'''", 'r"""')):
                is_c = True
                in_doc = q % 2 == 1
        if c:
            if in_c:
                is_c = True
                if "*/" in s:
                    in_c = False
            elif s.startswith("/*"):
                is_c, in_c = True, "*/" not in s
            elif s.startswith("//"):
                is_c = True
        if s.startswith("#") and not s.startswith("#!") and not s.startswith(("#include", "#define", "#if", "#endif", "#else")):
            is_c = True
        if name.endswith((".patch", ".txt", ".tsv", ".md", ".rules")) or os.path.basename(name) in ("BASE", "TREE", "PIN"):
            is_c = True  # data and prose: what they name is not run
        mask.append(is_c)
    return lines, mask


def main():
    repo, commit, files_list, excluded_list = sys.argv[1:5]
    tracked = git(repo, "ls-tree", "-r", "--name-only", commit).decode().split("\n")
    tracked = [t for t in tracked if t]
    tset = set(tracked)
    dirs = {t.rsplit("/", i)[0] for t in tracked for i in range(1, t.count("/") + 1)}
    spec = [l.split("#")[0].strip() for l in open(files_list)]
    spec = [s.rstrip("/") for s in spec if s]
    packed = {t for t in tracked if any(t == s or t.startswith(s + "/") for s in spec)}
    excluded = {}
    for l in open(excluded_list):
        l = l.rstrip("\n")
        if l.strip() and not l.lstrip().startswith("#"):
            p, _, why = l.partition("\t")
            excluded[p.strip().rstrip("/")] = why.strip()

    def covered(p):
        return p in packed or any(i.startswith(p + "/") for i in packed)

    def excluded_by(p):
        return next((e for e in excluded if p == e or p.startswith(e + "/")), None)

    code, prose, used = {}, {}, set()
    for f in sorted(packed):
        data = git(repo, "show", f"{commit}:{f}")
        if b"\0" in data[:8192]:
            continue
        lines, mask = comment_mask(f, data.decode("utf-8", "replace"))
        here = os.path.dirname(f)
        for line, is_c in zip(lines, mask):
            line = line.replace("$S/", "scripts/installer/").replace("{HERE}/", here + "/").replace("$HERE/", here + "/")
            for m in TOKEN.finditer(line):
                raw = PREFIX.sub("", m.group()).rstrip(".,;:)'\"")
                for cand in {raw.strip("/"), os.path.normpath(os.path.join(here, raw))}:
                    if cand not in tset and cand not in dirs:
                        continue
                    if covered(cand):
                        continue
                    (prose if is_c else code).setdefault(cand, set()).add(f)
        for m in re.finditer(r'SourceFileLoader\([^,]+,\s*f?"\{HERE\}/([^"]+)"', "\n".join(lines)):
            cand = os.path.join(here, m.group(1))
            if not covered(cand):
                code.setdefault(cand, set()).add(f)
    missing = stale = 0
    for p in sorted(code):
        e = excluded_by(p)
        if e:
            used.add(e)
            print(f"excluded  {p}  <- {', '.join(sorted(code[p]))}  ({excluded[e]})")
        else:
            missing += 1
            print(f"MISSING   {p}  <- {', '.join(sorted(code[p]))}")
    for p in sorted(set(prose) - set(code)):
        print(f"comment   {p}  <- {', '.join(sorted(prose[p]))}")
    for e in sorted(set(excluded) - used):
        stale += 1
        print(f"STALE     {e}  (excluded, but no packed file refers to it)")
    print(f"source-closure: {len(packed)} files packed; {len(code)} referenced from code, {len(code) - missing} of them "
          f"excluded with a reason; {len(set(prose) - set(code))} named only in comments; {missing} missing, {stale} stale")
    bad = missing + stale
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
