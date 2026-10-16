// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include <android-base/logging.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>

#include "Power.h"

using aidl::android::hardware::power::Power;

int main() {
    ABinderProcess_setThreadPoolMaxThreadCount(0);
    auto power = ndk::SharedRefBase::make<Power>(openbook::Sysfs());
    const std::string instance = std::string(Power::descriptor) + "/default";
    CHECK_EQ(AServiceManager_addService(power->asBinder().get(), instance.c_str()), STATUS_OK);
    ABinderProcess_joinThreadPool();
    return EXIT_FAILURE;
}
