// SPDX-License-Identifier: Apache-2.0
// openbook-live-init: the rdinit= of the OpenBook live USB stick (ANAL-190, docs/installer.md section 11). It runs
// as PID 1 before Android's first-stage init, does what a live stick needs before any partition is in use, and
// then execs /init:
//   grow   On a stick larger than the image: move the backup GPT to the end of the stick and, while "userdata" (the
//          last partition) is still blank, grow it to fill the stick. Android then formats /data at its full size
//          (fs_mgr formats a "formattable" partition whose first 4 KiB are zero: libcutils partition_wiped()). A
//          stick whose userdata is already in use only gets its backup GPT moved.
//   reset  androidboot.openbook.live_reset=1 (the "start fresh" entry): zero the first MiB of "metadata" and
//          "userdata", so Android formats both again, exactly as on the first boot.
//   logs   androidboot.openbook.logs=1 (the "save logs" entry): a helper process copies the kernel log to the
//          stick's ESP while Android boots. Once Android has booted (or after a timeout) it also saves logcat,
//          system facts, a screenshot and summary.json to openbook/logs/live-NNN/, then shuts Android down
//          (androidboot.openbook.logs_after=poweroff, the default; =reboot for unattended runs; =stay). It
//          mounts the ESP with the new mount API (fsopen/fsmount), so the mount is attached nowhere and Android
//          never sees it. That entry also boots SELinux permissive (userdebug only), which the helper needs to
//          read logcat and take the screenshot from outside Android's own domains. On products that ship it
//          (userdebug), the final capture first runs /system_ext/bin/openbook-hwtest (Wi-Fi, Bluetooth and audio
//          checks, ANAL-179) into hwtest-final.txt, with the settings in openbook/hwtest.conf on the ESP.
// Safety: it acts only with androidboot.openbook.live=1 (set only by the live stick's boot entries), only on the
// disk holding the ESP whose PARTUUID is androidboot.boot_part_uuid, only if that disk is on USB, and only if its
// GPT is valid and has the OpenBook live layout (EFI, metadata, super, userdata; userdata last). Anything
// unexpected is logged, and the boot continues with the disk unchanged. Every action is logged to the kernel log
// ("openbook-live:") and, when it changed something, to openbook/logs/live-init-NNN.json on the stick's ESP.
//
// Build: gcc -static -O2 -o openbook-live-init live-init.c
// Host test (a disk image file stands in for the stick; nothing else is touched):
//        openbook-live-init --gpt-test IMG [ESP_PARTUUID]    run the grow/repair step on IMG, print JSON
//        openbook-live-init --reset-test IMG                 run the reset step on IMG, print JSON
#define _GNU_SOURCE
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <linux/blkpg.h>

#define TAG "openbook-live"
#define WORK "/openbook-live"  // private node and mount dir on the rootfs; removed before exec /init
#define MiB (1ull << 20)

// ------------------------------------------------------------------ logging

static int kmsg_fd = -1;
static char logbuf[16384];  // everything said, for the JSON report
static size_t loglen;

static void say(const char *fmt, ...) {
    char buf[700], out[800];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    int m = snprintf(out, sizeof out, "<5>" TAG ": %s\n", buf);
    if (m >= (int)sizeof out) m = sizeof out - 1;
    if (kmsg_fd >= 0) {
        if (write(kmsg_fd, out, m) < 0) { /* nothing better to do */ }
    } else {
        fputs(out + 3, stderr);
    }
    size_t n = strlen(buf);
    if (loglen + n + 2 < sizeof logbuf) {
        memcpy(logbuf + loglen, buf, n);
        loglen += n;
        logbuf[loglen++] = '\n';
        logbuf[loglen] = 0;
    }
}

static int read_line(const char *path, char *out, size_t len) {
    out[0] = 0;
    FILE *f = fopen(path, "re");
    if (!f) return -1;
    if (!fgets(out, len, f)) out[0] = 0;
    fclose(f);
    out[strcspn(out, "\n")] = 0;
    return 0;
}

static unsigned long long read_ull(const char *path) {
    char v[64];
    if (read_line(path, v, sizeof v)) return 0;
    return strtoull(v, NULL, 10);
}

static double uptime_s(void) {
    struct timespec t;
    clock_gettime(CLOCK_BOOTTIME, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}

// JSON string escaping into a growing buffer.
struct sb { char *p; size_t n, cap; };
static void sb_add(struct sb *b, const char *s, size_t n) {
    if (b->n + n + 1 > b->cap) {
        size_t cap = b->cap ? b->cap * 2 : 4096;
        while (cap < b->n + n + 1) cap *= 2;
        char *q = realloc(b->p, cap);
        if (!q) return;
        b->p = q;
        b->cap = cap;
    }
    memcpy(b->p + b->n, s, n);
    b->n += n;
    b->p[b->n] = 0;
}
#define SB_LIT(b, lit) sb_add((b), (lit), sizeof(lit) - 1)  // string literals only: no hand-counted lengths
static void sb_printf(struct sb *b, const char *fmt, ...) {
    char tmp[1024];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(tmp, sizeof tmp, fmt, ap);
    va_end(ap);
    if (n > 0) sb_add(b, tmp, n < (int)sizeof tmp ? (size_t)n : sizeof tmp - 1);
}
static void sb_json_str(struct sb *b, const char *s) {
    SB_LIT(b, "\"");
    for (; s && *s; s++) {
        unsigned char c = *s;
        char e[8];
        if (c == '"' || c == '\\') { e[0] = '\\'; e[1] = c; sb_add(b, e, 2); }
        else if (c == '\n') SB_LIT(b, "\\n");
        else if (c < 0x20) { snprintf(e, sizeof e, "\\u%04x", c); sb_add(b, e, 6); }
        else sb_add(b, (const char *)&c, 1);
    }
    SB_LIT(b, "\"");
}

// ------------------------------------------------------------------ boot configuration

// Value of KEY from /proc/bootconfig ('key = "value"', first value of a list) or /proc/cmdline ('key=value').
static int conf_get(const char *key, char *out, size_t len) {
    char line[4096];
    size_t kl = strlen(key);
    out[0] = 0;
    FILE *f = fopen("/proc/bootconfig", "re");
    while (f && fgets(line, sizeof line, f)) {
        if (strncmp(line, key, kl) || (line[kl] != ' ' && line[kl] != '=')) continue;
        char *q = strchr(line, '"');
        if (!q) continue;
        char *e = strchr(q + 1, '"');
        if (e) *e = 0;
        snprintf(out, len, "%s", q + 1);
        fclose(f);
        return 1;
    }
    if (f) fclose(f);
    f = fopen("/proc/cmdline", "re");
    if (f && fgets(line, sizeof line, f)) {
        for (char *t = strtok(line, " \n"); t; t = strtok(NULL, " \n")) {
            if (!strncmp(t, key, kl) && t[kl] == '=') {
                snprintf(out, len, "%s", t + kl + 1);
                fclose(f);
                return 1;
            }
        }
    }
    if (f) fclose(f);
    return 0;
}

static long conf_long(const char *key, long def) {
    char v[64];
    return conf_get(key, v, sizeof v) && v[0] ? strtol(v, NULL, 10) : def;
}

// ------------------------------------------------------------------ block devices (GKI has no devtmpfs)

// Kernel name of the block device whose uevent has KEY=want (case-insensitive value), or -1.
static int find_uevent(const char *key, const char *want, char *name, size_t len) {
    DIR *d = opendir("/sys/class/block");
    if (!d) return -1;
    int hits = 0;
    struct dirent *e;
    size_t kl = strlen(key);
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        char p[512], line[256];
        snprintf(p, sizeof p, "/sys/class/block/%s/uevent", e->d_name);
        FILE *f = fopen(p, "re");
        if (!f) continue;
        while (fgets(line, sizeof line, f)) {
            line[strcspn(line, "\n")] = 0;
            if (!strncmp(line, key, kl) && line[kl] == '=' && !strcasecmp(line + kl + 1, want)) {
                if (!hits) snprintf(name, len, "%s", e->d_name);
                hits++;
            }
        }
        fclose(f);
    }
    closedir(d);
    return hits;
}

