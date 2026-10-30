// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// The graphics stack for this boot (ANAL-241/246, docs/nvidia-graphics-modes.md §3): which GPU drives the panel,
// read from asus-wmi's MUX and the DRM connectors, never from the requested mode. Shared by anybook_gpu_probe (the
// selector at early-init) and openbook-gfx-mode (its `select` command, for the fixture tests). Plain C++17 with no
// Android libraries, so the same code runs in the host tests, the QEMU guest and the vendor image.

#pragma once

#include <optional>
#include <set>
#include <string>
#include <vector>

namespace openbook::gfx {

enum class Mode { kUnknown, kEco, kHybrid, kUltimate, kInvalid };

const char* ModeName(Mode m);
// Only the three selectable modes parse; anything else is refused.
std::optional<Mode> ParseMode(const std::string& s);

// asus-wmi's two firmware switches, as its sysfs attributes read.
struct Firmware {
    bool present = false;  // both attributes exist and read as 0 or 1
    int mux = -1;          // gpu_mux_mode: 1 Optimus (iGPU drives the panel), 0 dGPU
    int dgpu = -1;         // dgpu_disable: 1 dGPU off
};
Mode ModeOf(const Firmware& fw);
std::string FwString(const Firmware& fw);  // "mux=1,dgpu=0" or "absent"
Firmware ReadFirmware(const std::string& fw_dir);  // /sys/devices/platform/asus-nb-wmi

// One DRM card or render node, and the PCI function behind it.
struct Connector {
    std::string name;    // eDP-1, HDMI-A-1
    std::string status;  // connected, disconnected, unknown
};
struct Card {
    std::string node;    // card0, renderD128
    std::string driver;  // amdgpu, nouveau, virtio_gpu (the kernel may parent a virtio card on virtio-pci)
    std::string pci;     // 0000:65:00.0
    unsigned vendor = 0, device = 0, pci_class = 0;  // PCI IDs and class of that function
    std::vector<Connector> connectors;
};
struct PciFn {
    std::string slot;
    unsigned vendor = 0, device = 0, pci_class = 0;
    std::string driver;
};

struct Selection {
    std::string hal = "none";   // amdgpu, nouveau, virtio, none
    std::string source;         // drm (a bound DRM card) or pci (a display controller whose driver has not bound)
    std::string display_card;   // card1, or empty when no card was chosen
    std::string render_node;    // renderD128, or empty
    std::string pci;            // the chosen GPU's PCI function, or empty
    unsigned vendor = 0, device = 0;
    std::string driver;         // its bound driver, "unbound" for source pci
    std::string others;         // other display controllers by vendor, e.g. "nvidia"
    std::string dgpu = "absent";  // absent, present (not the display GPU), display
    std::string note;           // why a fallback was taken
};

bool IsPanel(const std::string& connector);  // eDP, LVDS, DSI
bool IsVirtioGpu(const std::string& driver, unsigned vendor, unsigned device);
std::string VendorName(unsigned vendor);

// Follow the panel, not the intent. In Ultimate the display GPU is nouveau's card with a connected panel; otherwise
// the card whose panel is connected wins. A fallback is named in note. Without a bound card, a PCI display
// controller amdgpu (or virtio-gpu) has not bound yet is chosen, as anybook_gpu_probe always did.
Selection Select(Mode mode, const std::vector<Card>& cards, const std::vector<Card>& render_nodes,
                 const std::vector<PciFn>& pci);

// sysfs readers: <sysfs>/class/drm/card* (with connectors) or renderD*, and <sysfs>/bus/pci/devices/*.
std::vector<Card> ReadCards(const std::string& sysfs, bool render);
std::vector<PciFn> ReadPci(const std::string& sysfs);

}  // namespace openbook::gfx
