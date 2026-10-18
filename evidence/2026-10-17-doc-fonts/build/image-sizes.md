# Image sizes (bytes)

`main` = `b1-snap/{cf,g14}-base` (ANAL-202's snapshot of a `main` build, no B1 or B7). B1 only = ANAL-202's own Cuttlefish stage (`~/anybook/aosp/cf/b1`, built 2026-10-18 04:04 UTC, its 3 fonts). B1 + B7 = this branch.

| Product | Image | `main` | B1 only | B1 + B7 | B7's share |
|---|---|---|---|---|---|
| `anybook_cf_x86_64_pc` | `product.img` | 292,929,536 | 302,620,672 | 306,569,216 | **+3,948,544** |
| `anybook_cf_x86_64_pc` | `system.img` | 905,953,280 | 905,953,280 | 905,957,376 | **+4,096** |
| `anybook_cf_x86_64_pc` | `super.img` | 1,637,614,144 | — | 1,651,212,864 | — |
| `anybook_g14_x86_64` | `product.img` | 292,503,552 | — | 306,135,040 | (≈ the CF share: same `/product` content) |
| `anybook_g14_x86_64` | `system.img` | 695,439,360 | — | 695,443,456 | +4,096 (the only system change is `fonts.xml`) |
| `anybook_g14_x86_64` | `super.img` | 1,333,967,496 | — | 1,347,562,120 | — |

What B7 adds, file by file (`installed-files-product.json`, B1 only → B1 + B7): 17 fonts, 5,313,524 bytes; `fonts_customization.xml` +4,466; `NOTICE.xml.gz` +1,745. Nothing else in `/product` changes. In `/system`, `etc/fonts.xml` grows by 5,309 bytes. `product.img` grows less than the files because the partition is compressed.

The B1-only stage's `super.img` was de-sparsed by `assemble_cvd` (8 GiB), so it can't be compared.
