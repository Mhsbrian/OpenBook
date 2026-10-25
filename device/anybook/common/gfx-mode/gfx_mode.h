// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Graphics modes for the Googlebook (Ruby) image on ASUS laptops with a MUX (ANAL-241, docs/nvidia-graphics-modes.md):
//   eco       gpu_mux_mode=1 dgpu_disable=1   panel on the iGPU, dGPU off and not enumerated
//   hybrid    gpu_mux_mode=1 dgpu_disable=0   panel on the iGPU, dGPU enumerated (D3cold when idle)
//   ultimate  gpu_mux_mode=0 dgpu_disable=0   panel and HDMI on the dGPU (nouveau KMS)
// Prototype: the firmware writes, the rollback state machine and the stack selector. It builds without Android
// libraries so the same code runs in the host fixture tests and in the QEMU guest (scripts/googlebook/gfx-mode-*).

#pragma once

#include <optional>
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
    std::string locked;                // "", eco, hybrid or ultimate
    std::string deferred;              // "" or dgpu-off: disable the dGPU at the next early init
    std::string last_failure;
    std::string event;
    std::string fw_before;
    std::string fw_after;
};
std::string Serialize(const State& s);
std::optional<State> Parse(const std::string& text);

// One DRM card or render node, and the PCI function behind it.
struct Connector {
    std::string name;    // eDP-1, HDMI-A-1
    std::string status;  // connected, disconnected, unknown
};
struct Card {
    std::string node;    // card0, renderD128
    std::string driver;  // amdgpu, nouveau, virtio_gpu
    std::string pci;     // 0000:65:00.0
    std::vector<Connector> connectors;
};
struct PciFn {
    std::string slot;
    unsigned vendor = 0;
    unsigned pci_class = 0;
    std::string driver;
};

struct Selection {
    std::string hal = "none";  // amdgpu, nouveau, virtio, none
    std::string display_card;  // card0
    std::string render_node;   // renderD128
    std::string dgpu = "absent";  // absent, off, display
    std::string note;
};
bool IsPanel(const std::string& connector);  // eDP, LVDS, DSI
// Stack selection: follow the panel, not the intent. In Ultimate the display GPU must be nouveau's card with a
// connected panel; otherwise the card whose panel is connected wins (logged in note).
Selection Select(Mode mode, const std::vector<Card>& cards, const std::vector<Card>& render_nodes,
                 const std::vector<PciFn>& pci);

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
    int SelectStack();                  // early init, after the KMS driver for the mode is loaded
    int Frame(const std::string& card_connector);  // HWC presented a frame on this connector
    int Booted();                       // sys.boot_completed=1
    int Keep();                         // the owner kept the new mode
    int Revert();                       // the owner asked to go back
    int Deadline();                     // the health watchdog expired
    int Request(const std::string& mode);
    int Lock(const std::string& mode);  // "" locks the current mode
    int Unlock();
    int Restore();                      // force gpu_mux_mode=1 (recovery entry, adb)
    int Status();

  private:
    Firmware ReadFirmware();
    bool WriteFw(const std::string& attr, int value, std::string* error);
    bool EnableDgpu(std::string* error);
    std::vector<Card> Cards(bool render);
    std::vector<PciFn> Pci();
    std::string Board();
    bool BoardAllowed();
    bool StackVerified(const std::string& stack, std::string* why);
    bool DgpuDriverBusy();
    State Load();
    bool Save(State& s, const std::string& event);
    void Publish(const State& s, const Firmware& fw);
    void SetProp(const std::string& name, const std::string& value);
    void RequestReboot(const std::string& reason);
    void Rollback(State& s, const Firmware& fw, const std::string& reason);
    void Log(const std::string& line);
    void Crash(const char* point);

    Paths paths_;
    bool dry_run_;
    bool loaded_ = false;
};

}  // namespace openbook::gfx
