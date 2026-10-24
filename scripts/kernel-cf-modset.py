#!/usr/bin/env python3
"""Assemble the kernel module tree that boots our kernel in Cuttlefish, check it, and pack it as an initramfs.

usage: kernel-cf-modset.py --gki DIST --board DIST --blocklist FILE --out DIR [--mode anybook|board]
                           [--vendor-list FILE] [--block NAME.ko[:REASON]]...

  --gki DIST        the AnyBook dist (scripts/kernel-build.sh): bzImage, vmlinux.symvers, abi_symbollist,
                    linux_banner.txt, System.map, system_dlkm_staging_archive.tar.gz and the vendor .ko files.
                    Its GKI modules carry this build's signature, so they are the only ones its bzImage accepts.
  --board DIST      the Cuttlefish board modules: //common-modules/virtual-device:virtual_device_x86_64_dist,
                    built on the same GKI (its initramfs.img). Only its unsigned vendor modules are used.
  --vendor-list     the AnyBook vendor modules, one file name per line (kernel/cuttlefish/vendor-modules.txt)
  --blocklist       Cuttlefish's device/google/cuttlefish/shared/modules.blocklist (what the product image ships)
  --block           add a module to that blocklist for this image, e.g. one whose hardware the VM lacks. It is still
                    shipped; dlkm_loader skips it. dlkm_loader stops short of setting vendor.dlkm.modules.ready when
                    any listed module fails, and Cuttlefish's bt_vhci_forwarder waits for that property.
  --mode            anybook (default): GKI + AnyBook vendor modules + the board modules that are ABI-compatible
                    with them. board: GKI + board modules only (control run).

The result is what `cvd create --kernel_path=... --initramfs_path=...` expects: lib/modules/<release>/ with
modules.load and modules.dep. assemble_cvd keeps its fixed list of first-stage virtio modules (and their deps)
in the vendor ramdisk, moves signed modules to system_dlkm and unsigned ones to vendor_dlkm, and rebuilds
super.img and the vbmeta images (device/google/cuttlefish/host/commands/assemble_cvd/vendor_dlkm_utils.cc).

Checks, repeated until nothing changes (a module that fails is dropped, then its dependents are re-checked):
  CRCs     every __versions entry must match the CRC that the chosen provider exports (vmlinux.symvers,
           a GKI module's or a vendor module's __kcrctab)
  imports  every undefined symbol must be exported by vmlinux or a chosen module
  KMI      unsigned modules may import only KMI-listed symbols from vmlinux and GKI modules (MODULE_SIG_PROTECT)
Name clashes between the AnyBook and board sets keep the AnyBook module: it is the product.

Writes DIR/root/, DIR/initramfs.img (cpio newc, lz4 legacy), DIR/modset.md, DIR/modset.tsv, DIR/depmod.log.
Needs nm, objcopy (binutils), modprobe/depmod (kmod), cpio and lz4: the anybook-kernel image has them.
"""
import argparse
import collections
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile

SIG_MAGIC = b"~Module signature appended~\n"
# assemble_cvd's kRamdiskModules (vendor_dlkm_utils.cc at android17-release): these and their deps stay in
# the vendor ramdisk and are loaded by first-stage init, where any load failure is fatal.
CF_RAMDISK = {
    "failover.ko", "nd_virtio.ko", "net_failover.ko", "virtio_blk.ko", "virtio_console.ko", "virtio_dma_buf.ko",
    "virtio-gpu.ko", "virtio_input.ko", "virtio_mmio.ko", "virtio_net.ko", "virtio_pci.ko",
    "virtio_pci_legacy_dev.ko", "virtio_pci_modern_dev.ko", "virtio-rng.ko", "vmw_vsock_virtio_transport.ko",
    "vmw_vsock_virtio_transport_common.ko", "vsock.ko", "libarc4.ko", "rfkill.ko", "cfg80211.ko", "mac80211.ko",
    "mac80211_hwsim.ko",
}


def run(*cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, check=True, **kw).stdout


def signed(path):
    with open(path, "rb") as f:
        f.seek(-len(SIG_MAGIC), os.SEEK_END)
        return f.read() == SIG_MAGIC


