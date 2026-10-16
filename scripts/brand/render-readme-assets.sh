#!/usr/bin/env bash
# Render the README / marketing art in assets/readme/ from assets/src/readme-art.html with headless Chromium.
# Inputs: the committed installer design renders (docs/installer-design/png/) and a real screenshot of our build
# (evidence/2026-10-16-desktop/desktop/screen-windows.png). Fonts (Roboto Flex OFL-1.1, Material Symbols Apache-2.0)
# are fetched once into the host data dir and linked into assets/src/fonts (gitignored); they are never committed.
#
# usage: render-readme-assets.sh            needs chromium (or google-chrome) and ImageMagick (magick)
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); S=$R/assets/src; O=$R/assets/readme
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; F=$A/installer/fonts
CHROME=${CHROME:-$(command -v chromium || command -v google-chrome || command -v chrome)}
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
mkdir -p "$F" "$O/icons"
[ -s "$F/RobotoFlex.ttf" ] || curl -sSLf -o "$F/RobotoFlex.ttf" \
  "https://github.com/google/fonts/raw/main/ofl/robotoflex/RobotoFlex%5BGRAD,XOPQ,XTRA,YOPQ,YTAS,YTDE,YTFI,YTLC,YTUC,opsz,slnt,wdth,wght%5D.ttf"
[ -s "$F/MaterialSymbolsRounded.ttf" ] || curl -sSLf -o "$F/MaterialSymbolsRounded.ttf" \
  "https://github.com/google/material-design-icons/raw/master/variablefont/MaterialSymbolsRounded%5BFILL,GRAD,opsz,wght%5D.ttf"
ln -sfn "$F" "$S/fonts"

shot(){ # out query width height scale
  "$CHROME" --headless=new --disable-gpu --no-sandbox --hide-scrollbars --allow-file-access-from-files \
    --default-background-color=00000000 --force-device-scale-factor="$5" --window-size="$3,$4" \
    --virtual-time-budget=5000 --screenshot="$1" "file://$S/readme-art.html$2" 2>/dev/null
}
jpg(){ # png -> progressive JPEG (gradients and screenshots compress far better than PNG at the same quality)
  magick "$1" -strip -interlace JPEG -sampling-factor 4:2:0 -quality "${3:-88}" "$2"
}

for t in light dark; do
  shot "$TMP/hero-$t.png"     "?art=hero&theme=$t"     1200 520 2 && jpg "$TMP/hero-$t.png"     "$O/hero-$t.jpg"
  shot "$TMP/showcase-$t.png" "?art=showcase&theme=$t" 1200 560 2 && jpg "$TMP/showcase-$t.png" "$O/showcase-$t.jpg"
  shot "$TMP/desktop-$t.png"  "?art=desktop&theme=$t"  1200 720 2 && jpg "$TMP/desktop-$t.png"  "$O/desktop-$t.jpg"
done
# GitHub social preview: 1280x640, under 1 MB (set it under Settings > General > Social preview).
shot "$TMP/social2x.png" "?art=social&theme=light" 1280 640 2 \
  && magick "$TMP/social2x.png" -filter Lanczos -resize 1280x640 "$TMP/social.png" && jpg "$TMP/social.png" "$O/social-preview.jpg" 92
# App icon (transparent PNG) and the feature icons used in the README highlights grid.
shot "$R/assets/brand/openbook-icon-512.png" "?art=appicon" 512 512 1
for g in desktop_windows memory apps usb verified_user science; do
  shot "$O/icons/$g.png" "?art=icon&glyph=$g" 96 96 2
done
magick mogrify -strip "$R/assets/brand/openbook-icon-512.png" "$O"/icons/*.png
ls -l "$O" "$O/icons" "$R/assets/brand"
