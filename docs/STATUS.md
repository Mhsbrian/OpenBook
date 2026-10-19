# Status

## State of the union (2026-10-18, 15:20 UTC)

**Goal:** the Googlebook-style Android 17 desktop on the ASUS ROG Zephyrus G14 (GA403WR: Ryzen AI 9 HX 370, Radeon 890M), installed from a USB stick through a wizard and verified on the laptop. Repo: https://github.com/Mhsbrian/OpenBook.

**Repo hygiene:** PRs #1–#87 are merged and none are open. The 2026-10-17 cleanup left one remote branch, `main`; every other branch was merged or superseded. Two branches with commits never merged are kept as tags: `archive/anal-190-live-image-b` (superseded on `main`) and `archive/anal-178-stick-integration`.

### What works, and where it has been shown

| Area | In a VM (QEMU or Cuttlefish) | On the G14 | Evidence |
|---|---|---|---|
| Kernel (GKI android17-6.18 + 140 AMD modules) | Boots our Android 17. **Since #64:** the system DMA-BUF heap (`system_heap.ko`) and `efivarfs.ko`, GKI `.config` unchanged (26 more KMI symbols). On the G14 product the heap errors are gone (64 → 0) and a Vorbis ringtone decodes through Codec2, with the product's Codec2 AIDL and memfd fixes from the same PR; efivarfs mounts and reads the firmware's boot entries | **Yes:** 235 modules, 0 failed (PR #26 kernel). **The #64 kernel on `anal192d`:**<br>• `system_heap.ko` is in use, with 0 heap errors, and the Vorbis decoder starts.<br>• efivarfs is mounted by the installer.<br>• No GPU hang in 59 min under enforcing.<br>**But MediaPlayer sounds failed under enforcing:** `mediaserver` could not map AudioFlinger's memfd. Fixed in QEMU on the same image (PR #97) | `evidence/2026-10-16-g14-hwcheck/`, `evidence/2026-10-17-kernel-g14-r2/`, `evidence/2026-10-18-anal192d-media/` |
| Live USB boot, desktop | 40/40 live checks | **The normal enforcing boot reaches the desktop:** 28–31 s (`anal178c`, `anal176s`, `anal176t`, `anal192d`). **An hour on the enforcing desktop (`anal192d`):** 0 failed frames, 0 native crashes, launcher never restarted, Bluetooth and browser audio working. Since PR #52: 0 dropped frames (151 before); the stick is no longer offered for formatting; no lock-screen blackout. A GPU hang during the graphics check (MODE2 reset, VRAM lost) restarted the whole UI | `evidence/2026-10-17-g14-desktop/g14-anal178c/`, `g14-anal176s/`, `g14-anal176t/`, `evidence/2026-10-18-g14-anal192d-desktop/` |
| Graphics (RADV, radeonsi, ANGLE, minigbm, drm_hwcomposer) | Passing; dEQP pre-check on a Radeon 610M | **Desktop renders with 0 dropped frames**, composed on the GPU (overlay planes off since PR #52). **dEQP on the 890M** (`anal176t`, 14 min): Vulkan 1.4 45,220 pass / 5 fail, Vulkan 1.1 (shipped) 43,222 / 8 / 2 crash; GLES on ANGLE 13,099 / 0 and on radeonsi 13,621 / 0; EGL 847 / 0; ANGLE end2end 1,814 / 2. **Decided: ship Vulkan 1.4** (next image). Open: AHB rendering fails, and one GPU hang under 1.1 cost a full GPU reset and an Android UI restart (GC 11.5 has no per-queue reset with our firmware) | `evidence/2026-10-17-graphics-cts/g14-anal176t/` |
| Touchpad, keyboard | Yes | **Yes.** The touchpad's "Clock changed backwards" errors (every 40 ms of finger contact) are explained: the kernel autorepeats `BTN_TOOL_FINGER`. Fixed in Android (EventHub) and shown in QEMU with the laptop's own HID descriptor; on the laptop with the next stick | `evidence/2026-10-16-installer/g14-live/`, `evidence/2026-10-17-power-input/g14-sessions/` |
| Lid, power button, hotkeys, battery health | Yes | **Config in force, battery health works:** lid and power-button settings, hotkey layouts, the health HAL (charge counter, 88.7 % state of health, GOOD) and the power HAL's EPP changes, all on the laptop. **Closing the lid puts it to sleep and opening it wakes it** (`anal176t`) | `evidence/2026-10-17-power-input/g14-sessions/`, `g14-anal176t/` |
| Sleep | s2idle in a VM | **s2idle works, under Android too** (screen timeout → s2idle → key wake, display and Wi-Fi back); **deep sleep (S0i3) never reached.** The power check ruled out the driverless PSP; the SMU points at MPM or the USB4 router (unconfirmed) | `docs/power-input.md` §1.3, §7.6 |
| Wi-Fi, Bluetooth, audio | Yes (WPA2, iperf3, tone through ALSA and, with the HAL fix, through Android) | **Wi-Fi to the internet** (5 GHz, 160 MHz); **Bluetooth pairs**, A2DP with LDAC; **speakers and mic through ALSA** heard. Through Android the tone was broken (HAL fix in ANAL-179's PR, QEMU only). **Under enforcing (`anal176t`), Bluetooth audio connects without the Bluetooth app aborting**: A2DP Connected, the HAL's A2DP session and outputs open, 0 crashes, so #52's policy fix holds. Sound over Bluetooth and app (browser) sound are still unheard. The only playback tried, ringtone previews, **failed to decode** (`Failed to create audio/vorbis decoder`; missing system DMA-BUF heap suspected). Headphone jack and iperf3 not tested | `evidence/2026-10-17-g14-audio-net/`, `evidence/2026-10-17-g14-desktop/g14-anal176s/`, `g14-anal176t/` |
| ARM apps (Digitalis, built from source) | 14/16 ARM-only apps; works in enforcing | **arm64 apps run on Zen 5:** ARM apps check 5/5 on `anal192d`, arm64 probe 18/20 (the 2 known), CoreMark 0.361 / 0.351 of native; bridge self-check 5/5 in every session. Not yet seen: an arm64 app in an enforcing boot | `evidence/2026-10-17-digitalis-a17/`, `evidence/2026-10-17-digitalis-g14/`, `evidence/2026-10-18-digitalis-g14/` |
| Google services compatibility (microG add-on, ANAL-210) | **Cuttlefish: microG's self-check 18/18 green**, signature spoofing only for microG's certificate (negative test passes), device registration, push tokens for 3 Play-services apps, microG as location provider. QEMU, G14 image `g1a`: the add-on installs under enforcing on the live stick and on an installed disk's first start (self-check 18/18), the wizard's switch off by default, the plain stick has the same 140 packages as `main`'s image. One denial per boot from `stdio_to_kmsg`, removed in `f7df42d` (rerun pending the build lane) | Not yet | `evidence/2026-10-17-microg/` |
| Bring-your-own Google apps package (installer step, ANAL-211) | **QEMU, G14 image `anal211b`, enforcing: 79/79.** The wizard's advanced step checks a package from a USB drive (synthetic packages only) and installs it into a rebuilt `product`: power cuts at five points leave only the guaranteed states; the installed system boots with dm-verity on the new product (a flipped byte trips it); the apps run privileged from `/product` with their permissions; setup and Settings › About show the GSF Android ID. Host tests 89/89; without the step, installs are byte-identical to `main`'s | Not run | `evidence/2026-10-18-byo-gapps/` |
| Installer | **Wizard 25/25, engine 65/65, end to end 79/79; the firmware boot entry (`Boot####`, #68) boots with no fallback path** (SELinux enforcing): whole disk and **alongside a Windows-like disk** (Windows' partitions byte-identical and still booting; OpenBook boots from a firmware boot option); **power cuts at 6 points**, each leaving the old table, a blank disk or a complete install, and each restart completing; reinstall; the installed disk with and without the stick. **Firmware boot entries (since ANAL-191's #68):** the installer creates `Boot####` "OpenBook" itself; OVMF boots it with the fallback path deleted, and alongside leaves Windows' entry byte-identical and appends OpenBook to `BootOrder` (owner decision): Windows still starts by default and the firmware's boot menu lists OpenBook | Live USB boots; the wizard has not run yet | `evidence/2026-10-17-installer-wizard/`, `evidence/2026-10-17-installer-e2e/`, `evidence/2026-10-17-installer-bootorder/` |
| Image updates over adb (ANAL-223) | **QEMU 55/55** from the installer's whole-disk install of `anal192e`: A → B keeping `/data` (PIN, apps, settings, files), B → A through the new boot HAL, an unbootable slot rolled back after three tries, a power cut mid-update. Host tests of `openbook-bootsync` 56/56 | **Yes, 2026-10-18 23:24Z:** slot A (`anal192e`) → slot B (`openbook-ota-20261018-cand1`: `main` + #107 + bootsync + #109 + #106 + #104) over Wi-Fi in 82 s; booted, marked good, merge completed; same packages, Settings, Wi-Fi networks, account and PIN; no crashes | `evidence/2026-10-18-ota/`, `docs/adb-debug.md` §7, PR #112 |
| Debugging the installed system over the network (ANAL-222) | — | **Yes, on the installed G14 (NVMe, 2026-10-18):** adb from the build host over Wi-Fi, with no stick. `scripts/g14-adb.sh capture` saves the "save logs" set in 34 s (21 yes, 0 NO, 3 unknown). adb is back about 12 s after a reboot, and the desktop shows at 7.7 s. **No USB device mode**, so the network is the only path. **adb needs no authorization (root for anyone on the network)**; `ro.adb.secure=1` awaits the owner | `evidence/2026-10-18-g14-installed-adb/`, `docs/adb-debug.md` |

**What is left on the G14** (since 2026-10-18 the laptop runs OpenBook installed, from `anal192e`, updated over adb to `openbook-ota-20261018-cand1` the same day; tests go over adb, `docs/adb-debug.md`, ANAL-222, and **no more stick sessions are needed**):
- **Testable now over adb:** audible Bluetooth and app audio, the second graphics run on Vulkan 1.4, blur frame cost, the ARM apps check (and an arm64 app under enforcing, which had no route before), battery saver, and screen captures in place of owner photos. The 120 Hz render rate is already confirmed on the installed system.
- **New builds now reach the laptop over adb** (ANAL-223, `docs/adb-debug.md` §7). Since 2026-10-18 23:24Z the G14 runs slot B: `main` (with #97, #100, #101) plus #109 (the 120 fps composer fix), #106 and #104. **Since 2026-10-19 15:21Z it runs `openbook-ota-20261019-quire9`** (slot B): quire8 plus the note without its jolt, long runs that fit the screen, Android's install prompt waited for, and new app icons on the first desktop page. From 14:45Z: `openbook-ota-20261019-quire8` (slot A; ANAL-220 and ANAL-227, PR #115): Quire Q6 with the note in Atelier's glass-and-ink design, and computer control for the person's own apps. From 14:28Z: `openbook-ota-20261019-quire7` (slot B). From 14:07Z it ran `openbook-ota-20261019-quire6` (slot A): Quire Q6, so every agent knows it is OpenBook's assistant and acts on the laptop through Quire's tools, asking only before destructive actions; its Linux environment runs `quired` 0.3.0. Before that, from 12:36Z, it ran `openbook-ota-20261019-quire5` (slot B; ANAL-225, PR #113): the owner's Quire report fixed, so no accidental shakes from the touchpad, no note that blinks away, and the Linux environment starts by itself after a reboot, with one-click Set up the first time. Before that, from 10:35Z: slot A, `openbook-ota-20261019-quire2` (that tree plus #108, #110, #111 and the note-to-Linux-environment glue), marked good, merge completed, data the same, 120 Hz; the Linux environment runs there (guest up in 21 s) and opencode answers in Quire's note ("QUIRE OK" in 5.3 s); the Settings demo ran with the platform's consent. Rehearsed from the laptop's state: QEMU 36/36, and Quire in the updated VM (Linux environment 0 failures, screen checks 18/0). How to use it: `docs/quire-howto.md`. Update builds now need their own `BUILD_NUMBER`: with the running build's fingerprint, PackageManager kept its old parse cache and AVF's system service never started.
- **S0i3:** the laptop's own Linux was replaced by the whole-disk install. The Linux comparison now needs a Linux live USB; the S0i3 counters on OpenBook itself can be read over adb.

### Running now

- **Running:** only ANAL-209 (B8 first-run setup). ANAL-201's other ten items are merged: B1–B7 (#77, #72, #79, #73, #75, #81, #78), G1 microG (#80) and G2 bring-your-own GApps (#85). **The owner's stick is `openbook-live-20261018-anal192d`** (#86, built from `main`, with all of B1–B7 and #67/#68/#70/#80): live 40/40, wizard 51/51, end to end 79/79. The write command and the checklist are in ANAL-192's comments of 2026-10-18 10:56–10:57; results are routed from ANAL-192.
- **ANAL-198 (kernel lane): #64 merged.** It adds the system DMA-BUF heap and fixes two product bugs behind it (Codec2 HAL selection, Codec2 memfds under SELinux), so media decodes in QEMU. It also ships `efivarfs` as a vendor module, with Google's GKI configuration unchanged. Writing variables needed installer SELinux policy: done by ANAL-191 (#68). **On the G14 (`anal192d`), the heap and decoding held**, but under enforcing MediaPlayer could not play: `mediaserver` lacked the tmpfs form of AOSP's `audioserver:memfd_file` rule. PR #97 adds it. It is proven in QEMU on the `anal192d` image, and the policy compiles with all neverallows checked.
- **The G14 runs OpenBook installed from `anal192e`** (whole NVMe disk, 2026-10-18; ANAL-222). Owner stick iterations have ended. Checks run from the build host over adb (`scripts/g14-adb.sh`). The first capture gave 21 yes, 0 NO and 3 unknown (`evidence/2026-10-18-g14-installed-adb/`).
- **Results** go to each issue directly from adb captures. The coordinator no longer routes stick sessions. Issues that need a build newer than `anal192e` wait for a network update path (ANAL-193).
- **Merged today since 14:45:** #56 (ANAL-200, the bridge on Zen 5), #57 (ANAL-178, power and input on the G14, the touchpad fix), #58 (ANAL-179, audio, Wi-Fi and Bluetooth on the G14, the codec-paced audio HAL).

### Waiting on the owner

1. **No more stick sessions.** The G14 runs OpenBook installed (`anal192e`) and is tested over Wi-Fi with adb (ANAL-222, `docs/adb-debug.md`). On the laptop, keep Developer options > USB debugging on (it keeps network adb across reboots) and leave persistent logging on. Some checks still need your hands or ears: Bluetooth audio, headphones, touchpad use, the lid. Agents will ask for those by name.
   For S0i3, the laptop's own Linux is gone (the install took the whole disk). The Linux comparison (`scripts/power/linux-s2idle.py --amd-s2idle`) needs a Linux live USB if we still want it (ANAL-178).
2. **Decisions:** none blocks running work.
   - repo license (Apache-2.0 suggested);
   - upstream reports for the bridge (DigitalisX64; AOSP `Build.CPU_ABI`);
   - amd-pmf (`docs/kernel.md`);
   - Track B (`docs/PLAN.md` §6);
   - installing the Multica daemon on the G14 (ANAL-194).
   - **adb authorization on the G14 image (ANAL-222):** today anyone on the laptop's network gets a root shell over adb (port 5555, no prompt). We recommend `ro.adb.secure=1` in the G14 product: each new host then asks once on the laptop's screen. Until then, turn USB debugging and Wireless debugging off on networks you don't trust (`docs/adb-debug.md` §5).
   - Before any public image: AVB release-key custody, an "OpenBook" trademark check, and Mesa libelf (shipped as a shared library, as recommended).
3. **Already decided:** the dGPU stays off (`dgpu_disable=1`; HDMI is dark while it is set; NVIDIA work waits until after M4). The installer design follows our recommendation (owner on ANAL-189, 2026-10-16). Without "Start OpenBook by default", the installer appends OpenBook's `Boot####` to the end of `BootOrder`: the other system stays the default, and OpenBook is in the firmware's boot menu (owner on ANAL-159, 2026-10-17; ANAL-191, #70). ANAL-201's fonts (Google Sans and Google Sans Flex, OFL, internal names `google-sans*`), microG (G1), bring-your-own GApps (G2) and the whole beautification backlog B1–B8, all approved 2026-10-17 as ANAL-202 to ANAL-211.

### Next step for each open issue

| Issue | State | Next step | Needs |
|---|---|---|---|
| ANAL-176 G14 desktop and stability | In review | **The enforcing default entry reaches the desktop on the G14** and held for an hour on `anal192d` (30.7 s): 0 failed frames; few real jank frames (138 composer, 50 app; 60 fps cap until #88); launcher never restarted; 0 native crashes, 1 Java crash (wallpaper preview, ANAL-205); Bluetooth and browser audio under enforcing (with ANAL-179). PR #52's fixes all hold. Media decoding resolved by ANAL-198 (#64; MediaPlayer's control-block denial #97). New denials for others: `openbook_installd → sysfs_batteryinfo` (ANAL-191), Chrome's `isolated_app` setattr. Open: a GPU reset restarts the UI; Esc in All Apps not confirmed (`docs/g14-desktop.md` §6, §7, §14). Next: Esc and smoothness on `anal192e` | Over adb on the installed G14 (ANAL-222): Esc in All Apps, frame statistics |
| ANAL-177 graphics conformance | In review (PR #61, merged) | **dEQP on the G14's 890M:** Vulkan 1.4 45,220 pass / 5 fail against 1.1's 43,222 / 8 / 2 crash, so **1.4 ships** (Mesa's default build since #61). GLES on ANGLE and radeonsi 0 failures; EGL 847 / 0; ANGLE end2end 1,814 / 2. Found: rendering into Android hardware buffers fails, and one GPU hang under 1.1 reset the GPU and restarted the UI. Next: the second run on 1.4 with tuned lists | Over adb on the installed G14 (push dEQP; no stick) |
| ANAL-178 input and power | In review (PR, see History) | Touchpad clock errors down 99 % on the G14 (`anal192d`); the rest (palm lift-offs) fixed in QEMU (`0002`); the save-logs touchpad capture moved to boot completion. Next: S0i3 from the Linux comparison | S0i3 Linux comparison: a Linux live USB (the laptop's Linux is gone). Over adb: battery saver and the S0i3 counters. The owner's hands for the touchpad and lid |
| ANAL-179 Wi-Fi, Bluetooth, audio | In review (PR #58, merged) | On the G14: Wi-Fi to the internet, Bluetooth A2DP/LDAC, speakers and mic through ALSA. Android's audio path was broken; the codec-paced HAL fixes it in QEMU. Next: the G14 check | Over adb: `g14-adb.sh capture --hwtest` with an iperf3 server on the build host. The owner's ears for Bluetooth audio and headphones |
| ANAL-200 ARM bridge | In review (PR #93) | Done: the ARM apps check on the G14 (`anal192d`): 5/5 verdicts, arm64 probe 18/20 (the 2 known), CoreMark 0.361 / 0.351. Next: an arm64 app in an enforcing boot (a preinstalled arm64 app or the device loop) | The upstream-report OK. An arm64 app under enforcing is now possible: `adb install` on the installed G14 |
| ANAL-191 installer wizard and engine | In review | **The owner installed `anal192e` on the G14's whole NVMe disk, and it boots** (systemd-boot, enforcing; ANAL-222); the stick after it carries the firmware boot entry (efivarfs policy, #68) and the owner's `BootOrder` decision (OpenBook appended without consent). Open: `openbook-bootsync`, the text hardware report | — |
| ANAL-192 installer end-to-end tests and the owner's stick | In review | The owner's stick is `anal192e` (§13.13, the 120 Hz fix): live 40/40, refresh 3/3, wizard 51/51, end to end 79/79, the three add-on tests. Before it, `anal192d` (§13.12). Fixed on the way: #83 (clean checkouts of `main` failed since #81). Earlier: the integrated stick `anal192c` (live 40/40, wizard 25/25), the end-to-end matrix 79/79 (`scripts/installer/e2e-qemu.sh`), the user guide and release checklist draft (`docs/INSTALL.md`). Found: an installed OpenBook offers to format a plugged-in installer stick; the wizard calls an installed OpenBook "Linux". Open: the OTA slot switch (needs `openbook-bootsync`) | Owner stick runs have ended (the G14 is installed). A spare drive named by `/dev/disk/by-id` only for further real-install tests; the release decisions (`docs/INSTALL.md` §9) |
| ANAL-198 G14 kernel (follow-up) | In review (#64, #65 merged; PR #97 open) | Done:<br>• `system_heap.ko` and `efivarfs.ko` as vendor modules, with Google's GKI configuration unchanged.<br>• Codec2 fixes.<br>• GPU reset: a hang means a full reset (`docs/kernel.md`).<br>**On the G14 (`anal192d`):** heap, decode and efivarfs hold. MediaPlayer playback is blocked by a missing `mediaserver` memfd rule, fixed in QEMU by PR #97.<br>Next:<br>• PR #97 on the next stick.<br>• There, Settings → Sound previews.<br>• `amdgpu_firmware_info`: "save logs" collects it from PR #97 on | PR #97 merged and on the laptop: a network update (ANAL-193) or a reinstall |
| ANAL-222 debugging the installed G14 over adb | In review (PR #107) | Done: `scripts/g14-adb.sh` (find, connect, capture, follow logcat, persistent logs, wait for a boot, pair). The capture reuses the stick's own collect script and reports, and its first run is on the installed laptop. Persistent logging was turned back on after Developer options cleared it. Next: the add-on checks over adb, a USB-Ethernet path (load the GKI's USB network modules), and a pstore backend for panics | The owner's `ro.adb.secure` decision |
| ANAL-193 to ANAL-197 device loop | Re-planned (ANAL-222) | The G14's Linux is gone (whole-disk install), so phases 1–3 (ANAL-194–196) are superseded. adb from the build host runs the checks now (`docs/adb-debug.md`). Next: a network image update (A/B slot over adb, or OTA with `openbook-bootsync`), then ANAL-197's suites over adb | The owner's OK to retire ANAL-194–196 and to let agents write updates to the laptop's disk |
| ANAL-201 Googlebook UI and GApps review | In progress (PR #71 merged) | Review done (`docs/googlebook-ui.md`, `docs/gapps.md`). All ten follow-ups approved and running in parallel on the shared lane (builds take turns under the lane lock; each issue has its own Cuttlefish ports) | — |
| ANAL-202 to ANAL-209 beautification B1–B8 | In progress | B1 Google Sans · B2 blur on the G14 · B3 flag set v2 · B4 shapes and wallpaper dim · B5 clean desktop · B6 brand assets · B7 document fonts · B8 first-run setup. G14 checks go to ANAL-192's next stick | — |
| ANAL-202 B1: Google Sans typography | In review (PR #77 merged) | **Done in both products:** Google Sans and Google Sans Flex (OFL, google/fonts `47d54ca1`, unmodified) in `/product/fonts` with their OFL texts in the image notices; the generated `fonts_customization.xml` (40 families), which the build checks against its generator; the four `config_*FontFamily` values in the framework RRO. In Cuttlefish all 40 families load, both overlay values resolve, and Settings, captions, Quick Settings, notifications, all apps and Files render in Google Sans. Desktop capture unchanged, crash buffer empty, no new SELinux denials. `product.img` +9.24 MiB. Settings scroll: no regression (janky 1.35 vs 4.32 %, three alternating pairs; rows are a quarter taller). After merging `main` (B2, B4, B5), both products build again and Cuttlefish shows all of it together (`docs/googlebook-ui.md` §3.1) **On the G14 (`anal192d`):** no font warning or font-related denial; the laptop's own screenshot shows the caption and status bar in Google Sans at 240 dpi; the crash buffer's one crash is the wallpaper preview's, not B1's (`evidence/2026-10-18-g14-anal192d-typography/`) | Photos of Settings, Quick Settings, notifications and all apps (clipped text) on the next stick |
| ANAL-203 B2: background blur on the G14 | In review (PR #72 merged) | **On the G14 (`anal192d`):** blur is on and drawn: SurfaceFlinger's SkiaGL RenderEngine with Kawase blur, radius 51 px behind the shade, 9 openings in an hour. No amdgpu fault or reset, no UI restart, no large hitch (`evidence/2026-10-18-blur-g14/`). Before: Cuttlefish cost measured, the image blurs in QEMU, renderer properties evaluated (not flipped). Not yet measured on the G14: frame cost (the graphics check's `blur` part) | Over adb: the graphics check's `blur` part on the installed G14 |
| ANAL-204 B3 desktop flag set v2 | In review (PR #79 merged) | Done: all 218 Googlebook flags that AOSP 17 declares are triaged; 84 are on (value set 79 → 163); two that broke the desktop stay off (`docs/googlebook-flags.md`). **On the G14 (`anal192d`):** all 84 are in the image; no SystemUI restart, ANR or B3-related crash in three boots (`evidence/2026-10-18-g14-anal192d-b3/`). Next: the photo steps and the minimize → taskbar restore on `anal192e` | Over adb: minimize → taskbar restore, with screen captures instead of photos |
| ANAL-205 B4: circular icons, no wallpaper dim | In review (PR #73 merged) | **Done in Cuttlefish** (#73): circle mask, round icons, 0 wallpaper dim, Googlebook's wallpaper colour thresholds 55 / 12; a shape picked in Wallpaper & style still wins in the taskbar. **On the G14 (`anal192d`, logs only):** `getprop` 55 / 12; every taskbar icon is a circle in the laptop's screen captures; no crash from B4. The dim value can't be seen on B6's wallpapers: each has a dark-theme or dark-text hint, so none would be dimmed anyway. Found: Wallpaper & style crashes on a full preview from a desktop window (AOSP Kotlin null bug, fix `Void?`; on ANAL-192). Open: the taskbar's All Apps panel ignores a shape pick (AOSP) (`docs/googlebook-ui.md` §2.4) | Screen captures over adb instead of the owner's photos |
| ANAL-206 B5: a clean default desktop | In review (PR #75 merged) | Done in Cuttlefish and on the G14 product in QEMU: no search box and no `QuickSearchBox`; taskbar pins Files, Settings, browser, Calendar, Gallery, Camera (only with a camera); touch, keypress and non-forced screenshot sounds off; installer live checks 40/40 (`docs/aosp-desktop.md`, `evidence/2026-10-17-clean-desktop/`). Next: the G14 check on the next stick | The owner's review of the pin list; the G14 check over adb |
| ANAL-207 B6 brand assets | In review (PR #81 merged; G14 follow-up #101) | Done in Cuttlefish (#81). **On the G14 (`anal192d`, from the logs):** the boot animation played from our zip, at 30 fps; Open Pages, Spark and First Light became the defaults; the unlock sound's track opened under enforcing with no SoundPool denial; SystemUI played our low-battery sound (refused under enforcing until #97); the owner set one of our wallpapers (Folio dark). **Found and fixed:** Wallpaper & style's preview crashes when a desktop window is granted fullscreen (AOSP bug, one-line WallpaperPicker2 patch). Next: the owner's photos and listening (ANAL-192's next stick) | Screen captures over adb; the owner's listening |
| ANAL-208 B7: document fonts | In review (PR #78 merged) | Arimo, Tinos, Cousine, Gelasio, Comic Relief, Archivo Black and Narrow (OFL, google/fonts) in `/product/fonts`. In WebView, Arial, Times New Roman, Courier New, Georgia and Comic Sans MS now render in them, within 0.015 px of their widths (Cuttlefish). Googlebook's 13 other families are unpublished, so Verdana and Tahoma stay on Roboto. **G14 (`anal192d`, logs):** the image carries B7 byte for byte, no font error or font denial in any boot, and the browser ran 9 minutes on real pages with no crash (`evidence/2026-10-18-g14-anal192d-b7/`). Next: the photo of the `data:` page | A screen capture over adb; an owner decision on Helvetica/Times/Courier aliases (`docs/googlebook-ui.md` §2.1.1) |
| ANAL-209 B8: first-run setup | In review (PR #100) | **Done in Cuttlefish and on the G14 product in QEMU** (`docs/setup.md`): `OpenBookSetup` replaces Provision and the installer's interim setup in both products. Nine pages in the installer's style, no account: welcome, language and region, keyboard layout, internet, date and time, name and screen lock, the not-certified notice, extras (microG, Google apps you provide), done. Cuttlefish 15/15 (every page: en-GB, Europe/London, 24-hour clock, name, PIN, keyboard layout), Skip 8/8, flag 7/7. It steps aside on live sessions, with `androidboot.openbook.setup=skip` and with Cuttlefish's default `ro.setupwizard.mode=DISABLED`, so unattended runs are unchanged. Installer live checks 40/40, wizard 27/27 and G2's installed system 18/18 (QEMU, G14 product; with a user's Google apps package, setup adds G2's Register page). Found and fixed: a crash when stepping aside on a live stick's first boot (the wizard never came up in the dryrun) | A build with #100 on the laptop (`anal192e` still runs Provision): a network update (ANAL-193) or a reinstall |
| ANAL-210 microG (G1) | In review (PR #80) | Done in VMs: the patch in every image; the add-on on the stick, offered by the installer off by default, installed as normal apps on the first start. Cuttlefish: self-check 18/18, negative test, push tokens; QEMU: live and installed disk. Next: the rebuilt image's QEMU rerun (one denial removed), then the G14 | A build with the add-on on the laptop, or the add-on pushed over adb as in Cuttlefish |
| ANAL-211 bring-your-own GApps (G2) | In review (PR) | Done in QEMU: the advanced installer step, the package check (LiteGapps layout; framework, init, SELinux, ARM-only and platform-UID content refused), the rebuilt `product` with a new dm-verity hashtree, super metadata and unsigned vbmeta, the GSF ID screens; host 89/89, QEMU 79/79 (`docs/installer.md` §15). Next: the G14 dry run on ANAL-192's next stick | The owner's call on enforcing the privileged-permission allowlist, and on what an OTA does to a user's package. On hardware it is an install-time step: a stick and a spare drive |
| ANAL-212 120 Hz on the G14 | In review (PR) | **Both causes fixed; the second shown on the laptop.** 1. AOSP's `config_defaultRefreshRate` (60) capped the render rate (#88, in `anal192e`). 2. drm_hwcomposer set a new CTM blob every frame, so every flip was a full DC update that landed a vblank late (60 fps on a 120 Hz scanout). Patched composer on the G14: 8 ms present intervals 959/959, 0 missed (16 ms and 490 missed before). It runs until the next reboot. Next: ship the patch in the next image or network update; VRR as its own issue | A network update or reinstall to keep it |
| ANAL-219 Quire Q5: the surface | In review (PR) | **The Checker's three findings fixed (2026-10-19):** the note honours windows that hide overlays (consent from an activity beneath the dialog, a system overlay only while a session runs), sessions keyed by connection, intake only with SystemUI's window; 54/54 safety checks, 37/37 host tests. Open decision: the note does not show over Settings or Files (`docs/quire.md` §8). **Built and checked in Cuttlefish:** the note (a Quire core window), its ACP client, consent, the mirror with Pause and Take over, the tray, the halo and the pointer from SystemUI (frameworks/base 0008); every design state in both themes next to its render, keyboard 9/9, labels, Remove animations, contrast on all wallpapers. Found: after Pause and Resume a session's accessibility windows are gone (an AOSP NPE, `docs/quire.md` §8). Next: the Launcher3 taskbar button, the G14 frame check, TalkBack | Atelier's sign-off on the build, the Checker's on the evidence (ANAL-217) |
| ANAL-216 Quire Q2: platform hooks | In review (PR) | **Done in Cuttlefish:** invocation by shake, Meta+Space and the assist key; computer control on Settings with per-app consent, mirror, tap and hand-over; refusals for denied consent, a second unapproved app, lock screen and secure windows; no regression. Open: an app already running on the person's display has no accessibility tree in a session; release-key digest (`docs/quire.md` §8). Next: Q3–Q6; the G14 check on a later stick | The Checker's review (ANAL-217) |
| ANAL-218 Quire Q4: the Linux environment, `quired serve` | In review (PR) | **Done in Cuttlefish:** AVF and the Terminal app in both products; the Debian guest built here with `quired`; Quire core reaches it over vsock through the Terminal app's bridge; `quired agents` in the guest lists opencode and a prompt from Quire core is answered there (29/29); without KVM, Quire says so and names the fallback (8/8). The Checker's two `quired serve` holds are fixed (`quired` 0.2.1) and the builder's unmount is scoped to its own loop devices. The image now goes onto an installed system over adb (`scripts/quire/linux-env-adb.sh`; Cuttlefish over adb: 0 failures). Pairing a second computer: design revision 2, after the Checker's Hold (no TLS resumption; a transcript with both pins bound into the code), for re-review (`docs/quire-pairing.md`). Next: the G14 run over adb (`linux-env-adb.sh check`); pairing once the design is approved | The Checker's recheck (ANAL-217); the G14 update that carries AVF (ANAL-214, ANAL-223) |
| ANAL-210 microG (G1) | In review (PR #80) | Done in VMs: the patch in every image; the add-on on the stick, offered by the installer off by default, installed as normal apps on the first start. Cuttlefish: self-check 18/18, negative test, push tokens; QEMU: live and installed disk. Next: the rebuilt image's QEMU rerun (one denial removed), then the G14 | ANAL-192's next stick, after the PR merges |
| ANAL-211 bring-your-own GApps (G2) | In review (PR) | Done in QEMU: the advanced installer step, the package check (LiteGapps layout; framework, init, SELinux, ARM-only and platform-UID content refused), the rebuilt `product` with a new dm-verity hashtree, super metadata and unsigned vbmeta, the GSF ID screens; host 89/89, QEMU 79/79 (`docs/installer.md` §15). Next: the G14 dry run on ANAL-192's next stick | The owner's call on enforcing the privileged-permission allowlist, and on what an OTA does to a user's package |

| ANAL-166 performance and parity | Backlog | After the installer: benchmarks, Chrome, the Linux terminal (AVF without pKVM). No sub-issues yet | — |
| ANAL-186 NVIDIA | Parked | Research is done (ANAL-187); N1–N6 after M4 | — |
| ANAL-165 Track B (ANAL-182 to ANAL-185) | Parked | Starts only if the owner decides to use Google's image | Owner decision |

**Delivered, nothing left to do** (in review with merged PRs; the owner can close them):
- ANAL-167, ANAL-168, ANAL-169 (VM track);
- ANAL-170, ANAL-171, ANAL-172, ANAL-198 (kernel);
- ANAL-173, ANAL-174 (graphics);
- ANAL-175, ANAL-199 (G14 bring-up);
- ANAL-180, ANAL-181 (ARM evaluation);
- ANAL-187 (NVIDIA research);
- ANAL-189, ANAL-190 (installer design and live USB);
- the epics ANAL-160 (Track A in a VM) and ANAL-161 (kernel).

**Build host:** one AOSP build at a time (`flock ~/anybook/aosp/.lane.lock`, taken by `scripts/aosp-docker.sh`), because builds peak at about 50 GB of the 61 GB RAM. Builds and images are in `docs/BUILD.md`; the live image and the owner checklists are in `docs/installer.md` §11.

## History

### 2026-10-18: Quire Q4, agents in the Linux environment (ANAL-218)

- **AVF was compiled out of both products** (AOSP's PC product doesn't inherit AVF's `product_packages.mk`); `linux-env.mk` puts it in, with the Terminal app off by default as in AOSP.
- **The guest image is built here** from AOSP's builder, with Debian's own kernel instead of one downloaded from Google's CI, and `quired` as a `.deb` (`scripts/quire/linux-env-image.sh`).
- **`quired serve`:** one ACP connection from Quire core to every agent in the guest, over vsock (peers other than Android refused), with sign-in passed through (`authenticate`, `authMethods`).
- **Cuttlefish, nested KVM on AMD:** the guest boots in about 12 s; `quired agents` in the Terminal app lists opencode; a prompt from Quire core comes back "QUIRE OK" (29/29). Without KVM, Quire says so and names the fallback (8/8). Found: `virtmgr`'s vsock can't be half-closed by its owner, and AVF keeps calling a dead VM running; both handled in the bridge (`docs/quire.md` §4.1, §8).
- **Review fixes (PR #111, ANAL-217):** a session's default folder can no longer be led out of the root by a symlinked `~/Quire`; a client leaving while an agent starts no longer lets `quired serve` return before that agent stops; the image builder unmounts only its own loop devices (it works in `WORK/work`). `quired` 0.2.1.
- **Installed systems:** `scripts/quire/linux-env-adb.sh` pushes the guest image over adb, checks it, and runs Q4's on-device check (Cuttlefish over adb: 0 failures, prompt answered in 14.6 s).
- **Pairing design, revision 2:** no TLS resumption, and the pin check on every connection; a canonical transcript with both pins, bound into the exporter's context, the commitment and the 6-digit code; one attempt per pairing (`docs/quire-pairing.md`).
- **Not yet:** the G14 run (over adb, once its update carries AVF), and pairing itself (after the design's re-review).

### 2026-10-19: Quire Q5, the Checker's three safety findings fixed (ANAL-219)
- **The note honours windows that hide overlays.** It is an ordinary overlay, and only as big as the card, so clicks
  beside it reach the app below. Quire asks for computer control from an inert activity of its own, which stays beneath
  the platform's consent dialog: nothing of Quire's covers the dialog at 1920×1080 or 1280×800, and the platform still
  finds Quire on screen after Allow. While a session runs, the note with the mirror and Stop is a system overlay,
  because Settings hides overlays even on the session display.
- **A session belongs to its agent's connection.** Two agents both using "session-1" no longer see each other's
  requests, cancels or disconnects.
- **Quire takes in a window only when SystemUI says which one.** That needs the pointer, fresh bounds, and the
  window's package. frameworks/base 0008 now passes the package and the time, and never picks the home task.
  Otherwise nothing is taken in.
- **Checked** on a fresh in-tree build in Cuttlefish (`evidence/2026-10-19-quire-q5-safety/`): 54/54 safety checks,
  37/37 host tests, and the Q5 checks again with nothing behind the note (76 pass, 0 fail, 14 info).
- **Open, for the owner and the Checker:** Settings, Files and the permission screens hide overlays on every page, so
  the note does not show over them (`docs/quire.md` §8 item 10).
- **Atelier signed off on the build** (`69cf4d1`). Its one change, a still of the note beneath the consent dialog
  instead of a two-line card, is built (`45e773a`). Take over waits for the overlay decision.
- **The Checker's recheck** closed the agent and intake Holds, and found the session exemption leaking to other tasks.
  It is now bound to the session's own task (`f238e95`). Safety checks pass 60/60 with that case added.

### 2026-10-18: Quire's surface, the note, built to Q3's design (ANAL-219, Q5)
- **Built** (`docs/quire.md` §9): the note is a window of Quire core (a system application overlay, so it stays visible through the platform's computer-control consent, which re-checks that the session owner has a visible window). One card for every state of `docs/quire-design.md`, with its springs, colours from the wallpaper, Google Sans, and Remove animations honoured. An ACP v1 client renders thought and message chunks, steps, plans, images and permission requests with the agent's own option names. Computer control shows the platform's consent, the mirror zoomed 2× on the control in use with the agent's pointer, Pause, Take over and Stop. SystemUI (frameworks/base 0008) draws the halo and the intake outline and passes the pointer and the window's bounds, so the note opens at the pointer.
- **Checked in Cuttlefish** (`evidence/2026-10-18-quire-q5/`): every design state in light and dark next to its render; the real shake and Meta+Space at the pointer; keyboard 9/9; 157 controls labelled; contrast on all eight wallpapers; three recordings; a real agent (opencode) answered in the note. 72 pass, 1 fail (MediaProvider denials the check's own first recording caused), 12 info.
- **Found:** after Pause and Resume the session's accessibility windows are gone (`ProxyAccessibilityServiceConnection.getWindows()` dereferences null); Q6 needs a platform fix. Atelier's and the Checker's sign-offs, the G14 frame check, TalkBack and the Launcher3 button are open.

### 2026-10-18: still 60 fps on screen with 120 Hz selected: the composer's CTM (ANAL-212)
- **On the installed G14 over adb:**
  - SurfaceFlinger draws at 120 Hz (#88 works), but it presents every 16.7 ms: 470 of 478 intervals, and 477 of 480
    frames missed, with RenderEngine at 3 ms.
  - Every flip is a full DC update: `commit_planes_for_stream`, never `_fast`. It waits through a vblank and
    latches one vblank late.
  - The trigger is a new CTM blob from drm_hwcomposer on every commit. amdgpu turns that into a plane reset
    (`should_reset_plane`, `color_mgmt_changed`).
- **Fix:** `aosp/patches/external/drm_hwcomposer/0001`, which sends the CTM only when it changes.
- **Shown on the laptop:** the patched composer ran through a tmpfs bind mount (no partition written). Settings
  scrolling went from 16 ms present intervals and 490 missed frames to 8 ms × 959 and 0 missed. DC update types
  went from full 91 to fast 181.
- **Incident:** one unplanned reboot at 17:48Z, while the first version of the swap script bound the binary from
  `nosuid` `/data`. The laptop came back by itself on the installed binary.
- **State:** the patched composer stays active until the next reboot.
- **Tools:** `scripts/graphics/g14-flip-check.sh` and `g14-composer-swap.sh`.
- **Evidence:** `evidence/2026-10-18-refresh-rate/g14-installed/`.

### 2026-10-18: the installed G14 over the network: adb instead of the stick (ANAL-222)
- **Context:** the owner installed OpenBook on the G14's NVMe disk. The build host reaches it at `192.168.50.11` over Wi-Fi with adb: mDNS advertises "OpenBook on ROG Zephyrus G14 (GA403WR)" on port 5555 and on Wireless debugging's TLS port.
- **No USB path:** the G14 has no USB device-mode controller (`/sys/class/udc` empty, xHCI hosts only), so a cable cannot carry adb.
- **No authorization:** adbd needs none (userdebug, `ro.adb.secure` unset, `orange`), and `adb root` works for anyone on the network. Recommended fix: `ro.adb.secure=1`, the owner's decision.
- **Across a reboot:** adb is back about 12 s after the kernel starts, before unlock, and the desktop shows at 7.7 s. Every debugging toggle restarts adbd; the tool reconnects.
- **Persistent logs:** setting Developer options' "Store logger data persistently" to Off deleted `/data/misc/logd`. Back on with `g14-adb.sh persist-logs on`.
- **`scripts/g14-adb.sh capture`:** saves the stick's "save logs" set from the running system in 34 s. It reads the `COLLECT` script out of `live-init.c` (`scripts/installer/live-init-script.py`) and runs `live-report.py` and `avc-summary.py` (21 yes, 0 NO, 3 unknown).
- **Redaction:** `live-report.py` now also masks Wi-Fi pairing codes and every network name it learns from the logs, including neighbours' networks from scans. Full logs from the installed system stay on the host.
- **Where:** `docs/adb-debug.md`, `evidence/2026-10-18-g14-installed-adb/`.
- **Stick sessions retired (owner, 2026-10-18):** every testing issue now points at adb on the installed G14. PLAN §4a is re-planned around it: ANAL-194–196 are superseded because the laptop's Linux is gone, and a network image update is the proposed next phase. Fixes newer than `anal192e` (#97, #100, #101) need that update, or a reinstall, to reach the laptop.

### 2026-10-18: the installer on the G14, `anal192d` (ANAL-191)
- **Read** from the host copy `stick-20261018T123221Z` (`docs/installer.md` §12.12, `evidence/2026-10-18-g14-installer/`):
  - the wizard opened by itself on the stick's first boot; `efivarfs.ko` loaded and efivarfs mounted.
  - **An install of the internal NVMe was requested at 11:04 and refused before anything was written.** No install report reached the stick, and the disk's table is unchanged in both later boots. The likely cause is S8: on battery at 41 %. On mains it would have erased that disk.
- **Fixed:**
  - The daemon's power-supply reads are denied on real hardware, and AOSP reserves them for the health HAL, so S8 uses the app's BatteryManager reading. S8 now refuses when no reading is available; it used to skip the check.
  - "Save logs" collects the daemon's log (serials masked) and the firmware's boot entries, with `installer_*` verdicts in `report.md`.
- **Tests:** engine 69/69, QEMU "save logs" 11/11, wizard 17/17 (image `anal191i`).
- **Not fixable in policy:** the hardware check's `/vendor/firmware` listing (a vendor type); the speaker-tuning check stays silent.

### 2026-10-18: the touchpad fix on the G14; palm lift-offs and the touchpad capture (ANAL-178)
- **Read** the owner's `anal192d` session (host copy `g14/stick-20261018T123221Z`; `docs/power-input.md` §7.7).
- **Touchpad.** With the EventHub patch, the gestures library's clock errors fell from 6,700–19,600 to 71 per hour of use. The rest come from frames hid-multitouch sends without `MSC_TIMESTAMP`: palm lift-offs and the sticky-fingers release. `aosp/patches/frameworks/native/0002` keeps the last `MSC_TIMESTAMP` for them. Checks: unit test 7/7 (host `inputflinger_tests`); in QEMU with the laptop's descriptor, no errors at palm lift-offs (4 before).
- **Touchpad capture.** The save-logs capture ran after openbook-hwtest, minutes after the owner used the touchpad, so it saw nothing. `live-init` now records it from boot completion (shown in a QEMU save-logs boot).
- **Battery Saver** was not turned on, and Android refuses it on mains power. Checklist note posted on ANAL-192: unplug first.
- **Power facts:** about 15.5 W in use (42 % → 20 % in 51 min). The health HAL follows the firmware's recalibration (state of health 88.7 % → 87.8 %).

### 2026-10-18: B6 on the G14, from the owner's `anal192d` session; a wallpaper-preview crash fixed (ANAL-207)
- **Boot animation (C).** It played from our zip in both boots: `part0` in 1.41 s (42 frames, 30 fps), `part1` looping, and a 0.40 s fade.
- **Sound defaults (C).** `ro.config.*` are ours, and the system set the three as defaults on the first boot.
- **Unlock sound (C).** Under enforcing, SystemUI's track opened as the keyguard went away, with 0 `appdomain_tmpfs` denials and 0 track failures. Only QEMU can time its 0.5 s.
- **UI sound paths (C).** SystemUI played our `OpenBook_LowBattery.ogg` at 15 % battery. MediaPlayer's track was refused under enforcing; #97 fixes it, and ringtone previews need it too.
- **Wallpapers (C).** The owner set Folio dark from Wallpaper & style.
- **Preview crash.** The picker crashed once on the way: `WallpaperPreviewActivity`'s fullscreen callback declares a non-null `Void`, and the framework calls `onResult(null)`.
  - Reproduced in Cuttlefish on #81's build.
  - Fixed by `aosp/patches/packages/apps/WallpaperPicker2`.
- **Not yet seen:** the default wallpaper (no picture of the first desktop), the pointer, and the sounds by ear.
- Evidence: `evidence/2026-10-18-brand-assets-g14/`.

### 2026-10-18: OpenBook first-run setup (ANAL-209, B8)
- **`OpenBookSetup`** (`device/anybook/common/setup/`, `docs/setup.md`) overrides AOSP's Provision in both products and takes over the installer's interim setup.
  - Nine pages in the installer's style, with no account: welcome, language and region, keyboard layout, internet, date and time, name and screen lock, the not-certified (orange-state) notice, extras (microG, Google apps you provide), done.
  - A tenth page, G2's "Register this computer with Google" (the GSF Android ID), appears before Done on a system installed with the user's own Google apps package.
  - It shares the installer's theme, buttons and mark through a Soong filegroup.
- **Unattended runs are unchanged.** It steps aside on live sessions, with `androidboot.openbook.setup=skip`, and with `ro.setupwizard.mode=DISABLED` (Cuttlefish's default).
- **Cuttlefish, merged tree:** every page 15/15, Skip 8/8, the flag 7/7, the default 7/7. **QEMU, G14 product:** live checks 40/40, wizard 27/27 (setup on the installed disk walked), G2's installed system with a synthetic package 18/18.
- **Found and fixed:**
  - setup crashed when it stepped aside before the user was unlocked (a live stick's first boot), so the wizard didn't come up;
  - the time zone list was locked where nothing detects a zone;
  - state could be lost on the first-boot activity restart.
- **Not on the G14 yet:** the checklist is on ANAL-192.

### 2026-10-18: audio, Wi-Fi and Bluetooth on `anal192d` (ANAL-179)
- **Shown on the G14:**
  - `audio_android_clean` yes: the codec-paced HAL plays and records through Android with no gaps;
  - `wifi_pno` yes: the MT7925 takes scheduled scans;
  - Bluetooth audio (AAC, 26 minutes of streaming) and browser audio work under enforcing;
  - the SoundPool unlock sound plays at boot, with no denial (#67); the owner heard it.
- **Found:** MediaPlayer fails under enforcing (`mediaserver → audioserver_tmpfs`). ANAL-198's #97 fixes it.
- **Not shown:** the headphone jack (no plug event), the headset reconnecting, iperf3. The gateway did not answer ping, although the internet check passed (H: that access point drops ICMP).
- **Evidence:** `evidence/2026-10-18-g14-anal192d-audio-net/`; `docs/g14-audio-net.md` §11.

### 2026-10-18: blur on the G14, from the owner's `anal192d` session (ANAL-203)
- **Drawn on the laptop (C).** SurfaceFlinger: `Threaded RenderEngine with SkiaGL Backend (Ganesh)`, `Background Blurs Enabled (Kawase dual-filtering V2 algorithm)`. In about an hour of normal use, SystemUI blurred the desktop behind the shade at 51 px, in each of 9 openings. That is the full-screen case: `config_supportBlurredWallpaper` is still on.
- **Stable (C).**
  - 0 amdgpu fault or reset lines in the default, save-logs and ARM apps boots.
  - SurfaceFlinger, SystemUI and Launcher3 never restarted.
  - SystemUI had no ≥ 30-frame skip and no ≥ 700 ms frame.
  - The only crash was the Wallpaper picker's (`WallpaperPreviewActivity` NullPointerException), unrelated to blur.
- **Not measured:** the frame cost. The graphics check, whose `blur` part records it, wasn't booted. It is on `anal192e`'s list.

### 2026-10-18: the G14 drew at 60 frames a second on a 120 Hz scanout (ANAL-212)
- **Found** (`docs/graphics-amd.md`, "Refresh rate"): drm_hwcomposer runs the panel's preferred 120 Hz mode, but DisplayModeDirector's lowest-priority vote caps the render rate at `config_defaultRefreshRate`, 60 in AOSP. Our desktop RRO came from the AOSP desktop emulator, which leaves it at 60. Googlebook sets 0 (and a peak of 1000), as Cuttlefish does. On the G14 the desktop spent most of its time at 60 (`anal176s`: 76 s at 60, 6 s at 120); in QEMU's 75 Hz display it drew at 37.5.
- **Changed:** `config_defaultRefreshRate=0`, `config_defaultPeakRefreshRate=1000` in `AnyBookDesktopFrameworkOverlay`, for every desktop product. Content-based selection, touch boost and battery saver's 60 cap are unchanged.
- **Tested:** idmap2 maps both values. QEMU, same harness (`scripts/graphics/refresh-qemu.sh`, 75 Hz virtual display): render range [0, 60] → [0, 1000], Settings scrolling at 37.5 → 75 frames a second (12 of 12 samples each; `evidence/2026-10-18-refresh-rate/`). New `refresh_rate` verdict in `live-report.py`: NO on all four enforcing G14 sessions so far.
- **G14 baseline (`anal192d`, before the fix):** render range [0, 60] in both captured boots; the owner's hour-long default boot drew at 60 for 99.7 % of its screen-on time (`evidence/2026-10-18-refresh-rate/g14-anal192d-baseline.md`).
- **Not done:** the G14 with the fix (`anal192e`); VRR (the panel does 48–120 Hz, drm_hwcomposer exposes none); thermal refresh limits (needs a display config for the panel); the idle timer.

### 2026-10-18: Quire, connecting OpenBook to the person's own AI agents (ANAL-214, Q1)
- **Design** (`docs/quire.md`):
  - Quire plugs into hooks AOSP 17 already has: the pointer-shake gesture, contextual search, the assistant role and computer control (agents operate apps on a virtual display, with consent and hand-over).
  - Agents connect over ACP. OS tools reach agents over MCP.
  - Multica was reviewed, not copied.
- **Built:** `quired`, the harness host (`quire/quired/`, Go, standard library only).
  - It finds 11 agent CLIs on the build host and runs 7: Claude Code through an adapter, the rest over ACP.
  - Unit tests: 22/22 with the race detector, including regressions for the ANAL-217 review's findings.
  - Security contract (§5 there): Q1 is a harness for trusted local agents. It confines the ACP file operations it serves and makes the questions an agent asks fail closed. It does not stop an agent acting without asking. Authorization at the OS-tool broker, and never-tier limits on computer control, are requirements for Q2–Q6.
  - Live (`evidence/2026-10-18-quire/`): real ACP sessions with opencode, Copilot and omp; Cursor and Kimi need sign-in; Hermes has no provider.
  - Claude Code wrote a file only when the person allowed it, through `quired`'s permission bridge.
  - opencode answered over native ACP.
- **Next:** Q2 platform hooks in Cuttlefish, Q3 interaction design (Atelier), Checker's review.

### 2026-10-18: bring your own Google apps package (ANAL-211, G2)
- **Built** (`docs/installer.md` §15, `docs/gapps.md` §5): an advanced, off-by-default step after the disk choice.
  - The user picks a package with the system file picker. The engine checks it: LiteGapps' layout; only apps, their x86_64 libraries and permission, sysconfig and default-permission XMLs; anything touching the framework, init or SELinux refused path by path; XMLs checked element by element; APKs signed, no platform UID, x86_64 code.
  - It shows every app with its signer, and requires an explicit "not certified" confirmation.
  - The engine then builds a new `product` straight onto the target: the stick's EROFS blocks unchanged plus the package's files, a new dm-verity hashtree, `product_a` moved in super, and `vbmeta_a` with the new descriptor, unsigned (orange). The bootconfig's vbmeta digest follows.
  - Setup's last step and Settings › About show the GSF Android ID for `google.com/android/uncertified`.
- **Tested with synthetic packages only** (`scripts/gapps/`; no Google software):
  - host 89/89, with the plan and disks byte-identical to `main`'s without the step;
  - QEMU 79/79 on `anal211b`, enforcing: five power cuts in the new step, the wizard through the file picker to "installed", the installed system's dm-verity on the new product (a flipped byte gives `data block 74292 is corrupted`), and the apps privileged with their permissions.
- **Found:**
  - OpenBook doesn't set `ro.control_privapp_permissions`, so priv-apps aren't held to an allowlist. The plan warns; the setting is the owner's call.
- **Not done:** the G14 (steps on ANAL-192), a real package, OTAs (an update would replace `product`), fuzzing.

### 2026-10-18: microG as an optional add-on (ANAL-210)
- **The framework patch is in every image.**
  - LineageOS `198fa72864` (signature spoofing for microG) and `03da1783cb` (microG's location provider in /data), cherry-picked unchanged from `lineage-24.0`.
  - Our own patch drops their debuggable-only condition.
  - They apply to our `CP2A.260605` pin, and both products build.
- **The add-on:** microG's signed release APKs, unchanged: GmsCore 0.3.17.252432, Companion and the Services Framework Proxy.
  - They come on the stick (`scripts/microg/add-to-image.sh`).
  - The installer's disk screen offers them, **off by default**.
  - `openbook-addons` installs them as normal apps on the first start, after checking each against the sha256 the image pins.
  - Without the add-on nothing changes: a plan without it is byte for byte the old one, and the live boot logs one line (`docs/gapps.md` §6, `docs/installer.md` §14).
- **Cuttlefish (C):**
  - microG's self-check **18/18 green**.
  - **Negative test passes:** a `com.google.android.gms` signed with another key keeps its own certificate.
  - Device registration and push connect to Google. Home Assistant, Bitwarden and Nextcloud get FCM tokens; their official builds start with and without microG (`docs/COMPAT-MATRIX.md`).
  - After one restart, microG is the network and fused location provider. In the VM it has no network fix: synthetic Wi-Fi, online lookup opt-in.
- **Host tests:** `openbook-addons` 37/37, the installer's add-on path 19/19, the ANAL-191 engine suite 63/63.
- **QEMU (G14 image):** Image `g1a`: the add-on installs under enforcing on the live stick and on an installed disk's first start (self-check 18/18), the wizard's switch off by default, the plain stick has the same 140 packages as `main`'s image. One denial per boot from `stdio_to_kmsg`, removed in `f7df42d` (rerun pending the build lane).
- **Not on the G14 yet:** the checklist is on ANAL-192.

### 2026-10-18: B1, B3, B6, B7 merged; the next stick ordered (ANAL-159)
- **Merged** #77 (B1 Google Sans; the three files byte-identical to google/fonts `47d54ca1`, OFL), #78 (B7 document fonts, OFL; `fonts_customization.xml --check` passes after the merge), #79 (B3 flags v2: 84 enabled, the three that crashed SystemUI or emptied the shade dropped) and #81 (B6: generated by `scripts/brand/`, CC-BY-4.0 by the OpenBook authors).
- **Ordered the next owner stick** from ANAL-192: everything since `anal198`, so the owner writes one stick. The assets' CC-BY-4.0 licence joins the repo-licence decision.

### 2026-10-18: OpenBook's own wallpapers, boot animation, sounds and pointer (ANAL-207, B6)

- All of it is drawn or synthesised by `scripts/brand/` from the brand palette and mark, CC-BY-4.0. `render-brand-assets.sh --check` reproduces `assets/` from a clean checkout.
- **Installed in both products** (the CF build and the G14 product image):
  - `/product/media/bootanimation.zip`, and the sound set with `ro.config.*` and the UI sound paths;
  - the default wallpaper in the framework overlay, and the set of eight in the partner package;
  - `OpenBookPointerOverlay`.
- **Cuttlefish (`anybook-cf-b6`), 8/8 checks:**
  - The boot animation plays at boot and on replay.
  - The desktop shows Folio light. Wallpaper & style lists the OpenBook collection.
  - Each wallpaper's Monet primary matches the prediction within 3 RGB units for 7 of 8 (Bloom light: 7).
  - The framework draws our 20 pointer shapes in all 6 fills and 3 strokes, and a virtual mouse shows our arrow on screen.
- **The pointer overlay.** It replaces AOSP's nine pointer colour styles, adding its own attributes. A first try, compiled as resource package `android`, was enabled but ignored at runtime (package ID 0x01). Evidence: `evidence/2026-10-17-brand-assets/`.

### 2026-10-18: metric-compatible document fonts (ANAL-208, backlog B7, PR #78)
- **Only 7 of Googlebook's 20 document-font families are public (C).** Arimo, Tinos, Cousine, Gelasio, Comic Relief, Archivo Black and Archivo Narrow are in google/fonts, the versions Googlebook ships. Tachyonic, Velarium, Geotic, Tisane, Gaumond, Trophis, Codecs, Comedic Sans, Whendings and Arvos name `googlefonts` repositories that aren't public. So Verdana and Tahoma have no stand-in.
- **Metrics (C).** On all 95 printable ASCII glyphs, Arimo, Tinos and Cousine match Adobe's Helvetica, Times and Courier AFMs, regular and bold; Roboto matches none.
- **Two configs, because WebView reads only one (C).** The framework takes families and aliases from `/product/etc/fonts_customization.xml` (AOSP 17 accepts `<alias>`, and the customization's come first). WebView 145's Skia parses only `/system/etc/fonts.xml`, so a small `frameworks/base` patch declares the same families there and moves `arial`, `times new roman`, `courier new` and `georgia`, and adds `comic sans ms`.
- **In Cuttlefish (C).** Each of those five names renders in its stand-in, within 0.015 px of the font's own widths; unstyled text, `sans-serif` and `serif` don't change. A family that exists nowhere now falls back to Arimo, through Blink's last resort (`Sans`, then `Arial`).
- **Evidence:** `evidence/2026-10-17-doc-fonts/`.

### 2026-10-18: Google Sans in the desktop products (ANAL-202, backlog B1, PR #77)
- **Done** (`docs/googlebook-ui.md` §3.1, `device/anybook/common/desktop/fonts/`):
  - **Fonts.** Google Sans, Google Sans Italic and Google Sans Flex from google/fonts `47d54ca1`, byte for byte (sha256 in `fonts/README.md`), as `prebuilt_font` modules in `/product/fonts`. Each family's `OFL.txt` reaches `/product/etc/NOTICE.xml.gz` through its own `license` module. `TRADEMARKS.md` ships next to them; "Google" stays out of OpenBook branding.
  - **Font config.** `/product/etc/fonts_customization.xml` (40 families) is committed. The build regenerates it with `scripts/ui/fonts-customization.py --check` and fails if the two differ.
  - **Framework values.** `config_headlineFontFamily(Medium)` and `config_bodyFontFamily(Medium)` in `AnyBookDesktopFrameworkOverlay`, as on Googlebook. Both products inherit them from `desktop.mk`.
- **Evidence** (`evidence/2026-10-17-typography/`): both products build. Cuttlefish on the Radeon 610M, base against fonts: all 40 families load, the four values resolve, the UI renders in Google Sans; desktop capture unchanged; crash buffer empty and the same three denial kinds in every run. `product.img` +9.24 MiB in both products. Settings scroll, three alternating pairs on a loaded host: janky 1.35 % with the fonts against 4.32 % without. After merging `main` (B2, B4, B5), both products build again, and Cuttlefish shows Google Sans with B4's circles and B5's taskbar.
- **Found:** Google Sans' taller line metrics make Settings' rows about a quarter taller. A Soong `genrule` can't name its output like one of its sources ("multiple locations for label").
- **Next:** the G14 check on ANAL-192's stick. B7 (ANAL-208) adds its families to the same generator.

### 2026-10-18: desktop flag set v2, 84 Googlebook flags on (ANAL-204)
- **Triage (C).** Googlebook enables 218 flags that AOSP 17 declares and our build leaves off. Each now has a category, a decision and a reason (`device/anybook/common/desktop/release/googlebook-triage.tsv`): 84 enabled in six groups, 43 deferred, 89 skipped, 2 dropped.
  - 23 have no reader in our tree, so they do nothing. Among them are `perfect_edge` and `enable_taskbar_icon_desktop_clicks`.
  - Googlebook runs in headless system user mode (`ro.fw.mu.headless_system_user=true`); OpenBook doesn't, so the `hsu_*` flags are skipped.
- **Dropped after testing (C, Cuttlefish):**
  - `enable_add_window_decoration_to_all_tasks` crashed SystemUI when a minimized window was restored from the taskbar.
  - `start_on_gone_scene_if_no_lockscreen` emptied the notification shade. With OpenBook's disabled lock screen, SystemUI starts on Gone, and the keyguard section that binds the notification stack never runs. Setting a PIN on the same image brings the rows back.
- **Visible (C):** box shadows and a 1 px border on desktop windows, 60 px stepped cascading, the windowing pill in the maximize menu, QS tile tooltips, power-menu blur, and the Cast tile over Ethernet.
- **Tools:**
  - `scripts/desktop-flags.py --list` (the value set from the triage);
  - `scripts/ui/flag-facts.py` (declarations and readers);
  - `scripts/ui/flag-checks.py` (desktop checks driven by a virtual uinput mouse);
  - `scripts/ui/flag-triage-md.py`.
- **Deviation:** the six groups were built together in one image, because sibling builds held the shared lane. Each failure was then traced to one flag and confirmed in a rebuild (v3, v4).

### 2026-10-18: a clean default desktop (ANAL-206, backlog B5)
- **Done** (`docs/aosp-desktop.md`, "The default desktop"):
  - **No search box.** A Launcher3 RRO empties the hotseat's search slot, which held AOSP's `QuickSearchBox` "Google" bar. The same RRO overrides `QuickSearchBox`, so the app is gone; Settings search, the search key and global search don't need it.
  - **Taskbar pins** from a Launcher3 partner customization package (`AnyBookDesktopPartnerCustomization`): Files, Settings, the browser (today WebView Shell, the only one we ship), Calendar, Gallery, and Camera, which Camera2 hides on devices without a camera. No desktop icons.
  - **Quiet:** touch sounds off (`def_sound_effects_enabled`, as Googlebook), LatinIME's keypress sound off (AOSP turns it on at 600 dp and up), the screenshot shutter only when a region requires it (`screenshot_remove_nonforced_sound`, as Googlebook). Lock sounds stay on: they are the G14 checklist's SoundPool probe.
- **Evidence** (`evidence/2026-10-17-clean-desktop/`): both products build. Cuttlefish on the Radeon 610M: `scripts/ui/desktop-defaults.sh` and `scripts/desktop-capture.sh` pass, with before/after screenshots. The G14 product's live image in QEMU: five pins (no camera), no search box, the installer's entry still there, and `live-qemu.sh` 40/40.
- **Found:** an RRO value only wins where its configuration is at least as specific as the target's, so the LatinIME overlay repeats its value for `sw600dp` and `sw768dp`. Parallel Cuttlefish containers need `CF_ARGS=--vhost_user_vsock=true`, or `run_cvd` fails with "Can't tombstone server socket".
- **Not done:** the screenshot flash (no setting exists), and "add new apps to the desktop", which AOSP 17 hard-codes on. Both need patches.

### 2026-10-17: background blur on the G14, measured in Cuttlefish (ANAL-203)
- **Change (C).** `ro.surface_flinger.supports_background_blur=1` in the G14 product, as on Googlebook. Cuttlefish already had it and is unchanged. AOSP 17 needs nothing else: its blur configs default to on, and WM turns blur off by itself in battery saver and at severe thermal status (`docs/googlebook-ui.md` §2.3).
- **Cost in Cuttlefish (C)** (Radeon 610M, gfxstream; `scripts/ui/blur-bench.sh`, 6 alternating rounds of 20 shade and 20 Quick Settings cycles):
  - Blur is applied only when on: one layer, `VRI-NotificationShade`, radius 34.
  - On a quiet host SystemUI's frames don't change. SurfaceFlinger puts about two thirds of the frames on the GPU, at 2.8–4.0 ms of RenderEngine time each.
  - Under heavy host load the shade's janky frames double (16.9 vs 8.1 %).
  - No crash, restart or amdgpu fault.
- **G14 image (C).** It builds with the property, and in QEMU (SwiftShader) it blurs Quick Settings, only with blur on. On a CPU renderer blur costs SurfaceFlinger about one frame in five while a panel moves.
- **G14 check (built, not run).** The graphics add-on gets a `blur` part, which runs first and takes about 7 minutes. `gfx_blur` verdicts: blur applied, no GPU hang, frame cost against 120 Hz thresholds.
- **Found (C).** Googlebook and Google's 37.1 desktop image set SystemUI `config_supportBlurredWallpaper=false`: no full-screen blur behind the shade. Ours blurs the whole desktop behind the small Quick Settings panel. Passed to B3 (ANAL-204) with `blur_on_more_surfaces`.
- **Renderer properties (C, evaluation only).** Googlebook's `ro.hwui.use_vulkan`, `debug.renderengine.vulkan` and `debug.renderengine.graphite_desktop_optin` move HWUI and RenderEngine from GL on ANGLE onto Vulkan, or Graphite. Our build already enables Graphite's desktop flag, so one property would switch RenderEngine. They stay off: the G14's failing AHardwareBuffer dEQP case is the path both Vulkan backends use (`docs/graphics-amd.md`).
- **Host note.** Two Cuttlefish VMs on this host need `CF_ARGS=--vhost_user_vsock=true`. Otherwise the second one's modem simulator can't bind its vsock port, and `cvd create` fails.

### 2026-10-18: BootOrder decision, the Googlebook review and B4 merged (ANAL-159)
- **Merged** #70 (ANAL-191: without consent, OpenBook is appended to `BootOrder`; still `O_EXCL`; QEMU/OVMF: Windows stand-in stays default, OpenBook in the boot menu), #71 (ANAL-201: licensing checked: Google Sans and Google Sans Flex are OFL from google/fonts; no Google binaries committed; GMS user-supplied only; microG optional; no Play Integrity bypass) and #73 (ANAL-205 B4).
- Deleted the merged branches. #72 (ANAL-203) and ANAL-210's branch stay while their runs are active.

### 2026-10-17: circular icons and no wallpaper dim, as on Googlebook (ANAL-205, backlog B4, PR #73)
- **Set (C):**
  - in `AnyBookDesktopFrameworkOverlay`: `config_icon_mask` (a circle path of our own), `config_useRoundIcon=true` and `config_wallpaperDimAmount=0`;
  - in `desktop.mk`: `persist.wallpapercolors.threshold=55` and `max_dark_area=12`. AOSP 17's `WallpaperColors` reads both.
  - The CF and G14 products both build with them.
- **Measured in Cuttlefish against the unchanged base (C)** (`evidence/2026-10-17-shape-wallpaper/`):
  - `cmd overlay lookup` resolves all three values.
  - All apps, the taskbar, the Settings homepage and Settings' app list draw circles.
  - Grey 180 shows as 180 (171 before, AOSP's 5 % dim).
  - `WallpaperColors` now gives the dark-text hint to a grey of luminance 0.62 and to a white image with 8 % dark pixels.
  - No crashes.
- **Icon-shape picker (C):**
  - Wallpaper & style's Icons → Shape offers five shapes and shows Circle selected, which now matches what the home screen draws. With AOSP's mask it showed Circle while the launcher drew a rounded square.
  - A user's pick still wins in the taskbar.
  - The taskbar's all-apps panel keeps the system mask after a pick, in the baseline build too (AOSP Launcher3, cause not traced).
- **Tools:** `scripts/ui/shape-shots.sh`, `scripts/ui/wallpaper-dim-check.sh`, `scripts/ui/wallpaper-hints.sh`.

### 2026-10-17: the Googlebook image reviewed, GApps options, and Google Sans on OpenBook in a VM (ANAL-201)
- **Why Googlebook looks cleaner (C)** (`docs/googlebook-ui.md`):
  - It replaces the platform UI with Google builds: the Pixel Launcher, plus SystemUITitan and SettingsGoogle, both signed with the platform key.
  - It adds 61 overlays, Google Sans, background blur and 728 more flags; 510 of those flags aren't declared in AOSP 17.
  - GMS doesn't change the look: Google's own Google APIs Desktop image has the same GMS APEX and still shows AOSP's launcher, SystemUI and Settings.
- **Fonts (C).** AOSP 17's SystemUI, Launcher3 and SettingsLib ask for `google-sans*` and the 30 Material 3 `variable-*` families, and fall back to Roboto. Google Sans and Google Sans Flex are now OFL in google/fonts. In Cuttlefish, pushing the fonts, our `fonts_customization.xml` (40 families) and a four-value RRO renders Settings, Quick Settings and all apps in Google Sans (`evidence/2026-10-17-gbos-ui/fonts-prototype/`).
- **G14 gap (C).** The G14 product doesn't enable background blur; Cuttlefish inherits it from `device/google/cuttlefish`.
- **GApps (C)** (`docs/gapps.md`):
  - No image may contain Google apps.
  - microG (Apache-2.0, x86_64) plus LineageOS's Android 17 spoofing patch is the option we can ship.
  - LiteGapps `x86_64/37` is the only current Android 17 x86_64 package; it would be user-supplied, with a `product` rebuild in the installer (design, untested).
  - MindTheGapps dropped x86 after Android 13.
- **Not booted:** Google APIs Desktop 37.1 in emulator 37.2.12. The binder storm between SurfaceFlinger and the ranchu composer is in `gapis-desktop-37.1/boot-failure.txt`.
- **Tools:** `scripts/gbos-inventory.py`, `scripts/overlay-values.py`, `scripts/aconfig-storage-dump.py` (reads Android 17 flag storage offline), `scripts/ui/`.

### 2026-10-17: without consent, OpenBook goes last in `BootOrder` (ANAL-191, PR #70, owner decision)
- **Done** (`docs/installer.md` S11, §12.11, §13.7). The owner approved our recommendation:
  - an install with "Start OpenBook by default" off now appends its new `Boot####` to the end of `BootOrder`, so the other system stays the default and OpenBook is in the firmware's boot menu;
  - with the box ticked it still goes first; no other entry changes, and every write is read back;
  - Confirm says "OpenBook is added to this laptop's boot menu; Windows stays the default". Done names the entry and the boot-menu key.
- **Evidence** (`evidence/2026-10-17-installer-bootorder/`), QEMU/OVMF, enforcing:
  - engine host tests 65/65; wizard runs 41/41 (`anal191h`);
  - the Windows-like disk now boots a stand-in EFI app. With the install's NVRAM it still starts by default (`BootCurrent=0007`);
  - OVMF's boot menu lists OpenBook last, and picking it boots Android (`BootCurrent=0005`). Before this change the menu did not list it;
  - no denials for init, the daemon or the app.
- **Next:** the stick after `anal198` carries this; ANAL-192's spare-drive install will be the first real NVRAM write.

### 2026-10-17: the follow-ups merged; the next stick waits for the owner's results (ANAL-159)
- **Merged** #67 (ANAL-179: `audioserver` may use apps' memfds, the same rule AOSP gives mediaserver; SoundPool denials 2 → 0 in QEMU) and #68 (ANAL-191: the efivarfs label, mounted on live boots only).
  - The engine creates a new `Boot####` with `O_EXCL`, so it can't overwrite another OS's entry.
  - It touches `BootOrder` only with consent.
  - In QEMU/OVMF it booted with the fallback file removed (`BootCurrent=0005`), and Windows' entry and `BootOrder` stayed byte-identical.
- **Not building a new stick yet.** The owner hasn't run `anal198`. ANAL-198's routing now wakes the coordinator to order the next stick from ANAL-192 once that session is read.

### 2026-10-17: the installer creates firmware boot entries (ANAL-191, PR #68, follow-up to ANAL-198's #64)
- **Done** (`docs/installer.md` §12.11):
  - efivarfs gets a label (`openbook_efivarfs`, genfscon) and is mounted by init on live boots only.
  - `openbook_installd` may list and read variables and create one. It cannot delete a variable.
  - After verification the engine creates one `Boot####` "OpenBook" → `HD(GPT partition)/\EFI\OpenBook\systemd-bootx64.efi`.
  - `BootOrder` changes only with the user's "Start OpenBook by default"; then OpenBook goes first and the rest keep their order.
  - `openbook-install nvram` lists the firmware's entries.
- **Evidence** (`evidence/2026-10-17-installer-nvram/`), QEMU/OVMF, enforcing:
  - engine host tests 63/63; wizard runs 33/33;
  - a whole-disk install's entry boots with `EFI/BOOT/BOOTX64.EFI` deleted (`BootCurrent` = the new entry);
  - alongside a Windows-like disk, the "Windows Boot Manager" entry and `BootOrder` are byte-identical, and the new entry boots through `BootNext`;
  - no denials for init, the daemon or the app.
- **Owner decision:** without consent the alongside entry is not in `BootOrder`, and EDK2 firmware then does not list it in its boot menu. Allow appending OpenBook at the end of `BootOrder`? (Approved; see the entry above.)
- **Next:** the stick after `anal198` carries this; ANAL-192's spare-drive install will be the first real NVRAM write.

### 2026-10-17: SystemUI's SoundPool sounds under enforcing (ANAL-179)
- **Done:** ANAL-198 found that `audioserver` could not use SystemUI's SoundPool memfds (`appdomain_tmpfs`) once Codec2 decoded. It is fixed with one TE rule, `system_ext/audioserver.te`, which is AOSP's own `appdomain:memfd_file` grant in tmpfs form. No MLS change was needed: `private/mls` exempts `appdomain_tmpfs` from its read and write constraints.
- **Evidence** (`evidence/2026-10-17-soundpool/`), QEMU, enforcing:
  - on `main`, the unlock sound fails twice (2 denials, "could not create track"), and nothing reaches the codec;
  - with the fix, there are 0 denials, and both unlock sounds reach the codec (0.10 s and 0.15 s, the length of `Unlock.ogg`).
- **Next:** the next owner stick carries it. On the G14, the default boot's logs should show no `audioserver appdomain_tmpfs` denial.

### 2026-10-17: the kernel heap and efivarfs, and the `anal198` stick (ANAL-159)
- **The owner merged** #64 (ANAL-198: system DMA-BUF heap, efivarfs, Codec2 fixes) and #65 (the stick `openbook-live-20261017-anal198`, built from `main` `2d90741`, with Vulkan 1.4 and four add-ons). In QEMU: live 40/40, wizard 25/25, end to end 78/78, a ringtone decodes.
- **Woke ANAL-179** (SoundPool memory under MLS) and **ANAL-191** (efivarfs label for `Boot####` entries). Deleted the merged branches. ANAL-198's description now routes the owner's results to each issue.

### 2026-10-17: G14 results merged for power, input, audio, Wi-Fi and the bridge (ANAL-159)
- **Merged** #56 (ANAL-200), #57 (ANAL-178) and #58 (ANAL-179) after checks, with `main` merged into each and STATUS resolved by hand. The only MACs in the evidence are locally administered QEMU addresses.
- **Woke ANAL-192** to rebuild the integrated stick on `9598403` (two AOSP patches and a third add-on landed after its first image). **Woke ANAL-177 and ANAL-176** to read the owner's `anal176t` session, which holds the graphics check and the audio fixes. The owner had replied only on ANAL-178.

### 2026-10-17: the power check on the laptop: PSP ruled out; the lid works (ANAL-178)
- **Read** the owner's `anal176t` stick (read-only copy `g14/stick-20261017T154112Z`): default boot with the lid test, "save logs", the power check, and ANAL-177's graphics check (`live-002`, for ANAL-177).
- **Lid:** close → sleep → s2idle for 5 min 20 s → open → wake (C).
- **S0i3:** missed in all four power-check cycles. At entry every endpoint, the PSP included, is in D3, so the driverless-PSP hypothesis is out. The SMU's "Active time" table names `USB4_0` and `MPM`, but the table's layout does not match the kernel's struct, so the names are unconfirmed. Next: the same table on the laptop's own Linux 7.2.
- **Not seen:** battery saver (no trace in the logs); the touchpad capture saw no finger.
- `lid_events` now reads Android 17's "Sleeping power group … reason=lid_switch".

### 2026-10-17: G14 audio, Wi-Fi and Bluetooth results from the owner's two sessions (ANAL-179)
- **Done:** read both sessions (`anal178c`, `anal176s`) from the host copies, read-only, and redacted them. The `wifi_*`, `bt_*` and `audio_*` verdicts and logs are in `docs/g14-audio-net.md` §10, with G14 rows in `COMPAT-MATRIX.md`.
  - **Wi-Fi works:** MT7925 on 5320 MHz (160 MHz), DHCP, internet.
  - **Bluetooth pairs**, and A2DP runs with LDAC 96 kHz.
  - **The speakers and mic work through ALSA.**
- **Fixed:**
  - The audio HAL is now paced by the codec (AOSP patch 0002). Before, on the G14 the Android loopback lost 24 of 30 slices, and the HAL padded the capture 7 times. In QEMU, in one boot against AOSP's pacing: the tone reaches the codec whole (2.05 s against 1.65–1.70 s), and capture padding drops from 7 to 0.
  - The hwtest loopback now names its ports. In session 2 the tone had gone to the Bluetooth headphones.
  - hwtest's Wi-Fi status was stale.
  - PNO now runs through the driver's scheduled scan. With the screen off and no connection, the G14 had stopped scanning.
- **Waiting on the G14:** Bluetooth audio and app audio under enforcing. The Bluetooth app aborted when A2DP started, and the browser had no sound. The fix is #52, now merged.
- **Next:** ANAL-192's integrated stick runs this issue's checks (`docs/g14-audio-net.md` §10.4):
  - an iperf3 server configured;
  - headphones plugged in during the default boot;
  - Bluetooth audio and a browser video in the default boot;
  - `audio_android_clean` and `wifi_pno` in the save-logs boot.

### 2026-10-17: G14 results for power and input; the touchpad clock fixed (ANAL-178)
- **Read** the owner's `anal178c` and `anal176s` sessions from ANAL-176's host copies (`docs/power-input.md` §7, `evidence/2026-10-17-power-input/g14-sessions/`).
- **Touchpad.** The gestures library's "Clock changed backwards" every 40 ms comes from the kernel autorepeating `BTN_TOOL_FINGER`. A vendor usage page in the ELAN descriptor turns on `EV_REP`, and the repeat frames carry no `MSC_TIMESTAMP`. Fix: EventHub turns kernel key repeat off on touchpads (`aosp/patches/frameworks/native`). QEMU, with the laptop's own descriptor on `uhid`: 173 repeat frames and 172 errors before the fix, 0 and 0 after.
- **Shown on the laptop:** the lid and power-button config, the hotkey layouts, the health HAL (charge counter, state of health 88.7 %, GOOD), the power HAL's EPP changes, and Android's own s2idle (woken by a key; display and Wi-Fi back). S0i3 is still missed, and the lid was not closed.
- **For ANAL-192's stick:** the power-check boot (or the Linux run), a lid close, battery saver, 20 s of touchpad use in "save logs". New report verdicts read them: `lid_events`, `epp_modes`, `health_hal`, `touchpad_clock_warnings`.

### 2026-10-17: G14 enforcing desktop merged; ANAL-192 builds the owner stick (ANAL-159)
- **Merged** #52 (ANAL-176) after checks.
  - Privacy: the G14 screenshot's Bluetooth list is blanked.
  - Evidence: `enforcing=1`; desktop at 28.0 s and 29.0 s; dropped frames from 151 to 0; Wi-Fi on 5 GHz with internet; QEMU 40/40.
  - The Checker's validation came first.
- **README:** the G14 screenshot is now the multi-window desktop from `anal178c`; M3, M5 and the hardware table record the enforcing desktop. COMPAT-MATRIX has the first bare-metal G14 row.
- **Woke ANAL-192** to build the integrated stick from `main`.

### 2026-10-17: installer merged; one owner stick from here on (ANAL-159)
- **Merged** #53 (ANAL-191) after checks.
  - Engine refusals were verified with the target unchanged.
  - The dry run wrote 0 blocks.
  - The installed disk boots alone into OpenBook setup.
  - No installer denials appeared in enforcing boots.
  - The daemon runs on the live stick only, and only `platform_app` may use its socket.
- **On the G14:** the owner's `anal178c` session showed the normal enforcing boot reaching the desktop at 28 s, with Wi-Fi connected (ANAL-176; evidence with PR #52).
- **Woke ANAL-178, ANAL-179 and ANAL-200** to read their parts of the owner's last two sessions from the host copies. The owner had replied only on ANAL-176.
- **Promoted ANAL-192**, which now builds the single owner stick and checklist, then runs the installer's end-to-end tests.

### 2026-10-17: anal176s on the G14: the three fixes hold; Bluetooth and app audio fixed (ANAL-176)
- **G14** (`anal176s` = `main` + PR #52, default entry, enforcing, 8 minutes):
  - no storage notice for the stick (`Not managing disk 8:0`);
  - no lock-screen blackout;
  - 0 frames dropped (151 on `anal178c`).
- **Found and fixed:**
  - Bluetooth aborted whenever an audio device connected (the A2DP queue memfd was denied to `bluetooth`).
  - The browser had no sound: AudioFlinger's control blocks are MLS-protected `s0` memfds, because AOSP 17 does not enable `memfd_class`.
  - Two policy lines in `hal_audio_net.te`.
- **Next stick:** `openbook-live-20261017-anal176t`, QEMU 40/40, with one lock held across the build and the snapshot. Evidence: `evidence/2026-10-17-g14-desktop/g14-anal176s/`, `anal176t/`.

### 2026-10-17: the installer wizard, the install engine and first-boot setup (ANAL-191, PR #53)
- **Done** (`docs/installer.md` §12):
  - `openbook-install`: the engine and its daemon. It does the disk inventory, the hardware check, the read-only plan and the install, with S1–S13 in the engine. It writes GPT and FAT itself, with no mounts.
  - `OpenBookInstaller`: the seven Compose screens after the hi-fi design. It opens by itself on live boots.
  - OpenBook setup: language, Wi-Fi and screen lock on an installed system's first boot.
  - Install data on the stick: the layout, hashes, and `super` metadata for the installed 12 GiB size.
- **SELinux:** the daemon runs enforcing in its own domain and writes only through whole-disk nodes with their own label. The disk-identity sysfs files carry a new label. The app supplies display, touchpad and battery, because Treble keeps a system daemon out of those files.
- **Decision 6:** our G14 kernel has no `EFIVAR_FS`, so there is no firmware boot entry. Whole-disk installs boot through the fallback path; alongside installs need a firmware entry made by hand.
- **Evidence** (`evidence/2026-10-17-installer-wizard/`):
  - engine host tests 53/53;
  - QEMU 25/25, enforcing, at 2880×1800 with density 240: the dry run leaves the NVMe untouched (0 allocated blocks), the install takes 20 s and is verified, and the NVMe alone boots into OpenBook setup and then the launcher;
  - the live matrix 39/39 on the same image;
  - screenshots of every screen.
- **Not shown:** anything on the G14; alongside booted in QEMU; `openbook-bootsync`; the text hardware report.
- **Next:** the owner's dry run on the G14 (§12.8), then ANAL-192.

### 2026-10-17: the G14's default entry reaches the desktop under enforcing; live stick safety (ANAL-176)
- **Done:**
  - Read the owner's `anal178c` stick (built from `main`). The default entry, under SELinux enforcing, reached the desktop at 28 s on a freshly written stick, with the boot animation at 17 s (desktop3: 59 s) and no APEX decompression. It was then used for 4 minutes: Wi-Fi connected, Bluetooth, browser, apps.
  - The boot had 23 denials and no crashes.
- **Fixed** (branch `anal-176/live-stick-safety`):
  - vold took the boot stick for a USB drive, and SystemUI offered to set it up (format it). The owner opened the wizard and backed out. Fix: a vold patch that skips the disk the running system is on, with a QEMU matrix check for it.
  - The boot lock screen turned the screen off after 10 s. Fix: none until a PIN is set.
  - drm_hwcomposer's overlay planes cost 151 frames that were never shown. Fix: overlay planes off (H).
  - `live-report.py` crashed on the touchpad-clock verdict.
- **Evidence:** `evidence/2026-10-17-g14-desktop/g14-anal178c/`. `vold` and the overlay build. No image was built from this branch, because ANAL-191 holds the lane.
- **Next:** the next combined stick from `main` (`docs/g14-desktop.md` §6).

### 2026-10-17: cleanup and one consolidated status (ANAL-159)
- **Done:** the owner asked for less sprawl. No PRs are open. The remote branches went from 49 to 4. Two branches with commits never merged are kept as `archive/` tags. This file's top section is now one state of the union, with a next step for every open issue. `docs/PLAN.md` §4 and §7 point here instead of keeping their own copies.

### 2026-10-17: graphics check merged; the installer wizard starts (ANAL-159)
- **Merged** #48 (ANAL-177) after checks. Every number matches the raw results (610M pre-check, Cuttlefish EGL and ANGLE end2end), and nothing is claimed for the G14. The add-on applier writes new files only, and only on a `/dev/disk/by-id/usb-*` stick.
- **Promoted ANAL-191** (wizard and `openbook-install` engine) into the AOSP lane, which the owner asked for on ANAL-189: the design "to your recommendation", then moving on to installing on the laptop. It builds on `docs/installer.md` decisions 1–5 with no resizing in v1, and is tested only in QEMU. Publishing an image and installing to a real disk stay owner-gated.
- **Waiting on the owner:** the `combined` stick run (ANAL-176/178/179/200) and, optionally, the graphics check add-on (ANAL-177).

### 2026-10-17: Graphics conformance, the graphics check for the G14 stick (ANAL-177)
- **Done** (`docs/graphics-amd.md`, "dEQP and CTS on the G14"):
  - The graphics check: an add-on for the owner's live stick, so no new image is needed. One boot runs Android 17's dEQP (Vulkan 1.1 as shipped and 1.4, GLES on ANGLE and radeonsi, EGL in the dEQP app) and ANGLE's end2end CTS tests on the laptop's own drivers through Mesa's deqp-runner, saves the results on the stick and powers off.
  - `openbook-live-init` gained the add-on step (`androidboot.openbook.addon`). It also keeps copying the kernel log during long commands.
  - The case lists are fixed subsets of the Android 17 mustpass (66,226 VK, 13,671 GLES, 1,287 EGL and 2,364 ANGLE end2end cases), recorded in the evidence.
  - ANGLE end2end builds in our tree (`external/angle/android/cts`).
- **Pre-check on the 610M** (gfx1036, not the G14's GPU):
  - Vulkan 1.1 as shipped: 43,248 pass, 57 fail, 1 crash. 47 of the failures are Amber needing a Vulkan 1.2 entry point.
  - Vulkan 1.4: 45,161 pass, 5 fail.
  - radeonsi GLES: 13,621 pass, 0 fail.
  - **Provisional recommendation: ship Vulkan 1.4 (`ANDROID_STRICT=false`)**, once the 890M agrees.
- **Baselines:** Mesa CI has no gfx1150 expectation files, neither in 26.2.5 nor in main of 2026-10-17. The closest are `radv-navi31` (RDNA3) for RADV and the `vangogh`/`mendocino` files for radeonsi.
- **Plumbing, off the laptop:**
  - QEMU ran the add-on end to end on a copy of `combined` (SwiftShader).
  - Cuttlefish ran the two app parts with full lists: dEQP-EGL 822 pass, 0 fail; ANGLE end2end 1,802 pass, 7 fail.
  - Fixed on the way: `am instrument` needing init's classpath; ANGLE's missing in-app watchdog; stale FUSE entries breaking `/sdcard`.
- **Evidence:** `evidence/2026-10-17-graphics-cts/`.
- **Next:** the owner's stick run or the device agent, then the matrix rows and the Vulkan decision.

### 2026-10-17: one G14 stick from `main`; the bridge in enforcing boots (ANAL-159)
- **Done:** merged #46 (ANAL-200) after checks. Built the G14 product and a live image from `main` (`8b40298`), with ANAL-178's power check add-on, and ran the full live matrix (39/39).
- **Found:** every enforcing boot logged `mount binfmt_misc ... Permission denied` from the bridge's `berberis.rc`. The Cuttlefish product inherits Cuttlefish's rules for this; the G14 product's policy had none. ANAL-200's tests ran on Cuttlefish and in the permissive "save logs" entry, so they couldn't see it.
- **Fixed** (#47): the same two init rules in the PC vendor policy. In the rebuilt `openbook-live-20261017-combined` (`01750c5`), enforcing boots show no binfmt_misc denial. An arm64 executable run through binfmt_misc as the shell user passes all four bridge checks. The live matrix passes 39/39 and the power check 10/10.
- **Evidence:** `evidence/2026-10-17-g14-combined/`.
- **Next:** the owner writes `combined` and runs the steps in "Next G14 stick" above. ANAL-177 (dEQP/CTS) takes the AOSP lane.

### 2026-10-17: ARM compat, Digitalis is our Android 17 bridge (ANAL-200)
- **Done** (`docs/digitalis.md`): Digitalis is built from source in our A17 tree and ships in both products. The A17 guest NDK closes the API gap. Three fixes:
  - `MRS` ID registers emulated as Linux does (Tor VPN runs);
  - bit-exact `FRECPE`/`FRSQRTE`;
  - the Fennec crash, which was Android 17 no longer setting `Build.CPU_ABI` for bridged apps (ART patch). arm64 Firefox renders pages.
- **Evidence** (`evidence/2026-10-17-digitalis-a17/`):
  - 14/16 arm64-only apps on our Cuttlefish build (libndk_translation 13/16), in two identical runs;
  - CoreMark 0.394/0.399 there; in the same emulator, 0.300 against libndk_translation's 0.457;
  - 0 `FRECPE` mismatches against QEMU;
  - host tests 3,761/3,763 (2 skipped);
  - shipped-file audit: 89 files, built from source;
  - the G14 live image's `bridge_*` verdicts all pass in QEMU.
- **Next:** `bridge_*` verdicts, probe and CoreMark on the G14; upstream reports after the owner's OK.

### 2026-10-17: Power and input, Android side built: health HAL, lid config in force, one stick for all G14 tests (ANAL-178)
- **Done:** an OpenBook health HAL (the ACPI battery's charge counter and state of health; Android showed health "unknown"); the lid, power-button and hotkey pieces built and checked in a booted image; save logs records the touchpad's HID descriptors and raw events for the "Clock changed backwards" errors ANAL-176 handed on, and `service list` no longer stalls the capture.
- **Stick:** `openbook-live-20261017-anal178b` contains ANAL-179's `audionet3` (and ANAL-176's desktop4 fixes) plus all of this, with the power check on its ESP. QEMU: live matrix 39/39, power check 10/10, lid config in force (`evidence/2026-10-17-power-input/anal178b/`).
- **Next:** the owner writes `anal178b` instead of `audionet3` and runs `docs/power-input.md` §5.

### 2026-10-17: Power and input: S0i3 tests, laptop lid and power config (ANAL-178)

**Done** (`docs/power-input.md`)
- **S0i3, from the desk:** the laptop's own Linux 7.2 shows no S0i3 failure in 4 cycles (indirect), so the BIOS is not the blocker. amd_pmc, LPS0, IOMMU and CPU idle behave the same on both kernels. The one PCI function Linux drives and we don't is the AMD PSP (`ccp`). HYPOTHESIS: a driverless PSP stays in D0 and keeps its bridge GPPA in D0 through suspend.
- **Tests:** two test-only modules (an S0i3-entry PCI snapshot, and PCI power management for driverless functions), probe v7 with a one-boot bisect (`psp`, `dummy`, `asus`), an add-on that puts it on the owner's live stick, and a Linux comparison script (baseline, without amd-pmf, without `ccp`).
- **Android:** a PC framework overlay with Googlebook's laptop values (lid closes → sleep, AOSP's default is nothing; power button locks), a key layout for the ASUS WMI hotkeys, and save-logs facts and verdicts for power and input.

**Evidence:** `evidence/2026-10-17-power-input/`. In QEMU: the add-on's entries 14/14 (LPS0 fixture, s2idle) and 10/10 (as shipped), and the save-logs script inside Android 17. The overlay links against the product's framework (`aapt2`, `idmap2`); the layouts pass `validatekeymaps`. Nothing new has run on the G14 yet.

**Next:** the owner runs the Linux comparison and the power check (`docs/power-input.md` §1.5); then the kernel-lane fix, and the Android pieces in the AOSP lane after ANAL-179.

### 2026-10-17: G14 audio, Wi-Fi and Bluetooth, Android side (ANAL-179)

**Done** (`docs/g14-audio-net.md`)
- **Wi-Fi:** AOSP's wpa_supplicant and the framework's own nl80211 code, no vendor HAL (none is public) and no wificond (Android 17 has none); a DRIVER-command hook for the country code; the signed `regulatory.db`; AOSP's MT7925 firmware kept (the build the G14 loaded).
- **Bluetooth:** AOSP's AIDL HAL over the HCI user channel (`btusb` + `btmtk`), laptop profiles.
- **Audio:** `openbook-audio-setup` finds the codec's ALSA card at boot (the ALC285 is card 1 or 2) and unmutes it; an AOSP patch lets the example HAL use that card; a 48 kHz policy with jack handling.
- **Found:** no app could play or record (the audio HAL's message-queue memfds were denied), cfg80211's regulatory keyring was unsearchable, HDA codecs come up muted.
- **Tests:** `openbook-hwtest` runs in the save-logs entry (Wi-Fi scan/connect/DHCP/iperf3, Bluetooth, speaker-to-mic loopbacks), with `live-report.py` verdicts; a QEMU rig with an HDA card and a `mac80211_hwsim` access point.

**Evidence:** `evidence/2026-10-17-g14-audio-net/`. In QEMU: WPA2 connect, DHCP, iperf3 about 650–770 Mbit/s; a tone reaches the codec through ALSA cleanly and through AudioFlinger with dropped buffers (VM; open item). Nothing on the G14 yet.

**Next:** the owner boots `openbook-live-20261017-audionet3` (this branch + ANAL-176's desktop4): connect Wi-Fi, pair a device, then the save-logs entry (`docs/g14-audio-net.md` §7).

### 2026-10-17: G14 boots of desktop3, and desktop4 (ANAL-176)

- **Done:**
  - Read the owner's two `desktop3` boots:
    - The amdgpu `firmware_load` denial is gone.
    - The save-logs boot reached the desktop; enforcing boots would hit 14 denial lines, down from 66.
    - The first boot (non-logs) was switched off on a black screen while it was still decompressing APEXes, before SurfaceFlinger could start. So the enforcing entry is still unproven on the panel.
    - Escape killed the launcher.
    - The save-logs entry powered off, as designed.
  - Fixed:
    - APEXes now ship uncompressed (first boot of a fresh stick without the 34 s decompression);
    - the Launcher3 Escape crash (AOSP patch);
    - `aosp-patches.sh` now resets other branches' leftover patches in the shared tree;
    - builds and the image snapshot both hold the AOSP lane lock. `aosp-docker.sh` takes it and keeps it until the build's container exits, and `aosp-build.sh` refuses unless its own container holds it. The snapshot waits for the lock. This follows two Checker findings: the snapshot only checked container names once, and a build could start while someone else held the lock;
    - the `df /data` parsing in `live-report.py` and `live-qemu-check.py`.
- **Evidence:** `evidence/2026-10-17-g14-desktop/g14-desktop3/` (the G14 boots) and `desktop4/` (build, 37/39 in QEMU, first boot 17.8 s vs 27.9 s with SurfaceFlinger at 5.4 s vs 19.9 s). The save-logs helper now reports the earlier-boots archive honestly (`prior-boots.txt`, pipeline status).
- **Found:** drm_hwcomposer proposes more planes than amdgpu's display core takes per stream (4), so its test commit fails every frame and SurfaceFlinger composes on the GPU (open, `docs/g14-desktop.md` §7).
- **Next:** the owner boots the default entry on the `desktop3` stick as it is (first-boot setup is done), then `desktop4`.

### 2026-10-17: G14 boots of desktop2: why only "save logs" worked (ANAL-176)

- **Done:**
  - **Every enforcing boot was black because amdgpu could not load its firmware** (`firmware_load` denied on `/vendor/firmware`); this is now fixed in policy.
  - Also fixed:
    - a race that could start SurfaceFlinger before the GPU HALs were chosen;
    - the 1-minute screen-off;
    - shared-tree builds keeping stale outputs.
  - Every boot now keeps its logs, so a later "save logs" boot brings them back.
- **Evidence:** the owner's runs and the device's own screenshot of the desktop are in `evidence/2026-10-17-g14-desktop/g14-desktop2/`. The image `openbook-live-20261017-desktop3` passes 37/39 in QEMU.
- **Handed on:** the Bluetooth crash loop (ANAL-179), the missing `system` DMA-BUF heap (kernel lane), and touchpad clock warnings (ANAL-178).
- **Next:** the owner boots `desktop3`'s default entry.

### 2026-10-17: G14 desktop from USB, RADV swapchain fix and SELinux (ANAL-176)

**Done**
- **The G14's black screen, root-caused and reproduced off the laptop:** RADV 26.2.5 dereferences a null memory object when Android 17 binds a deferred swapchain image (every ANGLE window). The image's own RADV crashes the same way on the build host's Radeon 610M.
- **Fixed in Mesa:** three upstream RADV commits backported, plus an OpenBook patch so minigbm's modifier-less buffers use radeonsi's real tiling. 8 of 8 swapchain cases pass with 0 wrong pixels (`amd-android-hwtest.sh swapchain`).
- **SELinux:** on top of PR #38, `vendor.mesa.*`, the GPU's `drm` directory, the composer's backlight and the disk queues. 24 of 24 G14 sysfs paths labelled as intended (`sepolicy-label-check.py`); live-001's 66 kernel-log denials are covered except 3 AOSP or kernel-side ones.
- **Live image `openbook-live-20261017-desktop2`** with "safe graphics" entries (Mesa GL instead of ANGLE).

**Next:** the owner boots it on the G14 (`docs/g14-desktop.md` §6).

### 2026-10-16: Bare metal, the OpenBook G14 product (ANAL-199)

**Done**
- `anybook_g14_x86_64-cp2a-userdebug`: a generic PC layer (`device/anybook/common/pc`) plus a G14 layer (`device/anybook/g14`). It brings ANAL-198's kernel, dlkm images and firmware, ANAL-174's AMD graphics, base HALs with real sysfs backends (lights, EPP power, S0i3 power stats, thermal, Type-C, health), software KeyMint, Gatekeeper and Weaver (no attestation), and the N-KEY and ELAN input files. One vbmeta, orange AVB.
- `scripts/g14-image.sh` writes a 12 GiB USB GPT image with systemd-boot; `scripts/g14-qemu.sh` boots it from USB in QEMU/OVMF.

**Evidence:** `evidence/2026-10-16-g14-product/`
- `sys.boot_completed=1` at 29.9 s on the first boot and at 11.7 s on the second boot from the same disk. A PIN set on boot 1 still verifies on boot 2. SELinux enforcing.
- HAL host test 15/15; the dGPU hook's fixtures 14/14 on the host and inside QEMU.

**Found:** five hardware-independent blockers, all fixed: no `mount_all`, two missing service labels (Gatekeeper's shared secret, the minigbm mapper), the allocator's metadata memfds (including MLS for apps), and an audio policy without the modules the audio HAL declares. Also: AMD laptops get no TPM hwrng (`tpm_crb` quirk, also in the G14's own dmesg); `prng_seeder` gives up without blocking anyone.

**Next:** ANAL-190 rebuilds the live stick from this product; the owner boots it on the G14 (ANAL-176). Details: `docs/g14-product.md`.

### 2026-10-16: M8, live USB image (ANAL-190)
- `scripts/installer-image.sh` builds the approved raw GPT live image from ANAL-199's G14 product: systemd-boot, slot A only, `super` re-packed from 8 GiB to 1.23 GiB, firmware licences from the vendor image. Output: 2.68 GiB image, 0.9 GB `.xz`, built in 41 s, byte-identical across rebuilds.
- `openbook-live-init` (rdinit) grows `userdata` to fill the stick and moves the backup GPT on first boot, erases the live data on "start fresh", and on "save logs" writes dmesg, logcat, system facts, a screenshot and `summary.json` to the stick.
- QEMU/OVMF matrix and owner checklist: `docs/installer.md` §11. Evidence: `evidence/2026-10-16-installer/live/`.
- **Desktop not reached in QEMU** (product, ANAL-199): `system_server` is killed by its watchdog while it waits for the audio HAL.
- **First live boot on the G14:**
  - Working: USB boot, the 56 GiB live `/data` on the stick, amdgpu on the panel, SurfaceFlinger with a touchpad-driven pointer, keyboard, and the dGPU in D3cold.
  - Black screen because the boot animation crashes in RADV (`AcquireNextImageKHR`), and the framework loops on audio.
  - Evidence: `evidence/2026-10-16-installer/g14-live/`.
- **Rebuilt after ANAL-199's audio fix** (`openbook-live-20261016b`): Android finishes booting from the stick in QEMU, at 23 s with Launcher3. The G14 still needs the RADV fix: `radv_BindImageMemory2` dereferences a null memory object on Android's deferred swapchain path (`docs/installer.md` §11.11).

### 2026-10-16: Kernel, bare-metal packaging for the G14 (ANAL-198)

**Done**
- `scripts/kernel-g14-package.sh` (resumable) builds `vendor_boot`, `vendor_dlkm` and `system_dlkm` with Kleaf from the ANAL-171 tree, checks them, stages the firmware and runs a QEMU first-stage check.
- **Bare metal needs no first-stage module.** NVMe, xHCI, usb-storage, uas, dm and the filesystems are built into the GKI.
- **amdgpu loads in second stage.** The GKI has no efifb or simpledrm, and Googlebook keeps xe out of first stage too.
- The module plan with per-module rationale is `kernel/devices/anybook/g14/modules.tsv`.

**Evidence:** `evidence/2026-10-16-kernel-g14/`
- 5/5 QEMU runs pass: Android 17's first-stage init mounts `super` with AVB and dm-verity from usb-storage, usb-uas and NVMe. With an NVMe and a USB disk carrying the same partition names, `boot_part_uuid` picks the right one.
- `vendor_dlkm` loads with 0 symbol, CRC or signature errors; `asus-nb-wmi` returns -ENODEV in QEMU, as expected.
- `system_dlkm` is signed by the key built into our `vmlinux`.
- 137 firmware files are staged with a licence manifest. The CS35L56 `10431024` tuning is present, as WHENCE links.

**Found:** three Kleaf issues, all worked around:
- the flattened `vendor_dlkm` duplicates the GKI modules and drops the blocklist;
- its `vendor_kernel_modules` label has no `module_load` rule in AOSP;
- `kernel_vendor_cmdline` loses everything after its first space.

**Next:** ANAL-199 consumes the images (`docs/kernel.md`, "Hand-off to ANAL-199"); ANAL-176 boots them on the laptop.

### 2026-10-15: M0 (research, dev host, baselines)

**Done**
- Researched Googlebook OS and prior art. Findings are in `docs/RESEARCH.md`, and the two-track plan with ranked blockers is in `docs/PLAN.md`.
- Downloaded Google's official recovery image for ruby (Lenovo Googlebook 15, Intel), build `16452207_CL3B.260622.271.R1`. The zip md5 `0567fe2ed0dd1c1753b383a6b3dbfe81` matches Google's manifest. The image is stored locally and never committed.
- Unpacked it without root: GPT, `super`, EROFS partitions, boot/init_boot/vendor_boot, ramdisks, and the kernel config.
- ISA scan: of 2,675 x86-64 ELF files, 79 contain instructions Zen 4 doesn't implement. 65 of those use AVX-VNNI, including `init`, `linker64`, `surfaceflinger` and `libhwui`.
- **Execution test:** booted Google's stock kernel and ramdisks in QEMU/KVM with `-cpu host` on a Ryzen 9 7950X (Zen 4):
  - First-stage mount works: dm-linear `super`, dm-verity using Google's hashtree, AVB in orange state.
  - Second-stage init starts about 30 services.
  - **0 SIGILL or invalid-opcode traps.**
  - Boot stalls at `keystore2` because KeyMint lives in the Trusty pKVM security VM and there is no GSC TPM. Zygote and the UI never start.
- Booted Google's AOSP Desktop (Preview) Android 17 emulator image headless under KVM:
  - `boot_completed` after 16 s.
  - The desktop taskbar is up and Settings and Files open in freeform windows.
  - `feature:android.hardware.type.pc` is present, and the native bridge is libndk_translation with `arm64-v8a` listed.

**Evidence** (in `evidence/2026-10-15-m0/`)
- `m0-emulator/screen-desktop.png`, `m0-emulator/screen-windows.png`, `props.txt`, `boot-result.txt`, `logcat.txt.gz`, `dmesg.txt.gz`
- `gbos-boot-zen4-kvm.log`: full serial log of the Googlebook kernel and init on Zen 4
- `isa-scan-ruby.json`: per-binary counts of instructions Zen 4 doesn't implement
- `gbos-kernel-config.txt`: the stock Googlebook GKI config

### 2026-10-15: Kernel, stock android17-6.18 GKI reproduced with Kleaf (ANAL-170)

**Done**
- Googlebook OS ships the unmodified public GKI: the ruby `boot_a` kernel is byte-identical to ci.android.com build 16302624 (`kernel_x86_64`, branch `common-android17-6.18-2026-06`, `common` 3938c8d97142).
- Built it locally from that build's pinned manifest (`manifests/kernel/gbos-16302624.xml`) in 5 min 37 s. The `.config` and KMI CRCs are identical. Built with the same build number, `vmlinux` differs only in the per-build module-signing certificate and build ID (1,098 bytes).
- Config diff: 0 symbols. Google adds nothing beyond `gki_defconfig`. `PKVM_INTEL` is explicit in `gki_defconfig`; `X86_FRED` is selected by `KVM_INTEL` through an upstream Kconfig `select`.
- Our kernel boots on Zen 4 under KVM to the same `keystore2` stall as the stock kernel. Google's signed GKI modules (`rust_binder`, `zsmalloc`) are rejected, so `system_dlkm` must come from our build.
- The `android17-6.18` tip (6.18.32) also builds. The shipped KMI list is unchanged there.

**Evidence:** `evidence/2026-10-15-kernel/`. Details are in `docs/kernel.md`.

**Next:** an AMD defconfig fragment and an `anybook_amd` KMI symbol list on this tree, then boot with our `system_dlkm`.

### 2026-10-15: Graphics userspace, Mesa radeonsi + RADV for Android x86_64 (ANAL-173)

**Done**
- Built upstream Mesa 26.2.5 and Android-Generic `26.0/main` (26.0.8 + 63 commits), out-of-tree with NDK r30 at API 37 (`tools/Dockerfile.mesa-android`, `scripts/mesa-android-build.sh`). radeonsi uses ACO only, so no Android LLVM is needed. libelf comes from AOSP elfutils.
- Both trees: 0 unresolved NEEDED entries or symbols against the API 37 sysroot. `vulkan.radv.so` exports only `HMI`. Baseline ISA is x86-64 with SSE4.2; wider code is only behind runtime checks.
- Load test on the Android 17 emulator: the Vulkan HAL opens and `vkCreateInstance` succeeds with 0 devices (there's no GPU in the VM). EGL loads; `eglInitialize` fails because there's no DRM device. **Nothing has run on AMD hardware yet.**
- A clean rebuild is bit-identical. Details are in `docs/mesa.md`.

**Evidence:** `evidence/2026-10-15-mesa/`

**Blocked / needs a decision:** the static libelf is LGPL-3.0-or-later inside the MIT Mesa libraries. That's fine for local builds; binary redistribution needs a decision (`docs/mesa.md`).

**Next:** minigbm with an amdgpu/gbm_mesa backend so Mesa's `cros` gralloc path works, then SP-HAL SELinux labels, then a hardware run (M4).

### 2026-10-16: M1b prep, AOSP 17 build environment (ANAL-167, Track A)

**Done**
- `tools/Dockerfile.aosp`: Ubuntu 24.04, running as the host uid/gid.
- Synced `android-latest-release` (manifest `ad156f32`, `android17-release`) to `~/anybook/aosp`:
  - A full-history mirror of the 975 source projects: 102 GB, 32 min.
  - A build tree with shallow prebuilts: 128 GB, 15 min.
  - A full mirror of this manifest would be 748 GB, 87% of it prebuilt history (measured).
- ccache is set to 100 GB through `CC_WRAPPER`.
- `lunch aosp_cf_x86_64_pc-trunk_staging-userdebug` and `m nothing` succeed with the Soong nsjail sandbox enabled: 1:20 wall clock, 39 GiB peak RSS.

**Evidence:** `evidence/2026-10-15-aosp/` (sync logs, pinned manifest, `repo info`, lunch, `m nothing` logs and timings, sizes).

**Findings**
- `trunk_staging` on `android17-release` builds as `PLATFORM_VERSION=Baklava`. `cp2a` gives `PLATFORM_VERSION=17` (`REL`), so M1b should build `aosp_cf_x86_64_pc-cp2a-userdebug`.
- Upstream `external/curl` has its `android17-security-release` branch pointing at a tag object, which breaks all-heads mirrors.

**Next:** ANAL-168 full build of `aosp_cf_x86_64_pc-cp2a-userdebug`, measuring ccache hits, then boot it in Cuttlefish.

### 2026-10-15: ARM compat harness and libndk_translation baseline (ANAL-180)

**Done**
- `scripts/compat/`: probe APKs (arm64-only, armv7-only, x86_64 control) with 19 test groups, a pinned F-Droid corpus (16 arm64-only apps plus 7 x86_64 controls), a resumable matrix runner and a CoreMark benchmark.
- **Apps:** 13 of 16 arm64-only F-Droid apps run under libndk_translation. Tor VPN (SIGILL on `mrs ID_AA64ISAR0_EL1`) and Element X fail only under translation; AAAAXY also fails natively.
- **No arm32:** armeabi-v7a does not install (the image is 64-bit only).
- **Speed:** translated arm64 runs at 0.457× native x86_64 (CoreMark, same emulator).
- **Probe findings:** seq_cst store→load ordering is broken (about 1% of store-buffering trials), NaN rules follow x86, `CNTVCT_EL0` runs about 429× fast, and `MRS` of ID registers is not emulated.

**Evidence:** `evidence/2026-10-15-compat/` (2 runs with identical outcomes, screenshots, logs, `bench/`, `analysis/`).

**Next:** the same corpus under houdini (after M1a) and Digitalis/Berberis (after M1b); root-cause Element X.

### 2026-10-16: M1b, our AOSP 17 build boots in Cuttlefish (ANAL-168, Track A)

**Done**
- Built `aosp_cf_x86_64_pc-cp2a-userdebug` with `scripts/aosp-build.sh`: 2 h 10 min cold at `-j32` on the shared host. Peak container RAM was 41 GiB, plus 18.5 GiB of swap. `out/` is 137 GB (165 GB after `m dist`), and ccache got 25% hits even though the cache started empty.
- Booted it with `scripts/cf-boot.sh` in Google's Cuttlefish container (no sudo, no `--privileged`). `sys.boot_completed=1` came 17–29 s after `cvd create`. The display is up at 1920×1080 showing Launcher3, and `adb` captures work. The boot also works with our build's own host tools (`CF_HOST_TOOLS=build`).
- Device: Android 17, SDK 37, `CP2A.260605.016`. `feature:android.hardware.type.pc` and freeform window management are present. The kernel is Google's prebuilt android16-6.12 GKI.

**Evidence:** `evidence/2026-10-16-aosp/`. Details are in `docs/aosp-build.md` (M1b).

**Findings**
- Cuttlefish in Docker needs three things the recipe left out: `seccomp=unconfined` (Docker's default profile blocks `AF_VSOCK`), a writable host path, and a writable product path. cvd 1.57 also swaps in all of its packaged host tools, because AOSP's host package ships `debian_substitution_marker`.
- The build advertises `arm64-v8a` in its abilist but ships no native bridge. An arm64-only APK installs, then fails `dlopen` with `EM_AARCH64`.

**Next:** ANAL-169, graphics and desktop windowing on this image. In ANAL-181, a translator for the advertised `arm64-v8a`.

### 2026-10-16: Kernel, AMD config and vendor modules (ANAL-171)

**Done**
- OpenBook GKI: the shipped `android17-6.18` tree plus 3 patches (`kernel/patches/common/`). Release `6.18.21-android17-5-g44a90255c95f`.
  - Three bool built-ins: `AMD_IOMMU`, `PINCTRL_AMD`, `X86_AMD_PLATFORM_DEVICE`.
  - An `anybook_amd` KMI list with 1,887 symbols, 214 of them new. amdgpu alone needs 129 symbols the stock GKI does not export.
- Kleaf mixed build `//devices/anybook` (`kernel/devices/anybook/`) produces 138 vendor modules: amdgpu with DC, amdxdna, amd-pmc, pinctrl-amd (built in), i2c-designware/i2c-hid-acpi, HDA ALC269/CS35L56, ACP/SOF-AMD, mt7921e/mt7925e, rtw89, btusb-MTK, asus-wmi, hid-asus, virtio-gpu and more.
- linux-firmware subset list: 131 files, 52.5 MB, all redistributable, with each file's licence taken from WHENCE.

**Evidence:** `evidence/2026-10-16-kernel-amd/`
- All 138 modules have vermagic, CRCs and imports matching the kernel.
- In a QEMU/KVM load test, 137 modules load and 1 returns -ENODEV (no ASUS WMI in the VM), with 0 symbol errors. AMD-Vi interrupt remapping is on, and virtio-gpu creates `card0`.
- Every stock KMI CRC is unchanged.
- The equivalence build shows 5 harmless vmlinux differences.

**Blocked:** amd-pmf. `ccp.ko` links SEV code that calls `kernel_read`/`kernel_write`, both on GKI's deny list. Owner decision needed; see `docs/kernel.md`.

**Next:** ANAL-172 packages `vendor_dlkm`/`vendor_boot` and does a boot test; then the `android17-6.18` tip build.

**Update (same day):** the inventory showed a GA403WR with codec SSID 1043:1024. The mainline quirk for it is backported, and the card reader and NVIDIA-WMI-EC backlight modules are added (see `docs/kernel.md`).

### 2026-10-16: Kernel, OpenBook kernel boots our AOSP 17 userspace in Cuttlefish (ANAL-172)

**Done**
- `scripts/kernel-cf-boot.sh` boots the ANAL-171 kernel and its own signed `system_dlkm` under ANAL-168's `aosp_cf_x86_64_pc` images, through cvd's `--kernel_path`/`--initramfs_path`. Android is not rebuilt.
- `scripts/kernel-cf-modset.py` merges the GKI, the 138 OpenBook modules and the Cuttlefish board modules (built from `common-modules/virtual-device` on our GKI), and checks every cross-module CRC.

**Evidence:** `evidence/2026-10-16-kernel-cf/`
- `sys.boot_completed=1` 30–33 s after `cvd create` (twice), `uname -r` = `6.18.21-android17-5-g44a90255c95f`.
- 169/169 expected modules are live, including 137 of the 138 OpenBook modules, amdgpu among them. There are 0 symbol, CRC or signature errors.
- virtio-gpu drives a 1920×1080 display. dmesg and logcat are included.

**Not loaded**
- `asus-nb-wmi`: -ENODEV, because the VM has no ASUS WMI. It is blocklisted in the VM image.
- 9 Cuttlefish virtual Wi-Fi and mt76 USB modules: CRC-incompatible with OpenBook's cfg80211/mac80211/mt76, because Cuttlefish sets `NL80211_TESTMODE`. The VM therefore has no virtual Wi-Fi.
- amd-pstate does not register: crosvm's ACPI has no `_CPC`.

**Next:** VM Wi-Fi modules built against the OpenBook config; real probing on the G14 (bare-metal epic).

### 2026-10-16: ARM compat, Digitalis evaluation (ANAL-181)

**Done**
- Built Digitalis from source:
  - Translator `b6b7fc30` on AOSP `android16-qpr2-release`, manifest `3969040d`.
  - The 70 bridge modules in 44 min; the full reference image in 82 min.
- Installed it as the native bridge of the AOSP Desktop 37.0 emulator, on its own AVD, and ran the ANAL-180 corpus, probes and CoreMark. Two wiped runs gave identical outcomes.
- Ran Digitalis's own AOSP 16 image as a control. It gave the same results.
- **Apps:** 12 of 16 arm64-only apps alive, against 13 for libndk_translation. Digitalis loses Fennec to a deterministic translation SIGSEGV at `libxul.so+0x2b32da0`. Tor VPN (`MRS ID_AA64ISAR0_EL1`) and Element X fail under both bridges.
- **Probes:** Digitalis fixes seq_cst ordering, `CNTVCT` rate, `uname` and FMAX NaN. It adds an `FRECPE` failure.
- **Speed:** CoreMark 0.30× native, against 0.45× for libndk_translation the same day, so about 34% slower.
- **License audit:** Apache-2.0, built from source, no Digitalis prebuilts in the image. The sample-app repo carries a proprietary SDK binary and must stay out of Track A.
- **Recommendation: GO for Track A**, with conditions:
  - port it to Android 17 (its guest NDK is A16: 43 `libandroid` exports missing);
  - fix the Fennec crash, `MRS ID_AA64ISAR0_EL1` and `FRECPE`;
  - accept or close the speed gap.

  Details are in `docs/digitalis.md`.

**Evidence:** `evidence/2026-10-16-digitalis/` (run1, run2, a16-control, bench, bench-ndk, analysis, bundle checksums, pinned manifest).

**Blocked / needs a decision**
- The owner's OK to report the findings upstream to DigitalisX64. That is an outward-facing action.

**Next:** port Digitalis to `android17-release` and build it in the Track A tree (after ANAL-168), boot it in Cuttlefish, and re-run the matrix.

### 2026-10-16: M2 (Track A), desktop windowing and VM graphics on our AOSP 17 build (ANAL-169)

**Done**
- New product `anybook_cf_x86_64_pc-cp2a-userdebug` = `aosp_cf_x86_64_pc` plus a reusable desktop configuration (`device/anybook/common/desktop`). It contains:
  - framework and SystemUI RROs with the desktop values from Google's AOSP Desktop emulator image
  - `PRODUCT_CHARACTERISTICS := desktop` and `large_screen_common.mk`
  - an aconfig value set with the 79 flags that image enables and cp2a leaves off
- It boots in Cuttlefish straight to the Android desktop: apps open as freeform windows in a `Desk`, the desktop taskbar is pinned, and the status bar is the desktop one.
- The reference image and our build were captured with the same script and diffed. 0 desktop flags and 0 `persist.wm.*` or characteristics props differ.
- GPU: `gfxstream_guest_angle` on the host's **Radeon 610M** (Mesa RADV, no root) renders SurfaceFlinger and HWUI with 0% janky frames, against 10–31% for the old `guest_swiftshader` default. `gfxstream` on the 610M and both modes on the RTX 4090 also work. `drm_virgl` crashes crosvm in both the Debian and AOSP builds.
- With the VM-only force property off, a touchpad plus a keyboard still put the display in desktop-first mode. That is the path real laptops take.

**Evidence:** `evidence/2026-10-16-desktop/`. Details are in `docs/aosp-desktop.md`.

**Blocked:** nothing.

**Next:**
- ANAL-174 (AMD graphics in the device tree) can build on `anybook_cf_x86_64_pc`, inheriting `device/anybook/common/desktop/desktop.mk`.
- ANAL-181: the native bridge.
- Cuttlefish Wi-Fi is off (`wifi_on=0`).

### 2026-10-16: NVIDIA dGPU research and dGPU-off default for first boot (ANAL-187)

**Done**
- **Recommendation** (`docs/nvidia.md`):
  - No-go for using the dGPU in M3–M8.
  - Conditional go for research milestones N1–N6 after M4. The target is per-app offload through Android's updatable-driver switch, with NVK on the dGPU and amdgpu scanout.
- **The laptop is a GA403WR, so the GPU is an RTX 5070 Ti Laptop (GB205)**, not the GB206 in the issue title. nouveau treats both the same.
- **Kernel:**
  - nouveau has supported GB20x (GSP-RM 570.144) since 6.16, and that support is in our 6.18 tree.
  - Runtime PM on r570 is still being fixed upstream (7.3-rc4 to rc7). Our 6.18 tree carries a backport that upstream reverted.
  - The only RTX 5070 Laptop report shows about 5–10% of proprietary performance.
  - Nova has no display or render support yet.
- **Userspace:**
  - NVK is Vulkan 1.4 conformant on desktop Blackwell, but **it has no AHardwareBuffer support**, which CDD 7.1.4.2 [C-3-1] requires. ANGLE therefore cannot offer the required EGL extension on it.
  - Android loads one Vulkan driver per process; minigbm and EGL each use one GPU.
- **GSP firmware licence:** redistributable in OpenBook images under `LICENCE.nvidia` §2.1.2: unmodified, with the licence text shipped next to it.
- **First boot:** with `dgpu_disable=0` the dGPU will most likely sit in D0 under OpenBook:
  - nothing binds it;
  - the PCI core keeps unbound devices in D0;
  - `snd_hda_intel` holds its HDMI-audio function awake, because `VGA_SWITCHEROO` is off and power_save is 0.

  The inventory's missing dGPU is consistent with supergfxd removing it through sysfs, which Omarchy's setup does. That removal does not survive a reboot. **Default for ANAL-176:** `dgpu_disable=1`, set from Linux with the owner's confirmation; HDMI, which is on the dGPU, is lost while it is set. An OpenBook runtime-PM hook comes later as a fallback.
- **Test:** `scripts/dgpu-power-check.sh` is read-only by default and emits JSON. It runs under bash and Android's mksh. Fixture tests pass 9/9 in both shells, and shellcheck is clean.

**Evidence:** `evidence/2026-10-16-nvidia/`:
- source excerpts from our kernel, Mesa 26.2.5, AOSP 17 (ANGLE, libvulkan, EGL, minigbm, drm_hwcomposer), linux-firmware and Omarchy;
- fixture results;
- a dev-host run.

**Blocked:** nothing. The owner's go-ahead is needed before anyone sets `dgpu_disable=1` on the G14.

**Next:**
- The device agent (ANAL-195/196) runs `dgpu-power-check.sh --sample 120` on the G14's Linux.
- The owner decides on `dgpu_disable=1`.
- ANAL-176 runs the same check in the first OpenBook boot.

### 2026-10-16: M8 design, USB image, boot chain, install flow and wizard (ANAL-189)

**Done**
- `docs/installer.md`: the recommendation for owner sign-off.
  - A raw GPT `.img`, with no ISO.
  - systemd-boot type #1 entries, with GRUB as the tested fallback and GBL later.
  - Whole-disk and alongside layouts.
  - An Android (Compose) wizard on a scriptable install engine.
  - Safety rules S1–S13 and a licensing checklist.
  - A high-fidelity design (Material 3 Expressive, light and dark) in `docs/installer-design/`.
- `scripts/installer/` with `tools/Dockerfile.installer`:
  - Builds GPT "USB stick" images from our AOSP 17 images and the OpenBook GKI.
  - Boots them in QEMU/OVMF as USB storage, next to a decoy NVMe disk that has the same partition names.
  - A probe `rdinit` records the cmdline and bootconfig the loader passed, then continues into Android.

**Evidence:** `evidence/2026-10-16-installer/`
- GRUB 2.16 and systemd-boot 262 reach the Android console from USB with `boot_part_uuid`.
  - by-name links point at the stick, not the NVMe disk.
  - `/metadata` and `/data` are formatted on first boot and kept on the second.
  - A wrong vbmeta digest is detected and tolerated in orange.
  - systemd-boot boot counting works.
- A UKI loses Android's bootconfig: systemd-stub appends its own cpio archives after `.initrd`.
- GBL dev (`gbl-mainline:6296919847ee`):
  - It boots to the console only when `boot_part_uuid` is baked into `vendor_boot`.
  - It always uses slot `a`.
  - It panics with `NotUnique` when a second disk has the same partition names (upstream CLs 4051936 and 4286120 are open).

**Blocked / needs a decision:** owner sign-off before ANAL-190. Also adding `CONFIG_EFIVAR_FS` to our GKI, AVB release-key custody, and naming.

**Next:** ANAL-190, a live USB image from ANAL-174's product with systemd-boot.

### 2026-10-16: Graphics, AMD stack in the OpenBook device tree (ANAL-174)

**Done**
- `device/anybook/common/graphics-amd/` adds Mesa 26.2.5 radeonsi/RADV (ACO, no LLVM, GBM, shared libelf), minigbm with an amdgpu backend, drm_hwcomposer, ANGLE, props, SELinux and an init `.rc`. `anybook_cf_x86_64_pc` inherits it, and the G14 product will too.
- **HAL selection happens at boot.** `anybook_gpu_probe` reads the DRM drivers and PCI IDs at early-init, and on AMD switches to `ro.hardware.vulkan=radv`, `egl=angle`, `gralloc=minigbm`, `hwcomposer=drm`. minigbm picks its backend by DRM driver name, `amdgpu` or `virtio_gpu`.
- **minigbm patch** (`aosp/patches/external/minigbm`): ChromeOS's `amdgpu.c` needs a DRI entry point that Mesa ≥ 24.3 no longer exports. A new `dri_gbm.c` uses Mesa's GBM instead, and buffers are linear-only without it.
- **Mesa** is staged as vendor prebuilts from the pinned NDK build (`scripts/graphics-amd-stage-mesa.sh`). AOSP's `external/mesa3d` only builds gfxstream and lavapipe.

**Evidence:** `evidence/2026-10-16-graphics-amd/`
- The image builds in 3 min incrementally, with sepolicy and VINTF checks passing.
- **No VM regression** on `gfxstream_guest_angle`:
  - boot in +16–18 s (ANAL-169: +17 s)
  - the same desktop and the same SurfaceFlinger renderer (ANGLE → gfxstream → RADV on the 610M)
  - 0 % janky frames at 5 ms
  - no new AVC denials
  - the probe reports `hal=virtio`
- **The image's AMD drivers on real AMD silicon** (the build host's Radeon 610M, in a container with the image's bionic and no framework):
  - a RADV device runs a GPU fill with 0 errors
  - radeonsi GLES 3.2 renders
  - minigbm chooses `amdgpu`, and tiled and linear buffers round-trip
- In the VM, RADV's `vkCreateInstance` succeeds with 0 devices.
- The probe passes its unit tests and picks `amdgpu` on the G14 inventory and on the host's real sysfs.

**Findings**
- With Mesa's default `android-strict`, RADV reports **Vulkan 1.1** on Android. `ANDROID_STRICT=false` gives 1.4; decide with CTS in ANAL-177.
- `PRODUCT_DEVICE` is now `anybook_vsoc_x86_64`, because vendor sepolicy needs a board. Boot with `CF_DEVICE=anybook_vsoc_x86_64`.

**Next:** ANAL-199, the G14 product with the platform HALs on. Then ANAL-176 and ANAL-177 on the Radeon 890M. Details are in `docs/graphics-amd.md`.

### 2026-10-16: First OpenBook boot on the G14, hardware check (ANAL-189)

**Done**
- The owner booted the hardware-check stick on the GA403WR.
- UEFI → systemd-boot → our GKI from USB. 235 modules loaded, 0 failed.
- These came up: amdgpu (SMU, DCN 3.5, DMUB, eDP with PSR, backlight), mt7925e + `wlan0`, Bluetooth `hci0`, the ELAN touchpad, the keyboard, the lid switch, the NPU (`accel0`), the battery, UCSI and USB4.
- The stick also booted the Android preview: first and second stage ran from USB on the laptop.

**Evidence:** `evidence/2026-10-16-g14-hwcheck/` (report, full kernel log, analysis).

**Findings**
- `regulatory.db` is missing from the firmware list.
- The dGPU is on the bus with its HDMI-audio function bound (`dgpu_disable=1` was not set yet).
- The backup GPT is not at the end of a stick larger than the image.

**Next**
- A v2 check (power and display facts, JSON verdicts, `regulatory.db`, an opt-in s2idle sleep test) is ready as an in-place stick update (`scripts/installer/update-hwcheck-stick.sh`).
- The owner reruns it. The results feed ANAL-176/178/179.

### 2026-10-16: G14 hardware check runs 2 and 3: power and sleep (ANAL-189)
- amd-pstate-epp is active.
- **An s2idle suspend/resume cycle works, but S0ix residency is 0.** The driverless dGPU stays D0/active (the `docs/nvidia.md` §1 prediction, now measured).
- Battery health is 88.7 %, and `regulatory.db` now loads.
- **Next:** v3 check stick, with a sleep test after powering the dGPU down for one boot (unbind, remove, root-port runtime PM), which tests `docs/nvidia.md` option 2 on hardware.
- **Evidence:** `evidence/2026-10-16-g14-hwcheck/`.

### 2026-10-16: G14 run 4: dGPU detached, still no S0i3 (ANAL-189)
- Detaching the dGPU works (bridge to D3hot), but the SMU reports "Last S0i3 Status: Unknown/Fail", and the firmware re-enumerates the dGPU on resume.
- So the dGPU is not the only blocker.
- The eDP panel check is fixed (2880×1800).
- **Next:**
  - v4 stick with the kernel's sleep debugging;
  - a Linux baseline with AMD's `amd-s2idle test` on the same laptop.
- **Evidence:** `evidence/2026-10-16-g14-hwcheck/`.

### 2026-10-16: G14 run 5: dGPU bridge in D3cold, still no S0i3; one LPI constraint unmet (ANAL-189)
- With the kernel's sleep debugging on, the dGPU's bridge reaches D3cold, and the LPS0 entry/exit calls all succeed. The SMU still reports "Last S0i3 Status: Unknown/Fail".
- **Only one LPI constraint is unmet: `\_SB_.PCI0.GPP0.SWUS`** (min D3hot, current D0). HYPOTHESIS: this is the child of the empty hotplug port `00:01.1`, which nothing powers down; it is not the dGPU (`GPP9`, per a sibling model's ACPI dump).
- The dGPU returning on resume looks like the kernel powering the root port back up, not the firmware (corrects run 4).
- **Next:**
  - v5 stick (ACPI path per PCI device, ACPI power states and power resources around the sleep);
  - the `amd-s2idle` Linux baseline, still the decisive comparison.
- **Evidence:** `evidence/2026-10-16-g14-hwcheck/`.

### 2026-10-16: G14 run 6: the unmet constraint is an ACPI object the kernel powered up and never powered down (ANAL-189)
- `GPP0` = `00:01.1`, the empty hotplug port; the dGPU is `GPP9.PEGP` (`00:03.1`).
- `GPP0.SWUS` has no device, but stays D0 with `GPP0.SWUS.PWRS` on from boot to after resume. PCI setup powers a bridge's `_ADR` children up for the scan (`acpi_dev_power_up_children_with_adr()`), and nothing powers an unused one down again (6.18 source).
- **Next:** the v6 stick powers that object down before the sleep test, using a test-only module (QEMU-tested with a fixture that recreates the case).
  - If S0i3 is reached, the real fix belongs in the kernel lane: power down `_ADR` children that no device claimed after the bus scan, or a G14 quirk.
  - If not, the remaining suspects are the PSP without a driver (`65:00.2`) and the USB4 router.
- **Evidence:** `evidence/2026-10-16-g14-hwcheck/`.

### 2026-10-16: G14 run 7: GPP0.SWUS ruled out; S0i3 moves to ANAL-178 (ANAL-189)
- The v6 module powered `GPP0.SWUS` down on the laptop, and every LPI constraint was met. The dGPU was off too. S0i3 still failed, with the same SMU idle mask as runs 5 and 6.
- The OS-visible causes are exhausted: every managed PCI function is suspended, all LPI constraints are met, the LPS0 calls succeed, and the SMU gets the hint. What's left is below the OS (SMU/BIOS GA403WR.309), or a driver ACPI doesn't report: the PSP with no `ccp`/amd-pmf, or the USB4 router.
- **Deciding test (owner):** `amd-s2idle test` on the laptop's own Linux. If it reaches S0i3, diff its drivers against ours; if not, it's the BIOS.
- **Scope:** S0i3 affects standby battery drain only. It does not block live USB booting or installation. It continues in ANAL-178 with the hardware-check stick, the probe and the `acpi_d3cold` module.
- **Evidence:** `evidence/2026-10-16-g14-hwcheck/`.
