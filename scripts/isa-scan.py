#!/usr/bin/env python3
"""Scan every x86-64 ELF under the given roots for instructions that a target CPU lacks.

Disassembles with GNU objdump and counts mnemonics from ISA extensions that AMD Zen 4
(e.g. Ryzen 9 7950X, Ryzen 7040/8040) does NOT implement, plus which of those Zen 5 adds.
Usage: isa-scan.py OUT.json ROOT [ROOT...]
"""
import json, os, re, subprocess, sys
from concurrent.futures import ProcessPoolExecutor

# extension -> (regex on objdump mnemonic field, present on Zen 5?)
EXTS = {
    'AVX-VNNI':       (r'^\{vex\} vpdp(bu|ws)sds?\b', True),
    'AVX-IFMA':       (r'^\{vex\} vpmadd52[lh]uq\b', False),
    'AVX-VNNI-INT8':  (r'^vpdpb(ss|su|uu)ds?\b', False),
    'AVX-VNNI-INT16': (r'^vpdpw(su|us|uu)ds?\b', False),
    'AVX-NE-CONVERT': (r'^(vbcstne(bf16|sh)2ps|vcvtne[eo](bf16|ph)2ps|\{vex\} vcvtneps2bf16)\b', False),
    'CMPCCXADD':      (r'^cmpn?[a-z]{1,2}xadd\b', False),
    'SERIALIZE':      (r'^serialize\b', False),
    'MOVDIRI':        (r'^movdir(i|64b)\b', True),
    'WAITPKG':        (r'^(umwait|tpause|umonitor)\b', False),
    'KEYLOCKER':      (r'^(aes(enc|dec)(wide)?(128|256)kl|loadiwkey|encodekey(128|256))\b', False),
    'SHA512/SM3/SM4': (r'^(vsha512|vsm3|vsm4)', False),
    'HRESET':         (r'^hreset\b', False),
    'UINTR':          (r'^(uiret|testui|clui|stui|senduipi)\b', False),
    'PREFETCHI':      (r'^prefetchit[01]\b', True),
    'AMX':            (r'^(tileloadd|tilestored|tdpb[su][su]d|tdpbf16ps|ldtilecfg|sttilecfg|tilezero|tilerelease)\b', False),
    'ENQCMD':         (r'^enqcmds?\b', False),
    'PTWRITE':        (r'^ptwrite\b', False),
    'APX':            (r'^\{rex2\}|\b(r1[6-9]|r2[0-9]|r3[01])\b', False),
}
RX = {k: re.compile(v[0]) for k, v in EXTS.items()}

def is_x86_64_elf(path):
    try:
        with open(path, 'rb') as f:
            h = f.read(20)
        return len(h) == 20 and h[:4] == b'\x7fELF' and h[4] == 2 and h[18:20] == b'\x3e\x00'
    except OSError:
        return False

def scan(path):
    hits = {}
    try:
        p = subprocess.run(['objdump', '-d', '--no-show-raw-insn', '-w', path],
                           capture_output=True, text=True, errors='replace', timeout=900)
    except subprocess.TimeoutExpired:
        return path, {'_error': 'timeout'}
    for line in p.stdout.splitlines():
        parts = line.split('\t', 1)
        if len(parts) != 2 or not parts[0].rstrip().endswith(':'):
            continue
        ins = parts[1].strip()
        for k, rx in RX.items():
            if rx.search(ins):
                hits[k] = hits.get(k, 0) + 1
    return path, hits

def main():
    out, roots = sys.argv[1], sys.argv[2:]
    files = []
    for r in roots:
        for d, _, fs in os.walk(r):
            for f in fs:
                p = os.path.join(d, f)
                if not os.path.islink(p) and is_x86_64_elf(p):
                    files.append(p)
    res = {}
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        for path, hits in ex.map(scan, files, chunksize=4):
            if hits:
                res[path] = hits
    summary = {}
    for hits in res.values():
        for k in hits:
            if k.startswith('_'):
                continue
            summary.setdefault(k, {'files': 0, 'insns': 0, 'on_zen5': EXTS[k][1]})
            summary[k]['files'] += 1
            summary[k]['insns'] += hits[k]
    json.dump({'scanned_elf_files': len(files), 'summary': summary, 'files': res}, open(out, 'w'), indent=1)
    print(f'scanned {len(files)} x86-64 ELF files; {len(res)} contain non-Zen4 instructions')
    for k, v in sorted(summary.items(), key=lambda kv: -kv[1]['files']):
        print(f"  {k:<16} files={v['files']:<6} insns={v['insns']:<8} zen5={'yes' if v['on_zen5'] else 'no'}")

if __name__ == '__main__':
    main()