class Ko:
    """Exports with CRCs, __versions and undefined symbols of one module file."""

    def __init__(self, path, origin):
        self.path, self.origin, self.name = path, origin, os.path.basename(path)
        self.signed = signed(path)
        syms = run("nm", path).splitlines()
        with tempfile.NamedTemporaryFile() as t:
            subprocess.run(["objcopy", "-O", "binary", "-j", "__kcrctab", path, t.name], check=True)
            kcrctab = open(t.name, "rb").read()
        self.exports = {}
        for line in syms:
            p = line.split()
            if len(p) == 3 and p[2].startswith("__crc_"):
                self.exports[p[2][len("__crc_"):]] = struct.unpack_from("<I", kcrctab, int(p[0], 16))[0]
            elif len(p) >= 2 and p[-1].startswith("__ksymtab_"):
                self.exports.setdefault(p[-1][len("__ksymtab_"):], None)
        self.versions = {}
        for line in run("modprobe", "--dump-modversions", path).splitlines():
            crc, sym = line.split()[:2]
            self.versions[sym] = int(crc, 16)
        self.undefined = {l.split()[-1] for l in run("nm", "-u", path).splitlines() if l.strip()}


def unpack_initramfs(img, dest):
    os.makedirs(dest, exist_ok=True)
    data = subprocess.run(["lz4", "-dc", img], capture_output=True, check=True).stdout
    subprocess.run(["cpio", "-idm", "--quiet", "--no-absolute-filenames"], input=data, cwd=dest, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gki", required=True)
    ap.add_argument("--board", required=True)
    ap.add_argument("--vendor-list")
    ap.add_argument("--blocklist", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["anybook", "board"], default="anybook")
    ap.add_argument("--block", action="append", default=[])
    a = ap.parse_args()
    if a.mode == "anybook" and not a.vendor_list:
        ap.error("--mode anybook needs --vendor-list")

    release = open(os.path.join(a.gki, "linux_banner.txt")).read().split("Linux version ", 1)[1].split()[0]
    symvers = {}
    for line in open(os.path.join(a.gki, "vmlinux.symvers")):
        crc, sym = line.split()[:2]
        symvers[sym] = int(crc, 16)
    kmi = {l.strip() for l in open(os.path.join(a.gki, "abi_symbollist")) if l.startswith("  ")}

    shutil.rmtree(a.out, ignore_errors=True)
    work = os.path.join(a.out, "work")
    root = os.path.join(a.out, "root")
    mdir = os.path.join(root, "lib", "modules", release)
    os.makedirs(mdir)

    # GKI modules: from the dist's own system_dlkm staging tree, so the signatures match its bzImage.
    with tarfile.open(os.path.join(a.gki, "system_dlkm_staging_archive.tar.gz")) as t:
        t.extractall(os.path.join(work, "gki"), filter="data")
    gki_root = os.path.join(work, "gki", "lib", "modules", release)
    gki = {}
    for d, _, files in os.walk(gki_root):
        for f in files:
            if f.endswith(".ko"):
                rel = os.path.relpath(os.path.join(d, f), gki_root)
                gki[rel] = Ko(os.path.join(d, f), "gki")
    unsigned_gki = sorted(r for r, k in gki.items() if not k.signed)
    if unsigned_gki:
        sys.exit(f"GKI modules without a signature: {unsigned_gki[:5]}")

    # Board modules: the unsigned ones in the virtual_device initramfs (its GKI copies carry another key).
    unpack_initramfs(os.path.join(a.board, "initramfs.img"), os.path.join(work, "board"))
    board_root = os.path.join(work, "board", "lib", "modules", release)
    if not os.path.isdir(board_root):
        sys.exit(f"{a.board}/initramfs.img has no lib/modules/{release}: built for another kernel release?")
    board, board_order = {}, []
    for line in open(os.path.join(board_root, "modules.load")):
        rel = line.strip()
        if rel and rel not in gki:
            board_order.append(rel)
    for d, _, files in os.walk(board_root):
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), board_root)
            if f.endswith(".ko") and rel not in gki:
                board[rel] = Ko(os.path.join(d, f), "board")
    gki_names = {os.path.basename(r) for r in gki}
    board_gki_missing = sorted(gki_names - {f for d, _, fs in os.walk(board_root) for f in fs if f.endswith(".ko")})

    anybook = {}
    if a.mode == "anybook":
        for line in open(a.vendor_list):
            n = line.strip()
            if n and not n.startswith("#"):
                anybook[os.path.join("extra", "anybook", n)] = Ko(os.path.join(a.gki, n), "anybook")

    # Pick one module per name. AnyBook wins over the board set.
    excluded = {}  # rel -> (Ko, reason)
    clashes = []   # (kept Ko, dropped Ko)
    chosen = dict(gki)
    names = {k.name: rel for rel, k in gki.items()}
    for rel, k in list(anybook.items()) + list(board.items()):
        if k.signed:
            excluded[rel] = (k, "signed vendor module (would be moved to system_dlkm)")
        elif k.name in names:
            other = chosen[names[k.name]]
            excluded[rel] = (k, f"same name as the {other.origin} module `{names[k.name]}`, which is used instead")
            clashes.append((other, k))
        else:
            chosen[rel] = k
            names[k.name] = rel

    # Check imports and CRCs against the chosen providers until nothing else drops out.
    while True:
        prov = {s: ("vmlinux", c) for s, c in symvers.items()}
        for rel, k in chosen.items():
            for s, c in k.exports.items():
                prov.setdefault(s, (rel, c))
        dropped = {}
        for rel, k in chosen.items():
            if k.origin == "gki":
                continue
            why = []
            unresolved = sorted(s for s in k.undefined if s not in prov)
            if unresolved:
                why.append(f"{len(unresolved)} unresolved symbol(s), e.g. {', '.join(unresolved[:3])}")
            bad = sorted((s, prov[s][0]) for s, c in k.versions.items()
                         if s in prov and prov[s][1] is not None and prov[s][1] != c)
            if bad:
                by = collections.Counter(os.path.basename(p) for _, p in bad)
                why.append(f"{len(bad)} CRC mismatch(es) against {', '.join(f'{n} ({c})' for n, c in by.items())}, "
                           f"e.g. {', '.join(s for s, _ in bad[:3])}")
            unlisted = sorted(s for s in k.undefined if s in prov and
                              (prov[s][0] == "vmlinux" or chosen[prov[s][0]].origin == "gki") and s not in kmi)
            if unlisted:
                why.append(f"{len(unlisted)} import(s) not on the KMI list, e.g. {', '.join(unlisted[:3])}")
            if why:
                dropped[rel] = "; ".join(why)
        if not dropped:
            break
        for rel, why in dropped.items():
            excluded[rel] = (chosen.pop(rel), why)

    for rel, k in chosen.items():
        dst = os.path.join(mdir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(k.path, dst)
    for f in ("modules.builtin", "modules.builtin.modinfo"):
        shutil.copy2(os.path.join(a.gki, f), mdir)
    order = [r for r in sorted(gki)] + [r for r in board_order if r in chosen] + \
            [r for r in board if r in chosen and r not in board_order] + [r for r in anybook if r in chosen]
    with open(os.path.join(mdir, "modules.load"), "w") as o:
        o.write("".join(r + "\n" for r in order))
    with open(os.path.join(mdir, "modules.blocklist"), "w") as o:
        o.write(open(a.blocklist).read())
        for b in a.block:
            n, _, why = b.partition(":")
            o.write(f"\n# kernel-cf-modset.py --block: {why or 'its hardware is not in this VM; probe it by hand after boot'}\nblocklist {n}\n")
    dep = subprocess.run(["depmod", "-b", root, "-e", "-F", os.path.join(a.gki, "System.map"), release],
                         capture_output=True, text=True)
    with open(os.path.join(a.out, "depmod.log"), "w") as o:
        o.write(f"$ depmod -b root -e -F System.map {release}\nexit {dep.returncode}\n{dep.stdout}{dep.stderr}")
    if dep.returncode:
        sys.exit(f"depmod failed:\n{dep.stderr}")

    # Where assemble_cvd will put each module: closure of its ramdisk list over modules.dep.
    deps = {}
    for line in open(os.path.join(mdir, "modules.dep")):
        m, _, rest = line.partition(":")
        deps[m.strip()] = rest.split()
    ramdisk = set()
    todo = [r for r in order if os.path.basename(r) in CF_RAMDISK]
    while todo:
        r = todo.pop()
        if r not in ramdisk:
            ramdisk.add(r)
            todo += deps.get(r, [])
    blocked = {l.split()[1] for l in open(os.path.join(mdir, "modules.blocklist")) if l.startswith("blocklist ")}

    # Fixed mtimes, owners and order, so the same inputs give the same initramfs.img.
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    for d, dirs, files in os.walk(root):
        for f in dirs + files:
            os.utime(os.path.join(d, f), (epoch, epoch), follow_symlinks=False)
    os.utime(root, (epoch, epoch))
    cpio = subprocess.run("find . | LC_ALL=C sort | cpio -o -H newc -R 0:0 --quiet --reproducible",
                          shell=True, cwd=root, capture_output=True, check=True).stdout
    img = os.path.join(a.out, "initramfs.img")
    subprocess.run(["lz4", "-l", "-12", "--favor-decSpeed", "-f", "-", img], input=cpio, check=True,
                   capture_output=True)
    shutil.rmtree(work)

    def stage(rel, k):
        if rel in ramdisk:
            return "vendor_ramdisk"
        return "system_dlkm" if k.signed else "vendor_dlkm"

    rows = []
    for rel in order:
        k = chosen[rel]
        rows.append((k.name, k.origin, rel, stage(rel, k), "blocklisted" if k.name in blocked else "listed", ""))
    for rel, (k, why) in sorted(excluded.items(), key=lambda x: (x[1][0].origin, x[0])):
        rows.append((k.name, k.origin, rel, "excluded", "-", why))
    with open(os.path.join(a.out, "modset.tsv"), "w") as o:
        o.write("module\tsource\tpath\tstage\tload\treason\n")
        o.writelines("\t".join(r) + "\n" for r in rows)

    cnt = collections.Counter((k.origin, stage(r, k)) for r, k in chosen.items())
    exc = collections.Counter(k.origin for k, _ in excluded.values())
    src = {"gki": len(gki), "board": len(board), "anybook": len(anybook)}
    out = [f"# Cuttlefish module set: mode `{a.mode}`", "",
           f"Kernel release `{release}`. Sources: `{os.path.basename(os.path.normpath(a.gki))}` "
           f"(bzImage, GKI modules, AnyBook vendor modules) and `{os.path.basename(os.path.normpath(a.board))}` "
           "(Cuttlefish board modules).", "",
           "| source | modules | vendor_ramdisk | vendor_dlkm | system_dlkm | excluded |", "|---|---|---|---|---|---|"]
    for o in ("gki", "board", "anybook"):
        if src[o]:
            out.append(f"| {o} | {src[o]} | {cnt[(o, 'vendor_ramdisk')]} | {cnt[(o, 'vendor_dlkm')]} | "
                       f"{cnt[(o, 'system_dlkm')]} | {exc[o]} |")
    out += ["", f"{len(chosen)} modules in the initramfs; `modules.load` lists all of them. "
            f"Blocklisted (shipped, not loaded at boot by `dlkm_loader`): "
            f"{', '.join(sorted(n for n in blocked if n in names)) or 'none'}.", "",
            f"GKI modules missing from the board build's initramfs: {', '.join(board_gki_missing) or 'none'}.", ""]
    if clashes:
        out += ["## Same-name modules: exported CRCs compared", "",
                "A module from the other set can link against the kept copy only where the CRCs agree.", "",
                "| module | kept | dropped | exports (kept / dropped) | CRCs that differ | only in dropped |",
                "|---|---|---|---|---|---|"]
        for keep, drop in clashes:
            both = set(keep.exports) & set(drop.exports)
            diff = sorted(s for s in both if keep.exports[s] != drop.exports[s])
            only = sorted(set(drop.exports) - set(keep.exports))
            out.append(f"| {keep.name} | {keep.origin} | {drop.origin} | {len(keep.exports)} / {len(drop.exports)} | "
                       f"{len(diff)}{' (' + ', '.join(diff[:3]) + ')' if diff else ''} | "
                       f"{len(only)}{' (' + ', '.join(only[:3]) + ')' if only else ''} |")
        out.append("")
    if excluded:
        out += ["## Excluded", "", "| module | source | reason |", "|---|---|---|"]
        out += [f"| {r[0]} | {r[1]} | {r[5]} |" for r in rows if r[3] == "excluded"]
    with open(os.path.join(a.out, "modset.md"), "w") as o:
        o.write("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"\ninitramfs: {img} ({os.path.getsize(img) // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
