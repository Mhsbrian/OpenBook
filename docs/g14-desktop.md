# G14 desktop from USB: RADV swapchain fix, SELinux, live image (ANAL-176)

Status as of 2026-10-17. Goal: the OpenBook desktop on the GA403WR's panel, booted from USB, nothing written to internal disks. Evidence is in `evidence/2026-10-17-g14-desktop/`, starting with `SUMMARY.md`. Labels: **C** = confirmed (we ran it), **H** = hypothesis. **Nothing here has run on the G14 yet:** the owner checklist is in §6.

This builds on PR #38 (ANAL-199's follow-up to the first live boot: an ANGLE workaround for the crash and most of the SELinux labels) and PR #34/#37 (ANAL-190's live image tooling).

## 1. Result

| | |
|---|---|
| Root cause of the black screen | RADV 26.2.5 dereferences a null `VkDeviceMemory` when Android 17's libvulkan binds a swapchain image late (C, §2) |
| Reproduced off the laptop | the image's own RADV crashes with the G14's signature (`SIGSEGV`, fault addr `0x60`) on the build host's Radeon 610M (C) |
| Fix | three upstream Mesa commits backported to 26.2.5, plus one OpenBook patch for minigbm's modifier-less buffers (§3). The patched RADV passes 8 of 8 swapchain cases with 0 wrong pixels, both directions between RADV and radeonsi (C) |
| SELinux | the 22 distinct Android denials of live-001 are addressed by PR #38 and this branch, except 3 AOSP or kernel-side ones (§4). 24 of 24 G14 sysfs paths get their intended labels in the built policy (C) |
| Live image | `openbook-live-20261017-desktop2`: new "safe graphics" entries (Mesa GL instead of ANGLE), QEMU matrix in §5 |
| On the G14 | **not run yet** (device gate): owner steps in §6 |

## 2. The crash (C)

The tombstone in live-001 (`logcat-final.txt.gz`): `SIGSEGV`, fault addr `0x60`, in `vulkan.radv.so` under `vulkan::driver::AcquireNextImageKHR` ← ANGLE `WindowSurfaceVk::acquireNextSwapchainImage`. Symbolized with the unstripped build of the same BuildId (`evidence/.../radv-crash/symbolize.txt`), the faulting instruction is `mem->alloc_size` in `radv_BindImageMemory2`, with `mem` = NULL.

- **Why it is called.** libvulkan offers `VK_EXT_swapchain_maintenance1` to any driver with sync-fd fence import, and ANGLE then creates every window swapchain with `VK_SWAPCHAIN_CREATE_DEFERRED_MEMORY_ALLOCATION_BIT_EXT`. For such swapchains libvulkan creates unbound images and, at the first acquire of each gralloc buffer, calls `vkBindImageMemory2` with `memory = VK_NULL_HANDLE` and a `VkNativeBufferANDROID` in the chain (`frameworks/native/vulkan/libvulkan/swapchain.cpp`, `AcquireNextImageKHR`; `VK_ANDROID_native_buffer` spec version 8).
- **Who it hits.** Every EGL window surface under ANGLE: the boot animation, and HWUI in every app (HWUI defaults to SkiaGL here, `ro.hwui.use_vulkan` unset), so SystemUI and the launcher too. SurfaceFlinger itself composes offscreen and was fine (`Shader cache generated 97 shaders`).
- **Upstream.** Mesa main fixed it on 2026-09-16 (`f7a951028`, "radv/android: support deferred swapchain image binding", MR 44426, fixes `dEQP-VK.wsi.android.swapchain.create.image_swapchain_create_info`). No 26.2.x release has it.

## 3. Mesa: patches and test

`mesa/patches/upstream/*.patch`, applied by `scripts/mesa-android-build.sh`'s fetch step on top of the `mesa-26.2.5` pin with `git am` and a fixed committer and date (reproducible SHA `f30f204df44c`). `versions.txt` and the staged `PROVENANCE.txt` list them.

| Patch | Source | What |
|---|---|---|
| 0001 | upstream `15a3bb617` | fail image creation when the gralloc stride override fails (instead of keeping a wrong image) |
| 0002 | upstream `90b5425e8` | close the dup'ed dma-buf fd when the import fails |
| 0003 | upstream `f7a951028` | deferred swapchain image binding: keep the create info (`vk_android_init_deferred_image`), derive the layout from the `VkNativeBufferANDROID` at bind time, import and bind. One conflict in the AHB path resolved by hand |
| 0004 | **OpenBook** | gralloc buffers without an explicit modifier take RADV's BO-metadata path, with the metadata's swizzle mode forced |

