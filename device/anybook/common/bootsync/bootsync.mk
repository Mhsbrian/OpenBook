# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# A/B updates with systemd-boot (ANAL-223, docs/installer.md section 2.5): the boot control HAL that keeps the ESP's
# loader entries in step with the slots (openbook-bootsync). Replaces AOSP's com.android.hardware.boot.
# BoardConfig.mk here adds the SELinux policy.
PRODUCT_PACKAGES += \
    android.hardware.boot-service.openbook \
    openbook-bootsync
