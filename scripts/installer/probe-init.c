// SPDX-License-Identifier: Apache-2.0
// openbook-probe: a tiny rdinit= for boot-chain tests (ANAL-189). It runs as PID 1 before Android's first-stage
// init and records what the EFI loader handed the kernel. Every line goes to /dev/kmsg with a "PROBE" tag, so it
// lands in the serial log and in Android's dmesg:
//   - /proc/cmdline and /proc/bootconfig (the bootconfig trailer the loader appended to the initrd)
//   - which ramdisk fragments arrived (vendor ramdisk, generic ramdisk, module fragment)
//   - every block device: kernel name, sysfs path (USB vs NVMe), PARTNAME, PARTUUID from its uevent
//   - systemd-boot's LoaderDevicePartUUID EFI variable, when present
// Modes, chosen on the kernel cmdline:
//   (default)              exec /init so the same boot carries on into Android
//   openbook.probe=halt    power off instead
//   openbook.probe=report  hardware check for a real laptop: also record DMI, CPU and PCI facts, load the kernel
//                          modules shipped in /openbook-check/modules (skipping a safety list), record what bound,
//                          CPU frequency driver, sleep states, displays, battery, dGPU power state and temperatures,
//                          write report, verdicts (JSON) and kernel log to openbook/logs/ on the boot stick's ESP,
//                          then power off. It only ever mounts and writes the ESP whose PARTUUID is
//                          androidboot.boot_part_uuid, and only if that partition sits on a USB device.
//   openbook.probe.sleep=1 with report mode: also one suspend-to-idle cycle woken by the RTC after 20 s, with the
//                          stick unmounted while asleep; records time asleep, the AMD PMC s0ix counters, and the
//                          ACPI power states and power resources before and after (to map LPI constraint names).
//   openbook.probe.dgpu=detach  with report mode, before the sleep test: power the NVIDIA dGPU down for this boot
//                          the way an OpenBook image would without a driver (docs/nvidia.md section 1, option 2):
//                          unbind its HDMI-audio function, remove both functions from the PCI bus, and let the
//                          root port above them runtime-suspend (ACPI _PR3 turns the slot off). Nothing persists
//                          and no firmware setting changes. (openbook.probe.detach_vendor=0xNNNN: VM tests only.)
//   openbook.probe.acpi_d3cold=PATH[,PATH]  with report mode, before the sleep test: load the test-only module
//                          kmod/openbook_acpi_d3cold.c, which puts these ACPI device objects into D3cold if no device
//                          uses them (an ACPI object left on below an empty PCI port). For this boot only.
// Build: gcc -static -O2 -o openbook-probe probe-init.c
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/klog.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

static void say(const char *fmt, ...);

static int kmsg = -1;
static char *logbuf;  // everything said, kept for the report file
static size_t loglen, logcap;

static void keep(const char *s) {
    size_t n = strlen(s);
    if (loglen + n + 1 > logcap) {
        size_t cap = logcap ? logcap * 2 : 1 << 16;
        while (cap < loglen + n + 1) cap *= 2;
        char *p = realloc(logbuf, cap);
        if (!p) return;
        logbuf = p;
        logcap = cap;
    }
    memcpy(logbuf + loglen, s, n);
    loglen += n;
    logbuf[loglen] = 0;
}

static void say(const char *fmt, ...) {
    char buf[900];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    if (n < 0) return;
    if (n >= (int)sizeof buf) n = sizeof buf - 1;
    char out[1000];
    int m = snprintf(out, sizeof out, "<5>PROBE %s\n", buf);
    if (kmsg >= 0 && write(kmsg, out, m) < 0) { /* nothing else to do */ }
    keep(out + 3);
}

static int read_line(const char *path, char *out, size_t len) {
    out[0] = 0;
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    if (!fgets(out, len, f)) out[0] = 0;
    fclose(f);
    out[strcspn(out, "\n")] = 0;
    return 0;
}

static void dump_file(const char *tag, const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) { say("%s: %s missing (%s)", tag, path, strerror(errno)); return; }
    char line[800];
    int n = 0;
    while (fgets(line, sizeof line, f)) {
        line[strcspn(line, "\n")] = 0;
        say("%s| %s", tag, line);
        n++;
    }
    fclose(f);
    say("%s: %d line(s) from %s", tag, n, path);
}

static int exists(const char *p) { struct stat st; return stat(p, &st) == 0; }

// Value of androidboot.boot_part_uuid from /proc/bootconfig ('key = "value"') or /proc/cmdline ('key=value').
static void boot_part_uuid(char *out, size_t len) {
    char line[4096];
    out[0] = 0;
    FILE *f = fopen("/proc/bootconfig", "r");
    while (f && fgets(line, sizeof line, f)) {
        if (strncmp(line, "androidboot.boot_part_uuid", 26)) continue;
        char *q = strchr(line, '"');
        if (q) { snprintf(out, len, "%.36s", q + 1); fclose(f); return; }
    }
    if (f) fclose(f);
    f = fopen("/proc/cmdline", "r");
    if (f && fgets(line, sizeof line, f)) {
        char *k = strstr(line, "androidboot.boot_part_uuid=");
        if (k) snprintf(out, len, "%.36s", k + 27);
    }
    if (f) fclose(f);
}

// Find the block device whose uevent has KEY=want (KEY = PARTNAME or PARTUUID). Returns the count; the first
// match's kernel name goes to name (if not NULL).
static int find_uevent(const char *key, const char *want, char *name, size_t len) {
    DIR *d = opendir("/sys/class/block");
    if (!d) return 0;
    int hits = 0;
    struct dirent *e;
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        char p[512], line[256];
        snprintf(p, sizeof p, "/sys/class/block/%s/uevent", e->d_name);
        FILE *f = fopen(p, "r");
        if (!f) continue;
        while (fgets(line, sizeof line, f)) {
            line[strcspn(line, "\n")] = 0;
            size_t kl = strlen(key);
            if (!strncmp(line, key, kl) && line[kl] == '=' && !strcmp(line + kl + 1, want)) {
                if (!hits && name) snprintf(name, len, "%s", e->d_name);
                hits++;
            }
        }
        fclose(f);
    }
    closedir(d);
    return hits;
}

