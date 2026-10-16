# Copyright (C) 2026 The AnyBook Authors
# SPDX-License-Identifier: Apache-2.0

PRODUCT_MAKEFILES := \
    anybook_cf_x86_64_pc:$(LOCAL_DIR)/cuttlefish/anybook_cf_x86_64_pc.mk \
    anybook_g14_x86_64:$(LOCAL_DIR)/g14/anybook_g14_x86_64.mk

COMMON_LUNCH_CHOICES := \
    anybook_cf_x86_64_pc-cp2a-userdebug \
    anybook_g14_x86_64-cp2a-userdebug
