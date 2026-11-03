# Copyright (C) 2026 The AnyBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Board half of gfx-mode.mk: openbook-gfx-mode's SELinux domain, the firmware switches' label and the readers of
# its state.
BOARD_VENDOR_SEPOLICY_DIRS += device/anybook/common/gfx-mode/sepolicy/vendor
# The platform half: openbook.gfx.request, the app's request, which the switcher's init trigger reads, and the app's
# own domain, openbook_graphics_app (ANAL-323), for products that install it (gfx-mode-app.mk).
SYSTEM_EXT_PRIVATE_SEPOLICY_DIRS += device/anybook/common/gfx-mode/sepolicy/system_ext
