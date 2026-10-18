# ANAL-208 (B7): metric-compatible document fonts (2026-10-17/18)

The write-up is `docs/googlebook-ui.md` §2.1.1. The font files, their sources and checksums are in `device/anybook/common/desktop/fonts/documents/` (`README.md`).

## Results

| Check | Result | File |
|---|---|---|
| Which of Googlebook's 42 document fonts are public | 17 files, 7 families (Arimo, Tinos, Cousine, Gelasio, Comic Relief, Archivo Black, Archivo Narrow), all in google/fonts `47d54ca1`, the versions Googlebook ships. The other 25 files, 13 families, name `github.com/googlefonts/<name>` repositories that return 404 | `sources.md` |
| Arimo, Tinos, Cousine against Adobe's Helvetica, Times-Roman, Courier AFMs | 95 of 95 printable ASCII glyphs within AFM rounding, regular and bold (largest difference 0.24/1000 em). Roboto: 0 of 95; Noto Serif: 6 and 0 of 95 | `offline-metrics.md` |
| Does AOSP 17's font customization take aliases? | Yes. `FontCustomizationParser` reads `<alias>`, `FontListParser` lists them before the system's, and Typeface keeps the first. `cmd font dump` shows `arial → arimo` ahead of `arial → sans-serif` | `prototype/after/font-dump.txt` |
| Does WebView read it? | No. Chromium 145 uses Skia's `SkFontMgr_New_Android`, which parses only `/system/etc/fonts.xml` (paths relative to `/system/fonts`). So a small patch to the legacy `fonts.xml` is needed | `sources.md` |
| **Prototype** (`main` CF build plus the fonts and configs pushed, WebView 145): what each CSS name renders in | Before: Arial, Verdana, Tahoma, Comic Sans MS → Roboto; Times New Roman, Georgia → Noto Serif; Courier New → Cutive Mono. After: **Arial → Arimo, Times New Roman → Tinos, Courier New → Cousine, Georgia → Gelasio, Comic Sans MS → Comic Relief**, each within 0.015 px of the font's own widths on both strings, regular and bold. Verdana, Tahoma, `sans-serif`, `serif` and unstyled text unchanged | `prototype/metrics.md`, `prototype/{before,after}/screen.png` |
| Prototype, framework (`Typeface.create` + `Paint`) | Every Windows name within 1 px of its stand-in on both strings (Paint returns whole pixels) | `prototype/metrics.md` |
| **Both products build** (this branch: B1's 2 commits + B7, `9fc551f`) | `anybook_cf_x86_64_pc-cp2a-userdebug` 26:36, `anybook_g14_x86_64-cp2a-userdebug` 28:19, both `m exit 0`. The `frameworks/base` patch applied on its pin. Both install the same 20 fonts (B1's 3 + B7's 17), byte for byte the repo's; `fonts_customization.xml` is the committed file and `fonts.xml` the generator's output. `/product/etc/NOTICE.xml.gz` has each family's OFL text | `build/` |
| **Product build in Cuttlefish** (WebView 145) | Same as the prototype: **Arial → Arimo, Times New Roman → Tinos, Courier New → Cousine, Georgia → Gelasio, Comic Sans MS → Comic Relief**, within 0.015 px, regular and bold; Verdana and Tahoma → Roboto. Framework within 1 px. Boot 24 s, empty crash buffer, 0 denials | `product-cf/metrics.md`, `product-cf/screen.png` |
| **No regression in B1's families** (product build) | The four RRO values resolve to `google-sans*`; all 40 `google-sans*`/`variable-*` families load with their axes; `Typeface.create` of `google-sans`, `google-sans-text`, `google-sans-flex`, `variable-body-medium` measures within 1 px of the Google Sans instances fontTools computes, not Roboto. Settings renders in Google Sans | `product-cf/b1-*.txt`, `product-cf/b1-typeface.tsv`, `product-cf/ui/settings.png` |
| The typed check for the G14 (no host needed) | A 178-character `data:` URL typed into the browser's address bar shows Comic Sans MS, Courier New and Georgia in their stand-ins | `product-cf/owner-url.{txt,png}` |
| Image size | B7 alone (CF, against ANAL-202's B1-only build): `product.img` **+3,948,544 bytes** (17 files, 5,313,524 bytes, compressed), `system.img` **+4,096**. G14 B1 + B7 against `main`: `product.img` +13,631,488, `system.img` +4,096 | `build/image-sizes.md` |
| Prototype health | No crash except our own first probe run (before it loaded the font map); 0 SELinux denials | `prototype/logcat-crash.txt`, `prototype/denials.txt` |

## Files

- `offline-metrics.md`: per-glyph widths against the Core 14 AFMs, and each candidate font's width for the two test strings.
- `sources.md`: the primary sources behind the design, with dates.
- `build/`: `build-log-excerpt.txt` (the lane log's milestones), `image-sizes.md`, the image sizes of both products, the G14's font checksums.
- `product-cf/`: the product build in Cuttlefish.
  - `report.json`, `screen.png`, `metrics.md`, `typeface.tsv`: the WebView and framework checks.
  - `font-dump.txt` (`cmd font dump`), `fonts-xml.txt`, `fonts-files.txt`, `product-fonts.{txt,sha256}`, `logcat-fonts.txt`.
  - `b1-overlay.txt`, `b1-typeface.tsv`, `b1-expected.txt`: B1's families. `ui/settings.png`, `ui/ui-state.txt`; `ui/qsb-compare.png`: the search widget's "Google" is the same bitmap before ANAL-201, after it and with B7.
  - `owner-url.txt`, `owner-url.png`: the address-bar check for the G14.
  - `cf-boot.log`, `props-summary.txt`, `logcat-crash.txt` (empty), `denials.txt`.
- `prototype/`: the VM run on the `main` build (`b1-snap/cf-base`, no B1 or B7), before and after `scripts/ui/doc-fonts-push.sh`.
  - `before/`, `after/`: `report.json` (the test page's widths), `screen.png`; `after/` also `font-dump.txt`, `typeface.tsv`, `fonts-xml.txt`, `fonts-files.txt`.
  - `metrics.md`: which font each name got, before and after, in WebView and in the framework.
  - `cf-boot.log`, `props-summary.txt`, `remount.log`, `logcat-crash.txt`, `denials.txt`.

## Commands

```bash
# Offline: AFMs from Apache PDFBox a3bc49f7 (pdfbox/src/main/resources/org/apache/pdfbox/resources/afm/)
D=device/anybook/common/desktop/fonts/documents; F=$AOSP/out/target/product/anybook_vsoc_x86_64/system/fonts
scripts/ui/doc-fonts-metrics.py --fonttools $AOSP/external/fonttools/Lib --afm AFMDIR \
  --font arimo=$D/arimo/Arimo-VF.ttf --font tinos=$D/tinos/Tinos-Regular.ttf,$D/tinos/Tinos-Bold.ttf ... \
  --font roboto=$F/Roboto-Regular.ttf ... [--report LABEL=report.json] [--typeface LABEL=typeface.tsv]
# Cuttlefish (B7's ports)
export CF_DEVICE=anybook_vsoc_x86_64 CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_NAME=anybook-cf-b7 \
  CF_STAGE=~/anybook/aosp/cf/b7 CF_ADB_PORT=16537 CF_WEBRTC_PORT=11537 CF_OUT=<build or snapshot>
scripts/cf-boot.sh up && scripts/cf-boot.sh wait
export ANDROID_ADB_SERVER_PORT=5137; adb connect 127.0.0.1:16537
scripts/ui/doc-fonts-check.sh 127.0.0.1:16537 OUT/before
scripts/ui/doc-fonts-push.sh 127.0.0.1:16537 WORK          # prototype only: remount, push, reboot
scripts/ui/doc-fonts-check.sh 127.0.0.1:16537 OUT/after
scripts/ui/doc-fonts-typeface.sh 127.0.0.1:16537 OUT/after/typeface.tsv
scripts/cf-boot.sh down
```
