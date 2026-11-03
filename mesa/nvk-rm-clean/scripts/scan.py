#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Provenance gate for this tree. Exit 1 when any file (except this script) has a line that ties
behaviour to another vendor's closed userspace driver: a library name of it, a section-tagged binary
address, a binary-analysis or capture method, or a description of what that driver does.
(llvm-objdump on this tree's own build outputs is allowed.)
usage: scripts/scan.py [ROOT]   (default: the repository root)"""
import re, sys
from pathlib import Path
RULES = [
    ("library", r"libnvidia-[a-z0-9-]+|libnvcuvid|libcuda\b|libEGL_nvidia|libGLX_nvidia|libGLESv2_nvidia|nvidia_icd|eglcore|glcore|libnvoptix"),
    ("address", r"\b[EG] (?:0x)?[0-9a-f]{5,}\b|\bELF (?:0x)?[0-9a-f]{4,}\b"),
    ("method", r"disassembl|(?<!llvm-)objdump|decompil|reverse[- ]engineer|ghidra|\bRM traces?\b|runtime (?:trace|observation)|push-?buffer capture of|nvcap\.py|stock-userd|fence-tracing"),
    ("describes", r"\bstock\b|proprietary (?:driver|compiler|userspace|librar)|NVIDIA'?s (?:own )?(?:compiler|userspace|Vulkan driver|own driver)"),
]
RX = [(n, re.compile(p, re.I)) for n, p in RULES]
root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1])
hits = 0
for f in sorted(root.rglob("*")):
    if not f.is_file() or ".git" in f.parts or f.name == "scan.py" or f.suffix in (".spv",):
        continue
    try:
        text = f.read_text(errors="strict")
    except (UnicodeDecodeError, OSError):
        continue
    for i, line in enumerate(text.splitlines(), 1):
        kinds = [n for n, r in RX if r.search(line)]
        if kinds:
            hits += 1
            print(f"{f.relative_to(root)}:{i}: {','.join(kinds)}")
print(f"scan: {hits} hit(s)")
sys.exit(1 if hits else 0)