static void list_block(void) {
    DIR *d = opendir("/sys/class/block");
    if (!d) { say("block: no /sys/class/block"); return; }
    struct dirent *e;
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.' || !strncmp(e->d_name, "loop", 4) || !strncmp(e->d_name, "ram", 3) ||
            !strncmp(e->d_name, "zram", 4))
            continue;
        char p[512], link[512] = "", line[256], partname[80] = "-", partuuid[80] = "-";
        snprintf(p, sizeof p, "/sys/class/block/%s", e->d_name);
        ssize_t n = readlink(p, link, sizeof link - 1);
        if (n > 0) link[n] = 0;
        snprintf(p, sizeof p, "/sys/class/block/%s/uevent", e->d_name);
        FILE *f = fopen(p, "r");
        if (f) {
            while (fgets(line, sizeof line, f)) {
                line[strcspn(line, "\n")] = 0;
                if (!strncmp(line, "PARTNAME=", 9)) snprintf(partname, sizeof partname, "%.79s", line + 9);
                if (!strncmp(line, "PARTUUID=", 9)) snprintf(partuuid, sizeof partuuid, "%.79s", line + 9);
            }
            fclose(f);
        }
        // Trim "../../devices/" so the line shows the bus path (pci.../usb... vs pci.../nvme...).
        const char *path = strstr(link, "devices/") ? strstr(link, "devices/") + 8 : link;
        // Reports get shared: show partition UUIDs only for the USB stick, not the laptop's own disks.
        if (!strstr(link, "/usb") && strcmp(partuuid, "-")) snprintf(partuuid, sizeof partuuid, "[redacted]");
        say("block: %-10s partname=%-22s partuuid=%-36s %s", e->d_name, partname, partuuid, path);
    }
    closedir(d);
}

static void efivar(const char *name) {
    char p[256];
    snprintf(p, sizeof p, "/sys/firmware/efi/efivars/%s", name);
    FILE *f = fopen(p, "rb");
    if (!f) return;
    unsigned char raw[512];
    size_t n = fread(raw, 1, sizeof raw, f);
    fclose(f);
    // 4 bytes of attributes, then UTF-16LE text.
    char s[256];
    size_t j = 0;
    for (size_t i = 4; i + 1 < n && j + 1 < sizeof s; i += 2)
        if (raw[i]) s[j++] = raw[i];
    s[j] = 0;
    say("efivar: %s = %s", name, s);
}

// ------------------------------------------------------------------ report mode (real hardware)

// No serial numbers, UUIDs or asset tags: only model and firmware identity.
static void dmi_facts(void) {
    static const char *keys[] = {"sys_vendor", "product_name", "product_family", "product_version", "board_vendor",
                                 "board_name", "board_version", "bios_vendor", "bios_version", "bios_date", NULL};
    for (int i = 0; keys[i]; i++) {
        char p[128], v[256];
        snprintf(p, sizeof p, "/sys/class/dmi/id/%s", keys[i]);
        if (!read_line(p, v, sizeof v)) say("dmi: %s = %s", keys[i], v);
    }
}

static void cpu_facts(void) {
    FILE *f = fopen("/proc/cpuinfo", "r");
    char line[8192];
    int cpus = 0, shown = 0;
    while (f && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\n")] = 0;
        if (!strncmp(line, "processor", 9)) cpus++;
        if (!shown && !strncmp(line, "model name", 10)) say("cpu: %s", line);
        if (!shown && !strncmp(line, "flags", 5)) {
            say("cpu: avx_vnni=%s avx512_vnni=%s sev=%s", strstr(line, " avx_vnni") ? "yes" : "no",
                strstr(line, " avx512_vnni") ? "yes" : "no", strstr(line, " sev") ? "yes" : "no");
            shown = 1;
        }
    }
    if (f) fclose(f);
    say("cpu: %d logical CPUs", cpus);
    char v[256];
    FILE *m = fopen("/proc/meminfo", "r");
    if (m && fgets(v, sizeof v, m)) { v[strcspn(v, "\n")] = 0; say("mem: %s", v); }
    if (m) fclose(m);
}

static void pci_facts(const char *when) {
    DIR *d = opendir("/sys/bus/pci/devices");
    if (!d) return;
    struct dirent *e;
    int n = 0, bound = 0;
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        char p[256], ven[16] = "", dev[16] = "", cls[16] = "", drv[256] = "-";
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/vendor", e->d_name); read_line(p, ven, sizeof ven);
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/device", e->d_name); read_line(p, dev, sizeof dev);
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/class", e->d_name); read_line(p, cls, sizeof cls);
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/driver", e->d_name);
        char link[256];
        ssize_t l = readlink(p, link, sizeof link - 1);
        if (l > 0) { link[l] = 0; snprintf(drv, sizeof drv, "%s", strrchr(link, '/') ? strrchr(link, '/') + 1 : link); bound++; }
        char acpi[160] = "";  // the ACPI node this function belongs to, as named in the kernel's LPI messages
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/firmware_node/path", e->d_name); read_line(p, acpi, sizeof acpi);
        say("pci[%s]: %s %s:%s class %s driver %s%s%s", when, e->d_name, ven + 2, dev + 2, cls + 2, drv,
            acpi[0] ? " acpi " : "", acpi);
        n++;
    }
    closedir(d);
    say("pci[%s]: %d devices, %d with a driver", when, n, bound);
}

static void class_list(const char *cls) {
    char p[128];
    snprintf(p, sizeof p, "/sys/class/%s", cls);
    DIR *d = opendir(p);
    if (!d) { say("class %s: none", cls); return; }
    char names[1500] = "";
    struct dirent *e;
    int n = 0;
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        if (strlen(names) + strlen(e->d_name) + 2 < sizeof names) { strcat(names, " "); strcat(names, e->d_name); }
        n++;
    }
    closedir(d);
    say("class %s: %d:%s", cls, n, names);
}

// Input devices by name (keyboard, touchpad, lid switch, ...).
static void input_names(void) {
    DIR *d = opendir("/sys/class/input");
    if (!d) return;
    struct dirent *e;
    while ((e = readdir(d))) {
        if (strncmp(e->d_name, "input", 5)) continue;
        char p[256], v[256];
        snprintf(p, sizeof p, "/sys/class/input/%s/name", e->d_name);
        if (!read_line(p, v, sizeof v)) say("input: %s %s", e->d_name, v);
    }
    closedir(d);
}

