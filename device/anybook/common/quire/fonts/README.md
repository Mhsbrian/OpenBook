# Fonts inside Quire (ANAL-219)

The note draws two fonts the system doesn't ship (docs/quire-design.md §4.1, §4.6). Both are in `app/res/font/`.

| File | Font | Licence | Source |
|---|---|---|---|
| `quire_code.ttf` | Google Sans Code 6.001, variable (wght), unmodified | SIL OFL 1.1, `OFL-GoogleSansCode.txt` | github.com/google/fonts, `ofl/googlesanscode/GoogleSansCode[wght].ttf`; sha256 `c9649573afcd966f61096b1e9c3c3115e7b54315ca2adf9839c6f8b17d5f8e1f` |
| `quire_symbols.ttf` | Material Symbols Rounded, cut to the note's 60 icons | Apache-2.0 (the module's licence) | github.com/google/material-design-icons, `variablefont/MaterialSymbolsRounded[FILL,GRAD,opsz,wght].ttf`; sha256 of the source `32e4011709e055596eb8d2dd0f7cb547b47c1d40ac9ecb8fad54f7f7eac202e7` |

`quire_symbols.ttf` is made by `tools/subset-icons.py`: weight 400, grade 0 and optical size 24 are pinned, the FILL axis is
kept, and only the icons' Private Use Area code points remain (no ligatures), 14 KB instead of 15 MB. The same script
writes `app/src/dev/openbook/quire/note/Icons.kt`. To add an icon, add its name to `ICONS` in the script and run:

```bash
device/anybook/common/quire/tools/subset-icons.py ~/anybook/quire/fonts/MaterialSymbolsRounded.ttf \
  device/anybook/common/quire/app/res/font/quire_symbols.ttf \
  device/anybook/common/quire/app/src/dev/openbook/quire/note/Icons.kt
```

The fonts are used, never named in the product (the same trademark reading as ANAL-202, `docs/googlebook-ui.md`).
