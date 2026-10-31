// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "gfx_mode.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include <algorithm>
#include <map>
#include <set>
#include <sstream>

#include "gfx_util.h"

#ifdef __ANDROID__
#include <android/log.h>
#include <sys/system_properties.h>
#endif

namespace openbook::gfx {
namespace {

using namespace util;

constexpr char kSchema[] = "openbook-gfx-state/1";
constexpr char kStacksSchema[] = "# openbook-gfx-stacks/1";
constexpr int kMaxRollbacks = 3;
constexpr unsigned kVendorNvidia = 0x10de;
constexpr size_t kPropValueMax = 91;  // PROP_VALUE_MAX - 1
// The Ultimate watchdog's deadlines (docs/nvidia-graphics-modes.md §5), overridable for VMs by
// ro.vendor.openbook.gfx.{frame,boot,keep}_deadline_s.
constexpr int kFrameDeadlineS = 120;   // a composed frame on the panel, from early init
constexpr int kBootDeadlineS = 1200;   // boot completion; the first boot after an update compiles apps
constexpr int kKeepDeadlineS = 30;     // the owner's answer, from when the app showed the dialog

bool MkdirP(const std::string& dir) {
    std::string cur;
    std::stringstream in(dir);
    for (std::string part; std::getline(in, part, '/');) {
        if (part.empty()) {
            if (cur.empty()) cur = "/";
            continue;
        }
        cur += (cur.empty() || cur.back() == '/' ? "" : "/") + part;
        if (mkdir(cur.c_str(), 0700) != 0 && errno != EEXIST) return false;
    }
    return true;
}

bool WriteAll(int fd, const std::string& data) {
    size_t off = 0;
    while (off < data.size()) {
        ssize_t n = write(fd, data.data() + off, data.size() - off);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return false;
        off += n;
    }
    return true;
}

// Crash-ordered replace: the new bytes reach the disk before the name points at them, and the rename before
// the caller goes on (a firmware write must never be ahead of the state that explains it).
bool AtomicWrite(const std::string& dir, const std::string& name, const std::string& data, bool durable) {
    const std::string tmp = dir + "/." + name + ".tmp", path = dir + "/" + name;
    int fd = open(tmp.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    if (fd < 0) return false;
    bool ok = WriteAll(fd, data) && (!durable || fsync(fd) == 0);
    ok = (close(fd) == 0) && ok;
    if (!ok || rename(tmp.c_str(), path.c_str()) != 0) {
        unlink(tmp.c_str());
        return false;
    }
    if (durable) {
        int dfd = open(dir.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (dfd < 0) return false;
        ok = fsync(dfd) == 0;
        close(dfd);
    }
    return ok;
}

void AppendLine(const std::string& path, const std::string& line) {
    int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
    if (fd < 0) return;
    struct stat st;
    // Keep the history short: start a new file past 64 KiB, keeping one old one.
    if (fstat(fd, &st) == 0 && st.st_size > 64 * 1024) {
        close(fd);
        rename(path.c_str(), (path + ".1").c_str());
        fd = open(path.c_str(), O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
        if (fd < 0) return;
    }
    WriteAll(fd, line + "\n");
    fsync(fd);
    close(fd);
}

bool ValidMode(const std::string& m) { return m == "eco" || m == "hybrid" || m == "ultimate"; }

const std::set<std::string>& Phases() {
    static const std::set<std::string> p = {"idle", "pending", "trial", "booted", "rollback", "failed"};
    return p;
}

double Uptime() {
    timespec ts{};
    clock_gettime(CLOCK_BOOTTIME, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

// flock() on the state directory: one command at a time (init's boot steps, the switch service, the watchdog).
class FileLock {
  public:
    explicit FileLock(const std::string& dir) {
        if (MkdirP(dir)) fd_ = open((dir + "/lock").c_str(), O_RDWR | O_CREAT | O_CLOEXEC, 0600);
        if (fd_ >= 0) flock(fd_, LOCK_EX);
    }
    ~FileLock() {
        if (fd_ >= 0) close(fd_);
    }

  private:
    int fd_ = -1;
};

// /vendor/etc/openbook/gfx-stacks.conf: the boards OpenBook may switch, each stack's state and its files, and
// whether the app may offer Ultimate. The release builder writes "stack nouveau verified" only with ANAL-244's
// evidence for exactly these files, and "offer ultimate" only once both slots and the stick carry this switcher
// (the update interlock, §5.4). "development" lets a dev image boot Ultimate through the lab's adb channel.
struct Stacks {
    std::set<std::string> boards;
    std::map<std::string, std::string> state;  // stack -> unverified | development | verified
    std::map<std::string, std::vector<std::string>> files;
    std::set<std::string> offered;              // modes the app may offer beyond Eco and Hybrid
};

std::optional<Stacks> LoadStacks(const std::string& path, std::string* why) {
    std::string text;
    if (!ReadFile(path, &text)) {
        *why = "no stack manifest " + path;
        return std::nullopt;
    }
    std::stringstream in(text);
    std::string line;
    if (!std::getline(in, line) || Trim(line) != kStacksSchema) {
        *why = "stack manifest is not " + std::string(kStacksSchema + 2);
        return std::nullopt;
    }
    Stacks s;
    while (std::getline(in, line)) {
        std::stringstream words(line);
        std::string kind, a, b;
        if (!(words >> kind) || kind[0] == '#') continue;
        words >> a >> b;
        if (kind == "board" && !a.empty()) {
            s.boards.insert(a);
        } else if (kind == "stack" && (b == "verified" || b == "unverified" || b == "development")) {
            s.state[a] = b;
        } else if (kind == "file" && !b.empty() && b[0] == '/') {
            s.files[a].push_back(b);
        } else if (kind == "offer" && a == "ultimate" && b.empty()) {
            s.offered.insert(a);
        } else {
            *why = "stack manifest: unreadable line '" + line + "'";
            return std::nullopt;
        }
    }
    return s;
}

// The app's and adb's request values: VERB[:ARG][@SEQ], lower-case letters and digits only.
struct Parsed {
    std::string verb, arg, seq;
};
std::optional<Parsed> ParseRequest(const std::string& value, bool need_seq) {
    if (value.empty() || value.size() > kPropValueMax) return std::nullopt;
    Parsed p;
    std::string rest = value;
    size_t at = rest.find('@');
    if (at != std::string::npos) {
        p.seq = rest.substr(at + 1);
        rest = rest.substr(0, at);
        if (p.seq.empty() || p.seq.size() > 9 || !std::all_of(p.seq.begin(), p.seq.end(), ::isdigit)) {
            return std::nullopt;
        }
    } else if (need_seq) {
        return std::nullopt;
    }
    size_t colon = rest.find(':');
    p.verb = rest.substr(0, colon);
    if (colon != std::string::npos) {
        p.arg = rest.substr(colon + 1);
        if (p.arg.empty()) return std::nullopt;
    }
    auto word = [](const std::string& w) {
        return !w.empty() && std::all_of(w.begin(), w.end(), [](char c) { return islower(c) || c == '-'; });
    };
    if (!word(p.verb) || (!p.arg.empty() && !word(p.arg))) return std::nullopt;
    return p;
}

}  // namespace

std::string Serialize(const State& s) {
    std::ostringstream o;
    o << "schema=" << kSchema << "\n"
      << "committed=" << s.committed << "\ntarget=" << s.target << "\nphase=" << s.phase << "\n"
      << "tries=" << s.tries << "\nmax_tries=" << s.max_tries << "\nrollbacks=" << s.rollbacks << "\n"
      << "seq=" << s.seq << "\nboots=" << s.boots << "\nframe=" << (s.frame ? 1 : 0) << "\n"
      << "shown=" << (s.shown ? 1 : 0) << "\n"
      << "locked=" << s.locked << "\ndeferred=" << s.deferred << "\nlast_failure=" << s.last_failure << "\n"
      << "event=" << s.event << "\nfw_before=" << s.fw_before << "\nfw_after=" << s.fw_after << "\n"
      << "result=" << s.result << "\n";
    return o.str();
}

std::optional<State> Parse(const std::string& text) {
    State s;
    std::stringstream in(text);
    std::string line;
    if (!std::getline(in, line) || line != std::string("schema=") + kSchema) return std::nullopt;
    std::set<std::string> seen;
    while (std::getline(in, line)) {
        size_t eq = line.find('=');
        if (eq == std::string::npos) return std::nullopt;
        const std::string k = line.substr(0, eq), v = line.substr(eq + 1);
        if (!seen.insert(k).second) return std::nullopt;
        int n = 0;
        if (k == "committed" || k == "target") {
            if (!ValidMode(v)) return std::nullopt;
            (k == "committed" ? s.committed : s.target) = v;
        } else if (k == "phase") {
            if (!Phases().count(v)) return std::nullopt;
            s.phase = v;
        } else if (k == "tries" || k == "max_tries" || k == "rollbacks" || k == "seq" || k == "boots" ||
                   k == "frame" || k == "shown") {
            if (!ParseInt(v, &n) || n < 0) return std::nullopt;
            if (k == "tries") s.tries = n;
            if (k == "max_tries") s.max_tries = std::clamp(n, 1, 5);
            if (k == "rollbacks") s.rollbacks = n;
            if (k == "seq") s.seq = n;
            if (k == "boots") s.boots = n;
            if (k == "frame") s.frame = n != 0;
            if (k == "shown") s.shown = n != 0;
        } else if (k == "locked") {
            if (!v.empty() && !ValidMode(v)) return std::nullopt;
            s.locked = v;
        } else if (k == "deferred") {
            if (!v.empty() && v != "dgpu-off") return std::nullopt;
            s.deferred = v;
        } else if (k == "last_failure") {
            s.last_failure = v;
        } else if (k == "event") {
            s.event = v;
        } else if (k == "fw_before") {
            s.fw_before = v;
        } else if (k == "fw_after") {
            s.fw_after = v;
        } else if (k == "result") {
            s.result = v;
        }  // unknown keys from a newer version are ignored
    }
    return s;
}

Controller::Controller(Paths paths, bool dry_run) : paths_(std::move(paths)), dry_run_(dry_run) {}

void Controller::Log(const std::string& line) {
#ifdef __ANDROID__
    // The kernel log has it from early init on; logcat once logd runs.
    KernelLog("openbook-gfx-mode", line);
    __android_log_write(ANDROID_LOG_INFO, "openbook-gfx-mode", line.c_str());
#else
    printf("openbook-gfx-mode: %s\n", line.c_str());
    fflush(stdout);
#endif
}

void Controller::Crash(const char* point) {
#ifdef OPENBOOK_GFX_TEST_HOOKS
    const char* at = getenv("OPENBOOK_GFX_TEST_CRASH");
    if (at && strcmp(at, point) == 0) {
        Log(std::string("test: power lost at ") + point);
        _exit(99);
    }
#else
    (void)point;
#endif
}

bool Controller::WriteFw(const std::string& attr, int value, std::string* error) {
    const std::string path = attr == "rescan" ? paths_.sysfs + "/bus/pci/rescan" : paths_.fw + "/" + attr;
    if (dry_run_) {
        Log("dry-run: would write " + std::to_string(value) + " to " + path);
        *error = "dry-run";
        return false;
    }
    int fd = open(path.c_str(), O_WRONLY | O_CLOEXEC);
    bool ok = fd >= 0 && WriteAll(fd, std::to_string(value) + "\n");
    int err = errno;
    if (fd >= 0) ok = (close(fd) == 0) && ok;  // sysfs reports the store's error on write() itself
    *error = ok ? "" : strerror(err);
    Log("write " + attr + "=" + std::to_string(value) + (ok ? ": ok" : ": " + *error));
    return ok;
}

// The kernel's own note (asus-wmi.c, dgpu_disable_store): enabling may need a store, a PCI rescan, and a
// second store before the firmware saves it. Read back after each step.
bool Controller::EnableDgpu(std::string* error) {
    if (!WriteFw("dgpu_disable", 0, error)) return false;
    if (ReadFirmware(paths_.fw).dgpu == 0) return true;
    Log("dgpu_disable still reads 1: rescanning PCI and writing again");
    std::string ignored;
    WriteFw("rescan", 1, &ignored);
    if (!WriteFw("dgpu_disable", 0, error)) return false;
    if (ReadFirmware(paths_.fw).dgpu == 0) return true;
    *error = "dgpu_disable still reads 1 after two writes and a PCI rescan";
    return false;
}

std::string Controller::Board() {
    std::string b;
    ReadFile(paths_.sysfs + "/class/dmi/id/board_name", &b);
    return Trim(b);
}

bool Controller::BoardAllowed() {
    std::string why;
    auto stacks = LoadStacks(paths_.stacks, &why);
    return stacks && stacks->boards.count(Board());
}

std::string Controller::StackState(const std::string& stack, std::string* why) {
    auto stacks = LoadStacks(paths_.stacks, why);
    if (!stacks) return "unverified";
    auto it = stacks->state.find(stack);
    if (it == stacks->state.end() || it->second == "unverified") {
        *why = stack + " stack is not verified in this image";
        return "unverified";
    }
    if (stacks->files[stack].empty()) {
        *why = stack + " stack lists no files";
        return "unverified";
    }
    for (const auto& f : stacks->files[stack]) {
        struct stat st;
        if (stat(f.c_str(), &st) != 0 || !S_ISREG(st.st_mode) || st.st_size == 0) {
            *why = stack + " stack: missing " + f;
            return "unverified";
        }
    }
    return it->second;
}

bool Controller::StackUsable(const std::string& stack, std::string* why) {
    const std::string state = StackState(stack, why);
    return state == "verified" || state == "development";
}

bool Controller::UltimateOffered() {
    std::string why;
    auto stacks = LoadStacks(paths_.stacks, &why);
    return stacks && stacks->offered.count("ultimate") && StackState("nouveau", &why) == "verified";
}

// What the app may say about Ultimate: unsupported (no MUX, or a board OpenBook does not switch), unverified,
// development, verified (this image can drive it, but the interlock does not allow offering it yet), offered.
std::string Controller::UltimateAvailability(const Firmware& fw) {
    if (!fw.present || !BoardAllowed()) return "unsupported";
    std::string why;
    if (UltimateOffered()) return "offered";
    return StackState("nouveau", &why);
}

bool Controller::DgpuDriverBusy() {
    for (const auto& f : ReadPci(paths_.sysfs)) {
        if (f.vendor == kVendorNvidia && (f.pci_class >> 16) == 0x03 && !f.driver.empty()) return true;
    }
    return false;
}

std::string Controller::GetProp(const std::string& name) {
    if (!paths_.props.empty()) {
        std::string v;
        ReadFile(paths_.props + "/" + name, &v);
        return Trim(v);
    }
#ifdef __ANDROID__
    char value[PROP_VALUE_MAX] = "";
    __system_property_get(name.c_str(), value);
    return value;
#else
    return "";
#endif
}

// The lab switch (ANAL-257's persist.vendor.openbook.lab, set only by the lab helper) opens the adb channel's
// development requests.
bool Controller::LabOn() { return GetProp("persist.vendor.openbook.lab") == "1"; }

int Controller::ConfigSeconds(const char* name, int fallback) {
    int v = 0;
    const std::string s = GetProp(std::string("ro.vendor.openbook.gfx.") + name);
    return ParseInt(s, &v) && v > 0 && v <= 24 * 3600 ? v : fallback;
}

State Controller::Load() {
    std::string text;
    State s;
    loaded_ = false;
    if (!ReadFile(paths_.state_dir + "/state", &text)) return s;
    if (auto parsed = Parse(text)) {
        loaded_ = true;
        return *parsed;
    }
    // Keep the unreadable copy for the report; start from the firmware's word.
    AtomicWrite(paths_.state_dir, "state.corrupt", text, false);
    s.last_failure = "state-corrupt";
    return s;
}

bool Controller::Save(State& s, const std::string& event) {
    s.event = event;
    bool ok = MkdirP(paths_.state_dir) && AtomicWrite(paths_.state_dir, "state", Serialize(s), true);
    AppendLine(paths_.state_dir + "/history", "boot=" + std::to_string(s.boots) + " seq=" + std::to_string(s.seq) +
                                                  " phase=" + s.phase + " committed=" + s.committed + " " + event);
    Log(event + (ok ? "" : " (STATE NOT SAVED)"));
    return ok;
}

void Controller::SetProp(const std::string& name, const std::string& value) {
    const std::string v = value.size() > kPropValueMax ? value.substr(0, kPropValueMax) : value;
    if (!paths_.props.empty()) {
        MkdirP(paths_.props);
        AtomicWrite(paths_.props, name, v + "\n", false);
        return;
    }
#ifdef __ANDROID__
    __system_property_set(name.c_str(), v.c_str());
#else
    printf("%s=%s\n", name.c_str(), v.c_str());
#endif
}

// A request's answer: the text for people (vendor.openbook.gfx.request_result), and a code with the request's
// sequence number for the app (vendor.openbook.gfx.result and the summary). Codes: done restart already dry-run
// refused-{unsupported,busy,locked,invalid-firmware,unverified,not-offered,lab-off,nothing-to-keep,not-ultimate}
// failed-{firmware,state} bad-request.
void Controller::SetResult(State& s, const std::string& code, const std::string& text) {
    s.result = tag_.empty() ? code : tag_ + ":" + code;
    SetProp("vendor.openbook.gfx.request_result", text);
    SetProp("vendor.openbook.gfx.result", s.result);
}

// The app reads one summary, so it never sees half of an update: "1 MODE PHASE TARGET LOCK WRITES ULTIMATE
// RESULT" (docs/nvidia-graphics-modes.md §7). At most 91 characters.
void Controller::Publish(const State& s, const Firmware& fw) {
    SetProp("vendor.openbook.gfx.mode", ModeName(ModeOf(fw)));
    SetProp("vendor.openbook.gfx.fw", FwString(fw));
    SetProp("vendor.openbook.gfx.phase", s.phase);
    SetProp("vendor.openbook.gfx.committed", s.committed);
    SetProp("vendor.openbook.gfx.target", s.target);
    SetProp("vendor.openbook.gfx.tries", std::to_string(s.tries) + "/" + std::to_string(s.max_tries));
    SetProp("vendor.openbook.gfx.locked", s.locked.empty() ? "none" : s.locked);
    SetProp("vendor.openbook.gfx.last_failure", s.last_failure.empty() ? "none" : s.last_failure);
    SetProp("vendor.openbook.gfx.event", s.event);
    const std::string ultimate = UltimateAvailability(fw);
    SetProp("vendor.openbook.gfx.ultimate", ultimate);
    SetProp("vendor.openbook.gfx.summary", "1 " + std::string(ModeName(ModeOf(fw))) + " " + s.phase + " " +
                                                s.target + " " + (s.locked.empty() ? "none" : s.locked) + " " +
                                                (dry_run_ ? "off" : "on") + " " + ultimate + " " +
                                                (s.result.empty() ? "-" : s.result));
}

void Controller::RequestReboot(const std::string& reason) {
    if (dry_run_) {
        Log("dry-run: would reboot (" + reason + ")");
        return;
    }
    SetProp("sys.powerctl", "reboot," + reason);
}

// Back to the iGPU: the state first (durable), then gpu_mux_mode=1, then a reboot. A power cut at any point
// leaves phase=rollback, and the next early init writes again (up to kMaxRollbacks, then phase=failed).
void Controller::Rollback(State& s, const Firmware& fw, const std::string& reason) {
    s.phase = "rollback";
    s.target = s.locked == "eco" ? "eco" : "hybrid";
    if (s.locked == "eco") s.deferred = "dgpu-off";
    s.last_failure = reason;
    s.rollbacks = 1;
    s.tries = 0;
    s.fw_before = FwString(fw);
    Save(s, "rollback: " + reason);
    Crash("rollback-before-write");
    std::string err;
    if (WriteFw("gpu_mux_mode", 1, &err)) {
        s.fw_after = FwString(ReadFirmware(paths_.fw));
        Save(s, "rollback: gpu_mux_mode=1 written, restarting");
    } else {
        Save(s, "rollback: write failed (" + err + "), the next boot retries");
    }
    Publish(s, ReadFirmware(paths_.fw));
    RequestReboot("openbook-gfx-rollback");
}

int Controller::Boot() {
    FileLock lock(paths_.state_dir);
    Firmware fw = ReadFirmware(paths_.fw);
    State s = Load();
    const bool fresh = !loaded_;
    s.boots++;
    s.frame = false;
    s.shown = false;
    Mode mode = ModeOf(fw);
    std::vector<std::string> events;
    Log("boot " + std::to_string(s.boots) + ": firmware " + FwString(fw) + " (" + ModeName(mode) + "), phase " +
        s.phase + ", committed " + s.committed + (dry_run_ ? ", firmware writes off" : ""));
    if (fresh) {
        s.committed = s.target = (mode == Mode::kEco || mode == Mode::kHybrid) ? ModeName(mode) : "hybrid";
        events.push_back(s.last_failure == "state-corrupt" ? "state was unreadable, rebuilt" : "state created");
    }

    // The recovery entry (USB stick or the internal boot menu): openbook.gfx=restore-hybrid.
    std::string cmdline;
    ReadFile(paths_.cmdline, &cmdline);
    std::stringstream words(cmdline);
    bool restore = false;
    for (std::string w; words >> w;) {
        restore |= w == "openbook.gfx=restore-hybrid" || w == "androidboot.openbook.gfx=restore-hybrid";
    }
    if (restore && fw.present && fw.mux == 0) {
        std::string err;
        if (WriteFw("gpu_mux_mode", 1, &err)) {
            s.phase = "idle";
            s.committed = s.target = fw.dgpu == 1 ? "eco" : "hybrid";
            s.tries = s.rollbacks = 0;
            s.last_failure = "restored by the recovery entry";
            s.fw_after = FwString(ReadFirmware(paths_.fw));
            Save(s, "recovery entry: gpu_mux_mode=1 written, restarting");
            Publish(s, ReadFirmware(paths_.fw));
            RequestReboot("openbook-gfx-restore");
            return 0;
        }
        Save(s, "recovery entry: write failed (" + err + ")");
        Publish(s, fw);
        return 1;
    }
    if (restore) events.push_back("recovery entry: already on the iGPU");

    auto joined = [&events]() {
        std::string e;
        for (const auto& x : events) e += (e.empty() ? "" : "; ") + x;
        return e.empty() ? std::string("boot") : e;
    };
    if (!fw.present || !BoardAllowed()) {
        events.push_back(fw.present ? "board " + Board() + " not in the stack manifest: no firmware writes"
                                    : "no asus-wmi MUX interface");
        Save(s, joined());
        Publish(s, fw);
        SetProp("vendor.openbook.gfx.kms", "none");
        return 0;
    }

    if (s.phase == "pending") {
        const bool done = s.target == ModeName(mode) ||
                          (s.target == "eco" && mode == Mode::kHybrid && s.deferred == "dgpu-off");
        s.fw_after = FwString(fw);
        if (done && mode == Mode::kUltimate) {
            s.phase = "trial";
            s.tries = 0;
            events.push_back("switch applied: ultimate on trial");
        } else if (done) {
            s.phase = "idle";
            if (s.deferred.empty()) s.committed = s.target;
            events.push_back("switch applied: " + s.target);
        } else if (s.committed == ModeName(mode)) {
            s.phase = "idle";
            s.target = s.committed;
            s.deferred.clear();
            events.push_back("switch not applied: still " + s.committed);
        } else {
            s.phase = "idle";
            if (mode == Mode::kEco || mode == Mode::kHybrid) s.committed = s.target = ModeName(mode);
            events.push_back(std::string("switch partly applied: now ") + ModeName(mode));
        }
    }
    if (s.phase == "rollback") {
        if (mode == Mode::kUltimate || mode == Mode::kInvalid) {
            if (s.rollbacks >= kMaxRollbacks) {
                s.phase = "failed";
                events.push_back("rollback failed " + std::to_string(s.rollbacks) +
                                 " times; use the recovery entry or the firmware setup");
            } else {
                s.rollbacks++;
                std::string err;
                bool ok = WriteFw("gpu_mux_mode", 1, &err);
                Save(s, "rollback retry " + std::to_string(s.rollbacks) + (ok ? ": written, restarting" : ": " + err));
                Publish(s, ReadFirmware(paths_.fw));
                RequestReboot("openbook-gfx-rollback");
                return 0;
            }
        } else {
            s.phase = "idle";
            s.committed = s.target = ModeName(mode);
            s.tries = s.rollbacks = 0;
            events.push_back("rolled back to " + s.committed + " (" + s.last_failure + ")");
        }
    }
    if (s.phase == "failed" && (mode == Mode::kEco || mode == Mode::kHybrid)) {
        s.phase = "idle";
        s.committed = s.target = ModeName(mode);
        s.rollbacks = 0;
        events.push_back("firmware restored outside OpenBook");
    }
    if ((s.phase == "trial" || s.phase == "booted") && mode != Mode::kUltimate) {
        s.phase = "idle";
        if (mode == Mode::kEco || mode == Mode::kHybrid) s.committed = s.target = ModeName(mode);
        s.tries = 0;
        events.push_back("trial ended outside OpenBook");
    }
    if (s.phase == "idle") {
        if (mode == Mode::kInvalid) {
            Rollback(s, fw, "invalid firmware state " + FwString(fw));
            return 0;
        }
        if (mode == Mode::kUltimate && s.committed != "ultimate") {
            std::string why;
            if (!StackUsable("nouveau", &why)) {
                Rollback(s, fw, "ultimate set outside OpenBook: " + why);
                return 0;
            }
            if (s.locked == "eco" || s.locked == "hybrid") {
                Rollback(s, fw, "locked to " + s.locked);
                return 0;
            }
            s.phase = "trial";
            s.target = "ultimate";
            s.tries = 0;
            events.push_back("ultimate set outside OpenBook: on trial");
        }
    }
    if (s.phase == "idle") {
        std::string err;
        if (s.deferred == "dgpu-off" && mode == Mode::kHybrid) {
            if (WriteFw("dgpu_disable", 1, &err)) {
                fw = ReadFirmware(paths_.fw);
                mode = ModeOf(fw);
                s.committed = s.target = ModeName(mode);
                events.push_back("eco: dgpu_disable=1 written before the GPU drivers bind");
            } else {
                events.push_back("eco: dgpu_disable=1 failed (" + err + ")");
            }
        }
        s.deferred.clear();
        if (!s.locked.empty() && s.locked != ModeName(mode)) {
            if (s.locked == "eco" && mode == Mode::kHybrid && WriteFw("dgpu_disable", 1, &err)) {
                fw = ReadFirmware(paths_.fw);
                mode = ModeOf(fw);
                s.committed = s.target = ModeName(mode);
                events.push_back("lock: back to eco");
            } else if (s.locked == "hybrid" && mode == Mode::kEco && EnableDgpu(&err)) {
                fw = ReadFirmware(paths_.fw);
                mode = ModeOf(fw);
                s.committed = s.target = ModeName(mode);
                events.push_back("lock: back to hybrid (the dGPU appears after a restart)");
            } else {
                events.push_back("lock to " + s.locked + " not enforced" + (err.empty() ? "" : ": " + err));
            }
        }
        if ((mode == Mode::kEco || mode == Mode::kHybrid) && s.committed != ModeName(mode)) {
            events.push_back(std::string("mode changed outside OpenBook: ") + ModeName(mode));
            s.committed = s.target = ModeName(mode);
        }
    }

    // Every Ultimate boot is guarded: it counts until the panel shows a frame and boot completes.
    if (mode == Mode::kUltimate && (s.phase == "trial" || s.phase == "booted" || s.phase == "idle")) {
        std::string why;
        if (!StackUsable("nouveau", &why)) {
            Rollback(s, fw, "this image cannot drive ultimate: " + why);
            return 0;
        }
        if (s.phase == "booted") s.phase = "trial";  // restarted before the owner kept it
        s.tries++;
        if (s.tries > s.max_tries) {
            Rollback(s, fw, std::to_string(s.max_tries) + " ultimate boots without a healthy display");
            return 0;
        }
        events.push_back("guarded ultimate boot " + std::to_string(s.tries) + "/" + std::to_string(s.max_tries));
    }

    // An Ultimate boot whose count cannot be recorded is not protected: go back now.
    if (!Save(s, joined()) && mode == Mode::kUltimate) {
        Rollback(s, fw, "cannot record ultimate boots in " + paths_.state_dir);
        return 0;
    }
    Publish(s, fw);
    SetProp("vendor.openbook.gfx.kms", mode == Mode::kUltimate ? "nouveau" : "none");
    return 0;
}

// The selector's decision for this boot. anybook_gpu_probe makes it at early-init with the same code (gfx_select);
// this command is for the fixture tests and for a look on a running system.
int Controller::SelectStack() {
    Firmware fw = ReadFirmware(paths_.fw);
    Mode mode = ModeOf(fw);
    Selection sel = Select(mode, ReadCards(paths_.sysfs, false), ReadCards(paths_.sysfs, true), ReadPci(paths_.sysfs));
    Log(std::string("select: mode ") + ModeName(mode) + " -> hal " + sel.hal + " card " +
        (sel.display_card.empty() ? "-" : sel.display_card) + " render " +
        (sel.render_node.empty() ? "-" : sel.render_node) + " dgpu " + sel.dgpu +
        (sel.note.empty() ? "" : " (" + sel.note + ")"));
    SetProp("vendor.anybook.gpu.hal", sel.hal);
    SetProp("vendor.anybook.gpu.display_card", sel.display_card.empty() ? "none" : sel.display_card);
    SetProp("vendor.anybook.gpu.render_node", sel.render_node.empty() ? "none" : sel.render_node);
    SetProp("vendor.anybook.gpu.dgpu", sel.dgpu);
    SetProp("vendor.anybook.gpu.note", sel.note.empty() ? "none" : sel.note);
    return sel.hal == "none" ? 1 : 0;
}

int Controller::Frame(const std::string& card_connector) {
    FileLock lock(paths_.state_dir);
    State s = Load();
    Firmware fw = ReadFirmware(paths_.fw);
    const size_t colon = card_connector.find(':');
    const std::string card = card_connector.substr(0, colon);
    const std::string conn = colon == std::string::npos ? "" : card_connector.substr(colon + 1);
    const std::string want = ModeOf(fw) == Mode::kUltimate ? "nouveau" : "amdgpu";
    for (const auto& c : ReadCards(paths_.sysfs, false)) {
        if (c.node != card) continue;
        for (const auto& k : c.connectors) {
            if (k.name == conn && IsPanel(conn) && k.status == "connected" && c.driver == want) {
                s.frame = true;
                Save(s, "frame on " + card_connector + " (" + c.driver + ")");
                Publish(s, fw);
                return 0;
            }
        }
    }
    Save(s, "frame report ignored: " + card_connector + " is not a connected panel on " + want);
    return 1;
}

int Controller::Booted() {
    FileLock lock(paths_.state_dir);
    State s = Load();
    Firmware fw = ReadFirmware(paths_.fw);
    if (ModeOf(fw) != Mode::kUltimate) return 0;
    if (!s.frame) {
        Save(s, "boot completed without a frame on the panel");
        Publish(s, fw);
        return 1;
    }
    s.tries = 0;
    if (s.phase == "trial") {
        s.phase = "booted";
        Save(s, "healthy: waiting for the owner to keep ultimate");
    } else {
        Save(s, "healthy");
    }
    Publish(s, fw);
    return 0;
}

int Controller::Keep(Channel ch) {
    FileLock lock(paths_.state_dir);
    State s = Load();
    if (s.phase != "booted") {
        Log("keep refused: phase " + s.phase + " (nothing healthy to keep)");
        if (ch != Channel::kCli) {
            SetResult(s, "refused-nothing-to-keep", "refused: nothing to keep (phase " + s.phase + ")");
            Save(s, "keep refused");
            Publish(s, ReadFirmware(paths_.fw));
        }
        return 1;
    }
    s.phase = "idle";
    s.committed = s.target = "ultimate";
    s.last_failure.clear();
    SetResult(s, "done", "done");
    Save(s, "owner kept ultimate");
    Publish(s, ReadFirmware(paths_.fw));
    return 0;
}

int Controller::Shown() {
    FileLock lock(paths_.state_dir);
    State s = Load();
    if (s.phase != "booted" || s.shown) return 0;
    s.shown = true;
    SetResult(s, "done", "done");
    Save(s, "the owner was asked to keep ultimate");
    Publish(s, ReadFirmware(paths_.fw));
    return 0;
}

int Controller::Revert(Channel ch) {
    FileLock lock(paths_.state_dir);
    State s = Load();
    Firmware fw = ReadFirmware(paths_.fw);
    if (ModeOf(fw) != Mode::kUltimate) {
        Log("revert refused: not in ultimate");
        if (ch != Channel::kCli) {
            SetResult(s, "refused-not-ultimate", "refused: not in ultimate");
            Save(s, "revert refused");
            Publish(s, fw);
        }
        return 1;
    }
    SetResult(s, "restart", "restart");
    Rollback(s, fw, "owner asked to go back");
    return 0;
}

int Controller::Deadline() {
    FileLock lock(paths_.state_dir);
    State s = Load();
    Firmware fw = ReadFirmware(paths_.fw);
    if (s.phase == "booted") {
        Rollback(s, fw, "the owner did not keep ultimate");
        return 0;
    }
    if (ModeOf(fw) == Mode::kUltimate && s.tries > 0 && (s.phase == "trial" || s.phase == "idle")) {
        if (s.tries >= s.max_tries) {
            Rollback(s, fw, std::to_string(s.tries) + " ultimate boots without a healthy display");
        } else {
            Save(s, "no healthy display by the deadline: restarting (" + std::to_string(s.tries) + "/" +
                        std::to_string(s.max_tries) + ")");
            Publish(s, fw);
            RequestReboot("openbook-gfx-retry");
        }
        return 0;
    }
    Log("deadline: nothing to do (phase " + s.phase + ")");
    return 0;
}

// Started by init in every Ultimate boot (vendor.openbook.gfx.kms=nouveau). One look a second at the record that
// `frame`, `booted`, `shown` and `keep` keep: a frame on the panel by the frame deadline, boot completion (a
// healthy boot resets the count) by the boot deadline, and for a new Ultimate the owner's answer within the keep
// deadline of the dialog. A missed deadline is Deadline(): a restart while tries are left, else the rollback.
int Controller::Watchdog() {
    const int frame_s = ConfigSeconds("frame_deadline_s", kFrameDeadlineS);
    const int boot_s = ConfigSeconds("boot_deadline_s", kBootDeadlineS);
    const int keep_s = ConfigSeconds("keep_deadline_s", kKeepDeadlineS);
    const double start = Uptime();
    double shown_at = -1;
    Log("watchdog: frame within " + std::to_string(frame_s) + " s, boot completion within " +
        std::to_string(boot_s) + " s, the owner's answer within " + std::to_string(keep_s) + " s of the dialog");
    for (;;) {
        State s;
        Firmware fw;
        {
            FileLock lock(paths_.state_dir);
            s = Load();
            fw = ReadFirmware(paths_.fw);
        }
        const double t = Uptime() - start;
        if (ModeOf(fw) != Mode::kUltimate || s.phase == "rollback" || s.phase == "failed") {
            Log("watchdog: not an ultimate boot any more (phase " + s.phase + ")");
            return 0;
        }
        const bool healthy = s.frame && s.tries == 0;  // Booted() resets the count after a frame
        if (!s.frame && t > frame_s) {
            Log("watchdog: no frame on the panel after " + std::to_string(frame_s) + " s (the selector chose hal " +
                GetProp("vendor.anybook.gpu.hal") + ", card " + GetProp("vendor.anybook.gpu.display_card") +
                ", note " + GetProp("vendor.anybook.gpu.note") + ")");
            return Deadline();
        }
        if (!healthy && t > boot_s) {
            Log("watchdog: boot did not complete in " + std::to_string(boot_s) + " s");
            return Deadline();
        }
        if (healthy && s.phase != "booted") {
            Log("watchdog: healthy " + s.phase + " ultimate boot");
            return 0;
        }
        if (healthy && s.phase == "booted") {
            if (s.shown && shown_at < 0) shown_at = t;
            if (shown_at >= 0 && t - shown_at > keep_s) {
                Log("watchdog: no answer " + std::to_string(keep_s) + " s after the dialog");
                return Deadline();
            }
            if (shown_at < 0 && t > boot_s) {
                Log("watchdog: the keep dialog was not shown in " + std::to_string(boot_s) + " s");
                return Deadline();
            }
        }
        usleep(1000 * 1000);
    }
}

int Controller::Request(const std::string& mode_name, Channel ch) {
    auto mode = ParseMode(mode_name);
    if (!mode) {
        Log("request refused: '" + mode_name + "' is not eco, hybrid or ultimate");
        return 2;
    }
    FileLock lock(paths_.state_dir);
    Firmware fw = ReadFirmware(paths_.fw);
    State s = Load();
    auto refuse = [&](const std::string& code, const std::string& why) {
        SetResult(s, code, "refused: " + why);
        Log("request " + mode_name + " refused: " + why);
        if (ch != Channel::kCli) {
            Save(s, "request " + mode_name + " refused");
            Publish(s, fw);
        }
        return 1;
    };
    if (!fw.present) return refuse("refused-unsupported", "no asus-wmi MUX interface");
    if (!BoardAllowed()) return refuse("refused-unsupported", "board " + Board() + " is not in the stack manifest");
    // After failed rollbacks, asking for an iGPU mode is one more attempt at the safe direction.
    if (s.phase != "idle" && !(s.phase == "failed" && *mode != Mode::kUltimate)) {
        return refuse("refused-busy", "busy (phase " + s.phase + ")");
    }
    if (!s.locked.empty() && s.locked != mode_name) return refuse("refused-locked", "locked to " + s.locked);
    const Mode cur = ModeOf(fw);
    if (cur == Mode::kInvalid) {
        return refuse("refused-invalid-firmware", "firmware state " + FwString(fw) + " is invalid; restart to repair");
    }
    if (cur == *mode && s.deferred.empty()) {
        SetResult(s, "already", "already " + mode_name);
        Log("request " + mode_name + ": already there");
        if (ch != Channel::kCli) {
            Save(s, "request " + mode_name + ": already there");
            Publish(s, fw);
        }
        return 0;
    }
    std::string why, err;
    if (*mode == Mode::kUltimate) {
        // The app offers Ultimate only on a release that says so; adb (with the lab switch) and the command line
        // also take a development stack, for ANAL-244's bring-up on a dev image.
        if (ch == Channel::kApp && !UltimateOffered()) {
            return refuse(StackState("nouveau", &why) == "verified" ? "refused-not-offered" : "refused-unverified",
                          "ultimate is not offered on this version");
        }
        if (!StackUsable("nouveau", &why)) return refuse("refused-unverified", why);
    }
    if (dry_run_) {
        Log("dry-run: would switch " + std::string(ModeName(cur)) + " -> " + mode_name);
        SetResult(s, "dry-run", "dry-run");
        if (ch != Channel::kCli) {
            Save(s, "request " + mode_name + ": firmware writes are off in this image");
            Publish(s, fw);
        }
        return 0;
    }
    s.fw_before = FwString(fw);
    s.last_failure.clear();
    bool reboot = true;

    // A MUX write takes effect at the next boot. Arm the state durably first, so that a power cut after the
    // write still finds the switch at the next early init.
    auto mux_switch = [&](int mux, const std::string& target) {
        s.phase = "pending";
        s.target = target;
        s.seq++;
        s.tries = s.rollbacks = 0;
        if (!Save(s, "request " + mode_name + ": armed")) {
            err = "cannot record the switch in " + paths_.state_dir;
            return false;
        }
        Crash("after-arm");
        if (!WriteFw("gpu_mux_mode", mux, &err)) {
            s.phase = "idle";
            s.target = s.committed;
            s.deferred.clear();
            Save(s, "request " + mode_name + ": gpu_mux_mode write refused (" + err + ")");
            Publish(s, ReadFirmware(paths_.fw));
            return false;
        }
        Crash("after-mux-write");
        return true;
    };

    if (*mode == Mode::kUltimate) {
        if (fw.dgpu == 1 && !EnableDgpu(&err)) return refuse("failed-firmware", "could not enable the dGPU: " + err);
        if (!mux_switch(0, "ultimate")) return refuse("failed-firmware", "gpu_mux_mode=0 refused: " + err);
    } else if (*mode == Mode::kHybrid) {
        if (cur == Mode::kUltimate) {
            if (!mux_switch(1, "hybrid")) return refuse("failed-firmware", "gpu_mux_mode=1 refused: " + err);
        } else if (cur == Mode::kEco) {
            if (!EnableDgpu(&err)) return refuse("failed-firmware", "could not enable the dGPU: " + err);
            s.committed = s.target = "hybrid";
        } else {  // hybrid with eco still pending
            reboot = false;
            s.target = s.committed;
        }
        s.deferred.clear();
    } else {  // eco
        if (cur == Mode::kUltimate) {
            s.deferred = "dgpu-off";  // the guard refuses dgpu_disable=1 while the MUX is on the dGPU
            if (!mux_switch(1, "eco")) return refuse("failed-firmware", "gpu_mux_mode=1 refused: " + err);
        } else if (DgpuDriverBusy()) {
            s.deferred = "dgpu-off";  // a GPU driver drives the dGPU: switch before it binds, at the next boot
            s.target = "eco";
        } else {
            if (!WriteFw("dgpu_disable", 1, &err)) return refuse("failed-firmware", "dgpu_disable=1 refused: " + err);
            s.committed = s.target = "eco";
            reboot = false;
        }
    }
    s.fw_after = FwString(ReadFirmware(paths_.fw));
    SetResult(s, reboot ? "restart" : "done", reboot ? "restart" : "done");
    Save(s, "request " + mode_name + ": " + s.fw_before + " -> " + s.fw_after +
                (reboot ? ", restart to finish" : ", done"));
    Publish(s, ReadFirmware(paths_.fw));
    return 0;
}

int Controller::Lock(const std::string& mode_name, Channel ch) {
    FileLock lock(paths_.state_dir);
    State s = Load();
    Firmware fw = ReadFirmware(paths_.fw);
    const std::string current = ModeName(ModeOf(fw));
    const std::string m = mode_name.empty() ? current : mode_name;
    if (!ValidMode(m) || m != current || s.phase != "idle") {
        Log("lock refused: lock the current mode (" + current + ") while no switch is under way");
        if (ch != Channel::kCli) {
            SetResult(s, "refused-busy", "refused: lock the current mode while no switch is under way");
            Save(s, "lock refused");
            Publish(s, fw);
        }
        return 1;
    }
    s.locked = m;
    SetResult(s, "done", "done");
    Save(s, "locked to " + m);
    Publish(s, fw);
    return 0;
}

int Controller::Unlock(Channel) {
    FileLock lock(paths_.state_dir);
    State s = Load();
    s.locked.clear();
    SetResult(s, "done", "done");
    Save(s, "unlocked");
    Publish(s, ReadFirmware(paths_.fw));
    return 0;
}

int Controller::Restore() {
    FileLock lock(paths_.state_dir);
    State s = Load();
    Firmware fw = ReadFirmware(paths_.fw);
    if (!fw.present || fw.mux != 0) {
        Log("restore: nothing to do (firmware " + FwString(fw) + ")");
        SetResult(s, "already", "already on the iGPU");
        Publish(s, fw);
        return 0;
    }
    SetResult(s, "restart", "restart");
    Rollback(s, fw, "restore requested");
    return 0;
}

int Controller::Status() {
    Firmware fw = ReadFirmware(paths_.fw);
    State s = Load();
    std::string why = "ok";
    const std::string stack = StackState("nouveau", &why);
    std::ostringstream o;
    o << "firmware=" << FwString(fw) << "\nmode=" << ModeName(ModeOf(fw)) << "\nboard=" << Board()
      << "\nboard_allowed=" << (BoardAllowed() ? 1 : 0) << "\nnouveau_stack=" << stack
      << (stack == "unverified" ? " (" + why + ")" : "") << "\nultimate=" << UltimateAvailability(fw)
      << "\nfirmware_writes=" << (dry_run_ ? "off" : "on") << "\n"
      << Serialize(s);
    fputs(o.str().c_str(), stdout);
#ifdef __ANDROID__
    std::stringstream lines(o.str());
    for (std::string l; std::getline(lines, l);) __android_log_write(ANDROID_LOG_INFO, "openbook-gfx-mode", l.c_str());
#endif
    return 0;
}

// The OpenBook Graphics app's channel: openbook.gfx.request, a platform property only the app's domain may set
// (init passes its value here). VERB[:MODE]@SEQ, where VERB is switch (with a mode), lock (optionally with a
// mode), unlock, keep, revert or shown. Every answer carries SEQ, so the app matches it to its request.
int Controller::App(const std::string& value) {
    auto p = ParseRequest(value, true);
    if (!p) {
        Log("app request refused: '" + value + "' is not VERB[:MODE]@SEQ");
        SetProp("vendor.openbook.gfx.request_result", "bad-request");
        return 2;
    }
    tag_ = p->seq;
    Log("app request " + p->verb + (p->arg.empty() ? "" : " " + p->arg) + " (" + p->seq + ")");
    if (p->verb == "switch" && ParseMode(p->arg)) return Request(p->arg, Channel::kApp);
    if (p->verb == "lock" && (p->arg.empty() || ParseMode(p->arg))) return Lock(p->arg, Channel::kApp);
    if (p->verb == "unlock" && p->arg.empty()) return Unlock(Channel::kApp);
    if (p->verb == "keep" && p->arg.empty()) return Keep(Channel::kApp);
    if (p->verb == "revert" && p->arg.empty()) return Revert(Channel::kApp);
    if (p->verb == "shown" && p->arg.empty()) return Shown();
    FileLock lock(paths_.state_dir);
    State s = Load();
    SetResult(s, "bad-request", "bad request");
    Save(s, "app request refused: " + value);
    Publish(s, ReadFirmware(paths_.fw));
    return 2;
}

// The adb channel: debug.openbook.gfx, which the shell may set. Always: hybrid, restore, revert, status (the safe
// direction and a look). With the lab switch on (ANAL-257): eco, ultimate, keep, lock[:MODE], unlock. An optional
// @N lets the same command run again.
int Controller::Adb(const std::string& value) {
    auto p = ParseRequest(value, false);
    tag_ = "adb";
    if (!p) {
        Log("adb request refused: '" + value + "'");
        return 2;
    }
    const std::string& v = p->verb;
    Log("adb request " + v + (p->arg.empty() ? "" : " " + p->arg));
    if (v == "status" && p->arg.empty()) {
        {
            FileLock lock(paths_.state_dir);
            State s = Load();
            Publish(s, ReadFirmware(paths_.fw));
        }
        return Status();
    }
    if (v == "hybrid" && p->arg.empty()) return Request("hybrid", Channel::kAdb);
    if (v == "restore" && p->arg.empty()) return Restore();
    if (v == "revert" && p->arg.empty()) return Revert(Channel::kAdb);
    const bool lab_verb = (v == "eco" || v == "ultimate" || v == "keep" || v == "unlock") ? p->arg.empty()
                          : v == "lock" ? (p->arg.empty() || ParseMode(p->arg).has_value())
                                        : false;
    if (!lab_verb) {
        Log("adb request refused: unknown command '" + value + "'");
        return 2;
    }
    if (!LabOn()) {
        FileLock lock(paths_.state_dir);
        State s = Load();
        SetResult(s, "refused-lab-off", "refused: " + v + " over adb needs the lab switch (debug.openbook.lab)");
        Save(s, "adb request " + v + " refused: lab switch off");
        Publish(s, ReadFirmware(paths_.fw));
        return 1;
    }
    if (v == "eco" || v == "ultimate") return Request(v, Channel::kAdb);
    if (v == "keep") return Keep(Channel::kAdb);
    if (v == "lock") return Lock(p->arg, Channel::kAdb);
    return Unlock(Channel::kAdb);
}

}  // namespace openbook::gfx
