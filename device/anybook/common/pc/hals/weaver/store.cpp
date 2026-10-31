// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#define LOG_TAG "openbook.weaver"

#include "store.h"

#include <fcntl.h>
#include <string.h>
#include <unistd.h>

#include <android-base/file.h>
#include <android-base/logging.h>
#include <android-base/unique_fd.h>

namespace openbook {

namespace {

constexpr char kMagic[4] = {'O', 'B', 'W', '1'};

bool SameKey(const std::vector<uint8_t>& a, const std::vector<uint8_t>& b) {
    if (a.size() != b.size()) return false;
    uint8_t diff = 0;
    for (size_t i = 0; i < a.size(); i++) diff |= a[i] ^ b[i];
    return diff == 0;
}

}  // namespace

WeaverStore::WeaverStore(std::string dir, std::function<int64_t()> now_ms)
    : dir_(std::move(dir)), now_ms_(std::move(now_ms)) {}

int64_t WeaverStore::RetryTimeoutMs(uint32_t failures) {
    constexpr int64_t kTimeout = 30000;
    constexpr int64_t kDay = 24 * 60 * 60 * 1000;
    if (failures == 0) return 0;
    if (failures <= 10) return failures % 5 == 0 ? kTimeout : 0;
    if (failures < 30) return kTimeout;
    if (failures < 140) return kTimeout << ((failures - 30) / 10);
    return kDay;
}

std::string WeaverStore::FileOf(int slot) const {
    return dir_ + "/slot" + std::to_string(slot);
}

WeaverStore::Slot& WeaverStore::Get(int slot) {
    Slot& s = slots_[slot];
    if (s.loaded) return s;
    s.loaded = true;
    std::string blob;
    if (!android::base::ReadFileToString(FileOf(slot), &blob)) return s;
    // magic, u32 failures, u8 key length, key, u8 value length, value
    size_t p = 0;
    auto take = [&](size_t n) -> const char* {
        if (p + n > blob.size()) return nullptr;
        const char* r = blob.data() + p;
        p += n;
        return r;
    };
    const char* m = take(4);
    const char* f = take(4);
    const char* kl = take(1);
    if (!m || std::string(m, 4) != std::string(kMagic, 4) || !f || !kl) {
        LOG(ERROR) << FileOf(slot) << ": not a weaver slot file; treating the slot as empty";
        return s;
    }
    const char* k = take(static_cast<uint8_t>(*kl));
    const char* vl = take(1);
    const char* v = vl ? take(static_cast<uint8_t>(*vl)) : nullptr;
    if (!k || !v) {
        LOG(ERROR) << FileOf(slot) << ": truncated; treating the slot as empty";
        return s;
    }
    uint32_t failures;
    memcpy(&failures, f, 4);
    s.exists = true;
    s.failures = failures;
    s.key.assign(k, k + static_cast<uint8_t>(*kl));
    s.value.assign(v, v + static_cast<uint8_t>(*vl));
    // Throttling restarts with the process: a reboot never shortens the wait.
    if (s.failures > 0) s.last_failure_ms = now_ms_();
    return s;
}

bool WeaverStore::Save(int slot) {
    const Slot& s = slots_[slot];
    std::string blob(kMagic, 4);
    blob.append(reinterpret_cast<const char*>(&s.failures), 4);
    blob.push_back(static_cast<char>(s.key.size()));
    blob.append(s.key.begin(), s.key.end());
    blob.push_back(static_cast<char>(s.value.size()));
    blob.append(s.value.begin(), s.value.end());
    const std::string path = FileOf(slot), tmp = path + ".tmp";
    {
        android::base::unique_fd fd(open(tmp.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600));
        if (fd < 0 || !android::base::WriteFully(fd, blob.data(), blob.size()) || fsync(fd) != 0) {
            PLOG(ERROR) << "writing " << tmp;
            return false;
        }
    }
    if (rename(tmp.c_str(), path.c_str()) != 0) {
        PLOG(ERROR) << "renaming " << tmp;
        return false;
    }
    android::base::unique_fd dfd(open(dir_.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC));
    if (dfd >= 0) fsync(dfd);
    return true;
}

int64_t WeaverStore::Remaining(const Slot& s) {
    const int64_t wait = RetryTimeoutMs(s.failures);
    if (wait == 0) return 0;
    const int64_t left = s.last_failure_ms + wait - now_ms_();
    return left > 0 ? left : 0;
}

WeaverStore::ReadResult WeaverStore::Read(int slot, const std::vector<uint8_t>& key) {
    ReadResult r;
    if (slot < 0 || slot >= kSlots || key.size() > kKeySize) return r;
    Slot& s = Get(slot);
    if (int64_t left = Remaining(s); left > 0) {
        r.status = Status::kThrottle;
        r.timeout_ms = left;
        return r;
    }
    if (!s.exists || !SameKey(s.key, key)) {
        if (s.exists) {
            s.failures++;
            s.last_failure_ms = now_ms_();
            Save(slot);
            r.timeout_ms = RetryTimeoutMs(s.failures);
        }
        r.status = Status::kIncorrectKey;
        return r;
    }
    if (s.failures != 0) {
        s.failures = 0;
        Save(slot);
    }
    r.status = Status::kOk;
    r.value = s.value;
    return r;
}

bool WeaverStore::Write(int slot, const std::vector<uint8_t>& key, const std::vector<uint8_t>& value) {
    if (slot < 0 || slot >= kSlots || key.size() > kKeySize || value.size() > kValueSize) return false;
    Slot& s = Get(slot);
    Slot old = s;
    s.exists = true;
    s.key = key;
    s.value = value;
    s.failures = 0;
    s.last_failure_ms = 0;
    if (!Save(slot)) {
        s = old;
        return false;
    }
    return true;
}

int64_t WeaverStore::Timeout(int slot) {
    if (slot < 0 || slot >= kSlots) return -1;
    return Remaining(Get(slot));
}

}  // namespace openbook
