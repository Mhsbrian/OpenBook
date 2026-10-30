#!/usr/bin/env python3
"""Stage the AnyBook linux-firmware subset in Android's /vendor/firmware layout, with its licences and a manifest.

usage: kernel-g14-firmware.py --subset TSV --src DIR --fw LINUX_FIRMWARE_GIT --out DIR

  --subset  the subset list from scripts/kernel-firmware-subset.py (kernel/firmware/anybook-amd-subset.tsv,
            137 files since ANAL-175 added the GA403WR speaker tuning):
            file, WHENCE link target, size, sha256, requesting module, WHENCE driver and licence
  --src     that script's staging dir (~/anybook/kernel/firmware/anybook-amd): the files, LICENSES/ and WHENCE
  --fw      the linux-firmware clone the subset came from; used for the commit and to check every file's git blob
  --out     writes OUT/vendor/firmware/<linux-firmware path> (WHENCE links become regular files, because
            PRODUCT_COPY_FILES copies files), OUT/vendor/firmware/LICENSES/ (every licence file the WHENCE
            entries cite), OUT/WHENCE, OUT/firmware.mk (PRODUCT_COPY_FILES for the product build) and
            OUT/firmware-manifest.{tsv,md,json}: each file's source, licence and whether the GA403WR uses it

The kernel loads these directly from /vendor/firmware (firmware_class.path in the G14 vendor_boot command line).
Install them uncompressed: the GKI has FW_LOADER_COMPRESS off.
"""
import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import subprocess

URL = "https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/tree/{path}?id={commit}"

# What the GA403WR loads (evidence/2026-10-16-ga403wr-inventory): Strix Point GPU (GC 11.5.0, PSP 14.0.0,
# DCN 3.5, SDMA 6.1.0, VCN 4.0.5, VPE 6.1.0, UMSCH 4.0.0), NPU 1022:17f0 rev 10, MT7925 Wi-Fi and Bluetooth, and
# the CS35L56 tuning for codec SSID 1043:1024 with speaker ID 1 (the root inventory run saw it load), and, when
# nouveau drives the dGPU (ANAL-239), the RTX 5070 Ti Laptop's GSP-RM firmware (GB205).
GA403WR = re.compile(r"amdgpu/(gc_11_5_0|psp_14_0_0|dcn_3_5_dmcub|sdma_6_1_0|vcn_4_0_5|vpe_6_1_0|umsch_mm_4_0_0)[_.]"
                     r"|amdnpu/17f0_10/|mediatek/mt7925/|cirrus/cs35l56-b0-dsp1-misc-10431024-spkid1"
                     r"|nvidia/gb205/gsp/")

