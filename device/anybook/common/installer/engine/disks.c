// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Disk inventory (installer step "disks", read-only): whole disks from sysfs, their identity (model, serial, WWN,
// bus, the /dev/disk/by-id name computed the way udev's 60-persistent-storage.rules does, since Android has no
// /dev/disk/by-id), the partition table, filesystems and operating systems found on it, free space, and whether
// it may be a target (docs/installer.md S1, S2, S12, S13).
#include "common.h"

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <linux/fs.h>

// ------------------------------------------------------------------ udev-style names
// udev OPTIONS="string_escape=replace": whitespace runs -> one '_' (trimmed), then anything outside
// [0-9A-Za-z#+-.:=@_] (and not UTF-8) -> '_'.
static void udev_escape(const char *in, char *out, size_t n) {
    size_t o = 0;
    int pending = 0;
    const unsigned char *p = (const unsigned char *)in;
    while (*p && isspace(*p)) p++;
    for (; *p && o + 2 < n; p++) {
        if (isspace(*p)) {
            pending = 1;
            continue;
        }
        if (pending) {
            out[o++] = '_';
            pending = 0;
        }
        unsigned char c = *p;
        if (isalnum(c) || strchr("#+-.:=@_", c) || c >= 0x80) out[o++] = c;
        else out[o++] = '_';
    }
    out[o] = 0;
}

static int sysread(const char *dir, const char *rel, char *buf, size_t n) {
    char p[PATH_MAX];
    snprintf(p, sizeof p, "%s/%s", dir, rel);
    return read_text(p, buf, n);
}

// Walk up from a sysfs device directory to the first ancestor holding file `marker`.
static int find_up(const char *start, const char *marker, char *out, size_t n) {
    char cur[PATH_MAX];
    snprintf(cur, sizeof cur, "%s", start);
    for (int guard = 0; guard < 32; guard++) {
        char p[PATH_MAX + 64];
        snprintf(p, sizeof p, "%s/%s", cur, marker);
        if (!access(p, R_OK)) {
            snprintf(out, n, "%s", cur);
            return 0;
        }
        char *s = strrchr(cur, '/');
        if (!s || s == cur) break;
        *s = 0;
    }
    return -1;
}

