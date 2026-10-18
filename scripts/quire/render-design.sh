#!/usr/bin/env bash
# Render the Quire design (docs/quire-design/index.html) to PNGs with headless Chromium.
#
# Two sizes, as the acceptance for ANAL-215 asks:
#   fhd   1920x1080 dp at 1x  -> 1920x1080 px PNG   (Cuttlefish, 160 dpi)        docs/quire-design/png/
#   g14   1920x1200 dp at 1.5x -> 2880x1800 px      (the G14 panel at 240 dpi)   docs/quire-design/g14/ as JPEG q92 4:4:4
#         (55 PNGs at 2880x1800 weigh 35 MB; the JPEGs 22 MB. Pass G14_PNG=1 to keep the PNGs instead.)
#
# Fonts (Google Sans, Google Sans Flex, Google Sans Code: OFL-1.1; Material Symbols Rounded: Apache-2.0) are fetched
# once into the host data dir and linked into docs/quire-design/fonts/, which is gitignored: they are never committed.
#
# usage: render-design.sh [fhd|g14|all] [SCREEN...]     default: all sizes, every screen, light and dark
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
if [ ${#SCREENS[@]} -eq 0 ]; then
  SCREENS=(idle invoke-shake invoke-key invoke-secure invoke-taskbar invoke-voice invoke-selection compose agent-picker streaming steps plan
           consent consent-command consent-system mirror mirror-paused done error signin background settings-help long-output
           code images no-agent offline)
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
case $SIZES in
  fhd|g14) render_size "$SIZES" ;;
  all) render_size fhd; render_size g14 ;;
  *) echo "usage: $0 [fhd|g14|all] [SCREEN...]" >&2; exit 2 ;;
esac
# gallery contact sheet (light + dark, every state), at 1x
[ ${#SCREENS[@]} -ge 20 ] && shot "$D/png/gallery.png" "?size=fhd" 2000 17000 0.5 || true
