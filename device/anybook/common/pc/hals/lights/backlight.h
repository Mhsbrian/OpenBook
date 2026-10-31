// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Which /sys/class/backlight device drives the internal panel, and how Android's 0-255 maps onto it.

#pragma once

#include <cstdint>
#include <optional>
#include <string>

#include "sysfs.h"

namespace openbook {

struct Backlight {
    std::string name;  // e.g. amdgpu_bl1, nvidia_wmi_ec_backlight, acpi_video0
    std::string type;  // firmware, platform or raw
    int64_t max = 0;
};

// The kernel registers the backlight it chose (acpi_video, the GPU's native one, or a vendor EC driver). When more
// than one is registered, pick as desktop Linux does (systemd-backlight, GNOME): firmware > platform > raw, then by
// name. On the GA403WR in Optimus or Integrated mode that is amdgpu_bl1 (raw, max 400000), and in a dGPU-only MUX
// mode the EC's nvidia_wmi_ec_backlight (firmware) takes over (docs/HARDWARE.md, ANAL-175).
std::optional<Backlight> PickBacklight(const Sysfs& sysfs);

// Android's brightness (0-255; 0 = off) as a value for the device. A non-zero brightness never maps to 0, which
// would switch some panels off.
int64_t ScaleBrightness(int android_brightness, int64_t max);

}  // namespace openbook