static void compute_identity(struct disk *d) {
    char dev[PATH_MAX], v[256];
    snprintf(dev, sizeof dev, "%s/device", d->syspath);
    char model[128] = "", vendor[128] = "", serial[128] = "";
    if (!strcmp(d->bus, "nvme")) {
        sysread(dev, "model", model, sizeof model);
        sysread(dev, "serial", serial, sizeof serial);
        sysread(d->syspath, "wwid", d->wwn, sizeof d->wwn);
    } else if (!strcmp(d->bus, "mmc")) {
        sysread(dev, "name", model, sizeof model);
        sysread(dev, "serial", serial, sizeof serial);
    } else if (!strcmp(d->bus, "virtio")) {
        sysread(d->syspath, "serial", serial, sizeof serial);
        snprintf(model, sizeof model, "Virtio disk");
    } else {
        sysread(dev, "vendor", vendor, sizeof vendor);
        sysread(dev, "model", model, sizeof model);
        sysread(dev, "wwid", d->wwn, sizeof d->wwn);
        if (!strcmp(d->bus, "usb")) {
            char up[PATH_MAX];
            if (!find_up(d->syspath, "idVendor", up, sizeof up)) sysread(up, "serial", serial, sizeof serial);
        } else {
            // SATA/SCSI: the unit serial number VPD page (80h), bytes 4.. are the serial.
            char p[PATH_MAX + 16];
            snprintf(p, sizeof p, "%s/vpd_pg80", dev);
            size_t len;
            char *raw = read_file(p, &len);
            if (raw && len > 4) {
                size_t k = (unsigned char)raw[3];
                if (k > len - 4) k = len - 4;
                if (k >= sizeof serial) k = sizeof serial - 1;
                memcpy(serial, raw + 4, k);
                serial[k] = 0;
                trim(serial);
            }
            free(raw);
        }
    }
    trim(model);
    trim(vendor);
    trim(serial);
    snprintf(d->model, sizeof d->model, "%s", model[0] ? model : "Unknown disk");
    snprintf(d->vendor, sizeof d->vendor, "%s", vendor);
    snprintf(d->serial, sizeof d->serial, "%s", serial);
    char em[128], es[128], ev[128];
    udev_escape(model, em, sizeof em);
    udev_escape(serial, es, sizeof es);
    udev_escape(vendor, ev, sizeof ev);
    d->by_id[0] = 0;
    if (!strcmp(d->bus, "nvme") && em[0] && es[0]) {
        snprintf(d->by_id, sizeof d->by_id, "nvme-%s_%s", em, es);
    } else if (!strcmp(d->bus, "usb") && em[0]) {
        // usb_id: <vendor>_<model>[_<serial>]-<target>:<lun> from the SCSI address host:channel:target:lun
        char hctl[PATH_MAX], *b;
        int h = 0, c = 0, t = 0, l = 0;
        ssize_t r = readlink(dev, hctl, sizeof hctl - 1);
        if (r > 0) {
            hctl[r] = 0;
            b = strrchr(hctl, '/');
            sscanf(b ? b + 1 : hctl, "%d:%d:%d:%d", &h, &c, &t, &l);
        }
        snprintf(d->by_id, sizeof d->by_id, "usb-%s_%s%s%s-%d:%d", ev, em, es[0] ? "_" : "", es, t, l);
    } else if (!strcmp(d->bus, "sata") && em[0] && es[0]) {
        snprintf(d->by_id, sizeof d->by_id, "ata-%s_%s", em, es);
    } else if (!strcmp(d->bus, "virtio") && es[0]) {
        snprintf(d->by_id, sizeof d->by_id, "virtio-%s", es);
    } else if (!strcmp(d->bus, "mmc") && em[0] && es[0]) {
        snprintf(d->by_id, sizeof d->by_id, "mmc-%s_%s", em, es);
    } else if (!strcmp(d->bus, "scsi") && em[0] && es[0]) {
        snprintf(d->by_id, sizeof d->by_id, "scsi-%s_%s_%s", ev, em, es);
    }
    if (!d->by_id[0]) snprintf(d->by_id, sizeof d->by_id, "disk-%s", d->name);  // no serial: by kernel name
    (void)v;
}

// ------------------------------------------------------------------ filesystems
static int has(const uint8_t *b, size_t off, const char *s) { return !memcmp(b + off, s, strlen(s)); }

static void detect_fs(int fd, uint64_t off, uint64_t size, struct part_info *p) {
    static uint8_t b[70000];
    p->fs[0] = 0;
    size_t n = size < sizeof b ? size : sizeof b;
    if (n < 4096 || pread_all(fd, b, n, off)) return;
    char lab[64] = "";
    if (has(b, 3, "-FVE-FS-")) {
        snprintf(p->fs, sizeof p->fs, "bitlocker");
        p->encrypted = 1;
    } else if (has(b, 3, "NTFS    ")) {
        snprintf(p->fs, sizeof p->fs, "ntfs");
    } else if (has(b, 3, "EXFAT   ")) {
        snprintf(p->fs, sizeof p->fs, "exfat");
    } else if (has(b, 0, "LUKS\xba\xbe")) {
        snprintf(p->fs, sizeof p->fs, "luks");
        p->encrypted = 1;
    } else if (has(b, 0, "XFSB")) {
        snprintf(p->fs, sizeof p->fs, "xfs");
        memcpy(lab, b + 108, 12);
    } else if (b[1024 + 0x38] == 0x53 && b[1024 + 0x39] == 0xEF) {
        snprintf(p->fs, sizeof p->fs, "ext4");
        memcpy(lab, b + 1024 + 0x78, 16);
    } else if (n >= 65536 + 0x200 && has(b, 65536 + 0x40, "_BHRfS_M")) {
        snprintf(p->fs, sizeof p->fs, "btrfs");
        memcpy(lab, b + 65536 + 0x12b, 63);
    } else if (b[1024] == 0x10 && b[1025] == 0x20 && b[1026] == 0xF5 && b[1027] == 0xF2) {
        snprintf(p->fs, sizeof p->fs, "f2fs");
    } else if (b[1024] == 0xE2 && b[1025] == 0xE1 && b[1026] == 0xF5 && b[1027] == 0xE0) {
        snprintf(p->fs, sizeof p->fs, "erofs");
    } else if (has(b, 4096 - 10, "SWAPSPACE2") || has(b, 4096 - 10, "SWAP-SPACE")) {
        snprintf(p->fs, sizeof p->fs, "swap");
    } else if (has(b, 512, "LABELONE")) {
        snprintf(p->fs, sizeof p->fs, "lvm2");
    } else if (has(b, 0, "ANDROID!") || has(b, 0, "VNDRBOOT")) {
        snprintf(p->fs, sizeof p->fs, "android_boot");
    } else if (b[4096] == 0x67 && b[4097] == 0x44 && b[4098] == 0x6c && b[4099] == 0x61) {
        snprintf(p->fs, sizeof p->fs, "android_super");
    } else {
        char fl[16];
        int t = fat_probe(fd, off, size, fl, sizeof fl);
        if (t) {
            snprintf(p->fs, sizeof p->fs, "vfat");
            snprintf(lab, sizeof lab, "%s", fl);
        }
    }
    lab[sizeof lab - 1] = 0;
    trim(lab);
    snprintf(p->label, sizeof p->label, "%s", lab);
}

