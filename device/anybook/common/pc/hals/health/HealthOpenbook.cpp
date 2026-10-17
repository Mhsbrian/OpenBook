// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "HealthOpenbook.h"

#include <algorithm>
#include <limits>

namespace aidl::android::hardware::health {

namespace {

int32_t ClampInt(int64_t v) {
    return static_cast<int32_t>(std::min<int64_t>(v, std::numeric_limits<int32_t>::max()));
}

}  // namespace

void HealthOpenbook::UpdateHealthInfo(HealthInfo* h) {
    const auto b = openbook::ReadBattery(sysfs_);
    if (!b) return;
    if (h->batteryChargeCounterUah == 0 && b->charge_now_uah) h->batteryChargeCounterUah = ClampInt(*b->charge_now_uah);
    if (h->batteryFullChargeUah == 0 && b->full_uah) h->batteryFullChargeUah = ClampInt(*b->full_uah);
    if (h->batteryFullChargeDesignCapacityUah == 0 && b->design_uah) {
        h->batteryFullChargeDesignCapacityUah = ClampInt(*b->design_uah);
    }
    if (!b->state_of_health_percent) return;
    if (!h->batteryHealthData) h->batteryHealthData = BatteryHealthData{};
    if (h->batteryHealthData->batteryStateOfHealth == 0) {
        h->batteryHealthData->batteryStateOfHealth = *b->state_of_health_percent;
    }
    if (h->batteryHealth == BatteryHealth::UNKNOWN) {
        h->batteryHealth = openbook::ConditionFromStateOfHealth(*b->state_of_health_percent) ==
                                           openbook::BatteryCondition::kGood
                                   ? BatteryHealth::GOOD
                                   : BatteryHealth::FAIR;
    }
}

ndk::ScopedAStatus HealthOpenbook::getChargeCounterUah(int32_t* out) {
    if (auto status = Health::getChargeCounterUah(out); status.isOk() && *out != 0) return status;
    const auto b = openbook::ReadBattery(sysfs_);
    if (!b || !b->charge_now_uah) {
        return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
    }
    *out = ClampInt(*b->charge_now_uah);
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus HealthOpenbook::getBatteryHealthData(BatteryHealthData* out) {
    auto status = Health::getBatteryHealthData(out);
    if (out->batteryStateOfHealth == 0) {
        if (const auto b = openbook::ReadBattery(sysfs_); b && b->state_of_health_percent) {
            out->batteryStateOfHealth = *b->state_of_health_percent;
        }
    }
    return status;
}

}  // namespace aidl::android::hardware::health
