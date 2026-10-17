# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Wi-Fi on an OpenBook PC (product half; BoardConfig.mk has the supplicant's board variables). The laptop's
# mac80211 driver (mt7925e on the G14) creates wlan0 when vendor_dlkm loads; Android drives it with AOSP's
# wpa_supplicant (AIDL) and wificond, both over standard nl80211. There is no vendor Wi-Fi HAL: AOSP's
# libwifi_hal knows a "desktop" WLAN device whose implementation (libwifi-hal-desktop) is not public, and the
# framework supports running without one (WifiNative: "Vendor Hal not supported"), taking the interface name
# from wifi.interface. What that costs is listed in docs/g14-audio-net.md.

PRODUCT_PACKAGES += \
    wpa_supplicant \
    wpa_supplicant.conf.openbook \
    wpa_supplicant_overlay.conf.openbook \
    OpenBookWifiOverlay

PRODUCT_COPY_FILES += \
    frameworks/native/data/etc/android.hardware.wifi.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.wifi.xml

PRODUCT_VENDOR_PROPERTIES += wifi.interface=wlan0

# cfg80211's regulatory database (wireless-regdb, ISC), signed by its maintainer: the kernel checks the .p7s
# against the keys built into cfg80211 (sforshee, wens) and loads it through firmware_class.path=/vendor/firmware.
# AOSP 17 carries it in external/wireless-regdb (2025-10-07) for the unpublished device/google/desktop only, so
# it is copied rather than depended on.
PRODUCT_COPY_FILES += \
    external/wireless-regdb/regulatory.db:$(TARGET_COPY_OUT_VENDOR)/firmware/regulatory.db \
    external/wireless-regdb/regulatory.db.p7s:$(TARGET_COPY_OUT_VENDOR)/firmware/regulatory.db.p7s \
    external/wireless-regdb/LICENSE:$(TARGET_COPY_OUT_VENDOR)/firmware/LICENSE.wireless-regdb

# Throughput and link tests on userdebug (openbook-hwtest).
PRODUCT_PACKAGES_DEBUG += \
    iperf3 \
    iw
