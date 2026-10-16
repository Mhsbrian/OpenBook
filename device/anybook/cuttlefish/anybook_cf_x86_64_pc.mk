# Copyright (C) 2026 The AnyBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# AnyBook desktop on Cuttlefish x86_64: AOSP's aosp_cf_x86_64_pc plus the AnyBook desktop configuration.
#   lunch anybook_cf_x86_64_pc-cp2a-userdebug

$(call inherit-product, device/google/cuttlefish/vsoc_x86_64_only/pc/aosp_cf.mk)
$(call inherit-product, device/anybook/common/desktop/desktop.mk)

# AMD graphics (Mesa RADV/radeonsi, minigbm amdgpu, ANGLE) with HAL selection at boot. Cuttlefish keeps
# its virtio-gpu stack (gfxstream, ranchu/drm_hwcomposer APEXes, cf.gralloc), so the probe reports
# virtio here and the AMD HALs stay installed but unused; anybook_vsoc_x86_64's BoardConfig.mk adds
# the vendor policy.
ANYBOOK_GRAPHICS_PLATFORM_HALS := false
$(call inherit-product, device/anybook/common/graphics-amd/graphics-amd.mk)

PRODUCT_PACKAGES += anybook_cf_display_settings.xml

# Desktop-first on the VM's only display. On real laptops WM Shell's DesktopDisplayModeController switches
# the internal display to freeform by itself (touchpad plus physical keyboard, or a lid device state); the
# VM has neither, so this uses the same property Google's desktop emulator image sets.
PRODUCT_PRODUCT_PROPERTIES += \
    persist.wm.debug.force_desktop_first_on_default_display_for_testing=true

PRODUCT_NAME := anybook_cf_x86_64_pc
PRODUCT_DEVICE := anybook_vsoc_x86_64
PRODUCT_BRAND := AnyBook
PRODUCT_MANUFACTURER := Google
PRODUCT_MODEL := AnyBook Cuttlefish x86_64 desktop

# aosp_cf.mk only sets this for its own product name; build the same way it does (Soong-only images).
PRODUCT_SOONG_ONLY := $(RELEASE_SOONG_ONLY_CUTTLEFISH)
