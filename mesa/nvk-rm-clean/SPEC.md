# Clean-room specification: the work items

This tree is NVK on NVIDIA's open kernel driver, the RM backend, for Android x86_64. The places that had no public
source were removed before this tree was made. Each gap is now a numbered item.

Implement every **S** item and **H** item, and confirm every **V** item. Use only the public sources listed in
`README.md`. For each item, record in `PROVENANCE.md` which sources you used, by file and function. A value that no
public source gives must come from your own experiment on this tree, against the open kernel driver, and the method and
result must be recorded. Run `scripts/scan.py` before every commit; it must report 0 hits.

Target: NVIDIA open kernel modules **615.78.08** (OGKM tag `615.78.08`), Turing and later. The open modules support
nothing older. Mesa **26.2.5**.

## S items: implement (the backend fails until they are done)

**S1. `backend/src/gpu.rs` `bind_zcull`.** The ZCULL context-switch storage of a graphics channel.
- **Need:**
  - Every channel with the 3D engine must have its GR context's ZCULL state saved and restored correctly across
    context switches.
  - Return the GPU mapping of any buffer you allocate. The TSG keeps it (`Tsg::keep_zcull`) and frees it only after
    the TSG object, which the field order already does.
  - `Queue::create` calls this after the engine objects. Confirm the order from the sources.
  - Any failure fails channel creation.
- **Sources:**
  - `ctrl0080fifo.h`: `NV0080_CTRL_CMD_FIFO_GET_ENGINE_CONTEXT_PROPERTIES`, engine IDs.
  - `ctrl2080gr.h`: `NV2080_CTRL_CMD_GR_CTXSW_ZCULL_BIND`. Its comment documents the modes.
  - OGKM `kernel_graphics_context.c` and `kernel_fifo_ctrl.c`.
  - The `ctxsw_size` and `ctxsw_align` fields of nouveau's uAPI, in Mesa `include/drm-uapi/nouveau_drm.h`.

**S2. `backend/src/mesa.rs` `query_zcull`.** The ZCULL region geometry for NVK's ZCULL path (`abi::ZcullInfo`), and the
size and alignment of the context-switch storage (`abi::EngineContextProperties`).
- **Need:**
  - Query once per device at open.
  - Refuse values that Mesa's layout code cannot handle (zero divisors or alignments, or more than nil's maximum number
    of subregions), with the reason. The caller then leaves ZCULL off; it already handles an error that way.
- **Sources:**
  - `ctrl2080gr.h`: `NV2080_CTRL_CMD_GR_GET_ZCULL_INFO`.
  - `drm_nouveau_get_zcull_info` in Mesa `include/drm-uapi/nouveau_drm.h`.
  - Mesa `src/nouveau/nil` ZCULL code (limits).
  - `ctrl0080fifo.h`.

**S3. `backend/src/gpu.rs` `context_share`.** From Volta on: the context-share object of subcontext 0 of a new TSG, for
the queue's address space.
- **Need:** the TSG keeps it for its lifetime (`keep_veid0_share`), and the channel is allocated with it.
- **Sources:**
  - `nvos.h`: `NV_CTXSHARE_ALLOCATION_PARAMETERS` and its flags.
  - `cl9067.h` (`FERMI_CONTEXT_SHARE_A`).
  - OGKM `kernel_ctxshare.c`, `kernel_channel.c` and `kernel_channel_group_api.c`.

**S4. `backend/src/rm.rs` `compressible_request`.** The NVOS32 `(attr, attr2, format)` of a compressible device-local
allocation of a given size. The memory is never CPU-mapped or exported.
- **Need:**
  - RM decides whether compression is granted. `compression_granted` reads the answer.
  - The size is a 64 KiB multiple.
  - Choose physicality, page size, compression and caching from the documented semantics. Any size-dependent choice
    needs its own measurement.
