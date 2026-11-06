# Provenance

Every file here, where it came from, and what changed. The clean-side author fills in the last table, one row per
SPEC item.

## Origin of each part

| Path | Origin and licence | Changes for this tree |
|---|---|---|
| `backend/src/*.rs`, `backend/Cargo.lock`, `backend/shaders/pattern.*` | waydroid-nvidia `v0.2.0-rc12` (`788728d3d51c`), `nvidia-prolapse/driver-source/native`, MIT (`backend/LICENSE`). Includes four AnyBook commits: optional video feature, build-time driver version, completion-wait switch and its property | Only the library's files are kept. The places without a public source are removed, and stubs S1–S4 stand in for them. Contexts that would join another context's channel group are removed, as are those with a compute engine but no 3D. Comments that described another driver are removed. The verification notes V2–V5 are added. One test of a removed feature is gone |
| `backend/Cargo.toml` | same | Library only; the absent features stay off |
| `mesa/patches/upstream/*` | AnyBook (RADV fixes), MIT like Mesa | none |
| `mesa/patches/nvk/*` | AnyBook, ANAL-240 (NVK on Android, written for nouveau), MIT | none |
| `mesa/patches/nvk-rm-clean/0001`, `0003`–`0014` | waydroid-nvidia `v0.2.0-rc12` Mesa patches (each commit names its source file and SHA-256), MIT | none |
| `mesa/patches/nvk-rm-clean/0002` (rm-integration) | same, with its adapter files `nvkmd_rm.c`, `nvkmd_rm.h` and `nv_rm.h` | The image and memory compression policy is removed; stub S5 stands in for it. References to the removed queue-family interface are removed, as are comments that described another driver |
| `mesa/patches/nvk-rm-clean/0015`–`0023` | AnyBook (GoodBook `nvk-rm` 0033–0041), MIT | none |
| `mesa/patches/nvk-rm-clean/0024` | AnyBook, ANAL-330 (clean side), MIT like Mesa | New, item S5; see the clean-side entries below |
| `mesa/patches/nvk-rm-clean/0025` | AnyBook, ANAL-330 (clean side), MIT like Mesa | New, item H1; see the clean-side entries below |
| `mesa/patches/nvk-rm-clean/0026` | AnyBook, ANAL-330 (clean side), MIT like Mesa | New, item H2; see the clean-side entries below |
| `mesa/patches/nvk-rm-clean/0027` | AnyBook, ANAL-349 (clean side), MIT like Mesa | New: a fix for a failure found on the G14; see "Clean-side work (ANAL-349)" |
| `mesa/patches/nvk-rm-clean/0028` | AnyBook, ANAL-351 (clean side), MIT like Mesa | New: a performance fix for a cost measured on the G14; see "Clean-side work (ANAL-351)" |
| `mesa/patches/nvk-rm-clean/0029` | AnyBook, ANAL-353 (clean side), MIT like Mesa | New: thread-safe once-guards for the log lines of `0021` and `0027`; see "Clean-side work (ANAL-353)" |
| `scripts/mesa-android-build.sh` | AnyBook (GoodBook `main` `1601a3a2`) | Clean-room header. The host-test layer is optional at install |
| `scripts/scan.py`, `scripts/build-clean.sh`, `scripts/test-backend.sh`, `README.md`, `SPEC.md`, this file | AnyBook, new for ANAL-324 | — |

**Left out before this tree was made:**
- the original tree's Mesa patches 0003, 0012–0014, 0016–0025, 0029–0032 and 0050;
- its host-test layer;
- the backend's video decoder, tools and probes.

## Dirty-side preparation

- **Who:** the ANAL-324 run of 2026-11-01. It read the original private tree in order to remove its unsourced parts.
- **What it did:** it only deleted code and added the numbered stubs. The stubs return "not implemented" and contain no
  logic of their own.
- **Checks at handoff:**
  - `scripts/scan.py`: 0 hits.
  - `scripts/test-backend.sh`: 122 passed, 22 hardware tests ignored.
  - `scripts/build-clean.sh`: builds `vulkan.nouveau.so` and `libnv_bionic_native.so`; every backend symbol NVK needs
    resolves.

## Clean-side entries (one per SPEC item)