// Kernel modules: load modules.load in order, dependencies first (modules.dep), skipping the blocklist and a
// safety list. No module parameters are passed.
#define MAXMOD 512
static char *mod_path[MAXMOD], *mod_deps[MAXMOD];
static int mod_state[MAXMOD], nmod;  // 0 = not tried, 1 = loading, 2 = done
static int loaded_ok, load_failed, skipped;

static const char *base(const char *p) { const char *s = strrchr(p, '/'); return s ? s + 1 : p; }

// Not loaded in the hardware check:
//   - cs35l56 speaker-amp drivers: they download DSP firmware and tuning to the amps; the check plays no audio,
//     and the speakers are validated separately (ANAL-179);
//   - asus-wmi and friends (hid-asus, asus-nb-wmi): they can change firmware-backed settings;
//   - KUnit and other test modules, which run self-tests on load.
static int unsafe(const char *name) {
    return strstr(name, "cs35l56") || strstr(name, "kunit") || strstr(name, "test") || !strcmp(name, "asus-wmi.ko") ||
           !strcmp(name, "asus-nb-wmi.ko") || !strcmp(name, "hid-asus.ko");
}

static int find_mod(const char *rel) {
    for (int i = 0; i < nmod; i++)
        if (!strcmp(mod_path[i], rel)) return i;
    return -1;
}

static int blocked(const char *dir, const char *name) {
    char p[512], line[256];
    snprintf(p, sizeof p, "%s/modules.blocklist", dir);
    FILE *f = fopen(p, "r");
    int b = 0;
    while (f && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\n")] = 0;
        if (!strncmp(line, "blocklist ", 10) && !strcmp(line + 10, name)) b = 1;
    }
    if (f) fclose(f);
    return b;
}

static int load_mod(const char *dir, int i, int depth) {
    if (mod_state[i] == 2) return 0;
    if (mod_state[i] == 1 || depth > 32) return 0;
    mod_state[i] = 1;
    const char *name = base(mod_path[i]);
    if (unsafe(name) || blocked(dir, name)) {
        say("module %s: skipped (%s)", name, unsafe(name) ? "safety list" : "blocklist");
        skipped++;
        mod_state[i] = 2;
        return -1;
    }
    // Dependencies first.
    char deps[4096];
    snprintf(deps, sizeof deps, "%s", mod_deps[i] ? mod_deps[i] : "");
    char *save = NULL;  // strtok_r: this function recurses
    for (char *t = strtok_r(deps, " ", &save); t; t = strtok_r(NULL, " ", &save)) {
        int j = find_mod(t);
        if (j >= 0) load_mod(dir, j, depth + 1);
    }
    char p[512];
    snprintf(p, sizeof p, "%s/%s", dir, mod_path[i]);
    int fd = open(p, O_RDONLY | O_CLOEXEC);
    long r = fd < 0 ? -1 : syscall(SYS_finit_module, fd, "", 0);
    int err = errno;
    if (fd >= 0) close(fd);
    if (r == 0) { loaded_ok++; say("module %s: loaded", name); }
    else if (err == EEXIST) say("module %s: already loaded", name);
    else { load_failed++; say("module %s: FAILED (%s)", name, strerror(err)); }
    mod_state[i] = 2;
    return r == 0 ? 0 : -1;
}

static void load_modules(const char *dir) {
    char p[512], line[8192];
    snprintf(p, sizeof p, "%s/modules.dep", dir);
    FILE *f = fopen(p, "r");
    if (!f) { say("modules: no %s", p); return; }
    while (nmod < MAXMOD && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\n")] = 0;
        char *colon = strchr(line, ':');
        if (!colon) continue;
        *colon = 0;
        mod_path[nmod] = strdup(line);
        mod_deps[nmod] = strdup(colon[1] == ' ' ? colon + 2 : colon + 1);
        nmod++;
    }
    fclose(f);
    snprintf(p, sizeof p, "%s/modules.load", dir);
    f = fopen(p, "r");
    if (!f) { say("modules: no %s", p); return; }
    say("modules: %d known, loading in modules.load order", nmod);
    while (fgets(line, sizeof line, f)) {
        line[strcspn(line, "\n")] = 0;
        int i = find_mod(line);
        if (i >= 0) load_mod(dir, i, 0);
    }
    fclose(f);
    say("modules: %d loaded, %d failed, %d skipped", loaded_ok, load_failed, skipped);
}

static int write_all(const char *path, const char *data, size_t len) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
    if (fd < 0) return -1;
    size_t off = 0;
    while (off < len) {
        ssize_t w = write(fd, data + off, len - off);
        if (w <= 0) break;
        off += w;
    }
    fsync(fd);
    close(fd);
    return off == len ? 0 : -1;
}

static char esp_node[96];  // block node of the boot stick's ESP, made by mount_esp()

static int esp_mount(void) {
    return mount(esp_node, "/ob-esp", "vfat", MS_NOATIME | MS_NODEV | MS_NOEXEC | MS_NOSUID, "");
}

// Mount the boot stick's ESP (PARTUUID = boot_part_uuid, and only on USB). Returns 0 and fills the report paths.
static int mount_esp(const char *uuid, char *report, char *dmesg, char *json, size_t len) {
    char name[64] = "", p[512], link[512] = "";
    if (!uuid[0] || !find_uevent("PARTUUID", uuid, name, sizeof name)) { say("report: boot ESP not found"); return -1; }
    snprintf(p, sizeof p, "/sys/class/block/%s", name);
    ssize_t n = readlink(p, link, sizeof link - 1);
    if (n > 0) link[n] = 0;
    if (!strstr(link, "/usb")) { say("report: boot ESP %s is not on USB; refusing to write", name); return -1; }
    // GKI has no devtmpfs (first-stage init makes its own nodes), so make the node from sysfs "major:minor".
    char devno[32] = "";
    unsigned maj = 0, min = 0;
    snprintf(p, sizeof p, "/sys/class/block/%s/dev", name);
    if (read_line(p, devno, sizeof devno) || sscanf(devno, "%u:%u", &maj, &min) != 2) {
        say("report: no dev number for %s", name);
        return -1;
    }
    snprintf(p, sizeof p, "/dev/ob-esp-%s", name);
    snprintf(esp_node, sizeof esp_node, "%s", p);
    unlink(p);
    if (mknod(p, S_IFBLK | 0600, makedev(maj, min))) { say("report: mknod %s failed (%s)", p, strerror(errno)); return -1; }
    mkdir("/ob-esp", 0700);
    if (esp_mount()) {
        int err = errno;
        say("report: mount %s failed (%s); node %s, mountpoint %s", p, strerror(err), exists(p) ? "present" : "missing",
            exists("/ob-esp") ? "present" : "missing");
        return -1;
    }
    mkdir("/ob-esp/openbook", 0755);
    mkdir("/ob-esp/openbook/logs", 0755);
    for (int i = 1; i < 1000; i++) {
        snprintf(report, len, "/ob-esp/openbook/logs/hwcheck-%03d.txt", i);
        if (!exists(report)) {
            snprintf(dmesg, len, "/ob-esp/openbook/logs/hwcheck-%03d-dmesg.txt", i);
            snprintf(json, len, "/ob-esp/openbook/logs/hwcheck-%03d.json", i);
            say("report: writing %s on %s (USB)", report + 7, name);
            return 0;
        }
    }
    return -1;
}

