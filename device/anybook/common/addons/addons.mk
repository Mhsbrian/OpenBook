# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Optional app add-ons (ANAL-210, docs/gapps.md section 6): openbook-addons and its catalogue. The image carries no
# add-on APKs; they come on the boot disk's EFI partition (scripts/microg/add-to-image.sh), and without them nothing
# changes. Today's catalogue: microG (microg.json). BoardConfig.mk here adds the SELinux policy.
PRODUCT_PACKAGES += \
    openbook-addons
