// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Bring your own Google apps (ANAL-211, docs/gapps.md section 5): check a package the user supplied and stage what
// it may install. OpenBook never downloads, mirrors or names such a package; the user brings it, and the installer
// puts its apps into the new disk's product partition (product.c), which dm-verity then protects like the rest.
//
// The accepted layout is LiteGapps' (github.com/litegapps/litegapps, MIT build scripts, read 2026-10-18): a zip with
// module.prop and files/files.tar.xz, files/files.tar.br or files/files.tar, whose tar holds
// <arch>/<sdk>/system/product/... (LiteGapps installs into product on SDK > 28). Only these are accepted, below
// x86_64/<this image's SDK>/system/product/:
//   priv-app/<Dir>/<name>.apk, app/<Dir>/<name>.apk      apps (one base APK per directory, plus its splits)
//   priv-app/<Dir>/lib/x86_64/<name>.so (and app/...)    an app's extracted libraries, ELF64 x86-64 only
//   etc/permissions/<name>.xml                           privileged-permission allowlists (and features)
//   etc/sysconfig/<name>.xml                             system configuration for apps (power save, user types...)
//   etc/default-permissions/<name>.xml                   runtime permissions granted by default
// Anything else is refused, with a reason per path: the framework (framework/, overlay/, apex), init (etc/init/,
// bin/), SELinux (etc/selinux/), native libraries outside an app, other partitions (system, system_ext, vendor),
// other architectures and SDKs, links and special files, unsafe names. The XML files are checked element by element:
// shared libraries, split permissions, permissions assigned to system UIDs and permission-to-group mappings are
// refused (they change the framework); unknown elements are refused too. Every APK must be signed, must not claim a
// platform shared user ID (android.uid.*), and its native code must include x86_64 (every lib/x86_64/*.so ELF64
// x86-64): an APK with only ARM code would run translated, and this system has no 32-bit ABI. Libraries for other
// ABIs inside a multi-ABI APK are never loaded here (PackageManager picks x86_64) and are listed in the manifest.
//
// The accepted files are staged below /data/misc/openbook_install/gapps/<sha256 of the manifest>/ with the install
// manifest gapps.json (openbook-gapps/1): the package's identity and hash, every file with its size and sha256, and
// every app's package name, version, SDK levels, ABIs and signing certificate. The plan names the manifest by its
// sha256; apply verifies every staged file against it before writing anything.
#include "archive.h"

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define GAPPS_MAX_FILES 4000
#define GAPPS_MAX_BYTES (16ull << 30)
#define GAPPS_MAX_REFUSALS 64

struct gfile {
    char rel[256];   // below product/
    char kind[8];    // apk, lib, xml
    uint64_t bytes;
    char sha256[65];
    char stage[24];  // files/NNNNN
};
struct refusal {
    char path[256];
    char rule[32];
    char why[200];
};
struct chk {
    char tmp[700];
    int sdk;
    char prefix[64];  // x86_64/<sdk>/system/product/
    struct gfile *f;
    int nf, cap;
    uint64_t total;
    struct refusal r[GAPPS_MAX_REFUSALS];
    int nr, more;
    int io_error;
    char io_why[200];
};

static void refuse(struct chk *c, const char *path, const char *rule, const char *fmt, ...)
    __attribute__((format(printf, 4, 5)));
static void refuse(struct chk *c, const char *path, const char *rule, const char *fmt, ...) {
    if (c->nr >= GAPPS_MAX_REFUSALS) {
        c->more++;
        return;
    }
    struct refusal *r = &c->r[c->nr++];
    snprintf(r->path, sizeof r->path, "%s", path);
    snprintf(r->rule, sizeof r->rule, "%s", rule);
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(r->why, sizeof r->why, fmt, ap);
    va_end(ap);
}

