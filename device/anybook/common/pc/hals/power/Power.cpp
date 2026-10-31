// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#define LOG_TAG "openbook.power"

#include "Power.h"

#include <android-base/logging.h>

namespace aidl::android::hardware::power {

namespace {
ndk::ScopedAStatus Unsupported() {
    return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
}
}  // namespace

Power::Power(openbook::Sysfs sysfs) : epp_(std::move(sysfs)) {
    if (epp_.available()) {
        LOG(INFO) << "EPP on " << epp_.policies().size() << " cpufreq policies, base " << epp_.base();
    } else {
        LOG(INFO) << "no cpufreq policy takes an energy-performance preference; modes are accepted and ignored";
    }
}

bool Power::Supported(Mode type) const {
    if (!epp_.available()) return false;
    switch (type) {
        case Mode::INTERACTIVE:
        case Mode::LOW_POWER:
        case Mode::FIXED_PERFORMANCE:
        case Mode::LAUNCH:
            return true;
        default:
            return false;
    }
}

ndk::ScopedAStatus Power::setMode(Mode type, bool enabled) {
    std::lock_guard<std::mutex> l(lock_);
    switch (type) {
        case Mode::INTERACTIVE: modes_.interactive = enabled; break;
        case Mode::LOW_POWER: modes_.low_power = enabled; break;
        case Mode::FIXED_PERFORMANCE: modes_.fixed_performance = enabled; break;
        case Mode::LAUNCH: modes_.launch = enabled; break;
        default: return ndk::ScopedAStatus::ok();
    }
    if (epp_.available()) epp_.Set(openbook::ChooseEpp(modes_, epp_.base()));
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Power::isModeSupported(Mode type, bool* _aidl_return) {
    *_aidl_return = Supported(type);
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Power::setBoost(Boost, int32_t) {
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Power::isBoostSupported(Boost, bool* _aidl_return) {
    *_aidl_return = false;
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Power::createHintSession(int32_t, int32_t, const std::vector<int32_t>&, int64_t,
                                            std::shared_ptr<IPowerHintSession>* _aidl_return) {
    *_aidl_return = nullptr;
    return Unsupported();
}

ndk::ScopedAStatus Power::createHintSessionWithConfig(int32_t, int32_t, const std::vector<int32_t>&, int64_t,
                                                      SessionTag, SessionConfig*,
                                                      std::shared_ptr<IPowerHintSession>* _aidl_return) {
    *_aidl_return = nullptr;
    return Unsupported();
}

ndk::ScopedAStatus Power::getHintSessionPreferredRate(int64_t* outNanoseconds) {
    *outNanoseconds = -1;
    return Unsupported();
}

ndk::ScopedAStatus Power::getSessionChannel(int32_t, int32_t, ChannelConfig*) {
    return Unsupported();
}

ndk::ScopedAStatus Power::closeSessionChannel(int32_t, int32_t) {
    return Unsupported();
}

ndk::ScopedAStatus Power::getSupportInfo(SupportInfo* _aidl_return) {
    SupportInfo info;
    info.usesSessions = false;
    info.boosts = 0;
    info.modes = 0;
    for (Mode m : {Mode::INTERACTIVE, Mode::LOW_POWER, Mode::FIXED_PERFORMANCE, Mode::LAUNCH}) {
        if (Supported(m)) info.modes |= int64_t{1} << static_cast<int>(m);
    }
    info.sessionHints = 0;
    info.sessionModes = 0;
    info.sessionTags = 0;
    info.compositionData.isSupported = false;
    info.headroom.isCpuSupported = false;
    info.headroom.isGpuSupported = false;
    *_aidl_return = info;
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus Power::getCpuHeadroom(const CpuHeadroomParams&, CpuHeadroomResult*) {
    return Unsupported();
}

ndk::ScopedAStatus Power::getGpuHeadroom(const GpuHeadroomParams&, GpuHeadroomResult*) {
    return Unsupported();
}

ndk::ScopedAStatus Power::sendCompositionData(const std::vector<CompositionData>&) {
    return Unsupported();
}

ndk::ScopedAStatus Power::sendCompositionUpdate(const CompositionUpdate&) {
    return Unsupported();
}

}  // namespace aidl::android::hardware::power
