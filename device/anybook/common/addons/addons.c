// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// openbook-addons: installs the optional app add-ons (ANAL-210, docs/gapps.md section 6) that the boot disk carries.
//
// An add-on is a set of APKs the image itself names and pins: /system_ext/etc/openbook/addons/<name>.json lists each
// file with its package, versionCode and sha256 (device/anybook/common/addons/). The APKs travel outside the image,
// on the boot disk's EFI partition in openbook/addons/<name>/ (scripts/microg/add-to-image.sh puts them on a stick;
// the installer carries them to the installed disk when the user ticks the add-on). After every boot (init starts
// this once sys.boot_completed=1) it looks for each catalogued add-on there:
//   - not there: nothing happens, the system is exactly as without add-ons;
//   - there, and /data/misc/openbook_addons/<name>.json says this version is installed: nothing happens (an app the
//     user uninstalled stays uninstalled);
//   - there and new: every file is read and checked against the image's sha256 first; one mismatch refuses the whole
//     add-on. Then each package is installed as a normal app in /data through PackageManager (`cmd package`
//     install-create/-write/-commit, the bytes streamed over a pipe), unless the same or a newer version is already
//     installed, and gets the runtime permissions, app-ops and battery-optimisation exemption the catalogue lists.
// The EFI partition is only read, through the whole-disk node at the partition's offset (no mount).
//
//   openbook-addons [--catalog DIR] [--state DIR] [--boot-part-uuid UUID] [--disk FILE]... [--from-dir DIR]
//                   [--cmd PATH] [--log FILE] [--json FILE] [--force] run|status
// --disk: disks to search instead of /dev/block's whole disks (host tests: image files). --from-dir: take the APKs
// from DIR/<name>/ instead of the EFI partition (adb-driven tests on Cuttlefish, which has no OpenBook ESP).
// --cmd: the `cmd` binary (host tests: a fake). --json: the result there instead of on stdout. Exit 0 unless an
// add-on that is present failed or was refused.
#include "common.h"

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/fs.h>
#include <signal.h>
#include <spawn.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static const char *g_catalog = "/system_ext/etc/openbook/addons";
static const char *g_state = "/data/misc/openbook_addons";
static const char *g_cmd = "/system/bin/cmd";
static const char *g_from_dir;
static const char *g_disks[16];
static int g_ndisks, g_force;

// ------------------------------------------------------------------ the boot disk's EFI partition
struct esp {
    int fd;
    struct fat fat;
    int open;
    char dev[PATH_MAX];
};

static int try_disk(const char *path, struct esp *e) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    struct stat st;
    uint32_t sector = 512;
    uint64_t bytes = 0;
    if (fstat(fd, &st) == 0 && S_ISBLK(st.st_mode)) {
        int ss = 0;
        if (ioctl(fd, BLKSSZGET, &ss) == 0 && ss > 0) sector = ss;
        if (ioctl(fd, BLKGETSIZE64, &bytes)) bytes = 0;
    } else if (fstat(fd, &st) == 0) {
        bytes = st.st_size;
    }
    struct gpt g;
    memset(&g, 0, sizeof g);
    if (!bytes || gpt_read(fd, sector, bytes / sector, &g)) {
        gpt_free(&g);
        close(fd);
        return -1;
    }
    const struct gpt_part *p = gpt_find_uuid(&g, E.boot_part_uuid);
    if (!p) {
        gpt_free(&g);
        close(fd);
        return -1;
    }
    uint64_t off = p->first * sector, size = (p->last - p->first + 1) * sector;
    gpt_free(&g);
    if (fat_open(&e->fat, fd, off, size)) {
        LOG("%s: the boot partition %s is not FAT", path, E.boot_part_uuid);
        close(fd);
        return -1;
    }
    e->fd = fd;
    e->open = 1;
    snprintf(e->dev, sizeof e->dev, "%s", path);
    return 0;
}

static int whole_disk_name(const char *n) {
    size_t k;
    if (!strncmp(n, "sd", 2) || !strncmp(n, "vd", 2)) {
        for (k = 2; n[k]; k++)
            if (n[k] < 'a' || n[k] > 'z') return 0;
        return k > 2;
    }
    if (!strncmp(n, "nvme", 4)) {  // nvme<N>n<M>, no partition suffix
        const char *p = n + 4;
        if (!isdigit((unsigned char)*p)) return 0;
        while (isdigit((unsigned char)*p)) p++;
        if (*p++ != 'n' || !isdigit((unsigned char)*p)) return 0;
        while (isdigit((unsigned char)*p)) p++;
        return *p == 0;
    }
    if (!strncmp(n, "mmcblk", 6)) {
        const char *p = n + 6;
        if (!isdigit((unsigned char)*p)) return 0;
        while (isdigit((unsigned char)*p)) p++;
        return *p == 0;
    }
    return 0;
}