static int name_ok(const char *s, size_t n) {
    if (!n || n > 120 || (n == 1 && s[0] == '.') || (n == 2 && s[0] == '.' && s[1] == '.')) return 0;
    for (size_t i = 0; i < n; i++) {
        char ch = s[i];
        if (!((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9') || ch == '.' ||
              ch == '_' || ch == '-' || ch == '+' || ch == '@'))
            return 0;
    }
    return 1;
}

// Splits path into components; 0 if any component is unsafe. comps point into buf.
static int split_path(const char *path, char *buf, size_t bl, char **comp, int max, int *n) {
    while (!strncmp(path, "./", 2)) path += 2;
    if (path[0] == '/' || strlen(path) >= bl) return 0;
    snprintf(buf, bl, "%s", path);
    size_t l = strlen(buf);
    while (l && buf[l - 1] == '/') buf[--l] = 0;  // a directory's trailing slash
    *n = 0;
    if (!l) return 1;
    for (char *p = buf;;) {
        char *s = strchr(p, '/');
        size_t cl = s ? (size_t)(s - p) : strlen(p);
        if (!name_ok(p, cl) || *n >= max) return 0;
        comp[(*n)++] = p;
        if (!s) break;
        *s = 0;
        p = s + 1;
    }
    return 1;
}

static int ends_with(const char *s, const char *suf) {
    size_t a = strlen(s), b = strlen(suf);
    return a >= b && !strcmp(s + a - b, suf);
}

// Classify a path below product/: kind ("apk", "lib", "xml") or NULL with a refusal.
static const char *classify(struct chk *c, const char *full, char **p, int n) {
    const char *top = p[0];
    if (!strcmp(top, "priv-app") || !strcmp(top, "app")) {
        if (n == 3 && ends_with(p[2], ".apk") && strlen(p[2]) > 4) return "apk";
        if (n == 5 && !strcmp(p[2], "lib") && !strcmp(p[3], "x86_64") && ends_with(p[4], ".so")) return "lib";
        if (n >= 4 && !strcmp(p[2], "lib")) {
            refuse(c, full, "native_abi", "a native library for %s: only x86_64 code runs natively here", p[3]);
            return NULL;
        }
        if (n >= 3 && !strcmp(p[2], "oat")) {
            refuse(c, full, "preopted", "precompiled code (oat) is built for another system image");
            return NULL;
        }
        refuse(c, full, "unexpected_path", "only <dir>/<name>.apk and <dir>/lib/x86_64/<name>.so belong in %s/", top);
        return NULL;
    }
    if (!strcmp(top, "etc") && n == 3 &&
        (!strcmp(p[1], "permissions") || !strcmp(p[1], "sysconfig") || !strcmp(p[1], "default-permissions"))) {
        if (ends_with(p[2], ".xml")) return "xml";
        refuse(c, full, "unexpected_path", "only XML files belong in etc/%s/", p[1]);
        return NULL;
    }
    static const struct {
        const char *top, *sub, *rule, *why;
    } known[] = {
        {"framework", NULL, "framework", "touches the framework (framework libraries)"},
        {"overlay", NULL, "framework", "touches the framework (resource overlays change system UI and settings)"},
        {"apex", NULL, "framework", "touches the framework (APEX modules)"},
        {"etc", "init", "init", "touches init (service definitions)"},
        {"bin", NULL, "init", "adds executables to the system"},
        {"etc", "selinux", "selinux", "touches SELinux policy"},
        {"lib", NULL, "native_lib", "native libraries outside an app"},
        {"lib64", NULL, "native_lib", "native libraries outside an app"},
        {"etc", "vintf", "framework", "touches the framework (VINTF manifests)"},
        {"etc", "security", "framework", "touches the framework (security configuration)"},
        {"etc", "preferred-apps", "unexpected_path", "preferred-app settings are not accepted"},
        {"build.prop", NULL, "framework", "system properties"},
        {"etc", "build.prop", "framework", "system properties"},
    };
    for (size_t i = 0; i < ARRAY_LEN(known); i++)
        if (!strcmp(top, known[i].top) && (!known[i].sub || (n > 1 && !strcmp(p[1], known[i].sub)))) {
            refuse(c, full, known[i].rule, "%s", known[i].why);
            return NULL;
        }
    refuse(c, full, "unexpected_path", "not one of the paths a Google apps package may install");
    return NULL;
}

static int stage_file(struct chk *c, const char *rel, const char *kind, uint64_t size, struct src *body) {
    if (c->nf >= GAPPS_MAX_FILES) {
        refuse(c, rel, "too_many_files", "more than %d files", GAPPS_MAX_FILES);
        return 0;
    }
    if (c->total + size > GAPPS_MAX_BYTES) {
        refuse(c, rel, "too_big", "the package's files exceed %llu GiB", GAPPS_MAX_BYTES >> 30);
        return 0;
    }
    uint64_t max = !strcmp(kind, "xml") ? MiB : !strcmp(kind, "lib") ? 512 * MiB : 4096 * MiB;
    if (size > max) {
        refuse(c, rel, "too_big", "%llu bytes is more than a %s may have", (unsigned long long)size, kind);
        return 0;
    }
    for (int i = 0; i < c->nf; i++)
        if (!strcmp(c->f[i].rel, rel)) {
            refuse(c, rel, "duplicate", "the archive has this path twice");
            return 0;
        }
    if (c->nf == c->cap) {
        c->cap = c->cap ? 2 * c->cap : 64;
        c->f = realloc(c->f, c->cap * sizeof *c->f);
    }
    struct gfile *g = &c->f[c->nf];
    memset(g, 0, sizeof *g);
    snprintf(g->rel, sizeof g->rel, "%s", rel);
    snprintf(g->kind, sizeof g->kind, "%s", kind);
    snprintf(g->stage, sizeof g->stage, "files/%05d", c->nf);
    char path[800];
    snprintf(path, sizeof path, "%s/%s", c->tmp, g->stage);
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0640);
    if (fd < 0) {
        c->io_error = 1;
        snprintf(c->io_why, sizeof c->io_why, "cannot stage %s: %s", rel, strerror(errno));
        return -1;
    }
    static uint8_t buf[1 << 20];
    struct sha256 h;
    sha256_init(&h);
    uint64_t done = 0;
    while (done < size) {
        ssize_t r = body->read(body, buf, size - done < sizeof buf ? size - done : sizeof buf);
        if (r <= 0 || write(fd, buf, r) != r) {
            close(fd);
            c->io_error = 1;
            snprintf(c->io_why, sizeof c->io_why, r <= 0 ? "the archive's data is damaged in %s" : "cannot stage %s: %s",
                     rel, strerror(errno));
            return -1;
        }
        sha256_update(&h, buf, r);
        done += r;
    }
    if (fsync(fd) || close(fd)) {
        c->io_error = 1;
        snprintf(c->io_why, sizeof c->io_why, "cannot stage %s: %s", rel, strerror(errno));
        return -1;
    }
    sha256_final_hex(&h, g->sha256);
    g->bytes = size;
    c->total += size;
    c->nf++;
    return 0;
}