| Item | Public sources used (file, function or line) | Own experiments (method and result) | Author run (issue) | Date |
|---|---|---|---|---|
| S1 | OGKM 615.78.08: `ctrl0080fifo.h` NV0080_CTRL_CMD_FIFO_GET_ENGINE_CONTEXT_PROPERTIES (ENGINE_ID_GRAPHICS_ZCULL = 8; size and alignment semantics); `ctrl2080gr.h` NV2080_CTRL_CMD_GR_CTXSW_ZCULL_BIND (modes, the hClient rule), NV2080_CTRL_CTXSW_ZCULL_MODE_SEPARATE_BUFFER = 2; `g_device_nvoc.c`, `g_subdevice_nvoc.c` export flags (non-privileged, routed to physical RM); `kernel_fifo_ctrl.c` deviceCtrlCmdFifoGetEngineContextProperties_VF (alignment at least RM_PAGE_SIZE); `kernel_graphics_object.c` kgrobjConstruct (the first GR object allocates, maps and promotes the GR context, so the bind comes after the engine objects); `kernel_graphics_context.c` kgrctxUnmapCtxZcullBuffer, kgrctxFreeZcullBuffer (a client-mapped buffer: RM only drops its VA record); `kernel_ctxshare.c` and `g_kernel_channel_group_api_nvoc.h` (KernelChannelGroupApi::hKernelGraphicsContext: the GR context belongs to the channel group); `video_mem.c` (clients never get unscrubbed memory). Mesa 26.2.5: `include/drm-uapi/nouveau_drm.h` drm_nouveau_get_zcull_info ctxsw_size and ctxsw_align; `src/nouveau/vulkan/nvk_cmd_buffer.c` (ZCULL storage zeroed before use); `src/nouveau/drm-shim/nouveau_noop.c` (unit-test example values) | None. The VA bound (below 16 GiB) is this tree's own rule for internal mappings (`nv_rm.h` NV_RM_VA_START) | ANAL-330 | 2026-11-01 |
| S2 | OGKM 615.78.08: `ctrl2080gr.h` NV2080_CTRL_CMD_GR_GET_ZCULL_INFO (the ten fields and the region-size formula); `kernel_graphics.c` subdeviceCtrlCmdKGrGetZcullInfo; `g_subdevice_nvoc.c` export flags; `ctrl0080fifo.h` (the storage query shared with S1). Mesa 26.2.5: `include/drm-uapi/nouveau_drm.h` drm_nouveau_get_zcull_info; `src/nouveau/headers/nv_device_info.h` nv_zcull_device_info; `src/nouveau/winsys/nouveau_device.c` nouveau_ws_device_zcull_info (queried once at open, may fail); `src/nouveau/nil/zcull.rs` nil_zcull_new (divisors, alignments, MAX_SUBREGIONS = 16, 32-bit size) and REFERENCE_DEV_INFO (unit-test values); `src/nouveau/vulkan/nvk_cmd_draw.c`, `nvk_image.c` (the callers); class header `cl9297.h` (16-bit aliquot fields of SET_ZCULL_REGION_LOCATION and SET_ZCULL_SUBREGION_ALLOCATION) | None. For stage 2b: the ignored hardware test `mesa::hardware_tests::graphics_context_binds_zcull_storage` checks S1 to S3 on a real GPU | ANAL-330 | 2026-11-01 |
| S3 | OGKM 615.78.08: `nvos.h` NV_CTXSHARE_ALLOCATION_PARAMETERS (hVASpace; flags SUBCONTEXT SYNC = VEID 0 from Volta on; subctxId as output, field 30:0); `cl9067.h` FERMI_CONTEXT_SHARE_A; `kernel_ctxshare.c` kctxshareapiConstruct (a TSG must be the parent), kctxshareInitCommon (SYNC takes subcontext 0, subctxId written back); `kernel_channel.c` channel construct (hContextShare must have the channel's parent; client and legacy context shares cannot be mixed in one TSG); `kernel_channel_group_api.c` kchangrpapiSetLegacyMode (SUBCONTEXT_SYNC == 0); `alloc/alloc_channel.h` NVOS04_FLAGS_GROUP_CHANNEL_THREAD (not all classes at thread > 0) | None | ANAL-330 | 2026-11-01 |
| S4 | OGKM 615.78.08: `nvos.h` NVOS32_ATTR_* (DEPTH; COMPR, including 'If ATTR_COMPR is REQUIRED or ANY and ATTR_DEPTH is UNKNOWN, the allocation will fail'; FORMAT; PAGE_SIZE; LOCATION; PHYSICALITY; COHERENCY) and NVOS32_ATTR2_* (ZBC, GPU_CACHEABLE, ZBC_SKIP_ZBCREFCOUNT); `heap.c` (optionally compressed surfaces may be placed anywhere); `mem_mgr_gm107.c` (COMPR cleared when compression is unavailable or the kind is not compressible; 'compression should only be enabled on big/huge page mapping'); `kern_mem_sys.c` (COMPR_REQUIRED returned when compression resources were allocated); `mem_mgr_tu102.c` memmgrChooseKind_TU102 (IMAGE with COMPR ANY gives GENERIC_MEMORY_COMPRESSIBLE); `mem_mgr.c` (PAGE_SIZE BIG is the maximum big page size); `kern_gmmu.c` kgmmuFmtGet (64 KiB by default); `nv_gpu_ops.c` nvGpuOpsGetPteKind (32-bit element depth). Mesa 26.2.5: `hwref/turing/tu102/dev_mmu.h` (kind 0x08); `nil/image.rs` choose_pte_kind; `nvk_image.c` (linear images are never compressed) | None. No choice depends on the size: the request is identical for every 64 KiB multiple (unit test). Whether RM grants compression on the G14 is for stage 2b; nothing asks for it yet (S5) | ANAL-330 | 2026-11-01 |
| S5 | Mesa 26.2.5: `src/nouveau/vulkan/nvk_image.c` nvk_image_can_compress (what upstream never compresses); `nvk_device_memory.c` (compression only for not-shared dedicated allocations); `src/nouveau/nil/image.rs` tu102_choose_pte_kind, gb202_choose_pte_kind (depth/stencil kinds on Turing to Ada); this tree's `backend/src/gpu.rs` effective_kind (only the generic compressible kind falls back at bind) and `backend/src/mesa.rs` nv_rm_alloc (what the compressible placement refuses); the Vulkan specification (external memory handle types, sparse resources, host-visible memory). Patch `0024` | None. **Compression is off in this delivery**: no image and no allocation asks for it. A policy needs hardware testing first; the patch lists the conditions it must meet | ANAL-330 | 2026-11-01 |
| H1 | Class headers in Mesa (`cla097.h`, `cla0c0.h`, `clc597.h`, `clcd97.h`): INVALIDATE_SHADER_CACHES and INVALIDATE_SHADER_CACHES_NO_WFI, fields INSTRUCTION and CONSTANT. Mesa 26.2.5: `src/gallium/drivers/nouveau/nvc0/nvc0_program.c` nvc0_program_upload (invalidates after every upload); `src/nouveau/vulkan/nvk_heap.c` (freed ranges are reused; upload-queue ordering); `nvk_shader.c` nvk_shader_upload and the heap free on destroy; `nvk_queue.c` nvk_queue_submit_exec (upload-queue wait before client work), nvk_queue_init_context_state (classes bound at queue creation); `nvk_cmd_buffer.c` (existing _NO_WFI invalidations); `nvk_device.c` (the shader heap's 2048-byte overalloc: fetches reach past a program). The Vulkan specification (pipelines and shader objects are destroyed only after the work that uses them has completed). Patch `0025` | None. Written from the problem statement; the hardware run is stage 2b | ANAL-330 | 2026-11-01 |
| H2 | Mesa 26.2.5: `src/nouveau/vulkan/nvk_shader.c` nvk_shader_fill_push (SET_PIPELINE_PROGRAM_PREFETCH of DIV_ROUND_UP(size, 256) blocks, at most 127, from Ampere B on), nvk_shader_upload, nvk_shader_get_shader_size and nvk_shader_get_shader_alignment (programs packed at 0x80); `nvk_heap.c`. Class header `clc797.h` SET_PIPELINE_PROGRAM_PREFETCH (SIZE_IN_BLOCKS 6:0). Patch `0026` | None. The 256-byte start alignment makes the range the same whether the hardware counts blocks from the program address or from its enclosing block, so no undocumented behaviour is assumed | ANAL-330 | 2026-11-01 |
| V1 | OGKM 615.78.08: `README.md` ('can be used on any Turing or later GPU'); `kernel_channel.c` channel construct and `kernel_channel_group_api.c` kchangrpapiSetLegacyMode (without hContextShare RM puts the TSG in legacy mode with its own context shares). This tree's `backend/src/capabilities.rs` select: the pre-Volta contracts are chosen only for SM below 7.0, and SM 7.0 and later require a USERMODE class, so `modern` is always true. **Confirmed: unreachable on the open modules. Kept**, unchanged apart from two notes: removing them changes nothing on the target and would touch the submission code; a later cleanup may drop them | None | ANAL-330 | 2026-11-01 |
| V2 | OGKM 615.78.08: `src/common/unix/nvidia-push/src/nvidia-push.c` DoorbellKickoff (GP_PUT in USERD, then the doorbell) and `nvidia-push-init.c` (HOPPER_USERMODE_A with bBar1Mapping); `nv_gpu_ops.c` gpuDeviceMapUsermodeRegion (the same on Hopper and later); `usermode_api.c` (BAR1 doorbell page, but BAR0 without notice where BAR1 is disabled or all instance memory is in system memory); `kern_mem_sys.c` (BAR1 is disabled only on self-hosted Hopper); `gpu_registry.c` (all-sysmem instance memory only by registry override); `kernel-open/nvidia-uvm/uvm_turing_host.c` uvm_hal_turing_host_write_gpu_put (BAR1 read when GP_PUT is in system memory, wmb, doorbell); `clc36f.h` (GPPut at 0x8c), `clc361.h` (NOTIFY_CHANNEL_PENDING at 0x90), `nvos.h` NV_HOPPER_USERMODE_A_PARAMS, `g_gpu_class_list.c` (Blackwell also lists HOPPER_USERMODE_A). **Confirmed**; the Volta-to-Ada GP_PUT read-back is stricter than UVM. Not supported, now noted in `rm.rs`: BAR1-disabled platforms and the RmInstLoc all-sysmem override, where the doorbell would silently be the BAR0 page | None | ANAL-330 | 2026-11-01 |
| V3 | OGKM 615.78.08: `src/nvidia/src/kernel/rmapi/nv_gpu_ops.c` nvGpuOpsChannelDestroy (frees the engine object, then the channel, with no schedule-off, preempt or disable control); `kernel_channel.c` kchannelDestruct (the free goes to physical RM as NV_RM_RPC_FREE; the GR context is detached there). **Confirmed** for `gpu.rs` Drop for Queue and stop_submissions and for `mesa.rs` device teardown; the backend additionally waits for idle (bounded) before a free and frees the channel before its buffers, which UVM does not require | None | ANAL-330 | 2026-11-01 |
| V4 | OGKM 615.78.08: `nvos.h` NVOS46_FLAGS (ACCESS, PAGE_KIND 3:3, CACHE_SNOOP 4:4, PAGE_SIZE 11:8 with 4KB = 1 and BIG = 2, DMA_OFFSET_FIXED 15:15, PAGE_KIND_OVERRIDE 19:19) and its note 'BIG_PAGE = 64 KB on PASCAL'; `kern_gmmu.c` kgmmuFmtGet (the big page size defaults to 64 KiB). **Confirmed** for `gpu.rs` mapping_plan_paged: BIG only when the physical allocation has big pages and offset, length and fixed VA are all 64 KiB aligned, otherwise 4KB; RM chooses the kind unless an override is given | None | ANAL-330 | 2026-11-01 |
| V5 | OGKM 615.78.08: `nvos.h` NVOS32_ATTR_FORMAT and NVOS32_ATTR_COMPR (the granted kind returns in `format`); `src/nvidia-modeset/kapi/src/nvkms-kapi.c` ImportMemory (NV0000_CTRL_CMD_OS_UNIX_IMPORT_OBJECT_FROM_FD), its own block-linear allocations marked genericMemory, and genericPageKind 0x06 (NV_MMU_PTE_KIND_GENERIC_MEMORY) when the GPU supports it; `nvkms-headsurface.c` (maps imported memory with access flags only, so with the memory's own kind); `kernel-open/nvidia-drm/nvidia-drm-gem.c` nv_drm_gem_prime_import and `nvidia-drm-gem-dma-buf.c` (PRIME import). Mesa 26.2.5 `hwref/turing/tu102/dev_mmu.h` (kind 0x06). **Confirmed** for `rm.rs` allocate_block_linear: exactly the generic kind, FORMAT BLOCK_LINEAR, COMPR NONE, and a refusal of anything RM grants otherwise | None | ANAL-330 | 2026-11-01 |

Items without a public value: none. No item needed an own experiment; every value above is from a named public
source or derived from one (the 256-byte alignment of H2 removes the one open reading of the class header).

## Clean-side work (ANAL-330)

- **Who:** a fresh agent run on ANAL-330, 2026-11-01, in a new working directory whose per-directory memory was empty at
  the start.
- **What it read:** this tree; ANAL-330; ANAL-324's comment thread and its attached `ANAL-324-inventory.md` (SHA-256
  `d58fbd7a1e8f0b46c197205f79bb5c0ca9bde31c8b47d930fd3d14deba456271`); OGKM `615.78.08` from the local bare clone, with
  `git show` and `git grep` only; upstream Mesa at `mesa-26.2.5` (`~/anybook/mesa/src/upstream`); Linux 6.18 nouveau in
  the local GKI tree, searched for ZCULL facts (nothing taken from it). The Vulkan rules cited (external memory, sparse
  resources, destroying pipelines and shader objects only after their use completes) were applied from the
  specification as known, not re-read in this run.
- **Not opened:** ANAL-324's second attachment `ANAL-324-locations.tsv` (not named as allowed), X547's Haiku backend and
  open-gpu-doc (allowed, not needed), the GoodBook repository.
- **Disclosure:** directory listings of `~/anybook/mesa/src`, `~/anybook/mesa/build` and `~/anybook/kernel` showed the
  names of excluded trees and build folders. None was opened, searched or used. `scripts/build-clean.sh` only reads
  `src/upstream` and writes `src/nvk-rm-clean`, `build/nvk-rm-clean*` and `out/nvk-rm-clean`; meson fetched the
  public libdrm 2.4.133 tarball (MIT) from dri.freedesktop.org for its fallback subproject.
- **Checks at handoff** (code as of `e03034b`; the commit that adds this section changes only documentation and one
  doc comment):
  - `scripts/scan.py`: 0 hits.
  - `scripts/test-backend.sh`: 130 passed, 0 failed, 23 hardware tests ignored (one new:
    `mesa::hardware_tests::graphics_context_binds_zcull_storage`).
  - `scripts/build-clean.sh -clean`: builds; Mesa HEAD `f17ab6ff96a69ca9f0a7302f2ef6fcaa2283c07c` (mesa-26.2.5 plus 38
    patches); `vulkan.nouveau.so` SHA-256 `4c800a2c0a584f3191c20fccfa6b8b0cb65fca72258d7c8c1815275233659710`,
    `libnv_bionic_native.so` SHA-256 `0f6c604bff6452d4d60494b3d362ef8b398e5a6caa24e26920157a950512f84f`; all 29
    `nv_rm_*` symbols NVK imports resolve in the backend.
  - Not run here: anything on a GPU. Hardware testing is stage 2b.

**Author's statement** (ANAL-330, clean-side author, 2026-11-01): "I read nothing on the excluded list in README.md
while doing this work."

## Clean-side work (ANAL-349)

- **Who:** the ANAL-349 run of 2026-11-02. On the G14 in Hybrid, a Vulkan app whose instance is Vulkan 1.0 could not
  create a swapchain on the RTX: its window buffers came tiled from minigbm on amdgpu and NVK refused them.
- **What it read:** this tree, and OpenBook at PR #146 (the same patches); upstream Mesa `mesa-26.2.5` with this tree's
  patches applied (`src/vulkan/runtime/vk_android.c`, `vk_instance.c`, `vk_log.c`, `src/nouveau/vulkan/nvk_android.c`,
  `nvk_image.c`, `nvk_device_memory.c`, `nvkmd/rm/nvkmd_rm.c`, `src/nouveau/nil/image.rs`); this tree's
  `backend/src/mesa.rs` (`nv_rm_import`, `report`); AOSP 17 `frameworks/native/vulkan/libvulkan` (`swapchain.cpp`,
  `driver.cpp`, `driver_gen.cpp`) and `external/minigbm` (`amdgpu.c`, with OpenBook's two minigbm patches); Sascha
  Willems' Vulkan samples (MIT); ANAL-336's G14 logs and the G14's own log from this run.
- **Seen, not opened:** one `ls` printed the file names in `~/anybook/cleanroom/work-dirty`. One `grep -r` for the
  string `nvk-rm-clean` ran over `~/anybook/mesa/evidence`, which also holds other trees' evidence folders, and printed
  only lines of `evidence/nvk-rm-clean/versions.txt`. Listings of `~/anybook/mesa/{src,build,out}` showed the excluded
  trees' names. Nothing on the excluded list was otherwise opened, searched or used.
- **The change:** patch `0027`, from Mesa's `vk_android.c` and AOSP's `swapchain.cpp` (`getProducerUsage`,
  `convertGralloc1ToBufferUsage`); minigbm's `amdgpu.c` shows that a CPU usage gives a linear buffer.
- **Hardware:** the G14's RTX 5070 Ti Laptop, through OpenBook's per-app choice (ANAL-349's thread has the logs).

**Author's statement** (ANAL-349, clean-side author, 2026-11-02): "I read nothing on the excluded list in README.md
while doing this work, apart from the two incidents above, which showed file names and no file content."

## Clean-side work (ANAL-351)

- **Who:** the ANAL-351 run of 2026-11-02. On the G14 in Hybrid, ANGLE on the RTX ran a light GLES scene at 36 % of
  the Radeon's frame rate. Nearly all of each frame was `0021`'s copy of the VRAM swapchain image into the window
  buffer.
- **What it read:** this tree; upstream Mesa `mesa-26.2.5` with this tree's patches applied (`src/util/os_misc.c`,
  `src/nouveau/vulkan/nvk_android.c`, `nvk_cmd_copy.c`, `nvk_cmd_meta.c`, `nvk_cmd_draw.c`, `nvk_cmd_buffer.c`,
  `nvk_cmd_buffer.h`); glmark2 2023.01 (`src/canvas-android.cpp`, `src/scene-collection.h`: the test workload, nothing
  taken from it); OpenBook `main`; ANAL-336's and ANAL-349's threads and G14 evidence; the G14's own logs from this run;
  the G14's 2026-10-16 hardware inventory (`dmesg.txt`, `lspci-vvv.txt`) for its PCIe link.
- **Seen, not opened:** `ls ~/anybook/cleanroom` printed the name `work-dirty`, `ls ~/anybook/mesa/out` printed the
  excluded build folders' names, and `ls ~/anybook` printed the top-level names. The messages of `0020`–`0022` name
  GoodBook issues; those threads were not opened. Nothing on the excluded list was otherwise opened, searched or used.
- **The change:** patch `0028`, from Mesa's `nvk_cmd_meta.c` (`nvk_CmdCopyImage2` copies with a 3D draw on a graphics
  queue) and `nvk_cmd_copy.c` (`nvk_cmd_copy_image_ce`, also behind `nvk_linear_render_copy`): the copy of a VRAM
  swapchain image into its window buffer goes through the copy engine.
- **Hardware:** the G14's RTX 5070 Ti Laptop through OpenBook's per-app choice, with the debug properties
  `debug.mesa.nvk.anb.vram` and `debug.mesa.nvk.anb.fence` for the A/B (ANAL-351's thread has the logs).

**Author's statement** (ANAL-351, clean-side author, 2026-11-02): "I read nothing on the excluded list in README.md
while doing this work, apart from the directory listings above, which showed names and no file content."

## Clean-side work (ANAL-353)

- **Who:** the ANAL-353 run of 2026-11-06, the Checker's nonblocking follow-up on ANAL-349: the one-time log lines of
  `0021` and `0027` were guarded by a plain `static bool`, which two threads creating swapchains at once can both see
  clear.
- **What it read:** this tree (`README.md`, this file, `scripts/build-clean.sh`, patches `0021`, `0027` and `0028`);
  upstream Mesa `mesa-26.2.5` with this tree's patches applied (`src/nouveau/vulkan/nvk_android.c`,
  `src/vulkan/runtime/vk_android.c`, `src/util/u_atomic.h`, `src/util/u_call_once.h`); OpenBook `main` (the NVK
  package, its provenance files and build scripts, `docs/nvk-openbook.md`); the ANAL-353 and ANAL-338 threads and the
  ANAL-345 issue text.
- **Seen, not opened:** `ls ~/anybook/cleanroom` printed the name `work-dirty`. Nothing on the excluded list was
  otherwise opened, searched or used.
- **The change:** patch `0029`, from Mesa's `u_atomic.h`: each flag is tested and set in one `p_atomic_xchg()`, so
  exactly one caller logs. No other behaviour changes.
- **Hardware:** the G14's RTX 5070 Ti Laptop through OpenBook's per-app choice, a Vulkan 1.0 app and an ANGLE app, as
  for ANAL-349 (ANAL-353's thread has the logs).

**Author's statement** (ANAL-353, clean-side author, 2026-11-06): "I read nothing on the excluded list in README.md
while doing this work, apart from the directory listing above, which showed a name and no file content."

## In OpenBook (ANAL-327)

OpenBook carries this tree's commit `77608ebf9b1519140756494dc5b4d71f04761a29`: ANAL-330's clean-side tree as ANAL-326
tested it (stage 2b, commit `5f5c3d64`), plus ANAL-349's patch `0027`, ANAL-351's patch `0028` and ANAL-353's patch
`0029`, each tested on the G14 by its run. The backend and
these documents are in `mesa/nvk-rm-clean/`, the patches in `mesa/patches/`. The clean-room build scripts are replaced
by the `nvk-rm-clean` tree of `scripts/mesa-android-build.sh`. Its bytes are in `device/anybook/common/nvk/tested-bytes.txt`
(`vulkan.nouveau.so` `7bb60cfe…`; `libnv_bionic_native.so` `0f6c604b…`, `libdrm.so` `ccf9766c…` and `libelf_mesa.so`
`5f491b5d…` are unchanged). Everything above this section is the commit's `PROVENANCE.md`, unchanged.

### Every file from the commit

The blob is the commit's git blob; `scripts/nvk-provenance-check.sh` checks it (`exact`: the whole file; `prefix`:
the commit's file, then this section).

| OpenBook path | Blob | Origin |
|---|---|---|
| `mesa/nvk-rm-clean/PROVENANCE.md` | `f5bf3c54b665` (prefix:21965) | AnyBook, ANAL-324 (the clean-room tree's own) |
| `mesa/nvk-rm-clean/SPEC.md` | `1160cd019d5c` (exact) | AnyBook, ANAL-324 (the clean-room tree's own) |
| `mesa/nvk-rm-clean/backend/Cargo.lock` | `2418f9cba3f4` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/Cargo.toml` | `f19b89037563` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); library only |
| `mesa/nvk-rm-clean/backend/LICENSE` | `cd999c224321` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); library only |
| `mesa/nvk-rm-clean/backend/shaders/pattern.comp` | `7fdbf5e9d0b4` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/shaders/pattern.spv` | `176c627120d5` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/abi.rs` | `e6c96fbca358` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/backend.rs` | `ccd09c254192` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/capabilities.rs` | `30dd8a604919` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/capture.rs` | `502a81eb08c9` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/compat.rs` | `946614b52449` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/compat_data.rs` | `833d4a44e6ba` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/compiler.rs` | `261fba57abed` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/compute.rs` | `e3e74dc817f9` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/cpu_map_cache.rs` | `f019d900f5dc` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/diag.rs` | `a8aa6a31750c` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/events.rs` | `f33eb3abe882` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/external.rs` | `66d668045871` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/fences.rs` | `d5e29d7092f0` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/gpu.rs` | `b5c696835a1e` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/host_packet_tests.rs` | `7648e0856498` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/lib.rs` | `d641ff4d9c7d` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/mesa.rs` | `ff14b789b52a` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/mesa_hardware_tests.rs` | `fceeeae727e5` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/mesa_reclaim_tests.rs` | `091b591f28dd` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/platform.rs` | `df03809c67aa` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/reactor.rs` | `8d5b20b88728` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/reclaim.rs` | `25c364276267` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/rm.rs` | `27012e0b3af8` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/slots.rs` | `b77c1644bde9` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/sync_memory.rs` | `f632798c325d` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/syncobj.rs` | `44a4fef299b6` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/waiters.rs` | `d0dbb7c7644f` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/nvk-rm-clean/backend/src/watcher.rs` | `3e85a84bb3eb` (exact) | waydroid-nvidia v0.2.0-rc12 (MIT); cited places removed, S1–S4 and V2–V5 by ANAL-330 (clean side) |
| `mesa/patches/nvk-rm-clean/0001-waydroid-nvidia-build-compat.patch` | `91dbecd97574` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0002-waydroid-nvidia-rm-integration.patch` | `0e97bfdd3b74` (exact) | waydroid-nvidia (MIT), the RM integration; compression policy and queue-family interface removed, S5 stub |
| `mesa/patches/nvk-rm-clean/0003-waydroid-nvidia-nvk-upstream-ecfea8d9-ycbcr-modifier.patch` | `9a250fb102ac` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0004-waydroid-nvidia-nvk-upstream-bfb90f05-memory-plane-a.patch` | `03aa101b372b` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0005-waydroid-nvidia-nvk-explicit-plane-layouts.patch` | `5bb0f4c5b0e6` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0006-waydroid-nvidia-nvk-angle-nan-preserve-min-max.patch` | `b30492fe7a04` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0007-waydroid-nvidia-mesa-disk-cache-create-with-path.patch` | `82cf6c24d784` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0008-waydroid-nvidia-mesa-disk-cache-keep-file-backend.patch` | `b4d0b3eda0ad` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0009-waydroid-nvidia-mesa-disk-cache-evict-invalid-item.patch` | `a868f930f1c9` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0010-waydroid-nvidia-nvk-android-app-disk-cache.patch` | `3bfb5a4bfd15` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0011-waydroid-nvidia-nvk-3d-view-of-2d-image.patch` | `cd98b1b71388` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0012-waydroid-nvidia-nak-blackwell-ldcx-uniform-reads.patch` | `a0d0fb48493b` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0013-waydroid-nvidia-nak-licm-convergent.patch` | `127959a241ad` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0014-waydroid-nvidia-nak-loop-continue-sync.patch` | `746b08742dd7` (exact) | waydroid-nvidia v0.2.0-rc12 Mesa patch (MIT), unchanged |
| `mesa/patches/nvk-rm-clean/0015-nvk-fall-back-to-nouveau-when-the-device-is-not-on-N.patch` | `47c0ce0c0a06` (exact) | AnyBook (GoodBook nvk-rm 0033–0041), MIT, unchanged |
| `mesa/patches/nvk-rm-clean/0016-nvk-android-export-the-loader-ICD-entry-points-next-.patch` | `6e857e45abed` (exact) | AnyBook (GoodBook nvk-rm 0033–0041), MIT, unchanged |
| `mesa/patches/nvk-rm-clean/0017-nvk-rm-give-capture-replay-addresses-a-heap-of-their.patch` | `472a471e8e26` (exact) | AnyBook (GoodBook nvk-rm 0033–0041), MIT, unchanged |
| `mesa/patches/nvk-rm-clean/0018-nak-reuse-a-block-s-copy-of-an-immediate-instead-of-.patch` | `8a39782dac4e` (exact) | AnyBook (GoodBook nvk-rm 0033–0041), MIT, unchanged |
| `mesa/patches/nvk-rm-clean/0019-nvk-android-ask-gralloc-for-linear-buffers-on-a-hybr.patch` | `081cccb72dc4` (exact) | AnyBook (GoodBook nvk-rm 0033–0041), MIT, unchanged |
| `mesa/patches/nvk-rm-clean/0020-nvk-android-give-window-buffers-a-release-fence-inst.patch` | `e12ae56f6402` (exact) | AnyBook (GoodBook nvk-rm 0033–0041), MIT, unchanged |
| `mesa/patches/nvk-rm-clean/0021-nvk-android-optionally-render-swapchain-images-in-VR.patch` | `6ba264a11e76` (exact) | AnyBook (GoodBook nvk-rm 0033–0041), MIT, unchanged |
| `mesa/patches/nvk-rm-clean/0022-nvk-android-render-swapchain-images-in-VRAM-by-defau.patch` | `58429f6cc3f6` (exact) | AnyBook (GoodBook nvk-rm 0033–0041), MIT, unchanged |
| `mesa/patches/nvk-rm-clean/0023-nvk-optionally-report-the-NVIDIA-kernel-driver-s-ver.patch` | `f41b7ba5165f` (exact) | AnyBook (GoodBook nvk-rm 0033–0041), MIT, unchanged |
| `mesa/patches/nvk-rm-clean/0024-nvk-rm-no-image-or-allocation-uses-RM-granted-compre.patch` | `0893e858b596` (exact) | ANAL-330 clean side, item S5 |
| `mesa/patches/nvk-rm-clean/0025-nvk-invalidate-shader-caches-before-running-newly-up.patch` | `5f61b25dad0e` (exact) | ANAL-330 clean side, item H1 |
| `mesa/patches/nvk-rm-clean/0026-nvk-keep-the-program-prefetch-inside-the-program-s-o.patch` | `9c8b18eb3e5c` (exact) | ANAL-330 clean side, item H2 |
| `mesa/patches/nvk-rm-clean/0027-nvk-android-ask-for-linear-window-buffers-on-the-leg.patch` | `6a953abd249f` (exact) | ANAL-349 clean side, a fix found on the G14 |
| `mesa/patches/nvk-rm-clean/0028-nvk-android-copy-VRAM-swapchain-images-to-the-window.patch` | `02a1eb7eda3a` (exact) | ANAL-351 clean side, a performance fix measured on the G14 |
| `mesa/patches/nvk-rm-clean/0029-nvk-android-log-the-one-time-swapchain-lines-once-ac.patch` | `36885a332dec` (exact) | ANAL-353 clean side, thread-safe once-guards for two log lines |
| `mesa/patches/nvk/0001-nvk-link-with-the-common-Vulkan-ICD-version-script.patch` | `ff29c1a4303c` (exact) | AnyBook, ANAL-240 (NVK on Android, for nouveau), MIT |
| `mesa/patches/nvk/0002-nvk-advertise-two-queues-in-the-graphics-queue-famil.patch` | `97c2b7e3b894` (exact) | AnyBook, ANAL-240 (NVK on Android, for nouveau), MIT |
| `mesa/patches/nvk/0003-nvk-split-the-image-layout-out-of-nvk_image_init.patch` | `df3927058dba` (exact) | AnyBook, ANAL-240 (NVK on Android, for nouveau), MIT |
| `mesa/patches/nvk/0004-nvk-android-free-the-memory-imported-for-a-native-bu.patch` | `ae3de75db937` (exact) | AnyBook, ANAL-240 (NVK on Android, for nouveau), MIT |
| `mesa/patches/nvk/0005-nvk-android-check-gralloc-buffer-layouts-before-usin.patch` | `4bf5f6fc50e7` (exact) | AnyBook, ANAL-240 (NVK on Android, for nouveau), MIT |
| `mesa/patches/nvk/0006-nvk-android-support-deferred-swapchain-image-binding.patch` | `ce2a0fb73de0` (exact) | AnyBook, ANAL-240 (NVK on Android, for nouveau), MIT |
| `mesa/patches/nvk/0007-nvk-android-implement-VK_ANDROID_external_memory_and.patch` | `383ffe808d7f` (exact) | AnyBook, ANAL-240 (NVK on Android, for nouveau), MIT |
| `mesa/patches/upstream/0001-radv-android-fail-image-creation-when-the-gralloc-st.patch` | `1c26d64607ad` (exact) | OpenBook's own RADV series (MIT like Mesa), the same blob as OpenBook's |
| `mesa/patches/upstream/0002-radv-android-fix-fd-leak-on-gralloc-memory-import-fa.patch` | `4e2b8bb3bd12` (exact) | OpenBook's own RADV series (MIT like Mesa), the same blob as OpenBook's |
| `mesa/patches/upstream/0003-radv-android-support-deferred-swapchain-image-bindin.patch` | `d46aa446cec3` (exact) | OpenBook's own RADV series (MIT like Mesa), the same blob as OpenBook's |
| `mesa/patches/upstream/0004-OPENBOOK-radv-android-lay-out-gralloc-buffers-withou.patch` | `bc039b2aab2f` (exact) | OpenBook's own RADV series (MIT like Mesa), the same blob as OpenBook's |
| `mesa/patches/upstream/0005-OPENBOOK-radv-android-recognize-YV12-hardware-buffers.patch` | `a78546594d3d` (exact) | OpenBook's own RADV series (MIT like Mesa), the same blob as OpenBook's |
| `mesa/nvk-rm-clean/scripts/scan.py` | `e4aecff87263` (exact) | AnyBook, ANAL-324 (the clean-room tree's own) |
| `mesa/nvk-rm-clean/scripts/test-backend.sh` | `c214bacd12a5` (exact) | AnyBook, ANAL-324 (the clean-room tree's own) |

### OpenBook's own files for NVIDIA app support (ANAL-327)

Written by the ANAL-327 run (2026-11-02), a clean-side run: it read this tree, public sources and OpenBook, and
nothing on ANAL-324's exclusion list. None of these files contains driver code from anywhere else.

| Path | What | Sources |
|---|---|---|
| `mesa/nvk-rm-clean/README.md`, `clean-commit.txt` | this directory's guide; the commit's file list | this tree |
| `scripts/mesa-android-build.sh` (`nvk-rm-clean` tree) | build the tree: the patches, `clc`, `rm`, NVK-only options, the install layout, as the clean-room build did | this tree's `scripts/mesa-android-build.sh` and `build-clean.sh` (AnyBook) |
| `scripts/nvk-provenance-check.sh` | the gate: `scan.py` on every NVIDIA app path, and the blob check | this tree's `scan.py` |
| `scripts/nvk-stage.sh`, `device/anybook/common/nvk/` | the OpenBook NVK package (`org.openbook.nvk`): the libraries' names, the manifest, the module | AOSP 17: `frameworks/base` `GraphicsEnvironment.java` (`chooseDriver`, `MATCH_SYSTEM_ONLY`, the build-time meta-data), `frameworks/native` `GraphicsEnv.cpp` (the driver namespace), `vulkan/libvulkan/driver.cpp` (`vulkan.<ro.hardware.vulkan>.so`), `opengl/libs/EGL/Loader.cpp` (`lib<API>_<ro.hardware.egl>.so`), `build/soong` `java/app.go` (embedded JNI libraries); `external/angle` `Android.bp` (ANGLE's own APK) |
| `aosp/patches/external/angle/0001-…` | ANGLE tells NVK apart from NVIDIA's closed-source driver | ANGLE at the AOSP 17 pin `1f4500d3`: `vk_renderer.cpp` (`IsMesaPanVK`, `IsRADV`, `initFeatures`); `vulkan_core.h` (`VK_DRIVER_ID_MESA_NVK`); Mesa 26.2.5 `nvk_device.c` (`vk_pipeline_cache`) |
| `device/anybook/common/pc/` (`init.openbook.rc`, `bin/openbook-pc-setup.sh`, `sepolicy/vendor/openbook_pc_setup.te`), `scripts/openbook-pc-setup-test.sh` | offer the package only when the image has it | OpenBook; the ANAL-331 finding (2026-11-02) |
| `device/anybook/common/gfx-mode/app/` | "NVIDIA GPU for apps" on/off (`updatable_driver_all_apps` 0 or 3) | OpenBook; AOSP 17 `GraphicsEnvironment.chooseDriverInternal` |
| `docs/nvk-openbook.md` | the feature's document | all of the above |

**Disclosure:** directory listings on the build host showed the names of excluded trees, build folders and logs
(under `~/anybook/mesa/{src,evidence}`, `~/anybook/logs`, `~/anybook/cleanroom`); none was opened. ANAL-326's evidence
folder, read for its test results, holds a seven-line diff of a GoodBook test-harness script (`harness.diff`, a
version line); nothing was taken from it.
