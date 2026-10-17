# Status

## Now (2026-10-16, night)

The repo is **https://github.com/Mhsbrian/OpenBook**; the old AnyBook URL (`github.com/Mhsbrian/AnyBook`) redirects. PRs #1–#43 are merged (latest: #39 ANAL-176 RADV swapchain fix and SELinux labels; #43 ANAL-179 Wi-Fi, Bluetooth and audio for the G14). Open: #42 (ANAL-176 stability) and #41 (ANAL-178), both still being worked. #38 was closed as superseded, because #39 contains its commits. Every PR was checked before merging (script syntax, Python compile, no binaries or secrets, sizes, evidence backs the claim), and doc conflicts were resolved by hand.

**Decided by the owner**
- **Keep the dGPU disabled for now** (2026-10-16, on ANAL-187):
  - `dgpu_disable=1` is the bring-up default. ANAL-176 runs `scripts/dgpu-power-check.sh` read-only first, then sets the flag on the G14 from Linux before the first OpenBook boot. Commands and rollback are in `docs/nvidia.md` §1.
  - HDMI stays dark while the flag is set.
  - NVIDIA work beyond the research is parked; the N1–N6 track waits until after M4.

**Decisions needed from the owner** (no running work is blocked by these)
- **Repo license** for the scripts and docs. Apache-2.0 is suggested; the `device/anybook` files already carry SPDX Apache-2.0 headers.
- **Track B** (ANAL-165): whether to go past research with Google's proprietary image (`docs/PLAN.md` §6).
- **Mesa libelf licensing** (ANAL-173): libelf is LGPL-3.0+. Since ANAL-174, the image build ships it as a shared `libelf_mesa.so` (the recommended option), and `LIBELF=static` restores the static link (`docs/mesa.md`).
- **amd-pmf** (ANAL-171): it needs `ccp.ko` with SEV, which calls `kernel_read`/`kernel_write` from GKI's deny list. Options are in `docs/kernel.md`.
- **Digitalis upstream report** (ANAL-181/200): OK to report the Fennec, `MRS` and `FRECPE` findings to DigitalisX64? That is an outward-facing action.
- **Device-in-the-loop** (ANAL-194): install the Multica daemon on the G14's current Linux when ready (`docs/PLAN.md` §4a).
- **G14 hardware-check stick** (optional, owner): `scripts/installer/make-hwcheck-stick.sh` builds a USB image. It boots our kernel, drivers and firmware on the laptop, writes a report and the kernel log to the stick, and powers off without touching internal disks (`docs/installer.md` §2.7). Writing the stick needs you to name the exact USB device.
- **Live USB on the G14** (ANAL-190): the owner booted the live stick on the G14 (`evidence/2026-10-16-installer/g14-live/`). The rebuild on ANAL-199's audio fix (`openbook-live-20261016b`) boots to Launcher3 in QEMU and is ready to write (`docs/installer.md` §11.6, §11.11).

