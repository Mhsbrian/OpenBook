# Status

## State of the union (2026-10-17, 20:35 UTC)

**Goal:** the Googlebook-style Android 17 desktop on the ASUS ROG Zephyrus G14 (GA403WR: Ryzen AI 9 HX 370, Radeon 890M), installed from a USB stick through a wizard and verified on the laptop. Repo: https://github.com/Mhsbrian/OpenBook.

**Repo hygiene:** PRs #1–#66 are merged and none are open. The 2026-10-17 cleanup left one remote branch, `main`; every other branch was merged or superseded. Two branches with commits never merged are kept as tags: `archive/anal-190-live-image-b` (superseded on `main`) and `archive/anal-178-stick-integration`.

### What works, and where it has been shown

| Area | In a VM (QEMU or Cuttlefish) | On the G14 | Evidence |
|---|---|---|---|
| Kernel (GKI android17-6.18 + 140 AMD modules) | Boots our Android 17. **Since #64:** the system DMA-BUF heap (`system_heap.ko`) and `efivarfs.ko`, GKI `.config` unchanged (26 more KMI symbols). On the G14 product the heap errors are gone (64 → 0) and a Vorbis ringtone decodes through Codec2, with the product's Codec2 AIDL and memfd fixes from the same PR; efivarfs mounts and reads the firmware's boot entries | **Yes:** 235 modules, 0 failed (the PR #26 kernel; the new one goes on the next stick) | `evidence/2026-10-16-g14-hwcheck/`, `evidence/2026-10-17-kernel-g14-r2/` |
| Live USB boot, desktop | 40/40 live checks | **The normal enforcing boot reaches the desktop:** 28 s (`anal178c`), 29 s (`anal176s`, `anal176t`). No app crashed; 0 dropped frames since PR #52 (151 before) in both later sessions; the stick is no longer offered for formatting; no lock-screen blackout. A GPU hang during the graphics check (MODE2 reset, VRAM lost) restarted the whole UI | `evidence/2026-10-17-g14-desktop/g14-anal178c/`, `g14-anal176s/`, `g14-anal176t/` |
| Graphics (RADV, radeonsi, ANGLE, minigbm, drm_hwcomposer) | Passing; dEQP pre-check on a Radeon 610M | **Desktop renders with 0 dropped frames**, composed on the GPU (overlay planes off since PR #52). **dEQP on the 890M** (`anal176t`, 14 min): Vulkan 1.4 45,220 pass / 5 fail, Vulkan 1.1 (shipped) 43,222 / 8 / 2 crash; GLES on ANGLE 13,099 / 0 and on radeonsi 13,621 / 0; EGL 847 / 0; ANGLE end2end 1,814 / 2. **Decided: ship Vulkan 1.4** (next image). Open: AHB rendering fails, and one GPU hang under 1.1 cost a full GPU reset and an Android UI restart (GC 11.5 has no per-queue reset with our firmware) | `evidence/2026-10-17-graphics-cts/g14-anal176t/` |
| Touchpad, keyboard | Yes | **Yes.** The touchpad's "Clock changed backwards" errors (every 40 ms of finger contact) are explained: the kernel autorepeats `BTN_TOOL_FINGER`. Fixed in Android (EventHub) and shown in QEMU with the laptop's own HID descriptor; on the laptop with the next stick | `evidence/2026-10-16-installer/g14-live/`, `evidence/2026-10-17-power-input/g14-sessions/` |
| Lid, power button, hotkeys, battery health | Yes | **Config in force, battery health works:** lid and power-button settings, hotkey layouts, the health HAL (charge counter, 88.7 % state of health, GOOD) and the power HAL's EPP changes, all on the laptop. **Closing the lid puts it to sleep and opening it wakes it** (`anal176t`) | `evidence/2026-10-17-power-input/g14-sessions/`, `g14-anal176t/` |
| Sleep | s2idle in a VM | **s2idle works, under Android too** (screen timeout → s2idle → key wake, display and Wi-Fi back); **deep sleep (S0i3) never reached.** The power check ruled out the driverless PSP; the SMU points at MPM or the USB4 router (unconfirmed) | `docs/power-input.md` §1.3, §7.6 |
| Wi-Fi, Bluetooth, audio | Yes (WPA2, iperf3, tone through ALSA and, with the HAL fix, through Android) | **Wi-Fi to the internet** (5 GHz, 160 MHz); **Bluetooth pairs**, A2DP with LDAC; **speakers and mic through ALSA** heard. Through Android the tone was broken (HAL fix in ANAL-179's PR, QEMU only). **Under enforcing (`anal176t`), Bluetooth audio connects without the Bluetooth app aborting**: A2DP Connected, the HAL's A2DP session and outputs open, 0 crashes, so #52's policy fix holds. Sound over Bluetooth and app (browser) sound are still unheard. The only playback tried, ringtone previews, **failed to decode** (`Failed to create audio/vorbis decoder`; missing system DMA-BUF heap suspected). Headphone jack and iperf3 not tested | `evidence/2026-10-17-g14-audio-net/`, `evidence/2026-10-17-g14-desktop/g14-anal176s/`, `g14-anal176t/` |
| ARM apps (Digitalis, built from source) | 14/16 ARM-only apps; works in enforcing | **The bridge self-check passes on Zen 5** (5/5 verdicts, both sessions). No arm64 app run yet: the ARM apps check is on ANAL-192's stick | `evidence/2026-10-17-digitalis-a17/`, `evidence/2026-10-17-digitalis-g14/` |
| Installer | **Wizard 25/25, engine 53/53, end to end 79/79** (SELinux enforcing): whole disk and **alongside a Windows-like disk** (Windows' partitions byte-identical and still booting; OpenBook boots from a firmware boot option); **power cuts at 6 points**, each leaving the old table, a blank disk or a complete install, and each restart completing; reinstall; the installed disk with and without the stick | Live USB boots; the wizard has not run yet | `evidence/2026-10-17-installer-wizard/`, `evidence/2026-10-17-installer-e2e/` |

**What is left on the G14:** S0i3 deep sleep (needs the laptop's own Linux comparison), audible Bluetooth and app audio, the Android audio path with the HAL fix, media decoding on the laptop (it failed on `anal176t`; fixed in QEMU by #64, on `anal198`), the ARM apps check, the installer dry run, and the second graphics run on Vulkan 1.4. All but S0i3 are on `anal198`'s checklist.

### Running now

- **ANAL-179** (system sounds: `audioserver` can't map SystemUI's SoundPool memory under MLS) and **ANAL-191** (an efivarfs SELinux label so the installer can write a `Boot####` entry) are fixing the two follow-ups ANAL-198 found. QEMU only; their fixes ride the stick after `anal198`.
- **ANAL-198 (kernel lane): #64 merged.** It adds the system DMA-BUF heap and fixes two product bugs behind it (Codec2 HAL selection, Codec2 memfds under SELinux), so media decodes in QEMU. It also ships `efivarfs` as a vendor module, with Google's GKI configuration unchanged. Writing variables still needs installer SELinux policy (ANAL-191).
- **The owner's stick is now `openbook-live-20261017-anal198`** (built on the owner's request after #64; `docs/installer.md` §13.11). It comes from `main` `2d90741` and has everything `anal192c` had, plus Vulkan 1.4 (#61), the #64 kernel and media fixes, and ANAL-177's graphics check (sha256 `3b405d08…`). In QEMU: live 40/40, wizard 25/25, installer end to end 78/78, all four add-ons, and the media check. It replaces `anal192c`. The checklist is `anal192c`'s three boots (§13.6) plus a fourth, the graphics check.
- **After that session:** results go to ANAL-176, ANAL-177, ANAL-178, ANAL-179, ANAL-191 and ANAL-200.
- **Merged today since 14:45:** #56 (ANAL-200, the bridge on Zen 5), #57 (ANAL-178, power and input on the G14, the touchpad fix), #58 (ANAL-179, audio, Wi-Fi and Bluetooth on the G14, the codec-paced audio HAL).

### Waiting on the owner

1. **Write `openbook-live-20261017-anal198` and run its checklist** (`docs/installer.md` §13.11): `anal192c`'s three boots (the default entry, "save logs", the ARM apps check) plus "OpenBook graphics check", then reply "stick attached" on ANAL-192. It replaces every earlier stick. A spare drive for the real install (§13.7) waits until you name one by `/dev/disk/by-id`.
   Reply "stick attached" on ANAL-192 only; the coordinator routes each issue to its part. Ringtone sound is expected to fail until ANAL-198's heap fix ships on the next stick, along with Vulkan 1.4 and ANAL-177's second graphics run.
   Optional and independent of the stick, for S0i3: on the laptop's own Linux run `sudo python3 scripts/power/linux-s2idle.py --amd-s2idle` (about 5 min; `docs/power-input.md` §7.6) and attach the tarball to ANAL-178.
2. **Decisions:** none blocks running work.
   - repo license (Apache-2.0 suggested);
   - upstream reports for the bridge (DigitalisX64; AOSP `Build.CPU_ABI`);
   - amd-pmf (`docs/kernel.md`);
   - Track B (`docs/PLAN.md` §6);
   - installing the Multica daemon on the G14 (ANAL-194).
   - Before any public image: AVB release-key custody, an "OpenBook" trademark check, and Mesa libelf (shipped as a shared library, as recommended).
3. **Already decided:** the dGPU stays off (`dgpu_disable=1`; HDMI is dark while it is set; NVIDIA work waits until after M4). The installer design follows our recommendation (owner on ANAL-189, 2026-10-16).

### Next step for each open issue

| Issue | State | Next step | Needs |
|---|---|---|---|
| ANAL-176 G14 desktop and stability | In review | **The enforcing default entry reaches the desktop on the G14** (`anal178c` 28 s, `anal176s` 29 s). On the G14, PR #52's fixes hold: no storage notice for the stick, no lock-screen blackout, 0 dropped frames (151 before). On `anal176t`, Bluetooth audio connects under enforcing with no abort (the #52 audio fix holds); denials are down to 4 known kinds. Open: ringtone/media decoding (`Failed to create audio/vorbis decoder`; DMA-BUF system heap suspected, reproduce in QEMU), and a GPU reset restarting the UI (`docs/g14-desktop.md` §7, §13). Next: audible Bluetooth, browser and ringtone sound on ANAL-192's stick | ANAL-192's stick |
| ANAL-177 graphics conformance | In review (PR #61, merged) | **dEQP on the G14's 890M:** Vulkan 1.4 45,220 pass / 5 fail against 1.1's 43,222 / 8 / 2 crash, so **1.4 ships** (Mesa's default build since #61). GLES on ANGLE and radeonsi 0 failures; EGL 847 / 0; ANGLE end2end 1,814 / 2. Found: rendering into Android hardware buffers fails, and one GPU hang under 1.1 reset the GPU and restarted the UI. Next: the second run on 1.4 with tuned lists | The next stick after `anal192c` |
| ANAL-178 input and power | In review (PR #57, merged) | Lid works; touchpad clock fixed (EventHub, QEMU); the power check ruled out the PSP. Next: S0i3 from the Linux comparison | The laptop's own Linux `linux-s2idle.py --amd-s2idle` run; on ANAL-192's stick: battery saver, touchpad use (`docs/power-input.md` §7.5, §7.6) |
| ANAL-179 Wi-Fi, Bluetooth, audio | In review (PR #58, merged) | On the G14: Wi-Fi to the internet, Bluetooth A2DP/LDAC, speakers and mic through ALSA. Android's audio path was broken; the codec-paced HAL fixes it in QEMU. Next: the G14 check | ANAL-192's stick: iperf3 server, Bluetooth audio, browser video, headphones |
| ANAL-200 ARM bridge | In review (PR #56, merged) | Done: bridge verdicts 5/5 on the G14 in both sessions, G14 rows recorded, and the ARM apps check add-on (probe and CoreMark on the laptop, QEMU-tested). Next: read its G14 results | The ARM-apps-check boot on ANAL-192's stick; the upstream-report OK |
| ANAL-191 installer wizard and engine | In review | The G14 dry run, on ANAL-192's stick. Open: `openbook-bootsync`, the text hardware report, a firmware boot entry (our GKI has no `EFIVAR_FS`: a kernel-lane decision) | — |
| ANAL-192 installer end-to-end tests and the owner's stick | In review | Done in QEMU: the integrated stick `anal192c` (live 40/40, wizard 25/25), the end-to-end matrix 79/79 (`scripts/installer/e2e-qemu.sh`), the user guide and release checklist draft (`docs/INSTALL.md`). Found: an installed OpenBook offers to format a plugged-in installer stick; the wizard calls an installed OpenBook "Linux". Open: the OTA slot switch (needs `openbook-bootsync`) | The owner's run of `docs/installer.md` §13.6; a spare drive named by `/dev/disk/by-id` for §13.7; the release decisions (`docs/INSTALL.md` §9) |
| ANAL-198 G14 kernel (follow-up) | In review (#64, #65 merged) | Done: `system_heap.ko` and `efivarfs.ko` as vendor modules with Google's GKI configuration unchanged; Codec2 fixes, so a ringtone decodes in QEMU; the owner's stick `anal198`. GPU reset: MES didn't answer and pipe reset is off in 6.18, so a hang means a full reset (`docs/kernel.md`). Next: the G14 check on `anal198` | The owner's `anal198` session |
| ANAL-193 to ANAL-197 device loop | Backlog | ANAL-194 first: the Multica runtime and test agent on the G14's Linux | Owner installs the daemon |
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
