#!/usr/bin/env bash
# Render the OpenBook installer design (docs/installer-design/index.html) to PNGs with headless Chromium.
# Fonts (Roboto Flex, OFL-1.1; Material Symbols Rounded, Apache-2.0) are fetched once into the host data dir and
# linked into docs/installer-design/fonts/, which is gitignored: they are never committed.
#
# usage: render-design.sh [SCALE]   SCALE 1 (default) writes docs/installer-design/png/; SCALE 2 writes 2880x1800
#                                   copies to <data dir>/installer/design-2x/ for sharing
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); D=$R/docs/installer-design
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; F=$A/installer/fonts
SCALE=${1:-1}
CHROME=${CHROME:-$(command -v chromium || command -v google-chrome || command -v chrome)}
mkdir -p "$F"
[ -s "$F/RobotoFlex.ttf" ] || curl -sSLf -o "$F/RobotoFlex.ttf" \
  "https://github.com/google/fonts/raw/main/ofl/robotoflex/RobotoFlex%5BGRAD,XOPQ,XTRA,YOPQ,YTAS,YTDE,YTFI,YTLC,YTUC,opsz,slnt,wdth,wght%5D.ttf"
[ -s "$F/MaterialSymbolsRounded.ttf" ] || curl -sSLf -o "$F/MaterialSymbolsRounded.ttf" \
  "https://github.com/google/material-design-icons/raw/master/variablefont/MaterialSymbolsRounded%5BFILL,GRAD,opsz,wght%5D.ttf"
ln -sfn "$F" "$D/fonts"
if [ "$SCALE" = 1 ]; then OUT=$D/png; else OUT=$A/installer/design-${SCALE}x; fi
mkdir -p "$OUT"
shot(){ # name query width height
  "$CHROME" --headless=new --disable-gpu --no-sandbox --hide-scrollbars --force-device-scale-factor="$SCALE" \
    --window-size="$3,$4" --virtual-time-budget=4000 --screenshot="$OUT/$1.png" "file://$D/index.html$2" 2>/dev/null
  echo "$OUT/$1.png"
}
for s in welcome hardware choose disk confirm progress "done" boot; do shot "$s" "?screen=$s" 1440 900; done
for s in welcome disk progress; do shot "$s-dark" "?screen=$s&theme=dark" 1440 900; done
shot gallery "" 1600 2270
