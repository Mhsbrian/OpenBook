// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "sleep_stats.h"

namespace openbook {

std::optional<SleepResidency> ReadSleepResidency(const Sysfs& sysfs) {
    auto total = sysfs.ReadInt("/sys/power/suspend_stats/total_hw_sleep");
    if (!total) return std::nullopt;
    SleepResidency r;
    r.hw_sleep_ms = *total / 1000;
    r.suspends = sysfs.ReadInt("/sys/power/suspend_stats/success").value_or(0);
    r.last_hw_sleep_ms = sysfs.ReadInt("/sys/power/suspend_stats/last_hw_sleep").value_or(0) / 1000;
    return r;
}

}  // namespace openbook
