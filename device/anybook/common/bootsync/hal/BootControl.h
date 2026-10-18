/*
 * Copyright (C) 2022 The Android Open Source Project
 * Copyright (C) 2026 The OpenBook Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// AOSP's IBootControl default service (hardware/interfaces/boot/aidl/default) on libboot_control's misc partition,
// plus openbook-bootsync, which moves systemd-boot's entries on the ESP along with the slot changes (ANAL-223).
#pragma once

#include <aidl/android/hardware/boot/BnBootControl.h>
#include <libboot_control/libboot_control.h>

#include <string>
#include <vector>

namespace aidl::android::hardware::boot {

class BootControl final : public BnBootControl {
  public:
    BootControl();
    ::ndk::ScopedAStatus getActiveBootSlot(int32_t* _aidl_return) override;
    ::ndk::ScopedAStatus getCurrentSlot(int32_t* _aidl_return) override;
    ::ndk::ScopedAStatus getNumberSlots(int32_t* _aidl_return) override;
    ::ndk::ScopedAStatus getSnapshotMergeStatus(
            ::aidl::android::hardware::boot::MergeStatus* _aidl_return) override;
    ::ndk::ScopedAStatus getSuffix(int32_t in_slot, std::string* _aidl_return) override;
    ::ndk::ScopedAStatus isSlotBootable(int32_t in_slot, bool* _aidl_return) override;
    ::ndk::ScopedAStatus isSlotMarkedSuccessful(int32_t in_slot, bool* _aidl_return) override;
    ::ndk::ScopedAStatus markBootSuccessful() override;
    ::ndk::ScopedAStatus setActiveBootSlot(int32_t in_slot) override;
    ::ndk::ScopedAStatus setSlotAsUnbootable(int32_t in_slot) override;
    ::ndk::ScopedAStatus setSnapshotMergeStatus(
            ::aidl::android::hardware::boot::MergeStatus in_status) override;

  private:
    // Runs /vendor/bin/openbook-bootsync --json --current <slot> ARGS; its log goes to logcat, its JSON to *json.
    bool Bootsync(const std::vector<std::string>& args, std::string* json);
    ::android::bootable::BootControl impl_;
};

}  // namespace aidl::android::hardware::boot