- **Sources:** `nvos.h` (`NVOS32_ATTR_*`, `NVOS32_ATTR2_*`); OGKM `heap.c` and `mem_mgr`.

**S5. Mesa: which images and allocations use RM-granted compression.**
- **Where:**
  - `src/nouveau/vulkan/nvk_image.c`: `rm_compress`, currently `false`.
  - `src/nouveau/vulkan/nvkmd/rm/nvkmd_rm.c`: `rm_mem_alloc`, the `NV_RM_PLACEMENT_VRAM_COMPRESSIBLE` choice, currently
    never made.

  Both are in `mesa/patches/nvk-rm-clean/0002-*`. Change them with a new patch on top.
- **Need:** a policy from Vulkan semantics and NIL's compression support. Never compress images or memory that can be
  shared outside the device, mapped by the CPU, or used sparsely. Leaving compression off is acceptable for the first
  delivery; say so if you do.
- **Sources:** Mesa NVK and NIL (`nvk_image_can_compress`, NIL compressed kinds); the Vulkan specification.

## H items: hardening, written from the problem statement alone

**H1. Shader heap reuse.** NVK returns a destroyed shader's heap range for reuse. The GPU's instruction and
program-header caches may still hold the old bytes when a new program is placed there.
- **Need:** make sure a recycled range never runs stale cached bytes.
- **Sources:**
  - The class headers (`INVALIDATE_SHADER_CACHES` and `_NO_WFI` fields).
  - Mesa `nvc0_program.c`, which invalidates after uploads.
  - NVK's `nvk_heap.c`, `nvk_shader.c` and `nvk_queue.c`.

**H2. Program prefetch range (Ampere B and later).** NVK packs programs at 0x80 alignment and sets
`SET_PIPELINE_PROGRAM_PREFETCH` in 256-byte blocks from the program address.
- **Need:** make sure the prefetch never reaches past the program's own range.
- **Sources:** NVK `nvk_shader.c`; the class headers.

## V items: confirm against public sources, then record (change the code only if a source disagrees)

| Item | What to confirm |
|---|---|
| **V1** | The pre-Volta branches (no context share; the USERD-write kick) cannot be reached on the open modules. Keep or remove them, with the reason. Source: OGKM README (supported GPUs); `kernel_channel.c` legacy mode |
| **V2** | Doorbell ordering and the Hopper-and-later BAR1 usermode mapping (`gpu.rs` `kick`, `rm.rs` `map_usermode_class`). Sources: OGKM `src/common/unix/nvidia-push` (`nvidia-push-init.c`); `nv_gpu_ops.c`; `usermode_api.c`; UVM `uvm_*_host.c` |
| **V3** | Channels may be freed without a schedule-off or preempt first (`gpu.rs` `Drop for Queue`, `stop_submissions`; `mesa.rs` device teardown, context quiesce). Sources: `nv_gpu_ops.c` `nvGpuOpsChannelDestroy`; the RM channel free path |
| **V4** | Big-page mapping request (`gpu.rs` `mapping_plan_paged`). Source: `nvos.h` NVOS46 flags |
| **V5** | Exportable block-linear allocations request exactly the generic kind, uncompressed (`rm.rs` `allocate_block_linear`). Sources: `nvos.h` NVOS32 FORMAT; nvidia-drm PRIME import in OGKM `kernel-open` |

## Out of scope for this delivery

- A compute-only queue family. Contexts are refused if they would join another context's channel group, or have a
  compute engine without 3D.
- Performance tuning of barriers and compute launches.

Upstream behaviour stands for both. They are later, separate work.

## Done when

- `scripts/scan.py` reports 0 hits.
- `scripts/test-backend.sh` passes.
- `scripts/build-clean.sh` builds.
- Every S, H and V item has a provenance entry.
- `PROVENANCE.md` carries your statement that you read nothing on the excluded list in `README.md`.
- Hardware testing is a separate step. The results come back as test names, messages and kernel-log lines only.
