// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "gfx_select.h"

#include <stdio.h>

#include <algorithm>

#include "gfx_util.h"

namespace openbook::gfx {
namespace {

using namespace util;

constexpr unsigned kVendorAmd = 0x1002;
constexpr unsigned kVendorNvidia = 0x10de;
constexpr unsigned kVendorRedHat = 0x1af4;  // virtio
constexpr unsigned kDeviceVirtioGpu = 0x1050;
constexpr unsigned kClassDisplay = 0x03;  // PCI base class: display controller

bool IsDisplay(const PciFn& f) { return (f.pci_class >> 16) == kClassDisplay; }

std::string Hex4(unsigned v) {
    char buf[8];
    snprintf(buf, sizeof(buf), "%04x", v & 0xffff);
    return buf;
}

}  // namespace

const char* ModeName(Mode m) {
    switch (m) {
        case Mode::kEco: return "eco";
        case Mode::kHybrid: return "hybrid";
        case Mode::kUltimate: return "ultimate";
        case Mode::kInvalid: return "invalid";
        default: return "unknown";
    }
}

std::optional<Mode> ParseMode(const std::string& s) {
    if (s == "eco") return Mode::kEco;
    if (s == "hybrid") return Mode::kHybrid;
    if (s == "ultimate") return Mode::kUltimate;
    return std::nullopt;
}

Mode ModeOf(const Firmware& fw) {
    if (!fw.present) return Mode::kUnknown;
    if (fw.mux == 1) return fw.dgpu == 1 ? Mode::kEco : Mode::kHybrid;
    return fw.dgpu == 1 ? Mode::kInvalid : Mode::kUltimate;  // the kernel refuses to make mux=0 dgpu=1
}

std::string FwString(const Firmware& fw) {
    if (!fw.present) return "absent";
    return "mux=" + std::to_string(fw.mux) + ",dgpu=" + std::to_string(fw.dgpu);
}

Firmware ReadFirmware(const std::string& fw_dir) {
    Firmware fw;
    std::string mux, dgpu;
    if (ReadFile(fw_dir + "/gpu_mux_mode", &mux) && ReadFile(fw_dir + "/dgpu_disable", &dgpu) &&
        ParseInt(mux, &fw.mux) && ParseInt(dgpu, &fw.dgpu) && (fw.mux == 0 || fw.mux == 1) &&
        (fw.dgpu == 0 || fw.dgpu == 1)) {
        fw.present = true;
    } else {
        fw = Firmware{};
    }
    return fw;
}

bool IsPanel(const std::string& c) {
    return c.rfind("eDP-", 0) == 0 || c.rfind("LVDS-", 0) == 0 || c.rfind("DSI-", 0) == 0;
}

bool IsVirtioGpu(const std::string& driver, unsigned vendor, unsigned device) {
    return driver == "virtio_gpu" || (vendor == kVendorRedHat && device == kDeviceVirtioGpu && !driver.empty());
}

std::string VendorName(unsigned vendor) {
    switch (vendor) {
        case kVendorAmd: return "amd";
        case kVendorNvidia: return "nvidia";
        case 0x8086: return "intel";
        case kVendorRedHat: return "virtio";
        default: return "0x" + Hex4(vendor);
    }
}

Selection Select(Mode mode, const std::vector<Card>& cards, const std::vector<Card>& render_nodes,
                 const std::vector<PciFn>& pci) {
    auto panel = [](const Card& c) {
        return std::any_of(c.connectors.begin(), c.connectors.end(),
                           [](const Connector& k) { return IsPanel(k.name) && k.status == "connected"; });
    };
    auto kind = [](const Card& c) -> std::string {
        if (c.driver == "amdgpu" || c.driver == "nouveau") return c.driver;
        return IsVirtioGpu(c.driver, c.vendor, c.device) ? "virtio" : "";
    };
    auto find = [&](const std::string& k, bool need_panel) -> const Card* {
        for (const auto& c : cards) {
            if (kind(c) == k && (!need_panel || panel(c))) return &c;
        }
        return nullptr;
    };
    Selection s;
    const Card* chosen = nullptr;
    const PciFn* unbound = nullptr;
    if (mode == Mode::kUltimate) {
        if ((chosen = find("nouveau", true))) {
            s.hal = "nouveau";
        } else if ((chosen = find("amdgpu", true))) {
            s.hal = "amdgpu";
            s.note = "ultimate-but-panel-on-amdgpu";
        } else if ((chosen = find("nouveau", false))) {
            s.hal = "nouveau";
            s.note = "no-connected-panel";
        } else {
            s.note = "no-display-gpu";
        }
    } else {
        if ((chosen = find("amdgpu", true))) {
            s.hal = "amdgpu";
        } else if ((chosen = find("nouveau", true))) {
            s.hal = "nouveau";
            s.note = "panel-on-nouveau-in-optimus";
        } else if ((chosen = find("amdgpu", false))) {
            s.hal = "amdgpu";
            if (!chosen->connectors.empty()) s.note = "no-connected-panel";
        } else if ((chosen = find("virtio", false))) {
            s.hal = "virtio";
        } else {
            // No card yet: a display controller its driver has not bound (amdgpu still loading, or virtio-gpu,
            // whose module the VM fallback loads later). Not one claimed by radeon, vfio-pci or nvidia.
            for (const auto& f : pci) {
                if (IsDisplay(f) && f.vendor == kVendorAmd && (f.driver.empty() || f.driver == "amdgpu")) {
                    unbound = &f;
                    s.hal = "amdgpu";
                    break;
                }
            }
            for (const auto& f : pci) {
                if (unbound) break;
                if (IsDisplay(f) && f.vendor == kVendorRedHat && f.device == kDeviceVirtioGpu) {
                    unbound = &f;
                    s.hal = "virtio";
                }
            }
            if (!unbound) s.note = "no-display-gpu";
        }
    }
    if (chosen) {
        s.source = "drm";
        s.display_card = chosen->node;
        s.pci = chosen->pci;
        s.vendor = chosen->vendor;
        s.device = chosen->device;
        s.driver = chosen->driver;
        for (const auto& r : render_nodes) {
            if (!chosen->pci.empty() && r.pci == chosen->pci) {
                s.render_node = r.node;
                break;
            }
        }
    } else if (unbound) {
        s.source = "pci";
        s.pci = unbound->slot;
        s.vendor = unbound->vendor;
        s.device = unbound->device;
        s.driver = unbound->driver.empty() ? "unbound" : unbound->driver;
    }
    std::set<std::string> others;
    bool dgpu = false;
    for (const auto& f : pci) {
        if (!IsDisplay(f)) continue;
        dgpu |= f.vendor == kVendorNvidia;
        if (!s.pci.empty() && f.slot == s.pci) continue;
        others.insert(VendorName(f.vendor));
    }
    for (const auto& o : others) s.others += (s.others.empty() ? "" : ",") + o;
    s.dgpu = !dgpu ? "absent" : s.hal == "nouveau" || mode == Mode::kUltimate ? "display" : "present";
    return s;
}

std::vector<Card> ReadCards(const std::string& sysfs, bool render) {
    std::vector<Card> out;
    const std::string drm = sysfs + "/class/drm";
    const std::vector<std::string> names = ListDir(drm);
    const std::string prefix = render ? "renderD" : "card";
    for (const auto& name : names) {
        if (name.rfind(prefix, 0) != 0 || name.size() == prefix.size()) continue;
        if (!std::all_of(name.begin() + prefix.size(), name.end(), ::isdigit)) continue;  // skip card0-eDP-1
        Card c;
        c.node = name;
        const std::string dev = drm + "/" + name + "/device";
        c.driver = LinkBasename(dev + "/driver");
        // Walk up from the device (virtio1 under 0000:00:02.0, for instance) to its PCI function; without a
        // device link, from the node's own directory, which sits below that function too.
        char real[PATH_MAX];
        if (realpath(dev.c_str(), real) || realpath((drm + "/" + name).c_str(), real)) {
            for (std::string p = real; p.size() > 1; p = p.substr(0, p.find_last_of('/'))) {
                if (IsPciSlot(Basename(p))) {
                    c.pci = Basename(p);
                    c.vendor = ReadHex(p + "/vendor");
                    c.device = ReadHex(p + "/device");
                    c.pci_class = ReadHex(p + "/class");
                    if (c.driver.empty()) c.driver = LinkBasename(p + "/driver");
                    break;
                }
                if (p.find('/') == std::string::npos) break;
            }
        }
        if (!render) {
            for (const auto& conn : names) {
                if (conn.rfind(name + "-", 0) != 0) continue;
                std::string status;
                ReadFile(drm + "/" + conn + "/status", &status);
                c.connectors.push_back({conn.substr(name.size() + 1), Trim(status)});
            }
        }
        out.push_back(c);
    }
    return out;
}

std::vector<PciFn> ReadPci(const std::string& sysfs) {
    std::vector<PciFn> out;
    const std::string dir = sysfs + "/bus/pci/devices";
    for (const auto& slot : ListDir(dir)) {
        PciFn f;
        f.slot = slot;
        f.vendor = ReadHex(dir + "/" + slot + "/vendor");
        f.device = ReadHex(dir + "/" + slot + "/device");
        f.pci_class = ReadHex(dir + "/" + slot + "/class");
        f.driver = LinkBasename(dir + "/" + slot + "/driver");
        out.push_back(f);
    }
    return out;
}

}  // namespace openbook::gfx
