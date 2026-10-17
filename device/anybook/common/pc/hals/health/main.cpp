// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// AOSP's health service (hardware/interfaces/health/aidl/default/main.cpp) with HealthOpenbook. No charger mode:
// a PC charges with Android or firmware in control, never in an off-mode charger UI.

#include <android-base/logging.h>
#include <health-impl/HalHealthLoop.h>
#include <health/utils.h>

#include "HealthOpenbook.h"

using aidl::android::hardware::health::HalHealthLoop;
using aidl::android::hardware::health::HealthOpenbook;

int main() {
    auto config = std::make_unique<healthd_config>();
    ::android::hardware::health::InitHealthdConfig(config.get());
    auto binder = ndk::SharedRefBase::make<HealthOpenbook>("default", std::move(config), openbook::Sysfs());
    LOG(INFO) << "Starting health HAL (OpenBook).";
    auto loop = std::make_shared<HalHealthLoop>(binder, binder);
    return loop->StartLoop();
}
