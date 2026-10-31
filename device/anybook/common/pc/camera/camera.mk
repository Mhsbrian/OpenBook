# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
# The G14's built-in webcam is USB UVC (3277:0060), not an AMD/Intel ISP.
# Keep AOSP's camera permission/privacy path and its hal_camera_default domain.
PRODUCT_PACKAGES += android.hardware.camera.provider-V1-external-service
DEVICE_MANIFEST_FILE += device/anybook/common/pc/camera/manifest.xml
PRODUCT_COPY_FILES += \
    device/anybook/common/pc/camera/external_camera_config.xml:$(TARGET_COPY_OUT_VENDOR)/etc/external_camera_config.xml \
    frameworks/native/data/etc/android.hardware.camera.external.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.camera.external.xml
