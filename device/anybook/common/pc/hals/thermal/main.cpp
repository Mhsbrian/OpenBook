// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include <android-base/logging.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>

#include "Thermal.h"

using aidl::android::hardware::thermal::Thermal;

int main() {
    ABinderProcess_setThreadPoolMaxThreadCount(0);
    auto thermal = ndk::SharedRefBase::make<Thermal>(openbook::Sysfs());
    const std::string instance = std::string(Thermal::descriptor) + "/default";
    CHECK_EQ(AServiceManager_addService(thermal->asBinder().get(), instance.c_str()), STATUS_OK);
    ABinderProcess_joinThreadPool();
    return EXIT_FAILURE;
}
