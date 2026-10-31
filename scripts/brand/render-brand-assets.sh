#!/usr/bin/env bash
# Generate OpenBook's own brand assets for the system image (ANAL-207): wallpapers and their predicted dynamic colour,
# the boot animation, the sound set and the pointer theme, all into assets/ (assets/README.md lists them). Every one is
# drawn or synthesised by the scripts here from the brand palette and mark; nothing is downloaded but the pinned Python
# packages (scripts/brand/requirements.txt), installed once into a venv in the host data dir.
#
# usage: render-brand-assets.sh [--check] [PART...]
#   PART: wallpapers monet bootanimation sounds pointer (default: all)
#   --check  render into a temporary directory and compare with the committed assets (check-brand-assets.py):
#            exit 1 if anything differs. Use it from a clean checkout to show the generators reproduce assets/.
# Needs: python3 (3.11+, with venv), ffmpeg with libvorbis (sounds). Env: OPENBOOK_HOME (default ~/anybook).
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); B=$R/scripts/brand
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; V=$A/tools-local/brand-venv
CHECK=0; [ "${1:-}" = --check ] && { CHECK=1; shift; }
PARTS=("$@"); [ ${#PARTS[@]} -gt 0 ] || PARTS=(wallpapers monet bootanimation sounds pointer)

# The venv, rebuilt when requirements.txt changes.
want=$(sha256sum "$B/requirements.txt" | cut -d' ' -f1)
if [ "$(cat "$V/.requirements.sha256" 2>/dev/null)" != "$want" ]; then
  rm -rf "$V"; mkdir -p "$(dirname "$V")"
  python3 -m venv "$V"
  "$V/bin/pip" install -q --disable-pip-version-check -r "$B/requirements.txt"
  echo "$want" > "$V/.requirements.sha256"
fi
PY=("$V/bin/python" -I)   # -I: only the venv and the scripts' own directory (brandlib.py) are importable

if [ $CHECK = 1 ]; then
  OUT=$(mktemp -d); trap 'rm -rf "$OUT"' EXIT
  # sounds.json is updated in place, so the check starts from an empty one
else
  OUT=$R/assets
fi
for p in "${PARTS[@]}"; do
  case $p in
    wallpapers)    "${PY[@]}" "$B/wallpapers.py" --out "$OUT/wallpapers" ;;
    monet)         [ -d "$OUT/wallpapers/2880x1800" ] || "${PY[@]}" "$B/wallpapers.py" --out "$OUT/wallpapers" >/dev/null
                   "${PY[@]}" "$B/monet.py" --out "$OUT/wallpapers/monet.json" "$OUT"/wallpapers/2880x1800/*.jpg >/dev/null
                   echo "$OUT/wallpapers/monet.json" ;;
    bootanimation) "${PY[@]}" "$B/bootanimation.py" --out "$OUT/bootanimation" ;;
    sounds)        "${PY[@]}" "$B/sounds.py" --out "$OUT/sounds" ;;
    pointer)       "${PY[@]}" "$B/pointers.py" --out "$OUT/pointer" ;;
    *) echo "unknown part: $p" >&2; exit 2 ;;
  esac
done
# The wallpaper picker's thumbnails (480 x 300) for the partner package, from the 2880 x 1800 renders.
if printf '%s\n' "${PARTS[@]}" | grep -qx wallpapers; then
  "${PY[@]}" - "$OUT/wallpapers" <<'EOF'
import os, sys
from PIL import Image
d = sys.argv[1]
os.makedirs(os.path.join(d, "thumbs"), exist_ok=True)
for f in sorted(os.listdir(os.path.join(d, "2880x1800"))):
    im = Image.open(os.path.join(d, "2880x1800", f)).convert("RGB").resize((480, 300), Image.Resampling.LANCZOS)
    im.save(os.path.join(d, "thumbs", f), "JPEG", quality=88, optimize=True)
EOF
fi
[ $CHECK = 1 ] && exec "${PY[@]}" "$B/check-brand-assets.py" "$OUT" "$R/assets"
exit 0