# Corrections to earlier notes, kept in the manifest so nobody goes looking for these again.
NOTES = [
    "GA403WR speaker tuning is not missing. linux-firmware has no files named 10431024 in its git tree, which is "
    "what ANAL-171 and the ANAL-198 issue text went by, but WHENCE (lines 9731-9736 at 38c1a709) creates "
    "cirrus/cs35l56-b0-dsp1-misc-10431024-* as links to the 10431044 tuning and CS35L56_Rev3.11.16.wmfw. The "
    "laptop loads the spkid1 set (ANAL-175 root inventory). They are staged here as regular files.",
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def git(fw, *args):
    return subprocess.run(["git", "-C", fw, *args], check=True, capture_output=True, text=True).stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subset", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--fw", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    lines = open(a.subset).read().splitlines()
    commit = lines[0].split()[2]
    rows = [l.split("\t") for l in lines[2:] if l.strip()]
    files = [r for r in rows if r[1] != "MISSING"]
    declared_missing = [r[0] for r in rows if r[1] == "MISSING"]
    blobs = {}
    for l in git(a.fw, "ls-tree", "-r", commit, "--", *sorted({r[1] or r[0] for r in files})).splitlines():
        meta, path = l.split("\t", 1)
        blobs[path] = meta.split()[2]

    vf = os.path.join(a.out, "vendor/firmware")
    if os.path.exists(a.out):
        shutil.rmtree(a.out)
    os.makedirs(vf)
    manifest, problems = [], []
    for name, link, size, digest, module, driver, licence in files:
        src = os.path.join(a.src, name)
        dst = os.path.join(vf, name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)  # follows WHENCE links
        got = sha256(dst)
        blob = subprocess.run(["git", "hash-object", dst], check=True, capture_output=True, text=True).stdout.strip()
        source = link or name
        if got != digest:
            problems.append(f"{name}: sha256 {got} differs from the subset list")
        if blobs.get(source) != blob:
            problems.append(f"{name}: git blob {blob} differs from {source} at {commit[:12]} ({blobs.get(source)})")
        m = re.search(r"See (\S+) for details", licence)
        manifest.append({
            "path": f"vendor/firmware/{name}", "size": int(size), "sha256": got,
            "source": f"linux-firmware {commit[:12]}:{source}" + (f" (WHENCE link {name})" if link else ""),
            "source_url": URL.format(path=source, commit=commit), "git_blob": blob,
            "driver": driver, "licence": licence, "licence_file": m.group(1) if m else "",
            "requested_by": module, "ga403wr": "yes" if GA403WR.match(name) else "no",
        })

    lic_dir = os.path.join(vf, "LICENSES")
    os.makedirs(lic_dir)
    licences = sorted({m["licence_file"] for m in manifest if m["licence_file"]})
    for lf in licences:
        if not os.path.exists(os.path.join(a.src, "LICENSES", lf)):
            problems.append(f"licence file {lf} is cited by WHENCE but missing from {a.src}/LICENSES")
            continue
        shutil.copyfile(os.path.join(a.src, "LICENSES", lf), os.path.join(lic_dir, lf))
    shutil.copyfile(os.path.join(a.src, "WHENCE"), os.path.join(a.out, "WHENCE"))
    if len({m["licence"] for m in manifest if not m["licence_file"]}):
        problems.append("some WHENCE licences cite no licence file")

    with open(os.path.join(a.out, "firmware.mk"), "w") as f:
        f.write("# Generated by scripts/kernel-g14-firmware.py (ANAL-198) from linux-firmware "
                f"{commit[:12]}.\n# Set ANYBOOK_G14_FIRMWARE_DIR to the staged vendor/firmware directory.\n"
                "PRODUCT_COPY_FILES += \\\n")
        entries = [m["path"].removeprefix("vendor/firmware/") for m in manifest] + [f"LICENSES/{l}" for l in licences]
        f.write(" \\\n".join(f"    $(ANYBOOK_G14_FIRMWARE_DIR)/{e}:$(TARGET_COPY_OUT_VENDOR)/firmware/{e}"
                             for e in entries) + "\n")

    cols = ["path", "size", "sha256", "source", "driver", "licence_file", "requested_by", "ga403wr"]
    with open(os.path.join(a.out, "firmware-manifest.tsv"), "w") as f:
        f.write(f"# linux-firmware {commit}; /vendor/firmware layout; ANAL-198\n" + "\t".join(cols) + "\n")
        for m in manifest:
            f.write("\t".join(str(m[c]) for c in cols) + "\n")

    by_lic = collections.defaultdict(lambda: [0, 0])
    for m in manifest:
        by_lic[m["licence_file"]][0] += 1
        by_lic[m["licence_file"]][1] += m["size"]
    used = [m for m in manifest if m["ga403wr"] == "yes"]
    md = [f"# Firmware manifest: AnyBook G14 (ANAL-198)", "",
          f"- Source: linux-firmware `{commit}` ({URL.format(path='WHENCE', commit=commit)})",
          f"- Subset: `{os.path.basename(a.subset)}` (ANAL-171, 10431024 tuning added by ANAL-175), {len(manifest)} files, "
          f"{sum(m['size'] for m in manifest) / 1e6:.1f} MB, staged as `/vendor/firmware/<linux-firmware path>`",
          f"- Every file's sha256 matches the subset list and its git blob matches linux-firmware at that commit: "
          f"{'yes' if not problems else 'NO, see problems'}",
          f"- Used by the GA403WR: {len(used)} files, {sum(m['size'] for m in used) / 1e6:.1f} MB. "
          "The rest serves other Zen 4/Zen 5 laptops (Phoenix, Hawk Point, Strix Halo, Krackan; MT7921/MT7922; rtw89).",
          "", "| Licence file (all redistributable per WHENCE) | Files | MB |", "|---|---|---|"]
    md += [f"| `{l}` | {n} | {s / 1e6:.1f} |" for l, (n, s) in sorted(by_lic.items())]
    md += ["", "## Missing", "", "| File | Requested by | GA403WR | Note |", "|---|---|---|---|"]
    md += [f"| `{n}` | amdxdna | no | declared by the driver, absent from linux-firmware; the GA403WR's NPU is rev 10 "
           "(17f0_10) |" for n in declared_missing]
    md += ["", "## Notes", ""] + [f"- {n}" for n in NOTES]
    md += ["", "## Files", "", "| Path | Bytes | sha256 | Source | Licence | Module | GA403WR |",
           "|---|---|---|---|---|---|---|"]
    md += [f"| `{m['path']}` | {m['size']} | `{m['sha256'][:16]}…` | {m['source'].split(':', 1)[1]} | "
           f"{m['licence_file']} | {m['requested_by']} | {m['ga403wr']} |" for m in manifest]
    if problems:
        md += ["", "## Problems", ""] + [f"- {p}" for p in problems]
    open(os.path.join(a.out, "firmware-manifest.md"), "w").write("\n".join(md) + "\n")
    json.dump({"linux_firmware": commit, "files": manifest, "licence_files": licences,
               "missing": [{"file": n, "requested_by": "amdxdna", "ga403wr": "no"} for n in declared_missing],
               "notes": NOTES,
               "problems": problems}, open(os.path.join(a.out, "firmware-manifest.json"), "w"), indent=1)
    print(f"staged {len(manifest)} files ({len(used)} used by the GA403WR) and {len(licences)} licence files "
          f"in {vf}; {len(problems)} problems")
    for p in problems:
        print("PROBLEM:", p)
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
