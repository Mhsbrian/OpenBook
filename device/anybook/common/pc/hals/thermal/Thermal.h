// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <condition_variable>
#include <map>
#include <mutex>
#include <thread>
#include <vector>

#include <aidl/android/hardware/thermal/BnThermal.h>

#include "sensors.h"

namespace aidl::android::hardware::thermal {

// IThermal on sysfs (sensors.h). A thread polls every 5 s while callbacks are registered and reports sensors whose
// severity changed, and cooling devices whose state changed.
class Thermal : public BnThermal {
  public:
    explicit Thermal(openbook::Sysfs sysfs);
    ~Thermal() override;

    ndk::ScopedAStatus getCoolingDevices(std::vector<CoolingDevice>* _aidl_return) override;
    ndk::ScopedAStatus getCoolingDevicesWithType(CoolingType type, std::vector<CoolingDevice>* _aidl_return) override;
    ndk::ScopedAStatus getTemperatures(std::vector<Temperature>* _aidl_return) override;
    ndk::ScopedAStatus getTemperaturesWithType(TemperatureType type, std::vector<Temperature>* _aidl_return) override;
    ndk::ScopedAStatus getTemperatureThresholds(std::vector<TemperatureThreshold>* _aidl_return) override;
    ndk::ScopedAStatus getTemperatureThresholdsWithType(TemperatureType type,
                                                        std::vector<TemperatureThreshold>* _aidl_return) override;
    ndk::ScopedAStatus registerThermalChangedCallback(const std::shared_ptr<IThermalChangedCallback>& cb) override;
    ndk::ScopedAStatus registerThermalChangedCallbackWithType(const std::shared_ptr<IThermalChangedCallback>& cb,
                                                              TemperatureType type) override;
    ndk::ScopedAStatus unregisterThermalChangedCallback(const std::shared_ptr<IThermalChangedCallback>& cb) override;
    ndk::ScopedAStatus registerCoolingDeviceChangedCallbackWithType(
            const std::shared_ptr<ICoolingDeviceChangedCallback>& cb, CoolingType type) override;
    ndk::ScopedAStatus unregisterCoolingDeviceChangedCallback(
            const std::shared_ptr<ICoolingDeviceChangedCallback>& cb) override;
    ndk::ScopedAStatus forecastSkinTemperature(int32_t forecastSeconds, float* _aidl_return) override;

  private:
    struct TempCallback {
        std::shared_ptr<IThermalChangedCallback> cb;
        bool filter;
        TemperatureType type;
    };
    struct CoolCallback {
        std::shared_ptr<ICoolingDeviceChangedCallback> cb;
        CoolingType type;
    };

    std::vector<Temperature> ReadTemperatures(bool filter, TemperatureType type);
    std::vector<CoolingDevice> ReadCoolers(bool filter, CoolingType type);
    void Poll();

    std::mutex lock_;
    std::condition_variable wake_;
    bool stop_ = false;
    openbook::ThermalSensors sensors_;
    std::vector<TempCallback> temp_callbacks_;
    std::vector<CoolCallback> cool_callbacks_;
    std::map<std::string, int> last_severity_;
    std::map<std::string, long> last_cooler_;
    std::thread poller_;
};

}  // namespace aidl::android::hardware::thermal
