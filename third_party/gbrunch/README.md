# GBRUNCH emulator research inputs

Unmodified files from `danbyumagic/gbrunch` commit
`a8936fd33e50efda3f1b36e332ab30b67b709ab1`, reviewed 2026-10-19:

- `patches/qemu11-gfni.patch`
- `tools/test_gfni.c` (also checks VPCLMULQDQ)
- `tools/test_vnni.c`
- `LICENSE`

The patch applies to QEMU v11.1.2,
`4fc49f46dc95d4a27de2509e7fceb2931e91faeb`. QEMU retains its upstream
GPL licensing (`QEMU-COPYING`); the full QEMU source and licenses remain in the local build
directory. GBRUNCH's notice is preserved here. This is experimental emulator
support, not a change to Google libraries or a substitute for hardware tests.

`scripts/googlebook/build-tcg.sh` builds and compares the supplied arithmetic
tests against this host's GFNI, VPCLMULQDQ and AVX512-VNNI/VL implementation.
Use a host advertising those features; these are not portable scalar tests.
