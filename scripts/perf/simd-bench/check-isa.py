#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check from the disassembly that simd-bench's kernels use the instructions they are meant to measure.

Same source alone doesn't prove NEON coverage: the compiler could scalarize a kernel on one architecture. Using an
xmm register proves nothing on x86_64 either, since scalar float code (mulss) uses them too. So each baseline kernel
must contain the packed operations its work needs, on each architecture (REQUIRED: e.g. triad_f32 needs a packed float
multiply and add, fmul/fadd on .4s lanes or mulps/addps), and:
  - the scalar control (k_triad_scalar) has no packed float arithmetic;
  - k_aes128 and k_crc32c use the architecture's AES and CRC32C instructions.
Prints a JSON report; exit 1 if any assertion fails.

usage: check-isa.py --objdump LLVM_OBJDUMP BINARY...    (the architecture is read from the disassembly header)
"""
import argparse
import json
import re
import subprocess
import sys

# Packed operations each baseline kernel must contain; every pattern must match at least one instruction. arm64
# patterns require a multi-lane arrangement (.4s, .8h, .16b ...), x86_64 ones a packed mnemonic (v-prefixed under AVX).
FP4 = r"v\d+\.4s"
REQUIRED = {
    "k_triad_f32": {"aarch64": [rf"\bfmul\s+{FP4}", rf"\bfadd\s+{FP4}"], "x86_64": [r"\bv?mulps\b", r"\bv?addps\b"]},
    "k_dot_f32": {"aarch64": [rf"\bfmul\s+{FP4}", rf"\bfadd\s+{FP4}"], "x86_64": [r"\bv?mulps\b", r"\bv?addps\b"]},
    "k_dot_i8": {"aarch64": [r"\b(smull2?|smlal2?|mul|mla)\s+v\d+\.8h", r"\b(saddw2?|sadalp|add|saddl2?)\s+v\d+\.4s"],
                 "x86_64": [r"\bv?pmullw\b|\bv?pmaddwd\b|\bv?pmaddubsw\b", r"\bv?paddd\b"]},
    "k_blur_u8": {"aarch64": [r"\b(uaddw2?|uaddl2?|ushll2?|add|shl|mla)\s+v\d+\.8h", r"\b(rshrn2?|shrn2?|uzp1|xtn2?|uqxtn2?)\s+v\d+\.(8b|16b)"],
                  "x86_64": [r"\bv?paddw\b", r"\bv?packuswb\b|\bv?pshufb\b"]},
    "k_minmax_f32": {"aarch64": [rf"\bfminnm\s+{FP4}|\bfmin\s+{FP4}", rf"\bfmaxnm\s+{FP4}|\bfmax\s+{FP4}"],
                     "x86_64": [r"\bv?minps\b", r"\bv?maxps\b"]},
    "k_swizzle_u8": {"aarch64": [r"\btbl\s+v\d+\.16b|\brev32\s+v\d+\.16b"], "x86_64": [r"\bv?pshufb\b"]},
}
BASELINE = list(REQUIRED)
SCALAR = "k_triad_scalar"
OPTIONAL = {"k_crc32c": {"aarch64": r"\bcrc32cx\b", "x86_64": r"\bcrc32q\b"},
            "k_aes128": {"aarch64": r"\baese\b", "x86_64": r"\baesenc\b"}}
VECTOR = {"aarch64": re.compile(r"\b[vq]\d+(\.\d*[bhsd])?\b"),
          "x86_64": re.compile(r"%[xy]mm\d+")}
# Packed (not scalar) float arithmetic, which the scalar control must not contain.
PACKED_FP = {"aarch64": re.compile(r"\bf(add|mul|sub)\s+v\d+\.\d*s"),
             "x86_64": re.compile(r"\b(v?)(add|mul|sub)ps\b")}


def functions(text):
    """{name: [instruction lines]} from llvm-objdump -d output."""
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^[0-9a-f]+ <([^>]+)>:$", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur and re.match(r"^\s+[0-9a-f]+:", line):
            out[cur].append(" ".join(line.split(":", 1)[1].split()))  # "mnemonic operands", address dropped
    return out


def arch_of(text):
    m = re.search(r"file format elf64-(\S+)", text)
    fmt = m.group(1) if m else ""
    if "aarch64" in fmt or "littleaarch64" in fmt:
        return "aarch64"
    if "x86-64" in fmt:
        return "x86_64"
    raise SystemExit(f"unknown file format {fmt!r}")


def check(text):
    arch = arch_of(text)
    fns = functions(text)
    report, failures = {"arch": arch, "kernels": {}}, []
    for name in BASELINE + [SCALAR] + list(OPTIONAL):
        insns = fns.get(name)
        if insns is None:
            failures.append(f"{arch}: {name} not found (inlined or renamed?)")
            continue
        vec = sum(1 for i in insns if VECTOR[arch].search(i))
        packed = sum(1 for i in insns if PACKED_FP[arch].search(i))
        entry = {"instructions": len(insns), "vector": vec, "packed_fp": packed}
        if name in OPTIONAL:
            entry["isa"] = sum(1 for i in insns if re.search(OPTIONAL[name][arch], i))
            if not entry["isa"]:
                failures.append(f"{arch}: {name} has no {OPTIONAL[name][arch]} instruction")
        elif name == SCALAR:
            if packed:
                failures.append(f"{arch}: {SCALAR} has {packed} packed float instructions (vectorized)")
        else:
            missing = [pat for pat in REQUIRED[name][arch] if not any(re.search(pat, i) for i in insns)]
            entry["missing_packed"] = missing
            if missing:
                failures.append(f"{arch}: {name} lacks packed {missing} (scalarized?)")
        report["kernels"][name] = entry
    return report, failures


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--objdump", default="llvm-objdump")
    ap.add_argument("binaries", nargs="+")
    a = ap.parse_args()
    reports, failures = {}, []
    for b in a.binaries:
        text = subprocess.run([a.objdump, "-d", "--no-show-raw-insn", b], capture_output=True, text=True,
                              check=True).stdout
        r, f = check(text)
        reports[b.rsplit("/", 1)[-1]] = r
        failures += f
    print(json.dumps({"ok": not failures, "failures": failures, "binaries": reports}, indent=1))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
