#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Put a rebuilt OpenBook kernel into a published live image's Android partitions, from public inputs only (ANAL-341).
# The shipped images were made by OpenBook's Android product build; this does the same steps with AOSP's host tools:
#   boot.img         mkbootimg with the image's own boot arguments and the new bzImage; AVB hash footer, salted with
#                    the bzImage's sha256 as the product build did, with the image's boot properties
#   vendor_boot.img  the image's vendor_boot with its "dlkm" ramdisk fragment replaced by the new one; AVB hash footer
#                    with the image's salt and properties
#   super.img        the image's super made again with lpmake, in its own partition order, with system_dlkm_a and
#                    vendor_dlkm_a replaced (Kleaf's images, which carry their own AVB hashtree footers)
#   vbmeta.img       made again from every partition's descriptors, signed with AOSP's public test key
#   init_boot.img    unchanged; build_fingerprint.txt, from the image's MANIFEST.json
# The output directory is installer-image.sh's --inputs: it then writes a whole live image.
# Checks: the bzImage and every module in both dlkm images name the same kernel release; avbtool verifies vbmeta
# against all nine images.
#
# usage: kernel-into-image.sh --image LIVE.img --kernel DIR --out DIR
#   --kernel  a Kleaf dist of //devices/anybook:anybook_g14_dist (bzImage, system_dlkm.flatten.erofs.img,
#             bm/vendor_dlkm.img, bm/initramfs.img: the files scripts/kernel-g14-package.sh selects), or its packaging
#             images/ directory (bzImage, system_dlkm.img, vendor_dlkm.img, vendor_boot-ramdisk.lz4)
# Needs python3, binutils (strings), and mtools or 7-Zip to read the image's EFI partition.
# Env: AOSP_HOST_BIN  AOSP's host tools (avbtool, fsck.erofs, lpdump, lpmake, mkbootimg, unpack_bootimg; default
#                     <data dir>/aosp/src/out/host/linux-x86/bin)
#      AVB_KEY        the signing key (default <data dir>/aosp/src/external/avb/test/data/testkey_rsa4096.pem, AOSP's
#                     public test key, which the published images use)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
HB=${AOSP_HOST_BIN:-$A/aosp/src/out/host/linux-x86/bin}
KEY=${AVB_KEY:-$A/aosp/src/external/avb/test/data/testkey_rsa4096.pem}
IMG=; KD=; OUT=
while [ $# -gt 0 ]; do
  case $1 in
    --image) IMG=$(realpath "$2"); shift 2 ;;
    --kernel) KD=$(realpath "$2"); shift 2 ;;
    --out) OUT=$(realpath -m "$2"); shift 2 ;;
    -h|--help) sed -n '3,25p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
die() { echo "kernel-into-image: $*" >&2; exit 1; }
[ -f "$IMG" ] && [ -d "$KD" ] && [ -n "$OUT" ] || die "usage: --image LIVE.img --kernel DIR --out DIR"
for t in avbtool fsck.erofs lpdump lpmake mkbootimg unpack_bootimg; do [ -x "$HB/$t" ] || die "no $t in $HB"; done
[ -f "$KEY" ] || die "no signing key at $KEY"
if [ -f "$KD/bm/initramfs.img" ]; then   # a Kleaf dist: the bare-metal files, as kernel-g14-package.sh copies them
  BZ=$KD/bzImage; SD=$KD/system_dlkm.flatten.erofs.img; VD=$KD/bm/vendor_dlkm.img; FR=$KD/bm/initramfs.img
else                                    # kernel-g14-package.sh's images/
  BZ=$KD/bzImage; SD=$KD/system_dlkm.img; VD=$KD/vendor_dlkm.img; FR=$KD/vendor_boot-ramdisk.lz4
fi
for f in "$BZ" "$SD" "$VD" "$FR"; do [ -f "$f" ] || die "missing $f"; done
mkdir -p "$OUT"; W=$(mktemp -d "$OUT/.work.XXXXXX"); trap 'rm -rf "$W"' EXIT
avb() { "$HB/avbtool" "$@"; }

