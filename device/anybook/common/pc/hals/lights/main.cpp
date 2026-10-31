// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include <android-base/logging.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>

#include "Lights.h"

using aidl::android::hardware::light::Lights;

int main() {
    ABinderProcess_setThreadPoolMaxThreadCount(0);
    auto lights = ndk::SharedRefBase::make<Lights>(openbook::Sysfs());
    const std::string instance = std::string(Lights::descriptor) + "/default";
    CHECK_EQ(AServiceManager_addService(lights->asBinder().get(), instance.c_str()), STATUS_OK);
    ABinderProcess_joinThreadPool();
    return EXIT_FAILURE;
}
