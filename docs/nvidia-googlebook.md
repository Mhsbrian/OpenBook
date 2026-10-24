# NVIDIA dGPU on the Googlebook (Ruby) image: project-churro review and execution plan (ANAL-187 → ANAL-237)

Status as of 2026-10-22. This document covers the **Googlebook image** (the Ruby track: Google's Ruby system on OpenBook's G14 vendor and kernel). It does not cover the AOSP image. The earlier research, which is still valid for the kernel and userspace facts, is in `docs/nvidia.md`.

Labels:
- **CONFIRMED**: we read it in source or saw it on the laptop.
- **REPORTED**: another project's logs or third parties, not reproduced by us.
- **HYPOTHESIS**: not yet tested.

Evidence: `evidence/2026-10-21-nvidia-googlebook/`.

## Update, 2026-10-24: owner direction and refocus

**Owner direction** (B Honey on ANAL-187, 2026-10-22):
- **Top priority is deep sleep (S0i3) and battery,** through a basic, power-managed nouveau driver.
- **project-churro code may be used.** The owner calls it fair use: a private repo, for their own laptop, never published. Each reused patch records its provenance (Churro `d88a978`, file). If the repo or an image is ever published, those parts must be replaced or licensed first. This supersedes §1.4's "no code reused".

**What ANAL-238 measured on Ruby** (`evidence/2026-10-22-ruby-dgpu-power/`, PR #126):
- Our dGPU hook runs, and its HDMI-audio unbind works. The dGPU is very likely in D3cold; root is not readable on this user build.
- S0i3: 0 of 130 suspends.
- Asleep without S0i3 the laptop draws about 4.5 W.
- Most dark resumes are PCIe PME on the dGPU root port `00:03.1`.

**The honest technical picture** (`docs/power-input.md` §1):
- On the AOSP image, S0i3 also missed with the dGPU in D3cold and every endpoint in D3.
- Linux 7.2.8 on this laptop reached S0i3 with NVIDIA's driver managing the dGPU.
- **So a driver is not yet shown to be what unlocks S0i3.** Other suspects: PCIe PTM (`CONFIG_PCIE_PTM` is off in Google's GKI, so firmware PTM state stays during suspend), USB4 router power management, amd-pmf, MPM.

**Two issues therefore run side by side:**
- **ANAL-239: the basic driver.** nouveau as a Ruby vendor module with the r570 runtime-PM fixes. In Hybrid it is headless or pinned away from the panel path. `snd_hda_intel` must still be kept off the dGPU's HDMI-audio function: without vga_switcheroo (off in GKI) that function blocks D3cold even with nouveau bound.
- **ANAL-257: the S0i3 root cause.** Desk analysis of the SMU and idle-mask data, test-only modules (PTM off at suspend, the PCI snapshot), and a Linux live-USB A/B: nouveau bound vs driverless vs PTM off, with an optional Eco phase only with the owner's approval.

ANAL-240 (NVK), ANAL-241 (modes design) and ANAL-242 (VFIO) are parked until the deep-sleep work lands.

**Owner, 2026-10-24: no live USB, test directly over wireless adb.**
- adb on the Googlebook system is the non-root `shell` (CONFIRMED on `CL3B.260622.276.R4`: `ro.debuggable=0`, SELinux enforcing). It can read logs and bugreports, set `debug.*` properties and trigger sleep, but not load modules or read PCI power state.
- So one vendor update adds an allow-listed root "lab" helper, built on ANAL-238's PR #126 mechanism.
- nouveau and the test modules ship unloaded. adb properties load and unload them, run D3cold and s2idle cycles, and report to logcat.
- After that single install (with the owner's approvals), the A/B runs entirely over wireless adb.

## Summary

- **project-churro has already done Googlebook OS on our exact GPU, in discrete mode.** It is a recipe that converts the Googlebook recovery image for generic PCs, and its test laptop (an MSI) has the same GPU as the G14: RTX 5070 Ti Laptop, GB205, `10de:2f18`. In dGPU-only MUX mode it reports the panel, HDMI, Chrome and Skia-Vulkan SurfaceFlinger working on nouveau + NVK (REPORTED, 2026-10-18/19). That removes most of the "is it possible" risk for an Ultimate mode on the G14.
- **What it has not done is what our laptop needs most:**
  - hybrid use of the dGPU next to a working iGPU (its nouveau patch refuses to bind when any other GPU exists);
  - runtime PM;
  - suspend;
  - battery;
  - performance numbers;
  - CTS/dEQP;
  - an AMD iGPU;
  - switching the MUX from the OS.
- **We cannot copy its code.** It has no licence. We take the same upstream kernel commits from kernel.org and write our own Mesa and minigbm code from upstream patterns. The ideas and findings are free to use.
- **On the G14 today (read-only, CONFIRMED):**
  - The Ruby image enumerates the dGPU (`0000:64:00.0` and `.1` behind 00:03.1) with no GPU driver, and `snd_hda_intel` loaded.
  - Our vendor's D3cold hook (`vendor.openbook.dgpu-pm`) is present.
  - `dgpu_disable=1`, decided on 2026-10-16, was never applied: the laptop's Linux was replaced.
  - HDMI is dark, because it is wired to the dGPU.
- **Plan:** three graphics modes (Eco, Hybrid, Ultimate) that the user can lock from the OS, plus a research option that gives the dGPU to the Linux environment. MUX changes get automatic rollback and a USB recovery entry. Execution is epic ANAL-237 (ANAL-238 to ANAL-250).
- **Where we can still be first** (HYPOTHESIS until shown):
  - OS-integrated, rollback-safe graphics modes on a Googlebook-style system;
  - a power-managed dGPU next to an AMD iGPU;
  - per-app dGPU offload on Android;
  - the dGPU handed to the Linux VM.

  Discrete-mode Googlebook on GB205 is **not** a first. project-churro got there on 2026-10-18.

## 1. project-churro review

### 1.1 What it is

| | |
|---|---|
| Repo | https://github.com/alesimula/project-churro, reviewed at `d88a978` (2026-10-22 02:30 +0200) |
| Age, size | Created 2026-10-14. 48 commits, one author, 15 stars, 2 forks. 108 files, 1.5 MB, shell, C, Python and patches |
| Licence | **None.** GitHub reports `license: null`, and its own `docs/06` says "Churro has no LICENSE file yet; MIT would keep that simple" (CONFIRMED) |
| Approach | Converts the user's own Googlebook recovery image locally, with no Google binaries in the repo (like Chromefy/Croissant). It does five things: <ul><li>rebuilds **the same GKI** from Google's source with identical kABI CRCs, so Google's modules still load, and adds about 3,000 distro modules after a depmod/CRC check;</li><li>boots with GRUB and a boot-v4-style initrd;</li><li>uses software KeyMint/Gatekeeper;</li><li>repacks EROFS partitions with labels kept;</li><li>turns dm-verity off (orange state)</li></ul> |
| Hardware tried | <ul><li>MSI with an Arrow Lake Core Ultra 7 255HX and an RTX 5070 Ti Laptop (GB205): works in hybrid (Intel) and discrete (nouveau) mode.</li><li>VivoBook (Tiger Lake), with an instruction emulator.</li><li>G20AJ (Haswell plus GTX 970) on nouveau.</li><li>T300FA, which is below the CPU floor.</li></ul> |

### 1.2 What it reports on GB205 (REPORTED, its `docs/02` and `docs/05`)

1. **First boot in discrete mode.** nouveau binds GB205 and GSP-RM 570.144 boots with 12 GiB VRAM. SurfaceFlinger runs on "zink Vulkan 1.4 (NVIDIA GeForce RTX 5070 Ti Laptop GPU (NVK GB205))". But every display channel stalled: `core notifier timeout`, `wndw-N: timeout`.
2. **eDP alone.** The picture was squeezed into the left quarter of the screen. The cause: the laptop's GOP had left **DSC** on for the panel's 240 Hz mode, and nouveau never turns it off. Fixed with its `nouveau-dsc-off.patch` plus nine upstream GB20x display backports.
3. **Desktop usable, Chrome broken.** Chrome and its PWAs need `VK_ANDROID_external_memory_android_hardware_buffer`. NVK lacks it, so Chrome's GPU process restarted 291 times. Fixed by its NVK AHB patch.
4. **Skia Vulkan.** With two NVK graphics queues, SurfaceFlinger and HWUI run on NVK. A 3.5-minute MSI session had 2 `Davey!` events, 117 skipped frames, 0 nouveau faults and 0 crashes.
5. **Hybrid mode.** The NVIDIA GPU is unused, and the HDMI port wired to it stays dark. Reverse PRIME is listed as future work.

### 1.3 Component review and how we reuse each

| Churro component | What it does | Assessment | Our path |
|---|---|---|---|
| `nouveau.ko` as a vendor module, CRC-checked against Google's helper modules (107 symbols); replaces `drm_ttm_helper` with a strict superset | Lets nouveau load on Google's GKI | Sound. It is the same discipline we used for amdgpu | Same method on the Ruby G14 kernel `anybook-g14-gbos-16302624` (ANAL-239) |
| `nouveau-up-01..09` | GB20x display fixes and prerequisites | **Exact upstream commits**: `554ab79cfd10`, `c6659e0ffc19`, `eb1ffc3dc72d`, `9886aad51f4b`, `92f09dcb4e84`, `764deff8450c`, `39fd4b742720`, `9421dfe912e5`, `5bb489b33323` (`churro-pin.txt`) | Take them from kernel.org/linux-stable (GPL-2.0). Check 6.18.y first: 6.18.58 shipped 2026-10-21. Add the v7.3 r570 runtime-PM fixes and the revert of `8302d0afeaec`, which our tree carries as `ef763b480a3d` (`docs/nvidia.md` §2) |
| `nouveau-dsc-off.patch` | Clears head DSC on every modeset (classes C57D/CA7D) and the sink's `DP_DSC_ENABLE` before link training | Real bug class, blunt fix: it rules out DSC even when nouveau gains support. Whether the G14's 2880×1800@120 panel needs DSC is UNKNOWN | Assess on the G14 in Ultimate mode. Write our own minimal fix if needed, and offer it upstream (ANAL-239/244) |
| `nouveau-hybrid-guard.patch` | Refuses to bind if any non-NVIDIA display controller exists (`nouveau.hybrid=1` overrides) | **Wrong policy for the G14.** The iGPU is always present, and ASUS reportedly keeps it enumerated even in MUX mode (HYPOTHESIS), so nouveau would never bind | Our own MUX-aware policy, set at boot by the mode selector (ANAL-239, ANAL-241) |
| `nvk-android-hardware-buffer.patch` | AHB support for NVK on Mesa's common `vk_android` helpers, like panvk: <ul><li>buffer/image property queries;</li><li>deferred image creation from the AHB's layout at bind time;</li><li>dedicated-only import of the AHB's dma-buf</li></ul> | The most valuable piece: it removes our ANAL-187 blocker (CDD 7.1.4.2 [C-3-1], ANGLE's `EGL_ANDROID_image_native_buffer`). Gaps: <ul><li>it assumes one fd (`handle->data[0]`);</li><li>no YUV or external formats;</li><li>it claims export with no export test;</li><li>no dEQP results, only "Chrome works".</li></ul> Not in upstream Mesa as of 2026-10-22 (search) | Our own implementation on the same upstream helpers, following panvk/radv code (MIT), with `dEQP-VK.api.external.memory.android_hardware_buffer.*`, upstream-first (ANAL-240). With the owner's OK, invite the author to licence theirs or co-submit upstream |
| `nvk-two-graphics-queues.patch` | `queue_count = 2` for the graphics family; HWUI on Skia Vulkan needs ≥ 2 | Correct and trivial, and upstreamable | Same change, ours, upstream (ANAL-240) |
| minigbm `nouveau-native.patch` | Real `NOUVEAU_GEM_NEW` buffers (dumb buffers are refused on render nodes): linear, 256-byte pitch, VRAM with GART spill, GART for CPU-only buffers; map through `GEM_INFO`; `CPU_PREP` for sync | Needed for Ultimate mode. Linear-only costs performance, and there is no tiling. Android-Generic carries another nouveau backend (REPORTED) | Our own backend for Ultimate (ANAL-244). For Hybrid, allocation stays on amdgpu, with linear GTT buffers for cross-GPU use (ANAL-247) |
| Boot-time stack selection | GRUB `setpci` picks `androidboot.churro.gfx=native/nouveau/mesa/soft`; init imports `gfx-<stack>.rc` | Good pattern | Keyed on the **MUX state and the connected eDP**, not on "is there an iGPU". In our vendor, extend `anybook_gpu_probe` (ANAL-241) |
| `nouveau-ui-vk.rc`, `gfx-nouveau.rc` | `ro.hardware.egl=mesa` (Zink), `ro.hardware.vulkan=nouveau`, Skia Vulkan for SurfaceFlinger and HWUI | Matches what Mesa forces on Blackwell (Zink only) | Same choices for Ultimate (ANAL-244) |
| Mesa build | NVK's Rust parts use the GKI's Android Rust toolchain (`x86_64-linux-android` std, `panic=abort`), bindgen with a matched libclang, cbindgen and Mesa CI's libelf | Useful and specific know-how | Our Mesa build gains Rust (ANAL-240) |
| `gpu-nouveau/patch-vendor.sh` | `sysfs_gpu` labels for the PCI ID files of GPUs behind bridges | We fixed the same thing for the iGPU at 65:00.0 in the AOSP product | Label 64:00.0 (ANAL-239) |
| `nouveau-zink-from-kepler`, `nouveau-import-plane-offset` | Pre-Turing fixes | Not relevant: Blackwell is Zink-only upstream | — |
| `firmware-lockdown` (not NVIDIA) | Removes flashrom, futility, fwupd and vpd; blocklists the SPI and TPM drivers; adds `efi_pstore.pstore_disable=1`; limits vold to USB | A real safety lesson for any Googlebook image on a PC | Our G14: none of fwupd, flashrom or futility, but `gscutil`/`check_tpm_clear` with `/dev/tpm0`, `efi_pstore` and `spi_amd` loaded, and `update_engine` running (§2). Audit in ANAL-251 |

### 1.4 Licensing

- No licence means all rights are reserved, so **no Churro code goes into OpenBook**.
- The kernel backports are upstream GPL-2.0 commits, and we take them from upstream.
- The approach and findings are facts we can use: DSC left on by the GOP, AHB as the Chrome blocker, two queues for HWUI, dumb buffers refused on render nodes.
- Our implementations follow upstream Mesa and AOSP code instead.
- **Recommended outward action (needs the owner's OK):** open an issue on project-churro asking for a licence (MIT, as its doc suggests), and offer to co-submit the NVK AHB and two-queue changes to Mesa.

### 1.5 What Churro has not shown

- **Hybrid (Optimus) use of the dGPU.** It has no PRIME, no offload, and no HDMI in hybrid mode.
- **Power.** Nothing on nouveau runtime PM, s2idle with GSP, battery, or what a driverless dGPU costs.
- **Measurement.** No performance numbers, and no CTS or dEQP.
- **AMD iGPU + NVIDIA,** and switching the MUX from the OS.

## 2. The G14 on the Googlebook image today (read-only, 2026-10-22)

From `g14-ruby-readonly.txt`. adb runs as `shell` on a user build, so PCI power state and dmesg are not readable.

- **Builds:** system `Lenovo/ruby/ruby:17/CL3B.260622.271.R1/16452207:user/release-keys`, vendor `OpenBook/anybook_g14_x86_64` userdebug, kernel `6.18.21-android17-5-gfbfdd65b0fd1`, verified-boot state orange.
- **dGPU:** enumerated as `0000:64:00.0` and `0000:64:00.1`, the children of root port 00:03.1. DRM shows only `card0` (amdgpu, with eDP and 8 DP) and `renderD128`. Modules: `amdgpu`, `snd_hda_intel`, `asus_wmi`/`asus_nb_wmi` and `nvidia_wmi_ec_backlight`; no `nouveau`, `nova` or `vfio`.
- **Power hook:** `vendor.openbook.dgpu-pm` is in `/vendor/etc/init/hw/init.openbook.rc`. In the AOSP image it put both dGPU functions in D3cold on the G14 (`docs/g14-product.md`). **On Ruby it is unverified (HYPOTHESIS: it works the same, since it is our vendor).**
- **S0i3 attribution:** Ruby's sleep notes say S0i3 is "still blocked by the driverless dGPU". `docs/power-input.md` showed on the AOSP image that the dGPU already in D3cold did not change the S0i3 miss. ANAL-238 settles this with a root capture.
- **Firmware and TPM tools.** No fwupd, flashrom, futility, vpd or crossystem, and no `/dev/mtd*`. But these are present:
  - `/system/bin/gscutil`, `gscd`, `check_tpm_clear` and `ectool`, with their rc files, never started this boot;
  - `/dev/tpm0` (fTPM via `tpm_crb`);
  - `efi_pstore`, loaded with no `pstore_disable`;
  - `spi_amd`, loaded;
  - `update_engine`, running (see ANAL-229's OTA guard).

  ANAL-251 audits these.

## 3. Graphics modes (design target, ANAL-241)

| Mode | `gpu_mux_mode` | `dgpu_disable` | Panel / HDMI | Android stack | dGPU | Expected use |
|---|---|---|---|---|---|---|
| **Eco** | 1 (Optimus) | 1 | 890M / dark | RADV + ANGLE, minigbm and drm_hwcomposer on amdgpu (today's stack) | not powered or enumerated | longest battery |
| **Hybrid** (default) | 1 | 0 | 890M / dark until ANAL-249 | Same system stack. Opted-in apps on NVK (ANAL-247) | D3cold when idle (hook today; nouveau runtime PM after ANAL-243) | everyday use |
| **Ultimate** | 0 (dGPU) | 0 | NVIDIA / NVIDIA | nouveau KMS, NVK + Zink, Skia Vulkan, minigbm nouveau backend | always on | plugged in, HDMI, GPU-heavy work |
| **Linux GPU** (Hybrid option) | 1 | 0 | 890M / dark | unchanged | assigned to the Linux VM through VFIO; guest runs NVIDIA's own driver, installed by the user | CUDA and Linux games (ANAL-242 research) |

Mechanics:
- **Firmware switches.**
  - `dgpu_disable` is saved by firmware, and setting it ejects the dGPU through ACPI.
  - `gpu_mux_mode` needs a reboot.
  - The 6.18 asus-wmi refuses the dangerous combinations: "Can not switch MUX to dGPU mode when dGPU is disabled", and the reverse (`docs/nvidia.md`, `evidence/2026-10-16-nvidia/asus-wmi-6.18.txt`).
- **Boot-time selection.** An early-init probe reads the MUX state and which DRM device has the connected eDP. It then loads nouveau (or not), sets `ro.hardware.*` and pins minigbm and drm_hwcomposer to the display GPU.
- **Rollback.** Before a MUX switch, the switch service writes a pending marker and a boot counter. If a dGPU-MUX boot does not reach `boot_completed` with a composed frame within N tries, early init (asus-wmi is a vendor module) restores `gpu_mux_mode=1` and reboots. The USB stick gets a "Restore Hybrid graphics" entry.
- **UX.** Google's Settings app cannot be changed, so we ship our own tile or app in the vendor/product overlay (HYPOTHESIS: the right place is settled in ANAL-241).
- **Approval gate.** The first real MUX or `dgpu_disable` write on the G14 needs B Honey's approval naming the device and operation, after the design is approved and the recovery path has been tested.

Hybrid offload details (topology A) are in `docs/nvidia.md` §5. That section already rests on AOSP 17 source:
- one Vulkan HAL per process;
- the per-app updatable-driver switch;
- minigbm taking the first render node;
- NVK's 128-byte linear render-target rule.

## 4. Epic ANAL-237

| Stage | Issue | What | Gate / owner action |
|---|---|---|---|
| 1 | ANAL-238 | dGPU power state on Ruby (root capture), battery cost, S0i3 attribution | Image or stick writes need approval |
| 1 | ANAL-239 | nouveau for GB205 as a Ruby vendor module: MUX-aware, upstream GB20x and r570 fixes, GSP firmware, CRC report, QEMU load | none (no laptop) |
| 1 | ANAL-240 | NVK for Android: Rust toolchain, our own AHB, two queues, dEQP packages, upstream-first | Posting upstream needs the owner's OK |
| 1 | ANAL-241 | Modes design: switching, locking, boot-time selection, rollback, recovery, UX; QEMU prototype | **B Honey approves the design** |
| 1 | ANAL-242 | Research: VFIO dGPU into the Linux environment | none |
| 2 | ANAL-243 | Hybrid on the G14: nouveau bound, **runtime-PM gate (20 cycles), s2idle gate (20 cycles)**, headless NVK, dEQP-VK AHB | dev image write approval; **stop if a gate fails** |
| 2 | ANAL-244 | Ultimate on the G14: panel and HDMI on nouveau/NVK, Chrome, return to Hybrid | design approved, recovery tested, MUX write approved |
| 2 | ANAL-245 | Benchmark: NVK on GB205 against RADV on the 890M | decides which modes are worth shipping |
| 3 | ANAL-246 | Mode switcher with locking and automatic rollback | — |
| 3 | ANAL-247 | Per-app offload in Hybrid | benchmark shows a gain |
| 3 | ANAL-248 | Linux-environment GPU (VFIO) | ANAL-242 says go |
| 3 | ANAL-249 | HDMI in Hybrid (reverse PRIME) | research first |
| 4 | ANAL-250 | Release through ANAL-232 | the release process's approvals |

Separate: ANAL-251, the Ruby safety audit (firmware and TPM tools, `efi_pstore`, `update_engine`). It is parked for the owner to promote.

## 5. Risks (ranked)

1. **Runtime PM under nouveau on GB20x laptops is unproven.** Upstream fixed r570 runtime PM through 7.3 (released 2026-10-18), and Lyude Paul's July series says "there are still some remaining issues". If the ANAL-243 gate fails, Hybrid stays on the driverless D3cold hook, and the dGPU is used only in Ultimate.
2. **Performance may disappoint.** One GB206 laptop report showed 5–10% of the proprietary driver, and desktop Blackwell shows under 50%. ANAL-245 is a real gate: Ultimate may end up recommended only for HDMI and plugged-in use.
3. **Firmware state on the owner's laptop.** A MUX switch that leaves no working display is the worst case. That is why there is a rollback, a USB recovery entry, approval per write, and a QEMU state-machine test first.
4. **Android has no hybrid-GPU plumbing.** minigbm and drm_hwcomposer must be pinned to amdgpu before nouveau ever loads in Hybrid. Otherwise gralloc can silently move to the dGPU (`docs/nvidia.md` §5).
5. **Licence gap.** Without a licence from project-churro we write our own code. That costs time, not feasibility.
6. **Size.** 61 MB of GSP firmware in `vendor`, plus NVK, Zink and NAK.
7. **Nova** may replace nouveau for GSP GPUs in the long term. Our Mesa, gralloc, mode and Android work would carry over.

## Sources (read 2026-10-21/22)

- **project-churro** `d88a978`: README, `docs/02`, `03`, `05`, `06`, `08`, and the patches listed with their sha256 in `evidence/2026-10-21-nvidia-googlebook/churro-pin.txt`. https://github.com/alesimula/project-churro
- **kernel.org:** Linux 7.3 released 2026-10-18; 6.18.58 released 2026-10-21. https://www.kernel.org/
- **Lyude Paul, "drm/nouveau: GSP runtime PM fixes" v4** (2026-07-27): https://lkml.iu.edu/2607.3/06008.html
- **Phoronix, Linux 7.3-rc5 DRM fixes** (2026-09-26; secondary): r570 suspend/resume and VRAM pinning fixes. https://www.phoronix.com/news/Linux-7.3-rc5-DRM
- **Mesa search for NVK AHB** (2026-10-22): no upstream NVK merge request found. Nearest is Venus's AHB work, https://gitlab.freedesktop.org/mesa/mesa/-/merge_requests/10847
- **Our own earlier sources:** `docs/nvidia.md` (2026-10-16), `docs/g14-product.md`, `docs/power-input.md`, and the Ruby branch docs (`googlebook-bringup.md`, `googlebook-sleep.md`).
