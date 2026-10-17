# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Board half of installer.mk: openbook-installd's SELinux domain, the whole-disk device label it writes through, and
# the app's socket access (sepolicy/private).
SYSTEM_EXT_PRIVATE_SEPOLICY_DIRS += device/anybook/common/installer/sepolicy/private
