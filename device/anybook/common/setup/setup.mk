# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# OpenBook setup (ANAL-209, docs/setup.md): the first-run flow, in place of AOSP's Provision (OpenBookSetup
# overrides it). It steps aside on live sessions (androidboot.openbook.live=1), with androidboot.openbook.setup=skip
# (unattended runs) and with ro.setupwizard.mode=DISABLED (Cuttlefish's default, cvd --setupwizard_mode).
PRODUCT_PACKAGES += OpenBookSetup
