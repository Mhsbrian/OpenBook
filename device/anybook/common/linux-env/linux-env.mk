# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# The Linux environment (ANAL-218, docs/quire.md §4): AVF with its Terminal app, where Quire's agents run. AOSP's
# generic system product carries the com.android.virt APEX but builds it without AVF (no crosvm, virtmgr or Terminal)
# unless the product inherits this; the phone Cuttlefish products do, the PC one doesn't. cp2a already turns on the
# AVF release flags (custom VMs with paravirtualized devices, networking).
#
# The Terminal app ships disabled, as in AOSP: the person turns it on in Developer options ("Linux development
# environment"). It finds its Debian image at /sdcard/linux/images.tar.gz on a debuggable build, else downloads
# Google's; OpenBook builds its own (scripts/quire/linux-env-image.sh). Whether VMs can run is decided at boot: by
# Cuttlefish's launcher, and on a PC by init.openbook.rc from whether KVM is there.
$(call inherit-product, packages/modules/Virtualization/apex/product_packages.mk)
