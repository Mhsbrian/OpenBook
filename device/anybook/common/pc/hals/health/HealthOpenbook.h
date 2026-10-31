// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// AOSP's health HAL (libhealth_aidl_impl, BatteryMonitor on /sys/class/power_supply) plus what a PC's ACPI battery
// can tell but BatteryMonitor does not read: the charge counter from charge_now, the state of health from
// charge_full / charge_full_design, and a health verdict from it when the kernel reports none. Values the kernel
// does report are left as BatteryMonitor read them.

#pragma once

#include <health-impl/Health.h>

#include "battery.h"
#include "sysfs.h"

namespace aidl::android::hardware::health {

class HealthOpenbook : public Health {
  public:
    HealthOpenbook(std::string_view instance, std::unique_ptr<struct healthd_config>&& config,
                   openbook::Sysfs sysfs)
        : Health(instance, std::move(config)), sysfs_(std::move(sysfs)) {}

    ndk::ScopedAStatus getChargeCounterUah(int32_t* out) override;
    ndk::ScopedAStatus getBatteryHealthData(BatteryHealthData* out) override;

  protected:
    void UpdateHealthInfo(HealthInfo* health_info) override;

  private:
    openbook::Sysfs sysfs_;
};

}  // namespace aidl::android::hardware::health
