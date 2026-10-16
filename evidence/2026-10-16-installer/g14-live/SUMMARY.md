# First OpenBook live boot on the G14 (ANAL-190, 2026-10-16)

The owner wrote `openbook-live-20261016a.img` to the SanDisk Ultra 62 GB stick with `scripts/installer/write-stick.sh` (verified read-back, sha256 `b50b6dfc…`, `write-stick.log`). They booted the GA403WR twice:
1. The default "OpenBook" entry: a black screen for 3 minutes. That entry saves no logs.
2. "OpenBook - save logs to this USB stick": a black screen with a **mouse pointer that the touchpad moved**. It powered itself off after the final capture.

The stick was read back read-only with `scripts/installer/read-stick-logs.sh`. Files here are redacted (MAC addresses, USB serials). `live-001/report.md` holds the verdicts (`live-report.py --expect g14`).

## What worked on the G14 (C)

| | |
|---|---|
| Boot chain | UEFI → systemd-boot → GKI 6.18.21 → first and second stage from USB (`second_stage_s` 3.5) |
| Live storage | `openbook-live-init` grew `userdata` from 1 GiB to 56.2 GiB and moved the backup GPT to the end of the 62 GB stick (`live-init-001.json`). `/data` is f2fs on the stick: 58,885,120 KiB, by-name links only on `sda` |
| Graphics | amdgpu drives `eDP-1` at 2880×1800 (`connected enabled`); backlight `amdgpu_bl0` 199500/399000; the HAL picked `amdgpu`: ANGLE on RADV, minigbm, drm_hwcomposer. SurfaceFlinger ran for the whole boot without crashing; the pointer was drawn and moved |
| Input | ELAN touchpad (`ASCE1206:00 04F3:3315 Touchpad`), `Asus Keyboard` |
| NVIDIA dGPU | both functions `D3cold`/`suspended` (`10de:2f58`, `10de:2f80`): the dGPU stays off without a driver |
| Power | battery `BAT1` 54 % discharging, AC adapter, UCSI USB-C; `amd-pstate-epp` active (`balance_performance`), s2idle |
| Wi-Fi hardware | `mt7925e` loaded with its firmware; `wlan0` exists (down, because the product has no Wi-Fi service yet) |
| Modules | 139 loaded, amdgpu among them |

## What stopped it (C)

1. **The boot animation crashed in RADV:** `SIGSEGV` (null pointer, fault addr 0x60) in `vulkan.radv.so`, under `vulkan::driver::AcquireNextImageKHR` ← ANGLE `WindowSurfaceVk::acquireNextSwapchainImage` ← `GL_Clear` ← `BootAnimation::android`. It was not restarted (`init.svc.bootanim` stopped), so nothing but the pointer was drawn: the black screen. This is G14-only: VMs use SwiftShader. Owner: ANAL-199 / ANAL-174 (Android swapchain of Mesa RADV under ANGLE).
2. **The framework never started:** `system_server` was killed by its watchdog 5 times (7 starts), blocked in `AudioService` → `AudioSystem.setLowRamDevice`. `audioserver` waits for `IModule/default`, because `/vendor/etc/audio_policy_configuration.xml` is missing: the same cause as in QEMU. ANAL-199 has the fix in its build of 18:40 (its QEMU cycle 7), so this stick doesn't have it yet.
3. **SELinux:** this entry runs permissive. Of 394 denials in dmesg, 328 are the log helper itself (`u:r:kernel`, expected). **66 are Android services that the normal (enforcing) entry would block.** They're in `dmesg.txt.gz` for ANAL-199.
4. **No Wi-Fi service** (`cmd wifi status`: "Can't find service: wifi") and no `regulatory.db`: ANAL-199/179.

The screenshots (`screen-early.png`, `screen-final.png`) are black, as on the panel. SurfaceFlinger had no layers to show after the boot animation died.
