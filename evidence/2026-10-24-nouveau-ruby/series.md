# nouveau series for the Ruby G14 kernel (ANAL-239)

Applied by `scripts/kernel-nouveau-apply.sh` to `drivers/gpu/drm/nouveau` of kernel/common `805bc4b8e099` (which carries the same nouveau as the Ruby kernel `fbfdd65b0fd1`). Upstream: linux-6.18.y (`v6.18.21..v6.18.58`, fetched 2026-10-24) and torvalds `v7.3`.

| # | subject | from | upstream commit | in v7.3 | Churro (`d88a978`) |
|---|---|---|---|---|---|
| 0001 | drm/nouveau: fix u32 overflow in pushbuf reloc bounds check | 6.18.y `332884f5eb79` | `2fc87d37be1b` | yes |  |
| 0002 | drm/nouveau: fix nvkm_device leak on aperture removal failure | 6.18.y `4404d7d2dda4` | `6597ff1d8de3` | yes |  |
| 0003 | drm/nouveau/bios: specify correct display fuse register for Ampere and Ada | 6.18.y `340936ebf5ae` | `c1cf2d5db80c` | yes |  |
| 0004 | drm/nouveau: fix reversed error cleanup order in ucopy functions | 6.18.y `4e109faa9ea2` | `ab99ead646b1` | yes |  |
| 0005 | drm/nouveau/acr: fix missing nvkm_done() in error path of nvkm_acr_oneinit() | 6.18.y `fbb9effc8168` | `c3027973f692` | yes |  |
| 0006 | nouveau/gem: reserve the bo in the info ioctl around the vma lookup | 6.18.y `ff110e85837d` | `5e17160d41d9` | yes |  |
| 0007 | drm/nouveau/disp/r535: Add scanline position support + head state support | 6.18.y `f5acd8f48cac` | `804cb093b245` | yes | up-01 |
| 0008 | drm/nouveau/gsp: use per-version DP_CONFIG_STREAM params on r570 firmware | 6.18.y `5ba4bcb3b96c` | `39fd4b742720` | yes | up-07 |
| 0009 | drm/nouveau: unsubscribe the channel-kill event before the fence context | 6.18.y `f3830fdd6930` | `511585987d27` | yes |  |
| 0010 | drm/nouveau: Use write-combined maps for coherent | 6.18.y `4cf436de06ca` | `774b73428e6e` | yes |  |
| 0011 | drm/nouveau/uvmm: fix NULL deref unwinding an OP_MAP_SPARSE op | 6.18.y `b7dc03e09313` | `412a6ceb56d5` | yes |  |
| 0012 | drm/nouveau/uvmm: fix premature region free on failed OP_UNMAP_SPARSE | 6.18.y `24c25b182d17` | `ccf930812f23` | yes |  |
| 0013 | drm/nouveau/uvmm: clear the dirty flag when unwinding an OP_UNMAP_SPARSE | 6.18.y `1101cbfe7f34` | `38a62306c426` | yes |  |
| 0014 | drm/nouveau/disp: move GSP head-timing ISR and vblank helpers to tu102.c | 6.18.y `a046e789ab66` | `c6659e0ffc19` | yes | up-02 |
| 0015 | drm/nouveau/disp: move the GSP HDMI GCP AVMute write to engine/disp | 6.18.y `94d8195eb418` | `eb1ffc3dc72d` | yes | up-03 |
| 0016 | drm/nouveau/disp: route GSP-RM display MMIO through nvkm_disp_func hooks | 6.18.y `4739d519def7` | `9886aad51f4b` | yes | up-04 |
| 0017 | drm/nouveau/disp: fix HDMI vendor infoframes on GB20x | 6.18.y `ecb110991bc9` | `92f09dcb4e84` | yes | up-05 |
| 0018 | drm/nouveau/disp: fix HDMI GCP AVMute register offsets on GB20x | 6.18.y `0e346b65a413` | `764deff8450c` | yes | up-06 |
| 0019 | drm/nouveau/disp: fix head state readback on GB20x | 6.18.y `dc7c40ffaa1b` | `9421dfe912e5` | yes | up-08 |
| 0020 | drm/nouveau/gsp: fix vblank interrupts on GB20x | 6.18.y `e5e7a61fa9e8` | `5bb489b33323` | yes | up-09 |
| 0021 | drm/nouveau/gsp: add SEC2 to GA100 chip table | 6.18.y `f29267ace042` | `604d0efb17cc` | yes |  |
| 0022 | drm/nouveau/bios: skip the IFR header if present (adapted: `kzalloc_obj`) | 6.18.y `ca5f986eb459` | `4beeac5d2015` | yes |  |
| 0023 | Revert "nouveau/gsp: fix suspend/resume regression on r570 firmware" | 6.18.y `b0bd757f910a` | `a5c41fa7f925` | yes |  |
| 0024 | drm/nouveau/gsp: Increase delay for magic sleep in r535_gsp_fini() | 6.18.y `28b898b5c700` | `bbb9293c9bb7` | yes |  |
| 0025 | drm/nouveau/gsp/r570: Set GcOff = 0 in fbsr | 6.18.y `80b8a76823de` | `12f6eff11ccf` | yes |  |
| 0026 | drm/nouveau/gsp/r570: Enable S/R Display workaround in GSP | 6.18.y `526d8f45c6ef` | `24fbd6d4bcf3` | yes |  |
| 0027 | drm/nouveau/clk: fix list cursor use after loop in nvkm_clk_ustate_update | 6.18.y `0d096a7f7d79` | `aff09d9e37e0` | yes |  |
| 0028 | drm/nouveau/clk: don't clobber reclock status when restoring volt/fan | 6.18.y `40afa1f7a5c7` | `e5cccdafc855` | yes |  |
| 0029 | drm/nouveau/disp: don't reject HDMI config on cards without SCDC | 6.18.y `ca29834c8c14` | `1717fcc5be57` | yes |  |
| 0030 | drm/nouveau/uvmm: fix UAF in nouveau_uvmm_sm when BO is in TTM_PL_SYSTEM | 6.18.y `0d29bf51f8dd` | `3359a372efb6` | yes |  |
| 0031 | drm/nouveau: fix autosuspend cleanup during teardown | 6.18.y `9132215d2c90` | `fefd9480ec36` | yes |  |
| 0032 | drm/nouveau: Fix bridge reference leak in nv1a_ram_new() | 6.18.y `6d497216c10a` | `67b4411538c8` | yes |  |
| 0033 | drm/nouveau: fix double-free in nvif_vmm_dtor | 6.18.y `109a8d2d5b7d` | `97077ac87afe` | yes |  |
| 0034 | drm/nouveau: Fix gem reference leak in validate_init() | 6.18.y `030e93fc91d5` | `5ea72f7b7139` | yes |  |
| 0035 | drm/nouveau: Fix runtime PM leak in nouveau_connector_detect() | 6.18.y `59aa1f8c9594` | `1e04611d3735` | yes |  |
| 0036 | drm/nouveau: RCU-free the scheduler-containing nouveau_sched | 6.18.y `35151e9a8274` | `f7eae6d8d768` | yes |  |
| 0037 | drm/nouveau: don't bump pin count on failed re-pin in nouveau_bo_pin_locked() | 6.18.y `19f5a5839b30` | `6a6870d3077f` | yes |  |
| 0038 | drm/nouveau/gsp/r570: Add support for INTERNAL_GCX_ENTRY_PREREQUISITE | mainline | `cb4c7603678c` | yes |  |
| 0039 | drm/nouveau/gsp/r535: Add support for MEMSYS_GET_STATIC_CONFIG | mainline | `3217000f0b7e` | yes |  |
| 0040 | drm/nouveau/gsp/r570: Add comp mode workaround from issue #3172217 | mainline | `c7ef611a43bb` | yes |  |
| 0041 | drm/nouveau/gsp/r570: Start saving comptag backing stores | mainline | `82f4394bbe22` | yes |  |
| 0042 | drm/nouveau/gsp/r570: Enable Gcoff in fbsr again | mainline | `adb87c20081e` | yes |  |
| 0043 | nouveau: check gsp->rm as well as gsp pointer before gcx ready | mainline | `4d0e27041185` | yes |  |
| 0044 | ANYBOOK: nouveau: leave Tegra-only IOMMU and regulator calls out of the x86 build | OpenBook | - | - | - |

