#!/usr/bin/env bash
# Render the Quire design (docs/quire-design/index.html) to PNGs with headless Chromium.
#
# Two sizes, as the acceptance for ANAL-215 and ANAL-227 asks:
#   fhd   1920x1080 dp at 1x  -> 1920x1080 px PNG   (Cuttlefish, 160 dpi)        docs/quire-design/png/
#   g14   1920x1200 dp at 1.5x -> 2880x1800 px      (the G14 panel at 240 dpi)   docs/quire-design/g14/ as JPEG q92 4:4:4
#         (PNGs at 2880x1800 weigh ~0.7 MB each; the JPEGs ~0.4 MB. Pass G14_PNG=1 to keep the PNGs instead.)
#   walls the first moment and a finished task over each of the eight OpenBook wallpapers (light on light, dark on dark, no window behind),
#         cropped to the note and tiled into docs/quire-design/png/wallpapers.png, to judge the glass on every backdrop
#
# Fonts (Google Sans, Google Sans Flex, Google Sans Code: OFL-1.1; Material Symbols Rounded: Apache-2.0) are fetched
# once into the host data dir and linked into docs/quire-design/fonts/, which is gitignored: they are never committed.
#
# usage: render-design.sh [fhd|g14|walls|all] [SCREEN...]     default: all sizes, every screen, light and dark
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); D=$R/docs/quire-design
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; F=$A/quire/fonts
CHROME=${CHROME:-$(command -v chromium || command -v google-chrome || command -v chrome)}
SIZES=${1:-all}; shift || true
mkdir -p "$F"
GF=https://github.com/google/fonts/raw/main/ofl
[ -s "$F/GoogleSans.ttf" ]     || curl -sSLf -o "$F/GoogleSans.ttf"     "$GF/googlesans/GoogleSans%5BGRAD,opsz,wght%5D.ttf"
[ -s "$F/GoogleSansFlex.ttf" ] || curl -sSLf -o "$F/GoogleSansFlex.ttf" "$GF/googlesansflex/GoogleSansFlex%5BGRAD,ROND,opsz,slnt,wdth,wght%5D.ttf"
[ -s "$F/GoogleSansCode.ttf" ] || curl -sSLf -o "$F/GoogleSansCode.ttf" "$GF/googlesanscode/GoogleSansCode%5Bwght%5D.ttf"
[ -s "$F/MaterialSymbolsRounded.ttf" ] || curl -sSLf -o "$F/MaterialSymbolsRounded.ttf" \
  "https://github.com/google/material-design-icons/raw/master/variablefont/MaterialSymbolsRounded%5BFILL,GRAD,opsz,wght%5D.ttf"
ln -sfn "$F" "$D/fonts"

SCREENS=("$@")
if [ ${#SCREENS[@]} -eq 0 ]; then   # keep in step with ORDER in quire.js
  SCREENS=(idle invoke-shake invoke-key open invoke-taskbar invoke-secure invoke-voice invoke-selection compose agent-picker streaming
           steps setting-undo plan confirm-destructive consent-command consent-system mirror mirror-paused done stopped error signin
           background settings-help long-output code images no-agent offline glass-off)
fi

shot(){ # out query width height scale
  "$CHROME" --headless=new --disable-gpu --no-sandbox --hide-scrollbars --force-device-scale-factor="$5" \
    --window-size="$3,$4" --virtual-time-budget=5000 --screenshot="$1" "file://$D/index.html$2" 2>/dev/null
  echo "$1"
}
render_size(){ # size
  case $1 in
    fhd) OUT=$D/png;     W=1920; H=1080; SC=1;   Q="&size=fhd" ;;
    g14) OUT=$D/g14;     W=1920; H=1200; SC=1.5; Q="&size=g14" ;;
  esac
  mkdir -p "$OUT"
  for s in "${SCREENS[@]}"; do
    shot "$OUT/$s.png"      "?screen=$s$Q"            "$W" "$H" "$SC"
    shot "$OUT/$s-dark.png" "?screen=$s&theme=dark$Q" "$W" "$H" "$SC"
    if [ "$1" = g14 ] && [ -z "${G14_PNG:-}" ]; then
      for v in "$s" "$s-dark"; do magick "$OUT/$v.png" -quality 92 -sampling-factor 1x1 "$OUT/$v.jpg" && rm "$OUT/$v.png"; done
    fi
  done
}
render_walls(){ # the note over every wallpaper: open (the first moment) and setting-undo (a finished task), cropped to the note
  local T=$(mktemp -d); local tiles=()
  for w in bloom folio strata tide; do
    for th in light dark; do
      local q="&theme=$th&wall=$w&size=fhd&bare=1"
      shot "$T/open-$w-$th.png" "?screen=open$q" 1920 1080 1 >/dev/null
      shot "$T/undo-$w-$th.png" "?screen=setting-undo$q" 1920 1080 1 >/dev/null
      # the note sits at the pointer (1010,470) + (18,18); crop a 480x300 (open) and 480x400 (undo) window around it
      magick "$T/open-$w-$th.png" -crop 480x150+1000+470 +repage "$T/a.png"
      magick "$T/undo-$w-$th.png" -crop 480x330+1000+470 +repage "$T/b.png"
      magick "$T/a.png" "$T/b.png" -append -bordercolor none -border 0 "$T/tile-$w-$th.png"
      magick "$T/tile-$w-$th.png" -gravity north -background '#1B1B21' -fill '#fff' -font "$F/GoogleSans.ttf" -pointsize 16 -splice 0x28 -annotate +0+6 "$w · $th" "$T/tile-$w-$th.png"
      tiles+=("$T/tile-$w-$th.png")
    done
  done
  magick montage "${tiles[@]}" -tile 4x2 -geometry +8+8 -background '#1B1B21' "$D/png/wallpapers.png"
  echo "$D/png/wallpapers.png"; rm -rf "$T"
}
case $SIZES in
  fhd|g14) render_size "$SIZES" ;;
  walls) render_walls ;;
  all) render_size fhd; render_size g14; render_walls ;;
  *) echo "usage: $0 [fhd|g14|walls|all] [SCREEN...]" >&2; exit 2 ;;
esac
# gallery contact sheet (light + dark, every state), at 1x
[ ${#SCREENS[@]} -ge 20 ] && shot "$D/png/gallery.png" "?size=fhd" 2000 19500 0.5 || true
