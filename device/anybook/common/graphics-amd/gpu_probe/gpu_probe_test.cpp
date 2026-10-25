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

struct Fixture {
    std::vector<Device> devices;
    openbook::gfx::Firmware fw;
};

Fixture LoadFixture(const std::string& name) {
    std::string text;
    const std::string path = android::base::GetExecutableDirectory() + "/gpu_probe/testdata/" + name;
    EXPECT_TRUE(android::base::ReadFileToString(path, &text)) << path;
    Fixture f;
    for (const auto& line : android::base::Split(text, "\n")) {
        if (line.empty() || line[0] == '#') continue;
        if (line.rfind("fw ", 0) == 0) {
            auto fw = ParseFirmware(line);
            EXPECT_TRUE(fw) << name << ": " << line;
            if (fw) {
                EXPECT_EQ(FormatFirmware(*fw), line) << "FormatFirmware(ParseFirmware(line)) round trip";
                f.fw = *fw;
            }
            continue;
        }
        auto d = Parse(line);
        EXPECT_TRUE(d) << name << ": " << line;
        if (!d) continue;
        EXPECT_EQ(Format(*d), line) << "Format(Parse(line)) round trip";
        f.devices.push_back(*d);
    }
    return f;
}

struct Expectation {
    const char* fixture;
    Result want;
};

// Captures from real machines (see each file's header) and synthetic corner cases. Fields: hal pci_id driver
// source others pci_slot display_card render_node mode dgpu note.
const Expectation kExpectations[] = {
        {"g14-ga403wr.txt",
         {"amdgpu", "1002:150e", "amdgpu", "drm", "", "0000:65:00.0", "card1", "", "unknown", "absent", ""}},
        {"g14-ga403wr-early.txt",
         {"amdgpu", "1002:150e", "unbound", "pci", "", "0000:65:00.0", "", "", "unknown", "absent", ""}},
        {"g14-ga403wr-nouveau.txt",
         {"amdgpu", "1002:150e", "amdgpu", "drm", "nvidia", "0000:65:00.0", "card0", "", "unknown", "present", ""}},
        {"host-7950x-rtx4090.txt",
         {"amdgpu", "1002:164e", "amdgpu", "drm", "nvidia", "0000:12:00.0", "card0", "", "unknown", "present", ""}},
        {"cuttlefish-virtio.txt",
         {"virtio", "1af4:1050", "virtio-pci", "drm", "", "0000:00:02.0", "card0", "", "unknown", "absent", ""}},
        {"nvidia-only.txt", {"none", "", "", "", "nvidia", "", "", "", "unknown", "present", "no-display-gpu"}},
        {"vm-amd-vfio-virtio.txt",
         {"virtio", "1af4:1050", "virtio_gpu", "drm", "amd", "0000:00:02.0", "card0", "", "unknown", "absent", ""}},
        {"radeon-legacy.txt", {"none", "", "", "", "amd", "", "", "", "unknown", "absent", "no-display-gpu"}},
        {"no-gpu.txt", {"none", "", "", "", "", "", "", "", "unknown", "absent", "no-display-gpu"}},
        // ANAL-246: the G14's MUX states, with connectors and render nodes.
        {"g14-hybrid.txt",
         {"amdgpu", "1002:150e", "amdgpu", "drm", "nvidia", "0000:65:00.0", "card1", "renderD128", "hybrid", "present",
          ""}},
        {"g14-hybrid-nouveau-headless.txt",
         {"amdgpu", "1002:150e", "amdgpu", "drm", "nvidia", "0000:65:00.0", "card0", "renderD128", "hybrid", "present",
          ""}},
        {"g14-eco.txt",
         {"amdgpu", "1002:150e", "amdgpu", "drm", "", "0000:65:00.0", "card1", "renderD128", "eco", "absent", ""}},
        {"g14-ultimate.txt",
         {"nouveau", "10de:2f58", "nouveau", "drm", "amd", "0000:64:00.0", "card1", "renderD129", "ultimate",
          "display", ""}},
        {"g14-ultimate-igpu-hidden.txt",
         {"nouveau", "10de:2f58", "nouveau", "drm", "", "0000:64:00.0", "card0", "renderD128", "ultimate", "display",
          ""}},
        {"g14-ultimate-no-nouveau.txt",
         {"none", "", "", "", "amd,nvidia", "", "", "", "ultimate", "display", "no-display-gpu"}},
        {"g14-ultimate-panel-on-amdgpu.txt",
         {"amdgpu", "1002:150e", "amdgpu", "drm", "nvidia", "0000:65:00.0", "card0", "renderD128", "ultimate",
          "display", "ultimate-but-panel-on-amdgpu"}},
};

