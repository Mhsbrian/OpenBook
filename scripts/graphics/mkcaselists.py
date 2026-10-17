#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Make ANAL-177's dEQP case lists: fixed, reproducible subsets of the Android CTS mustpass lists in AOSP's
external/deqp (android/cts/main), sized so the whole graphics run fits in about 15-30 minutes on the G14.

Per suite, the source is the union of the dated mustpass lists a new Android 17 device runs
(<suite>-main-YYYY-03-01.txt for every year in the tree; for Vulkan, the vk-main-YYYY-03-01/ directories), in
file order. The subset is every STRIDE-th case starting at OFFSET (stratified: each source file is sampled on its
own, so every area keeps its share), plus the ALWAYS patterns (driver identity, info and smoke groups), minus the
EXCLUDE patterns (window-system tests that the surfaceless deqp-binary cannot run). Same tree + same settings =
same lists, byte for byte; caselists.json records the settings, counts and sha256 of every source and output.

ANGLE end2end (--angle-expectations, Android 17's CTS file external/angle/android/cts/angle_end2end_tests_expectations.txt):
the CTS runs every test that file marks PASS and skips the rest ("* = SKIP"). angle_end2end_tests_expectations.txt here
keeps every STRIDE-th PASS line and the same catch-all SKIP, so the helper app runs exactly that subset.

usage: mkcaselists.py MUSTPASS_DIR OUT_DIR [--stride SUITE=N ...] [--offset N] [--angle-expectations FILE]
"""
import argparse
import fnmatch
import glob
import hashlib
import json
import os
import re

# suite: (source globs relative to MUSTPASS_DIR, default stride, always-include patterns, exclude patterns)
SUITES = {
    "egl": (["egl-main-20??-03-01.txt"], 3, ["dEQP-EGL.info.*"], []),
    "gles2": (["gles2-main-20??-03-01.txt"], 4, ["dEQP-GLES2.info.*"], []),
    "gles3": (["gles3-main-20??-03-01.txt"], 8, ["dEQP-GLES3.info.*"], []),
    "gles31": (["gles31-main-20??-03-01.txt"], 8, ["dEQP-GLES31.info.*"], []),
    # dEQP-VK.info.* records the device, its properties and formats; api.smoke draws a triangle; version_check
    # reports the API version the driver advertises (1.1 under android-strict, 1.4 without).
    "vk": (["vk-main-20??-03-01/*.txt"], 30,
           ["dEQP-VK.info.*", "dEQP-VK.api.smoke.*", "dEQP-VK.api.version_check.*", "dEQP-VK.api.info.*",
            "dEQP-VK.api.device_init.create_device", "dEQP-VK.api.device_init.create_instance_name_version"],
           # WSI needs a native window (the surfaceless platform has none); the desktop itself exercises RADV's
           # Android swapchain path, and ANAL-176's amd-android-hwtest covers its deferred binding.
           ["dEQP-VK.wsi.*"]),
}


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mustpass")
    ap.add_argument("out")
    ap.add_argument("--stride", action="append", default=[], help="SUITE=N (default per suite)")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--angle-expectations")
    a = ap.parse_args()
    strides = {k: v[1] for k, v in SUITES.items()}
    strides["angle"] = 2
    for s in a.stride:
        k, _, n = s.partition("=")
        if (k not in SUITES and k != "angle") or not n.isdigit() or int(n) < 1:
            ap.error(f"bad --stride {s}")
        strides[k] = int(n)
    os.makedirs(a.out, exist_ok=True)
    meta = {"schema": "openbook-gfx-caselists/1", "mustpass": os.path.abspath(a.mustpass), "offset": a.offset,
            "suites": {}}
    for suite, (globs, _, always, exclude) in SUITES.items():
        stride = strides[suite]
        srcs = sorted(p for g in globs for p in glob.glob(os.path.join(a.mustpass, g)))
        if not srcs:
            raise SystemExit(f"{suite}: no source lists under {a.mustpass}")
        alw = re.compile("|".join(fnmatch.translate(p) for p in always)) if always else None
        exc = re.compile("|".join(fnmatch.translate(p) for p in exclude)) if exclude else None
        seen, out, total, excluded = set(), [], 0, 0
        for src in srcs:
            cases = [l.strip() for l in open(src) if l.strip() and not l.startswith("#")]
            kept = 0
            for i, c in enumerate(cases):
                if c in seen:
                    continue
                seen.add(c)
                total += 1
                if exc and exc.match(c):
                    excluded += 1
                    continue
                if kept % stride == a.offset % stride or (alw and alw.match(c)):
                    out.append(c)
                kept += 1
        path = os.path.join(a.out, f"{suite}.txt")
        open(path, "w").write("\n".join(out) + "\n")
        meta["suites"][suite] = {
            "file": f"{suite}.txt", "cases": len(out), "source_cases": total, "excluded": excluded, "stride": stride,
            "always": always, "exclude": exclude, "sha256": sha(path),
            "sources": {os.path.relpath(s, a.mustpass): sha(s) for s in srcs},
        }
        print(f"{suite}: {len(out)} of {total} cases (stride {stride}, {excluded} excluded) -> {path}")
    if a.angle_expectations:
        lines = open(a.angle_expectations).read().splitlines()
        passing = [l for l in lines if l.rstrip().endswith("= PASS")]
        catch_all = [l for l in lines if re.fullmatch(r"\S+ : \* = SKIP", l.strip())]
        if not passing or len(catch_all) != 1:
            raise SystemExit(f"{a.angle_expectations}: expected PASS lines and one '* = SKIP' line")
        keep = [l for i, l in enumerate(passing) if i % strides["angle"] == a.offset % strides["angle"]]
        head = []  # the licence header, up to the format note
        for l in lines:
            head.append(l)
            if "deqp_support/README.md" in l:
                break
        path = os.path.join(a.out, "angle_end2end_tests_expectations.txt")
        open(path, "w").write("\n".join(head + ["", f"// OpenBook ANAL-177: one in {strides['angle']} of the tests the "
                                                 "Android 17 CTS list marks PASS; everything else is skipped.", ""] + keep +
                                         ["", catch_all[0]]) + "\n")
        meta["suites"]["angle"] = {"file": os.path.basename(path), "cases": len(keep), "source_cases": len(passing),
                                   "stride": strides["angle"], "sha256": sha(path),
                                   "sources": {os.path.basename(a.angle_expectations): sha(a.angle_expectations)}}
        print(f"angle: {len(keep)} of {len(passing)} end2end tests (stride {strides['angle']}) -> {path}")
    json.dump(meta, open(os.path.join(a.out, "caselists.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