static const char *const ANDROID_NAMES[] = {"super", "userdata", "metadata", "misc", "boot_a", "boot_b",
                                            "vendor_boot_a", "init_boot_a", "vbmeta_a"};

struct esp_scan {
    int windows, linux_, openbook;
};

static void esp_cb(const char *name, int is_dir, uint32_t size, void *arg) {
    struct esp_scan *s = arg;
    (void)size;
    if (!is_dir) return;
    if (!strcasecmp(name, "Microsoft")) s->windows = 1;
    else if (!strcasecmp(name, "OpenBook")) s->openbook = 1;
    else if (strcasecmp(name, "BOOT")) s->linux_ = 1;  // ubuntu, fedora, debian, arch, systemd, opensuse, ...
}

static void entries_cb(const char *name, int is_dir, uint32_t size, void *arg) {
    struct esp_scan *s = arg;
    (void)size;
    // systemd-boot entries: ours are openbook-*.conf; any other is another OS's (usually Linux)
    if (!is_dir && strncasecmp(name, "openbook", 8)) s->linux_ = 1;
}

static void scan_esp(int fd, const struct part_info *p, struct esp_scan *s) {
    struct fat f;
    if (fat_open(&f, fd, p->start, p->bytes)) return;
    fat_list(&f, "EFI", esp_cb, s);
    fat_list(&f, "loader/entries", entries_cb, s);
    fat_close(&f);
}

static void add_os(struct disk *d, const char *os) {
    if (!os[0]) return;
    char tmp[96];
    snprintf(tmp, sizeof tmp, ",%s,", d->os_list);
    char needle[40];
    snprintf(needle, sizeof needle, ",%s,", os);
    if (strstr(tmp, needle)) return;
    size_t l = strlen(d->os_list);
    snprintf(d->os_list + l, sizeof d->os_list - l, "%s%s", l ? "," : "", os);
}

// ------------------------------------------------------------------ mounts and holders
static int holders_nonempty(const char *dir) {
    char p[PATH_MAX];
    snprintf(p, sizeof p, "%s/holders", dir);
    DIR *h = opendir(p);
    if (!h) return 0;
    struct dirent *e;
    int any = 0;
    while ((e = readdir(h)))
        if (e->d_name[0] != '.') any = 1;
    closedir(h);
    return any;
}