static int esp_find(struct esp *e) {
    memset(e, 0, sizeof *e);
    e->fd = -1;
    if (!E.boot_part_uuid[0]) {
        LOG("no androidboot.boot_part_uuid: not booted from an OpenBook disk");
        return -1;
    }
    for (int i = 0; i < g_ndisks; i++)
        if (!try_disk(g_disks[i], e)) return 0;
    if (g_ndisks) return -1;
    DIR *d = opendir("/dev/block");
    if (!d) {
        LOG("/dev/block: %s", strerror(errno));
        return -1;
    }
    struct dirent *de;
    int rc = -1;
    while (rc && (de = readdir(d))) {
        if (!whole_disk_name(de->d_name)) continue;
        char path[PATH_MAX];
        snprintf(path, sizeof path, "/dev/block/%s", de->d_name);
        rc = try_disk(path, e);
    }
    closedir(d);
    if (rc) LOG("no disk holds the boot partition %s", E.boot_part_uuid);
    return rc;
}

static void esp_close(struct esp *e) {
    if (!e->open) return;
    free(e->fat.fatbuf);
    close(e->fd);
    e->open = 0;
}

// The add-on's directory on the source: 1 present, 0 absent.
static int source_has(struct esp *e, const char *name) {
    char p[PATH_MAX];
    if (g_from_dir) {
        struct stat st;
        snprintf(p, sizeof p, "%s/%s", g_from_dir, name);
        return !stat(p, &st) && S_ISDIR(st.st_mode);
    }
    int is_dir = 0;
    snprintf(p, sizeof p, "openbook/addons/%s", name);
    return e->open && fat_exists(&e->fat, p, &is_dir) == 1 && is_dir;
}

static uint8_t *source_read(struct esp *e, const char *name, const char *file, size_t *len) {
    char p[PATH_MAX];
    if (g_from_dir) {
        snprintf(p, sizeof p, "%s/%s/%s", g_from_dir, name, file);
        return (uint8_t *)read_file(p, len);
    }
    uint32_t n = 0;
    snprintf(p, sizeof p, "openbook/addons/%s/%s", name, file);
    uint8_t *b = fat_read(&e->fat, p, &n);
    *len = n;
    return b;
}

// ------------------------------------------------------------------ cmd (PackageManager, app-ops, deviceidle)
// Runs `cmd ARGS...`, feeding IN (may be NULL) on stdin; stdout and stderr together into OUT (NUL-terminated).
// Returns the exit status, or -1.
static int run_cmd(const uint8_t *in, size_t inlen, char *out, size_t outlen, const char *const *args) {
    const char *argv[24];
    int n = 0;
    argv[n++] = g_cmd;
    for (int i = 0; args[i] && n < (int)ARRAY_LEN(argv) - 1; i++) argv[n++] = args[i];
    argv[n] = NULL;
    int pin[2], pout[2];
    if (pipe2(pin, O_CLOEXEC) || pipe2(pout, O_CLOEXEC)) return -1;
    posix_spawn_file_actions_t fa;
    posix_spawn_file_actions_init(&fa);
    posix_spawn_file_actions_adddup2(&fa, pin[0], 0);
    posix_spawn_file_actions_adddup2(&fa, pout[1], 1);
    posix_spawn_file_actions_adddup2(&fa, pout[1], 2);
    pid_t pid;
    int rc = posix_spawn(&pid, g_cmd, &fa, NULL, (char *const *)argv, environ);
    posix_spawn_file_actions_destroy(&fa);
    close(pin[0]);
    close(pout[1]);
    if (rc) {
        close(pin[1]);
        close(pout[0]);
        snprintf(out, outlen, "spawn %s: %s", g_cmd, strerror(rc));
        return -1;
    }
    // stdin first (install-write prints only after it has read everything), then the output.
    size_t done = 0;
    while (in && done < inlen) {
        ssize_t w = write(pin[1], in + done, inlen - done > (1u << 20) ? (1u << 20) : inlen - done);
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) break;
        done += w;
    }
    close(pin[1]);
    size_t got = 0;
    for (;;) {
        char buf[1024];
        ssize_t r = read(pout[0], buf, sizeof buf);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) break;
        size_t k = (size_t)r < outlen - 1 - got ? (size_t)r : outlen - 1 - got;
        memcpy(out + got, buf, k);
        got += k;
    }
    out[got] = 0;
    close(pout[0]);
    int st;
    while (waitpid(pid, &st, 0) < 0 && errno == EINTR) {
    }
    trim(out);
    if (in && done < inlen) return -1;
    return WIFEXITED(st) ? WEXITSTATUS(st) : -1;
}

