# Graphics run: pre-check, Radeon 610M (gfx1036)

Mesa CI expectations: `<data dir>/mesa/src/upstream/src/amd/ci` (RADV: raphael, radeonsi: mendocino, ANGLE: stoney).

| Part | Renderer | Cases | Pass | Fail | Crash | Timeout | Skip | Warn | Flake | Time | Mesa CI: our fails listed / new |
|---|---|---|---|---|---|---|---|---|---|---|---|
| vk | AMD Ryzen 9 7950X 16-Core Processor (RADV RAPHAEL_MENDOCINO) | 66226 | 43248 | 57 | 1 | 0 | 22917 | 0 | 3 | 116 s | 0 / 58 |
| vk14 | AMD Ryzen 9 7950X 16-Core Processor (RADV RAPHAEL_MENDOCINO) | 66226 | 45161 | 5 | 0 | 0 | 21055 | 0 | 5 | 96 s | 0 / 5 |
| gles-mesa | AMD Ryzen 9 7950X 16-Core Processor (radeonsi, raphael_mendo | 13671 | 13621 | 0 | 0 | 0 | 48 | 2 | 0 | 18 s | 0 / 0 |

## vk: failures by message

- 47 × Vulkan: Unable to load vkGetBufferDeviceAddress pointer at vktAmberTestCase.cpp:579
- 3 × linearTilingFeatures: has: VK_FORMAT_FEATURE_VIDEO_DECODE_OUTPUT_BIT_KHR|VK_FORMAT_FEATURE_VIDEO_ENCODE_INPUT_BIT_KHR
- 1 × Unknown extension: VK_ANDROID_native_buffer
- 1 × Fail
- 1 × Color image comparison failed; check log for more details
- 1 × Stencil image comparison failed; check log for more details
- 1 × Crash
- 1 × Extension VK_EXT_hdr_metadata is missing dependency
- 1 × Extension VK_EXT_headless_surface is missing dependency
- 1 × Output doesn't match with expected

Mesa CI (radv-fails.txt, radv-raphael-fails.txt) lists 0 failures among our cases; we pass 0 of them.

Not in Mesa CI's lists (58):

- `dEQP-VK.api.info.android.no_unknown_extensions`
- `dEQP-VK.api.info.format_properties.g10x6_b10x6r10x6_2plane_420_unorm_3pack16`
- `dEQP-VK.api.info.format_properties.g12x4_b12x4r12x4_2plane_420_unorm_3pack16`
- `dEQP-VK.api.info.format_properties.g8_b8r8_2plane_420_unorm`
- `dEQP-VK.api.version_check.entry_points`
- `dEQP-VK.compute.pipeline.basic.atomic_barrier_sum_small`
- `dEQP-VK.compute.pipeline.basic.branch_past_barrier`
- `dEQP-VK.compute.pipeline.zero_initialize_workgroup_memory.shared_memory_blocks.workgroup_size_2x8x8`
- `dEQP-VK.depth.bias_fs_clamp`
- `dEQP-VK.draw.dynamic_rendering.primary_cmd_buff.multi_draw.mosaic.indexed_mixed.max_draws.standard_stride.10_instances.tess_geom.multiview.offset_6_no_draw_id`
- `dEQP-VK.draw.dynamic_rendering.primary_cmd_buff.multi_draw.mosaic.indexed_packed.one_draw.stride_zero.10_instances.tess_geom.single_view.offset_6_no_draw_id`
- `dEQP-VK.draw.renderpass.output_location.array.r32g32b32a32-sfloat-mediump`
- `dEQP-VK.fragment_shading_rate.renderpass2.monolithic.attachment_rate.setup_with_copying_using_transfer_queue_concurent.r8_uint.rate_1x2_general_layout`
- `dEQP-VK.glsl.combined_operations.notxor`
- `dEQP-VK.graphicsfuzz.access-new-vector-inside-if-condition`
- `dEQP-VK.graphicsfuzz.always-discarding-function`
- `dEQP-VK.graphicsfuzz.cov-and-even-numbers-from-fragcoord`
- `dEQP-VK.graphicsfuzz.cov-array-cast-bool-float-div-by-zero-no-effect`
- `dEQP-VK.graphicsfuzz.cov-const-folding-bitfieldinsert-div-one`
- `dEQP-VK.graphicsfuzz.cov-dead-branch-func-return-arg`
- `dEQP-VK.graphicsfuzz.cov-do-while-loop-until-uniform-lt-itself`
- `dEQP-VK.graphicsfuzz.cov-folding-rules-redundant-mix`
- `dEQP-VK.graphicsfuzz.cov-function-index-array-redundant-clamps`
- `dEQP-VK.graphicsfuzz.cov-function-unpack-unorm-2x16-one`
- `dEQP-VK.graphicsfuzz.cov-global-loop-counter-findlsb-zero`
- `dEQP-VK.graphicsfuzz.cov-inst-combine-select-findlsb-uaddcarry`
- `dEQP-VK.graphicsfuzz.cov-int-initialize-from-multiple-large-arrays`
- `dEQP-VK.graphicsfuzz.cov-loop-function-call-vector-matrix-multiplication`
- `dEQP-VK.graphicsfuzz.cov-loop-with-two-integers`
- `dEQP-VK.graphicsfuzz.cov-max-clamp-same-minval`
- `dEQP-VK.graphicsfuzz.cov-min-vec2-transpose-mat2-identity`
- `dEQP-VK.graphicsfuzz.cov-nested-loops-global-counter-increment-single-element`
- `dEQP-VK.graphicsfuzz.cov-nested-loops-switch-case-fallthrough-increment-array-element`
- `dEQP-VK.graphicsfuzz.cov-simplify-component-uniform-idx`
- `dEQP-VK.graphicsfuzz.cov-transpose-multiply`
- `dEQP-VK.graphicsfuzz.cov-value-tracking-selection-dag-negation-clamp-loop`
- `dEQP-VK.graphicsfuzz.loop-call-discard`
- `dEQP-VK.graphicsfuzz.spv-access-chains`
- `dEQP-VK.graphicsfuzz.stable-colorgrid-modulo-injected-conditional-true`
- `dEQP-VK.graphicsfuzz.two-2-iteration-loops`

## vk14: failures by message

- 1 × Unknown extension: VK_ANDROID_native_buffer
- 1 × Fail
- 1 × Unknown extension VK_KHR_device_address_commands
- 1 × Extension VK_EXT_headless_surface is missing dependency
- 1 × Output doesn't match with expected

Mesa CI (radv-fails.txt, radv-raphael-fails.txt) lists 0 failures among our cases; we pass 0 of them.

Not in Mesa CI's lists (5):

- `dEQP-VK.api.info.android.no_unknown_extensions`
- `dEQP-VK.api.version_check.entry_points`
- `dEQP-VK.info.device_extensions`
- `dEQP-VK.info.instance_extensions`
- `dEQP-VK.spirv_assembly.instruction.compute.opfma.fp64.vec4.rte.denorm_flush.float_controls`

## Vulkan 1.1 (android-strict, shipped) vs 1.4 (non-strict)

- failing only with 1.1: 53; failing only with 1.4: 0
- passing only with 1.4: 1915; passing only with 1.1: 2
