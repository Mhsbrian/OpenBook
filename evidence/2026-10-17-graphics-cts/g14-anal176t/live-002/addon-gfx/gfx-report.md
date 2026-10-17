# Graphics run: live-002

Mesa CI expectations: `<data dir>/mesa/src/upstream/src/amd/ci` (RADV: navi31, radeonsi: vangogh, ANGLE: stoney).

| Part | Renderer | Cases | Pass | Fail | Crash | Timeout | Skip | Warn | Flake | Not run | Time | Mesa CI: our fails listed / new |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vk | AMD Radeon 890M Graphics (RADV STRIX1) | 66226 | 43222 | 8 | 2 | 0 | 22975 | 0 | 19 | 0 | 270 s | 0 / 10 |
| vk14 | AMD Radeon 890M Graphics (RADV STRIX1) | 66226 | 45220 | 5 | 0 | 0 | 21001 | 0 | 0 | 0 | 222 s | 0 / 5 |
| gles-angle | ANGLE (AMD, Vulkan 1.1.354 (AMD Radeon 890M Graphics (RADV S | 13671 | 13099 | 0 | 0 | 0 | 509 | 63 | 0 | 0 | 35 s | 0 / 0 |
| gles-mesa | AMD Radeon 890M Graphics (radeonsi, strix1, ACO, DRM 3.64, 6 | 13671 | 13621 | 0 | 0 | 0 | 48 | 2 | 0 | 0 | 33 s | 0 / 0 |
| egl |  | 1287 | 847 | 0 | 0 | 0 | 438 | 2 | 0 | 0 | 204 s |  |
| angle |  | 2364 | 1814 | 2 | 0 | 0 | 329 | 0 | 0 | 219 | 66 s |  |

## vk: failures by message

- 3 × linearTilingFeatures: has: VK_FORMAT_FEATURE_VIDEO_DECODE_OUTPUT_BIT_KHR|VK_FORMAT_FEATURE_VIDEO_ENCODE_INPUT_BIT_KHR
- 2 × Error opening file! at vktApiCopiesAndBlittingTests.cpp:21307
- 1 × Fail
- 1 × Crash
- 1 × Extension VK_VALVE_video_encode_rgb_conversion is missing dependency
- 1 × the process ended during this case
- 1 × Output doesn't match with expected

Mesa CI (radv-fails.txt, radv-navi31-fails.txt) lists 0 failures among our cases; we pass 0 of them.

Not in Mesa CI's lists (10):

- `dEQP-VK.api.copy_and_blit.copy_memory_indirect.size_12.offset_0.count_2.normal_stride.graphics`
- `dEQP-VK.api.copy_and_blit.copy_memory_indirect.size_12.offset_4.count_63.normal_stride.graphics`
- `dEQP-VK.api.info.format_properties.g10x6_b10x6r10x6_2plane_420_unorm_3pack16`
- `dEQP-VK.api.info.format_properties.g12x4_b12x4r12x4_2plane_420_unorm_3pack16`
- `dEQP-VK.api.info.format_properties.g8_b8r8_2plane_420_unorm`
- `dEQP-VK.draw.renderpass.ahb.triangle_list`
- `dEQP-VK.fragment_shading_rate.renderpass2.monolithic.attachment_rate.setup_with_copying_using_transfer_queue_concurent.r8_uint.rate_1x2_general_layout`
- `dEQP-VK.info.device_extensions`
- `dEQP-VK.ray_tracing_pipeline.amber.barycentrics`
- `dEQP-VK.spirv_assembly.instruction.compute.opfma.fp64.vec4.rte.denorm_flush.float_controls`

## vk14: failures by message

- 2 × Error opening file! at vktApiCopiesAndBlittingTests.cpp:21307
- 1 × Fail
- 1 × Unknown extension VK_KHR_device_address_commands
- 1 × Output doesn't match with expected

Mesa CI (radv-fails.txt, radv-navi31-fails.txt) lists 0 failures among our cases; we pass 0 of them.

Not in Mesa CI's lists (5):

- `dEQP-VK.api.copy_and_blit.copy_memory_indirect.size_12.offset_0.count_2.normal_stride.graphics`
- `dEQP-VK.api.copy_and_blit.copy_memory_indirect.size_12.offset_4.count_63.normal_stride.graphics`
- `dEQP-VK.draw.renderpass.ahb.triangle_list`
- `dEQP-VK.info.device_extensions`
- `dEQP-VK.spirv_assembly.instruction.compute.opfma.fp64.vec4.rte.denorm_flush.float_controls`

## angle: failures by message

- 2 × Fail

Failing cases:

- `MultisampledRenderToTextureWithAdvancedBlendTest.ClearThenDraw/ES3_1_Vulkan`: Fail
- `MultisampledRenderToTextureWithAdvancedBlendTest.RenderbufferClearThenDraw/ES3_1_Vulkan`: Fail

## Vulkan 1.1 (android-strict, shipped) vs 1.4 (non-strict)

- failing only with 1.1: 5; failing only with 1.4: 0
- passing only with 1.4: 1998; passing only with 1.1: 0