Not taken, with the reason:

- 6.18.y `0589706ace3b` (drm/client: remove holds_console_lock): changes the built-in DRM client API, i.e. vmlinux.
- v7.3 features and refactors (uvmm large pages, compression kinds, ZCULL ioctl, dmem cgroups, GA100 support, kmalloc_obj conversions, …): none is a runtime-PM, suspend or GB20x display fix.
- v7.3 `6ccf996a0dec` (Turing CE workaround object) and `cac96c8d93fa` (double drm_sched_entity_fini): userspace channel paths; no userspace channel exists in headless use. For ANAL-240/243.
- v7.3 `d008141ed4ce`, `6763a0aea6d6` (SPT/LPT races): depend on the v7.0 PTE-tracker rewrite; for NVK (ANAL-240).
- v7.3 `310326bb7df4` (quiesce on shutdown): 6.18 nouveau has no shutdown hook, so the WARN it fixes cannot occur.
- 7.4 merge window (after v7.3): `db684a65df75` (probe ENOMEM cleanup), `827eb9328eae` (fence uevent work), `f60849975a88`/`843bc34db94b` (DP IRQ), `38125d38d850`, `f569473c1393`: robustness fixes, candidates for the next revision.
- Churro `nouveau-dsc-off.patch`: only matters when nouveau drives the panel (Ultimate mode, ANAL-244). Churro `nouveau-hybrid-guard.patch`: refuses to bind next to any other GPU, so never on the G14.
- drm_gpuvm 6.18.y fixes `76a4c3af3253`, `41a60487b5b0`: drm_gpuvm.ko is built from common, which this change leaves as is; nothing uses GPU VM_BIND until NVK (ANAL-240).
