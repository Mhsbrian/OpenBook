# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Quire core (ANAL-216, docs/quire.md §4): a privileged system app that holds the assistant role, is the contextual
# search app and may own computer-control sessions, plus the framework overlay that makes it the default for both. Its
# aconfig flags (computer control, the pointer shake) are in ../desktop/release/openbook/.
PRODUCT_PACKAGES += \
    OpenBookQuire \
    OpenBookQuireFrameworkOverlay
