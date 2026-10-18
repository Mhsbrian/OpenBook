## Per-glyph widths against Adobe's Core 14 AFMs

Printable ASCII (U+0020–U+007E, 95 characters), advance widths in 1/1000 em. AFMs: Apache PDFBox `a3bc49f7`, `pdfbox/src/main/resources/org/apache/pdfbox/resources/afm/`.

| Font | Weight | Reference | Within 0.5/1000 em | Largest difference |
|---|---|---|---|---|
| arimo | 400 | Helvetica | 95 / 95 | 0.24 |
| arimo | 700 | Helvetica-Bold | 95 / 95 | 0.21 |
| tinos | 400 | Times-Roman | 95 / 95 | 0.24 |
| tinos | 700 | Times-Bold | 95 / 95 | 0.21 |
| cousine | 400 | Courier | 95 / 95 | 0.10 |
| cousine | 700 | Courier-Bold | 95 / 95 | 0.10 |
| roboto | 400 | Helvetica | 0 / 95 | 156.58 |
| roboto | 700 | Helvetica-Bold | 0 / 95 | 155.64 |
| noto-serif | 400 | Times-Roman | 6 / 95 | 359.08 |
| noto-serif | 700 | Times-Bold | 0 / 95 | 339.08 |

`Courier-Bold.afm` sha256 `1e86f0a949e316c08df32adc2fc2e2a92ed9902ffd54e3516e5a66a32db856da`
`Courier.afm` sha256 `e72833dda79161e3aaf385adfeb59c61c89a4a3e184f27d21c178056eea30e17`
`Helvetica-Bold.afm` sha256 `59ac93091bc7e76eb6baf60210526a4df88fe107dd5e13eb0ae70c9fc6d91fb9`
`Helvetica.afm` sha256 `5654761eab868ccb3080122accf13b4fb79edf37af09e1c57a881c35c334ee03`
`Times-Bold.afm` sha256 `37efa084183acfb06f45ad73bd75f6dd09b20d1e498c66ce1b9aa72b00db4ac7`
`Times-Roman.afm` sha256 `b6dbde33196ff61f051f8468fb81a0dece63997a80b7fba058e8295f49480026`

## Expected widths of the test strings at 100 px

The sum of advance widths (no kerning, no ligatures). String 1: `The quick brown fox jumps over the lazy dog 0123456789`. String 2: `WAVE Ivy, fjord; mmm iii (42%) & @#?!`.

| Font | Files | 400, string 1 (px) | 400, string 2 | 700, string 1 | 700, string 2 |
|---|---|---|---|---|---|
| arimo | `Arimo-VF.ttf` | 2562.695 | 1757.373 | 2723.096 | 1853.320 |
| tinos | `Tinos-Regular.ttf`, `Tinos-Bold.ttf` | 2352.344 | 1719.531 | 2458.447 | 1809.424 |
| cousine | `Cousine-Regular.ttf`, `Cousine-Bold.ttf` | 3240.527 | 2220.361 | 3240.527 | 2220.361 |
| gelasio | `Gelasio-VF.ttf` | 2539.551 | 1805.957 | 2930.566 | 2052.393 |
| comic-relief | `ComicRelief-Regular.ttf`, `ComicRelief-Bold.ttf` | 2709.082 | 1890.625 | 2858.984 | 2024.023 |
| archivo-black | `ArchivoBlack-Regular.ttf` | 3144.900 | 2073.000 | 3144.900 | 2073.000 |
| archivo-narrow | `ArchivoNarrow-VF.ttf` | 2106.000 | 1454.900 | 2233.200 | 1519.900 |
| roboto | `Roboto-Regular.ttf` | 2564.111 | 1695.215 | 2604.590 | 1731.982 |
| noto-serif | `NotoSerif-Regular.ttf`, `NotoSerif-Bold.ttf` | 2735.742 | 1880.225 | 2858.984 | 1976.025 |
| cutive-mono | `CutiveMono.ttf` | 3269.531 | 2240.234 | 3269.531 | 2240.234 |
| droid-sans-mono | `DroidSansMono.ttf` | 3240.527 | 2220.361 | 3240.527 | 2220.361 |