TEST(GpuProbe, Fixtures) {
    for (const auto& e : kExpectations) {
        SCOPED_TRACE(e.fixture);
        const Fixture f = LoadFixture(e.fixture);
        const Result r = Decide(f.devices, f.fw);
        EXPECT_EQ(r.hal, e.want.hal);
        EXPECT_EQ(r.pci_id, e.want.pci_id);
        EXPECT_EQ(r.driver, e.want.driver);
        EXPECT_EQ(r.source, e.want.source);
        EXPECT_EQ(r.others, e.want.others);
        EXPECT_EQ(r.pci_slot, e.want.pci_slot);
        EXPECT_EQ(r.display_card, e.want.display_card);
        EXPECT_EQ(r.render_node, e.want.render_node);
        EXPECT_EQ(r.mode, e.want.mode);
        EXPECT_EQ(r.dgpu, e.want.dgpu);
        EXPECT_EQ(r.note, e.want.note);
    }
}

TEST(GpuProbe, ParseRejectsGarbage) {
    EXPECT_FALSE(Parse("usb 1-1 driver=x"));
    EXPECT_FALSE(Parse("drm card0 driver"));
    EXPECT_FALSE(Parse("drm card0 vendor=amd"));
    EXPECT_FALSE(Parse("drm card0 color=red"));
    EXPECT_FALSE(Parse("drm card0 conn=:connected"));
    EXPECT_FALSE(Parse("drm card0 conn=eDP-1"));
    EXPECT_FALSE(Parse("pci 0000:65:00.0 conn=eDP-1:connected"));
    EXPECT_FALSE(ParseFirmware("fw mux=2 dgpu=0"));
    EXPECT_FALSE(ParseFirmware("fw mux=1 dgpu=0 extra"));
    EXPECT_FALSE(ParseFirmware("fw mux=1"));
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
              "drm card0 driver=amdgpu pci=0000:65:00.0 vendor=0x1002 device=0x150e class=0x038000 conn=eDP-1:-\n"
              "drm card1 driver=virtio_gpu pci=0000:00:02.0 vendor=0x1af4 device=0x1050 class=0x038000\n"
              "render renderD128 driver=amdgpu pci=0000:65:00.0 vendor=0x1002 device=0x150e class=0x038000\n"
              "pci 0000:00:02.0 driver=virtio-pci vendor=0x1af4 device=0x1050 class=0x038000\n"
              "pci 0000:65:00.0 driver=amdgpu vendor=0x1002 device=0x150e class=0x038000");
    const Result r = Decide(Collect(s.root()));
    EXPECT_EQ(r.hal, "amdgpu");
    EXPECT_EQ(r.display_card, "card0");
    EXPECT_EQ(r.render_node, "renderD128");

    // The pins: the chosen function's card (it has a connector: a KMS device) and render node, once /dev/dri has
    // them; nothing for a function without nodes.
    TemporaryDir dev;
    for (const char* node : {"card0", "renderD128"}) {
        ASSERT_TRUE(android::base::WriteStringToFile("", std::string(dev.path) + "/" + node));
    }
    const Pins p = FindPins(s.root(), dev.path, "0000:65:00.0", 0);
    EXPECT_EQ(p.card, "card0");
    EXPECT_EQ(p.render, "renderD128");
    EXPECT_TRUE(p.kms);
    const Pins v = FindPins(s.root(), dev.path, "0000:00:02.0", 0);  // card1 is not under /dev/dri here
    EXPECT_EQ(v.card, "");
    EXPECT_EQ(v.render, "");
}

}  // namespace
}  // namespace anybook::gpu_probe
