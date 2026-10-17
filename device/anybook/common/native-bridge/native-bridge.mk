# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# arm64 native bridge for x86_64 OpenBook products (ANAL-200): Digitalis, the Apache-2.0 arm64 guest for AOSP's
# Berberis translator, built from source in this tree. aosp/patches/frameworks/libs/binary_translation puts the
# Digitalis fork plus OpenBook's Android 17 port and fixes in place of AOSP's project; the guest libraries
# (bionic, NDK stubs, proxies) are frameworks/libs/native_bridge_support from this Android 17 tree. Pair it with
# native-bridge/BoardConfig.mk, which makes the build produce the arm64 native_bridge variants. docs/digitalis.md.
#
# It installs the translator (libberberis_arm64.so), the proxy libraries, the arm64 guest world in
# /system/{lib64,bin}/arm64, the binfmt_misc runners and their init scripts, and sets:
#   ro.dalvik.vm.native.bridge=libberberis_arm64.so  ro.dalvik.vm.isa.arm64=x86_64  ro.enable.native.bridge.exec=1
#   ro.berberis.flags=disable-ir-check
$(call inherit-product, frameworks/libs/binary_translation/enable_arm64_to_x86_64.mk)

# The bridge's self-check on the device (openbook-hwtest "bridge"; also by hand: /system/bin/arm64/openbook_bridge_check).
PRODUCT_PACKAGES += openbook_bridge_check.native_bridge
PRODUCT_ARTIFACT_PATH_REQUIREMENT_ALLOWED_LIST += system/bin/arm64/openbook_bridge_check
