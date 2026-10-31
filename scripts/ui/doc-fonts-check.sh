#!/usr/bin/env bash
# Check the document fonts (ANAL-208) in the browser OpenBook ships: open scripts/ui/doc-fonts-test.html in the
# WebView shell (Browser2, org.chromium.webview_shell), full screen, served from this host through `adb reverse`.
# The page measures each font family's text width and POSTs it back. Also records what the framework and the
# filesystem say about the fonts, and the screen.
#
# usage: doc-fonts-check.sh SERIAL OUTDIR
#   OUTDIR gets report.json (the page's widths), screen.png, font-dump.txt (`cmd font dump`), fonts-files.txt,
#   fonts-xml.txt (the document families in /system/etc/fonts.xml), logcat-fonts.txt.
#   Then: scripts/ui/doc-fonts-metrics.py --report OUTDIR/report.json ... compares the widths with the fonts' metrics.
# Env: ADB (default ~/anybook/android-sdk/platform-tools/adb), DOCFONTS_PORT (default 18537)
set -euo pipefail
S=$1; O=$2; HERE=$(cd "$(dirname "$0")" && pwd)
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}; PORT=${DOCFONTS_PORT:-18537}
a(){ "$ADB" -s "$S" "$@"; }
mkdir -p "$O"; rm -f "$O/report.json"

python3 -I "$HERE/doc-fonts-serve.py" "$PORT" "$O/report.json" 180 & SRV=$!
trap 'kill $SRV 2>/dev/null || true; a reverse --remove tcp:$PORT >/dev/null 2>&1 || true' EXIT
a reverse tcp:"$PORT" tcp:"$PORT"
a logcat -c || true
a shell am force-stop org.chromium.webview_shell
a shell am start -W --windowingMode 1 -a android.intent.action.VIEW \
  -d "http://127.0.0.1:$PORT/doc-fonts-test.html?t=$(date +%s)" -n org.chromium.webview_shell/.WebViewBrowserActivity
wait $SRV; trap - EXIT
a reverse --remove tcp:"$PORT" || true
sleep 3
a exec-out screencap -p > "$O/screen.png"

a shell cmd font dump > "$O/font-dump.txt" 2>&1 || true
a shell 'ls -l /product/fonts/ /product/etc/fonts_customization.xml; cd /product/fonts && sha256sum *.ttf' \
  > "$O/fonts-files.txt" 2>&1 || true
a shell "grep -n -E '<alias name=\"(arial|times new roman|courier new|georgia|verdana|tahoma|comic sans ms)\"|product/fonts' \
  /system/etc/fonts.xml" > "$O/fonts-xml.txt" 2>&1 || true
a logcat -d -b all | grep -E 'SkFontMgr|FontListParser|FontCustomization|avc: denied.*font|isolated.*font' \
  > "$O/logcat-fonts.txt" || true
python3 -I -c 'import json,sys; r=json.load(open(sys.argv[1])); print(r["userAgent"]);
[print("%-22s %10.3f %10.3f" % (x["name"], x["w400"][0], x["w700"][0])) for x in r["results"]]' "$O/report.json"
