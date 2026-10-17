# `openbook-live-20261017-anal176s`: the G14 stick with PR #52 (ANAL-176, 2026-10-17)

This is the first image with PR #52's three fixes: vold leaves the live stick alone, no lock screen at boot, and no overlay planes (`../g14-anal178c/SUMMARY.md`). Otherwise it is the same as `anal178c`: built from `anal-176/live-stick-safety` at `f90e3ee`, which is `main` at `cc1f2a2` plus PR #52, with the same power and graphics check add-ons. It replaces `anal178c` on the stick. **Not run on the G14 yet.**

| | |
|---|---|
| Product | `m droid openbook_hals_test validatekeymaps` exit 0 in 3 min 06 s (`build/`). `aosp-docker.sh` held the AOSP lane lock from 12:54:17Z. The log shows the vold patch applied (`base 6d20a0078c2b + 1 patches -> HEAD 307fbdc3bb08`), the overlay rebuilt, and no other branch's patches in the tree |
| Snapshot | 12:57:44Z, 9 s after the build. No other build ran in between (no newer build log); the newest snapshot file is `super.img` from 12:57:24Z |
| Image | `installer-image.sh --label openbook-live-20261017-anal176s --menu-timeout 10 --no-xz`, repo `f90e3ee` clean: 2,968,518,656 bytes, sha256 `b556c18b…` before the add-ons (`image/before-addons.sha256`, `.build.json`) |
| Add-ons | `openbook-powercheck-anal178-c` (`scripts/power/add-to-live-stick.sh --image`, 6 files verified) and `openbook-gfxcheck-20261017` (`scripts/graphics/add-to-live-stick.sh --image`), as on `anal178c`. **Final sha256 `e3fbd5abb24607b123b11bcfa1dd4e2770a6c1b790878a958e24e92a8e70d141`** (`image/openbook-live-20261017-anal176s.sha256`) |
| QEMU/OVMF matrix on the final image | **40 of 40** (run `live-20261017-anal176s`), including the new "vold leaves the boot stick alone". Desktop4's run fails that check (37/40). This run's boot times (28.8 s) were host contention: back to back with `anal178c` under the same load, the logs case reached `boot_completed` at 17.8 s against 17.6 s (`qemu/ab-boot-time.md`) |
| The fixes at runtime (VM) | **vold:** `Not managing disk 8:0, which holds the running system's partitions` at coldboot; desktop4 scanned `disk:8,0` and gave up. **Lock screen:** dismissed 36 ms after boot showed it, and no timeout sleep; desktop4 went to sleep 10.6 s after the lock screen appeared, as on the G14. **drm_hwcomposer:** `ro.vendor.hwc.use_overlay_planes=false`; only the usual `Failed to rm fb` messages (4; desktop4: 6). Details: `qemu/fixes-in-qemu.txt`; the default entry's desktop at 60 s, no lock screen: `qemu/default-shot-60.png` |

The `vold` check reads the persisted logcat in `prior-boots.tar.gz` as well. vold decides at coldboot, which the logs case's logcat capture had already rotated out (its first line is 12:58:46.8Z, vold's message 12:58:47.1Z in the persisted log; the first try of this run read 39/40 for that reason).

**Needs the G14:** the storage notice gone, no black screen 10 s after the desktop, and whether the dropped frames (151 on `anal178c`) are gone with overlay planes off (H). The owner's checklist is in `docs/g14-desktop.md` §6.