static void save_report(const char *report) {
    if (report[0] && write_all(report, logbuf ? logbuf : "", loglen))
        say("report: write failed (%s)", strerror(errno));
}

static void save_dmesg(const char *path) {
    int size = klogctl(10 /* SYSLOG_ACTION_SIZE_BUFFER */, NULL, 0);
    if (size <= 0) size = 1 << 20;
    char *buf = malloc(size);
    if (!buf) return;
    int n = klogctl(3 /* SYSLOG_ACTION_READ_ALL */, buf, size);
    // Reports get shared: blank USB device serial numbers (root hubs show a PCI address; keep those).
    for (char *q = buf; n > 0 && (q = memmem(q, buf + n - q, "SerialNumber: ", 14)); q += 14) {
        char *v = q + 14;
        if (!strncmp(v, "0000:", 5)) continue;
        for (; v < buf + n && *v != '\n'; v++) *v = 'x';
    }
    if (n > 0) write_all(path, buf, n);
    free(buf);
}

// ------------------------------------------------------------------ v2 facts

static void sys_say(const char *tag, const char *path) {
    char v[512];
    if (!read_line(path, v, sizeof v)) say("%s: %s", tag, v);
}

static void cpufreq_facts(void) {
    sys_say("cpufreq: driver", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver");
    sys_say("cpufreq: governor", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor");
    sys_say("cpufreq: epp", "/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference");
    sys_say("cpufreq: epp choices", "/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_available_preferences");
    sys_say("cpufreq: max kHz", "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq");
    sys_say("cpufreq: amd_pstate status", "/sys/devices/system/cpu/amd_pstate/status");
    sys_say("power: state", "/sys/power/state");
    sys_say("power: mem_sleep", "/sys/power/mem_sleep");
}

static int edp_connected;
static void display_facts(void) {
    DIR *d = opendir("/sys/class/drm");
    if (!d) return;
    struct dirent *e;
    while ((e = readdir(d))) {
        if (strncmp(e->d_name, "card", 4) || !strchr(e->d_name, '-')) continue;
        char p[256], st[32] = "", en[32] = "", mode[64] = "";
        snprintf(p, sizeof p, "/sys/class/drm/%s/status", e->d_name); read_line(p, st, sizeof st);
        if (!strcmp(st, "unknown")) {  // nothing has probed the connector yet (no DRM client): ask for a probe
            int fd = open(p, O_WRONLY);
            if (fd >= 0) { if (write(fd, "detect", 6) < 0) { /* keep "unknown" */ } close(fd); }
            read_line(p, st, sizeof st);
        }
        if (strcmp(st, "connected")) continue;
        snprintf(p, sizeof p, "/sys/class/drm/%s/enabled", e->d_name); read_line(p, en, sizeof en);
        snprintf(p, sizeof p, "/sys/class/drm/%s/modes", e->d_name); read_line(p, mode, sizeof mode);
        say("display: %s connected, %s, preferred mode %s", e->d_name, en, mode[0] ? mode : "-");
        if (strstr(e->d_name, "eDP")) edp_connected = 1;
    }
    closedir(d);
    sys_say("backlight: max", "/sys/class/backlight/amdgpu_bl0/max_brightness");
    sys_say("backlight: actual", "/sys/class/backlight/amdgpu_bl0/actual_brightness");
}

// No serial number.
static void battery_facts(void) {
    static const char *keys[] = {"status", "capacity", "energy_full_design", "energy_full", "energy_now",
                                 "charge_full_design", "charge_full", "cycle_count", "technology", "manufacturer",
                                 "model_name", "power_now", NULL};
    for (int i = 0; keys[i]; i++) {
        char p[128], tag[64];
        snprintf(p, sizeof p, "/sys/class/power_supply/BAT1/%s", keys[i]);
        snprintf(tag, sizeof tag, "battery: %s", keys[i]);
        sys_say(tag, p);
    }
    sys_say("ac: online", "/sys/class/power_supply/ACAD/online");
}

static char dgpu_state[64] = "absent";
static void dgpu_facts(void) {
    DIR *d = opendir("/sys/bus/pci/devices");
    if (!d) return;
    struct dirent *e;
    while ((e = readdir(d))) {
        char p[256], ven[16] = "", cls[16] = "", ps[32] = "-", rt[32] = "-", drv[128] = "-", link[256];
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/vendor", e->d_name);
        if (read_line(p, ven, sizeof ven) || strcmp(ven, "0x10de")) continue;
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/class", e->d_name); read_line(p, cls, sizeof cls);
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/power_state", e->d_name); read_line(p, ps, sizeof ps);
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/power/runtime_status", e->d_name); read_line(p, rt, sizeof rt);
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/driver", e->d_name);
        ssize_t l = readlink(p, link, sizeof link - 1);
        if (l > 0) { link[l] = 0; snprintf(drv, sizeof drv, "%s", strrchr(link, '/') + 1); }
        say("dgpu: %s class %s power_state %s runtime %s driver %s", e->d_name, cls + 2, ps, rt, drv);
        if (!strncmp(cls, "0x03", 4)) snprintf(dgpu_state, sizeof dgpu_state, "%s/%s", ps, rt);
    }
    closedir(d);
}

static void thermal_facts(void) {
    DIR *d = opendir("/sys/class/thermal");
    if (!d) return;
    struct dirent *e;
    while ((e = readdir(d))) {
        if (strncmp(e->d_name, "thermal_zone", 12)) continue;
        char p[256], ty[64] = "", t[32] = "";
        snprintf(p, sizeof p, "/sys/class/thermal/%s/type", e->d_name); read_line(p, ty, sizeof ty);
        snprintf(p, sizeof p, "/sys/class/thermal/%s/temp", e->d_name); read_line(p, t, sizeof t);
        say("thermal: %s %s %.1f C", e->d_name, ty, atoi(t) / 1000.0);
    }
    closedir(d);
}

static int input_has(const char *word) {
    DIR *d = opendir("/sys/class/input");
    if (!d) return 0;
    struct dirent *e;
    int hit = 0;
    while (!hit && (e = readdir(d))) {
        char p[256], v[256];
        snprintf(p, sizeof p, "/sys/class/input/%s/name", e->d_name);
        if (!read_line(p, v, sizeof v) && strcasestr(v, word)) hit = 1;
    }
    closedir(d);
    return hit;
}

static int pci_driver_bound(const char *driver) {
    char p[256];
    snprintf(p, sizeof p, "/sys/bus/pci/drivers/%s", driver);
    DIR *d = opendir(p);
    if (!d) return 0;
    struct dirent *e;
    int n = 0;
    while ((e = readdir(d))) if (strchr(e->d_name, ':')) n++;
    closedir(d);
    return n;
}

static int count_prefix(const char *dir, const char *prefix) {
    DIR *d = opendir(dir);
    if (!d) return 0;
    struct dirent *e;
    int n = 0;
    while ((e = readdir(d))) if (!strncmp(e->d_name, prefix, strlen(prefix))) n++;
    closedir(d);
    return n;
}

static char sleep_json[512] = "null";
static char detach_json[512] = "null";
static char acpi_json[256] = "null";

static void write_json(const char *path) {
    char board[128] = "", bios[128] = "", cpu[160] = "", drv[64] = "", ms[128] = "", line[512];
    read_line("/sys/class/dmi/id/board_name", board, sizeof board);
    read_line("/sys/class/dmi/id/bios_version", bios, sizeof bios);
    read_line("/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver", drv, sizeof drv);
    read_line("/sys/power/mem_sleep", ms, sizeof ms);
    FILE *f = fopen("/proc/cpuinfo", "r");
    while (f && fgets(line, sizeof line, f))
        if (!strncmp(line, "model name", 10)) { snprintf(cpu, sizeof cpu, "%s", strchr(line, ':') + 2); cpu[strcspn(cpu, "\n")] = 0; break; }
    if (f) fclose(f);
    char j[4096];
    int n = snprintf(j, sizeof j,
        "{\n \"schema\": \"openbook-hwcheck/5\",\n \"board\": \"%s\",\n \"bios\": \"%s\",\n \"cpu\": \"%s\",\n"
        " \"modules\": {\"loaded\": %d, \"failed\": %d, \"skipped\": %d},\n"
        " \"checks\": {\n  \"gpu_amdgpu\": %s,\n  \"edp_connected\": %s,\n  \"wifi_wlan0\": %s,\n"
        "  \"bluetooth_hci0\": %s,\n  \"touchpad\": %s,\n  \"keyboard\": %s,\n  \"lid_switch\": %s,\n"
        "  \"battery\": %s,\n  \"npu_accel\": %s,\n  \"usb4_thunderbolt\": %s,\n  \"typec_ports\": %d,\n"
        "  \"sound_cards\": %d,\n  \"cpufreq_driver\": \"%s\",\n  \"mem_sleep\": \"%s\",\n"
        "  \"dgpu_power\": \"%s\"\n },\n \"dgpu_detach\": %s,\n \"acpi_d3cold\": %s,\n \"sleep_test\": %s\n}\n",
        board, bios, cpu, loaded_ok, load_failed, skipped,
        pci_driver_bound("amdgpu") ? "true" : "false", edp_connected ? "true" : "false",
        exists("/sys/class/net/wlan0") ? "true" : "false", exists("/sys/class/bluetooth/hci0") ? "true" : "false",
        input_has("Touchpad") ? "true" : "false", input_has("Keyboard") ? "true" : "false",
        input_has("Lid Switch") ? "true" : "false", exists("/sys/class/power_supply/BAT1") ? "true" : "false",
        exists("/sys/class/accel/accel0") ? "true" : "false", pci_driver_bound("thunderbolt") ? "true" : "false",
        count_prefix("/sys/class/typec", "port"), count_prefix("/sys/class/sound", "card"), drv, ms, dgpu_state,
        detach_json, acpi_json, sleep_json);
    if (n > 0) write_all(path, j, n < (int)sizeof j ? n : (int)sizeof j - 1);
}

static long read_long(const char *path) {
    char v[64];
    return read_line(path, v, sizeof v) ? -1 : atol(v);
}

static long s0ix_residency(void) {
    FILE *f = fopen("/sys/kernel/debug/amd_pmc/s0ix_stats", "r");
    char line[256];
    long v = -1;
    while (f && fgets(line, sizeof line, f))
        if (!strncmp(line, "Residency Time:", 15)) v = atol(line + 15);
    if (f) fclose(f);
    return v;
}

// PCI devices that are not in D3 right before suspend, with their drivers: the candidates that block s0ix.
static void awake_devices(const char *when) {
    DIR *d = opendir("/sys/bus/pci/devices");
    if (!d) return;
    struct dirent *e;
    int n = 0;
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        char p[256], ps[32] = "", rt[32] = "", drv[128] = "-", link[256];
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/power_state", e->d_name);
        if (read_line(p, ps, sizeof ps) || !strncmp(ps, "D3", 2)) continue;
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/power/runtime_status", e->d_name); read_line(p, rt, sizeof rt);
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/driver", e->d_name);
        ssize_t l = readlink(p, link, sizeof link - 1);
        if (l > 0) { link[l] = 0; snprintf(drv, sizeof drv, "%s", strrchr(link, '/') + 1); }
        say("awake[%s]: %s %s runtime %s driver %s", when, e->d_name, ps, rt, drv);
        n++;
    }
    closedir(d);
    say("awake[%s]: %d PCI functions not in D3", when, n);
}

// The ACPI side of the same question: every power-manageable ACPI device (state, and the device it belongs to) and
// every ACPI power resource the kernel holds on. Unmet LPI constraints in the kernel log name these ACPI paths.
static void acpi_power(const char *when) {
    DIR *d = opendir("/sys/bus/acpi/devices");
    if (!d) return;
    struct dirent *e;
    int n = 0, on = 0;
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        char p[320], path[160] = "", ps[32] = "", rps[32] = "", use[8] = "", phys[64] = "-", link[256];
        snprintf(p, sizeof p, "/sys/bus/acpi/devices/%s/path", e->d_name);
        if (read_line(p, path, sizeof path)) continue;
        if (!strncmp(e->d_name, "LNXPOWER", 8)) {
            snprintf(p, sizeof p, "/sys/bus/acpi/devices/%s/resource_in_use", e->d_name); read_line(p, use, sizeof use);
            say("acpi-power[%s]: resource %s %s", when, path, strcmp(use, "1") ? "off" : "ON");
            on += !strcmp(use, "1");
            continue;
        }
        snprintf(p, sizeof p, "/sys/bus/acpi/devices/%s/power_state", e->d_name);
        if (read_line(p, ps, sizeof ps)) continue;  // not power-manageable
        snprintf(p, sizeof p, "/sys/bus/acpi/devices/%s/real_power_state", e->d_name); read_line(p, rps, sizeof rps);
        snprintf(p, sizeof p, "/sys/bus/acpi/devices/%s/physical_node", e->d_name);
        ssize_t l = readlink(p, link, sizeof link - 1);
        if (l > 0) { link[l] = 0; snprintf(phys, sizeof phys, "%s", strrchr(link, '/') ? strrchr(link, '/') + 1 : link); }
        say("acpi-power[%s]: %s %s real %s device %s", when, path, ps, rps[0] ? rps : "-", phys);
        n++;
    }
    closedir(d);
    say("acpi-power[%s]: %d power-manageable devices, %d power resources on", when, n, on);
}