// Make a block node for /sys/class/block/NAME at PATH (from its "major:minor").
static int make_node(const char *name, const char *path) {
    char p[256], devno[32];
    unsigned maj, min;
    snprintf(p, sizeof p, "/sys/class/block/%s/dev", name);
    if (read_line(p, devno, sizeof devno) || sscanf(devno, "%u:%u", &maj, &min) != 2) return -1;
    unlink(path);
    return mknod(path, S_IFBLK | 0600, makedev(maj, min));
}

// ------------------------------------------------------------------ GPT

struct gpt_header {
    char sig[8];
    uint32_t revision, header_size, header_crc, reserved;
    uint64_t my_lba, alt_lba, first_usable, last_usable;
    uint8_t disk_guid[16];
    uint64_t entries_lba;
    uint32_t n_entries, entry_size, entries_crc;
} __attribute__((packed));

struct gpt_entry {
    uint8_t type[16], uniq[16];
    uint64_t first, last, attrs;
    uint16_t name[36];
} __attribute__((packed));

static uint32_t crc32(const void *data, size_t n) {
    const uint8_t *p = data;
    uint32_t c = 0xFFFFFFFFu;
    while (n--) {
        c ^= *p++;
        for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & -(c & 1));
    }
    return ~c;
}

static void guid_str(const uint8_t g[16], char out[37]) {
    snprintf(out, 37, "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x", g[3], g[2], g[1], g[0],
             g[5], g[4], g[7], g[6], g[8], g[9], g[10], g[11], g[12], g[13], g[14], g[15]);
}

static void entry_name(const struct gpt_entry *e, char out[37]) {
    int i;
    for (i = 0; i < 36 && e->name[i]; i++) out[i] = e->name[i] < 128 ? (char)e->name[i] : '?';
    out[i] = 0;
}

static int is_zero(const void *p, size_t n) {
    const uint8_t *b = p;
    for (size_t i = 0; i < n; i++)
        if (b[i]) return 0;
    return 1;
}

static int pread_all(int fd, void *buf, size_t n, uint64_t off) {
    size_t done = 0;
    while (done < n) {
        ssize_t r = pread(fd, (char *)buf + done, n - done, off + done);
        if (r <= 0) return -1;
        done += r;
    }
    return 0;
}

static int pwrite_all(int fd, const void *buf, size_t n, uint64_t off) {
    size_t done = 0;
    while (done < n) {
        ssize_t r = pwrite(fd, (const char *)buf + done, n - done, off + done);
        if (r <= 0) return -1;
        done += r;
    }
    return 0;
}

static int region_is_zero(int fd, uint64_t off, uint64_t n) {
    static uint8_t buf[1 << 16];
    for (uint64_t done = 0; done < n;) {
        size_t k = n - done < sizeof buf ? n - done : sizeof buf;
        if (pread_all(fd, buf, k, off + done) || !is_zero(buf, k)) return 0;
        done += k;
    }
    return 1;
}

static int zero_region(int fd, uint64_t off, uint64_t n) {
    static uint8_t zeros[1 << 16];
    for (uint64_t done = 0; done < n;) {
        size_t k = n - done < sizeof zeros ? n - done : sizeof zeros;
        if (pwrite_all(fd, zeros, k, off + done)) return -1;
        done += k;
    }
    return 0;
}

struct gpt {
    struct gpt_header h;
    struct gpt_entry *e;  // h.n_entries entries
    size_t entries_bytes;
    int esp, metadata, super, userdata;  // entry indexes, -1 if absent
};

// Read and check the primary GPT; find the live layout's partitions. esp_uuid NULL: don't check the ESP's PARTUUID.
static int gpt_load(int fd, uint64_t sectors, const char *esp_uuid, struct gpt *g, char *why, size_t wl) {
    uint8_t sec[512];
    memset(g, 0, sizeof *g);
    g->esp = g->metadata = g->super = g->userdata = -1;
    if (pread_all(fd, sec, 512, 512)) { snprintf(why, wl, "cannot read LBA 1"); return -1; }
    memcpy(&g->h, sec, sizeof g->h);
    struct gpt_header h = g->h;
    if (memcmp(h.sig, "EFI PART", 8) || h.header_size != 92 || h.my_lba != 1) {
        snprintf(why, wl, "no primary GPT header at LBA 1");
        return -1;
    }
    h.header_crc = 0;
    if (crc32(&h, 92) != g->h.header_crc) { snprintf(why, wl, "primary GPT header CRC mismatch"); return -1; }
    if (g->h.entry_size != 128 || g->h.n_entries == 0 || g->h.n_entries > 1024 || g->h.entries_lba != 2) {
        snprintf(why, wl, "unexpected GPT entry array (%u x %u at LBA %llu)", g->h.n_entries, g->h.entry_size,
                 (unsigned long long)g->h.entries_lba);
        return -1;
    }
    g->entries_bytes = (size_t)g->h.n_entries * 128;
    if (g->entries_bytes % 512) { snprintf(why, wl, "GPT entry array not sector-sized"); return -1; }
    g->e = calloc(1, g->entries_bytes);
    if (!g->e || pread_all(fd, g->e, g->entries_bytes, 1024)) { snprintf(why, wl, "cannot read GPT entries"); return -1; }
    if (crc32(g->e, g->entries_bytes) != g->h.entries_crc) { snprintf(why, wl, "GPT entries CRC mismatch"); return -1; }
    if (g->h.alt_lba >= sectors || g->h.last_usable >= g->h.alt_lba) {
        snprintf(why, wl, "GPT says the disk has %llu sectors, but it has %llu: written from a larger image?",
                 (unsigned long long)g->h.alt_lba + 1, (unsigned long long)sectors);
        return -1;
    }
    uint64_t max_last = 0;
    int last_idx = -1;
    for (uint32_t i = 0; i < g->h.n_entries; i++) {
        struct gpt_entry *e = &g->e[i];
        if (is_zero(e->type, 16)) continue;
        char n[37], u[37];
        entry_name(e, n);
        guid_str(e->uniq, u);
        if (!strcmp(n, "EFI") && (!esp_uuid || !strcasecmp(u, esp_uuid))) g->esp = i;
        if (!strcmp(n, "metadata")) g->metadata = i;
        if (!strcmp(n, "super")) g->super = i;
        if (!strcmp(n, "userdata")) g->userdata = i;
        if (e->last > max_last) { max_last = e->last; last_idx = i; }
    }
    if (g->esp < 0 || g->metadata < 0 || g->super < 0 || g->userdata < 0) {
        snprintf(why, wl, "not the OpenBook live layout (EFI%s, metadata, super, userdata needed)",
                 esp_uuid ? " with the boot PARTUUID" : "");
        return -1;
    }
    if (last_idx != g->userdata) { snprintf(why, wl, "userdata is not the last partition"); return -1; }
    return 0;
}

