# The owner's stick `openbook-live-20261018-anal192d` (2026-10-18)

Built on the coordinator's request (07:55Z). It replaces `anal198`, which was written to the stick on 2026-10-17 and never booted. Recipe: `docs/installer.md` §13.9, in one lane-lock hold. Everything here ran in QEMU/KVM + OVMF on image files, SELinux enforcing. **Nothing has run on the G14 yet.** The owner's checklist and the routing for "stick attached" are in `docs/installer.md` §13.12.

## What is on it
- **Built from `main` `81578c1` plus PR #83's commit,** as `7d9bc0a` (clean). It equals `main` `13a020c` apart from `docs/STATUS.md`. Product `anybook_g14_x86_64-cp2a-userdebug`; see `image/build-excerpt.txt` and `image/openbook-live-20261018-anal192d.build.json`.
  - #67 SoundPool, #68 `Boot####`, #70 `BootOrder` append.
  - B1–B7: #77, #72, #79, #73, #75, #81, #78.
  - #80, microG's system part.
  - Vulkan 1.4 (`4210688`), kernel `6.18.21-android17-5-gfbfdd65b0fd1`.
  - Spot checks in `PRODUCT_OUT`:
    - `ro.surface_flinger.supports_background_blur=1`;
    - `/product/media/bootanimation.zip`, 1,510,395 bytes;
    - 20 fonts in `/product/fonts`;
    - `ro.config.ringtone=OpenBook_Pages.ogg`;
    - `/system_ext/bin/openbook-addons`.
- **Add-ons** (`image/addons.log`):
  - the power check `openbook-powercheck-anal178-c`;
  - the ARM apps check (`anal192c`'s add-on);
  - the graphics check `openbook-gfxcheck-anal192d`, 82 MB, with the `blur` part (`image/openbook-gfxcheck-anal192d-addon.json`).

  The microG add-on is not on it: 108 MB doesn't fit next to the graphics check.
- **sha256** `db2a820354c0f78d697e8813ffa280a23daf1e4954a8840e2d91829847192fbb`, and `before-addons.sha256` (`65d6eb03…`).

## Results
| Run | Result | Here |
|---|---|---|
| Live stick matrix | **40/40** (first boot 29.3 s under two concurrent AOSP builds; not a timing measurement) | `live-qemu/` |
| Wizard, 8 cases (with `nvram-boot` and the three alongside cases for #68/#70) | **51/51** | `wizard-qemu/` |
| End to end | **79/79** | `e2e-qemu/` (`inspect/` has every disk state) |
| Graphics check | 6/6 steps; `blur` 46 s, both rounds; every part exits 0 or skips as designed | `addons-qemu/gfx-*` |
| ARM apps check | every verdict passes; arm64 probe 18/2 (known groups) | `addons-qemu/bridge-*` |
| Power check | vm 14/14, real 10/10 steps | `addons-qemu/power-*` |
| SELinux denials, all enforcing boots above | 0 groups with an OpenBook type (264 records in 10 AOSP/test-shell groups) | `avc/anal192d.md` |
| `write-stick.sh --dry-run`, owner's SanDisk Ultra | passes, nothing written | `image/write-stick-dry-run.log` (serial redacted) |

## Found
- **`main` could not build from a clean checkout since #81** (B6). `.gitignore`'s `*.zip` had kept the product's link to `assets/bootanimation/bootanimation.zip` out of the commit. Fixed in PR #83, which is merged.
- **The AOSP lane was held by two orphans for 24 minutes** (a `tee` that had inherited the lock fd, and a waiting `flock`), left by another run's interrupted `installer-image.sh`. That image had already been rebuilt, so the orphans were stopped by PID (`docs/installer.md` §13.12).

## Screens (`screens/`)
| File | What it shows |
|---|---|
| `1-boot-animation-30s-qemu-display.png` | B6's boot animation on the live stick |
| `2-live-installer-google-sans-qemu-display.png` | The installer's first screen, in Google Sans |
| `3-installed-desktop-folio-circles-clean-pins.png` | The installed system's desktop: the Folio wallpaper, circular icons, B5's five pins, no search bar. QEMU shows a hotseat rather than the taskbar |

The `qemu-display` frames have red and blue swapped back (`docs/installer.md` §12.7).
