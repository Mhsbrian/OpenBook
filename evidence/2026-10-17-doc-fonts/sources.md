# Sources (read 2026-10-17)

## The fonts

- `github.com/google/fonts` at `47d54ca1ebb14fd864695f1d39dc734f39017c33` (2026-10-16, still `main` on 2026-10-17): `ofl/{arimo,tinos,cousine,gelasio,comicrelief,archivoblack,archivonarrow}`. Each `METADATA.pb` names the upstream project and commit; `device/anybook/common/desktop/fonts/documents/README.md` lists them with the checksums.
- `ofl/tinos` has no `OFL.txt` at that commit. It comes from `github.com/googlefonts/tinos` at `3b4482a99b80ea5fc75f187b1be3120a3f5905b3`, the commit `METADATA.pb` names. Its `DESCRIPTION.en_us.html` still says "Apache 2.0" from 2013; `METADATA.pb`, the font's `name` table and the project's `OFL.txt` all say OFL 1.1.
- The 13 unpublished families. The copyright strings in Googlebook's fonts (`scripts/gbos-inventory.py` output, `evidence/2026-10-17-gbos-ui/inventory/googlebook-ruby-fonts.tsv`) name `github.com/googlefonts/{arvos,arvos-black,arvos-narrow,codecs,comedic-sans,Gaumond,geotic,Tachyonic,tisane,trophis,velarium,whendings}`. `gh api repos/googlefonts/<name>` returned 404 for every one, `google/fonts` has no `ofl/<name>` for any, and GitHub and web searches found nothing.
- Adobe Core 14 AFMs (Helvetica, Helvetica-Bold, Times-Roman, Times-Bold, Courier, Courier-Bold) from Apache PDFBox `a3bc49f7a7de3c9f7ae30a68a239df41c6fdd819`, `pdfbox/src/main/resources/org/apache/pdfbox/resources/afm/`, with Adobe's `MustRead.html` ("may be used, copied, and distributed for any purpose"). Used for measurement only; not committed. Checksums in `offline-metrics.md`.

## How Android 17 reads font configs (AOSP, our pin)

- `frameworks/base/graphics/java/android/graphics/fonts/SystemFonts.java`: the framework reads `/system/etc/font_fallback.xml` (`FONTS_XML`) and `/product/etc/fonts_customization.xml` (`OEM_XML`, fonts in `/product/fonts/`). `fonts.xml` is `LEGACY_FONTS_XML`, read only by `getSystemPreinstalledFontConfigFromLegacyXml()`, which `Typeface.init()` uses to preload locale fonts in the zygote.
- `frameworks/base/graphics/java/android/graphics/fonts/FontCustomizationParser.java`: `<alias>` is read (`FontListParser.readAlias`).
- `frameworks/base/graphics/java/android/graphics/FontListParser.java` `readFamilies`: the customization's aliases start the list, then the system's; aliases to missing families are dropped.
- `frameworks/base/graphics/java/android/graphics/Typeface.java` `initSystemDefaultTypefaces`: "If alias and named family are conflict, use named family", and an alias name already in the map is skipped, so the first alias of a name wins.

## How WebView 145 reads them (Chromium `145.0.7632.218`, the WebView we ship)

- `skia/ext/font_utils.cc`: `BASE_FEATURE(kUseAndroidNDKFontAPI, base::FEATURE_DISABLED_BY_DEFAULT)`; without it, `SkFontMgr_New_Android(nullptr, ...)`. The WebView APK imports `ASystemFontIterator_*` but not `AFontMatcher_*`.
- Skia `748fb7de295843913a8fde5d6f8e550b3ebf545c` (Chromium 145's `skia_revision`):
  - `src/ports/SkFontMgr_android_parser.cpp` `GetSystemFontFamilies`: parses `/system/etc/fonts.xml` with base path `$ANDROID_ROOT/fonts/`. Nothing reads `fonts_customization.xml`, despite the comment about API 29. Alias names are lower-cased; an alias needs its family declared earlier.
  - `src/ports/SkFontMgr_android.cpp`: a font path is base path + file name; a family whose files don't open is dropped with its names; `onMatchFamily` lower-cases the request and returns the first family with that name.
- `third_party/blink/renderer/platform/fonts/skia/font_cache_skia.cc` `GetLastResortFallbackFont`: tries the generic family, then `Sans`, then `Arial`. That is why a family that exists nowhere now gets Arimo.
- `third_party/blink/renderer/platform/fonts/alternate_font_family.h`: Blink's own alternates, Arial↔Helvetica, Times↔Times New Roman, Courier↔Courier New, used when the asked-for family is missing.
- `android_webview/java/src/org/chromium/android_webview/AwSettings.java`: WebView's generic families are `sans-serif`, `serif`, `monospace`.
