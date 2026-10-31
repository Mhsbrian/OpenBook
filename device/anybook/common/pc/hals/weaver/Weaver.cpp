// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "Weaver.h"

namespace aidl::android::hardware::weaver {

using openbook::WeaverStore;

ndk::ScopedAStatus Weaver::getConfig(WeaverConfig* _aidl_return) {
    *_aidl_return = {WeaverStore::kSlots, WeaverStore::kKeySize, WeaverStore::kValueSize};
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Weaver::read(int32_t slotId, const std::vector<uint8_t>& key, WeaverReadResponse* _aidl_return) {
    std::lock_guard<std::mutex> l(lock_);
    auto r = store_.Read(slotId, key);
    _aidl_return->timeout = r.timeout_ms;
    _aidl_return->value = std::move(r.value);
    switch (r.status) {
        case WeaverStore::Status::kOk: _aidl_return->status = WeaverReadStatus::OK; break;
        case WeaverStore::Status::kIncorrectKey: _aidl_return->status = WeaverReadStatus::INCORRECT_KEY; break;
        case WeaverStore::Status::kThrottle: _aidl_return->status = WeaverReadStatus::THROTTLE; break;
        case WeaverStore::Status::kFailed: _aidl_return->status = WeaverReadStatus::FAILED; break;
    }
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Weaver::write(int32_t slotId, const std::vector<uint8_t>& key, const std::vector<uint8_t>& value) {
    std::lock_guard<std::mutex> l(lock_);
    if (!store_.Write(slotId, key, value)) {
        return ndk::ScopedAStatus::fromServiceSpecificError(IWeaver::STATUS_FAILED);
    }
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Weaver::warmUp() {
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Weaver::getTimeout(int32_t slotId, int64_t* _aidl_return) {
    std::lock_guard<std::mutex> l(lock_);
    int64_t t = store_.Timeout(slotId);
    if (t < 0) return ndk::ScopedAStatus::fromServiceSpecificError(IWeaver::STATUS_FAILED);
    *_aidl_return = t;
    return ndk::ScopedAStatus::ok();
}

}  // namespace aidl::android::hardware::weaver
