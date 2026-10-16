// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "gpu_probe.h"

#include <dirent.h>
#include <limits.h>
#include <stdlib.h>
#include <unistd.h>

#include <algorithm>
#include <cstdio>
#include <regex>
#include <set>
#include <sstream>

#include <android-base/file.h>
#include <android-base/parseint.h>
#include <android-base/strings.h>

namespace anybook::gpu_probe {
namespace {

constexpr uint32_t kVendorAmd = 0x1002;
constexpr uint32_t kVendorRedHat = 0x1af4;  // virtio
constexpr uint32_t kDeviceVirtioGpu = 0x1050;
constexpr uint32_t kClassDisplay = 0x03;  // PCI base class: display controller

std::vector<std::string> ListDir(const std::string& dir) {
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

uint32_t ReadHex(const std::string& path) {
    std::string s;
    uint32_t v = 0;
    if (!android::base::ReadFileToString(path, &s)) return 0;
    return android::base::ParseUint(android::base::Trim(s), &v) ? v : 0;
}

std::string LinkTarget(const std::string& path) {
    std::string target;
    return android::base::Readlink(path, &target) ? android::base::Basename(target) : "";
}

bool IsPciSlot(const std::string& name) {
    static const std::regex re("[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\\.[0-7]");
    return std::regex_match(name, re);
}

void ReadPciIds(const std::string& dir, Device* d) {
    d->vendor = ReadHex(dir + "/vendor");
    d->device = ReadHex(dir + "/device");
    d->pci_class = ReadHex(dir + "/class");
}

std::string Hex(uint32_t v, int width) {
    char buf[16];
    snprintf(buf, sizeof(buf), "0x%0*x", width, v);
    return buf;
}

std::string VendorName(uint32_t vendor) {
    switch (vendor) {
        case kVendorAmd: return "amd";
        case 0x10de: return "nvidia";
        case 0x8086: return "intel";
        case kVendorRedHat: return "virtio";
        default: return Hex(vendor, 4);
    }
}

bool IsAmd(const Device& d) {
    // A display controller still unbound (amdgpu not loaded yet) or bound to amdgpu; not one
    // claimed by radeon or vfio-pci.
    return d.vendor == kVendorAmd && (d.driver.empty() || d.driver == "amdgpu");
}

bool IsVirtioGpu(const Device& d) {
    return d.driver == "virtio_gpu" || (d.vendor == kVendorRedHat && d.device == kDeviceVirtioGpu);
}

Result Pick(const Device& d, const std::string& hal) {
    char id[16];
    snprintf(id, sizeof(id), "%04x:%04x", d.vendor, d.device);
    return {hal, d.vendor ? id : "", d.driver.empty() ? "unbound" : d.driver, d.source, ""};
}

}  // namespace

std::vector<Device> Collect(const std::string& sysfs) {
    std::vector<Device> out;
    static const std::regex card_re("card[0-9]+");
    const std::string drm = sysfs + "/class/drm";
    for (const auto& name : ListDir(drm)) {
        if (!std::regex_match(name, card_re)) continue;  // skip connectors (card0-eDP-1) and renderD*
        Device d{.source = "drm", .node = name};
        const std::string dev = drm + "/" + name + "/device";
        d.driver = LinkTarget(dev + "/driver");
        // Walk up from the device (e.g. virtio1 under 0000:00:02.0) to its PCI function.
        char real[PATH_MAX];
        if (realpath(dev.c_str(), real)) {
            for (std::string p = real; p.size() > sysfs.size() && p != "/"; p = android::base::Dirname(p)) {
                if (IsPciSlot(android::base::Basename(p))) {
                    d.pci_slot = android::base::Basename(p);
                    ReadPciIds(p, &d);
                    break;
                }
            }
        }
        out.push_back(d);
    }
    const std::string pci = sysfs + "/bus/pci/devices";
    for (const auto& slot : ListDir(pci)) {
        Device d{.source = "pci", .node = slot, .pci_slot = slot};
        ReadPciIds(pci + "/" + slot, &d);
        if ((d.pci_class >> 16) != kClassDisplay) continue;
        d.driver = LinkTarget(pci + "/" + slot + "/driver");
        out.push_back(d);
    }
    return out;
}

std::string Format(const Device& d) {
    // A PCI device's node already is its slot.
    const std::string pci = d.source == "pci" ? "" : " pci=" + (d.pci_slot.empty() ? "-" : d.pci_slot);
    return d.source + " " + d.node + " driver=" + (d.driver.empty() ? "-" : d.driver) + pci +
           " vendor=" + Hex(d.vendor, 4) + " device=" + Hex(d.device, 4) + " class=" + Hex(d.pci_class, 6);
}

std::optional<Device> Parse(const std::string& line) {
    std::istringstream in(line);
    Device d;
    if (!(in >> d.source >> d.node) || (d.source != "drm" && d.source != "pci")) return std::nullopt;
    if (d.source == "pci") d.pci_slot = d.node;
    for (std::string kv; in >> kv;) {
        auto eq = kv.find('=');
        if (eq == std::string::npos) return std::nullopt;
        std::string k = kv.substr(0, eq), v = kv.substr(eq + 1);
        if (v == "-") v.clear();
        if (k == "driver") {
            d.driver = v;
        } else if (k == "pci") {
            d.pci_slot = v;
        } else if (k == "vendor" || k == "device" || k == "class") {
            uint32_t n = 0;
            if (!android::base::ParseUint(v, &n)) return std::nullopt;
            (k == "vendor" ? d.vendor : k == "device" ? d.device : d.pci_class) = n;
        } else {
            return std::nullopt;
        }
    }
    return d;
}

Result Decide(const std::vector<Device>& devices) {
    auto find = [&](const std::string& source, bool (*match)(const Device&)) -> const Device* {
        for (const auto& d : devices) {
            if (d.source != source || !match(d)) continue;
            // A DRM card must have its driver bound: that is what renders.
            if (source == "drm" && d.driver.empty()) continue;
            return &d;
        }
        return nullptr;
    };
    Result r{.hal = "none"};
    const Device* chosen = nullptr;
    if ((chosen = find("drm", IsAmd))) {
        r = Pick(*chosen, "amdgpu");
    } else if ((chosen = find("drm", IsVirtioGpu))) {
        r = Pick(*chosen, "virtio");
    } else if ((chosen = find("pci", IsAmd))) {
        r = Pick(*chosen, "amdgpu");
    } else if ((chosen = find("pci", IsVirtioGpu))) {
        r = Pick(*chosen, "virtio");
    }
    std::set<std::string> others;
    for (const auto& d : devices) {
        if (d.source != "pci" || (chosen && d.pci_slot == chosen->pci_slot)) continue;
        others.insert(VendorName(d.vendor));
    }
    r.others = android::base::Join(others, ",");
    return r;
}

}  // namespace anybook::gpu_probe