static int on_entry(void *arg, const char *path, char type, uint64_t size, struct src *body) {
    struct chk *c = arg;
    char buf[600], *p[40];
    int n;
    char shown[256];
    snprintf(shown, sizeof shown, "%s", path);
    if (!split_path(path, buf, sizeof buf, p, 40, &n)) {
        refuse(c, shown, "unsafe_path", "an absolute path, \"..\", or characters a system path may not have");
        return 0;
    }
    if (type == '5' || n == 0) return 0;  // directories come from the files they hold
    if (type != '0') {
        refuse(c, shown, type == '1' || type == '2' ? "link" : "special_file",
               type == '1' || type == '2' ? "links are not accepted" : "only regular files are accepted");
        return 0;
    }
    char sdk[16];
    snprintf(sdk, sizeof sdk, "%d", c->sdk);
    if (strcmp(p[0], "x86_64")) {
        static const char *const arches[] = {"arm64", "arm", "x86", "riscv64"};
        for (size_t i = 0; i < ARRAY_LEN(arches); i++)
            if (!strcmp(p[0], arches[i])) {
                refuse(c, shown, "wrong_arch", "for %s; this system is x86_64", p[0]);
                return 0;
            }
        refuse(c, shown, "unexpected_path", "outside x86_64/%d/", c->sdk);
        return 0;
    }
    if (n < 2 || strcmp(p[1], sdk)) {
        refuse(c, shown, "wrong_sdk", "for SDK %s; this system is SDK %d (Android 17)", n > 1 ? p[1] : "?", c->sdk);
        return 0;
    }
    if (n < 5 || strcmp(p[2], "system") || strcmp(p[3], "product")) {
        const char *where = n > 2 && strcmp(p[2], "system") ? p[2] : n > 3 ? p[3] : "system";
        refuse(c, shown, "outside_product", "installs into %s; only the product partition is accepted", where);
        return 0;
    }
    char rel[256] = "";
    for (int i = 4; i < n; i++) {
        size_t l = strlen(rel);
        snprintf(rel + l, sizeof rel - l, "%s%s", i > 4 ? "/" : "", p[i]);
    }
    const char *kind = classify(c, rel, p + 4, n - 4);
    if (!kind) return 0;
    return stage_file(c, rel, kind, size, body);
}

// ------------------------------------------------------------------ XML (permissions, sysconfig, default-permissions)
struct xml_rule {
    const char *name;
    const char *parent;  // NULL: a child of the root
    const char *rule, *why;  // rule NULL: allowed
};
static const struct xml_rule CONFIG_RULES[] = {
    {"privapp-permissions", NULL, NULL, NULL},
    {"permission", "privapp-permissions", NULL, NULL},
    {"deny-permission", "privapp-permissions", NULL, NULL},
    {"feature", NULL, NULL, NULL},
    {"allow-in-power-save", NULL, NULL, NULL},
    {"allow-in-power-save-except-idle", NULL, NULL, NULL},
    {"allow-in-data-usage-save", NULL, NULL, NULL},
    {"allow-unthrottled-location", NULL, NULL, NULL},
    {"allow-ignore-location-settings", NULL, NULL, NULL},
    {"allow-implicit-broadcast", NULL, NULL, NULL},
    {"app-link", NULL, NULL, NULL},
    {"system-user-whitelisted-app", NULL, NULL, NULL},
    {"system-user-blacklisted-app", NULL, NULL, NULL},
    {"install-in-user-type", NULL, NULL, NULL},
    {"install-in", "install-in-user-type", NULL, NULL},
    {"do-not-install-in", "install-in-user-type", NULL, NULL},
    {"hidden-api-whitelisted-app", NULL, NULL, NULL},
    {"backup-transport-whitelisted-service", NULL, NULL, NULL},
    {"allow-association", NULL, NULL, NULL},
    {"bugreport-whitelisted", NULL, NULL, NULL},
    {"rollback-whitelisted-app", NULL, NULL, NULL},
    {"whitelisted-staged-installer", NULL, NULL, NULL},
    {"default-enabled-vr-app", NULL, NULL, NULL},
    {"component-override", NULL, NULL, NULL},
    {"component", "component-override", NULL, NULL},
    {"initial-package-state", NULL, NULL, NULL},
    {"library", NULL, "framework", "adds a shared library to the framework"},
    {"updatable-library", NULL, "framework", "adds a shared library to the framework"},
    {"apex-library", NULL, "framework", "adds a shared library to the framework"},
    {"split-permission", NULL, "framework", "changes how the platform splits permissions"},
    {"assign-permission", NULL, "framework", "grants a permission to a system user ID"},
    {"permission", NULL, "framework", "maps a permission to Linux groups"},
    {"group", NULL, "framework", "maps a permission to Linux groups"},
    {"unavailable-feature", NULL, "framework", "removes a platform feature"},
    {"oem-permissions", NULL, "framework", "grants OEM permissions"},
};
static const struct xml_rule DEFPERM_RULES[] = {
    {"exception", NULL, NULL, NULL},
    {"permission", "exception", NULL, NULL},
};

