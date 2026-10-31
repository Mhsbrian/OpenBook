#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Find a node in a `uiautomator dump` and print the centre of its bounds ("x y"), or nothing.

usage: ui-find.py DUMP.xml KIND VALUE [--pkg PACKAGE]
  KIND  text    text or content-desc starts with VALUE (text fields are skipped)
        textx   text or content-desc is exactly VALUE (text fields are skipped)
        id      resource-id is VALUE (Compose test tags, with testTagsAsResourceId)
The package defaults to org.openbook.setup; --pkg '' searches every package.
"""
import re
import sys
import xml.etree.ElementTree as ET


def main():
    args = sys.argv[1:]
    pkg = "org.openbook.setup"
    if "--pkg" in args:
        i = args.index("--pkg")
        pkg = args[i + 1]
        del args[i:i + 2]
    path, kind, value = args
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return
    for n in root.iter("node"):
        if pkg and n.get("package") != pkg:
            continue
        labels = [n.get("text") or "", n.get("content-desc") or ""]
        if kind in ("text", "textx") and n.get("class") == "android.widget.EditText":
            continue  # a text field holds what was typed into it, e.g. the search for the row to tap
        if kind == "text":
            hit = any(lab.startswith(value) for lab in labels if lab)
        elif kind == "textx":
            hit = value in labels
        elif kind == "id":
            hit = n.get("resource-id") == value
        else:
            sys.exit(f"unknown kind {kind}")
        if not hit:
            continue
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.get("bounds") or "")
        if m:
            x1, y1, x2, y2 = map(int, m.groups())
            if x2 > x1 and y2 > y1:
                print((x1 + x2) // 2, (y1 + y2) // 2)
                return


if __name__ == "__main__":
    main()