**Why 0004.** Our minigbm amdgpu backend (ANAL-174) allocates tiled buffers through Mesa's GBM without modifiers. radeonsi picks the tiling and records it in the kernel BO metadata, gralloc reports `DRM_FORMAT_MOD_INVALID` (`0x00ffffffffffffff`), and amdgpu's display reads the metadata. RADV passed the invalid modifier on as an "explicit" layout and chose its own swizzle mode; and on its metadata path `radv_image_reset_layout()` cleared the swizzle mode that `radv_patch_surface_from_metadata()` had read, so `ac_compute_surface()` chose again. 0004 makes all three import paths (ANB at create, ANB at bind, AHB) use the metadata when gralloc has no modifier, forces that swizzle mode (GFX9 to GFX11.5, Android only), and checks gralloc's pitch. On the build host's GPU RADV's own choice happens to match radeonsi's (64 KiB `R_X`, swizzle 27); on gfx1150 it may not (H), and 0004 removes the dependence.

**Test** (`scripts/amd-android-hwtest.sh … swapchain`, new part of ANAL-174's harness): the image's own bionic, Mesa and minigbm in a container on the build host's Radeon 610M (RDNA2). For each size (2880×1800 the G14 panel, 1920×1200, 1000×600, 64×64) and each libvulkan path (create, deferred):
1. allocate through minigbm's gralloc0 with a window buffer's usage (`HW_RENDER | HW_TEXTURE | HW_COMPOSER`); minigbm reports modifier `INVALID`, BO swizzle 27;
2. wrap it as libvulkan does: `VkNativeBufferANDROID` at `vkCreateImage`, or `VkImageSwapchainCreateInfoKHR` then `vkBindImageMemory2(memory = NULL, VkNativeBufferANDROID → VkBindImageMemorySwapchainInfoKHR)`;
3. RADV copies a per-pixel pattern into it; radeonsi imports the dma-buf **without** a modifier (so it lays it out from the BO metadata, like the display) and reads it back;
4. radeonsi writes a second pattern; RADV copies it out.

| | create path | deferred path |
|---|---|---|
| Image's RADV (26.2.5) | 4/4 pass, 0 wrong pixels | **4/4 crash**: `SIGSEGV` fault addr `0x60` (the G14's signature) |
| Patched RADV (`MESA_OUT=…`) | 4/4 pass, 0 wrong pixels | 4/4 pass, 0 wrong pixels |

The vulkan, gles and gralloc parts pass as before. `MESA_OUT=<mesa out>/vendor` overlays a Mesa build on the image's `/vendor` (a reflinked copy), so a Mesa change is tested before it is in an image.

**ANGLE workaround from PR #38 stays.** `debug.angle.feature_overrides_disabled=supportsSwapchainMaintenance1` keeps ANGLE on the create path. With the patches both paths work (C on RDNA2); the create path additionally survives a failed gralloc query (it falls back to the metadata path, while the deferred path has to fail the bind), so it is the safer default for the first desktop boot (H). Native Vulkan apps that ask for deferred allocation now work too. Dropping the workaround is a one-line change once the G14 has shown both paths.

## 4. SELinux

`scripts/installer/avc-summary.py LIVE_DIR` splits a save-logs run's denials into the log helper (`scontext kernel`), what Android does for the helper (`tcontext kernel`, its files on the ESP) and the rest, which the enforcing entries would block. live-001: **66** Android denial lines in the kernel log, 22 distinct (source, target, class) in kernel log and logcat together, not counting `flags_health_check`, which only ran because system_server was crash-looping (`evidence/.../selinux/live-001-avc.md`).