static int xml_check(struct chk *c, const char *rel, const char *t, size_t n, struct jw *w) {
    const char *dir = strchr(rel, '/') + 1;  // etc/<dir>/name.xml
    int defperm = !strncmp(dir, "default-permissions/", 20);
    const char *root_ok1 = defperm ? "exceptions" : !strncmp(dir, "sysconfig/", 10) ? "config" : "permissions";
    const char *root_ok2 = defperm ? "exceptions" : "permissions";
    const struct xml_rule *rules = defperm ? DEFPERM_RULES : CONFIG_RULES;
    size_t nrules = defperm ? ARRAY_LEN(DEFPERM_RULES) : ARRAY_LEN(CONFIG_RULES);
    char stack[16][64];
    int depth = 0, roots = 0, bad = 0;
    struct {
        char name[40];
        int count;
    } counts[24];
    int nc = 0;
    for (size_t i = 0; i < n && !bad;) {
        if (t[i] != '<') {
            i++;
            continue;
        }
        const char *end;
        if (!strncmp(t + i, "<?", 2) && (end = strstr(t + i, "?>"))) {
            i = end - t + 2;
            continue;
        }
        if (!strncmp(t + i, "<!--", 4) && (end = strstr(t + i + 4, "-->"))) {
            i = end - t + 3;
            continue;
        }
        if (!strncmp(t + i, "<![CDATA[", 9) && (end = strstr(t + i, "]]>"))) {
            i = end - t + 3;
            continue;
        }
        if (t[i + 1] == '!') {
            refuse(c, rel, "xml_doctype", "DOCTYPE or entity declarations are not accepted");
            return -1;
        }
        int closing = t[i + 1] == '/';
        size_t s = i + 1 + closing, e = s;
        while (e < n && (isalnum((unsigned char)t[e]) || t[e] == '-' || t[e] == '_' || t[e] == ':' || t[e] == '.')) e++;
        if (e == s || e - s >= 64) {
            refuse(c, rel, "xml_malformed", "malformed XML near byte %zu", i);
            return -1;
        }
        char name[64];
        snprintf(name, sizeof name, "%.*s", (int)(e - s), t + s);
        // attributes, up to > (quoted values may hold >)
        size_t k = e;
        char q = 0;
        for (; k < n; k++) {
            if (q) {
                if (t[k] == q) q = 0;
            } else if (t[k] == '"' || t[k] == '\'') {
                q = t[k];
            } else if (t[k] == '>') {
                break;
            } else if (t[k] == '<') {
                k = n;
            }
        }
        if (k >= n) {
            refuse(c, rel, "xml_malformed", "unterminated tag <%s", name);
            return -1;
        }
        int selfclose = k > e && t[k - 1] == '/';
        i = k + 1;
        if (closing) {
            if (!depth || strcmp(stack[depth - 1], name)) {
                refuse(c, rel, "xml_malformed", "</%s> does not close the open element", name);
                return -1;
            }
            depth--;
            continue;
        }
        if (depth == 0) {
            if (roots++ || (strcmp(name, root_ok1) && strcmp(name, root_ok2))) {
                refuse(c, rel, "xml_root", "the root element must be <%s>", root_ok1);
                return -1;
            }
        } else {
            const char *parent = depth >= 2 ? stack[depth - 1] : NULL;
            const struct xml_rule *hit = NULL;
            for (size_t r = 0; r < nrules && !hit; r++)
                if (!strcmp(rules[r].name, name) && ((!parent && !rules[r].parent) ||
                                                     (parent && rules[r].parent && !strcmp(parent, rules[r].parent))))
                    hit = &rules[r];
            if (!hit) {
                refuse(c, rel, "xml_element", "<%s>%s%s%s is not an element this file may contain", name,
                       parent ? " inside <" : "", parent ? parent : "", parent ? ">" : "");
                bad = 1;
                break;
            }
            if (hit->rule) {
                refuse(c, rel, hit->rule, "<%s> %s", name, hit->why);
                bad = 1;
                break;
            }
            if (depth == 1) {
                int f = -1;
                for (int x = 0; x < nc; x++)
                    if (!strcmp(counts[x].name, name)) f = x;
                if (f < 0 && nc < 24) {
                    f = nc++;
                    snprintf(counts[f].name, sizeof counts[f].name, "%s", name);
                    counts[f].count = 0;
                }
                if (f >= 0) counts[f].count++;
            }
        }
        if (!selfclose) {
            if (depth >= 16) {
                refuse(c, rel, "xml_malformed", "nested too deeply");
                return -1;
            }
            snprintf(stack[depth++], sizeof stack[0], "%s", name);
        }
    }
    if (bad) return -1;
    if (depth || !roots) {
        refuse(c, rel, "xml_malformed", depth ? "an element is not closed" : "no root element");
        return -1;
    }
    jw_obj(w, NULL);
    jw_str(w, "path", rel);
    jw_obj(w, "elements");
    for (int x = 0; x < nc; x++) jw_int(w, counts[x].name, counts[x].count);
    jw_endo(w);
    jw_endo(w);
    return 0;
}

// ------------------------------------------------------------------ staging directory
static void stage_root(char *out, size_t n) { env_path(out, n, "/data/misc/openbook_install/gapps"); }

