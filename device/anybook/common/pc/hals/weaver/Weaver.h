// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <mutex>

#include <aidl/android/hardware/weaver/BnWeaver.h>

#include "store.h"

namespace aidl::android::hardware::weaver {

class Weaver : public BnWeaver {
  public:
    explicit Weaver(openbook::WeaverStore store) : store_(std::move(store)) {}

    ndk::ScopedAStatus getConfig(WeaverConfig* _aidl_return) override;
    ndk::ScopedAStatus read(int32_t slotId, const std::vector<uint8_t>& key,
                            WeaverReadResponse* _aidl_return) override;
    ndk::ScopedAStatus write(int32_t slotId, const std::vector<uint8_t>& key,
                             const std::vector<uint8_t>& value) override;
    ndk::ScopedAStatus warmUp() override;
    ndk::ScopedAStatus getTimeout(int32_t slotId, int64_t* _aidl_return) override;

  private:
    std::mutex lock_;
    openbook::WeaverStore store_;
};

}  // namespace aidl::android::hardware::weaver
