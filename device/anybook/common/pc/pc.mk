# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# OpenBook on a generic x86_64 UEFI PC (product half; the board half is BoardConfig.mk here). Boots from a GPT
# disk, USB or NVMe, through an EFI loader that passes bootconfig (docs/installer.md), not through Cuttlefish.
# Device products (device/anybook/g14) inherit this and add their kernel, firmware, input files and quirks.
# docs/g14-product.md explains each choice.

# System, system_ext and product: the same as AOSP's GSI-style products (aosp_cf_x86_64_pc inherits these too).
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit_only.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/generic_system.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/handheld_system_ext.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/aosp_product.mk)

# Vendor base, GKI generic ramdisk (init_boot), virtual A/B with compression, adoptable emulated storage.
$(call inherit-product, $(SRC_TARGET_DIR)/product/handheld_vendor.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/generic_ramdisk.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/virtual_ab_ota/vabc_features.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/emulated_storage.mk)
$(call inherit-product, frameworks/native/build/tablet-10in-xhdpi-2048-dalvik-heap.mk)
PRODUCT_VIRTUAL_AB_COMPRESSION_METHOD := lz4
PRODUCT_VIRTUAL_AB_COW_VERSION := 3

# Android desktop: desktop characteristics, windowing and flags (ANAL-169).
$(call inherit-product, device/anybook/common/desktop/desktop.mk)

PRODUCT_SHIPPING_API_LEVEL := 37
PRODUCT_USE_DYNAMIC_PARTITIONS := true
PRODUCT_SET_DEBUGFS_RESTRICTIONS := true
PRODUCT_FS_COMPRESSION := 1
DEVICE_MANIFEST_FILE += device/anybook/common/pc/manifest.xml

VENDOR_SECURITY_PATCH = $(PLATFORM_SECURITY_PATCH)
BOOT_SECURITY_PATCH = $(PLATFORM_SECURITY_PATCH)
PRODUCT_VENDOR_PROPERTIES += ro.vendor.boot_security_patch=$(BOOT_SECURITY_PATCH)

# Laptop behaviour (lid, power button, battery saver; ANAL-178): OpenBookPcFrameworkOverlay, added with audio below.

# A PC: no telephony, a keyboard and a pointer, a lid.
PRODUCT_COPY_FILES += \
    frameworks/native/data/etc/pc_core_hardware.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/pc_core_hardware.xml \
    frameworks/native/data/etc/android.hardware.usb.host.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.usb.host.xml \
    frameworks/native/data/etc/android.software.verified_boot.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.software.verified_boot.xml \
    frameworks/native/data/etc/android.software.ipsec_tunnels.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.software.ipsec_tunnels.xml

# First-stage and second-stage fstab, init, ueventd.
PRODUCT_COPY_FILES += \
    device/anybook/common/pc/fstab.openbook:$(TARGET_COPY_OUT_VENDOR_RAMDISK)/first_stage_ramdisk/fstab.openbook \
    device/anybook/common/pc/fstab.openbook:$(TARGET_COPY_OUT_VENDOR)/etc/fstab.openbook \
    device/anybook/common/pc/init.openbook.rc:$(TARGET_COPY_OUT_VENDOR)/etc/init/hw/init.openbook.rc \
    device/anybook/common/pc/ueventd.openbook.rc:$(TARGET_COPY_OUT_VENDOR)/etc/ueventd.rc

# Boot-time sysfs setup (the runtime-PM fallback for a dGPU nobody drives, EPP files for the power HAL), and on
# userdebug ANAL-187's dGPU check (scripts/dgpu-power-check.sh).
PRODUCT_PACKAGES += openbook-pc-setup
PRODUCT_PACKAGES_DEBUG += \
    dgpu-power-check \
    openbook-pc-setup-test

# Graphics: AMD (Mesa radeonsi/RADV, minigbm amdgpu, drm_hwcomposer, ANGLE), picked at boot (ANAL-174). The
# platform HALs stay on: minigbm allocator/mapper and drm_hwcomposer serve amdgpu and, as a fallback,
# virtio-gpu in VMs. The fallback renders with SwiftShader Vulkan under ANGLE (init.openbook.rc).
$(call inherit-product, device/anybook/common/graphics-amd/graphics-amd.mk)
PRODUCT_PACKAGES += vulkan.pastel
PRODUCT_REQUIRES_INSECURE_EXECMEM_FOR_SWIFTSHADER := true

