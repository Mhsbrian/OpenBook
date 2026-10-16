// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// anybook_gpu_probe: run by init (init.anybook.graphics-amd.rc) at early-init. Publishes
//   vendor.anybook.gpu.hal     amdgpu | virtio | none
//   vendor.anybook.gpu.pci_id  vendor:device of the chosen GPU, e.g. 1002:150e
//   vendor.anybook.gpu.driver  its bound driver, or "unbound"
//   vendor.anybook.gpu.source  drm (bound DRM card) | pci (display controller, driver not bound yet)
//   vendor.anybook.gpu.others  other display controllers, e.g. "nvidia"
// and init maps vendor.anybook.gpu.hal=amdgpu to the AMD HAL properties.
//
// usage: anybook_gpu_probe [--sysfs DIR] [--list | --dry-run | --from FILE]
//   --list      print the GPUs found, one per line (the format of gpu_probe/testdata)
//   --dry-run   print the decision instead of setting properties
//   --from FILE decide from a --list capture instead of sysfs (implies --dry-run)

#include <cstdio>
#include <cstring>
#include <string>

#include <android-base/file.h>
#include <android-base/strings.h>
#ifdef __ANDROID__
#include <android-base/properties.h>
#endif

#include "gpu_probe.h"

using namespace anybook::gpu_probe;

int main(int argc, char** argv) {
    std::string sysfs = "/sys", from;
    bool list = false, dry_run = false;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--sysfs") && i + 1 < argc) {
            sysfs = argv[++i];
        } else if (!strcmp(argv[i], "--from") && i + 1 < argc) {
            from = argv[++i];
            dry_run = true;
        } else if (!strcmp(argv[i], "--list")) {
            list = true;
        } else if (!strcmp(argv[i], "--dry-run")) {
            dry_run = true;
        } else {
            fprintf(stderr, "usage: %s [--sysfs DIR] [--list | --dry-run | --from FILE]\n", argv[0]);
            return 2;
        }
    }

    std::vector<Device> devices;
    if (from.empty()) {
        devices = Collect(sysfs);
    } else {
        std::string text;
        if (!android::base::ReadFileToString(from, &text)) {
            perror(from.c_str());
            return 1;
        }
        for (const auto& line : android::base::Split(text, "\n")) {
            if (line.empty() || line[0] == '#') continue;
            auto d = Parse(line);
            if (!d) {
                fprintf(stderr, "%s: bad line: %s\n", from.c_str(), line.c_str());
                return 1;
            }
            devices.push_back(*d);
        }
    }

    if (list) {
        for (const auto& d : devices) printf("%s\n", Format(d).c_str());
        return 0;
    }

    const Result r = Decide(devices);
    // hal goes last: init acts on it, and its actions may read the others.
    const std::pair<const char*, const std::string*> props[] = {
            {"vendor.anybook.gpu.pci_id", &r.pci_id}, {"vendor.anybook.gpu.driver", &r.driver},
            {"vendor.anybook.gpu.source", &r.source}, {"vendor.anybook.gpu.others", &r.others},
            {"vendor.anybook.gpu.hal", &r.hal},
    };
    // stdout goes to the kernel log at boot (stdio_to_kmsg), so the GPUs seen are on record.
    if (!dry_run) {
        for (const auto& d : devices) printf("anybook_gpu_probe: %s\n", Format(d).c_str());
    }
    for (const auto& [name, value] : props) {
        if (dry_run) {
            printf("%s=%s\n", name, value->c_str());
            continue;
        }
#ifdef __ANDROID__
        if (!value->empty() && !android::base::SetProperty(name, *value)) {
            fprintf(stderr, "anybook_gpu_probe: cannot set %s\n", name);
            return 1;
        }
#endif
    }
    if (!dry_run) printf("anybook_gpu_probe: hal=%s pci_id=%s driver=%s source=%s others=%s\n",
                         r.hal.c_str(), r.pci_id.c_str(), r.driver.c_str(), r.source.c_str(), r.others.c_str());
    return 0;
}
