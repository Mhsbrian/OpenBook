// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Picks the graphics HAL family for this boot from the GPUs in sysfs: amdgpu on AMD hardware,
// virtio (gfxstream/virgl, configured by the VM product) on virtio-gpu, none otherwise.

#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace anybook::gpu_probe {

// One GPU as sysfs shows it: a DRM card, or a PCI display controller (class 0x03xxxx).
struct Device {
    std::string source;    // "drm" or "pci"
    std::string node;      // "card0", or the PCI slot for source "pci"
    std::string driver;    // bound kernel driver, empty if none
    std::string pci_slot;  // PCI function behind the device, empty if none
    uint32_t vendor = 0;   // PCI IDs of that function (0 if none)
    uint32_t device = 0;
    uint32_t pci_class = 0;
};

// Reads <sysfs>/class/drm/card* and <sysfs>/bus/pci/devices/*.
std::vector<Device> Collect(const std::string& sysfs);

// One line per device, also the format of the test fixtures (testdata/*.txt):
//   drm card0 driver=amdgpu pci=0000:65:00.0 vendor=0x1002 device=0x150e class=0x038000
//   pci 0000:65:00.0 driver=amdgpu vendor=0x1002 device=0x150e class=0x038000
std::string Format(const Device& d);
std::optional<Device> Parse(const std::string& line);

struct Result {
    std::string hal;     // "amdgpu", "virtio" or "none"
    std::string pci_id;  // "1002:150e" for the chosen GPU, empty for "none"
    std::string driver;  // its bound driver, "unbound" if the PCI device has none yet
    std::string source;  // "drm" (bound DRM card) or "pci" (display controller, no card yet)
    std::string others;  // other display controllers by vendor, e.g. "nvidia"
};

// Bound DRM cards win over PCI devices whose driver has not bound yet; AMD wins over virtio-gpu.
Result Decide(const std::vector<Device>& devices);

}  // namespace anybook::gpu_probe
