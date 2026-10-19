// SPDX-License-Identifier: Apache-2.0
// Ruby live diagnostics. PID 1 saves an early checkpoint, then execs Android.
// A separate, enforcing vendor domain saves kernel + shell diagnostics later.
// Only the bootconfig-selected USB ESP is opened for writing, briefly O_EXCL;
// no mounts, partition edits, data access, firmware writes or shell execution.
#include "common.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <stdlib.h>
#include <string.h>
#include <sys/klog.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <time.h>
#include <unistd.h>

#define CHUNK (256 * 1024)
#define LIMIT (48 * MiB)
#define SECONDS 600
#define FIFO "/dev/ruby-log-stream"
static char node[256], session[100];
static uint64_t esp_size, saved;
static unsigned seq;

static int field(const char *text, const char *key, const char *value) {
    size_t k = strlen(key), v = strlen(value);
    int matches = 0;
    for (const char *p = text; p && *p; p = strchr(p, '\n') ? strchr(p, '\n') + 1 : NULL) {
        size_t n = strcspn(p, "\n");
        if (n == k + 1 + v && !strncmp(p, key, k) && p[k] == '=' && !strncasecmp(p + k + 1, value, v))
            matches++;
    }
    return matches == 1;
}

static double clock_s(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}

static int config(const char *key, char *out, size_t size) {
    FILE *f = fopen("/proc/bootconfig", "re");
    if (!f) return -1;
    char line[1024], name[256], value[256];
    int count = 0;
    while (fgets(line, sizeof line, f)) {
        if (sscanf(line, "%255s = \"%255[^\"]\"", name, value) == 2 && !strcmp(name, key)) {
            if (strlen(value) >= size) { fclose(f); return -1; }
            memcpy(out, value, strlen(value) + 1);
            count++;
        }
    }
    fclose(f);
    return count == 1 ? 0 : -1;
}

// Exactly one PARTUUID match, explicitly EFI on USB; never infer from sda or
// partition names alone. Sysfs reads occur again before each open/write.
static int select_esp(int early) {
    char uuid[64], live[8], logs[8];
    uint8_t guid[16];
    if (config("androidboot.boot_part_uuid", uuid, sizeof uuid) || guid_from_str(uuid, guid) ||
        config("androidboot.openbook.live", live, sizeof live) || strcmp(live, "1") ||
        config("androidboot.openbook.ruby_logs", logs, sizeof logs) || strcmp(logs, "1")) return -1;
    DIR *d = opendir("/sys/class/block");
    if (!d) return -1;
    struct dirent *e;
    int matches = 0, valid = 0;
    char picked[256] = "";
    while ((e = readdir(d))) {
        char path[512], text[4096], link[PATH_MAX];
        if (e->d_name[0] == '.') continue;
        snprintf(path, sizeof path, "/sys/class/block/%s", e->d_name);
        if (!realpath(path, link) || strstr(link, "/devices/virtual/")) continue;
        // Loop, dm and RAM devices cannot be our physical USB ESP. Do not
        // query their unrelated uevents (or generate denied-read log storms).
        snprintf(path, sizeof path, "/sys/class/block/%s/uevent", e->d_name);
        if (read_text(path, text, sizeof text)) continue;
        if (!field(text, "PARTUUID", uuid)) continue;
        matches++;
        if (!field(text, "PARTNAME", "EFI") || strlen(e->d_name) > 63) continue;
        if (!strstr(link, "/usb")) continue;
        snprintf(path, sizeof path, "/sys/class/block/%s/size", e->d_name);
        if (read_text(path, text, sizeof text)) continue;
        esp_size = strtoull(text, NULL, 10) * 512;
        if (esp_size != 256 * MiB) continue; // pinned research layout
        snprintf(path, sizeof path, "/sys/class/block/%s/dev", e->d_name);
        unsigned maj, min;
        if (read_text(path, text, sizeof text) || sscanf(text, "%u:%u", &maj, &min) != 2) continue;
        if (early) {
            snprintf(picked, sizeof picked, "/ruby-log-work/esp");
            unlink(picked);
            if (mknod(picked, S_IFBLK | 0600, makedev(maj, min))) continue;
        } else {
            snprintf(picked, sizeof picked, "/dev/block/by-name/EFI");
            struct stat st;
            if (stat(picked, &st) || !S_ISBLK(st.st_mode) || st.st_rdev != makedev(maj, min)) continue;
        }
        valid++;
    }
    closedir(d);
    if (matches != 1 || valid != 1) return -1;
    snprintf(node, sizeof node, "%s", picked);
    return 0;
}

static int save_fat(struct fat *f, const char *name, const void *data, size_t len) {
    if (len > CHUNK || saved + len > LIMIT) return -1;
    uint32_t n = 0;
    char *manifest = (char *)fat_read(f, "ruby/RESEARCH.json", &n);
    const char schema[] = "\"schema\": \"openbook-ruby-live-research/1\"";
    const char local[] = "\"installable\": false";
    int ok = manifest && n < 65536 && memmem(manifest, n, schema, sizeof schema - 1) &&
        memmem(manifest, n, local, sizeof local - 1);
    free(manifest);
    char path[160];
    snprintf(path, sizeof path, "%s/%s", session, name);
    // New immutable chunks; never prune old sessions or consume boot reserve.
    if (!ok || fat_free_bytes(f) < 32 * MiB + len || fat_exists(f, path, NULL)) return -1;
    return fat_replace(f, path, data, len);
}

