## Document fonts

Metric-compatible stand-ins for the Windows and Office fonts that web pages and documents name, so text keeps its line breaks and layout (ANAL-208, `docs/googlebook-ui.md` §2.1). Installed to `/product/fonts`.

**Source:** `github.com/google/fonts`, commit `47d54ca1ebb14fd864695f1d39dc734f39017c33` (read 2026-10-17; the same commit as the desktop fonts in `..`). The files are unmodified. Only the variable fonts are renamed, because Soong reads the `[` in upstream's names as a glob. google/fonts has no `OFL.txt` for Tinos at that commit, so it comes from the Tinos project at the commit google/fonts names.

| Family | Stands in for | Upstream says | Upstream project (commit, from google/fonts `METADATA.pb`) |
|---|---|---|---|
| `arimo` | `arial` | "metrically compatible with Arial" | `googlefonts/arimo` `4a6255f2` |
| `tinos` | `times new roman` | "metrically compatible with Times New Roman" | `googlefonts/tinos` `3b4482a9` |
| `cousine` | `courier new` | "metrically compatible with Courier New" | `googlefonts/cousine` `c0fbdb43` (v1.241) |
| `gelasio` | `georgia` | "metrics compatible with Georgia in its Regular, Bold, Italic and Bold Italic weights" | `SorkinType/Gelasio` `9228e69b` |
| `comic-relief` | `comic sans ms` | "metrically equivalent to the popular Comic Sans MS" | `loudifier/Comic-Relief` `856315f5` (v1.2) |
| `archivo-black` | — | no metric claim | `Omnibus-Type/ArchivoBlack` `95df3c54` |
| `archivo-narrow` | — | no metric claim | `Omnibus-Type/ArchivoNarrow` `9793ec77` |

The quotes are from each family's `DESCRIPTION.en_us.html` in google/fonts, which matches the font's own `name` table. Googlebook also maps `arial black` and `arial narrow` to Archivo Black and Archivo Narrow. Their upstream makes no such claim, so here they are named families only.

