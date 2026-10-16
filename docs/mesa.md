# Mesa radeonsi + RADV for Android x86_64 (NDK, standalone)

ANAL-173, 2026-10-15. This covers Android x86_64 builds of Mesa's radeonsi (EGL / GLES 1–3.2) and RADV (Vulkan), made out-of-tree with the NDK. They are standalone vendor-partition drop-ins and the basis for later AOSP integration. Evidence is in `evidence/2026-10-15-mesa/`.

**State:** both trees build, link cleanly against the API 37 NDK sysroot, and **load and run their GPU-independent entry points on Android 17 x86_64** (the AOSP Desktop emulator under KVM).

**Update 2026-10-16 (ANAL-174, `docs/graphics-amd.md`):**
- The upstream tree is now built with GBM and a shared libelf. It is staged into the AnyBook image as vendor prebuilts (`device/anybook/common/graphics-amd`).
- The image's own copies ran on a real AMD GPU: the build host's Radeon 610M (RDNA2), in a container with the image's bionic and no Android framework (`evidence/2026-10-16-graphics-amd/hwtest/`).
  - RADV enumerates the GPU, creates a device, and a GPU `vkCmdFillBuffer` verifies.
  - radeonsi GLES 3.2 renders and reads back.
- Nothing has run on the G14's Radeon 890M yet.

## Rebuild

```bash
docker build -t anybook-mesa-android -f tools/Dockerfile.mesa-android tools/   # NDK r30 + meson, ~3.9 GB
scripts/mesa-android-build.sh                    # all steps, both trees; rerun after any timeout/failure
scripts/mesa-android-build.sh build -- ag        # or: one step, one tree
scripts/mesa-android-smoke.sh                    # load test on the AOSP Desktop emulator (needs m0-emulator.sh image)
```

- **Steps:** `fetch deps setup build install verify isa`. Each step is skipped when its output exists, and `ninja` resumes.
- **Trees:** `upstream` and `ag`.
- **Outputs (not committed):**
  - Sources: `~/anybook/mesa/src/{upstream,ag,deps/elfutils}`
  - Builds: `~/anybook/mesa/build/<tree>`
  - **Artifacts:** `~/anybook/mesa/out/<tree>/vendor/`
  - Raw evidence: `~/anybook/mesa/evidence/<tree>`
  - Logs: `~/anybook/logs/mesa/`
- **Cost on the 7950X (32 jobs):**
  - Full build without ccache: 22–32 s of ninja per tree (upstream 22 s clean rebuild, AG 32 s first build).
  - Disk: about 2 GB, plus the 3.9 GB image.
- **Env:** `STEP_TIMEOUT` (default 3000 s), `JOBS`, `API` (default 37), `CCACHE_DISABLE=1`.
  - `LIBELF=shared|static` (default `shared` since ANAL-174; see libelf below).
  - `ANDROID_STRICT=true|false` (default `true`). RADV reports Vulkan 1.1 on Android when true and 1.4 when false.
  - Changing either one re-runs `setup`: the build directory records its configuration in `anybook-config.txt`.
