# G14 desktop from USB: RADV swapchain fix, SELinux, live image (ANAL-176)

How the OpenBook desktop reaches the ASUS ROG Zephyrus G14 (GA403WR) panel from a live USB stick, under SELinux enforcing, with nothing written to the internal disks: the RADV fix behind the first black screen, the SELinux policy the hardware needs, the live image's boot entries, the fixes found on the laptop and what is still open. Labels: **C** = confirmed (we ran it), **H** = hypothesis. Section numbers are cited from other docs; keep them.

## 1. Current state

As of 2026-10-18:

| | |
|---|---|
| Desktop on the G14 | the default, enforcing entry reaches the desktop at about 28 to 31 s on a freshly written stick, and held for an hour with 0 failed frames (C, §14) |
| Root cause of the first black screen | RADV 26.2.5 dereferences a null `VkDeviceMemory` when Android 17's libvulkan binds a swapchain image late (C, §2) |
| Fix | three upstream Mesa commits backported to 26.2.5, plus one OpenBook patch for minigbm's modifier-less buffers (§3). The patched RADV passes 8 of 8 swapchain cases with 0 wrong pixels, both directions between RADV and radeonsi (C, on RDNA2) |
| Second black screen (enforcing only) | the kernel was denied `firmware_load` on `/vendor/firmware`, so amdgpu never initialised (C, fixed, §4) |
| SELinux | 24 of 24 G14 sysfs paths get their intended labels in the built policy (C); two denials stay open (§4) |
| Still to check on the laptop | Esc with the taskbar's All Apps open, smoothness above 60 fps (§6) |

## 2. The crash (C)

The first live boot's tombstone: `SIGSEGV`, fault addr `0x60`, in `vulkan.radv.so` under `vulkan::driver::AcquireNextImageKHR` ← ANGLE `WindowSurfaceVk::acquireNextSwapchainImage`. Symbolized with the unstripped build of the same BuildId, the faulting instruction is `mem->alloc_size` in `radv_BindImageMemory2`, with `mem` = NULL. The image's own RADV crashes the same way on the build host's Radeon 610M, so it reproduces off the laptop.

- **Why it is called.** libvulkan offers `VK_EXT_swapchain_maintenance1` to any driver with sync-fd fence import, and ANGLE then creates every window swapchain with `VK_SWAPCHAIN_CREATE_DEFERRED_MEMORY_ALLOCATION_BIT_EXT`. For such swapchains libvulkan creates unbound images and, at the first acquire of each gralloc buffer, calls `vkBindImageMemory2` with `memory = VK_NULL_HANDLE` and a `VkNativeBufferANDROID` in the chain (`frameworks/native/vulkan/libvulkan/swapchain.cpp`, `AcquireNextImageKHR`; `VK_ANDROID_native_buffer` spec version 8).
- **Who it hits.** Every EGL window surface under ANGLE: the boot animation, and HWUI in every app (HWUI defaults to SkiaGL here, `ro.hwui.use_vulkan` unset), so SystemUI and the launcher too. SurfaceFlinger itself composes offscreen and is not affected.
- **Upstream.** Mesa main fixed it on 2026-09-16 (`f7a951028`, "radv/android: support deferred swapchain image binding", MR 44426, fixes `dEQP-VK.wsi.android.swapchain.create.image_swapchain_create_info`). No 26.2.x release has it (as of 2026-10-17).

## 3. Mesa: patches and test

`mesa/patches/upstream/*.patch`, applied by `scripts/mesa-android-build.sh`'s fetch step on top of the `mesa-26.2.5` pin with `git am` and a fixed committer and date, so the patched HEAD is reproducible. `versions.txt` and the staged `PROVENANCE.txt` list them.

| Patch | Source | What |
|---|---|---|
| 0001 | upstream `15a3bb617` | fail image creation when the gralloc stride override fails (instead of keeping a wrong image) |
| 0002 | upstream `90b5425e8` | close the dup'ed dma-buf fd when the import fails |
| 0003 | upstream `f7a951028` | deferred swapchain image binding: keep the create info (`vk_android_init_deferred_image`), derive the layout from the `VkNativeBufferANDROID` at bind time, import and bind. One conflict in the AHB path resolved by hand |
| 0004 | **OpenBook** | gralloc buffers without an explicit modifier take RADV's BO-metadata path, with the metadata's swizzle mode forced |

A later patch, 0005 (YV12 hardware buffers), is described in `docs/graphics-amd.md`.

