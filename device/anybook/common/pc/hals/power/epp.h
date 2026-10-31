// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// amd-pstate in active mode (amd-pstate-epp, the OpenBook kernel's default: X86_AMD_PSTATE_DEFAULT_MODE=3) takes an
// energy-performance preference per cpufreq policy; the CPU's own controller picks frequencies. Android's power
// modes map onto those preferences. Nothing here touches ACPI platform_profile or asus-wmi: on ASUS laptops those
// change fan and power limits stored in firmware.

#pragma once

#include <string>
#include <vector>

#include "sysfs.h"

namespace openbook {

struct PowerModes {
    bool interactive = true;         // Mode::INTERACTIVE (screen on)
    bool low_power = false;          // Mode::LOW_POWER (battery saver)
    bool fixed_performance = false;  // Mode::FIXED_PERFORMANCE (benchmarks, CTS)
    bool launch = false;             // Mode::LAUNCH (an app is starting)
};

// The preference for a set of modes. `base` is what the kernel chose at boot (balance_performance by default).
//   fixed_performance          -> performance
//   launch while interactive   -> performance
//   screen off                 -> power
//   battery saver              -> balance_power
//   otherwise                  -> base
std::string ChooseEpp(const PowerModes& modes, const std::string& base);

class Epp {
  public:
    explicit Epp(Sysfs sysfs);

    bool available() const { return !policies_.empty(); }
    const std::string& base() const { return base_; }
    const std::vector<std::string>& policies() const { return policies_; }
    // Writes the preference to every policy; true if all writes succeeded. Skips writes that change nothing.
    bool Set(const std::string& preference);

  private:
    Sysfs sysfs_;
    std::vector<std::string> policies_;  // energy_performance_preference paths
    std::string base_ = "balance_performance";
    std::string current_;
};

}  // namespace openbook