static int name_in_file(const char *path, const char *name) {
    char *t = read_file(path, NULL);
    if (!t) return 0;
    int hit = 0;
    char needle[64];
    snprintf(needle, sizeof needle, "/dev/block/%s", name);
    for (char *p = t; (p = strstr(p, needle)); p++) {
        char c = p[strlen(needle)];
        // the disk itself or one of its partitions (sda1, nvme0n1p1, mmcblk0p1)
        if (c == ' ' || c == '\t' || isdigit((unsigned char)c) || c == 'p') {
            hit = 1;
            break;
        }
    }
    free(t);
    return hit;
}

static void check_mounted(struct disk *d) {
    char p[PATH_MAX];
    if (holders_nonempty(d->syspath)) d->mounted = 1;
    DIR *dir = opendir(d->syspath);
    if (dir) {
        struct dirent *e;
        while ((e = readdir(dir))) {
            if (strncmp(e->d_name, d->name, strlen(d->name))) continue;
            snprintf(p, sizeof p, "%s/%s", d->syspath, e->d_name);
            if (holders_nonempty(p)) d->mounted = 1;
        }
        closedir(dir);
    }
    env_path(p, sizeof p, "/proc/self/mounts");
    if (name_in_file(p, d->name)) d->mounted = 1;
    env_path(p, sizeof p, "/proc/swaps");
    if (name_in_file(p, d->name)) d->mounted = 1;
}

// ------------------------------------------------------------------ scan
static int skip_name(const char *n) {
    static const char *const pre[] = {"loop", "ram", "zram", "dm-", "md", "sr", "fd", "nbd", "mtdblock", "vold"};
    for (size_t i = 0; i < ARRAY_LEN(pre); i++)
        if (!strncmp(n, pre[i], strlen(pre[i]))) return 1;
    if (!strncmp(n, "mmcblk", 6) && (strstr(n, "boot") || strstr(n, "rpmb"))) return 1;
    if (!strncmp(n, "nvme", 4) && strchr(n + 4, 'c')) return 1;  // hidden multipath paths (nvme0c0n1)
    return n[0] == '.';
}

static int cmp_part(const void *a, const void *b) {
    const struct part_info *x = a, *y = b;
    return x->start < y->start ? -1 : x->start > y->start;
}