echo "-- partitions of $(basename "$IMG")"
OPENBOOK_HOME=$A python3 - "$IMG" "$W" "$R/scripts/installer/mklive.py" <<'PY'
import importlib.util, os, struct, sys
img, w, mklive_py = sys.argv[1:]
f = open(img, "rb"); f.seek(512)
lba, n, esz = struct.unpack_from("<QII", f.read(92), 72); f.seek(lba * 512); t = f.read(n * esz)
for i in range(n):
    e = t[i * esz:(i + 1) * esz]
    if e[:16] == b"\0" * 16:
        continue
    a, b = struct.unpack_from("<QQ", e, 32); name = e[56:128].decode("utf-16le").rstrip("\0")
    if name in ("boot_a", "init_boot_a", "vendor_boot_a", "vbmeta_a", "super", "EFI"):
        f.seek(a * 512); left = (b - a + 1) * 512
        with open(f"{w}/{name}.img", "wb") as o:
            while left:
                d = f.read(min(left, 64 << 20)); o.write(d); left -= len(d)
spec = importlib.util.spec_from_file_location("mklive", mklive_py)
m = importlib.util.module_from_spec(spec); sys.argv = ["mklive"]; spec.loader.exec_module(m)
_, _, parts = m.lp_layout(f"{w}/super.img")
m.extract_partitions(f"{w}/super.img", {k: v for k, v in parts.items() if k.endswith("_a")}, f"{w}/lp")
PY

# the image's ESP keeps what its repacked super no longer has: the product's group sizes (in the disk installer's
# super metadata) and the build fingerprint (in MANIFEST.json); read with mtools or 7-Zip
esp_get() { # esp_get PATH OUT
  if command -v mcopy >/dev/null; then mcopy -n -i "$W/EFI.img" "::/$1" "$2" 2>/dev/null
  elif command -v 7z >/dev/null; then (cd "$W" && 7z e -y -so EFI.img "$1" > "$2" 2>/dev/null)
  else die "reading the image's EFI partition needs mtools (mcopy) or 7-Zip (7z)"; fi
  [ -s "$2" ] || die "no $1 on the image's EFI partition"
}
esp_get openbook/install/super-metadata.img "$W/install-super.img"
esp_get openbook/MANIFEST.json "$W/MANIFEST.json"
LPGROUPS=$("$HB/lpdump" "$W/install-super.img" | awk '/^  Name:/{n=$2} /^  Maximum size:/{if (n != "default") print n":"$3}' | paste -sd, -)
[ -n "$LPGROUPS" ] || die "no partition groups in the image's install metadata"
FP=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("fingerprint", ""))' "$W/MANIFEST.json")

# what the image says about each footer: partition size, salt, properties; and vbmeta's rollback index and key
footer() { # footer IMG -> "SIZE SALT" on line 1, then one --prop argument per line
  avb info_image --image "$1" | python3 -c '
import re, sys
t = sys.stdin.read()
size = re.search(r"^Image size:\s+(\d+) bytes", t, re.M).group(1)
salt = re.search(r"Salt:\s+([0-9a-f]+)", t).group(1)
print(size, salt)
for k, v in re.findall(r"Prop: (\S+) -> \x27(.*)\x27", t):
    print(f"{k}:{v}")'
}
VB=$(avb info_image --image "$W/vbmeta_a.img")
ROLLBACK=$(sed -n 's/^Rollback Index: *//p' <<< "$VB" | head -1)
ALG=$(sed -n 's/^Algorithm: *//p' <<< "$VB" | head -1)
want_pk=$(sed -n 's/^Public key (sha1): *//p' <<< "$VB")
have_pk=$(avb extract_public_key --key "$KEY" --output "$W/key.bin" && sha1sum < "$W/key.bin" | cut -c1-40)
[ "$want_pk" = "$have_pk" ] || echo "   note: $KEY is not the key that signed the image's vbmeta ($want_pk)"

