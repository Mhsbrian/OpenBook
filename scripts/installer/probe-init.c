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
//                          write report + kernel log to openbook/logs/ on the boot stick's ESP, then power off.
//                          It only ever mounts and writes the ESP whose PARTUUID is androidboot.boot_part_uuid,
//                          and only if that partition sits on a USB device. Nothing else is written.
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
        say("pci[%s]: %s %s:%s class %s driver %s", when, e->d_name, ven + 2, dev + 2, cls + 2, drv);
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
//   - cs35l56 speaker-amp drivers: they download DSP firmware to the amps and there is no tuning file for this
//     laptop (10431024) in linux-firmware;
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

// Mount the boot stick's ESP (PARTUUID = boot_part_uuid, and only on USB). Returns 0 and fills the report paths.
static int mount_esp(const char *uuid, char *report, char *dmesg, size_t len) {
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
    unlink(p);
    if (mknod(p, S_IFBLK | 0600, makedev(maj, min))) { say("report: mknod %s failed (%s)", p, strerror(errno)); return -1; }
    mkdir("/ob-esp", 0700);
    if (mount(p, "/ob-esp", "vfat", MS_NOATIME | MS_NODEV | MS_NOEXEC | MS_NOSUID, "")) {
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
    if (n > 0) write_all(path, buf, n);
    free(buf);
}

static void hardware_check(const char *uuid) {
    char report[256] = "", dmesg[256] = "";
    say("hwcheck: OpenBook hardware check. Writes only to the boot stick, then powers off.");
    dmi_facts();
    cpu_facts();
    pci_facts("before");
    int have_esp = mount_esp(uuid, report, dmesg, sizeof report) == 0;
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
    say("hwcheck: done");
    if (have_esp) {
        save_report(report);
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