static void header_finish(struct gpt_header *h, uint64_t my, uint64_t alt, uint64_t entries_lba) {
    h->my_lba = my;
    h->alt_lba = alt;
    h->entries_lba = entries_lba;
    h->header_crc = 0;
    h->header_crc = crc32(h, 92);
}

struct result {
    char action[16];   // none, grow, repair, reset, skipped, error
    char detail[256];
    char disk[32];
    unsigned long long disk_sectors, old_alt_lba, new_alt_lba, userdata_old_sectors, userdata_new_sectors;
    int userdata_blank, reset_done;
};
static struct result R;

// Grow userdata / move the backup GPT on fd (a whole disk, or an image file in --gpt-test). Returns 1 if the GPT
// was rewritten, 0 if nothing was needed, -1 on error (disk unchanged unless "partially" is logged).
static int gpt_grow(int fd, uint64_t sectors, const char *esp_uuid, int *userdata_pno, uint64_t *ud_start,
                    uint64_t *ud_sectors) {
    struct gpt g;
    char why[200] = "";
    R.disk_sectors = sectors;
    if (gpt_load(fd, sectors, esp_uuid, &g, why, sizeof why)) {
        say("grow: %s; leaving the disk as it is", why);
        snprintf(R.detail, sizeof R.detail, "%s", why);
        free(g.e);
        return -1;
    }
    struct gpt_entry *ud = &g.e[g.userdata];
    uint64_t last = sectors - 1, new_last_usable = last - 1 - g.entries_bytes / 512;
    R.old_alt_lba = g.h.alt_lba;
    R.userdata_old_sectors = ud->last - ud->first + 1;
    R.userdata_new_sectors = R.userdata_old_sectors;
    *userdata_pno = g.userdata + 1;
    *ud_start = ud->first;
    *ud_sectors = R.userdata_old_sectors;
    R.userdata_blank = region_is_zero(fd, ud->first * 512, MiB < R.userdata_old_sectors * 512 ? MiB : R.userdata_old_sectors * 512);
    uint64_t new_end = ud->last;
    if (R.userdata_blank) {
        uint64_t n = (new_last_usable + 1 - ud->first) / 2048 * 2048;  // whole MiB, starts are MiB-aligned
        if (ud->first + n - 1 > ud->last) new_end = ud->first + n - 1;
    }
    int move_backup = g.h.alt_lba != last;
    say("grow: disk %llu sectors, GPT backup at LBA %llu, userdata %llu sectors (%s)", (unsigned long long)sectors,
        (unsigned long long)g.h.alt_lba, (unsigned long long)R.userdata_old_sectors,
        R.userdata_blank ? "blank" : "in use");
    if (!move_backup && new_end == ud->last) {
        say("grow: nothing to do");
        free(g.e);
        return 0;
    }
    uint64_t old_alt = g.h.alt_lba;
    ud->last = new_end;
    struct gpt_header h = g.h;
    h.last_usable = new_last_usable < h.last_usable ? h.last_usable : new_last_usable;
    h.entries_crc = crc32(g.e, g.entries_bytes);
    struct gpt_header primary = h, backup = h;
    header_finish(&primary, 1, last, 2);
    header_finish(&backup, last, 1, last - g.entries_bytes / 512);
    uint8_t sec[512];
    // Backup first, then primary: a cut at any point leaves at least one valid, consistent GPT.
    memset(sec, 0, sizeof sec);
    memcpy(sec, &backup, 92);
    if (pwrite_all(fd, g.e, g.entries_bytes, backup.entries_lba * 512) || pwrite_all(fd, sec, 512, last * 512) ||
        fsync(fd)) {
        say("grow: writing the backup GPT failed (%s); the primary GPT is unchanged", strerror(errno));
        snprintf(R.detail, sizeof R.detail, "backup GPT write failed");
        free(g.e);
        return -1;
    }
    memset(sec, 0, sizeof sec);
    memcpy(sec, &primary, 92);
    if (pwrite_all(fd, g.e, g.entries_bytes, 1024) || pwrite_all(fd, sec, 512, 512) || fsync(fd)) {
        say("grow: writing the primary GPT failed (%s); the backup GPT at the end is valid", strerror(errno));
        snprintf(R.detail, sizeof R.detail, "primary GPT write failed (backup valid)");
        free(g.e);
        return -1;
    }
    // Protective MBR: its 0xEE partition covers the whole disk (capped at 2^32-1 sectors).
    if (!pread_all(fd, sec, 512, 0) && sec[510] == 0x55 && sec[511] == 0xAA && sec[446 + 4] == 0xEE) {
        uint32_t n = sectors - 1 > 0xFFFFFFFFull ? 0xFFFFFFFFu : (uint32_t)(sectors - 1);
        memcpy(sec + 446 + 12, &n, 4);
        if (pwrite_all(fd, sec, 512, 0)) say("grow: protective MBR update failed (%s)", strerror(errno));
    }
    // The old backup header now sits in free space or inside the grown userdata: blank it.
    if (move_backup && old_alt < last - g.entries_bytes / 512) {
        memset(sec, 0, sizeof sec);
        if (pwrite_all(fd, sec, 512, old_alt * 512)) say("grow: could not blank the old backup header");
    }
    fsync(fd);
    R.new_alt_lba = last;
    R.userdata_new_sectors = new_end - ud->first + 1;
    *ud_sectors = R.userdata_new_sectors;
    say("grow: GPT backup moved LBA %llu -> %llu; userdata %llu -> %llu sectors (%.1f GiB)", (unsigned long long)old_alt,
        (unsigned long long)last, (unsigned long long)R.userdata_old_sectors,
        (unsigned long long)R.userdata_new_sectors, R.userdata_new_sectors * 512.0 / (1u << 30));
    snprintf(R.action, sizeof R.action, "%s", R.userdata_new_sectors != R.userdata_old_sectors ? "grow" : "repair");
    free(g.e);
    return 1;
}

// Zero the first MiB of metadata and userdata. Returns 0 on success.
static int live_reset(int fd, uint64_t sectors, const char *esp_uuid) {
    struct gpt g;
    char why[200] = "";
    if (gpt_load(fd, sectors, esp_uuid, &g, why, sizeof why)) {
        say("reset: %s; nothing erased", why);
        snprintf(R.detail, sizeof R.detail, "reset refused: %s", why);
        free(g.e);
        return -1;
    }
    int rc = 0;
    int parts[2] = {g.metadata, g.userdata};
    for (int i = 0; i < 2; i++) {
        struct gpt_entry *e = &g.e[parts[i]];
        uint64_t n = (e->last - e->first + 1) * 512;
        if (n > MiB) n = MiB;
        char name[37];
        entry_name(e, name);
        if (zero_region(fd, e->first * 512, n)) { say("reset: zeroing %s failed (%s)", name, strerror(errno)); rc = -1; }
        else say("reset: zeroed the first %llu KiB of %s", (unsigned long long)n / 1024, name);
    }
    fsync(fd);
    free(g.e);
    R.reset_done = rc == 0;
    return rc;
}

