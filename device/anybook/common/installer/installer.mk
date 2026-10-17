# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenBook installer (ANAL-191, docs/installer.md): the "Install OpenBook" wizard app and the install engine with
# its daemon. Both ship in every image; the app's launcher entry, its start at boot and the daemon are live-session
# only (androidboot.openbook.live=1). BoardConfig.mk here adds the SELinux policy.
PRODUCT_PACKAGES += \
    openbook-install \
    OpenBookInstaller
