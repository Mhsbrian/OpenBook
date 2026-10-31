# Copyright (C) 2026 The AnyBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Graphics modes (ANAL-246, docs/nvidia-graphics-modes.md): openbook-gfx-mode and its init steps. The board half
# is BoardConfig.mk here (its SELinux domain). It writes nothing on a laptop the product's stack manifest
# (/vendor/etc/openbook/gfx-stacks.conf, from the device directory) does not list, and no firmware at all unless
# the image sets ro.vendor.openbook.gfx.fw_writes=1, which a release does only with the owner's approval.
PRODUCT_PACKAGES += openbook-gfx-mode
