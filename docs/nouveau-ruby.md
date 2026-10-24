# nouveau on the Googlebook image: a power-managed driver for the G14's dGPU (ANAL-239)

Status as of 2026-10-24. Track: **Ruby** (Google's Ruby system on OpenBook's G14 vendor and kernel). Plan and
background: `docs/nvidia-googlebook.md` (PR #125) and `docs/nvidia.md`. Evidence: `evidence/2026-10-24-nouveau-ruby/`.

Labels:
- **CONFIRMED**: read in source, or seen in a build, check or QEMU run of ours.
- **HYPOTHESIS**: not yet shown; the on-laptop gates belong to ANAL-243.

**Nothing here ran on the laptop.** There is no NVIDIA GPU in QEMU, so nouveau has never bound a GPU in any of
these checks.

## Summary

- **What it is:** nouveau for the RTX 5070 Ti Laptop GPU (GB205), built for the G14 kernel lane as a vendor
  module, with one helper, `drm_gpuvm.ko`. It runs headless (`modeset=2`) with runtime PM forced on
  (`runpm=1`), so the dGPU can sit in D3cold when idle. It loads last, after amdgpu.
- **The source:** nouveau from the kernel tree, plus 43 upstream fixes:
  - linux-6.18.y up to 6.18.58, including the r570 suspend fixes and the revert of `8302d0afeaec`;
  - the v7.3 r570 runtime-PM series.

  It also carries two small OpenBook adaptations. No project-churro code is used: Churro's nine GB20x backports
  are upstream commits that 6.18.y already carries.
- **The kernel must change (CONFIRMED). This changes the release impact.** The Ruby GKI exports to vendor modules
  only what is on its KMI list. nouveau needs **33 symbols that no x86_64 list has**, among them DRM GEM core,
  maple-tree and KMS helpers.
  - So `anybook_amd` gains them (`kernel/patches/common/0004`), and the kernel, `system_dlkm` and every vendor
    module are rebuilt.
  - Existing exports and their CRCs are unchanged, and so is every existing module's code (§3).
  - Release impact: **Ruby boot (kernel), vendor_boot, system_dlkm, vendor_dlkm and vendor** (firmware and the
    hook), not only vendor_dlkm as the issue first assumed.
- **Checks (CONFIRMED):**
  - The G14 kernel pipeline passes: build, module lists, signatures, firmware, and 5 of 5 QEMU boots with every
    vendor module live.
  - The offline load check finds 0 problems against the new kernel.
  - The rebuild comparison passes: every installed export keeps its CRC, and every module keeps its exports,
    imports and code.
  - In QEMU, nouveau loads with `runpm=1 modeset=2` from `modules.options`, registers its PCI driver, binds
    nothing, creates no DRM node and causes no new SELinux denial.
  - The hook's fixture tests pass on the host and in the Android guest, and the GPU-probe decision holds with
    nouveau bound.
- **Not shown (HYPOTHESIS, ANAL-243):**
  - that nouveau boots GSP-RM on GB205;
  - that the dGPU reaches D3cold under nouveau (`_PR3`/PG00), and wakes from it;
  - s2idle with nouveau bound;
  - battery draw;
  - whether any of it helps S0i3 (ANAL-257).

## 1. Patch series

`kernel/patches/nouveau/`, applied by `scripts/kernel-nouveau-apply.sh`. Every patch keeps its upstream author and
`(cherry picked from …)` line. `evidence/2026-10-24-nouveau-ruby/series.md` has the table with upstream IDs and the
Churro mapping.

| Patches | What |
|---|---|
| 0001–0037 | Every nouveau commit in linux-6.18.y from v6.18.21 to v6.18.58, except `0589706ace3b`, which changes the built-in DRM client API, i.e. vmlinux. This includes the GB20x display fixes (Churro's `nouveau-up-01..09`, same patch IDs), the r570 suspend fixes and the revert of `8302d0afeaec`, which our tree carries as `ef763b480a3d`. |
| 0038–0043 | v7.3's r570 runtime-PM series, not in 6.18.y: GSP's GCX-entry readiness check before runtime suspend, the comptag/compression state saved across fbsr, GcOff back on, and the follow-up null check. |
| 0022, adapted | One line: `kzalloc_obj(*priv)` becomes `kzalloc(sizeof(*priv), GFP_KERNEL)`. Our 6.18.21 base predates 6.18.y's `kmalloc_obj` helpers. |
| 0044 (OpenBook) | Guards the Tegra-only IOMMU and regulator calls with `IS_ENABLED(CONFIG_NOUVEAU_PLATFORM_DRIVER)`, so the x86 build does not import `iommu_map`, `iommu_unmap` or `regulator_set_voltage` for code no PCI GPU reaches. |

The cancelled run's cherry-picks (`~/anybook/kernel/nvidia-anal239/wt`) were checked by regenerating the series
independently: the trees are identical.

Left out on purpose:
- Churro's `nouveau-dsc-off` (only for Ultimate mode, ANAL-244) and `nouveau-hybrid-guard` (it would never bind on
  the G14);
- robustness fixes from the 7.4 merge window (next revision);
- the NVK-only uvmm/sched fixes (ANAL-240).

`series.md` lists each one.

## 2. How it is built

- **External Kleaf module.** `kernel/devices/anybook/nvidia/` holds `BUILD.bazel`, `Kbuild`, `Makefile` and
  `Kconfig.ext`. `kernel-nouveau-apply.sh` copies `common`'s `drivers/gpu/drm/nouveau` into it, applies the series
  as commits in a git repository of its own, and checks the result against a pinned tree id
  (`kernel/patches/nouveau/TREE`).
  - Kleaf stamps that repository's HEAD into `nouveau.ko` as `scmversion`, so the module says exactly which
    source it is.
- **Why external, not `DRM_NOUVEAU=m`:** nouveau's Kconfig `select`s built-in options, `FW_CACHE` among them, which
  the GKI has off. Turning it on in the device config would build modules against a different configuration from
  vmlinux.
  - The external build leaves the device config alone, except `ANYBOOK_NOUVEAU` (from `Kconfig.ext`), which
    selects `DRM_GPUVM=m`.
  - No built-in code reads either symbol (CONFIRMED by grep).
- **mxm-wmi is not built.** nouveau calls it only from its vga_switcheroo code, which the GKI does not build:
  `nouveau.ko`'s `depends` does not name it.
- **Build:**

  ```sh
  ANYBOOK_KERNEL_SRC=<tree> G14_LABEL=anybook-g14-gbos-16302624-anal239 ANYBOOK_KERNEL_JOBS=8 \
    BAZEL_ARGS=--local_resources=memory=16384 scripts/kernel-g14-package.sh
  ```

  The apply step now also runs `kernel-nouveau-apply.sh`. `kernel-build.sh` sets `KLEAF_EXTRA_GIT_PROJECTS`
  when the nvidia package has its git repository. `ANYBOOK_KERNEL_SRC` (default `~/anybook/kernel/src`) lets a
  task build in its own copy of the tree.
- **Reproducible.** A second build in a fresh tree, from the repo alone, gives byte-identical `nouveau.ko`,
  `drm_gpuvm.ko` and `openbook_lid_guard.ko`.
  - Every other vendor module is identical apart from split `.BTF`, which pahole does not reproduce for 35 of them.
  - The kernel and GKI modules carry a new signing key per build (`repro/compare.txt`).
  - The release therefore pins the exact files of the first build.
- **Out-of-tree taint.** An external module taints the kernel with `O` (4096). The Ruby kernel already carries
  that flag from `openbook_lid_guard`, which is external too.

## 3. Why the kernel changes, and what changes

- **What modpost and the offline check showed (CONFIRMED).** The trimmed Ruby GKI does not export 30 of nouveau's
  imports, and exports 3 more (`iowrite16`, `mas_find`, `rb_first`) only to signed GKI modules (`KSYM_FLAG_PROTECTED`).
  - Kleaf's add-only symbol-list update, run independently, reached the same 33.
  - Kleaf also listed 29 symbols that other x86_64 lists already carry; those change nothing.
- **Adapting nouveau instead was tried and abandoned.** Five semantics-preserving patches removed 10 symbols:
  - `refcount_dec_and_mutex_lock`;
  - the rwlock irqsave pair;
  - `acpi_get_next_object`;
  - the PCI ROM enable/disable pair;
  - the Tegra calls.

  But 26 remained, among them `drm_gem_object_init`, `dma_resv_fini` and the maple-tree API that GEM and uvmm are
  built on. Working around those would be a fork of nouveau's core. Churro solves the same problem by rebuilding
  the GKI. Only the Tegra guard (0044) was kept.
- **The change itself:** `kernel/patches/common/0004` adds the 33 symbols to `gki/x86_64/symbols/anybook_amd`.
  - It is the same partner-list mechanism ANAL-171 (214 symbols) and the efivarfs follow-up (26) used.
  - `common` becomes `206eb00bd0c4`, and the release string `6.18.21-android17-5-g206eb00bd0c4`.
- **Proof that nothing else changed** (`rebuild-compare.md`, `scripts/kernel-nouveau-check.py --compare-vmlinux`).
  RB-20261023-03's kernel, `vendor_dlkm` and `system_dlkm` were compared with the rebuild:
  - **vmlinux:** 0 exports removed, 0 CRCs changed. 33 exports were added, and 3 lost the protected flag.
  - **The 140 vendor modules and the rebuilt `openbook_lid_guard`:**
    - exports, CRCs and flags are identical;
    - imports and their CRCs are identical;
    - every section is identical apart from `.modinfo`'s vermagic and scmversion, the build ID and `.BTF`.
  - **`.BTF`:** split BTF follows the vmlinux it was built against. The GKI has `MODULE_ALLOW_BTF_MISMATCH=y`, so
    BTF never blocks a load.
  - **The 100 `system_dlkm` modules:** the same, plus a new signature (a new GKI build means a new signing key).
- **What the release has to ship:**
  - The kernel (`boot`).
  - `vendor_boot`: its ramdisk directory is named after the release.
  - `system_dlkm`: its modules are signed by the new key.
  - `vendor_dlkm`: every module has the new vermagic, and the image now holds `drm_gpuvm.ko`, `nouveau.ko` and
    `modules.options`.
  - `openbook_lid_guard.ko`: rebuilt, in the dist, for the release to add as before.

## 4. Hybrid policy and power

- **`modules.options`** (`kernel/devices/anybook/g14/modules.options`, in `vendor_dlkm`): `options nouveau runpm=1
  modeset=2`.
  - **runpm=1 (required, CONFIRMED in source).** nouveau's default (-1) enables runtime PM only for an Optimus
    laptop it detects through ACPI `_DSM`. That detection is compiled only with `CONFIG_VGA_SWITCHEROO`, which the
    GKI lacks, so on Ruby the default would leave the dGPU in D0.
  - **modeset=2 (headless).** No display engine, connectors or CRTCs. In Hybrid the panel is on the 890M, and the
    dGPU's only output, HDMI, stays dark as today.
  - **CONFIRMED in QEMU:** libmodprobe passes both (`Loading module …/nouveau.ko with args 'runpm=1 modeset=2'`).
  - **Fallback without a rebuild:** `nouveau.modeset=0` on the kernel command line. libmodprobe appends command-line
    options after the file's (CONFIRMED in `libmodprobe/module_config.cpp`). nouveau then loads, binds nothing, and
    `vendor.openbook.dgpu-pm` handles the dGPU as today.
- **amdgpu keeps card0 and renderD128.**
  - nouveau is last in `vendor_dlkm`'s `modules.load`, after amdgpu and every module that loaded before.
  - Neither driver asks for asynchronous probing, so amdgpu's `drm_dev_register()` finishes inside its own load
    (CONFIRMED in source).
  - **Why it matters (CONFIRMED in our AOSP sources):**
    - minigbm takes the **first render node** whose driver it knows, and it has a nouveau backend;
    - drm_hwcomposer skips any DRM device without CRTCs, connectors and encoders, so it ignores a headless nouveau;
    - `anybook_gpu_probe` prefers an amdgpu-bound card. Its real code, built on the host against AOSP's `libbase`,
      returns `hal=amdgpu card0` for a G14 with nouveau bound (new fixture `g14-ga403wr-nouveau.txt`;
      `gpu-probe-host.txt`).
  - **HYPOTHESIS until ANAL-243:** on the laptop, `renderD128` is amdgpu's.
- **HDMI audio.** `openbook-pc-setup dgpu-pm` now takes `snd_hda_intel` off the dGPU's HDMI-audio function and sets
  `power/control=auto` on it **also when nouveau drives the GPU**.
  - Without vga_switcheroo nothing runtime-suspends that function, and it would keep the slot powered.
  - Runtime PM of the GPU function itself is left to nouveau; the hook logs it.
- **D3cold path (from source; HYPOTHESIS on the G14).** nouveau's Optimus `_DSM` power-off is compiled out with
  vga_switcheroo.
  - Its runtime suspend ends in `pci_set_power_state(D3cold)`.
  - Once both functions are suspended, the root port `00:03.1` runtime-suspends, and ACPI turns off its `_PR3`
    resource `PG00`, as the driverless hook already achieves on the AOSP image (`docs/g14-product.md`).
- **Logging.** `dgpu-pm` and `dgpu-report` log a `nouveau: runpm=… modeset=… bound=…` line to logd as well, through
  ANAL-238's `log()`: Ruby denies vendor writes to kmsg. That commit is included unchanged, see §6.
- **GSP firmware lifetime (CONFIRMED in source).** r535 copies the GSP images into DMA buffers at first boot and
  releases the files.
  - So runtime and system resume reboot GSP from memory, and the GKI's `FW_CACHE=n` is no problem.
  - The cost is that memory, while nouveau is bound (HYPOTHESIS: about 64 MB).

## 5. Firmware

- **Files:** GSP-RM 570.144 for GB205, 3 files, 64.0 MB, under `vendor/firmware/nvidia/gb205/gsp/`, plus
  `LICENSES/LICENCE.nvidia`. They come from linux-firmware `38c1a709`.
  - `kernel/firmware/anybook-nvidia.rules` selects them.
  - `scripts/kernel-firmware-subset.py` now resolves WHENCE directory links (`nvidia/gb205 -> gb202`); the AMD
    subset it produces is unchanged.
  - `scripts/kernel-g14-firmware.py` stages them: WHENCE links become regular files, with a manifest of hashes and
    licences.
- **Install unmodified and uncompressed.** The GKI has `FW_LOADER_COMPRESS` off. Ruby labels `/vendor/firmware`
  `openbook_vendor_fw_file`, which the kernel already reads for amdgpu.
- **Space:** vendor grows by about 64 MB, from 164.6 MB. The v2 layout's 24 GiB super has about 22 GB free.
- **Licence.** `LICENCE.nvidia` §2.1.2 allows redistribution of the unmodified files with the licence "solely for
  use on operating systems distributed under the terms of an OSI-approved open source license".
  - The Ruby image is Google's proprietary system and is not redistributed: it is the owner's own laptop.
  - **If a Ruby image is ever published,** this firmware needs a licence review, as Churro-derived code would
    (`docs/nvidia.md` §3, Track B).

## 6. Vendor changes and their base

- **`/vendor/bin/openbook-pc-setup`.** The base is RB-20261023-03's (`0e70d4a5…`). This branch carries ANAL-238's
  hook commit (`7c22694`, PR #126) unchanged, because its logd logging is required here. ANAL-239's change is on top:
  - HDMI audio is taken off `snd_hda_intel` even with nouveau bound;
  - the `nouveau:` facts line.
- **ANAL-238's `init.openbook.rc` and policy rule** (dgpu-report at boot, the D0 hold) are not needed by this
  change. They ship with ANAL-238. Without them, `dgpu-pm` still runs at early-init, but before logd starts, so its
  lines reach no log on Ruby.
- **No new SELinux rule.** `dgpu-pm` already reads sysfs and module parameters, writes the HDA unbind and
  `power/control`, and logs to logd (`policy-check.txt` of ANAL-238).
- **`/vendor/firmware`:** see §5.

## 7. Checks

| Check | Result | Evidence |
|---|---|---|
| G14 kernel pipeline (`kernel-g14-package.sh`): build, module lists, signatures, firmware staging, QEMU usb/uas/nvme/both-uuid/vm with every vendor module live | PASS | `kernel-g14/` |
| Offline load check, new modules against the new kernel's binaries (vermagic, every import's exporter and CRC, protected flags, GPL, duplicates, dependency order) | 0 problems | `load-check.md` |
| Rebuild comparison against RB-20261023-03 (kernel, vendor_dlkm, system_dlkm) | PASS | `rebuild-compare.md` |
| Checker self-tests: 141/141 installed Ruby modules pass as "new"; 9 planted faults (CRC, vermagic, protected import, duplicate export, load order, unresolved, export CRC) all caught | PASS | `tests/` |
| QEMU guest check, new kernel (vm, nvme): nouveau and drm_gpuvm live with `runpm=1 modeset=2`, PCI driver registered, nothing bound, no DRM node, no kernel error, no new denial against the Ruby-kernel baseline, hook runs as root, fixtures pass under the guest's sh and toybox | PASS | `qemu-guest/` |
| Hook fixture tests (bash, sh) | 49/49 | `tests/` |
| GPU-probe decision on the host, 9 fixtures including nouveau bound | as expected | `gpu-probe-host.txt` |
| Reproducibility: a second build in a fresh tree, using only the repo's scripts | `nouveau.ko`, `drm_gpuvm.ko`, `openbook_lid_guard.ko` and 107 vendor modules byte-identical; 35 differ only in split `.BTF`; the GKI modules and kernel differ by their per-build signing key | `repro/compare.txt` |

## 8. What ANAL-243 must show on the laptop

1. The kernel log shows nouveau binding GB205 and GSP-RM 570.144 booting.
2. `renderD128` and `card0` are amdgpu's. The panel, SurfaceFlinger and Chrome are unchanged.
3. `dgpu-report` shows `state=d3cold`, nouveau's `runtime_status=suspended` and PG00 off, then 20 D3cold↔D0 cycles.
4. s2idle 20 times with nouveau bound, plus the sleep draw and the PME wakes on IRQ 38, against today's 4.5 W.
5. If anything fails: `nouveau.modeset=0` on the command line, or the previous release's slot.