static int save(const char *name, const void *data, size_t len, int early) {
    if (len > CHUNK || saved + len > LIMIT || select_esp(early)) return -1;
    int fd = open(node, O_RDWR | O_EXCL | O_CLOEXEC);
    if (fd < 0) return -1; // mounted/held ESP is refused, including bootsync
    struct fat f;
    int rc = fat_open(&f, fd, 0, esp_size);
    if (!rc) {
        rc = save_fat(&f, name, data, len);
        if (!rc) rc = fat_flush(&f);
        if (!rc) rc = fsync(fd);
        fat_close(&f);
    }
    close(fd);
    if (!rc) saved += len;
    return rc;
}

static int session_id(void) {
    char id[64];
    uint8_t guid[16];
    if (read_text("/proc/sys/kernel/random/boot_id", id, sizeof id) || guid_from_str(id, guid)) return -1;
    snprintf(session, sizeof session, "openbook/logs/ruby-%s", id);
    return 0;
}

static void early(void) {
    mkdir("/proc", 0555); mkdir("/sys", 0555); mkdir("/ruby-log-work", 0700);
    int proc = !mount("proc", "/proc", "proc", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL);
    int sys = !mount("sysfs", "/sys", "sysfs", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL);
    double deadline = clock_s() + 20;
    int ready;
    while ((ready = select_esp(1)) && clock_s() < deadline) usleep(100000);
    if (!ready && !session_id()) {
        struct sb b = {0};
        sb_puts(&b, "Ruby diagnostic PID 1 reached; Android init is next.\n");
        char text[32768];
        const char *paths[] = {"/proc/cmdline", "/proc/bootconfig", "/proc/cpuinfo", NULL};
        for (int i = 0; paths[i]; i++) {
            if (!read_text(paths[i], text, sizeof text)) sb_printf(&b, "\n=== %s ===\n%s\n", paths[i], text);
        }
        save("early.txt", b.p, b.n, 1);
        sb_free(&b);
        char *buf = malloc(CHUNK);
        int n = buf ? klogctl(3, buf, CHUNK) : -1;
        if (n > 0) save("early-kernel.txt", buf, n, 1);
        free(buf);
    }
    unlink("/ruby-log-work/esp"); rmdir("/ruby-log-work");
    if (sys) umount("/sys");
    if (proc) umount("/proc");
    char *args[] = {"/init", NULL};
    execv(args[0], args);
    // PID 1 must not exit if Android init is missing.
    for (;;) pause();
}

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--early") && getpid() == 1) early();
    // rdinit receives no extra argv; production vendor service gets --collect.
    if (getpid() == 1) early();
    if (argc != 2 || strcmp(argv[1], "--collect") || session_id() || select_esp(0)) return 2;
    // Charge the maximum early-checkpoint size to this same session budget.
    saved = 2 * CHUNK;
    // One collector per boot; refuse any pre-existing inode or symlink.
    if (mkfifo(FIFO, 0666)) return 3;
    if (chmod(FIFO, 0666)) return 3;
    struct stat st;
    if (lstat(FIFO, &st) || !S_ISFIFO(st.st_mode)) return 3;
    int input = open(FIFO, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    int kernel = open("/dev/kmsg", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    char status[256];
    snprintf(status, sizeof status, "Collector started; kernel_fd=%d android_fd=%d; limit=48MiB timeout=600s\n", kernel, input);
    if (save("collector.txt", status, strlen(status), 0)) return 4;
    if (input < 0 || kernel < 0) return 5;
    struct sb buffers[2] = {{0}, {0}};
    struct pollfd fds[2] = {{kernel, POLLIN, 0}, {input, POLLIN, 0}};
    double start = clock_s(), flush = start;
    unsigned dropped = 0, failures = 0;
    while (clock_s() - start < SECONDS && saved < LIMIT - 2 * CHUNK) {
        poll(fds, 2, 200);
        for (int i = 0; i < 2; i++) {
            char buf[8192];
            ssize_t n = 0;
            while (buffers[i].n <= CHUNK - sizeof buf && (n = read(fds[i].fd, buf, sizeof buf)) > 0) {
                sb_add(&buffers[i], buf, n);
            }
            if (n < 0 && errno == EPIPE) dropped++; // overwritten kernel ring records
        }
        if (clock_s() - flush >= 5 || buffers[0].n > CHUNK - 8192 || buffers[1].n > CHUNK - 8192) {
            for (int i = 0; i < 2; i++) if (buffers[i].n) {
                char name[64];
                snprintf(name, sizeof name, "%s-%05u.txt", i ? "android" : "kernel", seq++);
                if (save(name, buffers[i].p, buffers[i].n, 0)) {
                    // Retain this chunk in RAM and retry without holding the ESP.
                    failures++; seq--; continue;
                }
                buffers[i].n = 0;
            }
            flush = clock_s();
        }
        // A FIFO with no writer reports POLLHUP immediately. Avoid busy spinning.
        usleep(20000);
    }
    for (int i = 0; i < 2; i++) if (buffers[i].n) {
        char name[64];
        snprintf(name, sizeof name, "%s-%05u.txt", i ? "android" : "kernel", seq++);
        if (save(name, buffers[i].p, buffers[i].n, 0)) failures++;
        else buffers[i].n = 0;
    }
    snprintf(status, sizeof status, "Capture finished after %.1fs; collector_bytes=%llu; kernel_overruns=%u; "
             "failed_save_attempts=%u; unsaved_bytes=%zu; reason=%s.\n",
             clock_s() - start, (unsigned long long)(saved - 2 * CHUNK), dropped, failures,
             buffers[0].n + buffers[1].n, saved >= LIMIT - 2 * CHUNK ? "byte-limit" : "timeout");
    save("complete.txt", status, strlen(status), 0);
    return 0;
}
