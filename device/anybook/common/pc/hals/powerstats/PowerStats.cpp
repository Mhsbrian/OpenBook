// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#define LOG_TAG "openbook.powerstats"

#include "PowerStats.h"

#include <android-base/logging.h>

namespace aidl::android::hardware::power::stats {

namespace {
constexpr int32_t kSocId = 0;
constexpr int32_t kS0i3Id = 0;
}  // namespace

PowerStats::PowerStats(openbook::Sysfs sysfs) : sysfs_(std::move(sysfs)) {
    available_ = openbook::ReadSleepResidency(sysfs_).has_value();
    LOG(INFO) << (available_ ? "reporting s2idle hardware sleep residency"
                             : "the kernel reports no hardware sleep; no power entities");
}

ndk::ScopedAStatus PowerStats::getPowerEntityInfo(std::vector<PowerEntity>* _aidl_return) {
    _aidl_return->clear();
    if (!available_) return ndk::ScopedAStatus::ok();
    PowerEntity soc;
    soc.id = kSocId;
    soc.name = "SoC";
    State s0i3;
    s0i3.id = kS0i3Id;
    s0i3.name = "S0i3";
    soc.states.push_back(s0i3);
    _aidl_return->push_back(soc);
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus PowerStats::getStateResidency(const std::vector<int32_t>& in_powerEntityIds,
                                                 std::vector<StateResidencyResult>* _aidl_return) {
    _aidl_return->clear();
    if (!available_) {
        return in_powerEntityIds.empty() ? ndk::ScopedAStatus::ok()
                                         : ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
    }
    for (int32_t id : in_powerEntityIds) {
        if (id != kSocId) return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
    }
    auto r = openbook::ReadSleepResidency(sysfs_);
    if (!r) return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_STATE);
    StateResidency res;
    res.id = kS0i3Id;
    res.totalTimeInStateMs = r->hw_sleep_ms;
    res.totalStateEntryCount = r->suspends;
    res.lastEntryTimestampMs = 0;  // not reported by the kernel
    StateResidencyResult result;
    result.id = kSocId;
    result.stateResidencyData.push_back(res);
    _aidl_return->push_back(result);
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus PowerStats::getEnergyConsumerInfo(std::vector<EnergyConsumer>* _aidl_return) {
    _aidl_return->clear();
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus PowerStats::getEnergyConsumed(const std::vector<int32_t>& in_energyConsumerIds,
                                                 std::vector<EnergyConsumerResult>* _aidl_return) {
    _aidl_return->clear();
    return in_energyConsumerIds.empty() ? ndk::ScopedAStatus::ok()
                                        : ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
}

ndk::ScopedAStatus PowerStats::getEnergyMeterInfo(std::vector<Channel>* _aidl_return) {
    _aidl_return->clear();
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus PowerStats::readEnergyMeter(const std::vector<int32_t>& in_channelIds,
                                               std::vector<EnergyMeasurement>* _aidl_return) {
    _aidl_return->clear();
    return in_channelIds.empty() ? ndk::ScopedAStatus::ok()
                                 : ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
}

}  // namespace aidl::android::hardware::power::stats
