// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "gpu_probe.h"

#include <sys/stat.h>
#include <unistd.h>

#include <android-base/file.h>
#include <android-base/strings.h>
#include <gtest/gtest.h>

namespace anybook::gpu_probe {
namespace {

std::vector<Device> LoadFixture(const std::string& name) {
    std::string text;
    const std::string path = android::base::GetExecutableDirectory() + "/gpu_probe/testdata/" + name;
    EXPECT_TRUE(android::base::ReadFileToString(path, &text)) << path;
    std::vector<Device> devices;
    for (const auto& line : android::base::Split(text, "\n")) {
        if (line.empty() || line[0] == '#') continue;
        auto d = Parse(line);
        EXPECT_TRUE(d) << name << ": " << line;
        if (!d) continue;
        EXPECT_EQ(Format(*d), line) << "Format(Parse(line)) round trip";
        devices.push_back(*d);
    }
    return devices;
}

struct Expectation {
    const char* fixture;
    Result want;
};

// Captures from real machines (see each file's header) and synthetic corner cases.
const Expectation kExpectations[] = {
        {"g14-ga403wr.txt", {"amdgpu", "1002:150e", "amdgpu", "drm", ""}},
        {"g14-ga403wr-early.txt", {"amdgpu", "1002:150e", "unbound", "pci", ""}},
        {"g14-ga403wr-nouveau.txt", {"amdgpu", "1002:150e", "amdgpu", "drm", "nvidia"}},
        {"host-7950x-rtx4090.txt", {"amdgpu", "1002:164e", "amdgpu", "drm", "nvidia"}},
        {"cuttlefish-virtio.txt", {"virtio", "1af4:1050", "virtio-pci", "drm", ""}},
        {"nvidia-only.txt", {"none", "", "", "", "nvidia"}},
        {"vm-amd-vfio-virtio.txt", {"virtio", "1af4:1050", "virtio_gpu", "drm", "amd"}},
        {"radeon-legacy.txt", {"none", "", "", "", "amd"}},
        {"no-gpu.txt", {"none", "", "", "", ""}},
};

TEST(GpuProbe, Fixtures) {
    for (const auto& e : kExpectations) {
        SCOPED_TRACE(e.fixture);
        const Result r = Decide(LoadFixture(e.fixture));
        EXPECT_EQ(r.hal, e.want.hal);
        EXPECT_EQ(r.pci_id, e.want.pci_id);
        EXPECT_EQ(r.driver, e.want.driver);
        EXPECT_EQ(r.source, e.want.source);
        EXPECT_EQ(r.others, e.want.others);
    }
}

TEST(GpuProbe, ParseRejectsGarbage) {
    EXPECT_FALSE(Parse("usb 1-1 driver=x"));
    EXPECT_FALSE(Parse("drm card0 driver"));
    EXPECT_FALSE(Parse("drm card0 vendor=amd"));
    EXPECT_FALSE(Parse("drm card0 color=red"));
}

// Collect() against a sysfs-shaped tree with the symlinks the kernel creates.
class FakeSysfs {
  public:
    FakeSysfs() { root_ = dir_.path; }
    void File(const std::string& path, const std::string& content) {
        Mkdirs(android::base::Dirname(path));
        ASSERT_TRUE(android::base::WriteStringToFile(content, root_ + "/" + path));
    }
    void Link(const std::string& path, const std::string& target) {
        Mkdirs(android::base::Dirname(path));
        ASSERT_EQ(0, symlink(target.c_str(), (root_ + "/" + path).c_str())) << path;
    }
    void Mkdirs(const std::string& path) {
        std::string p = root_;
        for (const auto& part : android::base::Split(path, "/")) {
            if (part.empty() || part == ".") continue;
            p += "/" + part;
            mkdir(p.c_str(), 0755);
        }
    }
    const std::string& root() const { return root_; }

  private:
    TemporaryDir dir_;
    std::string root_;
};

TEST(GpuProbe, CollectFromSysfs) {
    FakeSysfs s;
    // AMD GPU at 0000:65:00.0 with DRM card0, a connector and a render node.
    const std::string amd = "devices/pci0000:00/0000:00:08.1/0000:65:00.0";
    s.File(amd + "/vendor", "0x1002\n");
    s.File(amd + "/device", "0x150e\n");
    s.File(amd + "/class", "0x038000\n");
    s.Mkdirs("bus/pci/drivers/amdgpu");
    s.Link(amd + "/driver", "../../../../bus/pci/drivers/amdgpu");
    s.Mkdirs(amd + "/drm/card0");
    s.Link(amd + "/drm/card0/device", "../../../0000:65:00.0");
    s.Link("class/drm/card0", "../../" + amd + "/drm/card0");
    s.Mkdirs(amd + "/drm/card0/card0-eDP-1");
    s.Link("class/drm/card0-eDP-1", "../../" + amd + "/drm/card0/card0-eDP-1");
    s.Mkdirs(amd + "/drm/renderD128");
    s.Link("class/drm/renderD128", "../../" + amd + "/drm/renderD128");
    s.Link("bus/pci/devices/0000:65:00.0", "../../../" + amd);
    // virtio-gpu with the DRM device below virtio1 (Cuttlefish's 6.12 kernel parents it on the PCI
    // function instead; see testdata/cuttlefish-virtio.txt). Either way the walk finds 0000:00:02.0.
    const std::string vio = "devices/pci0000:00/0000:00:02.0";
    s.File(vio + "/vendor", "0x1af4\n");
    s.File(vio + "/device", "0x1050\n");
    s.File(vio + "/class", "0x038000\n");
    s.Mkdirs("bus/pci/drivers/virtio-pci");
    s.Link(vio + "/driver", "../../../bus/pci/drivers/virtio-pci");
    s.Mkdirs("bus/virtio/drivers/virtio_gpu");
    s.Mkdirs(vio + "/virtio1/drm/card1");
    s.Link(vio + "/virtio1/driver", "../../../../bus/virtio/drivers/virtio_gpu");
    s.Link(vio + "/virtio1/drm/card1/device", "../../../virtio1");
    s.Link("class/drm/card1", "../../" + vio + "/virtio1/drm/card1");
    s.Link("bus/pci/devices/0000:00:02.0", "../../../" + vio);
    // A NIC, which is not a display controller.
    const std::string nic = "devices/pci0000:00/0000:00:1c.0/0000:66:00.0";
    s.File(nic + "/vendor", "0x14c3\n");
    s.File(nic + "/device", "0x7925\n");
    s.File(nic + "/class", "0x028000\n");
    s.Link("bus/pci/devices/0000:66:00.0", "../../../" + nic);

    std::vector<std::string> lines;
    for (const auto& d : Collect(s.root())) lines.push_back(Format(d));
    EXPECT_EQ(android::base::Join(lines, "\n"),
              "drm card0 driver=amdgpu pci=0000:65:00.0 vendor=0x1002 device=0x150e class=0x038000\n"
              "drm card1 driver=virtio_gpu pci=0000:00:02.0 vendor=0x1af4 device=0x1050 class=0x038000\n"
              "pci 0000:00:02.0 driver=virtio-pci vendor=0x1af4 device=0x1050 class=0x038000\n"
              "pci 0000:65:00.0 driver=amdgpu vendor=0x1002 device=0x150e class=0x038000");
    EXPECT_EQ(Decide(Collect(s.root())).hal, "amdgpu");
}

}  // namespace
}  // namespace anybook::gpu_probe