static void read_table(struct disk *d, int fd) {
    snprintf(d->table, sizeof d->table, "none");
    if (!gpt_read(fd, d->sector, d->size / d->sector, &d->gpt)) {
        snprintf(d->table, sizeof d->table, "gpt");
        for (int i = 0; i < d->gpt.nparts; i++) {
            const struct gpt_part *g = &d->gpt.p[i];
            struct part_info *p = &d->parts[d->nparts++];
            p->index = g->index;
            snprintf(p->name, sizeof p->name, "%s", g->name);
            p->kind = gpt_type_kind(g->type);
            guid_to_str(g->type, p->type_guid);
            guid_to_str(g->uniq, p->uuid);
            p->start = g->first * d->sector;
            p->bytes = (g->last - g->first + 1) * d->sector;
            if (!d->esp_index && !strcmp(p->kind, "esp")) d->esp_index = p->index;
            for (size_t k = 0; k < ARRAY_LEN(ANDROID_NAMES); k++)
                if (!strcmp(p->name, ANDROID_NAMES[k])) d->android_names = 1;
        }
    } else {
        uint8_t mbr[512];
        if (!pread_all(fd, mbr, 512, 0) && mbr[510] == 0x55 && mbr[511] == 0xAA) {
            int any = 0;
            for (int i = 0; i < 4; i++) {
                const uint8_t *e = mbr + 446 + 16 * i;
                uint32_t start = e[8] | e[9] << 8 | e[10] << 16 | (uint32_t)e[11] << 24;
                uint32_t count = e[12] | e[13] << 8 | e[14] << 16 | (uint32_t)e[15] << 24;
                if (!e[4] || !count) continue;
                if (e[4] == 0xEE) {
                    any = 0;  // protective MBR of a damaged GPT
                    snprintf(d->table, sizeof d->table, "gpt?");
                    break;
                }
                any = 1;
                struct part_info *p = &d->parts[d->nparts++];
                p->index = i + 1;
                p->kind = e[4] == 0xEF ? "esp" : (e[4] == 0x07 || e[4] == 0x0C || e[4] == 0x0B) ? "msdata"
                          : e[4] == 0x83 ? "linux" : e[4] == 0x82 ? "linux_swap" : "other";
                snprintf(p->type_guid, sizeof p->type_guid, "mbr:%02x", e[4]);
                p->start = (uint64_t)start * 512;
                p->bytes = (uint64_t)count * 512;
            }
            if (any) snprintf(d->table, sizeof d->table, "mbr");
        }
    }
    struct esp_scan es = {0};
    for (int i = 0; i < d->nparts; i++) {
        struct part_info *p = &d->parts[i];
        if (p->start + p->bytes > d->size) continue;
        detect_fs(fd, p->start, p->bytes, p);
        if (!strcmp(p->kind, "esp") && !strcmp(p->fs, "vfat")) scan_esp(fd, p, &es);
        if (p->encrypted) d->encrypted = 1;
    }
    for (int i = 0; i < d->nparts; i++) {
        struct part_info *p = &d->parts[i];
        const char *os = "";
        if (!strcmp(p->kind, "msrecovery")) os = "Windows";
        else if (!strcmp(p->fs, "ntfs") || !strcmp(p->fs, "bitlocker")) os = es.windows || !strcmp(p->kind, "msdata") ? "Windows" : "";
        else if (!strcmp(p->fs, "ext4") || !strcmp(p->fs, "btrfs") || !strcmp(p->fs, "xfs") || !strcmp(p->fs, "luks") ||
                 !strcmp(p->fs, "lvm2") || !strcmp(p->kind, "linux_swap"))
            os = "Linux";
        else if (!strcmp(p->kind, "apple")) os = "macOS";
        else if (!strcmp(p->fs, "android_super") || !strcmp(p->fs, "android_boot")) os = "OpenBook";
        snprintf(p->os, sizeof p->os, "%s", os);
        add_os(d, os);
    }
    if (es.windows) add_os(d, "Windows");
    if (es.linux_) add_os(d, "Linux");
    if (es.openbook) add_os(d, "OpenBook");
    qsort(d->parts, d->nparts, sizeof d->parts[0], cmp_part);
    // Free space inside the GPT's usable area, 1 MiB aligned.
    if (!strcmp(d->table, "gpt")) {
        uint64_t lo = d->gpt.first_usable * d->sector, hi = (d->gpt.last_usable + 1) * d->sector;
        uint64_t cur = lo;
        for (int i = 0; i <= d->nparts; i++) {
            uint64_t next = i < d->nparts ? d->parts[i].start : hi;
            if (next > cur) {
                uint64_t a = (cur + MiB - 1) / MiB * MiB, b = next / MiB * MiB;
                if (b > a && b - a >= MiB) {
                    d->free_bytes += b - a;
                    if (b - a > d->largest.bytes) {
                        d->largest.start = a;
                        d->largest.bytes = b - a;
                    }
                }
            }
            if (i < d->nparts && d->parts[i].start + d->parts[i].bytes > cur) cur = d->parts[i].start + d->parts[i].bytes;
        }
    } else if (!strcmp(d->table, "none")) {
        d->free_bytes = d->size;
    }
}

void disk_table_hash(int fd, const struct disk *d, char out[65]) {
    // The first and the last MiB: protective MBR or MBR, primary and backup GPT (S4).
    struct sha256 c;
    sha256_init(&c);
    uint8_t *b = malloc(MiB);
    if (b) {
        uint64_t n = d->size < MiB ? d->size : MiB;
        if (!pread_all(fd, b, n, 0)) sha256_update(&c, b, n);
        if (d->size > 2 * MiB && !pread_all(fd, b, MiB, d->size - MiB)) sha256_update(&c, b, MiB);
        free(b);
    }
    sha256_final_hex(&c, out);
}

int disk_open(const struct disk *d, int writable) {
    struct stat st;
    int blk = !stat(d->dev, &st) && S_ISBLK(st.st_mode);
    return open(d->dev, (writable ? O_RDWR | (blk ? O_EXCL : 0) : O_RDONLY) | O_CLOEXEC);
}

