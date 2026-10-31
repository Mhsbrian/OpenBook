// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <mutex>

#include <aidl/android/hardware/power/BnPower.h>

#include "epp.h"

namespace aidl::android::hardware::power {

// IPower for PCs with amd-pstate (or intel_pstate) in EPP mode: power modes become energy-performance
// preferences. No boosts and no hint sessions: the CPU's own controller reacts faster than a sysfs write.
class Power : public BnPower {
  public:
    explicit Power(openbook::Sysfs sysfs);

    ndk::ScopedAStatus setMode(Mode type, bool enabled) override;
    ndk::ScopedAStatus isModeSupported(Mode type, bool* _aidl_return) override;
    ndk::ScopedAStatus setBoost(Boost type, int32_t durationMs) override;
    ndk::ScopedAStatus isBoostSupported(Boost type, bool* _aidl_return) override;
    ndk::ScopedAStatus createHintSession(int32_t tgid, int32_t uid, const std::vector<int32_t>& threadIds,
                                         int64_t durationNanos,
                                         std::shared_ptr<IPowerHintSession>* _aidl_return) override;
    ndk::ScopedAStatus createHintSessionWithConfig(int32_t tgid, int32_t uid,
                                                   const std::vector<int32_t>& threadIds, int64_t durationNanos,
                                                   SessionTag tag, SessionConfig* config,
                                                   std::shared_ptr<IPowerHintSession>* _aidl_return) override;
    ndk::ScopedAStatus getHintSessionPreferredRate(int64_t* outNanoseconds) override;
    ndk::ScopedAStatus getSessionChannel(int32_t tgid, int32_t uid, ChannelConfig* _aidl_return) override;
    ndk::ScopedAStatus closeSessionChannel(int32_t tgid, int32_t uid) override;
    ndk::ScopedAStatus getSupportInfo(SupportInfo* _aidl_return) override;
    ndk::ScopedAStatus getCpuHeadroom(const CpuHeadroomParams& params, CpuHeadroomResult* _aidl_return) override;
    ndk::ScopedAStatus getGpuHeadroom(const GpuHeadroomParams& params, GpuHeadroomResult* _aidl_return) override;
    ndk::ScopedAStatus sendCompositionData(const std::vector<CompositionData>& in_data) override;
    ndk::ScopedAStatus sendCompositionUpdate(const CompositionUpdate& in_update) override;

  private:
    bool Supported(Mode type) const;

    std::mutex lock_;
    openbook::Epp epp_;
    openbook::PowerModes modes_;
};

}  // namespace aidl::android::hardware::power