// The installed versionCode of PKG, 0 if not installed, -1 if PackageManager did not answer.
static long long installed_version(const char *pkg) {
    char out[4096];
    const char *a[] = {"package", "list", "packages", "--show-versioncode", pkg, NULL};
    if (run_cmd(NULL, 0, out, sizeof out, a) < 0) return -1;
    char want[256];
    snprintf(want, sizeof want, "package:%s versionCode:", pkg);
    char *save = NULL;
    for (char *line = strtok_r(out, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        trim(line);
        if (!strncmp(line, want, strlen(want))) return atoll(line + strlen(want));
    }
    return 0;
}

static int install_apk(const char *file, const uint8_t *data, size_t len, int bypass_low_sdk, char *err, size_t errlen) {
    char out[4096], size[32], sid[32];
    snprintf(size, sizeof size, "%zu", len);
    const char *create[] = {"package", "install-create", "-r", "-S", size,
                            bypass_low_sdk ? "--bypass-low-target-sdk-block" : NULL, NULL};
    int rc = run_cmd(NULL, 0, out, sizeof out, create);
    const char *b = strchr(out, '['), *e = b ? strchr(b, ']') : NULL;
    if (rc != 0 || !strstr(out, "Success") || !b || !e || e - b - 1 <= 0 || e - b - 1 >= (int)sizeof sid) {
        snprintf(err, errlen, "install-create: %s", out);
        return -1;
    }
    snprintf(sid, sizeof sid, "%.*s", (int)(e - b - 1), b + 1);
    const char *write_[] = {"package", "install-write", "-S", size, sid, "base.apk", "-", NULL};
    rc = run_cmd(data, len, out, sizeof out, write_);
    if (rc != 0 || !strstr(out, "Success")) {
        snprintf(err, errlen, "install-write %s: %s", file, out);
        const char *ab[] = {"package", "install-abandon", sid, NULL};
        run_cmd(NULL, 0, out, sizeof out, ab);
        return -1;
    }
    const char *commit[] = {"package", "install-commit", sid, NULL};
    rc = run_cmd(NULL, 0, out, sizeof out, commit);
    if (rc != 0 || !strstr(out, "Success")) {
        snprintf(err, errlen, "install-commit %s: %s", file, out);
        return -1;
    }
    return 0;
}

// ------------------------------------------------------------------ state
static void state_path(char *out, size_t n, const char *name) { snprintf(out, n, "%s/%s.json", g_state, name); }

static struct jv *state_read(const char *name) {
    char p[PATH_MAX], err[160];
    state_path(p, sizeof p, name);
    char *t = read_file(p, NULL);
    struct jv *v = t ? json_parse(t, err, sizeof err) : NULL;
    free(t);
    return v;
}

static void state_write(const char *name, const char *json) {
    char p[PATH_MAX], tmp[PATH_MAX];
    state_path(p, sizeof p, name);
    snprintf(tmp, sizeof tmp, "%s.tmp", p);
    if (write_file(tmp, json, strlen(json)) || rename(tmp, p)) LOG("cannot write %s: %s", p, strerror(errno));
}

static int valid_name(const char *s, const char *extra) {
    if (!s || !*s || strlen(s) > 120 || s[0] == '.') return 0;
    for (const char *p = s; *p; p++)
        if (!isalnum((unsigned char)*p) && !strchr(extra, *p)) return 0;
    return 1;
}

static int valid_sha(const char *s) {
    if (!s || strlen(s) != 64) return 0;
    for (const char *p = s; *p; p++)
        if (!isxdigit((unsigned char)*p) || isupper((unsigned char)*p)) return 0;
    return 1;
}

// ------------------------------------------------------------------ one add-on
enum { R_ABSENT, R_DONE, R_INSTALLED, R_REFUSED, R_FAILED, R_BAD_CATALOG };
static const char *const R_NAMES[] = {"absent", "already_installed", "installed", "refused", "failed", "bad_catalog"};

struct file_spec {
    const char *file, *package, *sha256;
    long long version_code;
    int bypass_low_sdk, power;
    struct jv *grant, *appops;
    uint8_t *data;
    size_t len;
};

static int addon_run(const struct jv *cat, struct esp *e, int dry_run, struct jw *w) {
    const char *name = jstr(cat, "name"), *version = jstr(cat, "version");
    struct jv *files = jget(cat, "files");
    jw_obj(w, NULL);
    jw_str(w, "name", name);
    jw_str(w, "version", version);
    if (!valid_name(name, "_-") || !version || !files || files->t != J_ARR || files->len < 1 || files->len > 16 ||
        !jstr(cat, "schema") || strcmp(jstr(cat, "schema"), "openbook-addon/1")) {
        LOG("catalogue entry %s: not an openbook-addon/1 catalogue", name ? name : "?");
        jw_str(w, "result", R_NAMES[R_BAD_CATALOG]);
        jw_endo(w);
        return R_BAD_CATALOG;
    }
    struct file_spec fs[16];
    memset(fs, 0, sizeof fs);
    int nf = files->len;
    for (int i = 0; i < nf; i++) {
        struct jv *f = files->items[i];
        fs[i].file = jstr(f, "file");
        fs[i].package = jstr(f, "package");
        fs[i].sha256 = jstr(f, "sha256");
        fs[i].version_code = (long long)jnum(f, "version_code", 0);
        fs[i].bypass_low_sdk = jbool(f, "bypass_low_target_sdk", 0);
        fs[i].power = jbool(f, "power_allowlist", 0);
        fs[i].grant = jget(f, "grant");
        fs[i].appops = jget(f, "appops");
        size_t fl = fs[i].file ? strlen(fs[i].file) : 0;
        if (!valid_name(fs[i].file, "._-") || fl < 5 || strcmp(fs[i].file + fl - 4, ".apk") ||
            !valid_name(fs[i].package, "._") || !valid_sha(fs[i].sha256) || fs[i].version_code <= 0) {
            LOG("%s: catalogue file %d is malformed", name, i);
            jw_str(w, "result", R_NAMES[R_BAD_CATALOG]);
            jw_endo(w);
            return R_BAD_CATALOG;
        }
    }

    if (!source_has(e, name)) {
        LOG("%s: not on the boot disk (%s): nothing to do", name,
            g_from_dir ? g_from_dir : (e->open ? "openbook/addons/ on the EFI partition" : "no EFI partition found"));
        jw_str(w, "result", R_NAMES[R_ABSENT]);
        jw_endo(w);
        return R_ABSENT;
    }
    struct jv *st = state_read(name);
    if (st && !g_force && jstr(st, "result") && !strcmp(jstr(st, "result"), "installed") && jstr(st, "version") &&
        !strcmp(jstr(st, "version"), version)) {
        LOG("%s %s: installed on %s already; nothing to do (uninstalled apps stay uninstalled)", name, version,
            jstr(st, "at") ? jstr(st, "at") : "?");
        json_free(st);
        jw_str(w, "result", R_NAMES[R_DONE]);
        jw_endo(w);
        return R_DONE;
    }
    json_free(st);

    // Every file first: one that is missing or differs from the image's pin refuses the whole add-on.
    int result = R_INSTALLED;
    char why[600] = "";
    jw_arr(w, "files");
    for (int i = 0; i < nf; i++) {
        char sha[65] = "";
        fs[i].data = source_read(e, name, fs[i].file, &fs[i].len);
        if (fs[i].data) sha256_hex(fs[i].data, fs[i].len, sha);
        jw_obj(w, NULL);
        jw_str(w, "file", fs[i].file);
        jw_u64(w, "bytes", fs[i].len);
        jw_str(w, "sha256", sha[0] ? sha : NULL);
        jw_bool(w, "sha256_ok", fs[i].data && !strcmp(sha, fs[i].sha256));
        jw_endo(w);
        if (!fs[i].data) {
            snprintf(why, sizeof why, "%s is missing from the add-on", fs[i].file);
            result = R_REFUSED;
        } else if (strcmp(sha, fs[i].sha256)) {
            snprintf(why, sizeof why, "%s has sha256 %s, the image pins %s", fs[i].file, sha, fs[i].sha256);
            result = R_REFUSED;
        } else {
            LOG("%s: %s sha256 %s ok (%zu bytes)", name, fs[i].file, sha, fs[i].len);
        }
        if (result == R_REFUSED) break;
    }
    jw_enda(w);
    if (result == R_REFUSED) LOG("%s: refused: %s; nothing was installed", name, why);

    jw_arr(w, "packages");
    for (int i = 0; result == R_INSTALLED && i < nf; i++) {
        jw_obj(w, NULL);
        jw_str(w, "package", fs[i].package);
        long long have = dry_run ? 0 : installed_version(fs[i].package);
        jw_int(w, "had_version_code", have);
        if (have < 0) {
            snprintf(why, sizeof why, "PackageManager did not answer for %s", fs[i].package);
            result = R_FAILED;
        } else if (have >= fs[i].version_code) {
            LOG("%s: %s %lld is installed (the add-on has %lld): kept", name, fs[i].package, have, fs[i].version_code);
            jw_str(w, "action", "kept");
        } else if (dry_run) {
            jw_str(w, "action", "would_install");
        } else {
            char err[sizeof why];
            if (install_apk(fs[i].file, fs[i].data, fs[i].len, fs[i].bypass_low_sdk, err, sizeof err)) {
                snprintf(why, sizeof why, "%s", err);
                result = R_FAILED;
            } else {
                LOG("%s: installed %s %lld from %s", name, fs[i].package, fs[i].version_code, fs[i].file);
                jw_str(w, "action", "installed");
            }
        }
        // Permissions, app-ops and the battery exemption, also for a package that was kept: the catalogue's defaults.
        if (result == R_INSTALLED && !dry_run) {
            char out[2048];
            jw_arr(w, "grant");
            for (int k = 0; fs[i].grant && fs[i].grant->t == J_ARR && k < fs[i].grant->len; k++) {
                const char *perm = fs[i].grant->items[k]->t == J_STR ? fs[i].grant->items[k]->s : NULL;
                if (!valid_name(perm, "._")) continue;
                const char *a[] = {"package", "grant", fs[i].package, perm, NULL};
                int rc = run_cmd(NULL, 0, out, sizeof out, a);
                jw_obj(w, NULL);
                jw_str(w, "permission", perm);
                jw_bool(w, "ok", rc == 0);
                jw_str(w, "error", rc == 0 ? NULL : out);
                jw_endo(w);
                if (rc) LOG("%s: grant %s %s: %s", name, fs[i].package, perm, out);
            }
            jw_enda(w);
            jw_arr(w, "appops");
            for (int k = 0; fs[i].appops && fs[i].appops->t == J_ARR && k < fs[i].appops->len; k++) {
                const char *op = fs[i].appops->items[k]->t == J_STR ? fs[i].appops->items[k]->s : NULL;
                if (!valid_name(op, "_")) continue;
                const char *a[] = {"appops", "set", fs[i].package, op, "allow", NULL};
                int rc = run_cmd(NULL, 0, out, sizeof out, a);
                jw_obj(w, NULL);
                jw_str(w, "op", op);
                jw_bool(w, "ok", rc == 0);
                jw_endo(w);
                if (rc) LOG("%s: appops %s %s: %s", name, fs[i].package, op, out);
            }
            jw_enda(w);
            if (fs[i].power) {
                char arg[300];
                snprintf(arg, sizeof arg, "+%s", fs[i].package);
                const char *a[] = {"deviceidle", "whitelist", arg, NULL};
                int rc = run_cmd(NULL, 0, out, sizeof out, a);
                jw_bool(w, "power_allowlist", rc == 0);
                if (rc) LOG("%s: deviceidle whitelist %s: %s", name, arg, out);
            }
        }
        jw_endo(w);
    }
    jw_enda(w);
    for (int i = 0; i < nf; i++) free(fs[i].data);

    if (result == R_FAILED) LOG("%s: failed: %s", name, why);
    if (result == R_INSTALLED) LOG("%s %s: done", name, version);
    jw_str(w, "result", dry_run && result == R_INSTALLED ? "would_install" : R_NAMES[result]);
    jw_str(w, "why", why[0] ? why : NULL);
    jw_endo(w);
    if (!dry_run && (result == R_INSTALLED || result == R_FAILED || result == R_REFUSED)) {
        struct jw s = {0};
        char at[32];
        utc_stamp(at, sizeof at, 0);
        jw_obj(&s, NULL);
        jw_str(&s, "schema", "openbook-addon-state/1");
        jw_str(&s, "name", name);
        jw_str(&s, "version", version);
        jw_str(&s, "result", R_NAMES[result]);
        jw_str(&s, "why", why[0] ? why : NULL);
        jw_str(&s, "at", at);
        jw_str(&s, "source", g_from_dir ? g_from_dir : e->dev);
        jw_endo(&s);
        state_write(name, s.b.p);
        sb_free(&s.b);
    }
    return result;
}

static int cmp_str(const void *a, const void *b) { return strcmp(*(char *const *)a, *(char *const *)b); }

int main(int argc, char **argv) {
    const char *uuid = NULL, *logpath = NULL, *jsonpath = NULL;
    int i = 1;
    for (; i < argc && argv[i][0] == '-'; i++) {
        if (!strcmp(argv[i], "--catalog") && i + 1 < argc) g_catalog = argv[++i];
        else if (!strcmp(argv[i], "--state") && i + 1 < argc) g_state = argv[++i];
        else if (!strcmp(argv[i], "--boot-part-uuid") && i + 1 < argc) uuid = argv[++i];
        else if (!strcmp(argv[i], "--disk") && i + 1 < argc && g_ndisks < (int)ARRAY_LEN(g_disks)) g_disks[g_ndisks++] = argv[++i];
        else if (!strcmp(argv[i], "--from-dir") && i + 1 < argc) g_from_dir = argv[++i];
        else if (!strcmp(argv[i], "--cmd") && i + 1 < argc) g_cmd = argv[++i];
        else if (!strcmp(argv[i], "--log") && i + 1 < argc) logpath = argv[++i];
        else if (!strcmp(argv[i], "--json") && i + 1 < argc) jsonpath = argv[++i];
        else if (!strcmp(argv[i], "--force")) g_force = 1;
        else break;
    }
    const char *verb = i < argc ? argv[i] : "";
    int dry_run = !strcmp(verb, "status");
    if (strcmp(verb, "run") && !dry_run) {
        fprintf(stderr,
                "usage: openbook-addons [--catalog DIR] [--state DIR] [--boot-part-uuid UUID] [--disk FILE]...\n"
                "                       [--from-dir DIR] [--cmd PATH] [--log FILE] [--json FILE] [--force] run|status\n");
        return 2;
    }
    signal(SIGPIPE, SIG_IGN);
    env_init(NULL, uuid);
    char lp[PATH_MAX];
    if (!logpath && !dry_run) {
        snprintf(lp, sizeof lp, "%s/addons.log", g_state);
        logpath = lp;
    }
    if (logpath) g_logfile = fopen(logpath, "ae");

    DIR *d = opendir(g_catalog);
    char *names[64];
    int n = 0;
    struct dirent *de;
    while (d && (de = readdir(d)) && n < (int)ARRAY_LEN(names)) {
        size_t l = strlen(de->d_name);
        if (l > 5 && !strcmp(de->d_name + l - 5, ".json")) names[n++] = strdup(de->d_name);
    }
    if (d) closedir(d);
    qsort(names, n, sizeof *names, cmp_str);

    struct esp e = {.fd = -1};
    if (n && !g_from_dir) esp_find(&e);
    LOG("openbook-addons %s: %d catalogued add-on(s) in %s; source %s", verb, n, g_catalog,
        g_from_dir ? g_from_dir : (e.open ? e.dev : "none"));

    struct jw w = {0};
    jw_obj(&w, NULL);
    jw_str(&w, "schema", "openbook-addons/1");
    jw_str(&w, "boot_part_uuid", E.boot_part_uuid[0] ? E.boot_part_uuid : NULL);
    jw_str(&w, "source", g_from_dir ? g_from_dir : (e.open ? e.dev : NULL));
    jw_arr(&w, "addons");
    int bad = 0;
    for (int k = 0; k < n; k++) {
        char p[PATH_MAX], err[160];
        snprintf(p, sizeof p, "%s/%s", g_catalog, names[k]);
        char *t = read_file(p, NULL);
        struct jv *cat = t ? json_parse(t, err, sizeof err) : NULL;
        free(t);
        if (!cat) {
            LOG("%s: unreadable catalogue", p);
            bad = 1;
        } else {
            int r = addon_run(cat, &e, dry_run, &w);
            if (r == R_REFUSED || r == R_FAILED || r == R_BAD_CATALOG) bad = 1;
            json_free(cat);
        }
        free(names[k]);
    }
    jw_enda(&w);
    jw_endo(&w);
    if (!jsonpath) puts(w.b.p);
    else if (write_file(jsonpath, w.b.p, w.b.n)) LOG("cannot write %s: %s", jsonpath, strerror(errno));
    esp_close(&e);
    return bad ? 1 : 0;
}
