// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "gfx_mode.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <map>
#include <set>
#include <sstream>

#ifdef __ANDROID__
#include <android/log.h>
#include <sys/system_properties.h>
#endif

namespace openbook::gfx {
namespace {

constexpr char kSchema[] = "openbook-gfx-state/1";
constexpr char kStacksSchema[] = "# openbook-gfx-stacks/1";
constexpr int kMaxRollbacks = 3;
constexpr unsigned kVendorNvidia = 0x10de;
constexpr size_t kPropValueMax = 91;  // PROP_VALUE_MAX - 1

std::string Trim(const std::string& s) {
    size_t b = s.find_first_not_of(" \t\r\n"), e = s.find_last_not_of(" \t\r\n");
    return b == std::string::npos ? "" : s.substr(b, e - b + 1);
}

bool ReadFile(const std::string& path, std::string* out) {
    int fd = open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (fd < 0) return false;
    out->clear();
    char buf[4096];
    ssize_t n;
    while ((n = read(fd, buf, sizeof(buf))) > 0) out->append(buf, n);
    int saved = errno;
    close(fd);
    errno = saved;
    return n == 0;
}

std::vector<std::string> ListDir(const std::string& dir) {
    std::vector<std::string> names;
    if (DIR* d = opendir(dir.c_str())) {
        while (dirent* e = readdir(d)) {
            if (e->d_name[0] != '.') names.emplace_back(e->d_name);
        }
        closedir(d);
    }
    std::sort(names.begin(), names.end());
    return names;
}

std::string Basename(const std::string& p) {
    size_t s = p.find_last_of('/');
    return s == std::string::npos ? p : p.substr(s + 1);
}

std::string LinkBasename(const std::string& path) {
    char buf[PATH_MAX];
    ssize_t n = readlink(path.c_str(), buf, sizeof(buf) - 1);
    if (n <= 0) return "";
    buf[n] = '\0';
    return Basename(buf);
}

bool IsPciSlot(const std::string& s) {
    // 0000:65:00.0
    if (s.size() != 12 || s[4] != ':' || s[7] != ':' || s[10] != '.') return false;
    for (size_t i : {0, 1, 2, 3, 5, 6, 8, 9}) {
        if (!isxdigit(static_cast<unsigned char>(s[i]))) return false;
    }
    return s[11] >= '0' && s[11] <= '7';
}

bool ParseInt(const std::string& s, int* out) {
    std::string t = Trim(s);
    if (t.empty() || t.size() > 9) return false;
    char* end = nullptr;
    long v = strtol(t.c_str(), &end, 10);
    if (*end != '\0') return false;
    *out = static_cast<int>(v);
    return true;
}

unsigned ReadHex(const std::string& path) {
    std::string s;
    if (!ReadFile(path, &s)) return 0;
    return static_cast<unsigned>(strtoul(Trim(s).c_str(), nullptr, 16));
}

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

struct Stacks {
    std::set<std::string> boards;
    std::map<std::string, std::string> state;  // stack -> verified | unverified
    std::map<std::string, std::vector<std::string>> files;
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
        } else if (kind == "stack" && (b == "verified" || b == "unverified")) {
            s.state[a] = b;
        } else if (kind == "file" && !b.empty() && b[0] == '/') {
            s.files[a].push_back(b);
        } else {
            *why = "stack manifest: unreadable line '" + line + "'";
            return std::nullopt;
        }
    }
    return s;
}

}  // namespace

const char* ModeName(Mode m) {
    switch (m) {
        case Mode::kEco: return "eco";
        case Mode::kHybrid: return "hybrid";
        case Mode::kUltimate: return "ultimate";
        case Mode::kInvalid: return "invalid";
        default: return "unknown";
    }
}

std::optional<Mode> ParseMode(const std::string& s) {
    if (s == "eco") return Mode::kEco;
    if (s == "hybrid") return Mode::kHybrid;
    if (s == "ultimate") return Mode::kUltimate;
    return std::nullopt;
}

Mode ModeOf(const Firmware& fw) {
    if (!fw.present) return Mode::kUnknown;
    if (fw.mux == 1) return fw.dgpu == 1 ? Mode::kEco : Mode::kHybrid;
    return fw.dgpu == 1 ? Mode::kInvalid : Mode::kUltimate;  // the kernel refuses to make mux=0 dgpu=1
}

