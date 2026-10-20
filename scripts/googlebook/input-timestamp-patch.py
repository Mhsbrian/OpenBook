#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact-build local adaptation of the open-source HardwareStateConverter fix.

No proprietary binaries are distributed. Refuse any other build. Replace only
the redundant MSC reset after SYN_REPORT; explicit MSC=0 and reset() still work.
This implements frameworks/native/0002 without replacing Ruby's framework ABI.
"""
import hashlib
from pathlib import Path
import argparse

SOURCE_SHA256 = "e27014ec1e2e4d611cdd6df2c1175d86d679d1353ee970f190e831953fbcb3e4"
# Translate the virtual address through the ELF executable segment below.
VADDR = 0x24CB58
ORIGINAL = bytes.fromhex("41 c7 47 40 00 00 00 00")
REPLACEMENT = b"\x90" * len(ORIGINAL)


def patch(data):
    import struct
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError("Unknown libinputflinger build; no patch applied")
    if data[:7] != b"\x7fELF\x02\x01\x01" or struct.unpack_from("<H", data, 18)[0] != 62:
        raise ValueError("Requires ELF64 x86_64")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    width, count = struct.unpack_from("<HH", data, 54)
    offsets = []
    for i in range(count):
        kind, flags, off, va, _, filesz, _, _ = struct.unpack_from("<IIQQQQQQ", data, phoff + i * width)
        if kind == 1 and flags & 1 and va <= VADDR and VADDR + len(ORIGINAL) <= va + filesz:
            offsets.append(off + VADDR - va)
    if len(offsets) != 1:
        raise ValueError("Instruction is not in exactly one executable segment")
    off = offsets[0]
    if data[off:off + len(ORIGINAL)] != ORIGINAL:
        raise ValueError("Instruction preimage mismatch")
    return data[:off] + REPLACEMENT + data[off + len(ORIGINAL):], off


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path); p.add_argument("output", type=Path)
    args = p.parse_args()
    result, offset = patch(args.source.read_bytes())
    with args.output.open("xb") as f:
        f.write(result)
    print(f"Patched eight bytes at file offset {offset:#x}; sha256={hashlib.sha256(result).hexdigest()}")
