// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Host tests for the OpenBook HAL logic on fixture sysfs trees. The G14 fixtures follow the GA403WR inventory
// (evidence/2026-10-16-ga403wr-inventory): amdgpu_bl1 raw max 400000, ACPI zones THRM and TZ01, BAT1, ucsi.

#include <sys/stat.h>
#include <unistd.h>

#include <cmath>
#include <string>

#include <android-base/file.h>
#include <gtest/gtest.h>

#include "backlight.h"
#include "battery.h"
#include "epp.h"
#include "sensors.h"
#include "sleep_stats.h"
#include "store.h"
#include "sysfs.h"

namespace openbook {
namespace {

class Tree {
  public:
    Tree() { root_ = dir_.path; }
    void File(const std::string& path, const std::string& content) {
        Mkdirs(path.substr(0, path.rfind('/')));
        ASSERT_TRUE(android::base::WriteStringToFile(content + "\n", root_ + path)) << path;
    }
    void Link(const std::string& target, const std::string& path) {
        Mkdirs(path.substr(0, path.rfind('/')));
        ASSERT_EQ(0, symlink(target.c_str(), (root_ + path).c_str())) << path;
    }
    std::string Content(const std::string& path) {
        std::string s;
        android::base::ReadFileToString(root_ + path, &s);
        return s;
    }
    Sysfs sysfs() const { return Sysfs(root_); }
    const std::string& root() const { return root_; }

