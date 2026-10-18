# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# OpenBook's own look and sound instead of AOSP's stock assets (ANAL-207): the boot animation, the sound set and the
# pointer theme. The default wallpaper is in the desktop framework overlay, the wallpaper set in the partner
# customization package. All the art is generated from assets/ (assets/README.md, scripts/brand/).
# Inherited by desktop.mk, so every AnyBook product gets it.

PRODUCT_PACKAGES += \
    OpenBookPointerOverlay \
    OpenBookSoundsSettingsProviderOverlay

# The brand mark's pages unfold and its spark lights up while Android boots. bootanimation reads
# /product/media/bootanimation.zip first (frameworks/base/cmds/bootanimation).
PRODUCT_COPY_FILES += \
    device/anybook/common/branding/media/bootanimation.zip:$(TARGET_COPY_OUT_PRODUCT)/media/bootanimation.zip

# The sound set. AOSP's sounds stay installed and selectable; these are the defaults. MediaProvider sets the
# ringtone, notification and alarm settings from ro.config.* at first boot. Product properties load last, so these
# win over aosp_product.mk's and handheld_system.mk's (vendor) values.
OPENBOOK_SOUNDS := \
    ringtones/OpenBook_Pages.ogg \
    notifications/OpenBook_Spark.ogg \
    alarms/OpenBook_FirstLight.ogg \
    ui/OpenBook_Lock.ogg \
    ui/OpenBook_Unlock.ogg \
    ui/OpenBook_Trusted.ogg \
    ui/OpenBook_LowBattery.ogg \
    ui/OpenBook_ChargingStarted.ogg
PRODUCT_COPY_FILES += $(foreach f,$(OPENBOOK_SOUNDS),\
    device/anybook/common/branding/media/audio/$(f):$(TARGET_COPY_OUT_PRODUCT)/media/audio/$(f))
PRODUCT_PRODUCT_PROPERTIES += \
    ro.config.ringtone=OpenBook_Pages.ogg \
    ro.config.notification_sound=OpenBook_Spark.ogg \
    ro.config.alarm_alert=OpenBook_FirstLight.ogg
