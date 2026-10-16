# Copyright (C) 2026 The AnyBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# AMD GPU graphics for AnyBook products, VM or bare metal (docs/graphics-amd.md). The board half is
# BoardConfig.mk in this directory. Which HALs run is decided at boot, not per product:
#   - anybook_gpu_probe (init.anybook.graphics-amd.rc) finds an AMD GPU through its DRM driver or PCI
#     vendor and then sets ro.hardware.{vulkan,egl,gralloc,hwcomposer}=radv,angle,minigbm,drm;
#   - minigbm picks its amdgpu backend (patched: aosp/patches/external/minigbm) from the DRM driver
#     name, next to virtgpu for virtio-gpu, in the same allocator and mapper.
#
# Set ANYBOOK_GRAPHICS_PLATFORM_HALS := false before inheriting this file when the product brings its
# own allocator/mapper/composer packaging (Cuttlefish), and in its BoardConfig.mk as well.

# The staged Mesa prebuilts provide anybook_mesa_amd; say how to get them instead of failing on an
# unknown module.
ifeq ($(wildcard vendor/anybook/mesa/Android.bp),)
$(error vendor/anybook/mesa is missing: build Mesa (scripts/mesa-android-build.sh) and stage it (scripts/graphics-amd-stage-mesa.sh))
endif

# Mesa 26.2 radeonsi (EGL/GLES, the fallback GL driver) and RADV (Vulkan), ACO only, no LLVM; GBM for
# minigbm's amdgpu backend; libdrm_amdgpu 2.4.133. AOSP's vendor libdrm.so is the libdrm core.
PRODUCT_PACKAGES += \
    anybook_mesa_amd \
    libdrm

# gralloc0 module: Mesa's "cros" u_gralloc asks it for buffer layouts (the NDK build of Mesa has no
# IMapper backend).
PRODUCT_PACKAGES += gralloc.minigbm

# ANGLE: GLES on Vulkan, ro.hardware.egl=angle on AMD.
PRODUCT_PACKAGES += \
    libEGL_angle \
    libGLESv1_CM_angle \
    libGLESv2_angle

# HAL selection at boot.
PRODUCT_PACKAGES += anybook_gpu_probe

ifneq ($(ANYBOOK_GRAPHICS_PLATFORM_HALS),false)
# Allocator and stable-C mapper (minigbm, with the amdgpu backend), and drm_hwcomposer on the KMS
# device. The policy for them is in sepolicy/platform.
PRODUCT_PACKAGES += \
    android.hardware.graphics.allocator-service.minigbm \
    mapper.minigbm \
    android.hardware.composer.hwc3-service.drm

# What RADV and ANGLE on RADV offer. Mesa's default android-strict build reports Vulkan 1.1; a build
# with ANDROID_STRICT=false (scripts/mesa-android-build.sh) reports 1.4 and would declare that instead.
# Products tune the dEQP levels once CTS has run (ANAL-177).
PRODUCT_COPY_FILES += \
    frameworks/native/data/etc/android.hardware.vulkan.level-1.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.vulkan.level.xml \
    frameworks/native/data/etc/android.hardware.vulkan.version-1_1.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.vulkan.version.xml \
    frameworks/native/data/etc/android.hardware.vulkan.compute-0.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.vulkan.compute.xml \
    frameworks/native/data/etc/android.hardware.opengles.aep.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.opengles.aep.xml
endif
