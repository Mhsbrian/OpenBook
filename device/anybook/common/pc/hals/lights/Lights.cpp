// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#define LOG_TAG "openbook.lights"

#include "Lights.h"

#include <android-base/logging.h>

namespace aidl::android::hardware::light {

namespace {
constexpr int32_t kBacklightId = 0;
}

Lights::Lights(openbook::Sysfs sysfs) : sysfs_(std::move(sysfs)) {
    backlight_ = openbook::PickBacklight(sysfs_);
    if (backlight_) {
        LOG(INFO) << "backlight " << backlight_->name << " (" << backlight_->type << ", max "
                  << backlight_->max << ")";
    } else {
        LOG(INFO) << "no backlight device; reporting no lights";
    }
}

ndk::ScopedAStatus Lights::setLightState(int32_t id, const HwLightState& state) {
    std::lock_guard<std::mutex> l(lock_);
    if (id != kBacklightId || !backlight_) {
        return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
    }
    // ARGB to luminance, as AOSP's lights implementations do.
    const uint32_t c = static_cast<uint32_t>(state.color);
    const int brightness = (77 * ((c >> 16) & 0xff) + 150 * ((c >> 8) & 0xff) + 29 * (c & 0xff)) >> 8;
    const int64_t value = openbook::ScaleBrightness(brightness, backlight_->max);
    if (!sysfs_.Write("/sys/class/backlight/" + backlight_->name + "/brightness", std::to_string(value))) {
        PLOG(ERROR) << "writing " << backlight_->name << " brightness " << value;
        return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_STATE);
    }
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Lights::getLights(std::vector<HwLight>* lights) {
    std::lock_guard<std::mutex> l(lock_);
    lights->clear();
    if (backlight_) {
        HwLight light;
        light.id = kBacklightId;
        light.ordinal = 0;
        light.type = LightType::BACKLIGHT;
        lights->push_back(light);
    }
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Lights::setLightEffects(const std::vector<HwLightEffect>&) {
    return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
}

}  // namespace aidl::android::hardware::light
