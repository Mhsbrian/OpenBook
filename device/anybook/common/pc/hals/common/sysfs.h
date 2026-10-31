// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// sysfs access for the OpenBook HALs. Every path is relative to a root ("" on the device), so the host tests run
// the same code on fixture trees.

#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace openbook {

class Sysfs {
  public:
    explicit Sysfs(std::string root = "") : root_(std::move(root)) {}

    std::string Path(std::string_view path) const { return root_ + std::string(path); }
    bool Exists(std::string_view path) const;
    // Whole file with surrounding whitespace removed; nullopt if it cannot be read.
    std::optional<std::string> Read(std::string_view path) const;
    std::optional<int64_t> ReadInt(std::string_view path) const;
    bool Write(std::string_view path, std::string_view value) const;
    // Entry names in a directory, sorted, without "." and "..".
    std::vector<std::string> List(std::string_view dir) const;

  private:
    std::string root_;
};

}  // namespace openbook
