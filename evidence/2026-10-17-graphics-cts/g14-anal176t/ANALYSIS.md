# G14 graphics check, first run: analysis (ANAL-177)

Source: the owner's stick `openbook-live-20261017-anal176t` with the add-on `openbook-gfxcheck-20261017` (`dc8b8b9`),
copied read-only to the build host by ANAL-178 (`<data dir>/installer/g14/stick-20261017T154112Z/live-002/`). This
folder holds the redacted copy (MAC addresses, USB serials and network names masked by `live-report.py --redact`):
`live-002/` (the boot's report, summary, logs) and `live-002/addon-gfx/` (the graphics results; `gfx-report.md` is the
summary). The raw `addon-gfx-out.tar` is not committed.

## Timeline (kernel uptime, from the `openbook-gfx:` markers in dmesg)

| Part | Start | End | Seconds | amdgpu fault/reset lines |
|---|---|---|---|---|
| vk (RADV 1.1, shipped) | 128.6 | 399.0 | 270 | 5 (one hang, one full reset) |
| vk14 (RADV 1.4) | 399.0 | 621.0 | 222 | 0 |
| gles-angle | 621.0 | 655.5 | 35 | 0 |
| gles-mesa | 655.6 | 688.8 | 33 | 0 |
| egl (app) | 688.8 | 892.8 | 204 | 0 |
| angle (end2end app) | 892.8 | 962.5 | 66 | 0 |

boot_completed at 28.2 s; the add-on started at 128 s (90 s settle plus unpacking 2,060 files, all checksums OK);
power-off after the final capture at 988.7 s.

## The GPU hang during `vk`

Kernel log (redacted copy, `live-002/dmesg.txt.gz`; ring-assignment lines left out):

```
[  166.469048] amdgpu 0000:65:00.0: amdgpu: Dumping IP State
[  166.471251] amdgpu 0000:65:00.0: amdgpu: Dumping IP State Completed
[  166.471341] amdgpu 0000:65:00.0: amdgpu: [drm] AMDGPU device coredump file has been created
[  166.471343] amdgpu 0000:65:00.0: amdgpu: [drm] Check your /sys/class/drm/card0/device/devcoredump/data
[  166.471345] amdgpu 0000:65:00.0: amdgpu: ring gfx_0.0.0 timeout, signaled seq=41352, emitted seq=41355
[  166.471348] amdgpu 0000:65:00.0: amdgpu:  Process deqp-binary64 pid 6293 thread deqp-binary64 pid 6293
[  166.471350] amdgpu 0000:65:00.0: amdgpu: Starting gfx_0.0.0 ring reset
[  168.475180] amdgpu 0000:65:00.0: amdgpu: MES failed to respond to msg=RESET
[  168.475184] amdgpu 0000:65:00.0: amdgpu: failed to reset legacy queue
[  168.475185] amdgpu 0000:65:00.0: amdgpu: reset via MES failed and try pipe reset -110
[  168.475187] amdgpu 0000:65:00.0: amdgpu: The CPFW hasn't support pipe reset yet.
[  168.475188] amdgpu 0000:65:00.0: amdgpu: Ring gfx_0.0.0 reset failed
[  168.475190] amdgpu 0000:65:00.0: amdgpu: GPU reset begin!. Source:  1
[  170.851828] amdgpu 0000:65:00.0: amdgpu: MES failed to respond to msg=REMOVE_QUEUE
[  170.851835] amdgpu 0000:65:00.0: amdgpu: failed to unmap legacy queue
[  171.173277] [drm:gfx_v11_0_hw_fini [amdgpu]] *ERROR* failed to halt cp gfx
[  171.175380] amdgpu 0000:65:00.0: amdgpu: MODE2 reset
[  171.199040] amdgpu 0000:65:00.0: amdgpu: GPU reset succeeded, trying to resume
[  171.199541] [drm] PCIE GART of 512M enabled (table at 0x000000801FB00000).
[  171.199587] amdgpu 0000:65:00.0: amdgpu: VRAM is lost due to GPU reset!
[  171.199591] amdgpu 0000:65:00.0: amdgpu: SMU is resuming...
[  171.202875] amdgpu 0000:65:00.0: amdgpu: SMU is resumed successfully!
[  171.214102] amdgpu 0000:65:00.0: amdgpu: [drm] DMUB hardware initialized: version=0x09005700
[  171.726571] amdgpu 0000:65:00.0: amdgpu: GPU reset(1) succeeded!
[  171.726577] amdgpu 0000:65:00.0: [drm] device wedged, but recovered through reset
```