| Denial (live-001) | Fixed by |
|---|---|
| bootanim, surfaceflinger, allocator, composer: GPU `uevent`/`vendor`, `drm` directory | #38 (PCI identity → `sysfs_gpu`), this branch (`drm` directory) |
| bootanim, surfaceflinger, system_server: `vendor_default_prop` | this branch: `vendor.mesa.*` and `vendor.minigbm.*` (Mesa's and minigbm's option lookups) → `vendor_graphics_option_prop`, readable by every `gpu_sphal_domain` but isolated apps |
| allocator: `default_prop` (`mesa.*`) | this branch: dontaudit, as for the composer |
| bootanim, allocator: `getattr /dev/dri/card0` | #38 (allocator allow), this branch (dontaudit for the other GPU users) |
| lights HAL, composer: `amdgpu_bl0` | #38 (`sysfs_leds`), this branch (composer access: drm_hwcomposer drives the backlight it found) |
| thermal HAL: Wi-Fi `hwmon5` | #38 |
| system_server: `asus::kbd_backlight`, HID `country` | #38 |
| init: `discard_max_bytes` on the stick | this branch: disk queues → `sysfs_openbook_block_queue`, writable by init |
| keystore → software Gatekeeper's `ISharedSecret` | **open**: AOSP forbids keystore that service type (known since ANAL-199) |
| init: `debugfs_bootreceiver_tracing` | **open**: init.rc enables a tracing event our GKI lacks; kernel lane |

**Why the enforcing entries stayed black: corrected in §9.** This section first guessed that unlabelled GPU sysfs files kept RADV from finding the GPU. The G14 runs of `desktop2` showed the real cause: the kernel was denied `firmware_load` on `/vendor/firmware`, so amdgpu never initialised under enforcing. The kernel-side denial had been filtered out with the log helper's own (§9).

**Checked without the laptop.** `scripts/sepolicy-label-check.py PRODUCT_OUT scripts/sepolicy-label-cases-g14.txt` resolves the G14's sysfs paths (from live-001 and its PCI topology) against the built `file_contexts` the way libselinux does: **24 of 24** as intended, including the neighbours that must stay unlabelled. It found one mistake on the way: NVMe namespaces have no `block/` directory in their path.

Expected on the next save-logs run (H): the kernel-log count drops from 66 to the open items above, a handful of lines.

## 5. Live image `openbook-live-20261017-desktop2`

Built with `scripts/installer-image.sh --label openbook-live-20261017-desktop2 --menu-timeout 10` from this branch's product build (clean commit; the record is in its `.build.json`). The menu shows for 10 seconds.

| Entry | Bootconfig adds | Use |
|---|---|---|
| OpenBook (default) | `openbook.live=1` | the live system, SELinux enforcing |
| OpenBook - save logs to this USB stick | `+ openbook.logs=1`, `selinux=permissive` | logs to the stick, then power-off |
| OpenBook - safe graphics (Mesa GL, no ANGLE) | `+ hardware.egl=mesa` | GLES on radeonsi directly; Vulkan stays RADV |
| OpenBook - safe graphics, save logs to this USB stick | both | the same, with logs |
| OpenBook - start fresh | `+ openbook.live_reset=1` | erase the stick's saved data |
| OpenBook - serial console | console, density 160 | VMs |

**QEMU/OVMF** (`scripts/installer/live-qemu.sh`, the same six cases as ANAL-190; `evidence/.../qemu/`): **37 of 39** checks pass, `sys.boot_completed=1` at 20.3 s uptime from the USB stick, the decoy NVMe unchanged. The two misses are the VM-only ones ANAL-190 also has: no power-off after the clean shutdown, and `screencap` timing out on the VM's display. The VM path runs SwiftShader under ANGLE, so neither the RADV fix nor the safe-graphics entries are exercised there; the VM screen shows "Display output is not active" (parked by the owner).

Denials on the VM path (`avc-summary.py` on the save-logs case): 41 Android lines in the kernel log and 8 distinct, down from 69 and 16 with the first build of this branch (`desktop1`, before `vendor.minigbm.*`). No `vendor_default_prop` is left. What remains is not G14-specific: the audio HAL's memfd (ANAL-199), the Bluetooth app aborting without a Bluetooth HAL (ANAL-179) and what `crash_dump` reads for it, SystemUI's `bluetooth_lea_prop`, `secure_element`'s dex cache, and the two open items in §4.

## 6. On the G14: owner checklist (`desktop3`)

`openbook-live-20261017-desktop3` carries the fixes from §9: the kernel may load firmware under enforcing (the black default entry), the GPU HALs are chosen before SurfaceFlinger starts, the screen stays on for 10 minutes, and every boot keeps its logcat on the stick for a later "save logs" boot.

1. **Write the image** (erases the stick; the reports on it are copied to the PC first):
   ```bash
   cd <a checkout of this repo>
   OPENBOOK_WRITE_CONFIRM=/dev/disk/by-id/usb-SanDisk_Ultra_<serial>-0:0 \
     scripts/installer/write-stick.sh ~/anybook/installer/out/openbook-live-20261017-desktop3.img \
     /dev/disk/by-id/usb-SanDisk_Ultra_<serial>-0:0
   ```
   Done when it prints `stick powered off: safe to unplug`.