static void rm_rf(const char *path) {
    DIR *d = opendir(path);
    if (d) {
        struct dirent *e;
        while ((e = readdir(d))) {
            if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
            char p[1024];
            snprintf(p, sizeof p, "%s/%s", path, e->d_name);
            struct stat st;
            if (!lstat(p, &st) && S_ISDIR(st.st_mode)) rm_rf(p);
            else unlink(p);
        }
        closedir(d);
    }
    rmdir(path);
}

static int mkdirs(const char *path) {
    char p[1024];
    snprintf(p, sizeof p, "%s", path);
    for (char *s = p + 1; *s; s++)
        if (*s == '/') {
            *s = 0;
            mkdir(p, 0770);
            *s = '/';
        }
    return mkdir(p, 0770) && errno != EEXIST ? -1 : 0;
}

static int cmp_gfile(const void *a, const void *b) { return strcmp(((const struct gfile *)a)->rel, ((const struct gfile *)b)->rel); }

static void sanitize(const char *in, char *out, size_t n) {
    size_t o = 0;
    for (const char *p = in ? in : ""; *p && o + 1 < n; p++) out[o++] = (*p >= 0x20 && *p < 0x7f) ? *p : '?';
    out[o] = 0;
}

// module.prop: key=value lines
static void prop_line(const char *text, const char *key, char *out, size_t n) {
    out[0] = 0;
    size_t kl = strlen(key);
    for (const char *p = text; p && *p;) {
        const char *e = strchr(p, '\n');
        size_t l = e ? (size_t)(e - p) : strlen(p);
        if (l > kl && !strncmp(p, key, kl) && p[kl] == '=') {
            char v[200];
            snprintf(v, sizeof v, "%.*s", (int)(l - kl - 1), p + kl + 1);
            trim(v);
            sanitize(v, out, n);
            return;
        }
        p = e ? e + 1 : NULL;
    }
}