- The guilty context belonged to a `deqp-binary64` process (pid 6293). All 12 dEQP processes in flight lost their
  device: 8 reported `VK_ERROR_DEVICE_LOST`, and 4 sat until deqp-runner's 60 s time-out. deqp-runner retried them and
  all 12 passed (they are 12 of the pass's 19 flakes). The logs do not say which of them hung the ring. The in-flight
  cases (first failing case per group, from `vk/run`'s group logs):
  - `ray_query.acceleration_structures.flags.sparse_binding_structures.compute_shader.gpu_built.triangles.different_instances_aop.nopadding.fasttrace_update_compaction_0_bothgeneric`
  - `ray_query.acceleration_structures.operations.traditional_structures.compute_shader.serialization.gpu_built.bottom_acceleration_structure.triangles`
  - `sparse_resources.image_rebind.cube.rg8i.256_256_1`
  - `texture.mipmap.3d.image_view_min_lod.base_level.nearest_nearest`
  - `renderpasses.dynamic_rendering.graphics_pipeline_library.suballocation.formats.d32_sfloat_s8_uint.input.clear.dont_care.clear_stencil_read_only`
  - `draw.renderpass.instanced.draw_indirect_vk_primitive_topology_triangle_fan_attrib_divisor_20_multiview`
  - `synchronization.op.multi_queue.timeline_semaphore.write_ssbo_fragment_read_ubo_vertex.buffer_16384_concurrent_maintenance9`
  - `api.image_clearing.dedicated_allocation.clear_color_image.1d.optimal.remaining_array_layers.r5g5b5a1_unorm_pack16_200x1_clamp_input_multiple_subresourcerange`
  - timed out (60 s): `ray_query…sparse_binding_structures.fragment_shader…aabbs_aop…`, `subgroups.arithmetic.compute.subgroupinclusivemin_ivec2_requiredsubgroupsize`, `texture.compressed_3D.astc_10x8_srgb_block_3d_npot_mip1`, `texture.filtering.2d_array.combinations.nearest.linear.mirrored_repeat.mirrored_repeat`
- The same cases ran under 1.4 right afterwards with no hang. HYPOTHESIS: load-dependent (12 concurrent GPU clients);
  one run cannot tie it to either build.
- Per-queue recovery failed ("MES failed to respond to msg=RESET", "The CPFW hasn't support pipe reset yet"), so amdgpu
  reset the whole GPU (MODE2, VRAM lost). Android's framework did not survive the lost contexts (logcat, redacted copy):

```
10-17 15:27:00.080  1511  1756 F libc    : Fatal signal 6 (SIGABRT), code -1 (SI_QUEUE) in tid 1756 (RenderThread), pid 1511 (ndroid.systemui)
10-17 15:27:00.381  1001  1065 F libc    : Fatal signal 6 (SIGABRT), code -1 (SI_QUEUE) in tid 1065 (RenderEngine), pid 1001 (surfaceflinger)
```

  Init restarted zygote at 222 s (`sys.system_server.start_count` 3); the desktop came back (`live-002/screen-final.png`,
  taken at the end of the run) and every later part ran normally, the two apps included.
- Four `deqp-binary64` SIGSEGVs in the same pass are dEQP's own crashes, recorded as `Crash` by deqp-runner, not GPU
  faults. All four are calls through a null function pointer (frame #00 at pc 0):
  - two in `amber::Executor::Execute` (`ray_tracing_pipeline.amber.barycentrics` and its retry);
  - two in `vk::createRenderPass2` from `FragmentShadingRate::AttachmentRateInstance`
    (`fragment_shading_rate…transfer_queue_concurent…` and its retry), the Vulkan 1.2 entry point a 1.1 device does not
    provide.

  Both cases pass under 1.4.

## Comparisons

| Part | 610M pre-check (gfx1036) | G14 (gfx1150) | Note |
|---|---|---|---|
| vk, 1.1 | 43,248 pass / 57 fail / 1 crash | 43,222 / 8 / 2, 19 flakes | The 610M's 47 Amber failures came from the pre-check's HAL shim: on the G14, through Android's loader, all 26 sampled `graphicsfuzz` cases pass |
| vk14, 1.4 | 45,161 / 5 / 0 | 45,220 / 5 / 0 | Common: `info.device_extensions`, `opfma.fp64…denorm_flush`. 610M only: 3 shim artifacts. G14 only: the AHB case and 2 `copy_memory_indirect` harness failures (the 610M does not expose the extension) |
| gles-mesa | 13,621 / 0 / 0 | 13,621 / 0 / 0 | Identical |
| gles-angle | not runnable off the laptop | 13,099 / 0 / 0, 63 warnings | Warnings: all `dEQP-GLES31.functional.debug.negative_coverage.*` (ANGLE's error-message wording) |
| egl | Cuttlefish (gfxstream): 822 / 0 | 847 / 0 | |
| angle end2end | Cuttlefish (gfxstream): 1,802 / 7 fail | 1,814 / 2 fail | Cuttlefish's 7 `TextureBorderClamp*` failures pass on the G14 (gfxstream's); the G14's 2 are `MultisampledRenderToTextureWithAdvancedBlendTest` (ES 3.1) |

Mesa CI (26.2.5 `src/amd/ci/`): none of the G14's failures is listed in `radv-fails.txt`, `radv-navi31-fails.txt`,
`radeonsi-vangogh-fails.txt` or `angle-radv-stoney-fails.txt`. The RADV and radeonsi lists contain no case of the
Android mustpass (`radv-navi31-fails.txt`: 44 entries, `radeonsi-vangogh-fails.txt`: 410, none in the mustpass), so
they cannot confirm or contradict these runs. `angle-radv-stoney-fails.txt` lists 92 cases of our GLES subset as
failing for ANGLE on a GCN Stoney; the G14 passes all 92.

## Vulkan 1.1 or 1.4

1.4 passes 1,998 more cases, fails none that 1.1 passes, and had no crash, flake or GPU fault; 5 cases fail only under
1.1. Decision: ship 1.4 (`docs/graphics-amd.md`, "Vulkan 1.1 or 1.4").