// Put unused ACPI device objects into D3cold for this boot (see the header), then let the parent bridge that the
// module held awake runtime-suspend again. The module logs each path's outcome to the kernel log.
static void acpi_d3cold(const char *paths) {
    char params[192];
    snprintf(params, sizeof params, "paths=%s", paths);
    int fd = open("/openbook-check/kmod/openbook_acpi_d3cold.ko", O_RDONLY | O_CLOEXEC);
    long r = fd < 0 ? -1 : syscall(SYS_finit_module, fd, params, 0);
    int err = errno;
    if (fd >= 0) close(fd);
    say("acpi-d3cold: load openbook_acpi_d3cold.ko %s: %s", params, r ? strerror(err) : "ok");
    sleep(2);
    snprintf(acpi_json, sizeof acpi_json, "{\"ran\": true, \"paths\": \"%s\", \"load_rc\": %d}", paths, r ? -err : 0);
}

static int write_str(const char *path, const char *v) {
    int fd = open(path, O_WRONLY);
    if (fd < 0) return -1;
    int r = write(fd, v, strlen(v)) < 0 ? -1 : 0;
    close(fd);
    return r;
}

// Power the dGPU down for this boot only (see the header). Functions are removed highest first.
static void detach_dgpu(const char *vendor) {
    DIR *d = opendir("/sys/bus/pci/devices");
    if (!d) return;
    char fns[8][64];
    int n = 0;
    struct dirent *e;
    while ((e = readdir(d)) && n < 8) {
        char p[256], ven[16] = "";
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/vendor", e->d_name);
        if (!read_line(p, ven, sizeof ven) && !strcmp(ven, vendor)) snprintf(fns[n++], sizeof fns[0], "%s", e->d_name);
    }
    closedir(d);
    if (!n) { say("dgpu-detach: no %s functions found", vendor); snprintf(detach_json, sizeof detach_json, "{\"ran\": false}"); return; }
    for (int i = 0; i < n; i++)  // sort descending so function .1 goes before .0
        for (int j = i + 1; j < n; j++)
            if (strcmp(fns[i], fns[j]) < 0) { char t[64]; memcpy(t, fns[i], 64); memcpy(fns[i], fns[j], 64); memcpy(fns[j], t, 64); }
    char p[256], link[512] = "", bridge[64] = "", before[32] = "?", after[32] = "?";
    snprintf(p, sizeof p, "/sys/bus/pci/devices/%s", fns[0]);
    ssize_t l = readlink(p, link, sizeof link - 1);
    if (l > 0) {
        link[l] = 0;
        char *slash = strrchr(link, '/');
        if (slash) { *slash = 0; snprintf(bridge, sizeof bridge, "%s", strrchr(link, '/') ? strrchr(link, '/') + 1 : link); }
    }
    snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/power_state", bridge); read_line(p, before, sizeof before);
    say("dgpu-detach: %d function(s) behind bridge %s (bridge %s)", n, bridge, before);
    for (int i = 0; i < n; i++) {
        char link2[256];
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/driver", fns[i]);
        ssize_t k = readlink(p, link2, sizeof link2 - 1);
        if (k > 0) {
            snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/driver/unbind", fns[i]);
            say("dgpu-detach: unbind %s: %s", fns[i], write_str(p, fns[i]) ? strerror(errno) : "ok");
        }
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/power/control", fns[i]); write_str(p, "auto");
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/remove", fns[i]);
        say("dgpu-detach: remove %s: %s", fns[i], write_str(p, "1") ? strerror(errno) : "ok");
    }
    if (bridge[0]) {
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/power/control", bridge);
        say("dgpu-detach: bridge %s runtime PM auto: %s", bridge, write_str(p, "auto") ? strerror(errno) : "ok");
        // Wait (max 10 s) until the bridge has finished runtime-suspending, then record where it ended up.
        char rt[32] = "", q[256], d3c[16] = "?";
        snprintf(q, sizeof q, "/sys/bus/pci/devices/%s/power/runtime_status", bridge);
        for (int i = 0; i < 100; i++) { read_line(q, rt, sizeof rt); if (!strcmp(rt, "suspended")) break; usleep(100000); }
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/power_state", bridge); read_line(p, after, sizeof after);
        snprintf(p, sizeof p, "/sys/bus/pci/devices/%s/d3cold_allowed", bridge); read_line(p, d3c, sizeof d3c);
        say("dgpu-detach: bridge %s now %s (runtime %s, d3cold_allowed %s)", bridge, after, rt, d3c);
    }
    snprintf(detach_json, sizeof detach_json,
             "{\"ran\": true, \"functions\": %d, \"bridge\": \"%s\", \"bridge_before\": \"%s\", \"bridge_after\": \"%s\"}",
             n, bridge, before, after);
}