int disks_scan(struct disk **out) {
    char base[PATH_MAX];
    env_path(base, sizeof base, "/sys/block");
    DIR *dir = opendir(base);
    if (!dir) return 0;
    struct dirent *e;
    char *names[64];
    int nn = 0;
    while ((e = readdir(dir)) && nn < 64)
        if (!skip_name(e->d_name)) names[nn++] = strdup(e->d_name);
    closedir(dir);
    // Stable order: by name.
    for (int i = 0; i < nn; i++)
        for (int j = i + 1; j < nn; j++)
            if (strcmp(names[i], names[j]) > 0) {
                char *t = names[i];
                names[i] = names[j];
                names[j] = t;
            }
    struct disk *d = calloc(nn ? nn : 1, sizeof *d);
    int n = 0;
    for (int i = 0; i < nn; i++) {
        struct disk *x = &d[n];
        memset(x, 0, sizeof *x);
        snprintf(x->name, sizeof x->name, "%s", names[i]);
        char link[PATH_MAX], v[64];
        snprintf(link, sizeof link, "%s/%s", base, names[i]);
        if (!realpath(link, x->syspath)) snprintf(x->syspath, sizeof x->syspath, "%s", link);
        snprintf(x->dev, sizeof x->dev, "%s/dev/block/%s", E.root, x->name);
        // Size, sector size and read-only flag from the device itself (ioctls): on Android, a system daemon may not
        // read unlabeled sysfs attributes. Image files in host tests carry them in the fixture's sysfs.
        int fd = open(x->dev, O_RDONLY | O_CLOEXEC);
        if (fd < 0) {
            LOG("disks: cannot open %s: %s", x->dev, strerror(errno));
            continue;
        }
        struct stat st;
        if (!fstat(fd, &st) && S_ISBLK(st.st_mode)) {
            uint64_t bytes = 0;
            int ssz = 512, ro = 0;
            ioctl(fd, BLKGETSIZE64, &bytes);
            ioctl(fd, BLKSSZGET, &ssz);
            ioctl(fd, BLKROGET, &ro);
            x->size = bytes;
            x->sector = ssz;
            x->read_only = ro;
        } else {
            x->size = sysread(x->syspath, "size", v, sizeof v) ? (uint64_t)st.st_size : strtoull(v, NULL, 10) * 512;
            x->sector = sysread(x->syspath, "queue/logical_block_size", v, sizeof v) ? 512 : atoi(v);
            x->read_only = !sysread(x->syspath, "ro", v, sizeof v) && atoi(v);
        }
        if (!x->size) {  // empty card reader slots and the like
            close(fd);
            continue;
        }
        if (x->sector != 512 && x->sector != 4096) x->sector = 512;
        const char *sp = x->syspath;
        const char *bus = strstr(sp, "/usb") ? "usb" : strstr(sp, "/nvme") ? "nvme" : strstr(sp, "/ata") ? "sata"
                          : strstr(sp, "/virtio") ? "virtio" : strstr(sp, "/mmc_host") ? "mmc" : "scsi";
        snprintf(x->bus, sizeof x->bus, "%s", bus);
        x->removable = !strcmp(x->bus, "usb") || !strcmp(x->bus, "mmc");
        compute_identity(x);
        read_table(x, fd);
        disk_table_hash(fd, x, x->table_sha256);
        close(fd);
        if (E.boot_part_uuid[0] && x->gpt.valid && gpt_find_uuid(&x->gpt, E.boot_part_uuid)) x->boot_disk = 1;
        check_mounted(x);
        x->external = !x->boot_disk && (!strcmp(x->bus, "usb") || strstr(sp, "thunderbolt") != NULL);
        n++;
    }
    for (int i = 0; i < nn; i++) free(names[i]);
    *out = d;
    return n;
}

void disks_free(struct disk *d, int n) {
    for (int i = 0; i < n; i++) gpt_free(&d[i].gpt);
    free(d);
}

