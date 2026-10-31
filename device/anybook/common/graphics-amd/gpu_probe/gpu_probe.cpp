// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "gpu_probe.h"

#include <sys/stat.h>

#include <chrono>
#include <cstdio>
#include <sstream>
#include <thread>

#include <android-base/parseint.h>
#include <android-base/strings.h>

namespace anybook::gpu_probe {
namespace {

namespace gfx = openbook::gfx;

constexpr uint32_t kClassDisplay = 0x03;  // PCI base class: display controller

std::string Hex(uint32_t v, int width) {
    char buf[16];
    snprintf(buf, sizeof(buf), "0x%0*x", width, v);
    return buf;
}

Device FromCard(const gfx::Card& c, const std::string& source) {
    Device d{.source = source, .node = c.node, .driver = c.driver, .pci_slot = c.pci};
    d.vendor = c.vendor;
    d.device = c.device;
    d.pci_class = c.pci_class;
    d.connectors = c.connectors;
    return d;
}

gfx::Card ToCard(const Device& d) {
    gfx::Card c;
    c.node = d.node;
    c.driver = d.driver;
    c.pci = d.pci_slot;
    c.vendor = d.vendor;
    c.device = d.device;
    c.pci_class = d.pci_class;
    c.connectors = d.connectors;
    return c;
}

}  // namespace

std::vector<Device> Collect(const std::string& sysfs) {
    std::vector<Device> out;
    for (const auto& c : gfx::ReadCards(sysfs, false)) out.push_back(FromCard(c, "drm"));
    for (const auto& c : gfx::ReadCards(sysfs, true)) out.push_back(FromCard(c, "render"));
    for (const auto& f : gfx::ReadPci(sysfs)) {
        if ((f.pci_class >> 16) != kClassDisplay) continue;
        Device d{.source = "pci", .node = f.slot, .driver = f.driver, .pci_slot = f.slot};
        d.vendor = f.vendor;
        d.device = f.device;
        d.pci_class = f.pci_class;
        out.push_back(d);
    }
    return out;
}

std::string Format(const Device& d) {
    // A PCI device's node already is its slot.
    const std::string pci = d.source == "pci" ? "" : " pci=" + (d.pci_slot.empty() ? "-" : d.pci_slot);
    std::string line = d.source + " " + d.node + " driver=" + (d.driver.empty() ? "-" : d.driver) + pci +
                       " vendor=" + Hex(d.vendor, 4) + " device=" + Hex(d.device, 4) + " class=" + Hex(d.pci_class, 6);
    if (!d.connectors.empty()) {
        std::vector<std::string> conns;
        for (const auto& c : d.connectors) conns.push_back(c.name + ":" + (c.status.empty() ? "-" : c.status));
        line += " conn=" + android::base::Join(conns, ",");
    }
    return line;
}

std::optional<Device> Parse(const std::string& line) {
    std::istringstream in(line);
    Device d;
    if (!(in >> d.source >> d.node) || (d.source != "drm" && d.source != "render" && d.source != "pci")) {
        return std::nullopt;
    }
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
        } else if (k == "conn" && d.source == "drm" && !v.empty()) {
            for (const auto& c : android::base::Split(v, ",")) {
                auto colon = c.find(':');
                if (colon == std::string::npos || colon == 0) return std::nullopt;
                std::string status = c.substr(colon + 1);
                d.connectors.push_back({c.substr(0, colon), status == "-" ? "" : status});
            }
        } else {
            return std::nullopt;
        }
    }
    return d;
}

std::string FormatFirmware(const gfx::Firmware& fw) {
    return fw.present ? "fw mux=" + std::to_string(fw.mux) + " dgpu=" + std::to_string(fw.dgpu) : "fw absent";
}

std::optional<gfx::Firmware> ParseFirmware(const std::string& line) {
    if (line == "fw absent") return gfx::Firmware{};
    int mux = -1, dgpu = -1;
    char tail = 0;
    if (sscanf(line.c_str(), "fw mux=%d dgpu=%d%c", &mux, &dgpu, &tail) != 2 || (mux != 0 && mux != 1) ||
        (dgpu != 0 && dgpu != 1)) {
        return std::nullopt;
    }
    return gfx::Firmware{.present = true, .mux = mux, .dgpu = dgpu};
}

Pins FindPins(const std::string& sysfs, const std::string& dev, const std::string& slot, int wait_ms) {
    auto exists = [&](const std::string& node) {
        struct stat st;
        return stat((dev + "/" + node).c_str(), &st) == 0;
    };
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(wait_ms);
    for (;;) {
        Pins p;
        for (const auto& c : gfx::ReadCards(sysfs, false)) {
            if (c.pci == slot && exists(c.node)) {
                p.card = c.node;
                p.kms = !c.connectors.empty();
                break;
            }
        }
        for (const auto& r : gfx::ReadCards(sysfs, true)) {
            if (r.pci == slot && exists(r.node)) {
                p.render = r.node;
                break;
            }
        }
        if ((!p.card.empty() && !p.render.empty()) || std::chrono::steady_clock::now() >= deadline) return p;
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
}

Result Decide(const std::vector<Device>& devices, const gfx::Firmware& fw) {
    std::vector<gfx::Card> cards, renders;
    std::vector<gfx::PciFn> pci;
    for (const auto& d : devices) {
        if (d.source == "drm") cards.push_back(ToCard(d));
        if (d.source == "render") renders.push_back(ToCard(d));
        if (d.source == "pci") {
            pci.push_back({.slot = d.pci_slot, .vendor = d.vendor, .device = d.device, .pci_class = d.pci_class,
                           .driver = d.driver});
        }
    }
    const gfx::Mode mode = gfx::ModeOf(fw);
    const gfx::Selection s = gfx::Select(mode, cards, renders, pci);
    char id[16] = "";
    if (s.vendor) snprintf(id, sizeof(id), "%04x:%04x", s.vendor, s.device);
    return {.hal = s.hal, .pci_id = id, .driver = s.driver, .source = s.source, .others = s.others,
            .pci_slot = s.pci, .display_card = s.display_card, .render_node = s.render_node,
            .mode = gfx::ModeName(mode), .dgpu = s.dgpu, .note = s.note};
}

}  // namespace anybook::gpu_probe
