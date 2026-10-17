# `openbook-live-20261017-desktop4`: desktop3 plus the fixes from its G14 boots (ANAL-176, 2026-10-17)

Why: `../g14-desktop3/SUMMARY.md` and `docs/g14-desktop.md` §10. Owner steps: `docs/g14-desktop.md` §6. **Not run on the G14 yet.**

| | |
|---|---|
| Changes vs desktop3 | `PRODUCT_COMPRESSED_APEX := false` (`device/anybook/common/pc/pc.mk`); Launcher3 Escape fix (`aosp/patches/packages/apps/Launcher3/0001-…`); product commit `ee244fc` |
| Image | 2,945,449,984 bytes (63 MB more than desktop3, the uncompressed APEXes), sha256 `bc94e48adab4df8488757673098e80479f5446dbe512504f019c88a7be7ae9d4`; `.img.xz` 896,594,116 bytes, sha256 `0f44c04fb9ce7852d0ae4d8c0f7239bdfe5f6f62a492fbba2c95145305f87c5f`; repo `e5c15ca`, clean (`image/`) |
| Product build | `m` exit 0 in 8 min 36 s under the AOSP lane lock (`build/`). The log shows the Launcher3 patch applied (`base c612e6ece389 + 1 patches -> HEAD 21f6b66c1b7d`) |
| In the build | `system/apex/`: 38 `.apex`, 0 `.capex`; `apexd.config.compressed_apex=false` in `system/build.prop`; `Launcher3QuickStep.apk`'s `tryHandleEscapeKey` has the null check after `getAppsView()` (`dexdump`: `if-eqz` before `getSearchUiManager`) |
| QEMU/OVMF matrix | **37 of 39**, the same as desktop3; the 2 misses are the known VM-only ones (no power-off after shutdown, `screencap` on the VM display) (`qemu/SUMMARY.md`) |
| First boot of a fresh stick | 0 APEX decompressions (desktop3: 28); SurfaceFlinger at 5.4 s instead of 19.9 s; `boot_completed` at 17.8 s instead of 27.9 s, back to back on an idle host (`qemu/first-boot-timing.md`) |

**Provenance note.** The shared AOSP tree had ANAL-179's unmerged `hardware/interfaces` commit "OPENBOOK: audio: primary module's ALSA card and device from properties". It was committed by hand at 01:31Z, so it is also in desktop3. It changes nothing without `vendor.audio.primary.card`/`.device`, which this branch does not set and the G14 boot of desktop3 did not have. `scripts/aosp-patches.sh` now reports such projects (and resets other branches' script-applied patches) before every build.

**Cannot be shown here (needs the G14):**
- the enforcing default entry reaching the desktop;
- the first boot's time on the stick (expected 35 to 40 s sooner than desktop3, H);
- Escape no longer killing the launcher. The patched code path needs the taskbar overlay open on a hardware keyboard.