int gapps_check(const char *path, const char *display_name, struct jw *w, char manifest_sha[65]) {
    struct chk *c = calloc(1, sizeof *c);
    char sdkp[16], root[600], why[300] = "";
    const char *code = NULL;
    manifest_sha[0] = 0;
    prop_get("ro.build.version.sdk", sdkp, sizeof sdkp);
    c->sdk = atoi(sdkp) > 0 ? atoi(sdkp) : GAPPS_SDK;
    snprintf(c->prefix, sizeof c->prefix, "x86_64/%d/system/product/", c->sdk);
    stage_root(root, sizeof root);
    snprintf(c->tmp, sizeof c->tmp, "%s/check-%d", root, (int)getpid());
    rm_rf(c->tmp);
    char files_dir[800];
    snprintf(files_dir, sizeof files_dir, "%s/files", c->tmp);
    struct zip z = {0};
    struct zstream zs;
    int zs_on = 0;
    struct src *dec = NULL;
    int dec_kind = 0;  // 1 xz, 2 brotli
    char pkg_sha[65] = "", payload[64] = "", mod[65536] = "";
    uint64_t pkg_bytes = 0;
    char m_name[120], m_version[64], m_author[64], m_arch[32], m_sdk[16], m_type[32];
    struct jw apps = {0}, xmls = {0};
    jw_arr(&apps, NULL);
    jw_arr(&xmls, NULL);
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    struct stat st;
    if (fd < 0 || fstat(fd, &st) || !S_ISREG(st.st_mode)) {
        code = "no_package";
        snprintf(why, sizeof why, "cannot read the package: %s", fd < 0 ? strerror(errno) : "not a regular file");
        goto out;
    }
    pkg_bytes = st.st_size;
    if (mkdirs(files_dir)) {
        code = "io";
        snprintf(why, sizeof why, "cannot create the staging directory %s: %s", files_dir, strerror(errno));
        goto out;
    }
    LOG("gapps: checking %s (%llu bytes) for x86_64, SDK %d", display_name, (unsigned long long)pkg_bytes, c->sdk);
    {  // the package's own hash, for the manifest and the plan
        static uint8_t buf[1 << 20];
        struct sha256 h;
        sha256_init(&h);
        for (uint64_t off = 0; off < pkg_bytes;) {
            size_t k = pkg_bytes - off < sizeof buf ? pkg_bytes - off : sizeof buf;
            if (pread_all(fd, buf, k, off)) {
                code = "no_package";
                snprintf(why, sizeof why, "cannot read the package: %s", strerror(errno));
                goto out;
            }
            sha256_update(&h, buf, k);
            off += k;
        }
        sha256_final_hex(&h, pkg_sha);
    }
    if (zip_open(&z, fd, pkg_bytes, why, sizeof why)) {
        code = "not_a_package";
        goto out;
    }
    const struct zentry *mp = zip_find(&z, "module.prop");
    if (mp) {
        size_t ml;
        uint8_t *m = zip_read_all(&z, mp, sizeof mod - 1, &ml);
        if (m) {
            memcpy(mod, m, ml);
            mod[ml] = 0;
            free(m);
        }
    }
    prop_line(mod, "name", m_name, sizeof m_name);
    prop_line(mod, "version", m_version, sizeof m_version);
    prop_line(mod, "author", m_author, sizeof m_author);
    prop_line(mod, "litegapps_arch", m_arch, sizeof m_arch);
    prop_line(mod, "litegapps_sdk", m_sdk, sizeof m_sdk);
    prop_line(mod, "litegapps_type", m_type, sizeof m_type);
    if (m_arch[0] && strcmp(m_arch, "x86_64")) refuse(c, "module.prop", "wrong_arch", "the package is for %s; this system is x86_64", m_arch);
    if (m_sdk[0] && atoi(m_sdk) != c->sdk)
        refuse(c, "module.prop", "wrong_sdk", "the package is for SDK %s; this system is SDK %d (Android 17)", m_sdk, c->sdk);
    {
        const char *cands[] = {"files/files.tar.xz", "files/files.tar.br", "files/files.tar"};
        const struct zentry *pe = NULL;
        int found = 0;
        for (int i = 0; i < 3; i++)
            if (zip_find(&z, cands[i])) {
                if (!pe) {
                    pe = zip_find(&z, cands[i]);
                    snprintf(payload, sizeof payload, "%s", cands[i]);
                    dec_kind = i == 0 ? 1 : i == 1 ? 2 : 0;
                }
                found++;
            }
        if (!pe || found > 1) {
            code = "not_a_package";
            snprintf(why, sizeof why, found > 1 ? "the package has more than one files/files.tar.*"
                                                : "not a LiteGapps-layout package (no files/files.tar.xz, .br or .tar)");
            goto out;
        }
        if (c->nr) goto refused;  // wrong architecture or SDK: don't unpack
        if (zs_open(&zs, &z, pe)) {
            code = "not_a_package";
            snprintf(why, sizeof why, "%s cannot be read (encrypted, or an unknown compression)", payload);
            goto out;
        }
        zs_on = 1;
        struct src *tar_in = &zs.base;
        if (dec_kind == 1) tar_in = dec = xz_stream_new(&zs.base);
        if (dec_kind == 2) tar_in = dec = br_stream_new(&zs.base);
        char tw[200];
        if (!tar_in || tar_walk(tar_in, on_entry, c, tw, sizeof tw)) {
            code = c->io_error ? "io" : "not_a_package";
            snprintf(why, sizeof why, "%s: %s", payload, c->io_error ? c->io_why : tw);
            goto out;
        }
    }
    if (!c->nf && !c->nr) refuse(c, c->prefix, "empty", "the package has nothing to install for x86_64, SDK %d", c->sdk);
    qsort(c->f, c->nf, sizeof *c->f, cmp_gfile);
    // Apps: one directory each, one base APK plus splits of the same package; signed; x86_64 native code.
    {
        char seen_pkgs[256][160];
        int nseen = 0;
        for (int i = 0; i < c->nf; i++) {
            struct gfile *g = &c->f[i];
            char spath[800];
            snprintf(spath, sizeof spath, "%s/%s", c->tmp, g->stage);
            if (!strcmp(g->kind, "lib")) {
                int lfd = open(spath, O_RDONLY | O_CLOEXEC), cls = 0;
                uint8_t h[64];
                ssize_t r = lfd >= 0 ? pread(lfd, h, sizeof h, 0) : -1;
                if (lfd >= 0) close(lfd);
                int mach = r > 0 ? elf_machine(h, r, &cls) : 0;
                if (mach != 62 || cls != 2)
                    refuse(c, g->rel, "native_abi", "not an ELF64 x86-64 library (machine %d, class %d)", mach, cls);
                char dir[256];
                snprintf(dir, sizeof dir, "%.*s/", (int)(strstr(g->rel, "/lib/") - g->rel), g->rel);
                int has_apk = 0;
                for (int k = 0; k < c->nf; k++)
                    if (!strcmp(c->f[k].kind, "apk") && !strncmp(c->f[k].rel, dir, strlen(dir))) has_apk = 1;
                if (!has_apk) refuse(c, g->rel, "unexpected_path", "a library in a directory without an APK");
                continue;
            }
            if (!strcmp(g->kind, "xml")) {
                size_t tl;
                char *t = read_file(spath, &tl);
                if (!t) refuse(c, g->rel, "io", "cannot read the staged file");
                else xml_check(c, g->rel, t, tl, &xmls);
                free(t);
                continue;
            }
            // An app directory: the first APK in it (sorted) starts it; its siblings must be splits of it.
            char dir[256];
            const char *last = strrchr(g->rel, '/');
            snprintf(dir, sizeof dir, "%.*s", (int)(last - g->rel), g->rel);
            if (i > 0 && !strcmp(c->f[i - 1].kind, "apk") && !strncmp(c->f[i - 1].rel, dir, strlen(dir)) &&
                c->f[i - 1].rel[strlen(dir)] == '/')
                continue;  // handled with the directory's first APK
            int nbase = 0;
            struct apk_info base = {0};
            jw_obj(&apps, NULL);
            jw_str(&apps, "dir", dir);
            jw_bool(&apps, "privileged", !strncmp(dir, "priv-app/", 9));
            jw_arr(&apps, "apks");
            int ok = 1;
            for (int k = i; k < c->nf && !strncmp(c->f[k].rel, dir, strlen(dir)) && c->f[k].rel[strlen(dir)] == '/'; k++) {
                if (strcmp(c->f[k].kind, "apk")) continue;
                char kp[800];
                snprintf(kp, sizeof kp, "%s/%s", c->tmp, c->f[k].stage);
                struct apk_info a;
                int afd = open(kp, O_RDONLY | O_CLOEXEC);
                int rc = afd >= 0 ? apk_inspect(afd, c->f[k].bytes, &a) : -1;
                if (afd >= 0) close(afd);
                if (rc) {
                    refuse(c, c->f[k].rel, "apk_invalid", "not a valid APK: %s", afd < 0 ? "unreadable" : a.why);
                    ok = 0;
                    continue;
                }
                jw_obj(&apps, NULL);
                jw_str(&apps, "path", c->f[k].rel);
                jw_str(&apps, "split", a.split[0] ? a.split : NULL);
                jw_endo(&apps);
                if (!a.cert_sha256[0]) refuse(c, c->f[k].rel, "unsigned", "the APK is not signed"), ok = 0;
                if (!strncmp(a.shared_user, "android.uid.", 12))
                    refuse(c, c->f[k].rel, "platform_uid", "claims the platform's shared user ID %s", a.shared_user), ok = 0;
                if (a.min_sdk > c->sdk || a.min_sdk < 0)
                    refuse(c, c->f[k].rel, "needs_newer_sdk", "needs SDK %d; this system is SDK %d", a.min_sdk, c->sdk), ok = 0;
                if (a.nabis && !a.x86_64_libs)
                    refuse(c, c->f[k].rel, "native_abi", "native code for %s%s%s only: no x86_64 code", a.abis[0],
                           a.nabis > 1 ? ", " : "", a.nabis > 1 ? a.abis[1] : ""), ok = 0;
                if (a.bad_elf)
                    refuse(c, c->f[k].rel, "native_abi", "%s is not an ELF64 x86-64 library", a.bad_elf_name), ok = 0;
                if (!a.split[0]) {
                    if (nbase++) refuse(c, c->f[k].rel, "split_mismatch", "a second base APK in %s/", dir), ok = 0;
                    base = a;
                } else if (base.package[0] && strcmp(a.package, base.package)) {
                    refuse(c, c->f[k].rel, "split_mismatch", "a split of %s in the directory of %s", a.package, base.package),
                        ok = 0;
                }
            }
            jw_enda(&apps);
            if (!nbase && ok) refuse(c, dir, "split_mismatch", "splits without a base APK"), ok = 0;
            for (int s = 0; s < nseen && base.package[0]; s++)
                if (!strcmp(seen_pkgs[s], base.package))
                    refuse(c, dir, "duplicate_package", "%s is in the package twice", base.package), ok = 0;
            if (base.package[0] && nseen < 256) snprintf(seen_pkgs[nseen++], sizeof seen_pkgs[0], "%s", base.package);
            jw_str(&apps, "package", base.package);
            jw_int(&apps, "version_code", base.version_code);
            jw_str(&apps, "version_name", base.version_name);
            jw_int(&apps, "min_sdk", base.min_sdk);
            jw_int(&apps, "target_sdk", base.target_sdk);
            jw_arr(&apps, "abis");
            for (int k = 0; k < base.nabis; k++) jw_str(&apps, NULL, base.abis[k]);
            jw_enda(&apps);
            jw_str(&apps, "native", base.x86_64_libs ? "x86_64" : base.nabis ? "other" : "none");
            jw_int(&apps, "requested_permissions", base.nperms);
            jw_str(&apps, "signing_scheme", base.scheme[0] ? base.scheme : NULL);
            jw_str(&apps, "signer_sha256", base.cert_sha256[0] ? base.cert_sha256 : NULL);
            jw_str(&apps, "signer", base.cert_subject[0] ? base.cert_subject : NULL);
            jw_endo(&apps);
        }
    }
    jw_enda(&apps);
    jw_enda(&xmls);
    if (c->nr) goto refused;
    {  // the install manifest
        struct jw m = {0};
        char shown[160], tstr[32];
        sanitize(display_name, shown, sizeof shown);
        utc_stamp(tstr, sizeof tstr, 0);
        jw_obj(&m, NULL);
        jw_str(&m, "schema", "openbook-gapps/1");
        jw_obj(&m, "package");
        jw_str(&m, "file", shown);
        jw_u64(&m, "bytes", pkg_bytes);
        jw_str(&m, "sha256", pkg_sha);
        jw_str(&m, "layout", "litegapps");
        jw_str(&m, "payload", payload);
        jw_str(&m, "name", m_name[0] ? m_name : NULL);
        jw_str(&m, "version", m_version[0] ? m_version : NULL);
        jw_str(&m, "author", m_author[0] ? m_author : NULL);
        jw_str(&m, "type", m_type[0] ? m_type : NULL);
        jw_endo(&m);
        jw_str(&m, "arch", "x86_64");
        jw_int(&m, "sdk", c->sdk);
        jw_str(&m, "checked", tstr);
        jw_u64(&m, "bytes", c->total);
        jw_arr(&m, "files");
        for (int i = 0; i < c->nf; i++) {
            jw_obj(&m, NULL);
            jw_str(&m, "path", c->f[i].rel);
            jw_str(&m, "kind", c->f[i].kind);
            jw_u64(&m, "bytes", c->f[i].bytes);
            jw_str(&m, "sha256", c->f[i].sha256);
            jw_str(&m, "stage", c->f[i].stage);
            jw_endo(&m);
        }
        jw_enda(&m);
        jw_raw(&m, "apps", apps.b.p);
        jw_raw(&m, "xml", xmls.b.p);
        jw_endo(&m);
        sha256_hex(m.b.p, m.b.n, manifest_sha);
        char mpath[800], final[800];
        snprintf(mpath, sizeof mpath, "%s/gapps.json", c->tmp);
        snprintf(final, sizeof final, "%s/%s", root, manifest_sha);
        if (write_file(mpath, m.b.p, m.b.n)) {
            code = "io";
            snprintf(why, sizeof why, "cannot write the manifest: %s", strerror(errno));
            sb_free(&m.b);
            goto out;
        }
        // One staged package at a time: an earlier check's files are removed.
        DIR *d = opendir(root);
        struct dirent *e;
        while (d && (e = readdir(d))) {
            if (e->d_name[0] == '.' || !strcmp(e->d_name, strrchr(c->tmp, '/') + 1)) continue;
            char p[1000];
            snprintf(p, sizeof p, "%s/%s", root, e->d_name);
            rm_rf(p);
        }
        if (d) closedir(d);
        if (rename(c->tmp, final)) {
            code = "io";
            snprintf(why, sizeof why, "cannot keep the staged files: %s", strerror(errno));
            sb_free(&m.b);
            goto out;
        }
        LOG("gapps: accepted %s: %d files, %llu bytes, manifest %s", shown, c->nf, (unsigned long long)c->total,
            manifest_sha);
        jw_bool(w, "ok", 1);
        jw_str(w, "gapps_sha256", manifest_sha);
        jw_raw(w, "gapps", m.b.p);
        jw_arr(w, "warnings");
        struct jv *mv = json_parse(m.b.p, NULL, 0);
        struct jv *ap = jget(mv, "apps");
        int nprivxml = 0;
        for (int i = 0; i < c->nf; i++)
            if (!strncmp(c->f[i].rel, "etc/permissions/", 16)) nprivxml++;
        for (int i = 0; ap && i < ap->len; i++) {
            struct jv *ab = jget(ap->items[i], "abis");
            if (ab && ab->len > 1) {
                char t[300];
                snprintf(t, sizeof t, "multi_abi:%s", jstr(ap->items[i], "package"));
                jw_str(w, NULL, t);
            }
        }
        if (!nprivxml) jw_str(w, NULL, "no_privapp_allowlist");
        json_free(mv);
        jw_enda(w);
        sb_free(&m.b);
    }
    goto done;
refused:
    code = "refused";
    snprintf(why, sizeof why, "%d path%s cannot be installed%s", c->nr + c->more, c->nr + c->more == 1 ? "" : "s",
             c->more ? " (the first 64 are listed)" : "");
out:
    rm_rf(c->tmp);
    jw_bool(w, "ok", 0);
    jw_str(w, "code", code ? code : "internal");
    jw_str(w, "error", why);
    if (c->nr) {
        jw_arr(w, "refused");
        for (int i = 0; i < c->nr; i++) {
            jw_obj(w, NULL);
            jw_str(w, "path", c->r[i].path);
            jw_str(w, "rule", c->r[i].rule);
            jw_str(w, "why", c->r[i].why);
            jw_endo(w);
        }
        jw_enda(w);
        jw_int(w, "refused_more", c->more);
    }
    LOG("gapps: refused %s (%s): %s", display_name, code ? code : "internal", why);
    for (int i = 0; i < c->nr && i < 10; i++) LOG("gapps:   %s: %s (%s)", c->r[i].path, c->r[i].why, c->r[i].rule);
done:;
    int ok = manifest_sha[0] != 0 && !code;
    if (zs_on) zs_close(&zs);
    if (dec_kind == 1) xz_stream_free(dec);
    if (dec_kind == 2) br_stream_free(dec);
    zip_close(&z);
    if (fd >= 0) close(fd);
    sb_free(&apps.b);
    sb_free(&xmls.b);
    free(c->f);
    free(c);
    if (!ok) manifest_sha[0] = 0;
    return ok ? 0 : -1;
}