// Make the kernel see the new userdata size: re-read the table, or resize just that partition.
static void reload_partitions(int fd, int pno, uint64_t start, uint64_t nsect) {
    ioctl(fd, BLKFLSBUF, 0);
    if (!ioctl(fd, BLKRRPART, 0)) { say("grow: kernel re-read the partition table"); return; }
    int err = errno;
    struct blkpg_partition p = {.start = (long long)(start * 512), .length = (long long)(nsect * 512), .pno = pno};
    struct blkpg_ioctl_arg a = {.op = BLKPG_RESIZE_PARTITION, .datalen = sizeof p, .data = &p};
    if (!ioctl(fd, BLKPG, &a)) say("grow: BLKRRPART failed (%s); resized partition %d with BLKPG", strerror(err), pno);
    else say("grow: the kernel still sees the old size (BLKRRPART: %s, BLKPG: %s); it applies on the next boot",
             strerror(err), strerror(errno));
}

// ------------------------------------------------------------------ the ESP

static int esp_mount_fd(const char *node) {  // a detached vfat mount: an fd, attached to no directory
    int fs = fsopen("vfat", FSOPEN_CLOEXEC);
    if (fs < 0) return -1;
    if (fsconfig(fs, FSCONFIG_SET_STRING, "source", node, 0) || fsconfig(fs, FSCONFIG_CMD_CREATE, NULL, NULL, 0)) {
        close(fs);
        return -1;
    }
    int m = fsmount(fs, FSMOUNT_CLOEXEC, MOUNT_ATTR_NOEXEC | MOUNT_ATTR_NODEV | MOUNT_ATTR_NOSUID | MOUNT_ATTR_NOATIME);
    close(fs);
    return m;
}

static int write_at(int dirfd, const char *name, const char *data, size_t len) {
    int fd = openat(dirfd, name, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
    if (fd < 0) return -1;
    int rc = pwrite_all(fd, data, len, 0);
    fsync(fd);
    close(fd);
    return rc;
}

static int mkdir_free(int base, const char *prefix, char *out, size_t len) {  // openbook/logs/<prefix>NNN
    mkdirat(base, "openbook", 0755);
    mkdirat(base, "openbook/logs", 0755);
    for (int i = 1; i < 1000; i++) {
        snprintf(out, len, "openbook/logs/%s%03d", prefix, i);
        if (!mkdirat(base, out, 0755)) return 0;
        if (errno != EEXIST) return -1;
    }
    return -1;
}

static void result_json(struct sb *b) {
    sb_printf(b, "{\"action\": \"%s\", \"detail\": ", R.action);
    sb_json_str(b, R.detail);
    sb_printf(b, ", \"disk\": \"%s\", \"disk_sectors\": %llu, \"gpt_backup_lba_before\": %llu, "
                 "\"gpt_backup_lba_after\": %llu, \"userdata_sectors_before\": %llu, \"userdata_sectors_after\": %llu, "
                 "\"userdata_blank\": %s, \"reset\": %s}",
              R.disk, R.disk_sectors, R.old_alt_lba, R.new_alt_lba, R.userdata_old_sectors, R.userdata_new_sectors,
              R.userdata_blank ? "true" : "false", R.reset_done ? "true" : "false");
}

// After a change: openbook/logs/live-init-NNN.json on the ESP (a classic mount; nothing else runs yet).
static void save_action_report(const char *esp_node) {
    int m = esp_mount_fd(esp_node);
    if (m < 0) { say("report: cannot mount the ESP (%s)", strerror(errno)); return; }
    char dir[64];
    mkdirat(m, "openbook", 0755);
    mkdirat(m, "openbook/logs", 0755);
    for (int i = 1; i < 1000; i++) {
        snprintf(dir, sizeof dir, "openbook/logs/live-init-%03d.json", i);
        if (faccessat(m, dir, F_OK, 0)) break;
    }
    struct sb b = {0};
    sb_printf(&b, "{\"schema\": \"openbook-live-init/1\", \"uptime_s\": %.1f, \"result\": ", uptime_s());
    result_json(&b);
    SB_LIT(&b, ", \"log\": ");
    sb_json_str(&b, logbuf);
    SB_LIT(&b, "}\n");
    if (write_at(m, dir, b.p, b.n)) say("report: writing %s failed (%s)", dir, strerror(errno));
    else say("report: wrote %s", dir);
    free(b.p);
    close(m);
}

// ------------------------------------------------------------------ the logs helper (androidboot.openbook.logs=1)

static int procfd = -1, logdir = -1, espfd = -1;
static char logdir_name[64];

static const char *ANDROID_ENV[] = {
    "PATH=/product/bin:/apex/com.android.runtime/bin:/apex/com.android.art/bin:/system_ext/bin:/system/bin:"
    "/system/xbin:/odm/bin:/vendor/bin:/vendor/xbin",
    "ANDROID_ROOT=/system", "ANDROID_DATA=/data", "ANDROID_STORAGE=/storage", "ANDROID_ART_ROOT=/apex/com.android.art",
    "ANDROID_I18N_ROOT=/apex/com.android.i18n", "ANDROID_TZDATA_ROOT=/apex/com.android.tzdata", "HOME=/data/local/tmp",
    "TMPDIR=/data/local/tmp", NULL};

// ANDROID_ENV plus the OPENBOOK_HWTEST_<KEY> settings from openbook/hwtest.conf on the ESP (read_hwtest_conf), for
// the Wi-Fi, Bluetooth and audio checks (openbook-hwtest, ANAL-179).
#define HWTEST_MAX 16
static const char *hwtest_env[sizeof ANDROID_ENV / sizeof *ANDROID_ENV + HWTEST_MAX];
static const char *const *run_env = ANDROID_ENV;

// Run CMD with /system/bin/sh in Android's mount namespace and root (init's: /proc/1/ns/mnt, /proc/1/root), so
// /proc/self/mounts, df and the APEX mounts look as they do to Android's own shell. Output goes to out_fd, or into
// cap (NUL-terminated) when cap is not NULL. Returns the exit status, or -1 (spawn failed or timed out).
static int run_android(const char *cmd, int out_fd, char *cap, size_t caplen, int timeout_s) {
    int pfd[2] = {-1, -1};
    if (cap && pipe2(pfd, O_CLOEXEC)) return -1;
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        int ns = openat(procfd, "1/ns/mnt", O_RDONLY | O_CLOEXEC);
        int root = openat(procfd, "1/root", O_PATH | O_DIRECTORY | O_CLOEXEC);
        if (ns < 0 || setns(ns, CLONE_NEWNS)) _exit(125);
        if (root < 0 || fchdir(root) || chroot(".") || chdir("/")) _exit(126);
        int nul = open("/dev/null", O_RDWR | O_CLOEXEC);
        int o = cap ? pfd[1] : out_fd >= 0 ? out_fd : nul;
        dup2(nul >= 0 ? nul : o, 0);
        dup2(o, 1);
        dup2(o, 2);
        setsid();
        char *const argv[] = {(char *)"sh", (char *)"-c", (char *)cmd, NULL};
        execve("/system/bin/sh", argv, (char *const *)run_env);
        _exit(127);
    }
    size_t got = 0;
    if (cap) {
        close(pfd[1]);
        cap[0] = 0;
    }
    double t0 = uptime_s();
    int status = -1;
    for (;;) {
        if (cap) {
            struct pollfd p = {.fd = pfd[0], .events = POLLIN};
            if (poll(&p, 1, 200) > 0) {
                char tmp[4096];
                ssize_t r = read(pfd[0], tmp, sizeof tmp);
                if (r > 0) {
                    size_t k = (size_t)r < caplen - 1 - got ? (size_t)r : caplen - 1 - got;
                    memcpy(cap + got, tmp, k);
                    got += k;
                    cap[got] = 0;
                }
            }
        } else {
            usleep(200000);
        }
        int st;
        pid_t w = waitpid(pid, &st, WNOHANG);
        if (w == pid) { status = WIFEXITED(st) ? WEXITSTATUS(st) : -1; break; }
        if (uptime_s() - t0 > timeout_s) {
            kill(-pid, SIGKILL);
            kill(pid, SIGKILL);
            waitpid(pid, &st, 0);
            say("logs: \"%.60s\" timed out after %d s", cmd, timeout_s);
            break;
        }
    }
    if (cap) {
        for (;;) {  // drain what is left
            char tmp[4096];
            ssize_t r = read(pfd[0], tmp, sizeof tmp);
            if (r <= 0) break;
            size_t k = (size_t)r < caplen - 1 - got ? (size_t)r : caplen - 1 - got;
            memcpy(cap + got, tmp, k);
            got += k;
            cap[got] = 0;
        }
        close(pfd[0]);
        while (got && (cap[got - 1] == '\n' || cap[got - 1] == '\r')) cap[--got] = 0;
    }
    return status;
}