2. **Boot "OpenBook"**, the default entry (Esc → USB stick → Enter). The first boot of a freshly written stick takes longer (it formats `/data` and unpacks the system on the stick). Expected: the boot animation, then the desktop. This entry never switches itself off. Use it; photograph the desktop. Note the time if anything goes black or freezes.
3. **Then one "save logs" boot** (↓ once, Enter). It brings back the logs of the earlier boots too (`prior-boots.tar.gz`), not only its own. It still powers off by itself about a minute after the desktop appears; that is the entry's design, not a crash.
4. Plug the stick into the PC and reply "stick attached", with the photos and anything that went wrong. The agent runs, read-only:
   ```bash
   scripts/installer/read-stick-logs.sh /dev/disk/by-id/usb-SanDisk_Ultra_<serial>-0:0
   python3 scripts/installer/avc-summary.py <data dir>/installer/g14/stick-<UTC>/live-NNN --json avc.json --md avc.md
   ```

`desktop2` (§5) is superseded: its default and safe-graphics entries cannot work on the G14 (§9).

**Acceptance** (from the issue): a photo of the desktop on the panel, `boot_completed=1` in the saved logs, the `live-report.py --expect g14` verdicts, and fewer than 66 denials by `avc-summary.py`'s kernel-log count.

**Unattended (device agent, ANAL-193/194):** the same as `docs/installer.md` §11.7, with `bootconfig-logs.img` or `bootconfig-safe-logs.img` as the base of the agent entry; `avc-summary.py --json` and `live-report.py` give machine-readable results.

## 7. Open items

- **gfx1150 itself** (H): every claim about RDNA 3.5 waits for the G14 run. The host GPU is RDNA2.
- **drm_hwcomposer's test-only commits fail with `EINVAL`** in live-001 whenever the pointer moved (hundreds of `Test-only seamless=0 ret=-22`), so SurfaceFlinger composes on the GPU instead. Not a blocker; a likely cause is the cursor plane rejecting a GBM-tiled cursor buffer (H). To look at once the desktop is up (`drm.debug` on the save-logs entry).
- **Wi-Fi** (no HAL, no `regulatory.db`): ANAL-179.
- **The two open denials** in §4.
- **The kernel power-off hang** after Android's clean shutdown (ANAL-190's QEMU runs): product side, still open.
- **Upstreaming 0004**: the metadata swizzle problem is general to RADV on Android with modifier-less gralloc; worth an upstream MR once the G14 has confirmed it.

## 8. Reproduce

```bash
scripts/mesa-android-build.sh fetch setup build install verify -- upstream     # applies mesa/patches/upstream
MESA_OUT=~/anybook/mesa/out/upstream/vendor scripts/amd-android-hwtest.sh "" <out> swapchain
scripts/graphics-amd-stage-mesa.sh                                              # -> vendor/anybook/mesa (+ PROVENANCE)
AOSP_JOBS=24 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug droid openbook_hals_test validatekeymaps
docker wait anybook-aosp-build                                                  # 45 s to 2.5 min incremental
python3 scripts/sepolicy-label-check.py ~/anybook/aosp/src/out/target/product/anybook_g14 scripts/sepolicy-label-cases-g14.txt
scripts/installer-image.sh --label openbook-live-20261017-desktop2 --menu-timeout 10
scripts/installer/live-qemu.sh ~/anybook/installer/out/openbook-live-20261017-desktop2.img live-20261017-desktop2
python3 scripts/installer/avc-summary.py evidence/2026-10-16-installer/g14-live/live-001
```

## 9. First G14 boots of `desktop2` and what they showed (2026-10-17)

