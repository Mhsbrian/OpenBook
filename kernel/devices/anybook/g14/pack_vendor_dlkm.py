#!/usr/bin/env python3
"""Build vendor_dlkm.img the way Android loads it, from Kleaf's vendor_dlkm staging archive (ANAL-198).

usage: pack_vendor_dlkm.py --out DIR --file-contexts FC --modules-list LIST INPUT...

INPUT are the files of a Kleaf vendor_dlkm_image(archive = True) and of //common:kernel_x86_64_system_dlkm_image;
the script picks vendor_dlkm_staging_archive.tar.gz and system_dlkm.modules.load from them. LIST names the
vendor modules to ship (g14/vendor_dlkm.modules.list); the staging also holds GKI kunit modules, which go nowhere.

Kleaf's own vendor_dlkm.flatten.img copies every module of the mixed build, the 100 GKI modules included, and
leaves modules.blocklist out. This lays out what Googlebook's vendor_dlkm holds instead (fs/vendor_dlkm_a on
ruby): lib/modules/ with only the vendor .ko files, flat, and a modules.dep with absolute paths,
/vendor/lib/modules/<m>.ko for vendor modules and /system/lib/modules/<m>.ko for the GKI modules they link
against, which system_dlkm provides. modules.load, modules.blocklist, modules.softdep and modules.options are
kept; modules.alias keeps the aliases of the vendor modules.

Then, as Kleaf's build_vendor_dlkm does: build_image (erofs, file contexts FC, which here are the platform's
vendor_file labels) and an unsigned AVB hashtree footer. Writes DIR/vendor_dlkm.img and DIR/vendor_dlkm.modules.{load,blocklist,dep}. Runs in a Kleaf
hermetic_genrule, which puts python3, build_image, mkfs.erofs and avbtool on PATH.
"""
import argparse
import os
import shutil
import subprocess
import tarfile
import tempfile


def base(p):
    return os.path.basename(p.strip())


def pick(inputs, name):
    (f,) = [i for i in inputs if os.path.basename(i) == name]
    return f


def layout(archive, gki, wanted, root):
    with tempfile.TemporaryDirectory() as t:
        with tarfile.open(archive) as tf:
            try:
                tf.extractall(t, filter="data")
            except TypeError:  # Python without extraction filters; the archive comes from Kleaf
                tf.extractall(t)
        (rel,) = os.listdir(os.path.join(t, "lib/modules"))
        src = os.path.join(t, "lib/modules", rel)
        dst = os.path.join(root, "lib/modules")
        os.makedirs(dst)

        deps = {}
        for line in open(os.path.join(src, "modules.dep")):
            mod, _, rest = line.partition(":")
            deps[mod] = rest.split()
        vendor = [m for m in deps if base(m) in wanted]
        if len(vendor) != len(wanted):
            raise SystemExit(f"not in the staging: {sorted(wanted - {base(m) for m in vendor})}")
        for m in vendor:
            for d in deps[m]:
                if base(d) not in wanted and base(d) not in gki:
                    raise SystemExit(f"{base(m)} needs {base(d)}, which is neither listed nor a GKI module")

        def path(m):
            return ("/system/lib/modules/" if base(m) in gki else "/vendor/lib/modules/") + base(m)

        needed_gki = sorted({d for m in vendor for d in deps[m] if base(d) in gki}, key=base)
        with open(os.path.join(dst, "modules.dep"), "w") as f:
            for m in vendor + needed_gki:
                f.write(f"{path(m)}:" + "".join(f" {path(d)}" for d in deps[m]) + "\n")
        for m in vendor:
            shutil.copy2(os.path.join(src, m), os.path.join(dst, base(m)))

        names = {base(m).removesuffix(".ko").replace("-", "_") for m in vendor}
        with open(os.path.join(src, "modules.alias")) as fi, open(os.path.join(dst, "modules.alias"), "w") as fo:
            fo.writelines(l for l in fi if l.startswith("alias ") and l.split()[-1].replace("-", "_") in names)
        with open(os.path.join(src, "modules.load")) as fi, open(os.path.join(dst, "modules.load"), "w") as fo:
            fo.writelines(base(l) + "\n" for l in fi if l.strip())
        for name in ("modules.blocklist", "modules.softdep", "modules.options"):
            if os.path.exists(os.path.join(src, name)):
                shutil.copy2(os.path.join(src, name), os.path.join(dst, name))
        open(os.path.join(dst, "modules.blocklist"), "a").close()
    return vendor, needed_gki


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--file-contexts", required=True)
    ap.add_argument("--modules-list", required=True)
    ap.add_argument("inputs", nargs="+")
    a = ap.parse_args()
    gki = {base(l) for l in open(pick(a.inputs, "system_dlkm.modules.load")) if l.strip()}
    os.makedirs(a.out, exist_ok=True)
    with tempfile.TemporaryDirectory() as w:
        root = os.path.join(w, "root")
        wanted = {l.strip() for l in open(a.modules_list) if l.strip() and not l.startswith("#")}
        vendor, needed_gki = layout(pick(a.inputs, "vendor_dlkm_staging_archive.tar.gz"), gki, wanted, root)
        props = os.path.join(w, "props")
        with open(props, "w") as f:
            f.write("fs_type=erofs\nuse_dynamic_partition_size=true\nmount_point=vendor_dlkm\n"
                    f"selinux_fc={os.path.abspath(a.file_contexts)}\n")
        img = os.path.join(a.out, "vendor_dlkm.img")
        subprocess.run(["build_image", root, props, img, "/dev/null"], check=True)
        subprocess.run(["avbtool", "add_hashtree_footer", "--partition_name", "vendor_dlkm",
                        "--hash_algorithm", "sha256", "--image", img], check=True)
        for f in ("load", "blocklist", "dep"):
            shutil.copy2(os.path.join(root, "lib/modules", f"modules.{f}"),
                         os.path.join(a.out, f"vendor_dlkm.modules.{f}"))
    print(f"vendor_dlkm: {len(vendor)} vendor modules; links {len(needed_gki)} GKI modules from system_dlkm: "
          + " ".join(base(m) for m in needed_gki))


if __name__ == "__main__":
    main()
