# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# OpenBook for the ASUS ROG Zephyrus G14 2025, board GA403WR (Ryzen AI 9 HX 370, Radeon 890M; docs/HARDWARE.md):
# the generic PC product plus the G14's kernel, firmware, input devices and display. docs/g14-product.md.
#   lunch anybook_g14_x86_64-cp2a-userdebug

$(call inherit-product, device/anybook/common/pc/pc.mk)

include device/anybook/g14/kernel.mk
ifeq ($(wildcard $(OPENBOOK_G14_KERNEL_DIR)/firmware/firmware.mk),)
$(error G14 kernel and firmware not staged in $(OPENBOOK_G14_KERNEL_DIR): run scripts/g14-stage-kernel.sh)
endif

# linux-firmware subset for the GA403WR and the other AMD laptops the module set covers (ANAL-198): 137 files and
# the 5 licence files WHENCE cites, into /vendor/firmware.
ANYBOOK_G14_FIRMWARE_DIR := $(OPENBOOK_G14_KERNEL_DIR)/firmware/vendor/firmware
include $(OPENBOOK_G14_KERNEL_DIR)/firmware/firmware.mk
# AOSP 17 imports the MediaTek MT7921/MT7922/MT7925 Wi-Fi and Bluetooth files itself (external/linux-firmware, at
# linux-firmware 0d347a3f, 2026-04-23), and Soong owns their /vendor/firmware paths. Those 9 come from AOSP's
# modules; ANAL-198's copies (38c1a709, 2026-10) of the same names differ and are dropped. ANAL-179 keeps AOSP's
# (firmware build 20260414, the one the G14 loaded in live-001): docs/g14-audio-net.md.
OPENBOOK_AOSP_FIRMWARE := \
    mediatek/BT_RAM_CODE_MT7922_1_1_hdr.bin \
    mediatek/BT_RAM_CODE_MT7961_1_2_hdr.bin \
    mediatek/WIFI_MT7922_patch_mcu_1_1_hdr.bin \
    mediatek/WIFI_MT7961_patch_mcu_1_2_hdr.bin \
    mediatek/WIFI_RAM_CODE_MT7922_1.bin \
    mediatek/WIFI_RAM_CODE_MT7961_1.bin \
    mediatek/mt7925/BT_RAM_CODE_MT7925_1_1_hdr.bin \
    mediatek/mt7925/WIFI_MT7925_PATCH_MCU_1_1_hdr.bin \
    mediatek/mt7925/WIFI_RAM_CODE_MT7925_1_1.bin
PRODUCT_COPY_FILES := $(filter-out $(addprefix %:$(TARGET_COPY_OUT_VENDOR)/firmware/,$(OPENBOOK_AOSP_FIRMWARE)),$(PRODUCT_COPY_FILES))
PRODUCT_PACKAGES += \
    linux_firmware_mt7921 \
    linux_firmware_mt7921-bt \
    linux_firmware_mt7922 \
    linux_firmware_mt7922-bt \
    linux_firmware_mt7925 \
    linux_firmware_mt7925-bt
PRODUCT_COPY_FILES += $(OPENBOOK_G14_KERNEL_DIR)/bzImage:kernel

# Built-in keyboard (ASUS N-KEY, USB 0b05:19b6) and touchpad (ELAN 04f3:3315, I2C HID). Marking them internal is
# what makes WM Shell put the panel into desktop mode on its own (docs/aosp-desktop.md). The firmware's WMI hotkeys
# (asus-nb-wmi, no USB IDs) get a layout by device name (ANAL-178).
PRODUCT_COPY_FILES += \
    device/anybook/g14/input/Vendor_0b05_Product_19b6.idc:$(TARGET_COPY_OUT_VENDOR)/usr/idc/Vendor_0b05_Product_19b6.idc \
    device/anybook/g14/input/Vendor_0b05_Product_19b6.kl:$(TARGET_COPY_OUT_VENDOR)/usr/keylayout/Vendor_0b05_Product_19b6.kl \
    device/anybook/g14/input/Vendor_04f3_Product_3315.idc:$(TARGET_COPY_OUT_VENDOR)/usr/idc/Vendor_04f3_Product_3315.idc \
    device/anybook/g14/input/Asus_WMI_hotkeys.kl:$(TARGET_COPY_OUT_VENDOR)/usr/keylayout/Asus_WMI_hotkeys.kl

# 14" 2880x1800 OLED (Samsung ATNA40CU05-0): 243 ppi. 240 dpi gives a 1920x1200 dp desktop, as on Googlebook.
PRODUCT_VENDOR_PROPERTIES += ro.vendor.openbook.lcd_density=240

# Background blur (shade, Quick Settings, launcher, app launch), as Googlebook sets it and Cuttlefish already does
# (device/google/cuttlefish/shared/device.mk). SurfaceFlinger's RenderEngine draws it, on the GPU (SkiaGL on ANGLE
# on RADV); WM turns it off by itself in battery saver and at severe thermal status (ANAL-203, docs/googlebook-ui.md
# §2.3).
PRODUCT_VENDOR_PROPERTIES += ro.surface_flinger.supports_background_blur=1

PRODUCT_NAME := anybook_g14_x86_64
PRODUCT_DEVICE := anybook_g14
PRODUCT_BRAND := OpenBook
PRODUCT_MANUFACTURER := ASUS
PRODUCT_MODEL := OpenBook on ROG Zephyrus G14 (GA403WR)
PRODUCT_VENDOR_PROPERTIES += \
    ro.soc.manufacturer=AMD \
    ro.soc.model=Ryzen_AI_9_HX_370
