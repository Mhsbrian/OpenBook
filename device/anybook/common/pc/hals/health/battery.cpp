// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "battery.h"

#include <algorithm>

namespace openbook {

namespace {

constexpr const char* kPowerSupply = "/sys/class/power_supply";

// uWh -> uAh at the design voltage (uV), the way the kernel's ACPI battery driver converts the other way.
std::optional<int64_t> EnergyToCharge(std::optional<int64_t> uwh, std::optional<int64_t> uv) {
    if (!uwh || !uv || *uv <= 0) return std::nullopt;
    return *uwh * 1000000 / *uv;
}

}  // namespace

std::optional<BatteryFacts> ReadBattery(const Sysfs& sysfs) {
    for (const auto& name : sysfs.List(kPowerSupply)) {
        const std::string dir = std::string(kPowerSupply) + "/" + name;
        if (sysfs.Read(dir + "/type").value_or("") != "Battery") continue;
        if (sysfs.Read(dir + "/scope").value_or("") == "Device") continue;
        if (sysfs.ReadInt(dir + "/present").value_or(1) == 0) continue;
        BatteryFacts b;
        b.name = name;
        b.charge_now_uah = sysfs.ReadInt(dir + "/charge_now");
        b.full_uah = sysfs.ReadInt(dir + "/charge_full");
        b.design_uah = sysfs.ReadInt(dir + "/charge_full_design");
        const auto uv = sysfs.ReadInt(dir + "/voltage_min_design");
        if (!b.charge_now_uah) b.charge_now_uah = EnergyToCharge(sysfs.ReadInt(dir + "/energy_now"), uv);
        if (!b.full_uah) b.full_uah = EnergyToCharge(sysfs.ReadInt(dir + "/energy_full"), uv);
        if (!b.design_uah) b.design_uah = EnergyToCharge(sysfs.ReadInt(dir + "/energy_full_design"), uv);
        if (b.full_uah && b.design_uah && *b.design_uah > 0 && *b.full_uah > 0) {
            b.state_of_health_percent =
                    static_cast<int>(std::min<int64_t>(100, *b.full_uah * 100 / *b.design_uah));
        }
        return b;
    }
    return std::nullopt;
}

BatteryCondition ConditionFromStateOfHealth(int percent) {
    return percent >= 80 ? BatteryCondition::kGood : BatteryCondition::kFair;
}

}  // namespace openbook
