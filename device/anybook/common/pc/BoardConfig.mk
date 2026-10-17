# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Board half of pc.mk: a generic x86_64 UEFI PC booting OpenBook from a GPT disk (docs/g14-product.md).
# Include it from a device's BoardConfig.mk after setting:
#   OPENBOOK_KERNEL_DIR   kernel prebuilts staged by scripts/g14-stage-kernel.sh: bzImage, vendor_dlkm.img,
#                         system_dlkm.img and vendor_boot-ramdisk.lz4, all from one Kleaf dist (MODULE_SIG_PROTECT:
#                         bzImage and system_dlkm must come from the same build)
#   OPENBOOK_BOOT_DEVICES (optional) root ports of the internal NVMe and the USB controllers, for loaders that
#                         pass no androidboot.boot_part_uuid; init ignores it when boot_part_uuid is set

include build/make/target/board/BoardConfigMainlineCommon.mk

TARGET_ARCH := x86_64
# The generic x86-64 baseline (SSE4.2), as Cuttlefish and the Mesa prebuilts use: runs on any 64-bit PC.
TARGET_ARCH_VARIANT := silvermont
TARGET_CPU_ABI := x86_64
TARGET_BOARD_PLATFORM := openbook_pc
TARGET_BOOTLOADER_BOARD_NAME := openbook
# arm64 apps run through the Digitalis native bridge (pc.mk inherits native-bridge.mk; ANAL-200).
include device/anybook/common/native-bridge/BoardConfig.mk

# ---------------------------------------------------------------- kernel and boot images
ifeq ($(wildcard $(OPENBOOK_KERNEL_DIR)/bzImage),)
$(error OpenBook kernel prebuilts missing in '$(OPENBOOK_KERNEL_DIR)': run scripts/g14-stage-kernel.sh (docs/g14-product.md))
endif
BOARD_USES_GENERIC_KERNEL_IMAGE := true
BOARD_BOOT_HEADER_VERSION := 4
BOARD_MKBOOTIMG_ARGS += --header_version $(BOARD_BOOT_HEADER_VERSION)
BOARD_INIT_BOOT_HEADER_VERSION := 4
BOARD_MKBOOTIMG_INIT_ARGS += --header_version $(BOARD_INIT_BOOT_HEADER_VERSION)
BOARD_RAMDISK_USE_LZ4 := true
BOARD_BOOTIMAGE_PARTITION_SIZE := 67108864
BOARD_INIT_BOOT_IMAGE_PARTITION_SIZE := 8388608
BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE := 67108864
BOARD_FLASH_BLOCK_SIZE := 4096

# First stage loads no modules on a PC: NVMe, xHCI, usb-storage, uas, dm and the filesystems are built into the
# GKI (ANAL-198). The "dlkm" fragment only carries lib/modules/<release>/ with an empty modules.load, so
# first-stage init never falls back to a flat /lib/modules/modules.load.
BOARD_VENDOR_RAMDISK_FRAGMENTS := dlkm
BOARD_VENDOR_RAMDISK_FRAGMENT.dlkm.PREBUILT := $(OPENBOOK_KERNEL_DIR)/vendor_boot-ramdisk.lz4
BOARD_VENDOR_RAMDISK_FRAGMENT.dlkm.MKBOOTIMG_ARGS := --ramdisk_type DLKM

# vendor_boot command line and static bootconfig. The loader adds the per-boot values: slot, AVB state, vbmeta
# digest, androidboot.boot_part_uuid (docs/installer.md §2.1). No console: the panel shows the firmware logo
# until amdgpu takes over; VM test entries add console=ttyS0.
BOARD_KERNEL_CMDLINE += firmware_class.path=/vendor/firmware log_buf_len=1M
BOARD_BOOTCONFIG += androidboot.hardware=openbook
ifneq ($(OPENBOOK_BOOT_DEVICES),)
BOARD_BOOTCONFIG += androidboot.boot_devices=$(OPENBOOK_BOOT_DEVICES)
endif

# ---------------------------------------------------------------- partitions
# GPT on the disk (scripts/g14-image.sh): EFI, misc, boot/init_boot/vendor_boot/vbmeta A/B, metadata, super,
# userdata. super holds slot A only; virtual A/B keeps the other slot's copy-on-write data in /data.
BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_USES_SYSTEM_EXTIMAGE := true
BOARD_SYSTEM_EXTIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_USES_PRODUCTIMAGE := true
BOARD_PRODUCTIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_USES_VENDORIMAGE := true
BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_USES_VENDOR_DLKMIMAGE := true
BOARD_VENDOR_DLKMIMAGE_FILE_SYSTEM_TYPE := erofs
TARGET_COPY_OUT_VENDOR_DLKM := vendor_dlkm
BOARD_PREBUILT_VENDOR_DLKMIMAGE := $(OPENBOOK_KERNEL_DIR)/vendor_dlkm.img
BOARD_USES_SYSTEM_DLKMIMAGE := true
BOARD_SYSTEM_DLKMIMAGE_FILE_SYSTEM_TYPE := erofs
TARGET_COPY_OUT_SYSTEM_DLKM := system_dlkm
BOARD_PREBUILT_SYSTEM_DLKMIMAGE := $(OPENBOOK_KERNEL_DIR)/system_dlkm.img
BOARD_USES_METADATA_PARTITION := true
TARGET_USERIMAGES_USE_F2FS := true
BOARD_USERDATAIMAGE_FILE_SYSTEM_TYPE := f2fs
BOARD_USERDATAIMAGE_PARTITION_SIZE := 1073741824

