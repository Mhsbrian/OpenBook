// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "sysfs.h"

#include <dirent.h>
#include <fcntl.h>
#include <unistd.h>

#include <algorithm>
#include <memory>

#include <android-base/file.h>
#include <android-base/parseint.h>
#include <android-base/strings.h>
#include <android-base/unique_fd.h>

namespace openbook {

bool Sysfs::Exists(std::string_view path) const {
    return access(Path(path).c_str(), F_OK) == 0;
}

std::optional<std::string> Sysfs::Read(std::string_view path) const {
    std::string content;
    if (!android::base::ReadFileToString(Path(path), &content)) return std::nullopt;
    return android::base::Trim(content);
}

std::optional<int64_t> Sysfs::ReadInt(std::string_view path) const {
    auto s = Read(path);
    int64_t v;
    if (!s || !android::base::ParseInt(*s, &v)) return std::nullopt;
    return v;
}

bool Sysfs::Write(std::string_view path, std::string_view value) const {
    // sysfs attributes take one write(). O_TRUNC as a shell's ">" does (sysfs ignores it; fixture files need it);
    // no O_CREAT, so a missing node fails instead of creating a file.
    android::base::unique_fd fd(open(Path(path).c_str(), O_WRONLY | O_TRUNC | O_CLOEXEC));
    if (fd < 0) return false;
    return android::base::WriteFully(fd, value.data(), value.size());
}

std::vector<std::string> Sysfs::List(std::string_view dir) const {
    std::vector<std::string> out;
    std::unique_ptr<DIR, decltype(&closedir)> d(opendir(Path(dir).c_str()), closedir);
    if (!d) return out;
    while (dirent* e = readdir(d.get())) {
        std::string name = e->d_name;
        if (name != "." && name != "..") out.push_back(std::move(name));
    }
    std::sort(out.begin(), out.end());
    return out;
}

}  // namespace openbook
