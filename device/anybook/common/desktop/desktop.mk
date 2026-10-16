# Copyright (C) 2026 The AnyBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Android desktop (laptop) configuration, matching Google's AOSP Desktop (Preview) emulator image
# (sdk_gdesktop_x86_64, Android 17). Inherit it from any AnyBook product, VM or bare metal.
# docs/aosp-desktop.md maps every setting to the reference image and to the code that reads it.

# desktop variants of resource strings (aapt --product, plus auto-generated characteristics RROs).
PRODUCT_CHARACTERISTICS := desktop

# Window extensions (persist.wm.extensions.enabled, ...activity_embedding_guard_with_android_15=false) and the
# two-pane Settings layout (persist.settings.large_screen_opt.enabled), as in the reference image.
$(call inherit-product, $(SRC_TARGET_DIR)/product/large_screen_common.mk)

# Desktop windowing and desktop SystemUI configs (framework and SystemUI RROs on /product).
PRODUCT_PACKAGES += \
    AnyBookDesktopFrameworkOverlay \
    AnyBookDesktopSystemUIOverlay
