# Photos-triggered SurfaceFlinger restarts (ANAL-210, 2026-10-19)

The owner reported the boot animation followed by the lock screen when opening
Google Photos after signing into microG. The installed G14 ran `20261019.quire9`
(tree `17581de`), with Photos 7.96.0.996044120, x86_64, and microG 0.3.17.252432.

## Diagnosis

Three SurfaceFlinger SIGABRTs at 15:43:07, 15:43:39 and 15:45:43 UTC have the
same failure: `GaneshBackendTexture` cannot import a 384×640 buffer with format
842094169 (`0x32315659`, YV12). See `surfaceflinger-crashes.txt`, which contains
only selected crash metadata and stack frames. Raw logs, memory dumps, account
details and the owner's pictures are not committed.

These were Android display/framework restarts within the same kernel boot.
At 15:53 UTC the kernel uptime was 1,917 seconds, spanning all three crashes;
the boot reason remained `reboot,ota`. Free RAM was about 25 GiB at that later
check (not a measurement at the exact crash instants).

RADV's `vk_format_from_android()` did not recognize YV12. Its generic fallback
returned `VK_FORMAT_UNDEFINED`, giving ANGLE an unusable buffer format.
`ahb-import-check.c` reproduces the failed EGLImage import on the G14 without
Photos, microG calls, a window, or a SurfaceFlinger restart. RGB and flexible
YUV420 controls succeed on the original driver; YV12 returns `EGL_BAD_PARAMETER`
(0x300c). Thus microG sign-in exposed an independent graphics defect.

## Correction and hardware test

Mesa patch `0005` maps YV12 to `VK_FORMAT_G8_B8_R8_3PLANE_420_UNORM`.
Mesa's existing `vk_android_get_ahb_layout()` path swaps the physical V/U planes
into Vulkan's U/V order and uses the allocator's strides and offsets.

The driver was built from a private copy of Mesa 26.2.5 plus OpenBook's existing
four patches. `gfx-nsbind` loaded the correction only inside the test process's
mount namespace. No global driver replacement or desktop restart was used.

| Test | Original driver | Patched driver |
|---|---|---|
| RGBA8888, 384×640 | Import and colour readback pass | Pass |
| YV12, 384×640 | EGL_BAD_PARAMETER | Import and colour readback pass |
| Flexible YUV420, 384×640 | Import and colour readback pass | Pass |
| All three formats at 4×4, 64×64, 640×360, 1920×1080 | Not run | 12/12 pass |

The test writes synthetic colour quadrants using `AHardwareBuffer_lockPlanes`,
imports them through the system ANGLE driver, samples an external texture into
an 8×8 offscreen framebuffer, and checks four RGB pixels against BT.601 full
range conversion (tolerance 4/255). This checks plane order and padded strides,
not merely whether allocation succeeds. The smallest test is 4×4 because
4:2:0 needs at least two chroma columns to represent both coloured halves.

Full Photos use after the system update remains to be checked by the owner.
Synthetic frame tests do not establish complete Photos/microG compatibility.

## Source references (checked 2026-10-19)

- [AOSP GaneshBackendTexture](https://android.googlesource.com/platform/frameworks/native/+/d09a587244661602d9a56b9786c1b28fd6861a3a/libs/renderengine/skia/compat/GaneshBackendTexture.cpp): fatal path after an invalid imported texture; also inspected in the local Android 17 source matching the build.
- [Mesa 26.2.5 RADV Android integration](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-26.2.5/src/amd/vulkan/radv_android.c) and [shared Android buffer layout](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-26.2.5/src/vulkan/runtime/vk_android.c): inspected in the local pinned source `ddaf85e353442d9d7f192fdcf1823e652e3f2ee3` plus patches 0001–0004.

## Update

Integration tree `d3e04fd` is the installed tree `17581de` plus Mesa patch 0005.
Build number: `20261019.photos1`. Update rehearsal and staging results are
recorded below when complete.
