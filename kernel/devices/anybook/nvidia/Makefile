# SPDX-License-Identifier: GPL-2.0
# Kleaf's kernel_module runs `make -C <this directory> M=... O=... MO=... KERNEL_SRC=...`; kbuild then reads ./Kbuild.
# nouveau/Kbuild selects its objects with make variables from nouveau's Kconfig, which the device config does not
# have (DRM_NOUVEAU stays off there, so the in-tree copy is never built; see Kconfig.ext). These are their values,
# for this module's make only; ./Kbuild sets the matching C macros.
NOUVEAU_KCONFIG := CONFIG_DRM_NOUVEAU=m CONFIG_DRM_NOUVEAU_BACKLIGHT=y

modules modules_install clean:
	$(MAKE) -C $(KERNEL_SRC) M=$(M) $(NOUVEAU_KCONFIG) $(KBUILD_OPTIONS) $(@)