| Here | Upstream (`ofl/…`) | Bytes | sha256 |
|---|---|---|---|
| `arimo/Arimo-VF.ttf` | `arimo/Arimo[wght].ttf` | 496268 | `e43898b143ec826ac8cb4034816458a7047fbe0836558de2a1f8c6223ae3e0ca` |
| `arimo/Arimo-Italic-VF.ttf` | `arimo/Arimo-Italic[wght].ttf` | 543196 | `a80fc54fd0233c1dfe298577c4d00f5ae81d5bb83510975e473c47e699b7f4ed` |
| `arimo/OFL.txt` | `arimo/OFL.txt` | 4384 | `11cce536cd2f3864d767003af5dcd739e2e15818cf2279b6175edeadd3960992` |
| `tinos/Tinos-Regular.ttf` | `tinos/Tinos-Regular.ttf` | 521588 | `60a0e8ef0c04dd5dd69ffe91025fa2ae5836cbd35600a82ba031977557e2cb61` |
| `tinos/Tinos-Italic.ttf` | `tinos/Tinos-Italic.ttf` | 565016 | `5942266ed398b155d7dc23e36833e7ec6be988f2439bdbeb8ef1bede808eaa91` |
| `tinos/Tinos-Bold.ttf` | `tinos/Tinos-Bold.ttf` | 597880 | `393269dbab8899f938db19783eca5eac92eb431f7ae0ab45b8349ca895f1a06b` |
| `tinos/Tinos-BoldItalic.ttf` | `tinos/Tinos-BoldItalic.ttf` | 578976 | `a5de79f0fe863ea0954757acb3d47b3ccd0a930ce3dd5b97230cd3866790a06e` |
| `tinos/OFL.txt` | `googlefonts/tinos` `3b4482a9` `OFL.txt` | 4383 | `cb3382d4643e8b02c12e322c220a3c76a5020d667e4fd4e7c75e744cca6caa6b` |
| `cousine/Cousine-Regular.ttf` | `cousine/Cousine-Regular.ttf` | 296856 | `1da22250675fc4c42fcf3a9736c44bc0570516105331443b663fd5cfbd1412fe` |
| `cousine/Cousine-Italic.ttf` | `cousine/Cousine-Italic.ttf` | 306880 | `ea2a76ae3d0ece9cd59f0d30fdc08dd70e8f5f457beee5b0852a7b50c2286c7c` |
| `cousine/Cousine-Bold.ttf` | `cousine/Cousine-Bold.ttf` | 298048 | `17c8a7245156d2253531c9e529474937b09d9f641c5ae7695c5e33f22822eef4` |
| `cousine/Cousine-BoldItalic.ttf` | `cousine/Cousine-BoldItalic.ttf` | 308292 | `848e858726fee0ae27b754e4cd6a2755209bf1428a8c91f747696d58c33906c3` |
| `cousine/OFL.txt` | `cousine/OFL.txt` | 4387 | `b81c4d4dc0a9f72c9155e78187316e016e2012a8102468804173dc61468b906d` |
| `gelasio/Gelasio-VF.ttf` | `gelasio/Gelasio[wght].ttf` | 168556 | `4daecea457258c9ebeb8bc99ed3fd24353618bfad3ea4b93fa0b5d0468fc04e4` |
| `gelasio/Gelasio-Italic-VF.ttf` | `gelasio/Gelasio-Italic[wght].ttf` | 174212 | `52559e845a4d33514e5f93bb9ae7dbeae1894a53f2c565a15f18af40cd337c09` |
| `gelasio/OFL.txt` | `gelasio/OFL.txt` | 4387 | `b393cb01867c919b44381512120dc3e4c954c7b47e2035c405f3a324799a4d29` |
| `comicrelief/ComicRelief-Regular.ttf` | `comicrelief/ComicRelief-Regular.ttf` | 80324 | `9ef4958ab06385d91f635f83a15569786b243f9d010cfb3f9a5cdda593c7bc22` |
| `comicrelief/ComicRelief-Bold.ttf` | `comicrelief/ComicRelief-Bold.ttf` | 94684 | `33aee007212b696afd57d50c901135cd723cd188f7ad98f3a1c572ea64e8f0d5` |
| `comicrelief/OFL.txt` | `comicrelief/OFL.txt` | 4396 | `009b3056cef5c9bcaff872bfb0e27fa4a0f8cc6f6984cc490caf5618748d766b` |
| `archivoblack/ArchivoBlack-Regular.ttf` | `archivoblack/ArchivoBlack-Regular.ttf` | 90988 | `dd9a89a019b4849f66ab75455fe7bdf931311042cbb0f0f97acc061539703180` |
| `archivoblack/OFL.txt` | `archivoblack/OFL.txt` | 4492 | `3173acd82f8c6159b5b1037b539fcbd4edff68e65c2ea8b9412b5a5ca97b08ff` |
| `archivonarrow/ArchivoNarrow-VF.ttf` | `archivonarrow/ArchivoNarrow[wght].ttf` | 93304 | `adbe027f625c8393ae0f6e174e32e233dda485bc3eda5153ce428275394ef97f` |
| `archivonarrow/ArchivoNarrow-Italic-VF.ttf` | `archivonarrow/ArchivoNarrow-Italic[wght].ttf` | 98456 | `147c09214be086bf1c70311ffb66f4f5a252e48f828f1d49e35ae56951016cc6` |
| `archivonarrow/OFL.txt` | `archivonarrow/OFL.txt` | 4495 | `b2087ef3fb91248e346600d19021249152a9688efea72905aa1996bb16a4c8de` |

The 17 font files total 5,313,524 bytes. Check them with `sha256sum`.

**License:** SIL Open Font License 1.1, with no Reserved Font Names. Each family's `OFL.txt` goes into the image's notices through the `license` modules in `Android.bp`.

**Not available:** Googlebook ships 13 more document families: Tachyonic, Velarium, Geotic, Tisane, Gaumond, Trophis, Codecs, Comedic Sans, Whendings 1–4 and Arvos (Black, Narrow). Each one's copyright string names a `github.com/googlefonts/<name>` project. On 2026-10-17 none of those repositories was public, google/fonts did not have them, and a web search found no release. They are not copied from Google's image. So Verdana and Tahoma have no metric-compatible stand-in yet, and render in the default sans-serif.

**How they are wired up** (`docs/googlebook-ui.md` §2.1):
- **Framework:** `../fonts_customization.xml` defines the families and the aliases. `scripts/ui/fonts-customization.py` writes it. AOSP 17's `FontCustomizationParser` reads `<alias>`, and Typeface keeps the first alias of a name it sees, which is the customization's.
- **WebView and Chrome:** their Skia reads only `/system/etc/fonts.xml`, so `aosp/patches/frameworks/base` declares the same families there and moves the aliases to them.
