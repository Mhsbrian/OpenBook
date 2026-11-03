# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# OpenBook Graphics (ANAL-323, docs/nvidia-graphics-modes.md §7): the switcher's app, with Eco, Hybrid and Ultimate
# and Apps on the NVIDIA GPU, as a privileged system_ext app in its own SELinux domain (app/Android.bp,
# sepolicy/system_ext, which BoardConfig.mk adds for every product). Products whose laptop has a MUX that
# openbook-gfx-mode handles include it; the G14 does.
PRODUCT_PACKAGES += OpenBookGraphics
