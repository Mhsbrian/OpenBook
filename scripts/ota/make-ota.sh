#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# A full A/B update package for an installed OpenBook (ANAL-223, docs/adb-debug.md "Updating the installed system"),
# from a build's target files, for scripts/g14-adb.sh ota:
#   1. snapshot the target files and otatools from PRODUCT_OUT (reflinks, under the AOSP lane lock, so no build runs
#      during it), or take --target-files/--otatools given;
#   2. --break-boot (tests only): a copy whose kernel cannot start (vendor_boot's command line names a missing rdinit,
#      panic=5), with vendor_boot and vbmeta rebuilt and signed by AOSP's own add_img_to_target_files: a slot that
#      verifies, installs and then never boots, for the rollback rehearsal;
#   3. ota_from_target_files: a full package (every partition, so it applies over any earlier OpenBook build), the
#      payload signed with the build's key (AOSP test keys today: update_engine checks it against the running
#      system's /system/etc/security/otacerts.zip);
#   4. OUT/LABEL.zip, LABEL.json (tree, fingerprint, build date, size, sha256, vbmeta digest, payload properties) and
#      LABEL.bootsync: the build's /vendor/bin/openbook-bootsync, which g14-adb.sh runs once on systems without one.
#
# usage: make-ota.sh LABEL [--target-files ZIP --otatools ZIP] [--break-boot] [--tree DESC] [--out DIR]
#   default: the target files and otatools.zip of <data dir>/aosp/src/out/target/product/anybook_g14
#   --tree: what the build was made from (default: the newest build log's "synced device/anybook" line)
# Builds/: <data dir>/ota/builds/LABEL/; output: --out (default <data dir>/ota/out); log: <data dir>/logs/ota/make-LABEL.log
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
P=$A/aosp/src/out/target/product/anybook_g14
LABEL=${1:?usage: make-ota.sh LABEL [--target-files ZIP --otatools ZIP] [--break-boot] [--tree DESC] [--out DIR]}; shift
TF=; OT=; BREAK=0; TREE=; O=$A/ota/out
while [ $# -gt 0 ]; do
  case $1 in
    --target-files) TF=$(realpath "$2"); shift 2 ;;
    --otatools) OT=$(realpath "$2"); shift 2 ;;
    --break-boot) BREAK=1; shift ;;
    --tree) TREE=$2; shift 2 ;;
    --out) O=$(realpath -m "$2"); shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
B=$A/ota/builds/$LABEL; mkdir -p "$B" "$O" "$A/logs/ota"
exec > >(tee -a "$A/logs/ota/make-$LABEL.log") 2>&1
echo "== make-ota $LABEL $(date -u +%FT%TZ)"
t0=$(date +%s)

