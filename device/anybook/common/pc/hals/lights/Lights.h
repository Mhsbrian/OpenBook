// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <mutex>
#include <optional>

#include <aidl/android/hardware/light/BnLights.h>

#include "backlight.h"

namespace aidl::android::hardware::light {

// ILights with one light, the panel backlight. The keyboard backlight belongs to the keyboard's input device
// (device.additionalSysfsLedsNode in its .idc), as on Googlebook.
class Lights : public BnLights {
  public:
    explicit Lights(openbook::Sysfs sysfs);

    ndk::ScopedAStatus setLightState(int32_t id, const HwLightState& state) override;
    ndk::ScopedAStatus getLights(std::vector<HwLight>* lights) override;
    ndk::ScopedAStatus setLightEffects(const std::vector<HwLightEffect>& effects) override;

  private:
    openbook::Sysfs sysfs_;
    std::mutex lock_;
    std::optional<openbook::Backlight> backlight_;
};

}  // namespace aidl::android::hardware::light
