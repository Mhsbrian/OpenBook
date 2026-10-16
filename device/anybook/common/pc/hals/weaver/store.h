// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Software Weaver slots in files. A real Weaver keeps them in a secure element that rate-limits guesses in hardware;
// here they sit in /data/vendor/weaver, readable by root, so this adds NO protection beyond what Android's
// lock-screen code already has. It exists so LockSettings runs its Weaver path, and it keeps slots across reboots,
// which AOSP's example Weaver (slots in RAM) does not. Wrong keys are throttled on libgatekeeper's schedule.

#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace openbook {

class WeaverStore {
  public:
    static constexpr int kSlots = 16;
    static constexpr int kKeySize = 16;
    static constexpr int kValueSize = 16;

    enum class Status { kOk, kFailed, kIncorrectKey, kThrottle };
    struct ReadResult {
        Status status = Status::kFailed;
        std::vector<uint8_t> value;
        int64_t timeout_ms = 0;
    };

    // now_ms: a monotonic clock in milliseconds (CLOCK_BOOTTIME on the device).
    WeaverStore(std::string dir, std::function<int64_t()> now_ms);

    ReadResult Read(int slot, const std::vector<uint8_t>& key);
    bool Write(int slot, const std::vector<uint8_t>& key, const std::vector<uint8_t>& value);
    // Remaining throttle time for a slot; -1 for an invalid slot.
    int64_t Timeout(int slot);

    // libgatekeeper's GateKeeper::ComputeRetryTimeout.
    static int64_t RetryTimeoutMs(uint32_t failures);

  private:
    struct Slot {
        bool loaded = false;
        bool exists = false;
        std::vector<uint8_t> key;
        std::vector<uint8_t> value;
        uint32_t failures = 0;
        int64_t last_failure_ms = 0;
    };

    Slot& Get(int slot);
    bool Save(int slot);
    std::string FileOf(int slot) const;
    int64_t Remaining(const Slot& s);

    std::string dir_;
    std::function<int64_t()> now_ms_;
    std::array<Slot, kSlots> slots_;
};

}  // namespace openbook
