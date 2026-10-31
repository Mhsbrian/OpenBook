// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// The ACPI battery of a PC, read from /sys/class/power_supply. AOSP's BatteryMonitor takes the charge counter from
// charge_counter, the health from health and the state of health from state_of_health or health_index: phone fuel
// gauges have them, ACPI batteries do not (the GA403WR's BAT1 has charge_now, charge_full and charge_full_design,
// all in uAh). Some ACPI batteries report energy (energy_*, uWh) instead of charge; those are converted with the
// design voltage.

#pragma once

#include <cstdint>
#include <optional>
#include <string>

#include "sysfs.h"

namespace openbook {

struct BatteryFacts {
    std::string name;                            // e.g. BAT1
    std::optional<int64_t> charge_now_uah;       // charge_now, or energy_now converted
    std::optional<int64_t> full_uah;             // charge_full, or energy_full converted
    std::optional<int64_t> design_uah;           // charge_full_design, or energy_full_design converted
    std::optional<int> state_of_health_percent;  // full / design, 0..100
};

// The first present battery (type "Battery", scope not "Device": not a mouse or a headset).
std::optional<BatteryFacts> ReadBattery(const Sysfs& sysfs);

enum class BatteryCondition { kGood, kFair };
// Below 80 % of its design capacity a laptop battery counts as worn (FAIR); never DEAD from capacity alone.
BatteryCondition ConditionFromStateOfHealth(int percent);

}  // namespace openbook