echo "-- boot.img: the new bzImage with the image's boot arguments"
"$HB/unpack_bootimg" --boot_img "$W/boot_a.img" --out "$W/ub" --format=mkbootimg > "$W/boot.args"
mapfile -t BF < <(footer "$W/boot_a.img")
eval "set -- $(cat "$W/boot.args")"
args=(); while [ $# -gt 0 ]; do
  case $1 in --kernel) args+=(--kernel "$BZ"); shift 2 ;; *) args+=("$1"); shift ;; esac
done
"$HB/mkbootimg" "${args[@]}" --output "$OUT/boot.img"
read -r size _ <<< "${BF[0]}"; props=(); for p in "${BF[@]:1}"; do props+=(--prop "$p"); done
avb add_hash_footer --image "$OUT/boot.img" --partition_name boot --partition_size "$size" \
  --salt "$(sha256sum < "$BZ" | cut -c1-64)" "${props[@]}"

echo "-- vendor_boot.img: the new dlkm ramdisk fragment"
"$HB/unpack_bootimg" --boot_img "$W/vendor_boot_a.img" --out "$W/uv" --format=mkbootimg > "$W/vb.args"
mapfile -t VF < <(footer "$W/vendor_boot_a.img")
eval "set -- $(cat "$W/vb.args")"
args=(); name=; frag=0
while [ $# -gt 0 ]; do
  case $1 in
    --ramdisk_name) name=$2; args+=("$1" "$2"); shift 2 ;;
    --vendor_ramdisk_fragment)
      if [ "$name" = dlkm ]; then args+=("$1" "$FR"); frag=1; else args+=("$1" "$2"); fi; shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
[ $frag = 1 ] || die "the image's vendor_boot has no dlkm ramdisk fragment"
"$HB/mkbootimg" "${args[@]}" --vendor_boot "$OUT/vendor_boot.img"
read -r size salt <<< "${VF[0]}"; props=(); for p in "${VF[@]:1}"; do props+=(--prop "$p"); done
avb add_hash_footer --image "$OUT/vendor_boot.img" --partition_name vendor_boot --partition_size "$size" \
  --salt "$salt" "${props[@]}"

