// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Temperature sensors and cooling devices of a PC, from sysfs: ACPI and other thermal zones, hwmon chips (amdgpu,
// k10temp, NVMe, Wi-Fi) and the battery. Types are android.hardware.thermal's TemperatureType and CoolingType
// values, kept as ints so this part builds and tests without AIDL.

#pragma once

#include <array>
#include <cmath>
#include <optional>
#include <string>
#include <vector>

#include "sysfs.h"

namespace openbook {

namespace temp_type {
constexpr int kUnknown = -1, kCpu = 0, kGpu = 1, kBattery = 2, kSkin = 3, kNpu = 9, kWifi = 14;
}
namespace cooling_type {
constexpr int kFan = 0, kCpu = 2, kGpu = 3, kComponent = 6;
}
// ThrottlingSeverity: NONE LIGHT MODERATE SEVERE CRITICAL EMERGENCY SHUTDOWN.
constexpr int kSeverities = 7;
constexpr int kSevere = 3, kCritical = 4, kShutdown = 6;

struct Sensor {
    std::string name;   // e.g. acpitz-0, amdgpu-edge, nvme-Composite, BAT1
    int type = temp_type::kUnknown;
    std::string input;  // file to read
    double scale = 0.001;  // file units to degrees Celsius (thermal zones and hwmon: millidegrees)
    std::array<float, kSeverities> hot;  // threshold per severity, NaN where none
    Sensor() { hot.fill(NAN); }
};

struct Cooler {
    std::string name;  // e.g. Processor-0, Fan-1
    int type = cooling_type::kComponent;
    std::string cur_state;
};

class ThermalSensors {
  public:
    explicit ThermalSensors(Sysfs sysfs) : sysfs_(std::move(sysfs)) {}

    // Scans sysfs. Called at start and again when a sensor's file disappears (a module reloaded).
    void Discover();
    const std::vector<Sensor>& sensors() const { return sensors_; }
    const std::vector<Cooler>& coolers() const { return coolers_; }
    std::optional<float> Read(const Sensor& s) const;
    std::optional<long> ReadCooler(const Cooler& c) const;

    // Highest severity whose hot threshold the value reached.
    static int Severity(float celsius, const std::array<float, kSeverities>& hot);

  private:
    void AddThermalZones();
    void AddHwmon();
    void AddBatteries();
    void AddCoolers();

    Sysfs sysfs_;
    std::vector<Sensor> sensors_;
    std::vector<Cooler> coolers_;
};

}  // namespace openbook