struct disk *disk_by_id(struct disk *d, int n, const char *by_id) {
    const char *id = by_id;
    if (!strncmp(id, "/dev/disk/by-id/", 16)) id += 16;
    for (int i = 0; i < n; i++)
        if (!strcmp(d[i].by_id, id)) return &d[i];
    return NULL;
}

static int free_slots(const struct disk *d) {
    if (!d->gpt.valid) return 0;
    int used = 0;
    for (int i = 0; i < d->gpt.nparts; i++)
        if (d->gpt.p[i].index > used) used = d->gpt.p[i].index;
    return (int)d->gpt.n_entries - d->gpt.nparts;
}

int disk_layout_ok(const struct disk *d, const char *layout, uint64_t min_bytes, const char **why) {
    *why = NULL;
    if (d->boot_disk) *why = "boot_disk";
    else if (d->read_only) *why = "read_only";
    else if (d->mounted) *why = "mounted";
    else if (!strcmp(layout, "whole")) {
        if (d->size < min_bytes) *why = "too_small";
    } else if (!strcmp(layout, "alongside")) {
        if (strcmp(d->table, "gpt")) *why = "no_gpt";
        else if (d->android_names) *why = "name_clash";
        else if (d->largest.bytes < min_bytes) *why = "no_space";
        else if (free_slots(d) < 14) *why = "table_full";
    } else {
        *why = "bad_layout";
    }
    return *why == NULL;
}

void disk_json(struct jw *w, const struct disk *d, uint64_t min_bytes) {
    jw_obj(w, NULL);
    jw_str(w, "name", d->name);
    jw_str(w, "by_id", d->by_id);
    jw_str(w, "model", d->model);
    jw_str(w, "vendor", d->vendor);
    jw_str(w, "serial", d->serial);
    jw_str(w, "wwn", d->wwn);
    jw_u64(w, "size_bytes", d->size);
    jw_int(w, "sector_size", d->sector);
    jw_str(w, "bus", d->bus);
    jw_bool(w, "removable", d->removable);
    jw_bool(w, "read_only", d->read_only);
    jw_bool(w, "boot_disk", d->boot_disk);
    jw_bool(w, "mounted", d->mounted);
    jw_str(w, "table", d->table);
    jw_arr(w, "os");
    char tmp[96];
    snprintf(tmp, sizeof tmp, "%s", d->os_list);
    char *save = NULL;
    for (char *t = strtok_r(tmp, ",", &save); t; t = strtok_r(NULL, ",", &save)) jw_str(w, NULL, t);
    jw_enda(w);
    jw_u64(w, "free_bytes", d->free_bytes);
    jw_u64(w, "largest_free_bytes", d->largest.bytes);
    jw_arr(w, "partitions");
    for (int i = 0; i < d->nparts; i++) {
        const struct part_info *p = &d->parts[i];
        jw_obj(w, NULL);
        jw_int(w, "index", p->index);
        jw_str(w, "name", p->name);
        jw_str(w, "type", p->kind);
        jw_str(w, "fs", p->fs);
        jw_str(w, "label", p->label);
        jw_u64(w, "bytes", p->bytes);
        jw_u64(w, "start", p->start);
        jw_str(w, "os", p->os);
        jw_bool(w, "encrypted", p->encrypted);
        jw_endo(w);
    }
    jw_enda(w);
    jw_obj(w, "layouts");
    const char *why;
    jw_obj(w, "whole");
    jw_bool(w, "ok", disk_layout_ok(d, "whole", min_bytes, &why));
    jw_str(w, "why", why);
    jw_endo(w);
    jw_obj(w, "alongside");
    jw_bool(w, "ok", disk_layout_ok(d, "alongside", min_bytes, &why));
    jw_str(w, "why", why);
    jw_u64(w, "free_bytes", d->largest.bytes);
    jw_endo(w);
    jw_endo(w);
    jw_arr(w, "warnings");
    if (d->external) jw_str(w, NULL, "external");
    if (d->encrypted) jw_str(w, NULL, "encrypted");
    jw_enda(w);
    jw_u64(w, "min_bytes", min_bytes);
    jw_endo(w);
}