// One s2idle cycle, woken by the RTC. The stick is unmounted while the machine sleeps.
static void sleep_test(void) {
    mkdir("/sys/kernel/debug", 0700);
    mount("debugfs", "/sys/kernel/debug", "debugfs", 0, NULL);
    dump_file("pmc-before", "/sys/kernel/debug/amd_pmc/s0ix_stats");
    dump_file("pmc-fw", "/sys/kernel/debug/amd_pmc/smu_fw_info");
    dump_file("pmc-idlemask", "/sys/kernel/debug/amd_pmc/amd_pmc_idlemask");
    // Let the kernel explain the sleep in its log: LPS0 _DSM calls, active GPIOs, device timings (PM_SLEEP_DEBUG).
    say("sleep: pm_debug_messages on: %s", write_str("/sys/power/pm_debug_messages", "1") ? strerror(errno) : "ok");
    static const char *dyn[] = {"module amd_pmc +p", "module pinctrl_amd +p", "file drivers/acpi/x86/s2idle.c +p", NULL};
    for (int i = 0; dyn[i]; i++)
        if (!write_str("/sys/kernel/debug/dynamic_debug/control", dyn[i])) say("sleep: dynamic debug '%s' on", dyn[i]);
    long res0 = s0ix_residency();
    awake_devices("before-suspend");
    acpi_power("before-suspend");
    long ok0 = read_long("/sys/power/suspend_stats/success"), fail0 = read_long("/sys/power/suspend_stats/fail");
    int fd = open("/sys/class/rtc/rtc0/wakealarm", O_WRONLY);
    if (fd < 0 || write(fd, "0", 1) < 0 || (close(fd), fd = open("/sys/class/rtc/rtc0/wakealarm", O_WRONLY)) < 0 ||
        write(fd, "+20", 3) < 0) {
        say("sleep: cannot set the RTC wake alarm (%s); skipping the sleep test", strerror(errno));
        if (fd >= 0) close(fd);
        snprintf(sleep_json, sizeof sleep_json, "{\"ran\": false, \"reason\": \"no rtc wakealarm\"}");
        return;
    }
    close(fd);
    char ms[128] = "";
    read_line("/sys/power/mem_sleep", ms, sizeof ms);
    say("sleep: RTC alarm in 20 s; suspending (mem_sleep: %s)", ms);
    sync();
    struct timespec m0, b0, m1, b1;
    clock_gettime(CLOCK_MONOTONIC, &m0);
    clock_gettime(CLOCK_BOOTTIME, &b0);
    fd = open("/sys/power/state", O_WRONLY);
    int rc = fd < 0 ? -1 : (int)write(fd, "mem", 3);
    int err = errno;
    if (fd >= 0) close(fd);
    clock_gettime(CLOCK_MONOTONIC, &m1);
    clock_gettime(CLOCK_BOOTTIME, &b1);
    double asleep = ((b1.tv_sec - b0.tv_sec) + (b1.tv_nsec - b0.tv_nsec) / 1e9) -
                    ((m1.tv_sec - m0.tv_sec) + (m1.tv_nsec - m0.tv_nsec) / 1e9);
    long ok1 = read_long("/sys/power/suspend_stats/success"), fail1 = read_long("/sys/power/suspend_stats/fail");
    say("sleep: write returned %d (%s); asleep %.1f s; suspend_stats success %ld->%ld fail %ld->%ld", rc,
        rc < 0 ? strerror(err) : "ok", asleep, ok0, ok1, fail0, fail1);
    sys_say("sleep: last failed dev", "/sys/power/suspend_stats/last_failed_dev");
    sys_say("sleep: last failed errno", "/sys/power/suspend_stats/last_failed_errno");
    dump_file("pmc-after", "/sys/kernel/debug/amd_pmc/s0ix_stats");
    dump_file("pmc-fw-after", "/sys/kernel/debug/amd_pmc/smu_fw_info");
    dump_file("pmc-idlemask-after", "/sys/kernel/debug/amd_pmc/amd_pmc_idlemask");
    dump_file("wakeup-sources", "/sys/kernel/debug/wakeup_sources");
    acpi_power("after-resume");
    write_str("/sys/power/pm_debug_messages", "0");
    long res1 = s0ix_residency();
    say("sleep: s0ix residency %ld us (%s)", res1 >= 0 && res0 >= 0 ? res1 - res0 : -1,
        res0 < 0 || res1 < 0 ? "unknown: no AMD PMC counters"
                             : res1 > res0 ? "reached the deepest state" : "did NOT reach the deepest state");
    char st[32] = "";
    read_line("/sys/class/drm/card0-eDP-1/status", st, sizeof st);
    say("sleep: after resume eDP-1 %s, wlan0 %s", st[0] ? st : "?", exists("/sys/class/net/wlan0") ? "present" : "missing");
    snprintf(sleep_json, sizeof sleep_json,
             "{\"ran\": true, \"write_rc\": %d, \"asleep_s\": %.1f, \"suspend_success_delta\": %ld, "
             "\"suspend_fail_delta\": %ld, \"s0ix_residency_us\": %ld, \"edp_after\": \"%s\"}",
             rc, asleep, ok1 - ok0, fail1 - fail0, res1 >= 0 && res0 >= 0 ? res1 - res0 : -1, st);
    umount("/sys/kernel/debug");
}