- **Into the AOSP tree:** `scripts/graphics-amd-stage-mesa.sh` copies `out/upstream/vendor` (without `libdrm.so`; the image uses AOSP's) to `vendor/anybook/mesa/` with a generated `Android.bp` and `PROVENANCE.txt` (ANAL-174).

## Pins

| What | Version | Source |
|---|---|---|
| Upstream Mesa | **26.2.5**, tag `mesa-26.2.5` = `ddaf85e3534…` (latest stable 26.x on 2026-10-15) | gitlab.freedesktop.org/mesa/mesa |
| Android-Generic Mesa | `26.0/main` = `b14bf42d23e…` (2026-09-30), Mesa **26.0.8** + 63 AG commits | github.com/Android-Generic/external_mesa |
| NDK | **r30 LTS**, 30.0.16248370, clang 21.0.0 (r574158c), SHA-1 checked; platforms 21–**37** | developer.android.com/ndk/downloads (checked 2026-10-15) |
| API level | **37** (`x86_64-linux-android37-clang`, `-Dplatform-sdk-version=37`) | Android 17 |
| libdrm | meson wrap: **2.4.133** (upstream) / **2.4.123** (AG), sha256-pinned in each tree's `subprojects/libdrm.wrap` | dri.freedesktop.org |
| libelf | elfutils **0.193** from AOSP `external/elfutils` tag `android-17.0.0_r1` = `219c3a36…` | android.googlesource.com |
| Build image | `ubuntu:24.04@sha256:534baea6…`, meson 1.12.1, mako 1.4.3, PyYAML 6.0.3, packaging 26.3, glslang 15.1.0 | `tools/Dockerfile.mesa-android` |

The Ubuntu apt packages (glslang, ninja, gcc) follow the 24.04 archive and are not version-pinned. They only run on the build host. A drift there would show up as different checksums.

## Configuration and why

Following https://docs.mesa3d.org/android.html. The cross file is generated at `~/anybook/mesa/build/android-x86_64-api37.ini`, with ccache and the NDK clang. The C++ flags come from Mesa's doc: `-fno-exceptions -fno-unwind-tables -fno-asynchronous-unwind-tables -static-libstdc++`.

```
-Dplatforms=android -Dplatform-sdk-version=37 -Dandroid-stub=true -Dandroid-libbacktrace=disabled -Dandroid-strict=$ANDROID_STRICT
-Dgallium-drivers=radeonsi -Dvulkan-drivers=amd -Dllvm=disabled -Damd-use-llvm=false
-Degl=enabled -Dgles1=enabled -Dgles2=enabled -Degl-lib-suffix=_mesa -Dgles-lib-suffix=_mesa
-Dgbm=enabled -Dglx=disabled -Dgallium-va=disabled -Dvideo-codecs= -Dallow-fallback-for=libdrm
-Dxmlconfig=disabled -Dexpat=disabled -Dzstd=disabled -Dvalgrind=disabled -Dlibunwind=disabled -Dlmsensors=disabled
--buildtype=release -Db_ndebug=true --prefix=/vendor --libdir=lib64 --datadir=etc
```

ANAL-174 changed three things here: `-Dgbm=enabled` (for minigbm's amdgpu backend), `--datadir=etc` (so `amdgpu.ids` lands where Soong can install it), and the `ANDROID_STRICT` variable. ANAL-173's evidence was built with `-Dgbm=disabled`, the default datadir and `LIBELF=static`.

- **LLVM: not needed.**
  - Mesa 26.x has `-Damd-use-llvm=false`, so radeonsi compiles every shader with ACO, as RADV already does (`meson.build:57,251`).
  - This avoids cross-building LLVM for bionic and statically linking it into each driver.
  - AG still carries "radeonsi: init use_aco properly when llvm is disabled" (16bfa001573).
- **libelf: required, and the NDK lacks it.**
  - radeonsi uses it for shader-binary loading (`ac_rtld.c`, `ac_rgp_elf_object_pack.c`). Upstream errors out with `Gallium driver radeonsi requires libelf` whenever GL/compute is enabled.
  - We build AOSP's own elfutils the way its `Android.bp` builds `libelf`, plus `libeu` (bionic fixups, `-include AndroidFixup.h`), minus zstd. The result is a 300 KB static `libelf.a`, located through a `.pc` file. AOSP-tree Mesa builds link the same library.
  - **Licensing:** elfutils libelf is LGPL-3.0-or-later (or GPL-2.0-or-later), statically linked into MIT Mesa.
    - Building locally is fine.
    - **Distributing binaries** (for example, Track A images) requires relinkable source or objects. We already have the full build script, and AOSP ships the same combination.
    - Alternatives:
      - Ship libelf as a shared `libelf.so`.
      - Use elftoolchain's BSD-2-Clause libelf. It covers Mesa's API (`elf_memory`, `elf_getscn`, `elf64_getshdr` and similar), but this is a **hypothesis**, untested.
    - Owner call: see Blocked in STATUS.
  - **Switch (ANAL-174):** `LIBELF=shared` (now the default) builds the same objects into `libelf_mesa.so`. It has its own SONAME so it can't clash with an AOSP `libelf.so`, and `libgallium_dri.so` and `vulkan.radv.so` load it dynamically. This is the recommended redistribution option. `LIBELF=static` restores the static link.
- **libdrm: shared, not static.**
  - With `-Dlibdrm:default_library=static`, the radeonsi link fails: `duplicate symbol: handle_table_remove` between libdrm_amdgpu's private `handle_table.c` and Gallium's `u_handle_table.c` (first attempt in `upstream/build.log.gz`).
  - So `libdrm.so` and `libdrm_amdgpu.so` ship next to the drivers. Mesa on Android already names them without version suffixes, as AOSP's `external/libdrm` does. Googlebook's own vendor `libdrm.so` uses the same SONAME.
  - Mesa 26.2 needs libdrm_amdgpu ≥ 2.4.133. Either ship ours or verify the vendor copy.
  - **In the image (ANAL-174):**
    - Our libdrm_amdgpu ships as **`libdrm_amdgpu_mesa.so`**. AOSP's `external/libdrm` 2.4.124 owns the `libdrm_amdgpu.so` name and install path, and two rules for one path break the build.
    - The libdrm core is AOSP's vendor `libdrm.so` 2.4.124. Every libdrm symbol Mesa 26.2.5 and libdrm_amdgpu 2.4.133 import is in it (checked with `nm`).
- **Android libraries.** `-Dandroid-stub=true` links against Mesa's build-time stubs for `libhardware`, `liblog`, `libnativewindow` and `libsync` (plus `libcutils` in AG). These exist on the device, not in the NDK. `verify` checks every symbol against the real NDK API-37 stubs; see below.
- **No driconf XML** (`xmlconfig` disabled, so the defaults are compiled in), no zstd (the disk cache uses zlib), no perfetto, no libbacktrace. AG enables xmlconfig on Android in-tree; that needs an expat build and is left for integration.

## Artifacts (vendor layout)

```
vendor/lib64/egl/libEGL_mesa.so        ro.hardware.egl=mesa
vendor/lib64/egl/libGLESv1_CM_mesa.so
vendor/lib64/egl/libGLESv2_mesa.so
vendor/lib64/libgallium_dri.so         radeonsi + ACO + NIR (Gallium megadriver, NEEDED by the EGL/GLES libs)
vendor/lib64/hw/vulkan.radv.so         ro.hardware.vulkan=radv (libvulkan_radeon.so, SONAME set to vulkan.radv.so)
vendor/lib64/libdrm.so, libdrm_amdgpu.so
vendor/share/libdrm/amdgpu.ids         marketing names; libdrm_amdgpu's compiled-in path
```

Since ANAL-174 the layout differs:
- `libdrm_amdgpu.so` is renamed `libdrm_amdgpu_mesa.so`.
- `amdgpu.ids` moved to `vendor/etc/libdrm/`.
- New files: `vendor/lib64/libgbm_mesa.so` (Mesa renames libgbm on Android ≥ 30), `vendor/lib64/gbm/dri_gbm.so` (GBM's DRI backend, at libgbm_mesa's compiled-in backends path) and `vendor/lib64/libelf_mesa.so`.
- Checksums are in `evidence/2026-10-16-graphics-amd/mesa/`.

Sizes (stripped) and checksums are in `<tree>/sizes.txt` and `<tree>/sha256sums.txt`.

| | upstream 26.2.5 | AG 26.0.8 |
|---|---|---|
| `libgallium_dri.so` | 24,835,136 | 23,826,768 |
| `vulkan.radv.so` | 18,681,465 | 17,252,001 |
| `libEGL_mesa.so` | 330,520 | 352,776 |
| GLESv1_CM / GLESv2 | 26,464 / 64,960 | 26,464 / 64,960 |
| libdrm / libdrm_amdgpu | 88,800 / 41,496 | 87,312 / 38,624 |
| **total** | **44.1 MB** | **41.6 MB** |

## Verification (`evidence/2026-10-15-mesa/<tree>/`)

- **NEEDED and symbol resolution against the API 37 sysroot** (`needed-check.txt`, `scripts/elf-needed-check.py`). Both trees: **OK, 0 unresolved.**
  - Every NEEDED entry is another artifact, an NDK library (`libc libm libdl liblog libnativewindow libsync libz`), or `libhardware.so`. AG adds `libcutils.so`.
  - Undefined symbols resolve against the NDK API-37 stubs, except these **LLNDK or platform-only** APIs that vendor code may use but apps may not:
    - `ANativeWindow_{dequeue,queue,cancel}Buffer`, `_query`, `_setUsage`, `_setSwapInterval`, `_setSharedBufferMode`, `ANativeWindowBuffer_getHardwareBuffer` (EGL)
    - `AHardwareBuffer_getNativeHandle` (RADV)
    - `sync_wait`, `hw_get_module`
    - AG only: `atrace_*` and `property_get` from libcutils
  - The same NEEDED set as Googlebook's own vendor `vulkan.intel.so` (Mesa 26.1.3 ANV), which links `libcutils libdrm libhardware liblog libnativewindow libsync libz`. Googlebook ships `libz.so`, `libcutils.so` and `libhardware.so` in `/vendor/lib64`.
- **HAL exports** (`hal-symbols.txt`).
  - `vulkan.radv.so` exports exactly **one** symbol: `HMI` (`hwvulkan_module_t`).
    - `vk_icdGetInstanceProcAddr` is **not** exported, by design: Mesa links Android Vulkan drivers with `src/vulkan/vulkan-android.sym` (`HMI` only).
    - Android's libvulkan reaches `vkGetInstanceProcAddr` through `hwvulkan_device_t`, not through the Khronos ICD interface.
  - `libEGL_mesa.so` exports 47 `egl*` symbols, GLESv2 358 and GLESv1_CM 145.
  - No `__emutls` imports: ELF TLS is forced for API ≥ 29.
- **`-march` / ISA** (`march.txt`, `isa-elfx86exts.txt`, `isa-wide-vector-functions.txt`).
  - No `-march`, `-mcpu` or `-mtune` anywhere. The baseline is the NDK default for `x86_64-linux-android37`: `-target-cpu x86-64 +sse4.2 +popcnt +cx16`, which is the Android x86_64 ABI. **Not tuned for Zen 4 or Zen 5.**
  - Two files get `-msse4.1` (`libmesa_sse41`, used only after a runtime check).
  - elfx86exts does list AVX/AVX2/AVX-512. The per-function scan shows these are only in:
    - BLAKE3's cpuid-dispatched `blake3_*_avx2/avx512`
    - addrlib's `[[gnu::target("avx2")]]` swizzle copies, guarded by `__builtin_cpu_supports("avx2")` (`addrswizzlersimd.h`; upstream 26.2 only, AG 26.0 has just BLAKE3)
  - So no AVX-VNNI or other Zen 5-only instructions are needed. This differs from Google's pantherlake-tuned blobs (PLAN §3.4).
- **Load test on Android 17 x86_64** (`smoke/`, `scripts/mesa-android-smoke.sh`).
  - Setup: AOSP Desktop emulator `CLE1.260506.004`, API 37, kernel 6.12.58, KVM, its own AVD on port 5590. Both trees give the same result:
    - `dlopen(vulkan.radv.so)` → `HMI` id=`vulkan` "Mesa 3D Vulkan HAL" → `open(vk0)=0` → 8 instance extensions → **`vkCreateInstance(1.3)=VK_SUCCESS`** → `vkEnumeratePhysicalDevices`: 0 devices (no `/dev/dri` in the VM; expected).
    - `dlopen(libEGL_mesa.so)` → client extensions and `eglGetProcAddress` work. `eglInitialize` → `EGL_NOT_INITIALIZED`; logcat shows `Using fallback gralloc implementation`, `Failed to open any DRM device` (expected without an AMD GPU). `libGLESv2_mesa.so` loads.
  - This proves bionic and linker compatibility on the target OS version. **It does not prove rendering.**
- **Reproducibility** (`upstream/reproducibility.txt`). After `rm -rf` of the build directory, a rebuild with `CCACHE_DISABLE=1` gives **bit-identical** SHA-256 for all 7 artifacts.

## Patches carried by Android-Generic (`ag/ag-patches.txt`)

AG's `26.0/main` is upstream `mesa-26.0.8` (merge-base `60e95b78`) plus 63 commits across 73 files (+1203/−137). The ones that matter for AMD on Android:

| Commit | What | In upstream 26.2.5? |
|---|---|---|
| `4e1cd411fc3` | radv: explicit DRM format modifier from Android gralloc (minigbm modifiers) | **Yes** (`141bd654834`) |
| `16bfa001573` | radeonsi: init `use_aco` when LLVM is disabled | No same-subject commit; 26.2 has `amd-use-llvm` and builds fine without LLVM |
| `20a37ff3959` | Revert "radv: use `AHARDWAREBUFFER_USAGE_CAMERA_MASK`" | No (upstream keeps the mask) |
| `b14bf42d23e` | util: split Android properties in `os_get_option()` (`property_get`, adds the libcutils dependency) | No |
| `97afe6eb089` | Enable xmlconfig (driconf) on Android | No |
| `c06afe82501` | egl/dri2: silence a misleading error in EGL logs | No |
| `81025d788ab` | install `libGLES_mesa` as a copy of `libEGL_mesa` (AOSP glue) | No |
| `ff593430de5`, `dc1ef933eb8`, `de9a667bed6` | anti-lag and overlay layers: Android exports, logcat, CPU load | No |
| `e43ac3a93f9` | driconf: override Vulkan `deviceName` | No |

The rest is AOSP `Android.mk`/Rust/LLVM-stub glue, plus Intel (crocus), NVIDIA (nouveau/NVK) and VMware work that doesn't affect these drivers. **Recommendation:** use upstream 26.2.x as the base, and cherry-pick only the `os_get_option` split-property patch and the xmlconfig patch at AOSP integration. Upstream already has the modifier fix.

## Known gaps (ranked)

Status after ANAL-174 (`docs/graphics-amd.md`):
- **Gap 1 (gralloc)** is closed by option (a): minigbm's amdgpu backend allocates through GBM.
- **Gap 2 (SELinux)** has its labels in `device/anybook/common/graphics-amd/sepolicy`.
- **Gap 3 (libdrm)** is resolved: AOSP's libdrm core plus our `libdrm_amdgpu_mesa.so`.
- **Gap 4 (ANGLE)** is settled: ANGLE on RADV is the default EGL on AMD, and radeonsi is the fallback.
- **Gap 5 (hardware)** is partly done: the image's drivers ran on the build host's 610M, but not yet on the G14.
- **New gap:** under `android-strict`, RADV reports Vulkan 1.1.

1. **Gralloc interface (blocks rendering on the device).**
   - An NDK build gets Mesa's `u_gralloc` backends `cros`, `libdrm`, `qcom` and `fallback` only. The IMapper4/IMapper5 backends need `android.hardware.graphics.mapper` / libui, which exist only inside an AOSP tree (`meson.build:1062-1066`).
   - Googlebook's vendor uses minigbm (`gralloc.minigbm.so` gralloc0 + `mapper.minigbm.so`) with **no amdgpu backend** (PLAN §3.3). The emulator test fell back to `fallback`.
   - Path:
     - (a) minigbm with the amdgpu or gbm_mesa backend, so Mesa's `cros` backend (gralloc0 `perform` buffer info) works.
     - (b) An in-tree AOSP build to get the IMapper5 backend.
   - **Next issue.**
2. **SELinux and linker namespaces for an SP-HAL drop-in.** The EGL, GLES, Vulkan, `libgallium_dri.so` and `libdrm*.so` files must be labeled `same_process_hal_file`, as Googlebook does for `mapper.minigbm.so` and `libdrm_intel.so`. `/dev/dri/renderD*` must be reachable (`gpu_device`), and `vendor.mesa.*` debug properties need `property_contexts`; the emulator logged "Access denied finding property vendor.mesa.radv.*".
3. **libdrm duplication.** Our `libdrm.so` has the same name as the vendor's. Either replace it with 2.4.133 (ABI-compatible superset) or link against the vendor copy after a symbol check.
4. **ANGLE.** Googlebook sets `ro.hardware.egl=angle`. For parity, RADV is the critical piece and ANGLE runs on top of it. radeonsi EGL (`ro.hardware.egl=mesa`) is the alternative and fallback path. ANGLE-on-RADV is untested.
5. **No AMD hardware run.**
   - VFIO passthrough of the host's Radeon 610M needs root, which we don't have.
   - What's still needed: `vkEnumeratePhysicalDevices`, dEQP and CTS need an AMD target booting an Android kernel with amdgpu (M3/M4).
6. **Not built:** VA/Vulkan video codecs, perfetto tracing, the driconf XML, and zstd shader-cache compression. No 32-bit (x86) libraries either, and none are needed for parity: Googlebook is 64-bit only (`ro.vendor.product.cpu.abilist=x86_64,arm64-v8a`, empty `abilist32`).
