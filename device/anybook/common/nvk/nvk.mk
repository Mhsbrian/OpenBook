# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# OpenBook NVK, the NVIDIA driver for apps (ANAL-327, docs/nvk-openbook.md): the system package org.openbook.nvk in
# /vendor/app/OpenBookNvk, with NVK (Vulkan) and ANGLE on NVK (OpenGL ES). Android uses an app driver only from a
# system package (GraphicsEnvironment: MATCH_SYSTEM_ONLY). openbook-pc-setup's dgpu-driver boot offers it to apps
# (ro.gfx.driver.0) once NVIDIA's driver drives the GPU, and only if this APK is in the image. Which apps use it:
# OpenBook Graphics (gfx-mode-app.mk): the on/off switch, the games rule and each app's choice.
#
# The libraries are local build outputs, never committed (like vendor/anybook/mesa): scripts/nvk-stage.sh stages them
# (after scripts/mesa-android-build.sh -- nvk-rm-clean) with this directory's AndroidManifest.xml into
# vendor/anybook/nvk and generates the OpenBookNvk module there. Soong refuses a module whose dependencies are
# missing, so the module is not defined in this directory. A G14 build without the stage stops here;
# OPENBOOK_NVK=false builds the image without NVIDIA app support, on purpose.
ifneq ($(OPENBOOK_NVK),false)
ifeq ($(wildcard vendor/anybook/nvk/Android.bp),)
$(error OpenBook NVK is not staged (vendor/anybook/nvk): run scripts/mesa-android-build.sh -- nvk-rm-clean and \
  scripts/nvk-stage.sh, or set OPENBOOK_NVK=false for an image without NVIDIA app support (docs/nvk-openbook.md))
endif
PRODUCT_PACKAGES += OpenBookNvk
endif
