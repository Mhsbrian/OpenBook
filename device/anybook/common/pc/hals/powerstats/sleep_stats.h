// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// s2idle residency from /sys/power/suspend_stats. On AMD the amd_pmc driver reports how long the SoC really sat in
// its hardware sleep state (S0i3) during each suspend (total_hw_sleep, microseconds; Linux 6.4+). There is no RAPL
// powercap in the OpenBook kernel, so there are no energy meters.

#pragma once

#include <cstdint>
#include <optional>

#include "sysfs.h"

namespace openbook {

struct SleepResidency {
    int64_t suspends = 0;          // successful suspends (success)
    int64_t hw_sleep_ms = 0;       // total time in hardware sleep (total_hw_sleep / 1000)
    int64_t last_hw_sleep_ms = 0;  // the last suspend's hardware sleep (last_hw_sleep / 1000)
};

// nullopt when the kernel does not report hardware sleep (no amd_pmc/intel_pmc_core, or a VM).
std::optional<SleepResidency> ReadSleepResidency(const Sysfs& sysfs);

}  // namespace openbook
