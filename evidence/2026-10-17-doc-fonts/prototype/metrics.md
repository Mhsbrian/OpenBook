## Prototype before (main, AOSP fonts): what the browser used for each name

Mozilla/5.0 (Linux; Android 17; AnyBook Cuttlefish x86_64 desktop Build/CP2A.260605.016; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/145.0.7632.218 Safari/537.36, devicePixelRatio 1. A match is a width within 0.05 px of that font's sum of advances.

| CSS font-family | 400, string 1 (px) | Font it matches | 700, string 1 (px) | Font it matches |
|---|---|---|---|---|
| Arial | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| Times New Roman | 2735.750 | noto-serif (+0.008) | 2858.984 | noto-serif (+0.000) |
| Courier New | 3269.531 | cutive-mono (+0.000) | 3269.531 | cutive-mono (+0.000) |
| Verdana | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| Georgia | 2735.750 | noto-serif (+0.008) | 2858.984 | noto-serif (+0.000) |
| Tahoma | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| Comic Sans MS | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| Arimo | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| Tinos | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| Cousine | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| Gelasio | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| Comic Relief | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| Archivo Black | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| Archivo Narrow | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| sans-serif | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| serif | 2735.750 | noto-serif (+0.008) | 2858.984 | noto-serif (+0.000) |
| monospace | 3240.531 | cousine (+0.004), droid-sans-mono (+0.004) | 3240.531 | cousine (+0.004), droid-sans-mono (+0.004) |
| OpenBookNoSuchFont | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |

## Prototype after (fonts pushed): what the browser used for each name

Mozilla/5.0 (Linux; Android 17; AnyBook Cuttlefish x86_64 desktop Build/CP2A.260605.016; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/145.0.7632.218 Safari/537.36, devicePixelRatio 1. A match is a width within 0.05 px of that font's sum of advances.

| CSS font-family | 400, string 1 (px) | Font it matches | 700, string 1 (px) | Font it matches |
|---|---|---|---|---|
| Arial | 2562.703 | arimo (+0.008) | 2723.109 | arimo (+0.014) |
| Times New Roman | 2352.344 | tinos (+0.000) | 2458.453 | tinos (+0.006) |
| Courier New | 3240.531 | cousine (+0.004), droid-sans-mono (+0.004) | 3240.531 | cousine (+0.004), droid-sans-mono (+0.004) |
| Verdana | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| Georgia | 2539.562 | gelasio (+0.012) | 2930.578 | gelasio (+0.012) |
| Tahoma | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| Comic Sans MS | 2709.094 | comic-relief (+0.012) | 2858.984 | comic-relief (+0.000) |
| Arimo | 2562.703 | arimo (+0.008) | 2723.109 | arimo (+0.014) |
| Tinos | 2352.344 | tinos (+0.000) | 2458.453 | tinos (+0.006) |
| Cousine | 3240.531 | cousine (+0.004), droid-sans-mono (+0.004) | 3240.531 | cousine (+0.004), droid-sans-mono (+0.004) |
| Gelasio | 2539.562 | gelasio (+0.012) | 2930.578 | gelasio (+0.012) |
| Comic Relief | 2709.094 | comic-relief (+0.012) | 2858.984 | comic-relief (+0.000) |
| Archivo Black | 3144.906 | archivo-black (+0.006) | 3144.906 | archivo-black (+0.006) |
| Archivo Narrow | 2106.000 | archivo-narrow (+0.000) | 2233.203 | archivo-narrow (+0.003) |
| sans-serif | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| serif | 2735.750 | noto-serif (+0.008) | 2858.984 | noto-serif (+0.000) |
| monospace | 3240.531 | cousine (+0.004), droid-sans-mono (+0.004) | 3240.531 | cousine (+0.004), droid-sans-mono (+0.004) |
| initial | 2564.125 | roboto (+0.014) | 2604.594 | roboto (+0.004) |
| OpenBookNoSuchFont | 2562.703 | arimo (+0.008) | 2723.109 | arimo (+0.014) |

## Prototype after (fonts pushed): what the framework used for each name

`Typeface.create(name)` and `Paint.measureText` at 100 px, subpixel, unhinted, kerning and ligatures off. Paint returns whole pixels, so a match is within 1 px on both strings.

| Family | Weight | String 1 (px) | String 2 (px) | Font it matches |
|---|---|---|---|---|
| arial | 400 | 2563 | 1758 | arimo (+0.305) |
| arial | 700 | 2723 | 1854 | arimo (-0.096) |
| times new roman | 400 | 2353 | 1720 | tinos (+0.656) |
| times new roman | 700 | 2459 | 1810 | tinos (+0.553) |
| courier new | 400 | 3241 | 2221 | cousine (+0.473), droid-sans-mono (+0.473) |
| courier new | 700 | 3241 | 2221 | cousine (+0.473), droid-sans-mono (+0.473) |
| verdana | 400 | 2565 | 1696 | roboto (+0.889) |
| verdana | 700 | 2605 | 1732 | roboto (+0.410) |
| georgia | 400 | 2540 | 1806 | gelasio (+0.449) |
| georgia | 700 | 2931 | 2053 | gelasio (+0.434) |
| tahoma | 400 | 2565 | 1696 | roboto (+0.889) |
| tahoma | 700 | 2605 | 1732 | roboto (+0.410) |
| comic sans ms | 400 | 2710 | 1891 | comic-relief (+0.918) |
| comic sans ms | 700 | 2859 | 2024 | comic-relief (+0.016) |
| sans-serif | 400 | 2565 | 1696 | roboto (+0.889) |
| sans-serif | 700 | 2605 | 1732 | roboto (+0.410) |
| serif | 400 | 2736 | 1881 | noto-serif (+0.258) |
| serif | 700 | 2859 | 1976 | noto-serif (+0.016) |
| monospace | 400 | 3241 | 2221 | cousine (+0.473), droid-sans-mono (+0.473) |
| monospace | 700 | 3241 | 2221 | cousine (+0.473), droid-sans-mono (+0.473) |