BOARD_SUPER_PARTITION_SIZE := 8589934592
BOARD_SUPER_PARTITION_GROUPS := openbook_dynamic_partitions
BOARD_OPENBOOK_DYNAMIC_PARTITIONS_PARTITION_LIST := system system_ext product vendor vendor_dlkm system_dlkm
BOARD_OPENBOOK_DYNAMIC_PARTITIONS_SIZE := 8585740288
BOARD_BUILD_SUPER_IMAGE_BY_DEFAULT := true

AB_OTA_UPDATER := true
AB_OTA_PARTITIONS += boot init_boot vendor_boot vbmeta system system_ext product vendor vendor_dlkm system_dlkm

# ---------------------------------------------------------------- verified boot
# One vbmeta verifies everything, as on Googlebook: hash descriptors for boot, init_boot and vendor_boot, hashtree
# descriptors for the six logical partitions. Signed with AOSP's test key. With Secure Boot off and an unlocked
# device the loader reports orange: dm-verity still runs, but OpenBook does NOT claim verified boot.
BOARD_AVB_ENABLE := true
BOARD_AVB_ALGORITHM := SHA256_RSA4096
BOARD_AVB_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_SYSTEM_ADD_HASHTREE_FOOTER_ARGS += --hash_algorithm sha256
BOARD_AVB_SYSTEM_EXT_ADD_HASHTREE_FOOTER_ARGS += --hash_algorithm sha256
BOARD_AVB_PRODUCT_ADD_HASHTREE_FOOTER_ARGS += --hash_algorithm sha256
BOARD_AVB_VENDOR_ADD_HASHTREE_FOOTER_ARGS += --hash_algorithm sha256

# ---------------------------------------------------------------- the rest
TARGET_USES_HWC2 := true
USE_OPENGL_RENDERER := true
TARGET_VULKAN_SUPPORT := true
BOARD_USES_GENERIC_AUDIO := false
BOARD_MALLOC_ALIGNMENT := 16

BOARD_VENDOR_SEPOLICY_DIRS += device/anybook/common/pc/sepolicy/vendor
# Platform-side rules for AOSP's own media daemons on this kernel (Codec2 queues; see the .te).
SYSTEM_EXT_PRIVATE_SEPOLICY_DIRS += device/anybook/common/pc/sepolicy/system_ext
# The installer's daemon and the whole-disk label it writes through (ANAL-191).
include device/anybook/common/installer/BoardConfig.mk

# Wi-Fi: AOSP's wpa_supplicant over nl80211, with its own init service (WIFI_HIDL_UNIFIED_...) and OpenBook's
# DRIVER-command hook (wifi/driver_cmd_openbook.c: COUNTRY through nl80211). No BOARD_WLAN_DEVICE: there is no
# vendor Wi-Fi HAL (wifi/wifi.mk).
BOARD_WPA_SUPPLICANT_DRIVER := NL80211
BOARD_WPA_SUPPLICANT_PRIVATE_LIB := lib_driver_cmd_openbook
WPA_SUPPLICANT_VERSION := VER_0_8_X
WIFI_HIDL_UNIFIED_SUPPLICANT_SERVICE_RC_ENTRY := true
# Lets Soong build AOSP's hostapd, which the image does not install: the QEMU Wi-Fi test runs it as the access
# point on a second simulated radio (scripts/audio-net-qemu.sh).
BOARD_HOSTAPD_DRIVER := NL80211

# Software rendering (SwiftShader under ANGLE) for GPUs no OpenBook driver handles: what VMs display with. It
# needs execmem in four system domains (sepolicy/swiftshader). Set false (and drop vulkan.pastel from the product)
# for an image that should refuse to run without a supported GPU.
OPENBOOK_SOFTWARE_GPU_FALLBACK ?= true
ifeq ($(OPENBOOK_SOFTWARE_GPU_FALLBACK),true)
BOARD_VENDOR_SEPOLICY_DIRS += device/anybook/common/pc/sepolicy/swiftshader
endif