The owner wrote `openbook-live-20261017-desktop2` at 01:05 UTC and booted the default entry (01:11, the first boot: `/data` formatted and APEXes decompressed), probably safe graphics, then "save logs" twice (01:17 and 01:19). Only "save logs" showed anything: the boot animation, then the desktop at 28 s (`evidence/2026-10-17-g14-desktop/g14-desktop2/`, including the device's own screenshot of the desktop at 2880×1800). Read back read-only with `read-stick-logs.sh`; the files are redacted.

| Finding | Evidence | Status |
|---|---|---|
| **Every enforcing boot was black because amdgpu could not load its firmware.** The kernel reads firmware straight from `/vendor/firmware` (`firmware_class.path`); since 6.x SELinux checks `system { firmware_load }` against the file's label, and AOSP only allows it for `kernel self` (ueventd's fallback). Permissive boots log it once and carry on. It also blocks the MT7925 Wi-Fi firmware | `avc: denied { firmware_load } … comm="modprobe" path="/vendor/firmware/amdgpu/psp_14_0_0_toc.bin" scontext=u:r:kernel …` in both runs, and already in the very first G14 boot (live-001 of 2026-10-16). bootstat: no boot before the first "save logs" ever reached `boot_completed` (`reboot,factory_reset` is bootstat's label for the first completed boot of a fresh `/data`) | **Fixed** (C, policy): `allow kernel openbook_vendor_fw_file:system firmware_load`. QEMU cannot show it (no firmware is loaded there) |
| **SurfaceFlinger could start before `ro.hardware.egl` was set** and abort ("couldn't find an OpenGL ES implementation"); init restarted it. Property triggers for values set at early-init only run after `on boot` | live-002 tombstone, SurfaceFlinger uptime 2 s; init's `QueueAllPropertyActions` | **Fixed**: the probe's rc queues an init event (`vendor-anybook-gpu-<hal>`) that runs before `early-fs` |
| "The screen went black and it turned off" after a few actions | Both sessions ended at 77 s: the save-logs helper's final capture 45 s after `boot_completed`, then its scheduled power-off. In live-002 the owner had just opened the wallpaper chooser (01:20:33) | By design of that entry (ANAL-190 is reworking the helper). The default entry has no such power-off |
| The screen turns off after 1 minute and the laptop sleeps (s2idle) | SettingsProvider default; ANAL-190's earlier stick showed `PM: suspend entry/exit` | **Changed**: 10 minutes on the desktop products |
| Bluetooth app aborts every few seconds (`HidlHci: assert failed: hci_ != nullptr`: no Bluetooth HAL) | 6 crashes per 45 s session | **ANAL-179** (Bluetooth HAL). RescueParty is off on userdebug, so it cannot reboot the machine |
| No `system` DMA-BUF heap: our GKI (and stock android17-6.18) has `CONFIG_DMABUF_HEAPS_SYSTEM` off; minigbm's BLOB buffers and Codec2 need it | 132 `Could not open DMA-BUF heap named: system` per session from the allocator | **Kernel lane**: build `system_heap` as a module. Video playback likely fails until then (H) |
| Touchpad: "Clock changed backwards" from the gesture library about 300 times per session | `HardwareStateConverter` passes the touchpad's `MSC_TIMESTAMP` scan clock, which likely restarts per touch (H) | **ANAL-178** (input) |
| Remaining denials after the fixes, by the corrected count | `avc-summary.py`: 29 and 22 lines (66 before), none blocking: the audio HAL's memfd, Gatekeeper's shared secret, `crash_dump`, SystemUI's `bluetooth_lea_prop`, `secure_element`, init's bootreceiver tracing | Known |

**No logs from the enforcing boots.** They saved nothing, so they had to be reconstructed from the next boots (bootstat, APEX state, FAT timestamps). From the next image on, `persist.logd.logpersistd=logcatd` keeps logcat with the kernel log in `/data/misc/logd` across boots (userdebug), and the save-logs helper's first capture archives it with tombstones, ANR traces and dropbox (`prior-boots.tar.gz`, unpacked by `read-stick-logs.sh` into `live-NNN/prior/`).

## 10. Sources (accessed 2026-10-17)

- Mesa: `f7a951028`, `15a3bb617`, `90b5425e8` on `main` (gitlab.freedesktop.org/mesa/mesa), MR 44426.
- AOSP 17 (`android17-release` tree in `~/anybook/aosp/src`): `frameworks/native/vulkan/libvulkan/swapchain.cpp` and `driver.cpp`, `frameworks/native/vulkan/include/vulkan/vk_android_native_buffer.h`, `external/angle/src/libANGLE/renderer/vulkan/SurfaceVk.cpp`, `frameworks/base/libs/hwui/Properties.cpp`, `system/sepolicy` (`gpu_sphal_use`, `vendor_restricted_prop`), `system/core/rootdir/init.rc` (`discard_max_bytes`), `external/minigbm/cros_gralloc` (gralloc0 `perform`, shared `libminigbm_gralloc`).
