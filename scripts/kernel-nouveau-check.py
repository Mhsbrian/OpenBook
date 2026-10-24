#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline load check of new vendor modules against an installed kernel and module set (ANAL-239).

Reads the binaries the laptop runs, not build metadata: the kernel's vmlinux (extracted from boot.img, e.g. with
common/scripts/extract-vmlinux) and the .ko files of its vendor_dlkm and system_dlkm. For each new module it does
what the Android 6.18 module loader does, offline:

  vermagic   equal to the installed modules' (the loader accepts a differing release with modversions; we do not)
  imports    every undefined symbol is exported by exactly one of vmlinux, an installed module or another new
             module, and has a modversions entry (__versions or __version_ext_*) whose CRC equals the exporter's
             __kcrctab CRC (check_version)
  protected  new modules are unsigned, so no import may carry KSYM_FLAG_PROTECTED in the exporter's __kflagstab
             (resolve_symbol under MODULE_SIG_PROTECT), and no export may be a protected export of vmlinux
             (__kexporttab) or duplicate any existing export (verify_exported_symbols)
  gpl        an import flagged KSYM_FLAG_GPL_ONLY needs a GPL-compatible module licence
  depends    modinfo depends equals the set of exporting modules; with --load-order, each dependency on the
             load list comes before the module (others are reported: modprobe needs them in modules.dep)
  names      no new module has the name of an installed one; with --replaces, a replacement must export a strict
             superset of the installed module's symbols with identical CRCs (none is expected for ANAL-239)

usage: kernel-nouveau-check.py --vmlinux VMLINUX --installed DIR [--installed DIR ...] --new KO [--new KO ...]
                               [--load-order modules.load] [--json OUT] [--md OUT]
       kernel-nouveau-check.py --compare-vmlinux OLD NEW [--compare OLD_DIR NEW_DIR ...] [--json OUT] [--md OUT]

