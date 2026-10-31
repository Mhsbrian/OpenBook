// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Graphics modes for the Googlebook (Ruby) image on ASUS laptops with a MUX (ANAL-241/246,
// docs/nvidia-graphics-modes.md):
//   eco       gpu_mux_mode=1 dgpu_disable=1   panel on the iGPU, dGPU off and not enumerated
//   hybrid    gpu_mux_mode=1 dgpu_disable=0   panel on the iGPU, dGPU enumerated (D3cold when idle)
//   ultimate  gpu_mux_mode=0 dgpu_disable=0   panel and HDMI on the dGPU (nouveau KMS)
// The firmware writes, the rollback state machine, the requests from the OpenBook Graphics app and adb, and the
// Ultimate watchdog. It builds without Android libraries (logcat and properties under __ANDROID__), so the same
// code runs in the host fixture tests, the QEMU guest and the vendor image.

#pragma once

#include <optional>
#include <string>
#include <vector>

#include "gfx_select.h"

namespace openbook::gfx {

// Persistent state in /metadata (first-stage mounted, so readable at early-init).
struct State {
    std::string committed = "hybrid";  // the last mode known to work
    std::string target = "hybrid";     // the mode being switched to
    std::string phase = "idle";        // idle pending trial booted rollback failed
    int tries = 0;                     // Ultimate boots since the last healthy one
    int max_tries = 2;                 // after this many, early init restores Hybrid
    int rollbacks = 0;                 // restore writes made in phase rollback
    int seq = 0;                       // requests made
    int boots = 0;                     // boots seen
    bool frame = false;                // this boot: the panel showed a composed frame on the expected GPU
    bool shown = false;                // this boot: the app showed "Keep Ultimate graphics?"
    std::string locked;                // "", eco, hybrid or ultimate
    std::string deferred;              // "" or dgpu-off: disable the dGPU at the next early init
    std::string last_failure;
    std::string event;
    std::string fw_before;
    std::string fw_after;
    std::string result;                // the last request's answer: SEQ:CODE (the app's channel), or CODE
};
std::string Serialize(const State& s);
std::optional<State> Parse(const std::string& text);

// Who asked: the switching rules differ by channel (docs/nvidia-graphics-modes.md §4).
enum class Channel {
    kCli,  // openbook-gfx-mode run by hand or by the tests (root only on a device)
    kApp,  // the OpenBook Graphics app: openbook.gfx.request, set by the app's domain only
    kAdb,  // debug.openbook.gfx from the adb shell: the safe direction; the rest needs the lab switch
};

struct Paths {
    std::string sysfs = "/sys";                               // DRM, PCI, DMI, the PCI rescan file
    std::string fw = "/sys/devices/platform/asus-nb-wmi";      // gpu_mux_mode, dgpu_disable
    std::string state_dir = "/metadata/openbook/gfx";
    std::string stacks = "/vendor/etc/openbook/gfx-stacks.conf";
    std::string cmdline = "/proc/cmdline";
    std::string props;  // empty: Android properties; otherwise one file per property in this directory (tests)
};

class Controller {
  public:
    Controller(Paths paths, bool dry_run);
    // Each returns the process exit status: 0 done, 1 refused or failed, 2 bad input.
    int Boot();                         // early init, after asus-wmi loads and before any GPU stack starts
    int SelectStack();                  // the stack selector's decision (anybook_gpu_probe makes it at boot)
    int Frame(const std::string& card_connector);  // the composer presented a frame on this connector
    int Booted();                       // sys.boot_completed=1
    int Keep(Channel ch = Channel::kCli);      // the owner kept the new mode
    int Shown();                        // the app showed the keep dialog: the owner's 30 s start
    int Revert(Channel ch = Channel::kCli);    // the owner asked to go back
    int Deadline();                     // the health watchdog expired
    int Watchdog();                     // Ultimate boots: the frame, boot and keep deadlines
    int Request(const std::string& mode, Channel ch = Channel::kCli);
    int Lock(const std::string& mode, Channel ch = Channel::kCli);  // "" locks the current mode
    int Unlock(Channel ch = Channel::kCli);
    int Restore();                      // force gpu_mux_mode=1 (recovery entry, adb)
    int Status();
    int App(const std::string& value);  // openbook.gfx.request: VERB[:MODE]@SEQ
    int Adb(const std::string& value);  // debug.openbook.gfx: hybrid | restore | status | ... [@N]

  private:
    bool WriteFw(const std::string& attr, int value, std::string* error);
    bool EnableDgpu(std::string* error);
    std::string Board();
    bool BoardAllowed();
    std::string StackState(const std::string& stack, std::string* why);  // unverified development verified
    bool StackUsable(const std::string& stack, std::string* why);  // verified or development: may boot Ultimate
    bool UltimateOffered();
    std::string UltimateAvailability(const Firmware& fw);
    bool DgpuDriverBusy();
    bool LabOn();
    int ConfigSeconds(const char* name, int fallback);
    State Load();
    bool Save(State& s, const std::string& event);
    void Publish(const State& s, const Firmware& fw);
    void SetProp(const std::string& name, const std::string& value);
    std::string GetProp(const std::string& name);
    void SetResult(State& s, const std::string& code, const std::string& text);
    void RequestReboot(const std::string& reason);
    void Rollback(State& s, const Firmware& fw, const std::string& reason);
    void Log(const std::string& line);
    void Crash(const char* point);

    Paths paths_;
    bool dry_run_;
    bool loaded_ = false;
    std::string tag_;  // the request's sequence number on the app and adb channels
};

}  // namespace openbook::gfx