static void hardware_check(const char *uuid) {
    char report[256] = "", dmesg[256] = "", json[256] = "", cmdline[4096] = "";
    read_line("/proc/cmdline", cmdline, sizeof cmdline);
    int want_sleep = strstr(cmdline, "openbook.probe.sleep=1") != NULL;
    int want_detach = strstr(cmdline, "openbook.probe.dgpu=detach") != NULL;
    char vendor[16] = "0x10de";
    char *dv = strstr(cmdline, "openbook.probe.detach_vendor=");
    if (dv) sscanf(dv + 29, "%15[0-9a-fx]", vendor);
    say("hwcheck: OpenBook hardware check v6%s%s. Writes only to the boot stick, then powers off.",
        want_sleep ? " with a sleep test" : "", want_detach ? " (dGPU powered down first)" : "");
    dmi_facts();
    cpu_facts();
    pci_facts("before");
    int have_esp = mount_esp(uuid, report, dmesg, json, sizeof report) == 0;
    if (have_esp) save_report(report);  // early copy, in case a driver hangs the machine

    char rel[128] = "", dir[256];
    read_line("/proc/sys/kernel/osrelease", rel, sizeof rel);
    snprintf(dir, sizeof dir, "/openbook-check/modules/%s", rel);
    if (exists(dir)) load_modules(dir); else say("modules: %s missing; built-in drivers only", dir);
    if (have_esp) save_report(report);

    say("hwcheck: waiting 10 s for drivers to finish probing (firmware loads are asynchronous)");
    sleep(10);
    pci_facts("after");
    static const char *classes[] = {"drm", "net", "bluetooth", "sound", "backlight", "power_supply", "hwmon",
                                    "thermal", "i2c-dev", "accel", "typec", "rtc", NULL};
    for (int i = 0; classes[i]; i++) class_list(classes[i]);
    input_names();
    cpufreq_facts();
    display_facts();
    battery_facts();
    dgpu_facts();
    thermal_facts();
    if (have_esp) { save_report(report); write_json(json); save_dmesg(dmesg); }
    if (want_detach) {
        if (want_sleep) acpi_power("before-detach");
        detach_dgpu(vendor);
        dgpu_facts();
        if (have_esp) { save_report(report); write_json(json); }
    }
    char *ad = strstr(cmdline, "openbook.probe.acpi_d3cold="), paths[160] = "";
    if (ad && sscanf(ad + 27, "%159[A-Za-z0-9_.,]", paths) == 1) {
        acpi_d3cold(paths);
        if (have_esp) { save_report(report); write_json(json); }
    }
    if (want_sleep) {
        if (have_esp) { sync(); umount("/ob-esp"); }
        sleep_test();
        sleep(3);  // let USB storage come back
        if (have_esp) {
            int ok = 0;
            for (int i = 0; i < 50 && !(ok = !esp_mount()); i++) usleep(200000);
            if (!ok) { have_esp = 0; say("sleep: could not remount the stick after resume (%s)", strerror(errno)); }
        }
        thermal_facts();
    }
    say("hwcheck: done");
    if (have_esp) {
        save_report(report);
        write_json(json);
        save_dmesg(dmesg);
        umount("/ob-esp");
        say("hwcheck: report saved; powering off");
    }
}