**Lanes on the dev host** (the 7950X has 61 GB RAM; an AOSP build peaks at about 41 GiB):
- **AOSP lane**, one builder at a time in `~/anybook/aosp/src`: ✓ ANAL-174 (PR #23), ✓ ANAL-199 (PR #35), ✓ ANAL-176 (PR #39; stability follow-ups in #42), ✓ ANAL-179 (PR #43, Wi-Fi/BT/audio). Now ▶ ANAL-176 follow-ups and ▶ ANAL-178's Android-side work share the lane under the lock. ANAL-178 starts in the kernel/hwcheck lane (S0i3, input); its Android-side work follows. ANAL-200 comes after that. Builds take `flock ~/anybook/aosp/.lane.lock`. The VM product's device is now `anybook_vsoc_x86_64`, so boot it with `CF_DEVICE=anybook_vsoc_x86_64`.
- **Kernel lane:** ✓ ANAL-198 (PR #26). The G14 images and firmware are ready for ANAL-199, and the lane is free.
- **Light lanes:** ✓ ANAL-189 (design and QEMU boot-chain prototype in PRs #22 and #25: high-fidelity wizard design, OpenBook naming, quiet boot, G14 hardware-check stick; awaiting sign-off) and ✓ ANAL-187 (research delivered; its dGPU-off default feeds ANAL-199 and ANAL-176).
- **Hand-offs:** condition wakeups on ANAL-159 promote each next step as soon as its dependencies reach review with a merged PR.

**Tracking** (Multica, children of ANAL-159). ✓ = delivered and PR merged, ▶ = running, ⏳ = starts automatically when its dependency delivers, ⏸ = parked.

| Epic | Stage 1 | Stage 2 | Stage 3 | Stage 4 |
|---|---|---|---|---|
| ANAL-160 Track A: AOSP 17 desktop boots in a VM | ✓ ANAL-167 build env (PR #5) | ✓ ANAL-168 `aosp_cf_x86_64_pc-cp2a` boots in Cuttlefish (PR #9) | ✓ ANAL-169 desktop windowing on the host GPU (PR #14) | — |
| ANAL-161 AMD GKI kernel (android17-6.18) | ✓ ANAL-170 stock GKI reproduced (PR #4) | ✓ ANAL-171 AMD config, 138 vendor modules (PR #8) | ✓ ANAL-172 our kernel boots our userspace (PR #12) | ✓ ANAL-198 bare-metal packaging: first-stage NVMe and USB boot, vendor_boot, dlkm images, firmware (PR #26) |
| ANAL-162 AMD graphics userspace | ✓ ANAL-173 Mesa radeonsi/RADV for Android (PR #3) | ✓ ANAL-174 AMD graphics in the tree, boot-time HAL selection (PR #23) | ⏸ ANAL-177 dEQP/CTS on the G14 | — |
| ANAL-164 ARM compat and native bridge | ✓ ANAL-180 harness and baseline (PR #6) | ✓ ANAL-181 Digitalis: GO with conditions (PR #11) | ⏳ ANAL-200 Digitalis on Android 17 as our bridge (after ANAL-199) | — |
| ANAL-163 Bare metal on the G14 (GA403WR) | ✓ ANAL-175 inventory and full driver map (PRs #8, #16; the owner's root run is processed too: dGPU `10de:2f58`, panel ATNA40CU05-0, speaker tuning found) | ✓ ANAL-199 G14 product `anybook_g14_x86_64`: USB GPT image, `boot_completed` in QEMU/OVMF, SELinux enforcing (PR #35) | ✓ ANAL-176 G14 desktop from USB (PR #39; follow-ups in #42). The desktop was reached on the G14 in a logs boot; the enforcing entry is being verified | ▶ ANAL-178 input and power (S0i3 first), ✓ ANAL-179 Wi-Fi, BT and audio (PR #43; G14 run pending) |
| ANAL-188 USB installer (M8) | ✓ ANAL-189 design and boot-chain prototype (PR #22): systemd-boot recommended, GRUB fallback; **awaiting owner sign-off** | ✓ ANAL-190 live USB image (PR #34): QEMU 38/39; booted on the G14 by the owner (`evidence/2026-10-16-installer/g14-live/`) | ⏸ ANAL-191 wizard | ⏸ ANAL-192 end-to-end tests |
| **ANAL-193 Device-in-the-loop on the G14 (§4a)** | ⏸ ANAL-194 runtime and agent on G14 Linux (owner installs the daemon) | ⏸ ANAL-195 Zen 5 validation in KVM | ⏸ ANAL-196 dual-boot test cycle | ⏸ ANAL-197 runtime on installed OpenBook |
| ANAL-186 NVIDIA dGPU | ✓ ANAL-187 research and dGPU-off default (`docs/nvidia.md`: off for M3–M8, N1–N6 after M4) | — | — | — |
| ANAL-165 Track B: Googlebook OS on AMD | ⏸ ANAL-182, ANAL-183 | ⏸ ANAL-184 | ⏸ ANAL-185 | — |
| ANAL-166 Performance and parity | ⏸ | — | — | — |

**Critical path to "OpenBook on the G14":**
1. ✓ ANAL-174 (PR #23) and ANAL-198 (PR #26).
2. ✓ ANAL-199 (PR #35): the G14 product, booting in QEMU. ✓ ANAL-190 (PR #34): the live USB image, first booted on the G14.
3. ✓ ANAL-176 (PR #39): the RADV crash that kept the G14 screen black is fixed and verified on a Radeon 610M. **The owner's boot of the `desktop2` stick confirms the desktop on the panel.**
4. ✓ ANAL-179 (PR #43): Wi-Fi (WPA2, DHCP, iperf3), Bluetooth and audio, tested in QEMU. The owner's `audionet3` stick run on the G14 is the hardware test. ▶ ANAL-178 (S0i3 power, input) is running.

**Reported, not yet in the repo:** in the owner's `desktop3` "save logs" boot, Android reached the desktop on the G14 at 78 s, the firmware fix worked, and an enforcing boot would hit 14 denials (down from 66). This comes from ANAL-176's reading of the stick logs; the evidence lands with PR #42.
5. The installer (ANAL-190 to ANAL-192).
6. ANAL-197: the runtime on the device.

## History

### 2026-10-17: G14 audio, Wi-Fi and Bluetooth, Android side (ANAL-179)

**Done** (`docs/g14-audio-net.md`)
- **Wi-Fi:** AOSP's wpa_supplicant and the framework's own nl80211 code, no vendor HAL (none is public) and no wificond (Android 17 has none); a DRIVER-command hook for the country code; the signed `regulatory.db`; AOSP's MT7925 firmware kept (the build the G14 loaded).
- **Bluetooth:** AOSP's AIDL HAL over the HCI user channel (`btusb` + `btmtk`), laptop profiles.
- **Audio:** `openbook-audio-setup` finds the codec's ALSA card at boot (the ALC285 is card 1 or 2) and unmutes it; an AOSP patch lets the example HAL use that card; a 48 kHz policy with jack handling.
- **Found:** no app could play or record (the audio HAL's message-queue memfds were denied), cfg80211's regulatory keyring was unsearchable, HDA codecs come up muted.
- **Tests:** `openbook-hwtest` runs in the save-logs entry (Wi-Fi scan/connect/DHCP/iperf3, Bluetooth, speaker-to-mic loopbacks), with `live-report.py` verdicts; a QEMU rig with an HDA card and a `mac80211_hwsim` access point.

**Evidence:** `evidence/2026-10-17-g14-audio-net/`. In QEMU: WPA2 connect, DHCP, iperf3 about 650–770 Mbit/s; a tone reaches the codec through ALSA cleanly and through AudioFlinger with dropped buffers (VM; open item). Nothing on the G14 yet.

**Next:** the owner boots `openbook-live-20261017-audionet3` (this branch + ANAL-176's desktop4): connect Wi-Fi, pair a device, then the save-logs entry (`docs/g14-audio-net.md` §7).

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