struct jv *gapps_load(const char *sha, char *dir, size_t dl, char **text, size_t *tlen, char *why, size_t wl) {
    char root[600], path[900];
    if (text) *text = NULL;
    size_t sl = sha ? strlen(sha) : 0;
    int hex = sl == 64;
    for (size_t i = 0; hex && i < sl; i++) hex = (sha[i] >= '0' && sha[i] <= '9') || (sha[i] >= 'a' && sha[i] <= 'f');
    if (!hex) {
        snprintf(why, wl, "not a package manifest's sha256");
        return NULL;
    }
    stage_root(root, sizeof root);
    snprintf(dir, dl, "%s/%s", root, sha);
    snprintf(path, sizeof path, "%s/gapps.json", dir);
    size_t n;
    char *t = read_file(path, &n), got[65];
    if (!t) {
        snprintf(why, wl, "the package checked earlier is no longer staged (%s): check it again", path);
        return NULL;
    }
    sha256_hex(t, n, got);
    char err[160];
    struct jv *m = strcmp(got, sha) ? NULL : json_parse(t, err, sizeof err);
    if (!m || !jstr(m, "schema") || strcmp(jstr(m, "schema"), "openbook-gapps/1") || !jget(m, "files")) {
        snprintf(why, wl, "the staged package's manifest changed or is damaged (%s): check the package again", path);
        json_free(m);
        free(t);
        return NULL;
    }
    if (text) {
        *text = t;
        if (tlen) *tlen = n;
    } else {
        free(t);
    }
    return m;
}