echo "-- super.img: the new system_dlkm and vendor_dlkm, every partition in the image's table order"
OPENBOOK_HOME=$A python3 - "$W/super.img" "$OUT/super.img" "$SD" "$VD" "$R/scripts/installer/mklive.py" "$HB/lpmake" "$LPGROUPS" <<'PY'
import importlib.util, os, subprocess, sys
src, out, sd, vd, mklive_py, lpmake, gsizes = sys.argv[1:]
gsize = dict(g.rsplit(":", 1) for g in gsizes.split(","))
spec = importlib.util.spec_from_file_location("mklive", mklive_py)
m = importlib.util.module_from_spec(spec); sys.argv = ["mklive"]; spec.loader.exec_module(m)
hdr, groups, parts = m.lp_layout(src)
files = m.extract_partitions(src, parts, os.path.dirname(out) + "/.lp-all")
files.update({"system_dlkm_a": sd, "vendor_dlkm_a": vd})
size = {n: (os.path.getsize(files[n]) if n in files else p["size"]) for n, p in parts.items()}
align = hdr["alignment"]
reserved = -(-(4096 + 2 * 4096 + 2 * hdr["metadata_slots"] * hdr["metadata_size"]) // align) * align
content = sum(-(-v // align) * align for v in size.values())
dev = max(hdr["device_size"], -(-(reserved + content) // (1 << 20)) * (1 << 20))
cmd = [lpmake, "--device-size", dev, "--metadata-size", hdr["metadata_size"], "--metadata-slots", hdr["metadata_slots"],
       "--super-name", "super", "--alignment", align, "--block-size", hdr["block_size"], "--force-full-image",
       "--output", out]
if hdr["virtual_ab"]:
    cmd.append("--virtual-ab")
for g, _ in groups:  # the product's group sizes, so the disk installer's metadata comes out as the product made it
    cmd += ["--group", f"{g}:{gsize.get(g, dev - reserved)}"]
for name, p in parts.items():
    cmd += ["--partition", f"{name}:{p['attrs']}:{size[name]}:{p['group']}"]
    if name in files and size[name]:
        cmd += ["--image", f"{name}={files[name]}"]
subprocess.run([str(c) for c in cmd], check=True, stdout=subprocess.DEVNULL)
for f in os.listdir(os.path.dirname(out) + "/.lp-all"):
    os.unlink(os.path.join(os.path.dirname(out) + "/.lp-all", f))
os.rmdir(os.path.dirname(out) + "/.lp-all")
print(f"   {len(parts)} partitions; system_dlkm_a {size['system_dlkm_a']} and vendor_dlkm_a {size['vendor_dlkm_a']} bytes")
PY
cp --reflink=auto "$W/init_boot_a.img" "$OUT/init_boot.img"
[ -z "$FP" ] || printf '%s\n' "$FP" > "$OUT/build_fingerprint.txt"

echo "-- vbmeta.img: every partition's descriptors, $ALG, rollback index $ROLLBACK"
L=$W/verify; mkdir -p "$L"
for p in boot init_boot vendor_boot; do ln -sf "$OUT/$p.img" "$L/$p.img"; done
for p in system vendor product system_ext; do ln -sf "$W/lp/${p}_a.img" "$L/$p.img"; done
ln -sf "$SD" "$L/system_dlkm.img"; ln -sf "$VD" "$L/vendor_dlkm.img"
inc=(); for p in boot init_boot vendor_boot system vendor product system_ext system_dlkm vendor_dlkm; do
  inc+=(--include_descriptors_from_image "$L/$p.img"); done
avb make_vbmeta_image --output "$OUT/vbmeta.img" --key "$KEY" --algorithm "$ALG" --rollback_index "$ROLLBACK" \
  --padding_size 65536 "${inc[@]}"
cp "$OUT/vbmeta.img" "$L/vbmeta.img"
avb verify_image --image "$L/vbmeta.img" --key "$KEY" > "$W/verify.txt" 2>&1 || { cat "$W/verify.txt"; die "avbtool verify_image failed"; }
echo "   avbtool verify_image: $(grep -c 'Successfully verified' "$W/verify.txt") descriptors verified"

echo "-- one kernel release for the bzImage and every module"
rel=$(strings "$BZ" | grep -m1 -oE '[0-9]+\.[0-9]+\.[0-9]+-android[0-9]+-[0-9]+(-g[0-9a-f]+)?' || true)
[ -n "$rel" ] || die "no kernel release string in $BZ"
for img in "$SD" "$VD"; do
  d=$W/fs-$(basename "$img" .img); "$HB/fsck.erofs" --extract="$d" --no-preserve "$img" >/dev/null
  python3 - "$d" "$rel" "$(basename "$img")" <<'PY'
import os, re, sys
root, rel, name = sys.argv[1:]
n, bad = 0, []
for dp, _, fs in os.walk(root):
    for f in fs:
        if f.endswith(".ko"):
            n += 1
            m = re.search(rb"vermagic=([^\0 ]+)", open(os.path.join(dp, f), "rb").read())
            if not m or m.group(1).decode() != rel:
                bad.append(f)
print(f"   {name}: {n} modules, {n - len(bad)} built for {rel}")
sys.exit(1 if bad or not n else 0)
PY
done
{
  echo "made: $(date -u +%FT%TZ) by kernel-into-image.sh from $(basename "$IMG") and $KD"
  echo "kernel release: $rel"
  (cd "$OUT" && sha256sum boot.img init_boot.img vendor_boot.img vbmeta.img super.img)
} > "$OUT/provenance.txt"
cp "$OUT/provenance.txt" /dev/stdout
echo "-- done: $OUT is installer-image.sh's --inputs"