static int run_to_file(const char *cmd, const char *file, int timeout_s) {
    int fd = openat(logdir, file, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
    if (fd < 0) return -1;
    int rc = run_android(cmd, fd, NULL, 0, timeout_s);
    fsync(fd);
    close(fd);
    return rc;
}

// System facts for collect-<phase>.txt; sections are "===NAME===" lines. mksh and toybox only.
static const char COLLECT[] =
    "s() { echo; echo \"===$1===\"; }\n"
    "s INFO; date; cat /proc/uptime; getprop ro.build.fingerprint\n"
    "s PROPS; getprop\n"
    "s BOOTCONFIG; cat /proc/bootconfig\n"
    "s CMDLINE; cat /proc/cmdline\n"
    "s BYNAME; ls -l /dev/block/by-name\n"
    "s PARTITIONS; cat /proc/partitions\n"
    "s MOUNTS; cat /proc/mounts\n"
    "s DF; df -k /data /metadata /system /vendor\n"
    "s MODULES; cat /proc/modules\n"
    "s PS; ps -A -o PID,PPID,USER,S,RSS,NAME\n"
    "s PCI; for d in /sys/bus/pci/devices/*; do dr=$(readlink $d/driver); echo \"${d##*/} $(cat $d/vendor) "
    "$(cat $d/device) $(cat $d/class) ${dr##*/} $(cat $d/power_state 2>/dev/null) "
    "$(cat $d/power/runtime_status 2>/dev/null)\"; done\n"
    "s DRM; for c in /sys/class/drm/card*-*; do echo \"${c##*/} $(cat $c/status 2>/dev/null) "
    "$(cat $c/enabled 2>/dev/null) $(head -n 1 $c/modes 2>/dev/null)\"; done\n"
    "s BACKLIGHT; for b in /sys/class/backlight/*; do echo \"${b##*/} $(cat $b/brightness)/$(cat $b/max_brightness)\"; done\n"
    "s POWER; cat /sys/power/state /sys/power/mem_sleep /sys/devices/system/cpu/amd_pstate/status 2>&1; "
    "cat /sys/devices/system/cpu/cpufreq/policy0/scaling_driver "
    "/sys/devices/system/cpu/cpufreq/policy0/energy_performance_preference 2>&1\n"
    "s SUPPLY; for p in /sys/class/power_supply/*; do echo \"${p##*/}: $(cat $p/type) $(cat $p/status 2>/dev/null) "
    "$(cat $p/capacity 2>/dev/null)\"; done\n"
    "s NET; ip addr\n"
    "s WIFI; cmd wifi status 2>&1 | head -n 40\n"
    "s BLUETOOTH; dumpsys bluetooth_manager 2>&1 | head -n 30\n"
    "s INPUTDEV; cat /proc/bus/input/devices\n"
    "s INPUT; dumpsys input 2>&1 | head -n 200\n"
    "s DISPLAY; dumpsys display 2>&1 | head -n 150\n"
    "s SF; dumpsys SurfaceFlinger 2>&1 | head -n 250\n"
    "s WINDOW; dumpsys window displays 2>&1 | head -n 80\n"
    "s ACTIVITY; dumpsys activity activities 2>&1 | grep -E 'mResumed|ResumedActivity|mFocused' | head -n 20\n"
    "s BATTERY; dumpsys battery 2>&1\n"
    "s THERMAL; dumpsys thermalservice 2>&1 | head -n 60\n"
    "s AUDIO; dumpsys media.audio_flinger 2>&1 | head -n 40\n"
    "s FEATURES; pm list features 2>&1\n"
    "s SERVICES; service list 2>&1\n"
    "s AVC; dmesg | grep -c 'avc:  denied'; logcat -d -b all | grep -c 'avc:  denied'\n"
    "s END\n";

static const char *SUMMARY_PROPS[] = {
    "sys.boot_completed", "dev.bootcomplete", "ro.build.fingerprint", "ro.product.model", "ro.boot.openbook.live",
    "ro.boot.openbook.logs", "ro.boot.slot_suffix", "ro.boot.verifiedbootstate", "ro.boot.selinux", "ro.boot.hardware",
    "vendor.anybook.gpu.hal", "ro.hardware.egl", "ro.hardware.vulkan", "ro.hardware.gralloc",
    "ro.hardware.hwcomposer", "ro.sf.lcd_density", "init.svc.surfaceflinger", "init.svc.zygote", "init.svc.bootanim",
    "init.svc.vendor.openbook.dlkm", "init.svc.vendor.openbook.dgpu-pm", "init.svc.wpa_supplicant", "wifi.interface",
    "ro.crypto.state", "ro.crypto.type", "sys.system_server.start_count", "ro.boottime.init", NULL};

struct capture { char phase[16]; double at; int collect, logcat, screen, hwtest; };
static struct capture caps[4];
static int ncaps;
static double t_second = -1, t_complete = -1;
static unsigned long long dmesg_bytes;
static int dmesg_out = -1, kmsg_in = -1;

// Copy new kernel log records to dmesg.txt as "[seconds] message" (the /dev/kmsg record format is
// "prio,seq,usec,flags;message\n" plus " KEY=value" continuation lines, which are dropped).
static void drain_kmsg(void) {
    static char rec[8192];
    for (;;) {
        ssize_t n = read(kmsg_in, rec, sizeof rec - 1);
        if (n < 0 && errno == EPIPE) continue;  // overwritten records: carry on with the next one
        if (n <= 0) return;
        rec[n] = 0;
        char *semi = strchr(rec, ';');
        if (!semi) continue;
        unsigned long long usec = 0;
        sscanf(rec, "%*u,%*u,%llu", &usec);
        char *msg = semi + 1, *nl = strchr(msg, '\n');
        if (nl) *nl = 0;
        char out[8400];
        int m = snprintf(out, sizeof out, "[%5llu.%06llu] %s\n", usec / 1000000, usec % 1000000, msg);
        if (m > (int)sizeof out - 1) m = sizeof out - 1;
        if (dmesg_bytes < (64ull << 20) && !pwrite_all(dmesg_out, out, m, dmesg_bytes)) dmesg_bytes += m;
    }
}

static int second_stage_running(void) {
    char buf[256];
    int fd = openat(procfd, "1/cmdline", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;
    ssize_t n = read(fd, buf, sizeof buf - 1);
    close(fd);
    if (n <= 0) return 0;
    return memmem(buf, n, "second_stage", 12) != NULL;
}

// What earlier boots left on /data: logcat with the kernel log persisted by logcatd (persist.logd.logpersistd on
// userdebug, device/anybook/common/pc/pc.mk), tombstones, ANR traces and dropbox. The only trace of boots that saved
// no logs themselves, such as the enforcing entries' (ANAL-176). Capped at 96 MiB; a cut archive still unpacks.
// The exit status is the whole pipeline's: non-zero when tar or gzip failed or the cap cut the archive (SIGPIPE), 4
// when none of the directories exists. stderr would land in the archive, hence the 2>/dev/null. prior-boots.txt
// lists each directory's size and file count, or "missing".
#define PRIOR_CAP 100663296  // 96 MiB
#define STR_(x) #x
#define STR(x) STR_(x)
static const char PRIOR_BOOTS[] =
    "cd /data 2>/dev/null || exit 3; L=; for d in misc/logd tombstones anr system/dropbox; do [ -d $d ] && L=\"$L $d\"; "
    "done; [ -n \"$L\" ] || exit 4; set -o pipefail; tar -cf - $L 2>/dev/null | gzip -c 2>/dev/null | "
    "head -c " STR(PRIOR_CAP);
static const char PRIOR_LIST[] =
    "cd /data && for d in misc/logd tombstones anr system/dropbox; do if [ -d $d ]; then "
    "echo \"$d $(du -sk $d | cut -f1) KiB, $(find $d -type f | wc -l) files\"; else echo \"$d missing\"; fi; done";
static int prior_done, prior_rc = -2;  // -2: not attempted
static long long prior_bytes = -1;

static void capture(const char *phase) {
    struct statfs s;
    if (!fstatfs(logdir, &s) && (unsigned long long)s.f_bavail * s.f_bsize < 24 * MiB) {
        say("logs: less than 24 MiB free on the ESP; skipping the %s capture", phase);
        return;
    }
    struct capture *c = &caps[ncaps < 4 ? ncaps++ : 3];
    snprintf(c->phase, sizeof c->phase, "%s", phase);
    c->at = uptime_s();
    char f[64];
    say("logs: %s capture at %.0f s", phase, c->at);
    // The final capture first runs the userdebug product's Wi-Fi, Bluetooth and audio checks, so the logcat and
    // system facts below include what they did. -1: not run (early capture, or a product without the tool).
    c->hwtest = -1;
    if (!strcmp(phase, "final")) {
        run_env = hwtest_env;
        c->hwtest = run_to_file("[ -x /system_ext/bin/openbook-hwtest ] || exit 127; /system_ext/bin/openbook-hwtest",
                                "hwtest-final.txt", 360);
        run_env = ANDROID_ENV;
        drain_kmsg();
    }
    snprintf(f, sizeof f, "collect-%s.txt", phase);
    c->collect = run_to_file(COLLECT, f, 240);
    snprintf(f, sizeof f, "logcat-%s.txt", phase);
    c->logcat = run_to_file("logcat -d -b all -v threadtime", f, 120);
    snprintf(f, sizeof f, "screen-%s.png", phase);
    c->screen = run_to_file("screencap -p", f, 60);
    if (!prior_done) {  // once, at the first capture
        prior_done = 1;
        run_to_file(PRIOR_LIST, "prior-boots.txt", 30);
        prior_rc = run_to_file(PRIOR_BOOTS, "prior-boots.tar.gz", 180);
        struct stat st;
        if (!fstatat(logdir, "prior-boots.tar.gz", &st, 0)) prior_bytes = st.st_size;
    }
    drain_kmsg();
    fsync(dmesg_out);
}

static void write_summary(const char *after) {
    struct sb b = {0};
    sb_printf(&b, "{\n \"schema\": \"openbook-live-logs/1\",\n \"dir\": \"%s\",\n \"uptime_s\": %.1f,\n", logdir_name,
              uptime_s());
    sb_printf(&b, " \"second_stage_s\": %.1f,\n \"boot_completed\": %s,\n \"boot_completed_s\": %.1f,\n", t_second,
              t_complete >= 0 ? "true" : "false", t_complete);
    sb_printf(&b, " \"dmesg_bytes\": %llu,\n \"after\": \"%s\",\n \"prior_boots_rc\": %d,\n \"prior_boots_bytes\": %lld,\n"
                  " \"prior_boots_capped\": %s,\n \"live_init\": ", dmesg_bytes, after, prior_rc, prior_bytes,
              prior_bytes == PRIOR_CAP ? "true" : "false");
    result_json(&b);
    SB_LIT(&b, ",\n \"captures\": [");
    for (int i = 0; i < ncaps; i++)
        sb_printf(&b, "%s\n  {\"phase\": \"%s\", \"uptime_s\": %.1f, \"collect_rc\": %d, \"logcat_rc\": %d, "
                      "\"screencap_rc\": %d, \"hwtest_rc\": %d}", i ? "," : "", caps[i].phase, caps[i].at,
                  caps[i].collect, caps[i].logcat, caps[i].screen, caps[i].hwtest);
    SB_LIT(&b, "\n ],\n \"props\": {");
    for (int i = 0; SUMMARY_PROPS[i]; i++) {
        char cmd[128], v[512];
        snprintf(cmd, sizeof cmd, "getprop %s", SUMMARY_PROPS[i]);
        if (run_android(cmd, -1, v, sizeof v, 20) < 0) v[0] = 0;
        sb_printf(&b, "%s\n  \"%s\": ", i ? "," : "", SUMMARY_PROPS[i]);
        sb_json_str(&b, v);
    }
    SB_LIT(&b, "\n }\n}\n");
    if (write_at(logdir, "summary.json", b.p, b.n)) say("logs: writing summary.json failed (%s)", strerror(errno));
    free(b.p);
}

// openbook/hwtest.conf on the ESP: "key=value" lines the owner or a device agent writes (e.g.
// iperf3_server=192.168.1.20), passed to openbook-hwtest as OPENBOOK_HWTEST_<KEY>. Keys [a-z0-9_], values
// [A-Za-z0-9.:_-] only, at most HWTEST_MAX; anything else is skipped. Never put credentials there: the file is
// plain text on the stick.
static void read_hwtest_conf(void) {
    static char store[HWTEST_MAX][128];
    int n = 0, e = 0;
    while (ANDROID_ENV[e]) { hwtest_env[e] = ANDROID_ENV[e]; e++; }
    hwtest_env[e] = NULL;
    int fd = openat(espfd, "openbook/hwtest.conf", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return;
    char buf[4096];
    ssize_t len = read(fd, buf, sizeof buf - 1);
    close(fd);
    if (len <= 0) return;
    buf[len] = 0;
    for (char *line = strtok(buf, "\r\n"); line && n < HWTEST_MAX; line = strtok(NULL, "\r\n")) {
        char *eq = strchr(line, '=');
        if (line[0] == '#' || !eq || eq == line || eq - line > 32 || strlen(eq + 1) > 64) continue;
        int good = 1;
        for (char *k = line; k < eq; k++) good &= (*k >= 'a' && *k <= 'z') || (*k >= '0' && *k <= '9') || *k == '_';
        for (char *v = eq + 1; *v; v++)
            good &= (*v >= 'A' && *v <= 'Z') || (*v >= 'a' && *v <= 'z') || (*v >= '0' && *v <= '9') || *v == '.' ||
                    *v == ':' || *v == '_' || *v == '-';
        if (!good) continue;
        int m = snprintf(store[n], sizeof store[n], "OPENBOOK_HWTEST_");
        for (char *k = line; k < eq && m < (int)sizeof store[n] - 1; k++) store[n][m++] = (char)toupper((unsigned char)*k);
        snprintf(store[n] + m, sizeof store[n] - m, "=%s", eq + 1);
        hwtest_env[e++] = store[n++];
        hwtest_env[e] = NULL;
    }
    say("logs: %d setting(s) from openbook/hwtest.conf", n);
}

// The helper process. Runs alongside Android until the final capture, then asks Android to shut down.
static void logs_helper(int ready_fd, const char *esp_node) {
    setsid();
    for (int fd = 0; fd < 3; fd++) close(fd);
    kmsg_in = open(WORK "/kmsg", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    espfd = esp_mount_fd(esp_node);
    int pfs = fsopen("proc", FSOPEN_CLOEXEC);
    if (pfs >= 0 && !fsconfig(pfs, FSCONFIG_CMD_CREATE, NULL, NULL, 0)) procfd = fsmount(pfs, FSMOUNT_CLOEXEC, 0);
    if (pfs >= 0) close(pfs);
    // Read the settings now: /proc is unmounted once the parent execs Android's init.
    long timeout = conf_long("androidboot.openbook.logs_timeout", 600);  // after second stage starts
    long settle = conf_long("androidboot.openbook.logs_settle", 45);     // after sys.boot_completed=1
    char after[16] = "poweroff";
    conf_get("androidboot.openbook.logs_after", after, sizeof after);
    if (strcmp(after, "reboot") && strcmp(after, "stay")) snprintf(after, sizeof after, "poweroff");
    int ok = kmsg_in >= 0 && espfd >= 0 && procfd >= 0 && !mkdir_free(espfd, "live-", logdir_name, sizeof logdir_name);
    if (ok) logdir = openat(espfd, logdir_name, O_DIRECTORY | O_CLOEXEC);
    if (ok && logdir >= 0) dmesg_out = openat(logdir, "dmesg.txt", O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
    ok = ok && logdir >= 0 && dmesg_out >= 0;
    if (!ok) say("logs: setup failed (kmsg %d, esp %d, proc %d, dir %d: %s); no logs this boot", kmsg_in, espfd,
                 procfd, logdir, strerror(errno));
    else say("logs: saving to %s on the stick's ESP", logdir_name);
    if (ok) read_hwtest_conf();
    if (write(ready_fd, ok ? "1" : "0", 1) < 0) { /* the parent goes on after a timeout */ }
    close(ready_fd);
    if (!ok) _exit(1);

    double t_start = uptime_s(), t_check = 0, t_sync = 0;
    int early_done = 0;
    for (;;) {
        drain_kmsg();
        double now = uptime_s();
        if (now - t_sync >= 5) { fsync(dmesg_out); t_sync = now; }
        if (t_second < 0) {
            if (second_stage_running()) { t_second = now; say("logs: Android second stage seen at %.0f s", now); }
            else if (now - t_start > timeout) { say("logs: no second stage after %ld s", timeout); break; }
        } else if (t_complete < 0) {
            if (now - t_check >= 10 && now - t_second >= 15) {
                char v[32];
                t_check = now;
                if (run_android("getprop sys.boot_completed", -1, v, sizeof v, 20) == 0 && !strcmp(v, "1")) {
                    t_complete = now;
                    say("logs: sys.boot_completed=1 at %.0f s", now);
                }
            }
            if (t_complete < 0 && !early_done && now - t_second >= 90) { capture("early"); early_done = 1; }
            if (t_complete < 0 && now - t_second >= timeout) { say("logs: boot not completed after %ld s", timeout); break; }
        } else if (now - t_complete >= settle) {
            break;
        }
        usleep(500000);
    }
    capture("final");
    write_summary(after);
    say("logs: done: %s (dmesg %llu bytes, %d capture(s))", logdir_name, dmesg_bytes, ncaps);
    drain_kmsg();
    fsync(dmesg_out);
    close(dmesg_out);
    close(logdir);
    close(espfd);  // the last reference: the detached vfat mount is cleanly unmounted here
    if (strcmp(after, "stay")) {
        int rb = !strcmp(after, "reboot");
        sleep(2);
        run_android(rb ? "setprop sys.powerctl reboot,openbook-logs-saved" : "setprop sys.powerctl shutdown,openbook-logs-saved",
                    -1, NULL, 0, 20);
        sleep(120);  // Android's own shutdown normally ends this process first
        say("logs: Android did not %s; doing it now", rb ? "reboot" : "shut down");
        sync();
        reboot(rb ? RB_AUTOBOOT : RB_POWER_OFF);
    }
    _exit(0);
}

// ------------------------------------------------------------------ main

static int open_image(const char *path, uint64_t *sectors) {
    int fd = open(path, O_RDWR | O_CLOEXEC);
    struct stat st;
    if (fd < 0 || fstat(fd, &st) || !S_ISREG(st.st_mode)) { fprintf(stderr, "%s: not a regular file\n", path); return -1; }
    *sectors = st.st_size / 512;
    return fd;
}

static int host_test(int argc, char **argv) {
    uint64_t sectors;
    int fd = open_image(argv[2], &sectors);
    if (fd < 0) return 2;
    snprintf(R.action, sizeof R.action, "none");
    int rc;
    if (!strcmp(argv[1], "--reset-test")) {
        rc = live_reset(fd, sectors, NULL);
        if (!rc) snprintf(R.action, sizeof R.action, "reset");
    } else {
        int pno;
        uint64_t s, n;
        rc = gpt_grow(fd, sectors, argc > 3 ? argv[3] : NULL, &pno, &s, &n);
        if (rc < 0) snprintf(R.action, sizeof R.action, "error");
    }
    close(fd);
    struct sb b = {0};
    result_json(&b);
    printf("%s\n", b.p);
    free(b.p);
    return rc < 0 ? 1 : 0;
}

int main(int argc, char **argv) {
    if (argc >= 3 && (!strcmp(argv[1], "--gpt-test") || !strcmp(argv[1], "--reset-test"))) return host_test(argc, argv);
    if (getpid() != 1) { fprintf(stderr, "openbook-live-init runs as rdinit= (PID 1); see --gpt-test\n"); return 2; }
    snprintf(R.action, sizeof R.action, "none");
    mkdir("/proc", 0555);
    mkdir("/sys", 0555);
    int own_proc = !mount("proc", "/proc", "proc", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL);
    int own_sys = !mount("sysfs", "/sys", "sysfs", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL);
    mkdir(WORK, 0700);
    mknod(WORK "/kmsg", S_IFCHR | 0600, makedev(1, 11));
    mknod(WORK "/null", S_IFCHR | 0666, makedev(1, 3));
    kmsg_fd = open(WORK "/kmsg", O_WRONLY | O_CLOEXEC);

    char live[8], reset[8], logs[8], uuid[64];
    conf_get("androidboot.openbook.live", live, sizeof live);
    conf_get("androidboot.openbook.live_reset", reset, sizeof reset);
    conf_get("androidboot.openbook.logs", logs, sizeof logs);
    conf_get("androidboot.boot_part_uuid", uuid, sizeof uuid);
    int logs_pid = -1;
    if (strcmp(live, "1")) {
        say("not a live boot (androidboot.openbook.live=%s); nothing to do", live[0] ? live : "unset");
        goto exec_init;
    }
    say("live boot: boot_part_uuid=%s reset=%s logs=%s", uuid[0] ? uuid : "unset", reset[0] ? reset : "0",
        logs[0] ? logs : "0");
    if (!uuid[0]) { snprintf(R.action, sizeof R.action, "skipped"); say("no boot_part_uuid; nothing to do"); goto exec_init; }

    // USB storage enumerates asynchronously: wait (max 20 s) for the ESP, like Android's ueventd would.
    char part[64] = "";
    double t0 = uptime_s();
    int found = 0;
    for (int i = 0; i < 200 && (found = find_uevent("PARTUUID", uuid, part, sizeof part)) <= 0; i++) usleep(100000);
    if (found != 1) {
        snprintf(R.action, sizeof R.action, "skipped");
        say("%d partition(s) with PARTUUID %s after %.1f s; touching nothing", found < 0 ? 0 : found, uuid,
            uptime_s() - t0);
        goto exec_init;
    }
    char link[512] = "", p[600];
    snprintf(p, sizeof p, "/sys/class/block/%s", part);
    ssize_t n = readlink(p, link, sizeof link - 1);
    if (n > 0) link[n] = 0;
    char *slash = strrchr(link, '/');
    char disk[32] = "";
    if (slash) {  // .../block/<disk>/<part>
        *slash = 0;
        char *d = strrchr(link, '/');
        if (d) snprintf(disk, sizeof disk, "%s", d + 1);
        *slash = '/';
    }
    snprintf(R.disk, sizeof R.disk, "%s", disk);
    say("boot ESP %s on disk %s (%.1f s): %s", part, disk, uptime_s() - t0, link);
    if (!strstr(link, "/usb") || !disk[0]) {
        snprintf(R.action, sizeof R.action, "skipped");
        say("the boot disk is not on USB; a live stick only changes itself, so touching nothing");
        goto exec_init;
    }
    snprintf(p, sizeof p, "/sys/class/block/%s/queue/logical_block_size", disk);
    unsigned long long lbs = read_ull(p);
    snprintf(p, sizeof p, "/sys/class/block/%s/size", disk);
    unsigned long long sectors = read_ull(p);
    snprintf(p, sizeof p, "/sys/class/block/%s/ro", disk);
    if (lbs != 512 || !sectors || read_ull(p)) {
        snprintf(R.action, sizeof R.action, "skipped");
        say("disk %s: logical block size %llu, %llu sectors, ro %llu: not handled; touching nothing", disk, lbs, sectors,
            read_ull(p));
        goto exec_init;
    }
    if (make_node(disk, WORK "/disk")) { say("mknod for %s failed (%s)", disk, strerror(errno)); goto exec_init; }
    int fd = open(WORK "/disk", O_RDWR | O_CLOEXEC);
    if (fd < 0) { say("open %s failed (%s)", disk, strerror(errno)); goto exec_init; }

    int changed = 0;
    if (!strcmp(reset, "1")) {
        if (!live_reset(fd, sectors, uuid)) { snprintf(R.action, sizeof R.action, "reset"); changed = 1; }
    }
    int pno;
    uint64_t ud_start, ud_sectors;
    int g = gpt_grow(fd, sectors, uuid, &pno, &ud_start, &ud_sectors);
    if (g > 0) {
        reload_partitions(fd, pno, ud_start, ud_sectors);
        changed = 1;
        if (R.reset_done) snprintf(R.action, sizeof R.action, "reset+%s", R.userdata_new_sectors != R.userdata_old_sectors ? "grow" : "repair");
    } else if (g < 0) {
        snprintf(R.action, sizeof R.action, "error");
        changed = 1;
    }
    close(fd);

    // The ESP may have a new device number after a re-read: look it up again.
    char esp[64] = "";
    if (find_uevent("PARTUUID", uuid, esp, sizeof esp) == 1 && !make_node(esp, WORK "/esp")) {
        if (changed) save_action_report(WORK "/esp");
        if (!strcmp(logs, "1")) {
            int pipefd[2];
            if (!pipe2(pipefd, O_CLOEXEC)) {
                logs_pid = fork();
                if (logs_pid == 0) {
                    close(pipefd[0]);
                    logs_helper(pipefd[1], WORK "/esp");
                }
                close(pipefd[1]);
                struct pollfd pf = {.fd = pipefd[0], .events = POLLIN};
                char c = '0';
                if (poll(&pf, 1, 5000) > 0 && read(pipefd[0], &c, 1) == 1 && c == '1')
                    say("logs helper running (pid %d)", logs_pid);
                close(pipefd[0]);
            }
        }
    } else {
        say("ESP %s not found again after the partition re-read", uuid);
    }

exec_init:
    say("exec /init (%s)", R.action);
    if (kmsg_fd >= 0) close(kmsg_fd);
    unlink(WORK "/kmsg");
    unlink(WORK "/null");
    unlink(WORK "/disk");
    unlink(WORK "/esp");
    rmdir(WORK);
    if (own_sys) umount("/sys");
    if (own_proc) umount("/proc");
    argv[0] = (char *)"/init";
    execv("/init", argv);
    return 127;
}