std::string FwString(const Firmware& fw) {
    if (!fw.present) return "absent";
    return "mux=" + std::to_string(fw.mux) + ",dgpu=" + std::to_string(fw.dgpu);
}

std::string Serialize(const State& s) {
    std::ostringstream o;
    o << "schema=" << kSchema << "\n"
      << "committed=" << s.committed << "\ntarget=" << s.target << "\nphase=" << s.phase << "\n"
      << "tries=" << s.tries << "\nmax_tries=" << s.max_tries << "\nrollbacks=" << s.rollbacks << "\n"
      << "seq=" << s.seq << "\nboots=" << s.boots << "\nframe=" << (s.frame ? 1 : 0) << "\n"
      << "locked=" << s.locked << "\ndeferred=" << s.deferred << "\nlast_failure=" << s.last_failure << "\n"
      << "event=" << s.event << "\nfw_before=" << s.fw_before << "\nfw_after=" << s.fw_after << "\n";
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
                   k == "frame") {
            if (!ParseInt(v, &n) || n < 0) return std::nullopt;
            if (k == "tries") s.tries = n;
            if (k == "max_tries") s.max_tries = std::clamp(n, 1, 5);
            if (k == "rollbacks") s.rollbacks = n;
            if (k == "seq") s.seq = n;
            if (k == "boots") s.boots = n;
            if (k == "frame") s.frame = n != 0;
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
        }  // unknown keys from a newer version are ignored
    }
    return s;
}

bool IsPanel(const std::string& c) {
    return c.rfind("eDP-", 0) == 0 || c.rfind("LVDS-", 0) == 0 || c.rfind("DSI-", 0) == 0;
}

Selection Select(Mode mode, const std::vector<Card>& cards, const std::vector<Card>& render_nodes,
                 const std::vector<PciFn>& pci) {
    auto panel = [](const Card& c) {
        return std::any_of(c.connectors.begin(), c.connectors.end(),
                           [](const Connector& k) { return IsPanel(k.name) && k.status == "connected"; });
    };
    auto find = [&](const std::string& driver, bool need_panel) -> const Card* {
        for (const auto& c : cards) {
            if (c.driver == driver && (!need_panel || panel(c))) return &c;
        }
        return nullptr;
    };
    Selection s;
    const Card* chosen = nullptr;
    if (mode == Mode::kUltimate) {
        if ((chosen = find("nouveau", true))) {
            s.hal = "nouveau";
        } else if ((chosen = find("amdgpu", true))) {
            s.hal = "amdgpu";
            s.note = "ultimate-but-panel-on-amdgpu";
        } else if ((chosen = find("nouveau", false))) {
            s.hal = "nouveau";
            s.note = "no-connected-panel";
        } else {
            s.note = "no-display-gpu";
        }
    } else {
        if ((chosen = find("amdgpu", true))) {
            s.hal = "amdgpu";
        } else if ((chosen = find("nouveau", true))) {
            s.hal = "nouveau";
            s.note = "panel-on-nouveau-in-optimus";
        } else if ((chosen = find("amdgpu", false))) {
            s.hal = "amdgpu";
            s.note = "no-connected-panel";
        } else if ((chosen = find("virtio_gpu", false))) {
            s.hal = "virtio";
        } else {
            s.note = "no-display-gpu";
        }
    }
    if (chosen) {
        s.display_card = chosen->node;
        for (const auto& r : render_nodes) {
            if (!chosen->pci.empty() && r.pci == chosen->pci) {
                s.render_node = r.node;
                break;
            }
        }
    }
    bool dgpu = std::any_of(pci.begin(), pci.end(),
                            [](const PciFn& f) { return f.vendor == kVendorNvidia && (f.pci_class >> 16) == 0x03; });
    s.dgpu = !dgpu ? "absent" : mode == Mode::kUltimate ? "display" : "off";
    return s;
}

Controller::Controller(Paths paths, bool dry_run) : paths_(std::move(paths)), dry_run_(dry_run) {}

