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

// What differs from AOSP's default service: setActiveBootSlot, markBootSuccessful and setSlotAsUnbootable first run
// openbook-bootsync, and only change misc when it succeeded. systemd-boot reads the ESP, not misc, so the ESP is
// what decides the next boot; misc follows it. In particular a slot is marked successful in misc (which lets
// update_engine start the virtual A/B merge) only once its ESP entry is marked good, so a failed ESP write can never
// leave a merged system that the loader would still roll back.
#include "BootControl.h"

#include <android-base/logging.h>
#include <android-base/strings.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cstdint>

using HIDLMergeStatus = ::android::bootable::BootControl::MergeStatus;
using ndk::ScopedAStatus;

namespace aidl::android::hardware::boot {

static constexpr char kBootsync[] = "/vendor/bin/openbook-bootsync";

BootControl::BootControl() {
    CHECK(impl_.Init());
}

bool BootControl::Bootsync(const std::vector<std::string>& args, std::string* json) {
    std::vector<std::string> a = {kBootsync, "--json", "--current",
                                  std::string(1, static_cast<char>('a' + impl_.GetCurrentSlot()))};
    a.insert(a.end(), args.begin(), args.end());
    std::vector<char*> argv;
    for (auto& s : a) argv.push_back(s.data());
    argv.push_back(nullptr);
    int out[2], err[2];
    if (pipe2(out, O_CLOEXEC) || pipe2(err, O_CLOEXEC)) {
        PLOG(ERROR) << "bootsync: pipe";
        return false;
    }
    pid_t pid = fork();
    if (pid == 0) {
        dup2(out[1], STDOUT_FILENO);
        dup2(err[1], STDERR_FILENO);
        execv(kBootsync, argv.data());
        _exit(127);
    }
    close(out[1]);
    close(err[1]);
    if (pid < 0) {
        PLOG(ERROR) << "bootsync: fork";
        close(out[0]);
        close(err[0]);
        return false;
    }
    std::string cmd = ::android::base::Join(args, ' '), log;
    json->clear();
    pollfd p[2] = {{out[0], POLLIN, 0}, {err[0], POLLIN, 0}};
    int open = 2;
    while (open > 0) {
        if (poll(p, 2, -1) < 0) {
            if (errno == EINTR) continue;
            break;
        }
        for (auto& f : p) {
            if (f.fd < 0 || !(f.revents & (POLLIN | POLLHUP | POLLERR))) continue;
            char buf[4096];
            ssize_t n = read(f.fd, buf, sizeof buf);
            if (n <= 0) {
                close(f.fd);
                f.fd = -1;
                open--;
                continue;
            }
            (f.fd == out[0] ? *json : log).append(buf, n);
        }
    }
    int status = 0;
    while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {
    }
    for (const auto& line : ::android::base::Split(log, "\n"))
        if (!line.empty()) LOG(INFO) << "bootsync " << cmd << ": " << line;
    bool ok = WIFEXITED(status) && WEXITSTATUS(status) == 0;
    if (!ok) LOG(ERROR) << "bootsync " << cmd << " failed (status " << status << "): " << *json;
    return ok;
}

// "next_boot_slot":"a" in bootsync's JSON: the slot systemd-boot starts next, or -1.
static int NextBootSlot(const std::string& json) {
    static constexpr char kKey[] = "\"next_boot_slot\":\"";
    size_t at = json.find(kKey);
    if (at == std::string::npos || at + sizeof kKey > json.size()) return -1;
    char s = json[at + sizeof kKey - 1];
    return s == 'a' ? 0 : s == 'b' ? 1 : -1;
}

ScopedAStatus BootControl::getActiveBootSlot(int32_t* _aidl_return) {
    *_aidl_return = impl_.GetActiveBootSlot();
    return ScopedAStatus::ok();
}

ScopedAStatus BootControl::getCurrentSlot(int32_t* _aidl_return) {
    *_aidl_return = impl_.GetCurrentSlot();
    return ScopedAStatus::ok();
}

ScopedAStatus BootControl::getNumberSlots(int32_t* _aidl_return) {
    *_aidl_return = impl_.GetNumberSlots();
    return ScopedAStatus::ok();
}

namespace {

static constexpr MergeStatus ToAIDLMergeStatus(HIDLMergeStatus status) {
    switch (status) {
        case HIDLMergeStatus::NONE:
            return MergeStatus::NONE;
        case HIDLMergeStatus::UNKNOWN:
            return MergeStatus::UNKNOWN;
        case HIDLMergeStatus::SNAPSHOTTED:
            return MergeStatus::SNAPSHOTTED;
        case HIDLMergeStatus::MERGING:
            return MergeStatus::MERGING;
        case HIDLMergeStatus::CANCELLED:
            return MergeStatus::CANCELLED;
    }
}

static constexpr HIDLMergeStatus ToHIDLMergeStatus(MergeStatus status) {
    switch (status) {
        case MergeStatus::NONE:
            return HIDLMergeStatus::NONE;
        case MergeStatus::UNKNOWN:
            return HIDLMergeStatus::UNKNOWN;
        case MergeStatus::SNAPSHOTTED:
            return HIDLMergeStatus::SNAPSHOTTED;
        case MergeStatus::MERGING:
            return HIDLMergeStatus::MERGING;
        case MergeStatus::CANCELLED:
            return HIDLMergeStatus::CANCELLED;
    }
}

}  // namespace

ScopedAStatus BootControl::getSnapshotMergeStatus(MergeStatus* _aidl_return) {
    *_aidl_return = ToAIDLMergeStatus(impl_.GetSnapshotMergeStatus());
    return ScopedAStatus::ok();
}

ScopedAStatus BootControl::getSuffix(int32_t in_slot, std::string* _aidl_return) {
    if (!impl_.IsValidSlot(in_slot)) {
        // Old HIDL hal returns empty string for invalid slots. We should maintain this behavior in
        // AIDL for compatibility.
        _aidl_return->clear();
    } else {
        *_aidl_return = impl_.GetSuffix(in_slot);
    }
    return ScopedAStatus::ok();
}

ScopedAStatus BootControl::isSlotBootable(int32_t in_slot, bool* _aidl_return) {
    if (!impl_.IsValidSlot(in_slot)) {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(
                INVALID_SLOT, (std::string("Invalid slot ") + std::to_string(in_slot)).c_str());
    }
    *_aidl_return = impl_.IsSlotBootable(in_slot);
    return ScopedAStatus::ok();
}

ScopedAStatus BootControl::isSlotMarkedSuccessful(int32_t in_slot, bool* _aidl_return) {
    if (!impl_.IsValidSlot(in_slot)) {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(
                INVALID_SLOT, (std::string("Invalid slot ") + std::to_string(in_slot)).c_str());
    }
    *_aidl_return = impl_.IsSlotMarkedSuccessful(in_slot);
    return ScopedAStatus::ok();
}

ScopedAStatus BootControl::markBootSuccessful() {
    std::string json;
    if (!Bootsync({"mark-good"}, &json)) {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(
                COMMAND_FAILED, "openbook-bootsync could not mark the ESP entry good");
    }
    if (!impl_.MarkBootSuccessful()) {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(COMMAND_FAILED,
                                                                  "Operation failed");
    }
    // systemd-boot started this slot although misc names the other one active: the other slot's tries ran out (or
    // its entry is gone). misc follows the loader, as a bootloader that counts tries in misc would have done.
    const int32_t cur = impl_.GetCurrentSlot();
    if (NextBootSlot(json) == cur && static_cast<int32_t>(impl_.GetActiveBootSlot()) != cur) {
        LOG(INFO) << "the loader fell back to slot " << impl_.GetSuffix(cur) << ": misc follows";
        impl_.SetSlotAsUnbootable(1 - cur);
        impl_.SetActiveBootSlot(cur);
    }
    return ScopedAStatus::ok();
}

ScopedAStatus BootControl::setActiveBootSlot(int32_t in_slot) {
    if (!impl_.IsValidSlot(in_slot)) {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(
                INVALID_SLOT, (std::string("Invalid slot ") + std::to_string(in_slot)).c_str());
    }
    std::string json;
    if (!Bootsync({"activate", impl_.GetSuffix(in_slot)}, &json)) {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(
                COMMAND_FAILED, "openbook-bootsync could not make the slot the loader's next boot");
    }
    if (!impl_.SetActiveBootSlot(in_slot)) {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(COMMAND_FAILED,
                                                                  "Operation failed");
    }
    return ScopedAStatus::ok();
}

ScopedAStatus BootControl::setSlotAsUnbootable(int32_t in_slot) {
    if (!impl_.IsValidSlot(in_slot)) {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(
                INVALID_SLOT, (std::string("Invalid slot ") + std::to_string(in_slot)).c_str());
    }
    std::string json;
    if (!Bootsync({"disable", impl_.GetSuffix(in_slot)}, &json)) {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(
                COMMAND_FAILED, "openbook-bootsync could not remove the slot's ESP entry");
    }
    if (!impl_.SetSlotAsUnbootable(in_slot)) {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(COMMAND_FAILED,
                                                                  "Operation failed");
    }
    return ScopedAStatus::ok();
}

ScopedAStatus BootControl::setSnapshotMergeStatus(MergeStatus in_status) {
    if (!impl_.SetSnapshotMergeStatus(ToHIDLMergeStatus(in_status))) {
        return ScopedAStatus::fromServiceSpecificErrorWithMessage(COMMAND_FAILED,
                                                                  "Operation failed");
    }
    return ScopedAStatus::ok();
}

}  // namespace aidl::android::hardware::boot