int main(int argc, char **argv) {
    (void)argc;
    mkdir("/dev", 0755);
    mkdir("/proc", 0555);
    mkdir("/sys", 0555);
    mount("devtmpfs", "/dev", "devtmpfs", 0, NULL);
    mount("proc", "/proc", "proc", 0, NULL);
    mount("sysfs", "/sys", "sysfs", 0, NULL);
    kmsg = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);

    say("openbook-probe start (pid %d)", getpid());
    dump_file("cmdline", "/proc/cmdline");
    dump_file("bootconfig", "/proc/bootconfig");

    say("ramdisk: vendor ramdisk fstab %s",
        exists("/first_stage_ramdisk/system/etc/fstab.cf.f2fs.hctr2") ? "present" : "MISSING");
    say("ramdisk: generic ramdisk /init %s, /system/bin/snapuserd %s", exists("/init") ? "present" : "MISSING",
        exists("/system/bin/snapuserd") ? "present" : "missing");
    char rel[128] = "";
    read_line("/proc/sys/kernel/osrelease", rel, sizeof rel);
    char mp[256];
    snprintf(mp, sizeof mp, "/lib/modules/%s/modules.load", rel);
    say("ramdisk: kernel %s, release module dir %s", rel, exists(mp) ? "present" : "MISSING");

    // USB mass storage enumerates asynchronously. Like Android's ueventd, wait (max 20 s) for the partition whose
    // PARTUUID is androidboot.boot_part_uuid; without one, for a partition named "super".
    char uuid[64];
    boot_part_uuid(uuid, sizeof uuid);
    const char *key = uuid[0] ? "PARTUUID" : "PARTNAME", *want = uuid[0] ? uuid : "super";
    struct timespec t0, t;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    int found = 0;
    for (int i = 0; i < 200 && !(found = find_uevent(key, want, NULL, 0)); i++) usleep(100000);
    clock_gettime(CLOCK_MONOTONIC, &t);
    say("block: %d partition(s) with %s=%s after %.1f s", found, key, want,
        (t.tv_sec - t0.tv_sec) + (t.tv_nsec - t0.tv_nsec) / 1e9);
    usleep(500000);  // let the rest of that disk's partitions register
    list_block();

    if (exists("/sys/firmware/efi")) {
        say("efi: booted via UEFI");
        mount("efivarfs", "/sys/firmware/efi/efivars", "efivarfs", MS_RDONLY, NULL);
        efivar("LoaderDevicePartUUID-4a67b082-0a4c-41cf-b6c7-440b29bb8c4f");
        efivar("LoaderInfo-4a67b082-0a4c-41cf-b6c7-440b29bb8c4f");
        efivar("LoaderEntrySelected-4a67b082-0a4c-41cf-b6c7-440b29bb8c4f");
        efivar("StubInfo-4a67b082-0a4c-41cf-b6c7-440b29bb8c4f");
        umount("/sys/firmware/efi/efivars");
    } else {
        say("efi: NOT booted via UEFI");
    }

    char cmdline[4096] = "";
    FILE *c = fopen("/proc/cmdline", "r");
    if (c) { if (!fgets(cmdline, sizeof cmdline, c)) cmdline[0] = 0; fclose(c); }
    if (strstr(cmdline, "openbook.probe=report")) {
        hardware_check(uuid);
        sync();
        reboot(RB_POWER_OFF);
        return 0;
    }
    if (strstr(cmdline, "openbook.probe=halt")) {
        say("openbook-probe done: halt requested, powering off");
        sync();
        reboot(RB_POWER_OFF);
        return 0;
    }

    say("openbook-probe done: exec /init");
    if (kmsg >= 0) close(kmsg);
    umount("/sys");
    umount("/proc");
    umount("/dev");
    argv[0] = (char *)"/init";
    execv("/init", argv);
    return 127;
}
