# ANAL-203: background blur on the G14, with measured cost (2026-10-17)

The write-ups are `docs/googlebook-ui.md` §2.3 (what blur needs, the cost, the G14 thresholds) and `docs/graphics-amd.md`, "Background blur and the renderer properties" (who draws it; `ro.hwui.use_vulkan`, `debug.renderengine.vulkan` and `debug.renderengine.graphite_desktop_optin`).

**Change:** `ro.surface_flinger.supports_background_blur=1` in `device/anybook/g14/anybook_g14_x86_64.mk`. Nothing else under `device/` changes (`build/device-diff-stat.txt`), so the Cuttlefish product is unchanged.

## Results

| Check | Result | Files |
|---|---|---|
| Cuttlefish build from this branch | `anybook_cf_x86_64_pc-cp2a-userdebug`, exit 0, 1 min 38 s incremental. Booted in 24 s with `--vhost_user_vsock=true`: without it, a second Cuttlefish on the host (B3's) held the modem simulator's vsock port and `cvd create` failed | `build/cf-build.txt`, `build/cf-boot.log` |
| Cuttlefish properties | `ro.surface_flinger.supports_background_blur=1` (from `device/google/cuttlefish`), build date 23:06 UTC (this build) | `build/cf-getprop-blur.txt` |
| **Blur cost in Cuttlefish** (Radeon 610M, `gfxstream_guest_angle`) | 6 rounds, on and off alternating, 20 shade and 20 Quick Settings cycles each, plus a Settings scroll. Quiet pair (host load 14–27): SystemUI janky frames 3.6 % vs 4.6 % (shade), 0.8 % vs 0.9 % (Quick Settings); RenderEngine 2.8–4.0 ms per GPU-composed frame with blur, about 1,100 of 1,600–1,800 frames on the GPU (none without blur). Loaded pair (85–92): shade 16.9 % vs 8.1 %. Settings scroll: no blur effect | `cf/summary.md`, `cf/summary.csv`, `cf/blur-report.json`, `cf/rounds/` |
| Blur applied, and only when on | With blur on, one layer blurred, `VRI-NotificationShade`, radius 34. With blur off, none. No layer blurred with the panels closed, in any round | `cf/rounds/r*/shade/sf-blur-layers.txt`, `cf/rounds/r*/state.txt` |
| Screenshots | Quick Settings and the shade with blur on and off: the whole desktop behind the panel is blurred with blur on | `cf/screens/cmp-qs-on-off.png`, `cf/screens/cmp-shade-on-off.png` |
| Stability | No crash in the guest's logcat, no SurfaceFlinger, SystemUI or system_server restart, no amdgpu fault line on the host (`journalctl -k`, 23:09–23:42 UTC) | `cf/rounds/r*/state.txt` |
| First Cuttlefish run | One off round in which the shade stayed blurred (round 2), plus a Settings scroll with no frames (Settings' first start). Neither was reproduced by hand; the second run checks for both before every round | `cf-first-run/` |
| The graphics check's new `blur` part, in Cuttlefish | `GFX_PARTS='blur vk' GFX_QUICK=1 run.sh`: the blur part ran in 47 s, wrote `parts.jsonl`, put `disable_window_blurs` back as it found it, and `gfx-report.py` reported it (the `vk` part failed only because no dEQP payload was pushed) | `addon-cf/` |
| `live-report.py` on the owner's `anal176t` run | Same verdicts as before the change, plus `gfx_blur`: not in this run | (checked on a scratch copy) |
| **G14 product build** | `anybook_g14_x86_64-cp2a-userdebug` from `ddfec87`, exit 0, 5 min 38 s. `vendor/build.prop`: `ro.surface_flinger.supports_background_blur=1`. Disk image `openbook-g14-anal203.img` (sha256 `957046a4…`) made under the same lane lock | `build/g14-build-props.txt`, `build/g14-build.txt`, `build/openbook-g14-anal203.img.*` |
| **G14 image in QEMU** (SwiftShader) | Boot 36 s. After finishing OpenBook setup (a fresh image starts in it, with the shade disabled), Quick Settings with blur on: `backgroundBlurRadius=34`; with blur off: none. SystemUI `supportsBlursOnWindows: true`. `blur-check.sh` (sha256 matches the repo's) ran both rounds: blur applied, no restart. Cost on a CPU renderer: RenderEngine +7.3–7.8 ms per frame, SurfaceFlinger missed frames 18–22 % vs 1.5–2.4 % without blur. Crash buffer empty. 4 AVC denials, none from SurfaceFlinger or the blur path: keystore→gatekeeper, SystemUI's `bluetooth_lea_prop`, and the test's own shell reading `vendor.anybook.gpu.hal` | `qemu/` |
| First QEMU run | The image was still in OpenBook setup, so Quick Settings didn't open. Also, mksh couldn't create the heredoc's temp file in `/data/local` as the shell user. `blur-qemu.sh` now finishes setup first and sets `TMPDIR` | (not kept) |

The Cuttlefish verdicts in `cf/summary.md` use the G14 thresholds and fail `frame_cost` under the host's load, as expected for a 2-CU GPU behind gfxstream on a busy host. They pass on the quiet pair.

## Commands

```bash
# Cuttlefish: build and stage under the lane lock, then boot on B2's ports
flock ~/anybook/aosp/.lane.lock bash -c 'scripts/aosp-docker.sh /repo/scripts/aosp-build.sh anybook_cf_x86_64_pc-cp2a-userdebug'
CF_DEVICE=anybook_vsoc_x86_64 CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_NAME=anybook-cf-b2 CF_STAGE=~/anybook/aosp/cf/b2 \
  CF_ADB_PORT=16532 CF_WEBRTC_PORT=11532 CF_ARGS=--vhost_user_vsock=true scripts/cf-boot.sh up && scripts/cf-boot.sh wait
export ANDROID_ADB_SERVER_PORT=5132; adb connect 127.0.0.1:16532
BLUR_CYCLES=20 scripts/ui/blur-bench.sh 127.0.0.1:16532 OUT on off on off on off
scripts/ui/blur-report.py OUT
# The add-on part by hand
adb push scripts/graphics/gfx-run.sh /data/local/tmp/openbook-gfx/run.sh; adb push scripts/ui/blur-check.sh /data/local/tmp/openbook-gfx/
adb shell "GFX_PARTS=blur GFX_QUICK=1 sh /data/local/tmp/openbook-gfx/run.sh /data/local/tmp/gfx-out"
scripts/graphics/gfx-report.py PULLED_OUT
# G14 image in QEMU
scripts/g14-image.sh --label openbook-g14-anal203 && scripts/ui/blur-qemu.sh ~/anybook/installer/out/openbook-g14-anal203.img anal203-blur
```
