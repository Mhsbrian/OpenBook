// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "sensors.h"

#include <map>

#include <android-base/strings.h>

namespace openbook {

namespace {

int ZoneType(const std::string& type) {
    // Only names that say what they measure get a type. ACPI zones (acpitz) can be anything from the CPU package
    // to a chassis sensor, so they stay UNKNOWN until a device layer knows better.
    if (type == "x86_pkg_temp" || type == "k10temp" || type == "cpu-thermal") return temp_type::kCpu;
    if (android::base::StartsWith(type, "iwlwifi") || android::base::StartsWith(type, "mt79")) return temp_type::kWifi;
    return temp_type::kUnknown;
}

int HwmonType(const std::string& chip) {
    if (chip == "k10temp" || chip == "coretemp" || chip == "zenpower") return temp_type::kCpu;
    if (chip == "amdgpu" || chip == "nouveau" || chip == "i915" || chip == "xe") return temp_type::kGpu;
    if (android::base::StartsWith(chip, "mt79") || android::base::StartsWith(chip, "iwlwifi")) return temp_type::kWifi;
    return temp_type::kUnknown;
}

int CoolerType(const std::string& type) {
    if (type == "Processor" || android::base::StartsWith(type, "intel_powerclamp")) return cooling_type::kCpu;
    if (type == "Fan" || android::base::StartsWith(type, "fan")) return cooling_type::kFan;
    if (android::base::StartsWith(type, "amdgpu")) return cooling_type::kGpu;
    return cooling_type::kComponent;
}

// Kernel trip point types to Android severities: the kernel itself acts at "critical" (orderly shutdown), so that
// is SHUTDOWN; "hot" is CRITICAL; "passive" (the kernel starts throttling) is SEVERE.
int TripSeverity(const std::string& trip) {
    if (trip == "critical") return kShutdown;
    if (trip == "hot") return kCritical;
    if (trip == "passive") return kSevere;
    return -1;
}

void SetLower(std::array<float, kSeverities>* hot, int severity, float celsius) {
    if (severity < 0) return;
    float& t = (*hot)[severity];
    if (std::isnan(t) || celsius < t) t = celsius;
}

}  // namespace

void ThermalSensors::Discover() {
    sensors_.clear();
    coolers_.clear();
    AddThermalZones();
    AddHwmon();
    AddBatteries();
    AddCoolers();
}

void ThermalSensors::AddThermalZones() {
    std::map<std::string, int> seen;
    for (const auto& z : sysfs_.List("/sys/class/thermal")) {
        if (!android::base::StartsWith(z, "thermal_zone")) continue;
        const std::string dir = "/sys/class/thermal/" + z;
        auto type = sysfs_.Read(dir + "/type");
        if (!type || !sysfs_.Exists(dir + "/temp")) continue;
        Sensor s;
        s.name = *type + "-" + std::to_string(seen[*type]++);
        s.type = ZoneType(*type);
        s.input = dir + "/temp";
        for (int i = 0;; i++) {
            const std::string trip = dir + "/trip_point_" + std::to_string(i);
            auto ttype = sysfs_.Read(trip + "_type");
            auto ttemp = sysfs_.ReadInt(trip + "_temp");
            if (!ttype) break;
            if (ttemp && *ttemp > 0) SetLower(&s.hot, TripSeverity(*ttype), *ttemp / 1000.0f);
        }
        sensors_.push_back(s);
    }
}

void ThermalSensors::AddHwmon() {
    for (const auto& h : sysfs_.List("/sys/class/hwmon")) {
        const std::string dir = "/sys/class/hwmon/" + h;
        auto chip = sysfs_.Read(dir + "/name");
        if (!chip) continue;
        // ACPI zones and power supplies also register hwmon chips; they are read directly above and below.
        if (*chip == "acpitz" || android::base::StartsWith(*chip, "BAT") || *chip == "ACAD" || *chip == "AC") continue;
        for (const auto& f : sysfs_.List(dir)) {
            if (!android::base::StartsWith(f, "temp") || !android::base::EndsWith(f, "_input")) continue;
            const std::string base = dir + "/" + f.substr(0, f.size() - std::string("_input").size());
            Sensor s;
            auto label = sysfs_.Read(base + "_label");
            s.name = *chip + "-" + (label ? *label : f.substr(0, f.find('_')));
            s.type = HwmonType(*chip);
            s.input = dir + "/" + f;
            if (auto v = sysfs_.ReadInt(base + "_max"); v && *v > 0) SetLower(&s.hot, kSevere, *v / 1000.0f);
            if (auto v = sysfs_.ReadInt(base + "_crit"); v && *v > 0) SetLower(&s.hot, kCritical, *v / 1000.0f);
            if (auto v = sysfs_.ReadInt(base + "_emergency"); v && *v > 0) SetLower(&s.hot, kShutdown, *v / 1000.0f);
            sensors_.push_back(s);
        }
    }
}

void ThermalSensors::AddBatteries() {
    for (const auto& p : sysfs_.List("/sys/class/power_supply")) {
        const std::string dir = "/sys/class/power_supply/" + p;
        if (sysfs_.Read(dir + "/type").value_or("") != "Battery" || !sysfs_.Exists(dir + "/temp")) continue;
        Sensor s;
        s.name = p;
        s.type = temp_type::kBattery;
        s.input = dir + "/temp";
        s.scale = 0.1;  // power_supply reports tenths of a degree
        sensors_.push_back(s);
    }
}

void ThermalSensors::AddCoolers() {
    std::map<std::string, int> seen;
    for (const auto& c : sysfs_.List("/sys/class/thermal")) {
        if (!android::base::StartsWith(c, "cooling_device")) continue;
        const std::string dir = "/sys/class/thermal/" + c;
        auto type = sysfs_.Read(dir + "/type");
        if (!type || !sysfs_.Exists(dir + "/cur_state")) continue;
        Cooler k;
        k.name = *type + "-" + std::to_string(seen[*type]++);
        k.type = CoolerType(*type);
        k.cur_state = dir + "/cur_state";
        coolers_.push_back(k);
    }
}

std::optional<float> ThermalSensors::Read(const Sensor& s) const {
    auto v = sysfs_.ReadInt(s.input);
    if (!v) return std::nullopt;
    return static_cast<float>(*v * s.scale);
}

std::optional<long> ThermalSensors::ReadCooler(const Cooler& c) const {
    auto v = sysfs_.ReadInt(c.cur_state);
    if (!v) return std::nullopt;
    return static_cast<long>(*v);
}

int ThermalSensors::Severity(float celsius, const std::array<float, kSeverities>& hot) {
    int sev = 0;
    for (int i = 1; i < kSeverities; i++) {
        if (!std::isnan(hot[i]) && celsius >= hot[i]) sev = i;
    }
    return sev;
}

}  // namespace openbook