void Controller::Log(const std::string& line) {
    printf("openbook-gfx-mode: %s\n", line.c_str());
    fflush(stdout);
#ifdef __ANDROID__
    __android_log_write(ANDROID_LOG_INFO, "openbook-gfx-mode", line.c_str());
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

Firmware Controller::ReadFirmware() {
    Firmware fw;
    std::string mux, dgpu;
    if (ReadFile(paths_.fw + "/gpu_mux_mode", &mux) && ReadFile(paths_.fw + "/dgpu_disable", &dgpu) &&
        ParseInt(mux, &fw.mux) && ParseInt(dgpu, &fw.dgpu) && (fw.mux == 0 || fw.mux == 1) &&
        (fw.dgpu == 0 || fw.dgpu == 1)) {
        fw.present = true;
    } else {
        fw = Firmware{};
    }
    return fw;
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
    if (ReadFirmware().dgpu == 0) return true;
    Log("dgpu_disable still reads 1: rescanning PCI and writing again");
    std::string ignored;
    WriteFw("rescan", 1, &ignored);
    if (!WriteFw("dgpu_disable", 0, error)) return false;
    if (ReadFirmware().dgpu == 0) return true;
    *error = "dgpu_disable still reads 1 after two writes and a PCI rescan";
    return false;
}

std::vector<Card> Controller::Cards(bool render) {
    std::vector<Card> out;
    const std::string drm = paths_.sysfs + "/class/drm";
    const std::vector<std::string> names = ListDir(drm);
    const std::string prefix = render ? "renderD" : "card";
    for (const auto& name : names) {
        if (name.rfind(prefix, 0) != 0 || name.find('-') != std::string::npos) continue;
        if (!std::all_of(name.begin() + prefix.size(), name.end(), ::isdigit) || name.size() == prefix.size()) continue;
        Card c;
        c.node = name;
        const std::string dev = drm + "/" + name + "/device";
        c.driver = LinkBasename(dev + "/driver");
        char real[PATH_MAX];
        if (realpath(dev.c_str(), real)) {
            for (std::string p = real; p.size() > 1; p = p.substr(0, p.find_last_of('/'))) {
                if (IsPciSlot(Basename(p))) {
                    c.pci = Basename(p);
                    break;
                }
                if (p.find('/') == std::string::npos) break;
            }
        }
        if (!render) {
            for (const auto& conn : names) {
                if (conn.rfind(name + "-", 0) != 0) continue;
                std::string status;
                ReadFile(drm + "/" + conn + "/status", &status);
                c.connectors.push_back({conn.substr(name.size() + 1), Trim(status)});
            }
        }
        out.push_back(c);
    }
    return out;
}

std::vector<PciFn> Controller::Pci() {
    std::vector<PciFn> out;
    const std::string dir = paths_.sysfs + "/bus/pci/devices";
    for (const auto& slot : ListDir(dir)) {
        PciFn f;
        f.slot = slot;
        f.vendor = ReadHex(dir + "/" + slot + "/vendor");
        f.pci_class = ReadHex(dir + "/" + slot + "/class");
        f.driver = LinkBasename(dir + "/" + slot + "/driver");
        out.push_back(f);
    }
    return out;
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

bool Controller::StackVerified(const std::string& stack, std::string* why) {
    auto stacks = LoadStacks(paths_.stacks, why);
    if (!stacks) return false;
    auto it = stacks->state.find(stack);
    if (it == stacks->state.end() || it->second != "verified") {
        *why = stack + " stack is not verified in this image";
        return false;
    }
    if (stacks->files[stack].empty()) {
        *why = stack + " stack lists no files";
        return false;
    }
    for (const auto& f : stacks->files[stack]) {
        struct stat st;
        if (stat(f.c_str(), &st) != 0 || !S_ISREG(st.st_mode) || st.st_size == 0) {
            *why = stack + " stack: missing " + f;
            return false;
        }
    }
    return true;
}

bool Controller::DgpuDriverBusy() {
    for (const auto& f : Pci()) {
        if (f.vendor == kVendorNvidia && (f.pci_class >> 16) == 0x03 && !f.driver.empty()) return true;
    }
    return false;
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
        s.fw_after = FwString(ReadFirmware());
        Save(s, "rollback: gpu_mux_mode=1 written, restarting");
    } else {
        Save(s, "rollback: write failed (" + err + "), the next boot retries");
    }
    Publish(s, ReadFirmware());
    RequestReboot("openbook-gfx-rollback");
}

int Controller::Boot() {
    FileLock lock(paths_.state_dir);
    Firmware fw = ReadFirmware();
    State s = Load();
    const bool fresh = !loaded_;
    s.boots++;
    s.frame = false;
    Mode mode = ModeOf(fw);
    std::vector<std::string> events;
    Log("boot " + std::to_string(s.boots) + ": firmware " + FwString(fw) + " (" + ModeName(mode) + "), phase " +
        s.phase + ", committed " + s.committed + (dry_run_ ? ", dry run" : ""));
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
            s.fw_after = FwString(ReadFirmware());
            Save(s, "recovery entry: gpu_mux_mode=1 written, restarting");
            Publish(s, ReadFirmware());
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
                Publish(s, ReadFirmware());
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
            if (!StackVerified("nouveau", &why)) {
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
                fw = ReadFirmware();
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
                fw = ReadFirmware();
                mode = ModeOf(fw);
                s.committed = s.target = ModeName(mode);
                events.push_back("lock: back to eco");
            } else if (s.locked == "hybrid" && mode == Mode::kEco && EnableDgpu(&err)) {
                fw = ReadFirmware();
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
        if (!StackVerified("nouveau", &why)) {
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

int Controller::SelectStack() {
    Firmware fw = ReadFirmware();
    Mode mode = ModeOf(fw);
    Selection sel = Select(mode, Cards(false), Cards(true), Pci());
    Log(std::string("select: mode ") + ModeName(mode) + " -> hal " + sel.hal + " card " +
        (sel.display_card.empty() ? "-" : sel.display_card) + " render " +
        (sel.render_node.empty() ? "-" : sel.render_node) + " dgpu " + sel.dgpu +
        (sel.note.empty() ? "" : " (" + sel.note + ")"));
    SetProp("vendor.anybook.gpu.hal", sel.hal);
    SetProp("vendor.anybook.gpu.display_card", sel.display_card.empty() ? "none" : sel.display_card);
    SetProp("vendor.anybook.gpu.render_node", sel.render_node.empty() ? "none" : sel.render_node);
    SetProp("vendor.openbook.gfx.dgpu", sel.dgpu);
    SetProp("vendor.openbook.gfx.select_note", sel.note.empty() ? "none" : sel.note);
    return sel.hal == "none" ? 1 : 0;
}

int Controller::Frame(const std::string& card_connector) {
    FileLock lock(paths_.state_dir);
    State s = Load();
    Firmware fw = ReadFirmware();
    const size_t colon = card_connector.find(':');
    const std::string card = card_connector.substr(0, colon);
    const std::string conn = colon == std::string::npos ? "" : card_connector.substr(colon + 1);
    const std::string want = ModeOf(fw) == Mode::kUltimate ? "nouveau" : "amdgpu";
    for (const auto& c : Cards(false)) {
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
    Firmware fw = ReadFirmware();
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

int Controller::Keep() {
    FileLock lock(paths_.state_dir);
    State s = Load();
    if (s.phase != "booted") {
        Log("keep refused: phase " + s.phase + " (nothing healthy to keep)");
        return 1;
    }
    s.phase = "idle";
    s.committed = s.target = "ultimate";
    s.last_failure.clear();
    Save(s, "owner kept ultimate");
    Publish(s, ReadFirmware());
    return 0;
}

int Controller::Revert() {
    FileLock lock(paths_.state_dir);
    State s = Load();
    Firmware fw = ReadFirmware();
    if (ModeOf(fw) != Mode::kUltimate) {
        Log("revert refused: not in ultimate");
        return 1;
    }
    Rollback(s, fw, "owner asked to go back");
    return 0;
}

int Controller::Deadline() {
    FileLock lock(paths_.state_dir);
    State s = Load();
    Firmware fw = ReadFirmware();
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

int Controller::Request(const std::string& mode_name) {
    auto mode = ParseMode(mode_name);
    if (!mode) {
        Log("request refused: '" + mode_name + "' is not eco, hybrid or ultimate");
        return 2;
    }
    FileLock lock(paths_.state_dir);
    Firmware fw = ReadFirmware();
    State s = Load();
    auto refuse = [&](const std::string& why) {
        SetProp("vendor.openbook.gfx.request_result", "refused: " + why);
        Log("request " + mode_name + " refused: " + why);
        return 1;
    };
    if (!fw.present) return refuse("no asus-wmi MUX interface");
    if (!BoardAllowed()) return refuse("board " + Board() + " is not in the stack manifest");
    // After failed rollbacks, asking for an iGPU mode is one more attempt at the safe direction.
    if (s.phase != "idle" && !(s.phase == "failed" && *mode != Mode::kUltimate)) {
        return refuse("busy (phase " + s.phase + ")");
    }
    if (!s.locked.empty() && s.locked != mode_name) return refuse("locked to " + s.locked);
    const Mode cur = ModeOf(fw);
    if (cur == Mode::kInvalid) return refuse("firmware state " + FwString(fw) + " is invalid; restart to repair");
    if (cur == *mode && s.deferred.empty()) {
        SetProp("vendor.openbook.gfx.request_result", "already " + mode_name);
        Log("request " + mode_name + ": already there");
        return 0;
    }
    std::string why, err;
    if (*mode == Mode::kUltimate && !StackVerified("nouveau", &why)) return refuse(why);
    if (dry_run_) {
        Log("dry-run: would switch " + std::string(ModeName(cur)) + " -> " + mode_name);
        SetProp("vendor.openbook.gfx.request_result", "dry-run");
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
            Publish(s, ReadFirmware());
            return false;
        }
        Crash("after-mux-write");
        return true;
    };

    if (*mode == Mode::kUltimate) {
        if (fw.dgpu == 1 && !EnableDgpu(&err)) return refuse("could not enable the dGPU: " + err);
        if (!mux_switch(0, "ultimate")) return refuse("gpu_mux_mode=0 refused: " + err);
    } else if (*mode == Mode::kHybrid) {
        if (cur == Mode::kUltimate) {
            if (!mux_switch(1, "hybrid")) return refuse("gpu_mux_mode=1 refused: " + err);
        } else if (cur == Mode::kEco) {
            if (!EnableDgpu(&err)) return refuse("could not enable the dGPU: " + err);
            s.committed = s.target = "hybrid";
        } else {  // hybrid with eco still pending
            reboot = false;
            s.target = s.committed;
        }
        s.deferred.clear();
    } else {  // eco
        if (cur == Mode::kUltimate) {
            s.deferred = "dgpu-off";  // the guard refuses dgpu_disable=1 while the MUX is on the dGPU
            if (!mux_switch(1, "eco")) return refuse("gpu_mux_mode=1 refused: " + err);
        } else if (DgpuDriverBusy()) {
            s.deferred = "dgpu-off";  // a GPU driver drives the dGPU: switch before it binds, at the next boot
            s.target = "eco";
        } else {
            if (!WriteFw("dgpu_disable", 1, &err)) return refuse("dgpu_disable=1 refused: " + err);
            s.committed = s.target = "eco";
            reboot = false;
        }
    }
    s.fw_after = FwString(ReadFirmware());
    Save(s, "request " + mode_name + ": " + s.fw_before + " -> " + s.fw_after +
                (reboot ? ", restart to finish" : ", done"));
    Publish(s, ReadFirmware());
    SetProp("vendor.openbook.gfx.request_result", reboot ? "restart" : "done");
    return 0;
}

int Controller::Lock(const std::string& mode_name) {
    FileLock lock(paths_.state_dir);
    State s = Load();
    const std::string current = ModeName(ModeOf(ReadFirmware()));
    const std::string m = mode_name.empty() ? current : mode_name;
    if (!ValidMode(m) || m != current || s.phase != "idle") {
        Log("lock refused: lock the current mode (" + current + ") while no switch is under way");
        return 1;
    }
    s.locked = m;
    Save(s, "locked to " + m);
    Publish(s, ReadFirmware());
    return 0;
}

int Controller::Unlock() {
    FileLock lock(paths_.state_dir);
    State s = Load();
    s.locked.clear();
    Save(s, "unlocked");
    Publish(s, ReadFirmware());
    return 0;
}

int Controller::Restore() {
    FileLock lock(paths_.state_dir);
    State s = Load();
    Firmware fw = ReadFirmware();
    if (!fw.present || fw.mux != 0) {
        Log("restore: nothing to do (firmware " + FwString(fw) + ")");
        return 0;
    }
    Rollback(s, fw, "restore requested");
    return 0;
}

int Controller::Status() {
    Firmware fw = ReadFirmware();
    State s = Load();
    std::string why = "ok";
    bool verified = StackVerified("nouveau", &why);
    printf("firmware=%s\nmode=%s\nboard=%s\nboard_allowed=%d\nnouveau_stack=%s\n%s", FwString(fw).c_str(),
           ModeName(ModeOf(fw)), Board().c_str(), BoardAllowed() ? 1 : 0, verified ? "verified" : why.c_str(),
           Serialize(s).c_str());
    return 0;
}

}  // namespace openbook::gfx
