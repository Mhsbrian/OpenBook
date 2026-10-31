## Desktop fonts

Google Sans and Google Sans Flex for the OpenBook desktop products (ANAL-202, `docs/googlebook-ui.md` §2.1).

**Source:** `github.com/google/fonts`, commit `47d54ca1ebb14fd864695f1d39dc734f39017c33` (read 2026-10-17). The files are unmodified; only the names differ, because Soong reads the `[` in upstream's names as a glob.

| Here | Upstream (`ofl/…`) | sha256 |
|---|---|---|
| `googlesans/GoogleSans-VF.ttf` | `googlesans/GoogleSans[GRAD,opsz,wght].ttf` | `d0a87d835a944b8b40d0e82a5651bb59ab97b936a2aeed5946eb57e7b2a3a90a` |
| `googlesans/GoogleSans-Italic-VF.ttf` | `googlesans/GoogleSans-Italic[GRAD,opsz,wght].ttf` | `b6662abd2131cad1b248750149a7f2b644f871ebcc9af7fe4cd1135cd290b6d1` |
| `googlesans/OFL.txt` | `googlesans/OFL.txt` | `2b75ef20f13d83a7514aee452c4782c20cdc9ff2dee17600f44d37a06d4fb958` |
| `googlesans/TRADEMARKS.md` | `googlesans/TRADEMARKS.md` | `215bc8c1ce46d1b81531f33ebb5af201e7a5da76b8f3ae4c705336fd70fc89e1` |
| `googlesansflex/GoogleSansFlex-VF.ttf` | `googlesansflex/GoogleSansFlex[ROND,opsz,slnt,wdth,wght].ttf` | `a9ac770798857d5e8ac593ced42b22e40a7c08cec98319f92b0eccc2783a77ba` |
| `googlesansflex/OFL.txt` | `googlesansflex/OFL.txt` | `fc13d69f63e36d284b6e383d4d1463d8ad404f0aa065e57cf961252d51063137` |
| `googlesansflex/TRADEMARKS.md` | `googlesansflex/TRADEMARKS.md` | `5cad381c0828db656f32a787a1eff76db3303c74ec4f94668ae9fc2873ffe42f` |

Check them with `sha256sum`.

**License:** SIL Open Font License 1.1, with no Reserved Font Names. Each family's `OFL.txt` goes into the image's notices through the `license` modules in `Android.bp`.

**Trademarks:** "Google", "Google Sans" and "Google Sans Flex" are trademarks of Google LLC (`TRADEMARKS.md`). OpenBook uses `google-sans*` only as internal font-family names that refer to these original fonts. No OpenBook product, brand or UI text uses the names. The owner approved this on ANAL-201 (2026-10-17).

**`fonts_customization.xml`** is written by `scripts/ui/fonts-customization.py`, and `fonts-customization.py` here links to it. The build fails if the committed file differs from the generator's output. After changing the script:

```bash
scripts/ui/fonts-customization.py > device/anybook/common/desktop/fonts/fonts_customization.xml
```
