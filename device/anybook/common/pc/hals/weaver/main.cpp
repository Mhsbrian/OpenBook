// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include <time.h>

#include <android-base/logging.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>

#include "Weaver.h"

using aidl::android::hardware::weaver::Weaver;

int main() {
    ABinderProcess_setThreadPoolMaxThreadCount(0);
    auto now_ms = [] {
        timespec ts;
        clock_gettime(CLOCK_BOOTTIME, &ts);
        return int64_t{ts.tv_sec} * 1000 + ts.tv_nsec / 1000000;
    };
    auto weaver = ndk::SharedRefBase::make<Weaver>(openbook::WeaverStore("/data/vendor/weaver", now_ms));
    const std::string instance = std::string(Weaver::descriptor) + "/default";
    CHECK_EQ(AServiceManager_addService(weaver->asBinder().get(), instance.c_str()), STATUS_OK);
    ABinderProcess_joinThreadPool();
    return EXIT_FAILURE;
}
