// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <aidl/android/hardware/power/stats/BnPowerStats.h>

#include "sleep_stats.h"

namespace aidl::android::hardware::power::stats {

// IPowerStats with one power entity, "SoC", and one state, "S0i3": the hardware sleep residency the PMC driver
// reports for s2idle. No energy consumers or meters.
class PowerStats : public BnPowerStats {
  public:
    explicit PowerStats(openbook::Sysfs sysfs);

    ndk::ScopedAStatus getPowerEntityInfo(std::vector<PowerEntity>* _aidl_return) override;
    ndk::ScopedAStatus getStateResidency(const std::vector<int32_t>& in_powerEntityIds,
                                         std::vector<StateResidencyResult>* _aidl_return) override;
    ndk::ScopedAStatus getEnergyConsumerInfo(std::vector<EnergyConsumer>* _aidl_return) override;
    ndk::ScopedAStatus getEnergyConsumed(const std::vector<int32_t>& in_energyConsumerIds,
                                         std::vector<EnergyConsumerResult>* _aidl_return) override;
    ndk::ScopedAStatus getEnergyMeterInfo(std::vector<Channel>* _aidl_return) override;
    ndk::ScopedAStatus readEnergyMeter(const std::vector<int32_t>& in_channelIds,
                                       std::vector<EnergyMeasurement>* _aidl_return) override;

  private:
    openbook::Sysfs sysfs_;
    bool available_;
};

}  // namespace aidl::android::hardware::power::stats
