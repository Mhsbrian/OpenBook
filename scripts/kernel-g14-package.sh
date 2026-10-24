#!/usr/bin/env bash
# Bare-metal packaging for the ASUS ROG Zephyrus G14 2025 (GA403WR), ANAL-198: build the kernel-side images
# with Kleaf, check them, stage the firmware, and run the QEMU first-stage check. See docs/kernel.md,
# "Bare-metal packaging for the G14".
#
# usage: kernel-g14-package.sh [--from STEP] [--only STEP] [--evidence DIR]
#   steps, in order: apply build lists sigcheck firmware qemu collect
#   Resumable: each finished step leaves OUT/.stamps/<step>; a rerun skips those whose inputs did not change
#   (the stamp holds a hash of them). --from STEP reruns STEP and everything after it.
#   --evidence DIR  also copy the reports (no images, no firmware blobs) into DIR, e.g. evidence/<date>-kernel-g14
# env: G14_LABEL (default anybook-g14-<synced target>), ANYBOOK_KERNEL_JOBS / BAZEL_ARGS as for kernel-build.sh,
#      ANYBOOK_KERNEL_SRC the kernel tree (default ~/anybook/kernel/src).
#      While an anybook-aosp-build container runs, the build step caps Bazel at 16 jobs and 16 GiB unless
#      ANYBOOK_KERNEL_JOBS is set.
#
# Outputs: ~/anybook/kernel/dist/<label>/ (the Kleaf dist) and ~/anybook/kernel/g14/<label>/:
#   images/   vendor_boot.img, vendor_boot-ramdisk.lz4 (its DLKM fragment), vendor_dlkm.img, system_dlkm.img,
#             boot.img, bzImage, and vm/ with the VM variants
#   lists/    vendor_boot and vendor_dlkm modules.load, modules.blocklist and modules.dep as built
#   firmware/ vendor/firmware/ tree, licences, firmware.mk and firmware-manifest.{md,tsv,json}
#   qemu/     per-run serial logs and results
#   images.{md,json}, modlists.{md,json}, sigcheck.{md,json}, results.json (all steps, machine-readable)
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
A=${ANYBOOK_HOME:-$HOME/anybook}; K=$A/kernel; S=${ANYBOOK_KERNEL_SRC:-$K/src}
STEPS=(apply build lists sigcheck firmware qemu collect)
FROM=; ONLY=; EVIDENCE=
while [ $# -gt 0 ]; do
  case $1 in
    --from) FROM=$2; shift 2 ;;
    --only) ONLY=$2; shift 2 ;;
    --evidence) EVIDENCE=$(realpath -m "$2"); shift 2 ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
done
T=$(cat "$S/.anybook-target"); LABEL=${G14_LABEL:-anybook-g14-$T}
D=$K/dist/$LABEL; O=$K/g14/$LABEL; ST=$O/.stamps
TOOLS=$S/prebuilts/kernel-build-tools/linux_musl-x86/bin
mkdir -p "$O" "$ST" "$A/logs/kernel"
LOG=$A/logs/kernel/g14-package-$LABEL-$(date +%Y%m%d-%H%M%S).log
exec > >(tee -a "$LOG") 2>&1
echo "### kernel-g14-package label=$LABEL $(date -Is) log=$LOG"