# ---- 1. the inputs
if [ -z "$TF" ]; then
  [ -z "$TREE" ] && TREE=$(grep -h "synced device/anybook from /repo" "$(ls -t "$A"/logs/aosp/build-*.log | head -n 1)" |
    tail -n 1 | sed 's/.*(AnyBook \(.*\))/\1/')
  # `m otatools-package` leaves the zip in its intermediates (out/dist/ only with `dist`).
  flock "$A/aosp/.lane.lock" bash -c "set -e
    tf=\$(ls -t '$P'/obj/PACKAGING/target_files_intermediates/*-target_files*.zip | head -n 1)
    ot=\$(ls -t '$A'/aosp/src/out/host/linux-x86/obj/ETC/otatools-package*_intermediates/otatools-package* \\
                '$A'/aosp/src/out/dist/otatools.zip 2>/dev/null | head -n 1)
    cp --reflink=auto \"\$tf\" '$B/target_files.zip'; cp --reflink=auto \"\$ot\" '$B/otatools.zip'
    echo \"snapshot: \$tf (\$(stat -c %y \"\$tf\")), \$ot\""
  TF=$B/target_files.zip; OT=$B/otatools.zip
fi
[ -f "$TF" ] && [ -f "$OT" ] || { echo "target files or otatools missing" >&2; exit 1; }
rm -rf "$B/otatools"; mkdir -p "$B/otatools"; unzip -q "$OT" -d "$B/otatools"
export PATH="$B/otatools/bin:$A/aosp/src/prebuilts/jdk/jdk21/linux-x86/bin:$PATH"
X=(--path "$B/otatools")
# The target files name their keys relative to the AOSP tree (external/avb/test/data/..., build/make/target/product/
# security/testkey): the tools run from there, reading only.
cd "$A/aosp/src"

# ---- 2. the test-only broken copy
if [ $BREAK = 1 ]; then
  W=$B/break; rm -rf "$W"; mkdir -p "$W"
  cp --reflink=auto "$TF" "$W/target_files.zip"
  (cd "$W" && unzip -q -o target_files.zip VENDOR_BOOT/vendor_cmdline 'META/*')
  echo "vendor_boot cmdline before: $(cat "$W/VENDOR_BOOT/vendor_cmdline")"
  printf '%s rdinit=/openbook-ota-test-no-such-init panic=5\n' "$(tr -d '\n' < "$W/VENDOR_BOOT/vendor_cmdline")" \
    > "$W/VENDOR_BOOT/vendor_cmdline"
  (cd "$W" && zip -q -d target_files.zip IMAGES/vendor_boot.img IMAGES/vbmeta.img &&
    zip -q target_files.zip VENDOR_BOOT/vendor_cmdline)
  add_img_to_target_files -a "$W/target_files.zip"
  TF=$W/target_files.zip
fi

# ---- 3. the package
OUT=$O/$LABEL.zip
rm -f "$OUT"
ota_from_target_files "${X[@]}" "$TF" "$OUT"

# ---- 4. manifest and bootsync
python3 - "$TF" "$OUT" "$O/$LABEL.json" "$O/$LABEL.bootsync" "$LABEL" "${TREE:-unknown}" "$BREAK" <<'EOF'
import hashlib, json, os, struct, sys, zipfile
tf, pkg, man, bs, label, tree, broken = sys.argv[1:8]
t = zipfile.ZipFile(tf)
props = {}
for name in ("SYSTEM/build.prop", "VENDOR/build.prop"):
    for l in t.read(name).decode(errors="replace").splitlines():
        if "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1)
            props.setdefault(k, v)
vb = t.read("IMAGES/vbmeta.img")
auth, aux = struct.unpack_from(">QQ", vb, 12)
b = t.read("VENDOR/bin/openbook-bootsync")
open(bs, "wb").write(b)
os.chmod(bs, 0o755)
h = hashlib.sha256()
with open(pkg, "rb") as f:
    for c in iter(lambda: f.read(1 << 22), b""):
        h.update(c)
z = zipfile.ZipFile(pkg)
meta = dict(l.split("=", 1) for l in z.read("META-INF/com/android/metadata").decode().splitlines() if "=" in l)
m = {"schema": "openbook-ota/1", "label": label, "tree": tree, "test_only_broken_boot": broken == "1",
     "fingerprint": meta.get("post-build") or props.get("ro.build.fingerprint"),
     "build_date_utc": int(props.get("ro.system.build.date.utc") or props.get("ro.build.date.utc") or 0),
     "device": meta.get("pre-device"), "bytes": os.path.getsize(pkg), "sha256": h.hexdigest(),
     "vbmeta_digest": hashlib.sha256(vb[:256 + auth + aux]).hexdigest(), "vbmeta_size": 256 + auth + aux,
     "payload_properties": z.read("payload_properties.txt").decode().splitlines(),
     "partitions": sorted(n[7:-4] for n in t.namelist() if n.startswith("IMAGES/") and n.endswith(".img")),
     "bootsync_sha256": hashlib.sha256(b).hexdigest(), "metadata": meta}
json.dump(m, open(man, "w"), indent=1)
print(json.dumps({k: m[k] for k in ("label", "tree", "fingerprint", "bytes", "sha256", "vbmeta_digest")}, indent=1))
EOF
echo "== $OUT ($(du -h "$OUT" | cut -f1)) in $(( $(date +%s) - t0 )) s"