**Why 0004.** Our minigbm amdgpu backend (ANAL-174) allocates tiled buffers through Mesa's GBM without modifiers. radeonsi picks the tiling and records it in the kernel BO metadata, gralloc reports `DRM_FORMAT_MOD_INVALID` (`0x00ffffffffffffff`), and amdgpu's display reads the metadata. Unpatched RADV passes the invalid modifier on as an "explicit" layout and chooses its own swizzle mode; and on its metadata path `radv_image_reset_layout()` clears the swizzle mode that `radv_patch_surface_from_metadata()` read, so `ac_compute_surface()` chooses again. 0004 makes all three import paths (ANB at create, ANB at bind, AHB) use the metadata when gralloc has no modifier, forces that swizzle mode (GFX9 to GFX11.5, Android only), and checks gralloc's pitch. On the build host's GPU RADV's own choice happens to match radeonsi's (64 KiB `R_X`, swizzle 27); on gfx1150 it may not (H), and 0004 removes the dependence.

**Test** (`scripts/amd-android-hwtest.sh … swapchain`, part of ANAL-174's harness): the image's own bionic, Mesa and minigbm in a container on the build host's Radeon 610M (RDNA2). For each size (2880×1800 the G14 panel, 1920×1200, 1000×600, 64×64) and each libvulkan path (create, deferred):
1. allocate through minigbm's gralloc0 with a window buffer's usage (`HW_RENDER | HW_TEXTURE | HW_COMPOSER`); minigbm reports modifier `INVALID`, BO swizzle 27;
2. wrap it as libvulkan does: `VkNativeBufferANDROID` at `vkCreateImage`, or `VkImageSwapchainCreateInfoKHR` then `vkBindImageMemory2(memory = NULL, VkNativeBufferANDROID → VkBindImageMemorySwapchainInfoKHR)`;
3. RADV copies a per-pixel pattern into it; radeonsi imports the dma-buf **without** a modifier (so it lays it out from the BO metadata, like the display) and reads it back;
4. radeonsi writes a second pattern; RADV copies it out.

| | create path | deferred path |
|---|---|---|
| Unpatched RADV (26.2.5) | 4/4 pass, 0 wrong pixels | **4/4 crash**: `SIGSEGV` fault addr `0x60` (the G14's signature) |
| Patched RADV (`MESA_OUT=…`) | 4/4 pass, 0 wrong pixels | 4/4 pass, 0 wrong pixels |

`MESA_OUT=<mesa out>/vendor` overlays a Mesa build on the image's `/vendor` (a reflinked copy), so a Mesa change is tested before it is in an image.

**The ANGLE workaround stays** (`device/anybook/common/graphics-amd/graphics-amd.mk`). `debug.angle.feature_overrides_disabled=supportsSwapchainMaintenance1` keeps ANGLE on the create path. With the patches both paths work (C on RDNA2); the create path also survives a failed gralloc query (it falls back to the metadata path, while the deferred path has to fail the bind), so it is the safer default (H). Native Vulkan apps that ask for deferred allocation work too. Dropping the workaround is a one-line change once the G14 has shown both paths.

## 4. SELinux

The G14 needs policy that QEMU never exercises: real GPU, backlight, keyboard and firmware paths. The rules live under `device/anybook/common/*/sepolicy/`.

| What was denied | Rule |
|---|---|
| **kernel: `system { firmware_load }` on `/vendor/firmware`.** Since 6.x the kernel checks it against the firmware file's own label, and AOSP only allows it for `kernel self` (ueventd's fallback). Under enforcing, amdgpu never initialised and the screen stayed black; it also blocked the MT7925 Wi-Fi firmware. Permissive boots log it once and carry on | `allow kernel openbook_vendor_fw_file:system firmware_load` (`pc/sepolicy/vendor/kernel.te`) |
| bootanim, surfaceflinger, allocator, composer: GPU `uevent`/`vendor`, `drm` directory | PCI identity → `sysfs_gpu`; the `drm` directory |
| bootanim, surfaceflinger, system_server: `vendor_default_prop` | `vendor.mesa.*` and `vendor.minigbm.*` (Mesa's and minigbm's option lookups) → `vendor_graphics_option_prop`, readable by every `gpu_sphal_domain` but isolated apps |
| allocator: `default_prop` (`mesa.*`) | dontaudit, as for the composer |
| bootanim, allocator: `getattr /dev/dri/card0` | allow for the allocator, dontaudit for the other GPU users |
| lights HAL, composer: `amdgpu_bl0` | `sysfs_leds`, plus composer access (drm_hwcomposer drives the backlight it finds) |
| thermal HAL: Wi-Fi `hwmon5` | labelled |
| system_server: `asus::kbd_backlight`, HID `country` | labelled |
| init: `discard_max_bytes` on the stick | disk queues → `sysfs_openbook_block_queue`, writable by init |
| Bluetooth and app audio | see §12 |
| keystore → software Gatekeeper's `ISharedSecret` | **open**: AOSP forbids keystore that service type |
| init: `debugfs_bootreceiver_tracing` | **open**: init.rc enables a tracing event our GKI lacks; kernel side |

**Checked without the laptop.** `scripts/sepolicy-label-check.py PRODUCT_OUT scripts/sepolicy-label-cases-g14.txt` resolves the G14's sysfs paths (from its PCI topology) against the built `file_contexts` the way libselinux does: **24 of 24** as intended, including the neighbours that must stay unlabelled. Gotcha it caught: NVMe namespaces have no `block/` directory in their path.

**Reading denials** from a stick: `scripts/installer/avc-summary.py LIVE_DIR` (§10) splits them into the log helper's own, real kernel-side ones (firmware loads), ones Android services raise when answering the helper, and the rest, which the enforcing entries would block.

## 5. Live image boot entries

`scripts/installer-image.sh --label <label> --menu-timeout 10` builds the stick image from a product build (the record is in its `.build.json`). With `--menu-timeout 10` the menu shows for 10 seconds. Details of the image are in `docs/installer.md`.

| Entry | Bootconfig adds | Use |
|---|---|---|
| OpenBook (default) | `openbook.live=1` | the live system, SELinux enforcing |
| OpenBook - save logs to this USB stick | `+ openbook.logs=1`, `selinux=permissive` | saves logs to the stick, then shuts down |
| OpenBook - safe graphics (Mesa GL, no ANGLE) | `+ hardware.egl=mesa` | GLES on radeonsi directly; Vulkan stays RADV |
| OpenBook - safe graphics, save logs to this USB stick | both | the same, with logs |
| OpenBook - start fresh | `+ openbook.live_reset=1` | erase the stick's saved data |
| OpenBook - serial console | console, density 160 | VMs |

**QEMU/OVMF** (`scripts/installer/live-qemu.sh`): as of 2026-10-17, 37 of 39 checks pass, with `sys.boot_completed=1` at about 20 s from the USB stick and the decoy NVMe unchanged. The two misses are VM-only: no power-off after the clean shutdown, and `screencap` timing out on the VM's display. The VM path runs SwiftShader under ANGLE, so neither the RADV fix nor the safe-graphics entries are exercised there, and QEMU loads no firmware, so it cannot show the `firmware_load` denial.

## 6. On the G14: what is left

The enforcing desktop works on the laptop (§14). The next stick should show:
1. **Escape with the taskbar's All Apps open.** Press Esc while All Apps or a taskbar menu is open, and note it. Key presses are not logged; the launcher survived 35 taskbar-overlay sessions in the hour of §14, but whether Esc was among them is unknown.
2. **Smoothness at the panel's refresh rate.** Note any stutter or flicker, with the time, now that drawing is no longer capped at 60 fps (ANAL-212).
3. Audio items that are ANAL-179's (a notification sound and ringtone preview with #97, the headphone jack, reconnecting the headset; `docs/g14-audio-net.md` §11).
4. Power off from the menu, boot "save logs" once, and reattach the stick.

**Checking a stick's run:** `boot_completed=1` in the saved logs, the `live-report.py --expect g14` verdicts, and `avc-summary.py`'s counts (§10).

**Unattended (device agent, ANAL-193/194):** the same as `docs/installer.md` §11.7, with `bootconfig-logs.img` or `bootconfig-safe-logs.img` as the base of the agent entry; `avc-summary.py --json` and `live-report.py` give machine-readable results.

## 7. Open items

As of 2026-10-18:

- **MediaPlayer playback** (ringtones, notification sounds, Settings' previews, apps that use MediaPlayer). Decoding works on the laptop since ANAL-198's system DMA-BUF heap (#64). Playback failed with "Could not get control block": under enforcing, `mediaserver` may not map AudioFlinger's memfd (`audioserver_tmpfs`). PR #97 fixes it, shown in QEMU; the laptop check waits for a stick that carries it (`docs/g14-audio-net.md` §11).
- **Denials seen in an hour of use:**
  - `openbook_installd → sysfs_batteryinfo` (`/sys/class/power_supply/*/type`) and `→ openbook_vendor_fw_file` (dir search): the installer daemon on real hardware (ANAL-191).
  - `isolated_app → app_data_file:file setattr` on Chrome's `model-info.pb`, and `→ content_capture_service`; no visible effect (H).
- **A GPU reset restarts the whole UI** (§13).
- **gfx1150 itself** (H): the swapchain test (§3) runs on RDNA2 only. On the G14 the desktop runs on ANGLE's create path; the deferred path is not shown on RDNA 3.5 yet.
- **drm_hwcomposer and overlay planes.**
  - drm_hwcomposer puts more planes on the panel's stream than amdgpu's display core accepts (`MAX_SURFACES 4` in `dc.h`). Its test commits fail with `EINVAL` (`dc_state_add_plane: can not attach plane_state! Maximum is: 4`) up to once per frame, and some real commits failed too (`Failed to pin framebuffer with error -22`, then SurfaceFlinger `present failed`): frames never shown, in half-second bursts while dialogs opened.
  - `ro.vendor.hwc.use_overlay_planes=false` (`device/anybook/common/graphics-amd/graphics-amd.mk`) leaves the primary and cursor planes. On the G14 it brought failed frames to 0, and refused test commits to a dozen, all during display bring-up (C). The cost is GPU composition every frame.
  - Using overlay planes again needs drm_hwcomposer to respect the display core's plane limit.
- **The two open denials** in §4.
- **The kernel power-off hang** after Android's clean shutdown (seen in QEMU, ANAL-190): product side, open as of 2026-10-17.
- **Upstreaming 0004**: the metadata swizzle problem is general to RADV on Android with modifier-less gralloc; worth an upstream MR once the G14 has confirmed it.

## 8. Reproduce

```bash
scripts/mesa-android-build.sh fetch setup build install verify -- upstream     # applies mesa/patches/upstream
MESA_OUT=~/anybook/mesa/out/upstream/vendor scripts/amd-android-hwtest.sh "" <out> swapchain
scripts/graphics-amd-stage-mesa.sh                                              # -> vendor/anybook/mesa (+ PROVENANCE)
AOSP_JOBS=24 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug droid openbook_hals_test validatekeymaps
docker wait anybook-aosp-build                                                  # aosp-docker.sh holds the lane lock until it exits
python3 scripts/sepolicy-label-check.py ~/anybook/aosp/src/out/target/product/anybook_g14 scripts/sepolicy-label-cases-g14.txt
scripts/installer-image.sh --label <label> --menu-timeout 10
scripts/installer/live-qemu.sh ~/anybook/installer/out/<label>.img <run name>
scripts/installer/read-stick-logs.sh /dev/disk/by-id/usb-<stick> <dest>         # after a "save logs" boot; read-only
python3 scripts/installer/avc-summary.py <dest>/live-NNN
```

## 9. Fixes found on the G14

Problems that only the laptop showed, and what fixed them (C unless marked):

| Symptom | Cause | Fix |
|---|---|---|
| Every enforcing boot black | `firmware_load` denied, amdgpu never initialised | §4 |
| SurfaceFlinger aborts at boot ("couldn't find an OpenGL ES implementation"), init restarts it | SurfaceFlinger could start before `ro.hardware.egl` was set. Property triggers for values set at early-init only run after `on boot` | the GPU probe's rc queues an init event (`vendor-anybook-gpu-<hal>`) that runs before `early-fs` |
| First boot of a fresh stick sits on a black screen for about a minute | compressed APEXes are decompressed into `/data` first (34 s for 20 APEXes on the stick) | §11 |
| vold treats the boot stick as an unreadable USB drive, and SystemUI offers to set it up; that wizard formats the disk | vold `disk:8,0 failed to identify` | `aosp/patches/system/vold`: vold skips the disk holding the running system's partitions (it logs `Not managing disk 8:0`). The QEMU matrix checks it |
| Screen goes off 10 s after the desktop appears | the boot lock screen's display timeout (`activityTimeoutWM=10000`) | `config_disableLockscreenByDefault`: a lock screen only once a PIN, pattern or password is set |
| Screen off after 1 minute, then s2idle | SettingsProvider default | 10 minutes on the desktop products |
| **Esc kills the launcher** (taskbar and desktop gone until it restarts) when the taskbar overlay holds something other than All Apps | `TaskbarOverlayDragLayer.tryHandleEscapeKey` reads `getAppsView()`, a `findViewById`, without a null check | OpenBook Launcher commit `02be96c0` (formerly `aosp/patches/packages/apps/Launcher3` 0001). Esc with All Apps open is still to check (§6) |
| Frames never shown, refused test commits every frame | drm_hwcomposer's overlay planes | §7 |
| No `system` DMA-BUF heap (`Could not open DMA-BUF heap named: system`); minigbm's BLOB buffers and Codec2 need it | our GKI (and stock android17-6.18) has `CONFIG_DMABUF_HEAPS_SYSTEM` off | `system_heap.ko` (ANAL-198, #64) |
| Bluetooth app aborts every few seconds (`HidlHci: assert failed: hci_ != nullptr`) | no Bluetooth HAL | ANAL-179. RescueParty is off on userdebug, so it can't reboot the machine |
| Touchpad: "Clock changed backwards" from the gesture library, about 300 times a session | `HardwareStateConverter` passes the touchpad's `MSC_TIMESTAMP` scan clock, which likely restarts per touch (H) | ANAL-178 (input) |

## 10. Boot logs from the stick

- The "save logs" entries boot permissive, write the kernel log, logcat, system facts and a screenshot to `openbook/logs/live-NNN/` on the stick's FAT partition, then shut down. Their log helper runs in the kernel domain.
- Enforcing boots save nothing themselves. `persist.logd.logpersistd=logcatd` (`device/anybook/common/pc/pc.mk`, userdebug) keeps logcat with the kernel log in `/data/misc/logd` across boots, and the save-logs helper's first capture archives it with tombstones, ANR traces and dropbox (`prior-boots.tar.gz`).
- `scripts/installer/read-stick-logs.sh /dev/disk/by-id/usb-<stick> [DEST]` copies the logs to the host read-only, unpacks `prior-boots.tar.gz` into `live-NNN/prior/`, and runs `live-report.py` on each folder.
- `scripts/installer/avc-summary.py LIVE_DIR [--json OUT] [--md OUT]` separates the helper's own denials (`scontext kernel` from its processes), real kernel ones (modprobe, kworkers), ones induced by the helper (`tcontext kernel` or vfat), and Android's, which the enforcing entries would block. Gotcha: an early version counted only Android denials and so missed amdgpu's `firmware_load`, which is what kept every enforcing boot black.
- bootstat labels the first completed boot of a fresh `/data` `reboot,factory_reset`, which helps reconstruct boots that saved nothing.

## 11. First boot on a fresh stick

`PRODUCT_COMPRESSED_APEX := false` (`device/anybook/common/pc/pc.mk`), as Cuttlefish does. Why: a compressed APEX is decompressed into `/data` on the first boot of every fresh `/data`. On the stick that took 34 s for 20 APEXes, SurfaceFlinger started at 55 s, and nothing shows on the panel before SurfaceFlinger. A boot switched off during that wait leaves `/data` formatted but uncleanly closed, and the next boot does the setup again. With uncompressed APEXes the boot animation shows at about 17 s and the desktop at about 28 s on a freshly written stick (C).

## 12. Bluetooth and app audio under enforcing

Two rules in `device/anybook/common/pc/sepolicy/vendor/hal_audio_net.te`, both confirmed on the G14:
- **Bluetooth audio.** The audio HAL hands Bluetooth the A2DP data queue, a memfd of `hal_audio_default_tmpfs`, which Bluetooth may not use by default (`FAILED_TRANSACTION`, the Bluetooth app aborts when a headset connects). Fix: `allow bluetooth hal_audio_default_tmpfs:file { getattr map read write }`. With it, the headset bonds and A2DP connects with no abort.
- **App audio.** Apps run with MLS categories. AudioFlinger's control blocks are `s0` files (`audioserver_tmpfs`, because AOSP 17 does not enable `memfd_class`), so apps targeting SDK 28 and up may not write them (`Could not get control block`, no sound from the browser). Fix: `typeattribute audioserver_tmpfs mlstrustedobject`.

The rest of the audio work (HAL, routing, the jack) is in `docs/g14-audio-net.md`.

## 13. GPU hangs and resets

A GPU hang that ends in a MODE2 reset with VRAM lost takes the whole UI down: SystemUI aborts with `EGL_CONTEXT_LOST`, SurfaceFlinger with `Failed to create a valid texture`, and the framework restarts itself (zygote restart, SystemUI back within about 7 s). Seen on the G14 when a dEQP case hung the gfx ring (ANAL-177); any app that hangs the GPU would do the same. SurfaceFlinger can't survive losing VRAM, so this stays open (§7).

## 14. Measured on the G14

One hour of normal use on the default boot under enforcing (2026-10-18, ANAL-192's integrated stick, `main` at `81578c1` plus #83). The audio side is ANAL-179's (`docs/g14-audio-net.md` §11); the refresh rate is ANAL-212's.

| Area | Result |
|---|---|
| Desktop | 30.7 s on a freshly written stick (`sf_stop_bootanim: 30687`); vold leaves the stick alone; lock screen dismissed at boot; no sleep; clean shutdown after 58 min |
| Failed frames | **0** (`Failed to pin framebuffer`, `present failed`), and 0 refused test commits after bring-up (12 during it). No GPU reset |
| Stutter | Android's jank tracker flagged 4,973 frames inside UI animations as missed by SurfaceFlinger (legacy type `JANK_COMPOSER`). By its newer classification **4,769 of them are `JANK_NONE`**; only 138 are composer jank and 50 app jank. App frame times were ≤ 17 ms for 4,793 frames and over 67 ms for 7. The render rate was capped at 60 fps for 99.7 % of screen-on time; ANAL-212's #88 removes the cap |
| Launcher | `com.android.launcher3` started once and never died. Its taskbar overlay (All Apps, menus) closed 35 times without a crash. Esc presses are not logged |
| Bluetooth audio | A2DP connected and streamed for up to 26 min, 0 Bluetooth denials, 0 tombstones |
| Browser audio | Chrome and WebView Shell played to the speakers and over Bluetooth; 0 app `audioserver_tmpfs` denials (§12) |
| Crashes | 0 native crashes, 0 tombstones, 0 ANRs. 1 Java crash: the Wallpaper & style preview (`WallpaperPreviewActivity.requestFullscreen` NPE), ANAL-205's (#91) |
| Denials | 229 lines, 9 kinds: Gatekeeper's shared secret, SystemUI's Bluetooth properties, `system_server` `wifi_hal_prop` and the other known ones; `mediaserver → audioserver_tmpfs` (#97); the installer daemon and Chrome ones in §7 |
| Media decoding | 0 DMA-BUF heap errors and 0 decoder failures |

## 15. Sources (accessed 2026-10-17/18)

- Mesa: `f7a951028`, `15a3bb617`, `90b5425e8` on `main` (gitlab.freedesktop.org/mesa/mesa), MR 44426.
- AOSP 17 (`android17-release`): `frameworks/native/vulkan/libvulkan/swapchain.cpp` and `driver.cpp`, `frameworks/native/vulkan/include/vulkan/vk_android_native_buffer.h`, `external/angle/src/libANGLE/renderer/vulkan/SurfaceVk.cpp`, `frameworks/base/libs/hwui/Properties.cpp`, `system/sepolicy` (`gpu_sphal_use`, `vendor_restricted_prop`), `system/core/rootdir/init.rc` (`discard_max_bytes`), `external/minigbm/cros_gralloc` (gralloc0 `perform`, shared `libminigbm_gralloc`).
- AOSP 17, for §9 and §11: `build/make/core/product_config.mk` (`PRODUCT_COMPRESSED_APEX`), `device/google/cuttlefish/shared/device.mk` (sets it to false), `packages/apps/Launcher3/quickstep/src/com/android/launcher3/taskbar/overlay/TaskbarOverlayDragLayer.java` and `TaskbarOverlayContext.java` (`getAppsView()` is a `findViewById`, so it is null without All Apps).
- Kernel (android17-6.18): `drivers/gpu/drm/amd/display/dc/dc.h` (`MAX_SURFACES 4`), `dc/core/dc_state.c` (`dc_state_add_plane`).
- AOSP 17, for §9 and §12: `system/sepolicy/private/mls` (file write needs `l1 eq l2` or `mlstrustedobject`), `private/policy_capabilities` (no `memfd_class`), `private/app.te` (`appdomain audioserver_tmpfs`); `system/vold/VolumeManager.cpp` (`handleBlockEvent`), `frameworks/base/core/java/com/android/internal/widget/LockPatternUtils.java` (`isLockScreenDisabled`), `frameworks/base/packages/SystemUI/…/NotificationShadeWindowControllerImpl.java` (`config_lockScreenDisplayTimeout`), `external/drm_hwcomposer/drm/DrmDisplayPipeline.cpp` and `utils/properties.cpp` (`ro.vendor.hwc.use_overlay_planes`).
