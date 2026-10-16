// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include <android-base/logging.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>

#include "PowerStats.h"

using aidl::android::hardware::power::stats::PowerStats;

int main() {
    ABinderProcess_setThreadPoolMaxThreadCount(0);
    auto stats = ndk::SharedRefBase::make<PowerStats>(openbook::Sysfs());
    const std::string instance = std::string(PowerStats::descriptor) + "/default";
    CHECK_EQ(AServiceManager_addService(stats->asBinder().get(), instance.c_str()), STATUS_OK);
    ABinderProcess_joinThreadPool();
    return EXIT_FAILURE;
}