hash_of() { { cat "$@" 2>/dev/null || true; } | sha256sum | cut -c1-16; }  # missing inputs hash as absent
inputs() {  # what each step depends on; a change reruns it
  case $1 in
    apply) hash_of "$R"/kernel/patches/{common,nouveau}/* <(find "$R/kernel/devices/anybook" -type f -exec sha256sum {} + | sort) ;;
    build) echo "$(hash_of "$ST/apply")-$(git -C "$S/common" rev-parse HEAD)" ;;
    lists) hash_of "$D/sha256.txt" "$D"/{bm,vm}/*.img $(find "$R/kernel/devices/anybook/g14" -type f | sort) "$R/scripts/kernel-g14-modlists.py" ;;
    sigcheck) hash_of "$D/sha256.txt" "$D"/{bm,vm}/*.img "$R/scripts/kernel-g14-sigcheck.py" ;;
    qemu) hash_of "$D/sha256.txt" "$D"/{bm,vm}/*.img "$R"/scripts/kernel-g14-qemu.{py,sh} "$R/kernel/devices/anybook/g14/test/fstab.qemu" ;;
    firmware) hash_of "$R/evidence/2026-10-16-kernel-amd/firmware-subset.tsv" "$R/scripts/kernel-g14-firmware.py" ;;
    collect) hash_of "$ST"/{build,lists,sigcheck,firmware,qemu} ;;
  esac
}
idx() { local i; for i in "${!STEPS[@]}"; do [ "${STEPS[$i]}" = "$1" ] && echo "$i"; done; }
want() {  # should step $1 run?
  [ -n "$ONLY" ] && { [ "$ONLY" = "$1" ]; return; }
  [ -n "$FROM" ] && [ "$(idx "$1")" -ge "$(idx "$FROM")" ] && return 0
  [ "$(cat "$ST/$1" 2>/dev/null)" != "$(inputs "$1")" ]
}
done_step() { inputs "$1" > "$ST/$1"; echo "### step $1 done $(date -Is)"; }

if want apply; then
  "$R/scripts/kernel-amd-apply.sh"   # also prepares devices/anybook/nvidia/nouveau (ANAL-239)
  done_step apply
fi

if want build; then
  if [ -z "${ANYBOOK_KERNEL_JOBS:-}" ] && docker ps --format '{{.Names}}' | grep -qx anybook-aosp-build; then
    export ANYBOOK_KERNEL_JOBS=16 BAZEL_ARGS="${BAZEL_ARGS:-} --local_ram_resources=16384"
    echo "### AOSP build running: Bazel capped at --jobs=16 --local_ram_resources=16384"
  fi
  echo "jobs=${ANYBOOK_KERNEL_JOBS:-all} bazel_args=${BAZEL_ARGS:-}" > "$O/build-settings.txt"
  rm -rf "$D"   # pkg_install does not remove files a previous run left
  KERNEL_TARGET=//devices/anybook:anybook_g14_dist "$R/scripts/kernel-build.sh" "$LABEL"
  done_step build
fi

if want lists; then
  "$R/scripts/kernel-docker.sh" python3 "$R/scripts/kernel-g14-modlists.py" check --dist "$D" \
    --report "$O/modlists.md" --json "$O/modlists.json"
  done_step lists
fi

if want sigcheck; then
  "$R/scripts/kernel-docker.sh" python3 "$R/scripts/kernel-g14-sigcheck.py" --dist "$D" \
    --cert "$S/bazel-bin/common/kernel_x86_64/certs/signing_key.x509" --tools "$TOOLS" --out "$O/sigcheck"
  done_step sigcheck
fi

if want firmware; then
  python3 "$R/scripts/kernel-g14-firmware.py" --subset "$R/evidence/2026-10-16-kernel-amd/firmware-subset.tsv" \
    --src "$K/firmware/anybook-amd" --fw "$K/firmware/linux-firmware" --out "$O/firmware"
  done_step firmware
fi

if want qemu; then
  # --force: results from an earlier dist must not be reused; the disk images are cached by input hash
  G14_OUT=$O/qemu "$R/scripts/kernel-g14-qemu.sh" "$D" --force
  done_step qemu
fi

if want collect; then
  rm -rf "$O/images" "$O/lists"; mkdir -p "$O/images/vm" "$O/lists"
  for v in bm vm; do
    dst=$O/images; [ $v = vm ] && dst=$O/images/vm
    cp --reflink=auto "$D/$v/vendor_boot.img" "$D/$v/vendor_dlkm.img" "$dst/"
    cp --reflink=auto "$D/$v/initramfs.img" "$dst/vendor_boot-ramdisk.lz4"
    cp "$D/$v/modules.load" "$O/lists/vendor_boot.$v.modules.load"
    for f in load blocklist dep; do cp "$D/$v/vendor_dlkm.modules.$f" "$O/lists/vendor_dlkm.$v.modules.$f"; done
  done
  cp --reflink=auto "$D/system_dlkm.flatten.erofs.img" "$O/images/system_dlkm.img"
  cp --reflink=auto "$D/boot.img" "$D/bzImage" "$O/images/"
  cp "$D/system_dlkm.flatten.modules.load" "$O/lists/system_dlkm.modules.load"
  python3 - "$O" "$D" "$TOOLS" <<'EOF'
import hashlib, json, os, subprocess, sys
o, d, tools = sys.argv[1:4]
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
what = {
    "vendor_boot.img": "boot image v4, vendor_boot; one DLKM ramdisk fragment \"dlkm\" with no modules (first stage needs none)",
    "vm/vendor_boot.img": "the same for VMs; the fragment holds 7 virtio modules",
    "vm/vendor_boot-ramdisk.lz4": "the VM fragment on its own",
    "vm/vendor_dlkm.img": "the same vendor modules; VM modules.load (no virtio, in first stage) and blocklist (asus-nb-wmi)",
    "vendor_boot-ramdisk.lz4": "that fragment on its own (lib/modules/<release>/), for a product-built vendor_boot",
    "vendor_dlkm.img": "erofs, unsigned hashtree footer; the vendor modules, Android layout",
    "system_dlkm.img": "erofs (Kleaf system_dlkm.flatten.erofs.img), 100 GKI modules signed by this build's key",
    "boot.img": "GKI boot image of the same build (kernel only)",
    "bzImage": "the kernel",
}
rows = []
for sub in ("", "vm"):
    for f in sorted(os.listdir(os.path.join(o, "images", sub))):
        p = os.path.join(o, "images", sub, f)
        if os.path.isdir(p): continue
        info = ""
        if f.endswith(".img") and "boot" not in f:
            info = subprocess.run([f"{tools}/avbtool", "info_image", "--image", p], capture_output=True,
                                  text=True).stdout
        rows.append({"file": os.path.join(sub, f), "bytes": os.path.getsize(p), "sha256": sha(p),
                     "what": what.get(os.path.join(sub, f), ""), "avb_footer": "Hashtree descriptor" in info})
json.dump(rows, open(os.path.join(o, "images.json"), "w"), indent=1)
md = ["# G14 images (ANAL-198)", "", f"Kleaf dist: `{d}` ({open(os.path.join(d, 'linux_banner.txt')).read().split()[2]})", "",
      "| File | Bytes | MiB | sha256 | AVB hashtree | What |", "|---|---|---|---|---|---|"]
md += [f"| `{r['file']}` | {r['bytes']} | {r['bytes'] / 2**20:.1f} | `{r['sha256']}` | {'yes' if r['avb_footer'] else '-'} | {r['what']} |" for r in rows]
open(os.path.join(o, "images.md"), "w").write("\n".join(md) + "\n")
res = {"label": os.path.basename(o), "images": rows}
for k in ("modlists", "sigcheck"):
    res[k] = json.load(open(os.path.join(o, f"{k}.json")))
res["firmware"] = {k: v for k, v in json.load(open(os.path.join(o, "firmware/firmware-manifest.json"))).items() if k != "files"}
res["firmware"]["files"] = len(json.load(open(os.path.join(o, "firmware/firmware-manifest.json")))["files"])
res["qemu"] = json.load(open(os.path.join(o, "qemu/results.json")))
res["pass"] = bool(res["modlists"]["ok"] and res["sigcheck"]["ok"] and not res["firmware"]["problems"] and res["qemu"]["pass"])
json.dump(res, open(os.path.join(o, "results.json"), "w"), indent=1)
print(f"### overall: {'PASS' if res['pass'] else 'FAIL'}")
EOF
  cat "$O/images.md"
  done_step collect
fi

if [ -n "$EVIDENCE" ]; then
  mkdir -p "$EVIDENCE/lists" "$EVIDENCE/qemu" "$EVIDENCE/firmware"
  cp "$O"/{images,modlists,sigcheck}.{md,json} "$O/results.json" "$O/build-settings.txt" "$EVIDENCE/"
  cp "$O"/lists/* "$EVIDENCE/lists/"
  cp "$O"/firmware/firmware-manifest.* "$O/firmware/firmware.mk" "$EVIDENCE/firmware/"
  for f in "$O"/qemu/*; do
    case $f in *.serial.log) gzip -9c "$f" > "$EVIDENCE/qemu/$(basename "$f").gz" ;; *) cp "$f" "$EVIDENCE/qemu/" ;; esac
  done
  cp "$D/linux_banner.txt" "$D/sha256.txt" "$EVIDENCE/"
  echo "### evidence copied to $EVIDENCE"
fi
echo "### done; outputs in $O; log $LOG"
