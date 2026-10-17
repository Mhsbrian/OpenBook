# `openbook-live-20261017-anal176t`: anal176s plus Bluetooth and app audio under enforcing (ANAL-176, 2026-10-17)

This is `anal176s` plus the two audio policy fixes from its G14 session (`../g14-anal176s/SUMMARY.md`):
- `bluetooth` may use the audio HAL's A2DP queue memfds, so Bluetooth no longer aborts when an audio device connects;
- `audioserver_tmpfs` is an `mlstrustedobject`, so apps targeting SDK 28+, such as the browser, can create audio tracks.

It was built from `anal-176/live-stick-safety` at `f364203` (`main` `cc1f2a2` plus PR #52), with the same power and graphics check add-ons. It replaces `anal176s`. **Not run on the G14 yet.**

| | |
|---|---|
| Product | `m droid openbook_hals_test validatekeymaps` exit 0 in 1 min 42 s (`build/`). The vold patch was applied (`307fbdc3bb08`) |
| Lane and snapshot | **One outer `flock` held the AOSP lane lock across the build and the snapshot.** `aosp-docker.sh` saw "the caller holds the AOSP lane lock", and `installer-image.sh` ran with `OPENBOOK_LANE_LOCK_HELD=1`. The build ended and the snapshot was taken at 14:07:32Z, so no other build could run in between. The snapshot's `super.img` is byte-identical to the build's |
| Policy in the image | The `vendor.img` behind that `super.img` (`precompiled_sepolicy`, extracted with `fsck.erofs`): `audioserver_tmpfs` is in `mlstrustedobject`. A neverallow probe for `bluetooth hal_audio_default_tmpfs:file { read write map getattr }` is reported violated, which proves the allow is there. `m selinux_policy` passed AOSP's neverallow checks |
| Image | `installer-image.sh --label openbook-live-20261017-anal176t --menu-timeout 10 --no-xz`, repo `f364203` clean: 2,968,518,656 bytes, sha256 `86f1e3c4…` before the add-ons |
| Add-ons | `openbook-powercheck-anal178-c` and `openbook-gfxcheck-20261017`, applied with their own appliers (`--image`). **Final sha256 `8ba0eff56ea66f54e97df4f202be618b302db63b7ee672e64640a6cc9c7c50c9`** |
| QEMU/OVMF matrix on the final image | **40 of 40** (run `live-20261017-anal176t`). First boot `boot_completed` at 15.3 s; "vold leaves the boot stick alone" passes (`8:0` not managed). No audio memfd denials in the logs case. The VM has no Bluetooth and no SDK 28+ app playing sound, so neither fix is exercised there |

**Needs the G14:**
- pair a Bluetooth audio device and play sound through it (Bluetooth must not crash);
- play a video with sound in the browser;
- everything from `anal176s`'s run, again: no storage notice, no lock-screen blackout, no dropped frames.
