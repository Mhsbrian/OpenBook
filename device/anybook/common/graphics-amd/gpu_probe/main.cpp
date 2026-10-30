// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// anybook_gpu_probe: run by init (init.anybook.graphics-amd.rc) at early-init. Publishes
//   vendor.anybook.gpu.hal          amdgpu | virtio | nouveau | none
//   vendor.anybook.gpu.pci_id       vendor:device of the chosen GPU, e.g. 1002:150e
//   vendor.anybook.gpu.driver       its bound driver, or "unbound"
//   vendor.anybook.gpu.source       drm (bound DRM card) | pci (display controller, driver not bound yet)
//   vendor.anybook.gpu.others       other display controllers, e.g. "nvidia"
//   vendor.anybook.gpu.pci_slot     the chosen GPU's PCI function (ANAL-246)
//   vendor.anybook.gpu.mode         the MUX state it followed: eco | hybrid | ultimate | invalid | unknown
//   vendor.anybook.gpu.dgpu         absent | present | display
//   vendor.anybook.gpu.note         a fallback it took, or "none"
// and init maps vendor.anybook.gpu.hal to the HAL properties.
//
// --pin, after the HAL event (the GPU's driver has bound by then): pins the composer and gralloc to the chosen
// GPU, so neither can move to another one, such as the dGPU in Hybrid (docs/nvidia-graphics-modes.md §3):
//   vendor.hwc.drm.device           /dev/dri/cardN, the chosen GPU's KMS card (drm_hwcomposer opens only it)
//   vendor.minigbm.render_node      renderDN, its render node (minigbm tries it first)
//   vendor.anybook.gpu.display_card, vendor.anybook.gpu.render_node   the same names, or "none"
// It waits up to --wait-ms for them to appear, and pins nothing it cannot find.
//
// usage: anybook_gpu_probe [--sysfs DIR] [--fw DIR] [--dev DIR] [--list | --dry-run | --from FILE | --pin [--wait-ms N]]
//   --list      print the GPUs found, one per line (the format of gpu_probe/testdata)
//   --dry-run   print the decision instead of setting properties
//   --from FILE decide from a --list capture instead of sysfs (implies --dry-run)

#include <cstdio>
#include <cstring>
#include <string>

#include <android-base/file.h>
#include <android-base/parseint.h>
#include <android-base/strings.h>
#ifdef __ANDROID__
#include <android-base/properties.h>
#include <android/log.h>
#endif

#include "gfx_util.h"
#include "gpu_probe.h"

using namespace anybook::gpu_probe;
namespace gfx = openbook::gfx;