# Base HALs. AOSP implementations; the ones listed with "openbook" use the real sysfs of a PC instead of the
# AOSP examples' fixed values. docs/g14-product.md has the table.
PRODUCT_PACKAGES += \
    android.hardware.health-service.openbook \
    com.android.hardware.boot \
    com.android.hardware.authsecret \
    com.android.hardware.dumpstate \
    com.android.hardware.memtrack \
    android.hardware.lights-service.openbook \
    android.hardware.power-service.openbook \
    android.hardware.power.stats-service.openbook \
    android.hardware.thermal-service.openbook \
    android.hardware.usb-service.example

# Software KeyMint and Gatekeeper (no TEE, no hardware attestation: keys are only as safe as /data), and a
# file-backed software Weaver. ro.hardware.keystore_desede: the software KeyMint supports 3DES.
PRODUCT_PACKAGES += \
    com.android.hardware.keymint.rust_nonsecure \
    com.android.hardware.gatekeeper.nonsecure \
    android.hardware.weaver-service.openbook
PRODUCT_VENDOR_PROPERTIES += ro.hardware.keystore_desede=true

# Audio: AOSP's AIDL example HAL, its primary module on the built-in codec (ANAL-179, docs/g14-audio-net.md).
# openbook-audio-setup finds the codec's ALSA card at boot and sets its mixer up; OpenBook's HAL patch
# (aosp/patches/hardware/interfaces) reads the card from vendor.audio.primary.card. The HAL creates its modules
# from /vendor/etc/audio_policy_configuration.xml (audio/ explains which ones it needs);
# audio_policy_config_vendor_1.mk adds the AOSP files it includes, these the rest.
PRODUCT_PACKAGES += \
    com.android.hardware.audio \
    openbook-audio-setup \
    OpenBookPcFrameworkOverlay
PRODUCT_COPY_FILES += \
    device/anybook/common/pc/audio/audio_policy_configuration.xml:$(TARGET_COPY_OUT_VENDOR)/etc/audio_policy_configuration.xml \
    device/anybook/common/pc/audio/primary_audio_policy_configuration.xml:$(TARGET_COPY_OUT_VENDOR)/etc/primary_audio_policy_configuration.xml \
    frameworks/av/services/audiopolicy/config/bluetooth_with_le_audio_policy_configuration_7_0.xml:$(TARGET_COPY_OUT_VENDOR)/etc/bluetooth_with_le_audio_policy_configuration_7_0.xml
$(call inherit-product, frameworks/av/services/audiopolicy/audio_policy_config_vendor_1.mk)
$(call inherit-product, hardware/interfaces/audio/aidl/default/audio_effects.mk)

# Wi-Fi: AOSP's wpa_supplicant and wificond on the laptop's mac80211 driver, no vendor Wi-Fi HAL (wifi/wifi.mk).
$(call inherit-product, device/anybook/common/pc/wifi/wifi.mk)

# Bluetooth: AOSP's AIDL HAL over the kernel's HCI user channel (btusb + btmtk on the G14). The profiles a laptop
# uses: audio out (A2DP source, AVRCP), keyboards and mice (HID host), LE (GATT), battery levels, file transfer,
# tethering to a phone (PANU). No HFP gateway yet: it needs the HAL's SCO audio path, untested. Class of device:
# computer/laptop with networking, capturing, object transfer and audio services.
PRODUCT_PACKAGES += android.hardware.bluetooth-service.default
PRODUCT_COPY_FILES += \
    frameworks/native/data/etc/android.hardware.bluetooth_le.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.bluetooth_le.xml
PRODUCT_PRODUCT_PROPERTIES += \
    bluetooth.device.class_of_device=58,1,12 \
    bluetooth.profile.a2dp.source.enabled=true \
    bluetooth.profile.avrcp.target.enabled=true \
    bluetooth.profile.bas.client.enabled=true \
    bluetooth.profile.gatt.enabled=true \
    bluetooth.profile.hid.host.enabled=true \
    bluetooth.profile.opp.enabled=true \
    bluetooth.profile.pan.panu.enabled=true

# userdebug: the checks the live image's "save logs" entry runs (openbook-hwtest) and their tools.
PRODUCT_PACKAGES_DEBUG += \
    openbook-hwtest \
    openbook-audio-test \
    tinycap \
    tinymix \
    tinypcminfo \
    tinyplay

PRODUCT_VENDOR_PROPERTIES += \
    ro.logd.size=1M \
    tombstoned.max_tombstone_count=50 \
    ro.crypto.metadata_init_delete_all_keys.enabled=true
