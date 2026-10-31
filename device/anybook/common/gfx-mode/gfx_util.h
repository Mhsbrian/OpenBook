// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Small file helpers shared by gfx_select.cpp and gfx_mode.cpp (no Android libraries).

#pragma once

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdlib.h>
#include <unistd.h>

#include <algorithm>
#include <string>
#include <vector>

namespace openbook::gfx::util {

#ifdef __ANDROID__
// The kernel log, written directly. init's stdio_to_kmsg goes through /dev/kmsg_debug on a userdebug vendor, which
// Ruby's user system leaves unlabelled, so the early-init output was lost (ANAL-246, the first Ruby VM run).
inline void KernelLog(const std::string& tag, const std::string& line) {
    int fd = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);
    if (fd < 0) return;
    const std::string msg = "<6>" + tag + ": " + line + "\n";
    ssize_t n = write(fd, msg.data(), msg.size());
    (void)n;
    close(fd);
}
#endif

inline std::string Trim(const std::string& s) {
    size_t b = s.find_first_not_of(" \t\r\n"), e = s.find_last_not_of(" \t\r\n");
    return b == std::string::npos ? "" : s.substr(b, e - b + 1);
}

inline bool ReadFile(const std::string& path, std::string* out) {
    int fd = open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (fd < 0) return false;
    out->clear();
    char buf[4096];
    ssize_t n;
    while ((n = read(fd, buf, sizeof(buf))) > 0) out->append(buf, n);
    int saved = errno;
    close(fd);
    errno = saved;
    return n == 0;
}

inline std::vector<std::string> ListDir(const std::string& dir) {
    std::vector<std::string> names;
    if (DIR* d = opendir(dir.c_str())) {
        while (dirent* e = readdir(d)) {
            if (e->d_name[0] != '.') names.emplace_back(e->d_name);
        }
        closedir(d);
    }
    std::sort(names.begin(), names.end());
    return names;
}

inline std::string Basename(const std::string& p) {
    size_t s = p.find_last_of('/');
    return s == std::string::npos ? p : p.substr(s + 1);
}

inline std::string LinkBasename(const std::string& path) {
    char buf[PATH_MAX];
    ssize_t n = readlink(path.c_str(), buf, sizeof(buf) - 1);
    if (n <= 0) return "";
    buf[n] = '\0';
    return Basename(buf);
}

// 0000:65:00.0
inline bool IsPciSlot(const std::string& s) {
    if (s.size() != 12 || s[4] != ':' || s[7] != ':' || s[10] != '.') return false;
    for (size_t i : {0, 1, 2, 3, 5, 6, 8, 9}) {
        if (!isxdigit(static_cast<unsigned char>(s[i]))) return false;
    }
    return s[11] >= '0' && s[11] <= '7';
}

inline bool ParseInt(const std::string& s, int* out) {
    std::string t = Trim(s);
    if (t.empty() || t.size() > 9) return false;
    char* end = nullptr;
    long v = strtol(t.c_str(), &end, 10);
    if (*end != '\0') return false;
    *out = static_cast<int>(v);
    return true;
}

inline unsigned ReadHex(const std::string& path) {
    std::string s;
    if (!ReadFile(path, &s)) return 0;
    return static_cast<unsigned>(strtoul(Trim(s).c_str(), nullptr, 16));
}

}  // namespace openbook::gfx::util
