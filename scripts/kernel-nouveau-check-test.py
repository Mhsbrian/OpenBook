#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Tests for kernel-nouveau-check.py on real modules: each fault is planted in a copy and must be reported.

usage: kernel-nouveau-check-test.py VMLINUX VENDOR_MODULES_DIR SYSTEM_MODULES_DIR
  e.g. the Ruby release's vmlinux (extracted from boot.img) and its extracted vendor_dlkm/system_dlkm lib/modules.
The probe module is drm_exec.ko (imports from vmlinux, exports used by others) and its importer amdgpu.ko.
"""
import importlib.util
import os
import shutil
import struct
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("check", os.path.join(HERE, "kernel-nouveau-check.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

VML, VENDOR, SYSTEM = (os.path.abspath(p) for p in sys.argv[1:4])
fails = 0


def run(installed, new, load=None):
    return c.check(types.SimpleNamespace(vmlinux=VML, installed=installed, new=new, load_order=load))


def expect(name, rep, key=None, text=None):
    global fails
    r = next(iter(rep["new"].values())) if rep["new"] else {}
    ok = (bool(r.get(key)) if key else True) and (text is None or any(text in p for p in rep["problems"]))
    ok = ok and (not rep["ok"] if key or text else rep["ok"])
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f": {rep['problems'][:3]}"))
    fails += not ok


def section(path, name):
    e = c.Elf(path)
    s = e.by_name[name]
    return s["off"], s["size"]


with tempfile.TemporaryDirectory() as t:
    inst = os.path.join(t, "installed")
    os.mkdir(inst)
    for f in os.listdir(VENDOR):
        if f.endswith(".ko") and f != "drm_exec.ko":
            os.symlink(os.path.join(VENDOR, f), os.path.join(inst, f))
    probe = os.path.join(t, "drm_exec.ko")
    load = os.path.join(t, "modules.load")
    open(load, "w").write("".join(l for l in open(os.path.join(VENDOR, "modules.load"))))

    # 1. The real module, as installed: clean.
    shutil.copy(os.path.join(VENDOR, "drm_exec.ko"), probe)
    expect("unchanged module passes", run([inst, SYSTEM], [probe], load))

    # 2. One import CRC changed in __versions (an extended entry where the module has them).
    data = bytearray(open(probe, "rb").read())
    off, size = section(probe, "__version_ext_crcs") if "__version_ext_crcs" in c.Elf(probe).by_name else \
        section(probe, "__versions")
    data[off] ^= 0xFF
    bad = os.path.join(t, "crc", "drm_exec.ko")
    os.makedirs(os.path.dirname(bad))
    open(bad, "wb").write(data)
    expect("changed import CRC is reported", run([inst, SYSTEM], [bad]), "crc_mismatches")

    # 3. Another vermagic (same length, so the ELF stays valid).
    data = bytearray(open(probe, "rb").read())
    i = data.index(b"vermagic=6.18.21")
    data[i + len("vermagic=")] = ord("7")
    bad = os.path.join(t, "vermagic", "drm_exec.ko")
    os.makedirs(os.path.dirname(bad))
    open(bad, "wb").write(data)
    expect("other vermagic is reported", run([inst, SYSTEM], [bad]), text="vermagic")

    # 4. An exporter's flag turned PROTECTED: its importer may no longer use the symbol.
    prot = os.path.join(t, "prot")
    os.mkdir(prot)
    for f in os.listdir(inst):
        os.symlink(os.path.realpath(os.path.join(inst, f)), os.path.join(prot, f))
    data = bytearray(open(probe, "rb").read())
    off, size = section(probe, "__kflagstab")
    for k in range(size):
        data[off + k] |= c.KSYM_FLAG_PROTECTED
    open(os.path.join(prot, "drm_exec.ko"), "wb").write(data)
    os.remove(os.path.join(prot, "amdgpu.ko"))
    expect("protected import is reported", run([prot, SYSTEM], [os.path.join(VENDOR, "amdgpu.ko")]),
           "protected_imports")

    # 5. A new module that is already installed: same name and duplicate exports.
    expect("duplicate exports are reported", run([VENDOR, SYSTEM], [probe]), "duplicate_exports")

    # 6. A dependency loaded after the module.
    order = [l for l in open(load) if l.strip() and l.strip() != "drm_exec.ko"] + ["drm_exec.ko\n"]
    late = os.path.join(t, "late.load")
    open(late, "w").writelines(order)
    os.remove(os.path.join(inst, "amdgpu.ko"))
    expect("dependency loaded later is reported", run([inst, SYSTEM], [os.path.join(VENDOR, "amdgpu.ko"), probe], late),
           text="loaded after it")

    # 7. An unresolved symbol: the importer without its exporter.
    expect("unresolved import is reported", run([inst, SYSTEM], [os.path.join(VENDOR, "amdgpu.ko")]), "unresolved")

    # 8. Rebuild comparison: a module against itself passes; with a changed export CRC it fails.
    rep = c.compare(types.SimpleNamespace(compare_vmlinux=[VML, VML], compare=[[VENDOR, VENDOR]]))
    ok = rep["ok"] and not rep["vmlinux"]["added"]
    print(("ok   " if ok else "FAIL ") + "identical sets compare clean"); fails += not ok
    data = bytearray(open(probe, "rb").read())
    off, size = section(probe, "__kcrctab")
    data[off] ^= 0x01
    cmp_dir = os.path.join(t, "cmp")
    os.mkdir(cmp_dir)
    open(os.path.join(cmp_dir, "drm_exec.ko"), "wb").write(data)
    r = c.compare_module(os.path.join(VENDOR, "drm_exec.ko"), os.path.join(cmp_dir, "drm_exec.ko"))
    ok = any("exports lost" in p for p in r["problems"])
    print(("ok   " if ok else "FAIL ") + "changed export CRC fails the comparison"); fails += not ok

print(f"kernel-nouveau-check-test: {fails} failure(s)")
sys.exit(1 if fails else 0)
