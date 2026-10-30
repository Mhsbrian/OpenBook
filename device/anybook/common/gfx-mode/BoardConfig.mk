# Copyright (C) 2026 The AnyBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Board half of gfx-mode.mk: openbook-gfx-mode's SELinux domain, the firmware switches' label and the readers of
# its state.
BOARD_VENDOR_SEPOLICY_DIRS += device/anybook/common/gfx-mode/sepolicy/vendor
# The platform half: openbook.gfx.request, the app's request, which the switcher's init trigger reads.
SYSTEM_EXT_PRIVATE_SEPOLICY_DIRS += device/anybook/common/gfx-mode/sepolicy/system_ext
