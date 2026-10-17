# `openbook-live-20261017-desktop4`: desktop3 plus the fixes from its G14 boots (ANAL-176, 2026-10-17)

Why: `../g14-desktop3/SUMMARY.md` and `docs/g14-desktop.md` §10. Owner steps: `docs/g14-desktop.md` §6. **Not run on the G14 yet.**

| | |
|---|---|
| Changes vs desktop3 | `PRODUCT_COMPRESSED_APEX := false` (`device/anybook/common/pc/pc.mk`); Launcher3 Escape fix (`aosp/patches/packages/apps/Launcher3/0001-…`); product commit `ee244fc`. Save-logs helper: `prior_boots_rc` is the whole archive pipeline's status, plus `prior-boots.txt`, `prior_boots_bytes`, `prior_boots_capped` (`scripts/installer/prior-boots-test.sh` 6/6) |
| Image | 2,945,449,984 bytes (63 MB more than desktop3, the uncompressed APEXes), sha256 `93b0b3f465b75aa38764f9a50c6394921da9d345defb835ef7f7d605c45da3cd`; `.img.xz` 896,595,164 bytes, sha256 `c0fb0d30578754db97e56f8ad004e532c5bf06e552989c537b7ac2cb6041aefa`; repo `d29a89d`, clean (`image/`). Rebuilt from the same product snapshot (`--inputs`) after the save-logs helper's archive-status fix; the first build (`e5c15ca`, sha256 `bc94e48a…`, `image/first-build/`) was never handed out |
| Product build | `m` exit 0 in 8 min 36 s under the AOSP lane lock (`build/`). The log shows the Launcher3 patch applied (`base c612e6ece389 + 1 patches -> HEAD 21f6b66c1b7d`) |
| In the build | `system/apex/`: 38 `.apex`, 0 `.capex`; `apexd.config.compressed_apex=false` in `system/build.prop`; `Launcher3QuickStep.apk`'s `tryHandleEscapeKey` has the null check after `getAppsView()` (`dexdump`: `if-eqz` before `getSearchUiManager`) |
| QEMU/OVMF matrix | **37 of 39** for the rebuilt image (run `live-20261017-desktop4b`), the same as desktop3; the 2 misses are the known VM-only ones (no power-off after shutdown, `screencap` on the VM display). First boot `boot_completed` at 18.2 s. Save-logs case: `prior_boots_rc` 0, 1.9 MB, not capped, `prior-boots.txt` lists the four directories (`qemu/SUMMARY.md`, `qemu/logs/`). The first build's run, also 37/39 after the `df` fix, is in `qemu/first-build/` |
| First boot of a fresh stick | 0 APEX decompressions (desktop3: 28); SurfaceFlinger at 5.4 s instead of 19.9 s; `boot_completed` at 17.8 s instead of 27.9 s, back to back on an idle host (`qemu/first-boot-timing.md`). Measured on the first build; the product is the same |

**Provenance note.** The shared AOSP tree had ANAL-179's unmerged `hardware/interfaces` commit "OPENBOOK: audio: primary module's ALSA card and device from properties". It was committed by hand at 01:31Z, so it is also in desktop3. It changes nothing without `vendor.audio.primary.card`/`.device`, which this branch does not set and the G14 boot of desktop3 did not have. `scripts/aosp-patches.sh` now reports such projects (and resets other branches' script-applied patches) before every build.

**Cannot be shown here (needs the G14):**
- the enforcing default entry reaching the desktop;
- the first boot's time on the stick (expected 35 to 40 s sooner than desktop3, H);
- Escape no longer killing the launcher. The patched code path needs the taskbar overlay open on a hardware keyboard.