namespace {

// A line for the record: the kernel log and logcat on Android (gfx_util.h's KernelLog), stdout elsewhere. As user
// system the probe may not open /dev/kmsg itself, and at early init logd is not up yet, so --pin, which runs once it
// is, repeats the early decision.
void Note(const std::string& line) {
#ifdef __ANDROID__
    openbook::gfx::util::KernelLog("anybook_gpu_probe", line);
    __android_log_write(ANDROID_LOG_INFO, "anybook_gpu_probe", line.c_str());
#else
    printf("anybook_gpu_probe: %s\n", line.c_str());
#endif
}

bool Set(bool dry_run, const char* name, const std::string& value) {
    if (dry_run) {
        printf("%s=%s\n", name, value.c_str());
        return true;
    }
#ifdef __ANDROID__
    if (!value.empty() && !android::base::SetProperty(name, value)) {
        fprintf(stderr, "anybook_gpu_probe: cannot set %s\n", name);
        return false;
    }
#endif
    return true;
}

// The composer and gralloc pins for the GPU the early-init decision chose (its PCI function).
int Pin(const std::string& sysfs, const std::string& dev, const std::string& slot, int wait_ms, bool dry_run) {
    const Pins p = FindPins(sysfs, dev, slot, wait_ms);
    Note("pin " + slot + ": card " + (p.card.empty() ? "-" : p.card) +
         (p.card.empty() || p.kms ? "" : " (no connectors: not pinned)") + " render " + (p.render.empty() ? "-" : p.render));
    bool ok = true;
    if (!p.card.empty() && p.kms) ok &= Set(dry_run, "vendor.hwc.drm.device", dev + "/" + p.card);
    if (!p.render.empty()) ok &= Set(dry_run, "vendor.minigbm.render_node", p.render);
    ok &= Set(dry_run, "vendor.anybook.gpu.display_card", p.card.empty() ? "none" : p.card);
    ok &= Set(dry_run, "vendor.anybook.gpu.render_node", p.render.empty() ? "none" : p.render);
    return ok ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
    std::string sysfs = "/sys", fw_dir = "/sys/devices/platform/asus-nb-wmi", dev = "/dev/dri", from;
    bool list = false, dry_run = false, pin = false;
    int wait_ms = 5000;
    auto usage = [&]() {
        fprintf(stderr,
                "usage: %s [--sysfs DIR] [--fw DIR] [--dev DIR] [--list | --dry-run | --from FILE | --pin "
                "[--wait-ms N]]\n",
                argv[0]);
        return 2;
    };
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--sysfs") && i + 1 < argc) {
            sysfs = argv[++i];
        } else if (!strcmp(argv[i], "--fw") && i + 1 < argc) {
            fw_dir = argv[++i];
        } else if (!strcmp(argv[i], "--dev") && i + 1 < argc) {
            dev = argv[++i];
        } else if (!strcmp(argv[i], "--from") && i + 1 < argc) {
            from = argv[++i];
            dry_run = true;
        } else if (!strcmp(argv[i], "--wait-ms") && i + 1 < argc) {
            if (!android::base::ParseInt(argv[++i], &wait_ms, 0, 60000)) return usage();
        } else if (!strcmp(argv[i], "--list")) {
            list = true;
        } else if (!strcmp(argv[i], "--dry-run")) {
            dry_run = true;
        } else if (!strcmp(argv[i], "--pin")) {
            pin = true;
        } else {
            return usage();
        }
    }

    if (pin) {
        std::string slot;
#ifdef __ANDROID__
        auto prop = [](const char* name) { return android::base::GetProperty(name, ""); };
        slot = prop("vendor.anybook.gpu.pci_slot");
        Note("early init chose hal=" + prop("vendor.anybook.gpu.hal") + " mode=" + prop("vendor.anybook.gpu.mode") +
             " source=" + prop("vendor.anybook.gpu.source") + " note=" + prop("vendor.anybook.gpu.note"));
#endif
        if (slot.empty()) {
            Note("pin: no GPU was chosen at early-init; nothing pinned");
            return 0;
        }
        return Pin(sysfs, dev, slot, wait_ms, dry_run);
    }

    std::vector<Device> devices;
    gfx::Firmware fw;
    if (from.empty()) {
        devices = Collect(sysfs);
        fw = gfx::ReadFirmware(fw_dir);
    } else {
        std::string text;
        if (!android::base::ReadFileToString(from, &text)) {
            perror(from.c_str());
            return 1;
        }
        for (const auto& line : android::base::Split(text, "\n")) {
            if (line.empty() || line[0] == '#') continue;
            if (line.rfind("fw ", 0) == 0) {
                auto f = ParseFirmware(line);
                if (!f) {
                    fprintf(stderr, "%s: bad line: %s\n", from.c_str(), line.c_str());
                    return 1;
                }
                fw = *f;
                continue;
            }
            auto d = Parse(line);
            if (!d) {
                fprintf(stderr, "%s: bad line: %s\n", from.c_str(), line.c_str());
                return 1;
            }
            devices.push_back(*d);
        }
    }

    if (list) {
        if (fw.present) printf("%s\n", FormatFirmware(fw).c_str());
        for (const auto& d : devices) printf("%s\n", Format(d).c_str());
        return 0;
    }

    const Result r = Decide(devices, fw);
    // hal goes last: init acts on it, and its actions may read the others.
    const std::pair<const char*, const std::string*> props[] = {
            {"vendor.anybook.gpu.pci_id", &r.pci_id},     {"vendor.anybook.gpu.driver", &r.driver},
            {"vendor.anybook.gpu.source", &r.source},     {"vendor.anybook.gpu.others", &r.others},
            {"vendor.anybook.gpu.pci_slot", &r.pci_slot}, {"vendor.anybook.gpu.mode", &r.mode},
            {"vendor.anybook.gpu.dgpu", &r.dgpu},         {"vendor.anybook.gpu.hal", &r.hal},
    };
    // The GPUs seen go to the kernel log at boot, so they are on record.
    if (!dry_run) {
        if (fw.present) Note(FormatFirmware(fw));
        for (const auto& d : devices) Note(Format(d));
    }
    if (!Set(dry_run, "vendor.anybook.gpu.note", r.note.empty() ? "none" : r.note)) return 1;
    for (const auto& [name, value] : props) {
        if (!Set(dry_run, name, *value)) return 1;
    }
    if (dry_run) {
        printf("display_card=%s\nrender_node=%s\n", r.display_card.c_str(), r.render_node.c_str());
    } else {
        Note("hal=" + r.hal + " pci_id=" + r.pci_id + " driver=" + r.driver + " source=" + r.source + " others=" +
             r.others + " mode=" + r.mode + " card=" + (r.display_card.empty() ? "-" : r.display_card) + " render=" +
             (r.render_node.empty() ? "-" : r.render_node) + " dgpu=" + r.dgpu + (r.note.empty() ? "" : " note=" + r.note));
    }
    return 0;
}
