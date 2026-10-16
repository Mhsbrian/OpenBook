// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#define LOG_TAG "openbook.power"

#include "epp.h"

#include <android-base/logging.h>
#include <android-base/strings.h>

namespace openbook {

namespace {
constexpr char kCpufreq[] = "/sys/devices/system/cpu/cpufreq";
}

std::string ChooseEpp(const PowerModes& modes, const std::string& base) {
    if (modes.fixed_performance) return "performance";
    if (!modes.interactive) return "power";
    if (modes.launch) return "performance";
    if (modes.low_power) return "balance_power";
    return base;
}

Epp::Epp(Sysfs sysfs) : sysfs_(std::move(sysfs)) {
    for (const auto& name : sysfs_.List(kCpufreq)) {
        if (!android::base::StartsWith(name, "policy")) continue;
        const std::string dir = std::string(kCpufreq) + "/" + name;
        // Only amd-pstate-epp (and intel_pstate, which takes the same values) honour the preference.
        auto driver = sysfs_.Read(dir + "/scaling_driver").value_or("");
        if (driver != "amd-pstate-epp" && driver != "intel_pstate") continue;
        if (!sysfs_.Exists(dir + "/energy_performance_preference")) continue;
        policies_.push_back(dir + "/energy_performance_preference");
    }
    if (!policies_.empty()) {
        auto pref = sysfs_.Read(policies_.front());
        if (pref && !pref->empty() && *pref != "default") base_ = *pref;
        current_ = base_;
    }
}

bool Epp::Set(const std::string& preference) {
    if (preference == current_) return true;
    bool ok = true;
    for (const auto& p : policies_) {
        if (!sysfs_.Write(p, preference)) {
            PLOG(ERROR) << "writing " << preference << " to " << p;
            ok = false;
        }
    }
    if (ok) current_ = preference;
    LOG(INFO) << "energy_performance_preference=" << preference << " on " << policies_.size()
              << " policies" << (ok ? "" : " (with errors)");
    return ok;
}

}  // namespace openbook
