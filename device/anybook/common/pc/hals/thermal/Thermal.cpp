// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#define LOG_TAG "openbook.thermal"

#include "Thermal.h"

#include <chrono>

#include <android-base/logging.h>

namespace aidl::android::hardware::thermal {

namespace {

constexpr auto kPollInterval = std::chrono::seconds(5);

template <typename T>
bool SameBinder(const std::shared_ptr<T>& a, const std::shared_ptr<T>& b) {
    return a->asBinder() == b->asBinder();
}

}  // namespace

Thermal::Thermal(openbook::Sysfs sysfs) : sensors_(std::move(sysfs)) {
    sensors_.Discover();
    for (const auto& s : sensors_.sensors()) {
        LOG(INFO) << "sensor " << s.name << " type " << s.type << " (" << s.input << ")";
    }
    for (const auto& c : sensors_.coolers()) LOG(INFO) << "cooling device " << c.name << " type " << c.type;
    poller_ = std::thread([this] { Poll(); });
}

Thermal::~Thermal() {
    {
        std::lock_guard<std::mutex> l(lock_);
        stop_ = true;
    }
    wake_.notify_all();
    poller_.join();
}

std::vector<Temperature> Thermal::ReadTemperatures(bool filter, TemperatureType type) {
    std::vector<Temperature> out;
    for (const auto& s : sensors_.sensors()) {
        if (filter && static_cast<int>(type) != s.type) continue;
        auto v = sensors_.Read(s);
        if (!v) continue;
        Temperature t;
        t.type = static_cast<TemperatureType>(s.type);
        t.name = s.name;
        t.value = *v;
        t.throttlingStatus = static_cast<ThrottlingSeverity>(openbook::ThermalSensors::Severity(*v, s.hot));
        out.push_back(t);
    }
    return out;
}

std::vector<CoolingDevice> Thermal::ReadCoolers(bool filter, CoolingType type) {
    std::vector<CoolingDevice> out;
    for (const auto& c : sensors_.coolers()) {
        if (filter && static_cast<int>(type) != c.type) continue;
        auto v = sensors_.ReadCooler(c);
        if (!v) continue;
        CoolingDevice d;
        d.type = static_cast<CoolingType>(c.type);
        d.name = c.name;
        d.value = *v;
        out.push_back(d);
    }
    return out;
}

ndk::ScopedAStatus Thermal::getCoolingDevices(std::vector<CoolingDevice>* _aidl_return) {
    std::lock_guard<std::mutex> l(lock_);
    *_aidl_return = ReadCoolers(false, CoolingType::FAN);
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Thermal::getCoolingDevicesWithType(CoolingType type, std::vector<CoolingDevice>* _aidl_return) {
    std::lock_guard<std::mutex> l(lock_);
    *_aidl_return = ReadCoolers(true, type);
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Thermal::getTemperatures(std::vector<Temperature>* _aidl_return) {
    std::lock_guard<std::mutex> l(lock_);
    *_aidl_return = ReadTemperatures(false, TemperatureType::UNKNOWN);
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Thermal::getTemperaturesWithType(TemperatureType type, std::vector<Temperature>* _aidl_return) {
    std::lock_guard<std::mutex> l(lock_);
    *_aidl_return = ReadTemperatures(true, type);
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Thermal::getTemperatureThresholds(std::vector<TemperatureThreshold>* _aidl_return) {
    return getTemperatureThresholdsWithType(TemperatureType::UNKNOWN, _aidl_return);
}

ndk::ScopedAStatus Thermal::getTemperatureThresholdsWithType(TemperatureType type,
                                                             std::vector<TemperatureThreshold>* _aidl_return) {
    // UNKNOWN through getTemperatureThresholds() means "all"; asked for explicitly it filters like any type.
    std::lock_guard<std::mutex> l(lock_);
    _aidl_return->clear();
    for (const auto& s : sensors_.sensors()) {
        if (type != TemperatureType::UNKNOWN && static_cast<int>(type) != s.type) continue;
        TemperatureThreshold t;
        t.type = static_cast<TemperatureType>(s.type);
        t.name = s.name;
        t.hotThrottlingThresholds.assign(s.hot.begin(), s.hot.end());
        t.coldThrottlingThresholds.assign(openbook::kSeverities, NAN);
        _aidl_return->push_back(t);
    }
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Thermal::registerThermalChangedCallback(const std::shared_ptr<IThermalChangedCallback>& cb) {
    if (!cb) return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
    std::lock_guard<std::mutex> l(lock_);
    for (const auto& c : temp_callbacks_) {
        if (SameBinder(c.cb, cb)) return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
    }
    temp_callbacks_.push_back({cb, false, TemperatureType::UNKNOWN});
    wake_.notify_all();
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Thermal::registerThermalChangedCallbackWithType(const std::shared_ptr<IThermalChangedCallback>& cb,
                                                                   TemperatureType type) {
    if (!cb) return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
    std::lock_guard<std::mutex> l(lock_);
    for (const auto& c : temp_callbacks_) {
        if (SameBinder(c.cb, cb)) return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
    }
    temp_callbacks_.push_back({cb, true, type});
    wake_.notify_all();
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Thermal::unregisterThermalChangedCallback(const std::shared_ptr<IThermalChangedCallback>& cb) {
    if (!cb) return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
    std::lock_guard<std::mutex> l(lock_);
    for (auto it = temp_callbacks_.begin(); it != temp_callbacks_.end(); ++it) {
        if (SameBinder(it->cb, cb)) {
            temp_callbacks_.erase(it);
            return ndk::ScopedAStatus::ok();
        }
    }
    return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
}

ndk::ScopedAStatus Thermal::registerCoolingDeviceChangedCallbackWithType(
        const std::shared_ptr<ICoolingDeviceChangedCallback>& cb, CoolingType type) {
    if (!cb) return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
    std::lock_guard<std::mutex> l(lock_);
    for (const auto& c : cool_callbacks_) {
        if (SameBinder(c.cb, cb)) return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
    }
    cool_callbacks_.push_back({cb, type});
    wake_.notify_all();
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Thermal::unregisterCoolingDeviceChangedCallback(
        const std::shared_ptr<ICoolingDeviceChangedCallback>& cb) {
    if (!cb) return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
    std::lock_guard<std::mutex> l(lock_);
    for (auto it = cool_callbacks_.begin(); it != cool_callbacks_.end(); ++it) {
        if (SameBinder(it->cb, cb)) {
            cool_callbacks_.erase(it);
            return ndk::ScopedAStatus::ok();
        }
    }
    return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
}

ndk::ScopedAStatus Thermal::forecastSkinTemperature(int32_t, float*) {
    return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
}

void Thermal::Poll() {
    std::unique_lock<std::mutex> l(lock_);
    while (!stop_) {
        wake_.wait_for(l, kPollInterval, [this] { return stop_; });
        if (stop_) break;
        if (temp_callbacks_.empty() && cool_callbacks_.empty()) continue;

        for (const auto& t : ReadTemperatures(false, TemperatureType::UNKNOWN)) {
            const int sev = static_cast<int>(t.throttlingStatus);
            auto it = last_severity_.find(t.name);
            const bool changed = it == last_severity_.end() ? sev != 0 : it->second != sev;
            last_severity_[t.name] = sev;
            if (!changed) continue;
            LOG(INFO) << t.name << " " << t.value << " C, severity " << sev;
            for (auto c = temp_callbacks_.begin(); c != temp_callbacks_.end();) {
                if (c->filter && c->type != t.type) { ++c; continue; }
                if (c->cb->notifyThrottling(t).getStatus() == STATUS_DEAD_OBJECT) {
                    c = temp_callbacks_.erase(c);
                } else {
                    ++c;
                }
            }
        }
        for (const auto& d : ReadCoolers(false, CoolingType::FAN)) {
            auto it = last_cooler_.find(d.name);
            const bool changed = it != last_cooler_.end() && it->second != d.value;
            last_cooler_[d.name] = d.value;
            if (!changed) continue;
            for (auto c = cool_callbacks_.begin(); c != cool_callbacks_.end();) {
                if (c->type != d.type) { ++c; continue; }
                if (c->cb->notifyCoolingDeviceChanged(d).getStatus() == STATUS_DEAD_OBJECT) {
                    c = cool_callbacks_.erase(c);
                } else {
                    ++c;
                }
            }
        }
    }
}

}  // namespace aidl::android::hardware::thermal
