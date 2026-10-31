# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Board for anybook_g14_x86_64: the generic PC board with the G14 kernel and AMD graphics.

# Kernel, dlkm images and firmware from ANAL-198's packaging, staged into the AOSP tree by
# scripts/g14-stage-kernel.sh (one Kleaf dist: the bzImage and system_dlkm must match).
include device/anybook/g14/kernel.mk
OPENBOOK_KERNEL_DIR := $(OPENBOOK_G14_KERNEL_DIR)

# For loaders that pass no androidboot.boot_part_uuid: the GA403WR's NVMe root port (00:02.1, bus 61) and its two
# xHCI root ports (00:08.1 -> 65:00.4, 00:08.3 -> 67:00.0/.3/.4), from the inventory's dmesg. Init ignores this
# whenever boot_part_uuid is set, which the OpenBook loader always does.
OPENBOOK_BOOT_DEVICES := pci0000:00/0000:00:02.1,pci0000:00/0000:00:08.1,pci0000:00/0000:00:08.3

include device/anybook/common/pc/BoardConfig.mk
include device/anybook/common/graphics-amd/BoardConfig.mk
