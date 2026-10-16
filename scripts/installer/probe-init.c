// SPDX-License-Identifier: Apache-2.0
// openbook-probe: a tiny rdinit= for boot-chain tests (ANAL-189). It runs as PID 1 before Android's first-stage
// init, records what the EFI loader handed the kernel, then execs /init so the same boot carries on into Android.
// Every line goes to /dev/kmsg with a "PROBE" tag, so it lands in the serial log and in Android's dmesg.
//   - /proc/cmdline and /proc/bootconfig (the bootconfig trailer the loader appended to the initrd)
//   - which ramdisk fragments arrived (vendor ramdisk, generic ramdisk, module fragment)
//   - every block device: kernel name, sysfs path (USB vs NVMe), PARTNAME, PARTUUID from its uevent
//   - systemd-boot's LoaderDevicePartUUID EFI variable, when present
// With "openbook.probe=halt" on the cmdline it powers off instead of continuing.
// Build: gcc -static -O2 -o openbook-probe probe-init.c
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static int kmsg = -1;

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

// Number of partitions whose uevent has KEY=want (KEY = PARTNAME or PARTUUID).
static int count_uevent(const char *key, const char *want) {
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
            if (!strncmp(line, key, kl) && line[kl] == '=' && !strcmp(line + kl + 1, want)) hits++;
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
    FILE *r = fopen("/proc/sys/kernel/osrelease", "r");
    char rel[128] = "";
    if (r) { if (fgets(rel, sizeof rel, r)) rel[strcspn(rel, "\n")] = 0; fclose(r); }
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
    for (int i = 0; i < 200 && !(found = count_uevent(key, want)); i++) usleep(100000);
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
