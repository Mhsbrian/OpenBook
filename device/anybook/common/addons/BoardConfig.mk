# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Board half of addons.mk: openbook-addons' SELinux domain (sepolicy/private). It reads the boot disk through the
# installer's whole-disk label, so include it with device/anybook/common/installer/BoardConfig.mk.
SYSTEM_EXT_PRIVATE_SEPOLICY_DIRS += device/anybook/common/addons/sepolicy/private
