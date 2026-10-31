// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Picks the graphics HAL family for this boot from the GPUs in sysfs: amdgpu on AMD hardware,
// virtio (gfxstream/virgl, configured by the VM product) on virtio-gpu, none otherwise. On a laptop with an
// ASUS MUX it follows the panel (ANAL-246, docs/nvidia-graphics-modes.md §3): the GPU whose card has the
// connected internal panel wins, and nouveau's card only in Ultimate. The decision is openbook-gfx-mode's
// selector (device/anybook/common/gfx-mode/gfx_select.h); this file reads and writes its inputs.

#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "gfx_select.h"

namespace anybook::gpu_probe {

// One GPU as sysfs shows it: a DRM card, a render node, or a PCI display controller (class 0x03xxxx).
struct Device {
    std::string source;    // "drm", "render" or "pci"
    std::string node;      // "card0", "renderD128", or the PCI slot for source "pci"
    std::string driver;    // bound kernel driver, empty if none
    std::string pci_slot;  // PCI function behind the device, empty if none
    uint32_t vendor = 0;   // PCI IDs of that function (0 if none)
    uint32_t device = 0;
    uint32_t pci_class = 0;
    std::vector<openbook::gfx::Connector> connectors;  // DRM cards: card1-eDP-1 -> {eDP-1, connected}
};

// Reads <sysfs>/class/drm/card* (with their connectors), renderD*, and <sysfs>/bus/pci/devices/*.
std::vector<Device> Collect(const std::string& sysfs);

// One line per device, also the format of the test fixtures (testdata/*.txt):
//   drm card0 driver=amdgpu pci=0000:65:00.0 vendor=0x1002 device=0x150e class=0x038000 conn=eDP-1:connected
//   render renderD128 driver=amdgpu pci=0000:65:00.0 vendor=0x1002 device=0x150e class=0x038000
//   pci 0000:65:00.0 driver=amdgpu vendor=0x1002 device=0x150e class=0x038000
// and the MUX state, when the laptop has one:
//   fw mux=1 dgpu=0
std::string Format(const Device& d);
std::optional<Device> Parse(const std::string& line);
std::string FormatFirmware(const openbook::gfx::Firmware& fw);
std::optional<openbook::gfx::Firmware> ParseFirmware(const std::string& line);

struct Result {
    std::string hal;     // "amdgpu", "virtio", "nouveau" or "none"
    std::string pci_id;  // "1002:150e" for the chosen GPU, empty for "none"
    std::string driver;  // its bound driver, "unbound" if the PCI device has none yet
    std::string source;  // "drm" (bound DRM card) or "pci" (display controller, no card yet)
    std::string others;  // other display controllers by vendor, e.g. "nvidia"
    // ANAL-246: where the stack runs.
    std::string pci_slot;      // the chosen GPU's PCI function
    std::string display_card;  // its DRM card (card1), empty before its driver binds
    std::string render_node;   // its render node (renderD128), empty likewise
    std::string mode;          // the MUX state: eco, hybrid, ultimate, invalid, unknown (no MUX)
    std::string dgpu;          // absent, present, display
    std::string note;          // why a fallback was taken, empty if none
};

// The KMS card and render node of the PCI function SLOT, as they appear in sysfs and under DEV (/dev/dri), waiting
// up to WAIT_MS for the driver to create both. kms: the card has connectors (a display drm_hwcomposer can drive).
struct Pins {
    std::string card, render;
    bool kms = false;
};
Pins FindPins(const std::string& sysfs, const std::string& dev, const std::string& slot, int wait_ms);

// Bound DRM cards win over PCI devices whose driver has not bound yet; AMD wins over virtio-gpu; with a MUX the
// card that drives the connected panel wins.
Result Decide(const std::vector<Device>& devices, const openbook::gfx::Firmware& fw = {});

}  // namespace anybook::gpu_probe