  private:
    void Mkdirs(const std::string& path) {
        for (size_t i = 1; i <= path.size(); i++) {
            if (i == path.size() || path[i] == '/') mkdir((root_ + path.substr(0, i)).c_str(), 0755);
        }
    }
    TemporaryDir dir_;
    std::string root_;
};

// ---------------------------------------------------------------- lights
TEST(Backlight, G14PicksAmdgpu) {
    Tree t;
    const std::string bl = "/sys/devices/pci0000:00/0000:00:08.1/0000:65:00.0/drm/card1/card1-eDP-1/amdgpu_bl1";
    t.File(bl + "/type", "raw");
    t.File(bl + "/max_brightness", "400000");
    t.File(bl + "/brightness", "400000");
    t.Link("../../devices/pci0000:00/0000:00:08.1/0000:65:00.0/drm/card1/card1-eDP-1/amdgpu_bl1",
           "/sys/class/backlight/amdgpu_bl1");
    auto b = PickBacklight(t.sysfs());
    ASSERT_TRUE(b);
    EXPECT_EQ("amdgpu_bl1", b->name);
    EXPECT_EQ(400000, b->max);
}

TEST(Backlight, FirmwareBeatsRaw) {
    // A dGPU-only MUX mode: the EC's backlight registers next to (or instead of) the GPU's.
    Tree t;
    t.File("/sys/class/backlight/amdgpu_bl1/type", "raw");
    t.File("/sys/class/backlight/amdgpu_bl1/max_brightness", "400000");
    t.File("/sys/class/backlight/nvidia_wmi_ec_backlight/type", "firmware");
    t.File("/sys/class/backlight/nvidia_wmi_ec_backlight/max_brightness", "255");
    auto b = PickBacklight(t.sysfs());
    ASSERT_TRUE(b);
    EXPECT_EQ("nvidia_wmi_ec_backlight", b->name);
}

TEST(Backlight, NoneOrBroken) {
    Tree t;
    EXPECT_FALSE(PickBacklight(t.sysfs()));
    t.File("/sys/class/backlight/acpi_video0/type", "firmware");
    t.File("/sys/class/backlight/acpi_video0/max_brightness", "0");
    EXPECT_FALSE(PickBacklight(t.sysfs()));
}

TEST(Backlight, Scale) {
    EXPECT_EQ(0, ScaleBrightness(0, 400000));
    EXPECT_EQ(400000, ScaleBrightness(255, 400000));
    EXPECT_EQ(200784, ScaleBrightness(128, 400000));
    EXPECT_EQ(1, ScaleBrightness(1, 100));  // never off for a non-zero request
    EXPECT_EQ(255, ScaleBrightness(999, 255));
}

// ---------------------------------------------------------------- power
void Policies(Tree* t, int n, const std::string& driver, const std::string& pref) {
    for (int i = 0; i < n; i++) {
        const std::string p = "/sys/devices/system/cpu/cpufreq/policy" + std::to_string(i);
        t->File(p + "/scaling_driver", driver);
        t->File(p + "/energy_performance_preference", pref);
    }
}

TEST(Epp, ChooseByModes) {
    PowerModes m;
    EXPECT_EQ("balance_performance", ChooseEpp(m, "balance_performance"));
    m.low_power = true;
    EXPECT_EQ("balance_power", ChooseEpp(m, "balance_performance"));
    m.launch = true;
    EXPECT_EQ("performance", ChooseEpp(m, "balance_performance"));
    m.interactive = false;
    EXPECT_EQ("power", ChooseEpp(m, "balance_performance"));
    m.fixed_performance = true;
    EXPECT_EQ("performance", ChooseEpp(m, "balance_performance"));
}

TEST(Epp, WritesEveryPolicy) {
    Tree t;
    Policies(&t, 24, "amd-pstate-epp", "balance_performance");  // HX 370: 24 threads
    Epp epp(t.sysfs());
    ASSERT_TRUE(epp.available());
    EXPECT_EQ(24u, epp.policies().size());
    EXPECT_EQ("balance_performance", epp.base());
    EXPECT_TRUE(epp.Set("power"));
    for (int i = 0; i < 24; i++) {
        EXPECT_EQ("power", t.Content("/sys/devices/system/cpu/cpufreq/policy" + std::to_string(i) +
                                     "/energy_performance_preference"));
    }
}

TEST(Epp, IgnoresOtherDrivers) {
    Tree t;
    Policies(&t, 4, "acpi-cpufreq", "");
    EXPECT_FALSE(Epp(t.sysfs()).available());
    Tree u;
    Policies(&u, 2, "amd-pstate-epp", "default");
    EXPECT_EQ("balance_performance", Epp(u.sysfs()).base());  // "default" is not a value we can write back
}

// ---------------------------------------------------------------- thermal
void G14Thermal(Tree* t) {
    t->File("/sys/class/thermal/thermal_zone0/type", "acpitz");
    t->File("/sys/class/thermal/thermal_zone0/temp", "69000");
    t->File("/sys/class/thermal/thermal_zone0/trip_point_0_type", "critical");
    t->File("/sys/class/thermal/thermal_zone0/trip_point_0_temp", "105000");
    t->File("/sys/class/thermal/thermal_zone0/trip_point_1_type", "passive");
    t->File("/sys/class/thermal/thermal_zone0/trip_point_1_temp", "95000");
    t->File("/sys/class/thermal/thermal_zone1/type", "acpitz");
    t->File("/sys/class/thermal/thermal_zone1/temp", "20000");
    t->File("/sys/class/thermal/cooling_device0/type", "Processor");
    t->File("/sys/class/thermal/cooling_device0/cur_state", "0");
    t->File("/sys/class/hwmon/hwmon0/name", "acpitz");
    t->File("/sys/class/hwmon/hwmon0/temp1_input", "69000");
    t->File("/sys/class/hwmon/hwmon3/name", "amdgpu");
    t->File("/sys/class/hwmon/hwmon3/temp1_input", "45000");
    t->File("/sys/class/hwmon/hwmon3/temp1_label", "edge");
    t->File("/sys/class/hwmon/hwmon3/temp1_crit", "100000");
    t->File("/sys/class/hwmon/hwmon3/temp1_emergency", "105000");
    t->File("/sys/class/hwmon/hwmon4/name", "nvme");
    t->File("/sys/class/hwmon/hwmon4/temp1_input", "38850");
    t->File("/sys/class/hwmon/hwmon4/temp1_label", "Composite");
    t->File("/sys/class/power_supply/BAT1/type", "Battery");
    t->File("/sys/class/power_supply/ACAD/type", "Mains");
}

TEST(Thermal, G14Sensors) {
    Tree t;
    G14Thermal(&t);
    ThermalSensors s(t.sysfs());
    s.Discover();
    ASSERT_EQ(4u, s.sensors().size());  // 2 zones, amdgpu, nvme; acpitz hwmon and the temp-less battery skipped
    EXPECT_EQ("acpitz-0", s.sensors()[0].name);
    EXPECT_EQ(temp_type::kUnknown, s.sensors()[0].type);
    EXPECT_FLOAT_EQ(95.0f, s.sensors()[0].hot[kSevere]);
    EXPECT_FLOAT_EQ(105.0f, s.sensors()[0].hot[kShutdown]);
    EXPECT_FLOAT_EQ(69.0f, *s.Read(s.sensors()[0]));
    EXPECT_EQ("acpitz-1", s.sensors()[1].name);
    EXPECT_EQ("amdgpu-edge", s.sensors()[2].name);
    EXPECT_EQ(temp_type::kGpu, s.sensors()[2].type);
    EXPECT_FLOAT_EQ(100.0f, s.sensors()[2].hot[kCritical]);
    EXPECT_EQ("nvme-Composite", s.sensors()[3].name);
    EXPECT_FLOAT_EQ(38.85f, *s.Read(s.sensors()[3]));
    ASSERT_EQ(1u, s.coolers().size());
    EXPECT_EQ("Processor-0", s.coolers()[0].name);
    EXPECT_EQ(cooling_type::kCpu, s.coolers()[0].type);
}

TEST(Thermal, BatteryTenths) {
    Tree t;
    t.File("/sys/class/power_supply/BAT1/type", "Battery");
    t.File("/sys/class/power_supply/BAT1/temp", "315");
    ThermalSensors s(t.sysfs());
    s.Discover();
    ASSERT_EQ(1u, s.sensors().size());
    EXPECT_EQ(temp_type::kBattery, s.sensors()[0].type);
    EXPECT_FLOAT_EQ(31.5f, *s.Read(s.sensors()[0]));
}

TEST(Thermal, Severity) {
    std::array<float, kSeverities> hot;
    hot.fill(NAN);
    EXPECT_EQ(0, ThermalSensors::Severity(200.0f, hot));
    hot[kSevere] = 95;
    hot[kShutdown] = 105;
    EXPECT_EQ(0, ThermalSensors::Severity(69.0f, hot));
    EXPECT_EQ(kSevere, ThermalSensors::Severity(95.0f, hot));
    EXPECT_EQ(kSevere, ThermalSensors::Severity(104.9f, hot));
    EXPECT_EQ(kShutdown, ThermalSensors::Severity(106.0f, hot));
}

TEST(Thermal, EmptyVm) {
    Tree t;  // QEMU q35: no thermal zones, no hwmon
    ThermalSensors s(t.sysfs());
    s.Discover();
    EXPECT_TRUE(s.sensors().empty());
    EXPECT_TRUE(s.coolers().empty());
}

// ---------------------------------------------------------------- power stats
TEST(SleepStats, Reads) {
    Tree t;
    EXPECT_FALSE(ReadSleepResidency(t.sysfs()));
    t.File("/sys/power/suspend_stats/success", "4");
    t.File("/sys/power/suspend_stats/total_hw_sleep", "7250000");
    t.File("/sys/power/suspend_stats/last_hw_sleep", "1500000");
    auto r = ReadSleepResidency(t.sysfs());
    ASSERT_TRUE(r);
    EXPECT_EQ(4, r->suspends);
    EXPECT_EQ(7250, r->hw_sleep_ms);
    EXPECT_EQ(1500, r->last_hw_sleep_ms);
}

// ---------------------------------------------------------------- health
// The GA403WR's BAT1 (ANAL-189 run 2): charge in uAh, no health, charge_counter or state_of_health files.
TEST(Battery, G14ChargeBased) {
    Tree t;
    const std::string bat = "/sys/devices/LNXSYSTM:00/LNXSYBUS:00/PNP0C0A:00/power_supply/BAT1";
    t.File(bat + "/type", "Battery");
    t.File(bat + "/present", "1");
    t.File(bat + "/charge_now", "2560000");
    t.File(bat + "/charge_full", "4063000");
    t.File(bat + "/charge_full_design", "4580000");
    t.File("/sys/devices/LNXSYSTM:00/LNXSYBUS:00/ACPI0003:00/power_supply/ACAD/type", "Mains");
    t.Link("../../devices/LNXSYSTM:00/LNXSYBUS:00/PNP0C0A:00/power_supply/BAT1", "/sys/class/power_supply/BAT1");
    t.Link("../../devices/LNXSYSTM:00/LNXSYBUS:00/ACPI0003:00/power_supply/ACAD", "/sys/class/power_supply/ACAD");
    auto b = ReadBattery(t.sysfs());
    ASSERT_TRUE(b);
    EXPECT_EQ("BAT1", b->name);
    EXPECT_EQ(2560000, *b->charge_now_uah);
    EXPECT_EQ(4063000, *b->full_uah);
    EXPECT_EQ(4580000, *b->design_uah);
    EXPECT_EQ(88, *b->state_of_health_percent);
    EXPECT_EQ(BatteryCondition::kGood, ConditionFromStateOfHealth(*b->state_of_health_percent));
}

TEST(Battery, EnergyBasedAndWorn) {
    Tree t;
    t.File("/sys/class/power_supply/BAT0/type", "Battery");
    t.File("/sys/class/power_supply/BAT0/energy_now", "30000000");          // 30 Wh
    t.File("/sys/class/power_supply/BAT0/energy_full", "42000000");         // 42 Wh
    t.File("/sys/class/power_supply/BAT0/energy_full_design", "60000000");  // 60 Wh
    t.File("/sys/class/power_supply/BAT0/voltage_min_design", "15000000");  // 15 V
    auto b = ReadBattery(t.sysfs());
    ASSERT_TRUE(b);
    EXPECT_EQ(2000000, *b->charge_now_uah);
    EXPECT_EQ(2800000, *b->full_uah);
    EXPECT_EQ(4000000, *b->design_uah);
    EXPECT_EQ(70, *b->state_of_health_percent);
    EXPECT_EQ(BatteryCondition::kFair, ConditionFromStateOfHealth(*b->state_of_health_percent));
}

TEST(Battery, SkipsDevicesAndAbsent) {
    Tree t;
    t.File("/sys/class/power_supply/hidpp_battery_0/type", "Battery");   // a mouse
    t.File("/sys/class/power_supply/hidpp_battery_0/scope", "Device");
    t.File("/sys/class/power_supply/BAT1/type", "Battery");              // bay empty
    t.File("/sys/class/power_supply/BAT1/present", "0");
    t.File("/sys/class/power_supply/ucsi-source-psy-USBC000:001/type", "USB");
    EXPECT_FALSE(ReadBattery(t.sysfs()));
    Tree none;
    EXPECT_FALSE(ReadBattery(none.sysfs()));
}

// ---------------------------------------------------------------- weaver
TEST(Weaver, RetrySchedule) {
    EXPECT_EQ(0, WeaverStore::RetryTimeoutMs(0));
    EXPECT_EQ(0, WeaverStore::RetryTimeoutMs(4));
    EXPECT_EQ(30000, WeaverStore::RetryTimeoutMs(5));
    EXPECT_EQ(0, WeaverStore::RetryTimeoutMs(6));
    EXPECT_EQ(30000, WeaverStore::RetryTimeoutMs(10));
    EXPECT_EQ(30000, WeaverStore::RetryTimeoutMs(29));
    EXPECT_EQ(60000, WeaverStore::RetryTimeoutMs(40));
    EXPECT_EQ(24 * 3600 * 1000, WeaverStore::RetryTimeoutMs(140));
}

TEST(Weaver, PersistsAndThrottles) {
    TemporaryDir dir;
    int64_t now = 1000;
    auto clock = [&now] { return now; };
    const std::vector<uint8_t> key(16, 0x11), bad(16, 0x22), value(16, 0x33);
    {
        WeaverStore w(dir.path, clock);
        EXPECT_EQ(WeaverStore::Status::kIncorrectKey, w.Read(3, key).status);  // never written
        ASSERT_TRUE(w.Write(3, key, value));
        auto r = w.Read(3, key);
        EXPECT_EQ(WeaverStore::Status::kOk, r.status);
        EXPECT_EQ(value, r.value);
        EXPECT_FALSE(w.Write(16, key, value));
        EXPECT_FALSE(w.Write(0, std::vector<uint8_t>(17), value));
    }
    {
        // A new process, as after a reboot: the slot is still there.
        WeaverStore w(dir.path, clock);
        EXPECT_EQ(value, w.Read(3, key).value);
        for (int i = 1; i <= 4; i++) EXPECT_EQ(WeaverStore::Status::kIncorrectKey, w.Read(3, bad).status);
        auto r = w.Read(3, bad);  // fifth failure
        EXPECT_EQ(WeaverStore::Status::kIncorrectKey, r.status);
        EXPECT_EQ(30000, r.timeout_ms);
        EXPECT_EQ(WeaverStore::Status::kThrottle, w.Read(3, key).status);  // even the right key waits
        EXPECT_EQ(30000, w.Timeout(3));
        now += 30000;
        EXPECT_EQ(0, w.Timeout(3));
        EXPECT_EQ(WeaverStore::Status::kOk, w.Read(3, key).status);  // resets the counter
        EXPECT_EQ(-1, w.Timeout(99));
    }
    {
        WeaverStore w(dir.path, clock);
        EXPECT_EQ(0, w.Timeout(3));  // the success above was saved
    }
}

TEST(Weaver, ThrottleSurvivesRestart) {
    TemporaryDir dir;
    int64_t now = 50;
    auto clock = [&now] { return now; };
    const std::vector<uint8_t> key(16, 1), bad(16, 2), value(16, 3);
    {
        WeaverStore w(dir.path, clock);
        ASSERT_TRUE(w.Write(0, key, value));
        for (int i = 0; i < 5; i++) w.Read(0, bad);
    }
    now = 10;  // a reboot resets the clock
    WeaverStore w(dir.path, clock);
    EXPECT_EQ(30000, w.Timeout(0));
}

}  // namespace
}  // namespace openbook