The second form checks a rebuilt kernel against the installed one ("never replace a module unless the replacement
exports a strict superset with identical CRCs"):
  vmlinux    every installed export is still exported, with the same CRC; a flag may only lose PROTECTED
             (a symbol newly put on the KMI list); added exports are listed
  modules    for each module in both directories: the same exports with the same CRCs and flags, the same imports
             with the same CRCs, and every section byte-identical except .modinfo's vermagic and scmversion, the
             build ID and, for signed GKI modules, the appended signature. Modules only in one directory are listed.
Exit status 1 on any problem. Python 3 standard library only.
"""
import argparse
import hashlib
import json
import os
import struct
import sys

KSYM_FLAG_GPL_ONLY, KSYM_FLAG_PROTECTED = 1, 2
GPL_COMPATIBLE = {"GPL", "GPL v2", "GPL and additional rights", "Dual BSD/GPL", "Dual MIT/GPL", "Dual MPL/GPL"}


class Elf:
    def __init__(self, path):
        self.path = path
        self.data = open(path, "rb").read()
        d = self.data
        if d[:4] != b"\x7fELF" or d[4] != 2 or d[5] != 1:
            raise ValueError(f"{path}: not a 64-bit little-endian ELF")
        self.type = struct.unpack_from("<H", d, 16)[0]
        shoff, = struct.unpack_from("<Q", d, 40)
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", d, 58)
        raw = [struct.unpack_from("<IIQQQQIIQQ", d, shoff + i * shentsize) for i in range(shnum)]
        names = raw[shstrndx]
        self.sections = []
        for r in raw:
            name_off, typ, flags, addr, off, size, link, info, align, entsize = r
            end = d.index(b"\0", names[4] + name_off)
            self.sections.append(dict(name=d[names[4] + name_off:end].decode(), type=typ, addr=addr, off=off,
                                      size=size, link=link, entsize=entsize))
        self.by_name = {s["name"]: s for s in self.sections}

    def sec(self, name):
        s = self.by_name.get(name)
        return None if s is None else self.data[s["off"]:s["off"] + s["size"]]

    def symbols(self):
        st = next((s for s in self.sections if s["type"] == 2), None)  # SHT_SYMTAB
        if st is None:
            return []
        strtab = self.sections[st["link"]]
        out = []
        for i in range(st["size"] // 24):
            name, info, other, shndx, value, size = struct.unpack_from("<IBBHQQ", self.data, st["off"] + i * 24)
            end = self.data.index(b"\0", strtab["off"] + name)
            out.append((self.data[strtab["off"] + name:end].decode(), info, shndx, value))
        return out

    def modinfo(self):
        out = {}
        for item in (self.sec(".modinfo") or b"").split(b"\0"):
            if b"=" in item:
                k, _, v = item.decode(errors="replace").partition("=")
                out.setdefault(k, v)
        return out


def kernel_exports(elf):
    """vmlinux: name -> (crc, flags), from __ksymtab (PREL32 entries), __kcrctab and __kflagstab."""
    ks, kc, kf = (elf.by_name[n] for n in ("__ksymtab", "__kcrctab", "__kflagstab"))
    strs = elf.by_name["__ksymtab_strings"]
    n = ks["size"] // 12
    if kc["size"] != 4 * n or kf["size"] < n:
        raise ValueError("vmlinux export tables disagree in length")
    out = {}
    for i in range(n):
        addr = ks["addr"] + 12 * i
        name_off, = struct.unpack_from("<i", elf.data, ks["off"] + 12 * i + 4)
        name_addr = addr + 4 + name_off
        p = strs["off"] + name_addr - strs["addr"]
        name = elf.data[p:elf.data.index(b"\0", p)].decode()
        crc, = struct.unpack_from("<I", elf.data, kc["off"] + 4 * i)
        out[name] = (crc, elf.data[kf["off"] + i])
    return out


def kernel_protected_exports(elf):
    """vmlinux __kexporttab: PREL32 references (x86_64) to the names in __ksymtab_strings that unsigned modules may
    not export (PROTECT_EXPORT in include/linux/export-internal.h)."""
    s = elf.by_name.get("__kexporttab")
    if s is None:
        return None
    strs = elf.by_name["__ksymtab_strings"]
    out = set()
    for i in range(s["size"] // 4):
        off, = struct.unpack_from("<i", elf.data, s["off"] + 4 * i)
        addr = s["addr"] + 4 * i + off
        if not strs["addr"] <= addr < strs["addr"] + strs["size"]:
            raise ValueError("__kexporttab entry outside __ksymtab_strings")
        p = strs["off"] + addr - strs["addr"]
        out.add(elf.data[p:elf.data.index(b"\0", p)].decode())
    return out


def module_exports(elf):
    """.ko: name -> (crc, flags). __ksymtab_<name> symbols give each export's slot in __ksymtab; __kcrctab and
    __kflagstab are indexed by the same slot."""
    ks = elf.by_name.get("__ksymtab")
    if ks is None:
        return {}
    idx = {s["name"]: i for i, s in enumerate(elf.sections)}
    kc, kf = elf.sec("__kcrctab"), elf.sec("__kflagstab")
    out = {}
    for name, info, shndx, value in elf.symbols():
        if name.startswith("__ksymtab_") and shndx == idx["__ksymtab"]:
            slot = value // 12
            crc = struct.unpack_from("<I", kc, 4 * slot)[0] if kc else None
            out[name[len("__ksymtab_"):]] = (crc, kf[slot] if kf else 0)
    return out


def module_versions(elf):
    """Imports' modversions CRCs: __versions (u64 crc + 56-byte name) and the extended tables."""
    out = {}
    v = elf.sec("__versions") or b""
    for i in range(len(v) // 64):
        crc, = struct.unpack_from("<Q", v, 64 * i)
        name = v[64 * i + 8:64 * i + 64].split(b"\0")[0].decode()
        if name:
            out[name] = crc & 0xffffffff
    crcs, names = elf.sec("__version_ext_crcs"), elf.sec("__version_ext_names")
    if crcs is not None and names is not None:
        for i, name in enumerate(n for n in names.split(b"\0") if n):
            out[name.decode()] = struct.unpack_from("<I", crcs, 4 * i)[0]
    return out


def undefined(elf):
    return sorted({n for n, info, shndx, value in elf.symbols() if shndx == 0 and n and info >> 4 in (1, 2)})


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def check(a):
    problems = []
    vml = Elf(a.vmlinux)
    kexp = kernel_exports(vml)
    kprot = kernel_protected_exports(vml)
    build_id = None
    note = vml.sec(".notes") or b""
    if b"GNU\0" in note:
        i = note.index(b"GNU\0")
        namesz, descsz, typ = struct.unpack_from("<III", note, i - 12)
        if typ == 3:
            build_id = note[i + 4:i + 4 + descsz].hex()
    providers = {"vmlinux": {"path": a.vmlinux, "sha256": sha256(a.vmlinux), "exports": kexp}}
    installed = {}
    for d in a.installed:
        for f in sorted(os.listdir(d)):
            if f.endswith(".ko"):
                p = os.path.join(d, f)
                e = Elf(p)
                name = e.modinfo().get("name", f[:-3])
                if name in installed:
                    problems.append(f"installed module {name} appears twice ({installed[name]['path']}, {p})")
                installed[name] = {"path": p, "sha256": sha256(p), "exports": module_exports(e),
                                   "vermagic": e.modinfo().get("vermagic", ""), "signed": e.data.endswith(
                                       b"~Module signature appended~\n")}
    vermagics = {m["vermagic"] for m in installed.values()}
    if len(vermagics) != 1:
        problems.append(f"installed modules have {len(vermagics)} different vermagic strings")
    ref_vermagic = sorted(vermagics)[0] if vermagics else ""
    new = {}
    for p in a.new:
        e = Elf(p)
        mi = e.modinfo()
        name = mi.get("name", os.path.basename(p)[:-3])
        new[name] = {"path": p, "sha256": sha256(p), "elf": e, "modinfo": mi, "exports": module_exports(e)}
    providers.update({n: m for n, m in installed.items()})
    # A new module with an installed module's name keeps both as exporters, so their duplicate exports show.
    key = {n: n + "#new" if n in installed else n for n in new}
    providers.update({key[n]: {"path": m["path"], "sha256": m["sha256"], "exports": m["exports"]} for n, m in new.items()})

    # Who exports what (vmlinux, installed, new); a symbol with two owners cannot load.
    owners = {}
    for pname, pv in providers.items():
        for s in pv["exports"]:
            owners.setdefault(s, []).append(pname)

    load = None
    if a.load_order:
        load = [os.path.basename(l.strip())[:-3].replace("-", "_") for l in open(a.load_order) if l.strip()]

    results = {}
    for name, m in new.items():
        e, mi = m["elf"], m["modinfo"]
        r = {"sha256": m["sha256"], "vermagic": mi.get("vermagic", ""), "license": mi.get("license", ""),
             "intree": mi.get("intree", ""), "scmversion": mi.get("scmversion", ""),
             "depends": sorted(x for x in mi.get("depends", "").split(",") if x), "imports": 0,
             "imports_by_provider": {}, "crc_mismatches": [], "missing_versions": [], "unresolved": [],
             "ambiguous": [], "protected_imports": [], "gpl_violations": [], "exports": len(m["exports"]),
             "duplicate_exports": [], "protected_exports": [], "problems": []}
        if r["vermagic"] != ref_vermagic:
            r["problems"].append(f"vermagic {r['vermagic']!r} != installed {ref_vermagic!r}")
        if name in installed:
            r["problems"].append("an installed module has the same name")
        vers = module_versions(e)
        gpl_ok = r["license"] in GPL_COMPATIBLE
        used = set()
        for s in undefined(e):
            if s.startswith("__this_module") or s == "_GLOBAL_OFFSET_TABLE_":
                continue
            own = [o for o in owners.get(s, []) if o != key[name]]
            if not own:
                r["unresolved"].append(s)
                continue
            if len(own) > 1:
                r["ambiguous"].append(f"{s}: {', '.join(own)}")
            o = own[0]
            crc, flags = providers[o]["exports"][s]
            r["imports"] += 1
            r["imports_by_provider"][o] = r["imports_by_provider"].get(o, 0) + 1
            if o != "vmlinux":
                used.add(o.removesuffix("#new"))
            if s not in vers:
                r["missing_versions"].append(s)
            elif crc is not None and vers[s] != crc:
                r["crc_mismatches"].append(f"{s}: module {vers[s]:#010x}, {o} {crc:#010x}")
            if flags & KSYM_FLAG_PROTECTED:
                r["protected_imports"].append(f"{s} ({o})")
            if flags & KSYM_FLAG_GPL_ONLY and not gpl_ok:
                r["gpl_violations"].append(f"{s} ({o})")
        for s in m["exports"]:
            other = [o for o in owners[s] if o != key[name]]
            if other:
                r["duplicate_exports"].append(f"{s}: {', '.join(other)}")
            if kprot is not None and s in kprot:
                r["protected_exports"].append(s)
        want = {x.replace("-", "_") for x in r["depends"]}
        got = {x.replace("-", "_") for x in used}
        if want != got:
            r["problems"].append(f"modinfo depends {sorted(want)} != exporting modules {sorted(got)}")
        if load is not None:
            # A dependency on the load list must come first. One that is not (a system_dlkm module such as rfkill)
            # is loaded by modprobe through the module's modules.dep line, which the packaging must then write.
            me = name.replace("-", "_")
            r["deps_via_modules_dep"] = sorted(d for d in got if d not in load)
            if me not in load:
                r["problems"].append("not in the load order")
            else:
                for dep in sorted(got):
                    if dep in load and load.index(dep) > load.index(me):
                        r["problems"].append(f"dependency {dep} is loaded after it")
        r["imports_by_provider"] = dict(sorted(r["imports_by_provider"].items(), key=lambda kv: -kv[1]))
        for k in ("crc_mismatches", "missing_versions", "unresolved", "ambiguous", "protected_imports",
                  "gpl_violations", "duplicate_exports", "protected_exports"):
            if r[k]:
                r["problems"].append(f"{len(r[k])} {k.replace('_', ' ')}, e.g. {r[k][:3]}")
        results[name] = r
        problems += [f"{name}: {x}" for x in r["problems"]]

    report = {
        "schema": "openbook-module-load-check/1",
        "kernel": {"vmlinux": os.path.abspath(a.vmlinux), "sha256": providers["vmlinux"]["sha256"],
                   "build_id": build_id, "exports": len(kexp),
                   "protected_exports": None if kprot is None else len(kprot)},
        "installed": {"dirs": [os.path.abspath(d) for d in a.installed], "modules": len(installed),
                      "signed": sum(m["signed"] for m in installed.values()), "vermagic": ref_vermagic,
                      "sha256": {n: m["sha256"] for n, m in sorted(installed.items())}},
        "new": results,
        "totals": {k: sum(len(r[k]) for r in results.values()) for k in (
            "crc_mismatches", "missing_versions", "unresolved", "ambiguous", "protected_imports", "gpl_violations",
            "duplicate_exports", "protected_exports")} | {"imports": sum(r["imports"] for r in results.values())},
        "problems": problems,
        "ok": not problems,
    }
    return report


SIG_MAGIC = b"~Module signature appended~\n"
IGNORED_SECTIONS = {".modinfo", ".note.gnu.build-id"}
# Split BTF refers to the type IDs of the vmlinux it was built with, so it changes whenever vmlinux is rebuilt.
# The GKI has MODULE_ALLOW_BTF_MISMATCH=y: a module whose BTF does not match still loads (its BTF is dropped).
BTF_SECTIONS = {".BTF", ".BTF.base"}
# Modules that carry their kernel's own data, so a rebuilt kernel changes them by design.
EMBEDS_KERNEL = {"kheaders.ko": "embeds the kernel's own headers archive (/sys/kernel/kheaders.tar.xz)"}


def relocs(e, name):
    """A RELA section as (offset, type, symbol index) triples, without addends."""
    data = e.sec(name) or b""
    return [(o, i & 0xffffffff, i >> 32) for o, i, _ in struct.iter_unpack("<QQq", data)]


def strings(data):
    return sorted(x for x in data.split(b"\0") if x)


def release_only(o, n, differing, old_rel, new_rel):
    """True when the only content change is the kernel release string (UTS_RELEASE, e.g. amdgpu's devcoredump
    banner): the string sections differ only in strings that name the release, and the relocations differ only in
    their addends, because merging the strings again moved the others."""
    if not old_rel or not new_rel or old_rel == new_rel:
        return False
    for name in differing:
        if name.startswith(".rela"):
            if relocs(o, name) != relocs(n, name):
                return False
        elif name.startswith(".rodata"):
            a, b = strings(o.sec(name)), strings(n.sec(name))
            if [x for x in a if old_rel.encode() not in x] != [x for x in b if new_rel.encode() not in x]:
                return False
            if [x.replace(old_rel.encode(), new_rel.encode()) for x in a if old_rel.encode() in x] != \
                    [x for x in b if new_rel.encode() in x]:
                return False
        else:
            return False
    return True


def compare_vmlinux(old_path, new_path):
    old, new = kernel_exports(Elf(old_path)), kernel_exports(Elf(new_path))
    r = {"old": {"sha256": sha256(old_path), "exports": len(old)}, "new": {"sha256": sha256(new_path), "exports": len(new)},
         "removed": sorted(set(old) - set(new)), "crc_changed": [], "flags_changed": [], "unprotected": [],
         "added": sorted(set(new) - set(old))}
    for name in sorted(set(old) & set(new)):
        (oc, of), (nc, nf) = old[name], new[name]
        if oc != nc:
            r["crc_changed"].append(f"{name}: {oc:#010x} -> {nc:#010x}")
        if of != nf:
            if of & ~KSYM_FLAG_PROTECTED == nf and of & KSYM_FLAG_PROTECTED:
                r["unprotected"].append(name)
            else:
                r["flags_changed"].append(f"{name}: {of} -> {nf}")
    r["problems"] = [f"{len(r[k])} {k.replace('_', ' ')}, e.g. {r[k][:3]}" for k in ("removed", "crc_changed",
                                                                                   "flags_changed") if r[k]]
    return r


def compare_module(old_path, new_path):
    o, n = Elf(old_path), Elf(new_path)
    problems = []
    oe, ne = module_exports(o), module_exports(n)
    if oe != ne:
        lost = sorted(set(oe) - set(ne))
        changed = sorted(s for s in set(oe) & set(ne) if oe[s] != ne[s])
        gained = sorted(set(ne) - set(oe))
        if lost or changed:
            problems.append(f"exports lost {lost[:3]} or changed {changed[:3]}")
        if gained:
            problems.append(f"exports gained {gained[:3]} (a superset, but not expected from a rebuild)")
    if module_versions(o) != module_versions(n):
        problems.append("imports or their CRCs differ")
    differing, btf = [], False
    for name in sorted({x["name"] for e in (o, n) for x in e.sections} - IGNORED_SECTIONS):
        so, sn = o.by_name.get(name), n.by_name.get(name)
        if so and sn and so["type"] == sn["type"] == 8:  # SHT_NOBITS (.bss): no bytes in the file, only a size
            same = so["size"] == sn["size"]
        else:
            same = o.sec(name) == n.sec(name)
        if not same:
            if name in BTF_SECTIONS:
                btf = True
            else:
                differing.append(name)
    om, nm = o.modinfo(), n.modinfo()
    note = None
    rel = lambda m: m.get("vermagic", "").split(" ")[0]
    if differing and os.path.basename(new_path) in EMBEDS_KERNEL:
        note = EMBEDS_KERNEL[os.path.basename(new_path)]
    elif differing and release_only(o, n, differing, rel(om), rel(nm)):
        note = "only the kernel release string differs (and the string offsets it moves): " + ", ".join(differing)
    elif differing:
        problems.append(f"sections differ: {differing}")
    keep = lambda m: {k: v for k, v in m.items() if k not in ("vermagic", "scmversion")}
    if keep(om) != keep(nm):
        problems.append("modinfo differs beyond vermagic/scmversion")
    return {"old_sha256": sha256(old_path), "new_sha256": sha256(new_path), "exports": len(oe),
            "imports": len(module_versions(o)), "btf_differs": btf, "note": note,
            "signed": (o.data.endswith(SIG_MAGIC), n.data.endswith(SIG_MAGIC)),
            "vermagic": (om.get("vermagic", ""), nm.get("vermagic", "")), "problems": problems}


def label(d):
    """vendor_dlkm for .../vendor_dlkm/lib/modules, else the directory's own name."""
    d = os.path.normpath(d)
    if d.endswith(os.path.join("lib", "modules")):
        return os.path.basename(os.path.dirname(os.path.dirname(d)))
    return os.path.basename(d)


def compare(a):
    rep = {"schema": "openbook-kernel-rebuild-compare/1", "vmlinux": compare_vmlinux(*a.compare_vmlinux),
           "modules": {}, "only_old": [], "only_new": [], "problems": []}
    rep["problems"] += [f"vmlinux: {p}" for p in rep["vmlinux"]["problems"]]
    for old_dir, new_dir in a.compare or []:
        olds = {f for f in os.listdir(old_dir) if f.endswith(".ko")}
        news = {f for f in os.listdir(new_dir) if f.endswith(".ko")}
        rep["only_old"] += sorted(os.path.join(old_dir, f) for f in olds - news)
        rep["only_new"] += sorted(os.path.join(new_dir, f) for f in news - olds)
        for f in sorted(olds & news):
            r = compare_module(os.path.join(old_dir, f), os.path.join(new_dir, f))
            rep["modules"][os.path.join(label(old_dir), f)] = r
            rep["problems"] += [f"{f}: {p}" for p in r["problems"]]
    rep["problems"] += [f"only in the installed set: {p}" for p in rep["only_old"]]
    rep["ok"] = not rep["problems"]
    return rep


def compare_markdown(rep):
    v = rep["vmlinux"]
    out = ["# Rebuilt kernel against the installed one", "",
           f"- vmlinux: {v['old']['exports']} -> {v['new']['exports']} exports; removed {len(v['removed'])}, CRC changed "
           f"{len(v['crc_changed'])}, flags changed {len(v['flags_changed'])}; added {len(v['added'])}; "
           f"unprotected {len(v['unprotected'])}",
           f"- modules compared: {len(rep['modules'])}; byte-identical: "
           f"{sum(r['old_sha256'] == r['new_sha256'] for r in rep['modules'].values())}; only .BTF differs (beyond "
           f"vermagic/scmversion/build ID/signature): {sum(r['btf_differs'] and not r['problems'] and not r['note'] for r in rep['modules'].values())}; "
           f"explained differences: {sum(bool(r['note']) for r in rep['modules'].values())}; with problems: "
           f"{sum(bool(r['problems']) for r in rep['modules'].values())}; only installed: {len(rep['only_old'])}; "
           f"only new: {len(rep['only_new'])}",
           f"- Result: **{'PASS' if rep['ok'] else 'FAIL'}**", "", "Added exports: " + ", ".join(f"`{x}`" for x in v["added"]),
           "", "Exports no longer protected: " + (", ".join(f"`{x}`" for x in v["unprotected"]) or "none"), ""]
    if rep["only_new"]:
        out.append("Only in the rebuilt set: " + ", ".join(f"`{os.path.basename(x)}`" for x in rep["only_new"]))
    notes = [(k, r["note"]) for k, r in rep["modules"].items() if r["note"]]
    if notes:
        out += ["", "Explained differences:", ""] + [f"- `{k}`: {n}" for k, n in notes]
    return "\n".join(out) + "\n"


def markdown(rep):
    t = rep["totals"]
    out = ["# Offline load check: new vendor modules against the installed kernel", "",
           f"- Kernel: vmlinux sha256 `{rep['kernel']['sha256']}`, build ID `{rep['kernel']['build_id']}`, "
           f"{rep['kernel']['exports']} exports, {rep['kernel']['protected_exports']} protected export names",
           f"- Installed modules: {rep['installed']['modules']} ({rep['installed']['signed']} signed), "
           f"vermagic `{rep['installed']['vermagic']}`",
           f"- Imports checked: {t['imports']}; CRC mismatches {t['crc_mismatches']}; missing versions "
           f"{t['missing_versions']}; unresolved {t['unresolved']}; ambiguous {t['ambiguous']}; protected imports "
           f"{t['protected_imports']}; GPL violations {t['gpl_violations']}; duplicate exports "
           f"{t['duplicate_exports']}; protected exports {t['protected_exports']}",
           f"- Result: **{'PASS' if rep['ok'] else 'FAIL'}**", "",
           "| module | sha256 | vermagic ok | imports (by exporter) | exports | depends | problems |",
           "|---|---|---|---|---|---|---|"]
    for n, r in rep["new"].items():
        by = ", ".join(f"{k} {v}" for k, v in r["imports_by_provider"].items())
        out.append(f"| {n} | `{r['sha256'][:16]}…` | {'yes' if r['vermagic'] == rep['installed']['vermagic'] else 'NO'}"
                   f" | {r['imports']} ({by}) | {r['exports']} | {', '.join(r['depends']) or '-'} | "
                   f"{'; '.join(r['problems']) or 'none'} |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vmlinux")
    ap.add_argument("--installed", action="append")
    ap.add_argument("--new", action="append")
    ap.add_argument("--load-order")
    ap.add_argument("--compare-vmlinux", nargs=2, metavar=("OLD", "NEW"))
    ap.add_argument("--compare", nargs=2, action="append", metavar=("OLD_DIR", "NEW_DIR"))
    ap.add_argument("--json")
    ap.add_argument("--md")
    a = ap.parse_args()
    if a.compare_vmlinux:
        rep = compare(a)
        if a.json:
            with open(a.json, "w") as f:
                json.dump(rep, f, indent=2)
                f.write("\n")
        md = compare_markdown(rep)
        if a.md:
            open(a.md, "w").write(md)
        print(md, end="")
        for p in rep["problems"]:
            print("FAIL", p)
        return 0 if rep["ok"] else 1
    if not (a.vmlinux and a.installed and a.new):
        ap.error("--vmlinux, --installed and --new are required (or use --compare-vmlinux)")
    rep = check(a)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rep, f, indent=2)
            f.write("\n")
    md = markdown(rep)
    if a.md:
        open(a.md, "w").write(md)
    print(md, end="")
    for p in rep["problems"]:
        print("FAIL", p)
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
