# Copyright (C) 2026 The AnyBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# AnyBook desktop on Cuttlefish x86_64: AOSP's aosp_cf_x86_64_pc plus the AnyBook desktop configuration.
#   lunch anybook_cf_x86_64_pc-cp2a-userdebug

$(call inherit-product, device/google/cuttlefish/vsoc_x86_64_only/pc/aosp_cf.mk)
$(call inherit-product, device/anybook/common/desktop/desktop.mk)

PRODUCT_PACKAGES += anybook_cf_display_settings.xml

# Desktop-first on the VM's only display. On real laptops WM Shell's DesktopDisplayModeController switches
# the internal display to freeform by itself (touchpad plus physical keyboard, or a lid device state); the
# VM has neither, so this uses the same property Google's desktop emulator image sets.
PRODUCT_PRODUCT_PROPERTIES += \
    persist.wm.debug.force_desktop_first_on_default_display_for_testing=true

PRODUCT_NAME := anybook_cf_x86_64_pc
PRODUCT_DEVICE := vsoc_x86_64_only
PRODUCT_BRAND := AnyBook
PRODUCT_MANUFACTURER := Google
PRODUCT_MODEL := AnyBook Cuttlefish x86_64 desktop

# aosp_cf.mk only sets this for its own product name; build the same way it does (Soong-only images).
PRODUCT_SOONG_ONLY := $(RELEASE_SOONG_ONLY_CUTTLEFISH)
