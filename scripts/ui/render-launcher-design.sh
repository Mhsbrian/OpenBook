#!/usr/bin/env bash
# Render the launcher design (docs/launcher-design/index.html) to images with headless Chromium.
#
#   dp    1920x1200 dp at 1x   -> 1920x1200 PNG      (the QEMU image at 160 dpi)      <design>/png/
#   g14   1920x1200 dp at 1.5x -> 2880x1800 JPEG q92 (the G14 panel at 240 dpi)       <design>/g14/
#   walls All Apps over every OpenBook wallpaper, light and dark, tiled into <design>/png/wallpapers.png
#
# Fonts (Google Sans Flex: OFL-1.1; Material Symbols Rounded: Apache-2.0) are the ones scripts/quire/render-design.sh
# fetches into the host data dir. They are linked into docs/launcher-design/fonts/, which is gitignored.
# Renders are output, not source: they go to the design store, never into Git (CONTRIBUTING.md).
#
# usage: render-launcher-design.sh [dp|g14|walls|all] [SCREEN...]   default: all sizes, every screen, light and dark
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); D=$R/docs/launcher-design
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; F=$A/quire/fonts
O=${OPENBOOK_EVIDENCE:-$A/evidence/openbook}/design/launcher-design; mkdir -p "$O/png"
CHROME=${CHROME:-$(command -v chromium || command -v google-chrome || command -v chrome)}
SIZES=${1:-all}; shift || true
mkdir -p "$F"
GF=https://github.com/google/fonts/raw/main/ofl
[ -s "$F/GoogleSansFlex.ttf" ] || curl -sSLf -o "$F/GoogleSansFlex.ttf" "$GF/googlesansflex/GoogleSansFlex%5BGRAD,ROND,opsz,slnt,wdth,wght%5D.ttf"
[ -s "$F/MaterialSymbolsRounded.ttf" ] || curl -sSLf -o "$F/MaterialSymbolsRounded.ttf" \
  "https://github.com/google/material-design-icons/raw/master/variablefont/MaterialSymbolsRounded%5BFILL,GRAD,opsz,wght%5D.ttf"
ln -sfn "$F" "$D/fonts"

SCREENS=("$@")
[ ${#SCREENS[@]} -gt 0 ] || SCREENS=(desktop taskbar allapps allapps-focus allapps-search menu-desktop menu-taskbar overview overview-focus motion)

shot(){ # out query width height scale
  "$CHROME" --headless=new --disable-gpu --no-sandbox --hide-scrollbars --force-device-scale-factor="$5" \
    --window-size="$3,$4" --virtual-time-budget=5000 --screenshot="$1" "file://$D/index.html$2" 2>/dev/null
  echo "$1"
}
render_size(){ # dp|g14
  case $1 in
    dp)  OUT=$O/png; SC=1 ;;
    g14) OUT=$O/g14; SC=1.5 ;;
  esac
  mkdir -p "$OUT"
  for s in "${SCREENS[@]}"; do
    shot "$OUT/$s.png"      "?screen=$s"            1920 1200 "$SC"
    shot "$OUT/$s-dark.png" "?screen=$s&theme=dark" 1920 1200 "$SC"
    if [ "$1" = g14 ]; then
      for v in "$s" "$s-dark"; do magick "$OUT/$v.png" -quality 92 -sampling-factor 1x1 "$OUT/$v.jpg" && rm "$OUT/$v.png"; done
    fi
  done
}
render_walls(){ # All Apps over each wallpaper, cropped to the panel and the taskbar
  local T; T=$(mktemp -d); local tiles=()
  for w in bloom folio strata tide; do
    for th in light dark; do
      shot "$T/$w-$th.png" "?screen=allapps&theme=$th&wall=$w" 1920 1200 1 >/dev/null
      magick "$T/$w-$th.png" -crop 900x780+510+420 +repage -resize 50% "$T/tile-$w-$th.png"
      magick "$T/tile-$w-$th.png" -gravity north -background '#1B1B21' -fill '#fff' -font "$F/GoogleSansFlex.ttf" -pointsize 14 \
        -splice 0x24 -annotate +0+4 "$w · $th" "$T/tile-$w-$th.png"
      tiles+=("$T/tile-$w-$th.png")
    done
  done
  magick montage "${tiles[@]}" -tile 4x2 -geometry +8+8 -background '#1B1B21' "$O/png/wallpapers.png"
  echo "$O/png/wallpapers.png"; rm -rf "$T"
}
case $SIZES in
  dp|g14) render_size "$SIZES" ;;
  walls) render_walls ;;
  all) render_size dp; render_size g14; render_walls ;;
  *) echo "usage: $0 [dp|g14|walls|all] [SCREEN...]" >&2; exit 2 ;;
esac
