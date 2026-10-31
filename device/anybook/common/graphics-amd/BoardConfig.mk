# Copyright (C) 2026 The AnyBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Board half of graphics-amd.mk: include it from the BoardConfig.mk of every product that inherits
# graphics-amd.mk. Set ANYBOOK_GRAPHICS_PLATFORM_HALS := false first when the board brings its own
# allocator/mapper/composer policy (Cuttlefish), as the product half does for the packages.

BOARD_VENDOR_SEPOLICY_DIRS += device/anybook/common/graphics-amd/sepolicy/vendor

ifneq ($(ANYBOOK_GRAPHICS_PLATFORM_HALS),false)
BOARD_VENDOR_SEPOLICY_DIRS += \
    device/anybook/common/graphics-amd/sepolicy/platform \
    external/minigbm/cros_gralloc/sepolicy
endif
