# The G14 before (14:24Z, quire6, slot a) and after (14:28Z, quire7, slot b): `g14-adb.sh state`, counts only

| | Before | After |
|---|---|---|
| users, packages and their versions, the person's files (count and list hash) | same | same |
| settings | — | only `boot_count` and `global_color_palette_version` (boot counters) |
| slot, vbmeta | `_a`, `950ca34b…` | `_b`, `0c1bf76a…` (the package's) |
| all media entries (`media_files`) | 194 | 193 (−8 KiB, not the person's files) |

Quire was running after the boot (`pidof`), with no crash in the crash buffer.
