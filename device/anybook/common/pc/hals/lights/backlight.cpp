// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "backlight.h"

#include <algorithm>

namespace openbook {

namespace {

int Rank(const std::string& type) {
    if (type == "firmware") return 0;
    if (type == "platform") return 1;
    if (type == "raw") return 2;
    return 3;
}

}  // namespace

std::optional<Backlight> PickBacklight(const Sysfs& sysfs) {
    std::optional<Backlight> best;
    for (const auto& name : sysfs.List("/sys/class/backlight")) {
        const std::string dir = "/sys/class/backlight/" + name;
        auto max = sysfs.ReadInt(dir + "/max_brightness");
        if (!max || *max <= 0) continue;
        Backlight b{name, sysfs.Read(dir + "/type").value_or(""), *max};
        if (!best || Rank(b.type) < Rank(best->type)) best = b;  // List() is sorted: ties keep the first name
    }
    return best;
}

int64_t ScaleBrightness(int android_brightness, int64_t max) {
    int b = std::clamp(android_brightness, 0, 255);
    if (b == 0 || max <= 0) return 0;
    int64_t v = (static_cast<int64_t>(b) * max + 127) / 255;
    return std::max<int64_t>(v, 1);
}

}  // namespace openbook
