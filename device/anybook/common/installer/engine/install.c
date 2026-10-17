// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// plan (the dry run) and apply (the install), docs/installer.md section 3.5. Both start from one layout
// computation, so the plan the user saw is exactly what apply does: apply re-computes the plan with the same seeds
// (disk GUID, PARTUUIDs, serial number) and refuses if its hash differs from the confirmed one. The plan includes
// the target's identity and a hash of its partition table, so this also catches a disk that changed (S4).
//
// Write order (S9): the old table is wiped first (whole disk), then partition contents, then the boot files, then
// the new GPT; a cut leaves the old table or a blank disk. The loader entry and the fallback path are written only
// after every partition has been read back and verified, so a failed read-back leaves nothing that boots.
#include "common.h"

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <linux/fs.h>

#define ENGINE_VERSION "1"

enum content { C_NONE, C_COPY, C_ZERO_HEAD, C_ZERO_ALL, C_SUPER, C_FAT_NEW };

struct lpart {
    int index;
    char name[40];
    const char *type;
    char uuid[37];
    uint64_t start, bytes;
    enum content content;
    char src[40];        // stick partition (C_COPY, C_SUPER)
    uint64_t src_bytes;  // bytes to copy (C_COPY)
    char sha256[65];
};

struct efile {
    char path[128];
    int shared;       // on the existing ESP (alongside), not on our boot partition
    int activate;     // written only after verification (loader entry, loader.conf, fallback path)
    char src[128];    // path on the stick's ESP, or "" for generated content
    uint8_t *data;    // generated content, or the stick's file once read (check_source)
    uint32_t bytes;
    char sha256[65];
};

struct layout {
    const struct plan_req *r;
    struct disk *t;
    struct source *src;
    struct jv *inst;
    int whole;
    uint8_t disk_guid[16];
    int nparts;
    struct lpart p[24];
    int boot;  // p[] index of our boot partition (ESP or XBOOTLDR)
    const struct part_info *shared_esp;
    char boot_part_uuid[37];
    int nfiles;
    struct efile f[16];
    uint64_t super_bytes;
    uint8_t *super_meta;  // the stick's super metadata for the installed size (check_source)
    uint32_t super_meta_len;
    uint64_t write_bytes, source_bytes;
    struct power pw;
};

static void layout_free(struct layout *L) {
    for (int i = 0; i < L->nfiles; i++) free(L->f[i].data);
    free(L->super_meta);
    memset(L, 0, sizeof *L);
}

int normalized_equal(const char *a, const char *b) {
    if (!a || !b) return 0;
    for (;;) {
        while (*a && isspace((unsigned char)*a)) a++;
        while (*b && isspace((unsigned char)*b)) b++;
        if (!*a || !*b) return !*a && !*b;
        if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return 0;
        a++;
        b++;
    }
}

struct power g_power_override;
int g_power_override_set;

void power_read(struct power *p) {
    memset(p, 0, sizeof *p);
    p->battery_pct = -1;
    p->known = 1;
    char base[512];
    env_path(base, sizeof base, "/sys/class/power_supply");
    DIR *dir = opendir(base);
    struct dirent *e;
    while (dir && (e = readdir(dir))) {
        if (e->d_name[0] == '.') continue;
        char path[800], type[32], v[32];
        snprintf(path, sizeof path, "%s/%s/type", base, e->d_name);
        if (read_text(path, type, sizeof type)) {
            p->known = 0;
            continue;
        }
        if (!strcmp(type, "Battery")) {
            snprintf(path, sizeof path, "%s/%s/scope", base, e->d_name);
            if (!read_text(path, v, sizeof v) && !strcmp(v, "Device")) continue;  // a mouse's or a pen's battery
            snprintf(path, sizeof path, "%s/%s/capacity", base, e->d_name);
            if (!read_text(path, v, sizeof v)) {
                p->have_battery = 1;
                p->battery_pct = atoi(v);
            }
        } else {
            snprintf(path, sizeof path, "%s/%s/online", base, e->d_name);
            if (!read_text(path, v, sizeof v) && atoi(v)) p->ac = 1;
        }
    }
    if (dir) closedir(dir);
    p->ok = p->ac || !p->have_battery || p->battery_pct >= 50;  // S8
}

int plan_seed(struct plan_req *r) {
    uint8_t g[16];
    guid_random(g);
    guid_to_str(g, r->disk_guid);
    uint8_t s[8];
    random_bytes(s, sizeof s);
    for (int i = 0; i < 8; i++) snprintf(r->serialno + 2 * i, 3, "%02X", s[i]);
    for (int i = 0; i < 24; i++) {
        guid_random(g);
        guid_to_str(g, r->part_guids[i]);
    }
    return 0;
}

// ------------------------------------------------------------------ bootconfig blob (scripts/installer/bootconfig.py)
static void bc_render_kv(struct sb *b, const char *k, const char *v) {
    int quote = !*v;
    for (const char *p = v; *p; p++)
        if (strchr(" \t;#,{}=\"'", *p)) quote = 1;
    if (quote) sb_printf(b, "%s = \"%s\"\n", k, v);
    else sb_printf(b, "%s = %s\n", k, v);
}

static uint8_t *bootconfig_blob(struct layout *L, uint32_t *len) {
    struct sb t = {0};
    struct jv *bc = jget(L->inst, "bootconfig");
    for (int i = 0; bc && i < bc->len; i++) {
        const char *k = bc->keys[i];
        if (!strcmp(k, "androidboot.boot_part_uuid") || !strcmp(k, "androidboot.serialno") ||
            !strncmp(k, "androidboot.openbook.live", 25) || !strcmp(k, "androidboot.openbook.logs"))
            continue;
        if (bc->items[i]->t == J_STR) bc_render_kv(&t, k, bc->items[i]->s);
    }
    bc_render_kv(&t, "androidboot.boot_part_uuid", L->boot_part_uuid);
    bc_render_kv(&t, "androidboot.serialno", L->r->serialno);
    if (L->r->locale[0]) bc_render_kv(&t, "androidboot.openbook.locale", L->r->locale);
    if (L->r->keyboard[0]) bc_render_kv(&t, "androidboot.openbook.keyboard", L->r->keyboard);
    bc_render_kv(&t, "androidboot.openbook.installed", L->whole ? "whole" : "alongside");
    sb_add(&t, "\0", 1);
    while (t.n % 4) sb_add(&t, "\0", 1);
    uint32_t size = t.n, sum = 0;
    for (size_t i = 0; i < t.n; i++) sum += (uint8_t)t.p[i];
    uint8_t tail[8];
    memcpy(tail, &size, 4);
    memcpy(tail + 4, &sum, 4);
    sb_add(&t, (char *)tail, 8);
    sb_add(&t, "#BOOTCONFIG\n", 12);
    *len = t.n;
    return (uint8_t *)t.p;
}

static int add_file(struct layout *L, const char *path, int shared, int activate, const char *src, uint8_t *gen,
                    uint32_t genlen) {
    if (L->nfiles >= (int)ARRAY_LEN(L->f)) return -1;
    struct efile *f = &L->f[L->nfiles++];
    snprintf(f->path, sizeof f->path, "%s", path);
    f->shared = shared;
    f->activate = activate;
    if (src) {
        snprintf(f->src, sizeof f->src, "%s", src);
        struct jv *files = jget(jget(L->inst, "esp"), "files");
        struct jv *meta = jget(files, src);
        if (!meta || !jstr(meta, "sha256")) return -1;
        f->bytes = (uint32_t)jnum(meta, "bytes", 0);
        snprintf(f->sha256, sizeof f->sha256, "%s", jstr(meta, "sha256"));
    } else {
        f->data = gen;
        f->bytes = genlen;
        sha256_hex(gen, genlen, f->sha256);
    }
    return 0;
}

static const char *basename_of(const char *p) {
    const char *s = strrchr(p, '/');
    return s ? s + 1 : p;
}

// ------------------------------------------------------------------ layout
static int compute_layout(const struct plan_req *r, struct disk *d, int n, struct source *src, struct layout *L,
                          const char **code, char *why, size_t wl) {
    memset(L, 0, sizeof *L);
    L->r = r;
    L->src = src;
    L->inst = src->install;
    L->boot = -1;
    power_read(&L->pw);
    if (!src->ok) {
        *code = "no_source";
        snprintf(why, wl, "%s", src->why);
        return -1;
    }
    L->t = disk_by_id(d, n, r->target);
    if (!L->t) {
        *code = "no_target";
        snprintf(why, wl, "no disk %s", r->target);
        return -1;
    }
    struct disk *t = L->t;
    uint64_t min = (uint64_t)jnum(L->inst, "min_disk_bytes", 64e9);
    const char *w;
    if (!disk_layout_ok(t, r->layout, min, &w)) {
        *code = "not_eligible";
        snprintf(why, wl, "%s", w);
        return -1;
    }
    L->whole = !strcmp(r->layout, "whole");
    if (guid_from_str(r->disk_guid, L->disk_guid)) {
        *code = "bad_request";
        snprintf(why, wl, "bad seeds");
        return -1;
    }
    if (!L->whole) memcpy(L->disk_guid, t->gpt.disk_guid, 16);
    struct jv *parts = jget(L->inst, "partitions");
    struct jv *mparts = jget(src->manifest, "partitions");
    if (!parts || parts->t != J_ARR || parts->len < 3 || parts->len > 20) {
        *code = "no_source";
        snprintf(why, wl, "install data: bad partition list");
        return -1;
    }
    uint32_t sector = t->sector;
    uint64_t esect_bytes = 16384;  // a 128-entry GPT array
    uint64_t lo, hi;
    int idx[24], nidx = 0;
    if (L->whole) {
        lo = MiB;
        hi = (t->size - sector - (esect_bytes + sector - 1) / sector * sector) / MiB * MiB;
        for (int i = 0; i < 24; i++) idx[nidx++] = i + 1;
    } else {
        lo = t->largest.start;
        hi = t->largest.start + t->largest.bytes;
        // the lowest free GPT entry numbers
        for (uint32_t i = 1; i <= t->gpt.n_entries && nidx < 24; i++) {
            int used = 0;
            for (int k = 0; k < t->gpt.nparts; k++)
                if (t->gpt.p[k].index == (int)i) used = 1;
            if (!used) idx[nidx++] = i;
        }
        for (int k = 0; k < t->nparts; k++)
            if (t->parts[k].index == t->esp_index && !strcmp(t->parts[k].fs, "vfat")) L->shared_esp = &t->parts[k];
    }
    uint64_t cur = lo;
    int gi = 0;
    // Our boot partition first: a new ESP (whole disk, or a disk without one), else an XBOOTLDR partition.
    {
        struct lpart *p = &L->p[L->nparts++];
        int x = !L->whole && L->shared_esp;
        p->index = idx[gi];
        snprintf(p->name, sizeof p->name, "%s", x ? "xbootldr" : "EFI");
        p->type = x ? GUID_XBOOTLDR : GUID_ESP;
        snprintf(p->uuid, sizeof p->uuid, "%s", r->part_guids[gi++]);
        p->start = cur;
        p->bytes = (uint64_t)jnum(L->inst, x ? "xbootldr_mib" : "esp_mib", 512) * MiB;
        p->content = C_FAT_NEW;
        cur += p->bytes;
        L->boot = 0;
    }
    for (int i = 0; i < parts->len; i++) {
        struct jv *e = parts->items[i];
        const char *name = jstr(e, "name"), *s = jstr(e, "src");
        uint64_t mib = (uint64_t)jnum(e, "mib", 0);
        if (!name || gi >= nidx) {
            *code = "no_source";
            snprintf(why, wl, "install data: bad partition entry");
            return -1;
        }
        struct lpart *p = &L->p[L->nparts++];
        p->index = idx[gi];
        snprintf(p->name, sizeof p->name, "%s", name);
        p->type = GUID_LINUX;
        snprintf(p->uuid, sizeof p->uuid, "%s", r->part_guids[gi++]);
        p->start = cur;
        if (mib) {
            p->bytes = mib * MiB;
        } else {  // the rest (userdata, last)
            p->bytes = hi > cur ? hi - cur : 0;
            if (i != parts->len - 1 || p->bytes < 4096 * MiB) {
                *code = "not_eligible";
                snprintf(why, wl, L->whole ? "too_small" : "no_space");
                return -1;
            }
        }
        cur += p->bytes;
        if (s) {
            struct jv *m = jget(mparts, s);
            if (!m || !jstr(m, "sha256")) {
                *code = "no_source";
                snprintf(why, wl, "install data: no hash for %s", s);
                return -1;
            }
            snprintf(p->src, sizeof p->src, "%s", s);
            p->src_bytes = (uint64_t)jnum(m, "bytes", 0);
            snprintf(p->sha256, sizeof p->sha256, "%s", jstr(m, "sha256"));
            if (p->src_bytes > p->bytes) {
                *code = "no_source";
                snprintf(why, wl, "%s (%llu bytes) does not fit %s", s, (unsigned long long)p->src_bytes, name);
                return -1;
            }
            p->content = !strcmp(name, "super") ? C_SUPER : C_COPY;
        } else {
            p->content = !strcmp(name, "misc") ? C_ZERO_ALL : C_ZERO_HEAD;
        }
    }
    if (cur > hi) {
        *code = "not_eligible";
        snprintf(why, wl, L->whole ? "too_small" : "no_space");
        return -1;
    }
    // super: the installed super's size must match its metadata (install.super.device_bytes).
    struct jv *sup = jget(L->inst, "super");
    for (int i = 0; i < L->nparts; i++)
        if (L->p[i].content == C_SUPER) {
            uint64_t dev = (uint64_t)jnum(sup, "device_bytes", 0);
            if (!dev || dev != L->p[i].bytes) {
                *code = "no_source";
                snprintf(why, wl, "install data: super metadata is for %llu bytes, the partition has %llu",
                         (unsigned long long)dev, (unsigned long long)L->p[i].bytes);
                return -1;
            }
            L->super_bytes = dev;
        }
    snprintf(L->boot_part_uuid, sizeof L->boot_part_uuid, "%s", L->p[L->boot].uuid);
    // Boot files.
    struct jv *esp = jget(L->inst, "esp");
    const char *loader = jstr(esp, "loader"), *kernel = jstr(esp, "kernel");
    struct jv *initrds = jget(esp, "initrds");
    struct jv *entry = jget(L->inst, "entry");
    if (!loader || !kernel || !initrds || initrds->t != J_ARR || !entry) {
        *code = "no_source";
        snprintf(why, wl, "install data: no loader files");
        return -1;
    }
    char path[160];
    int rc = add_file(L, "openbook/a/kernel", 0, 0, kernel, NULL, 0);
    struct sb ent = {0};
    sb_printf(&ent, "title %s\nversion %s\nsort-key openbook-1\nlinux /openbook/a/kernel\n",
              jstr(entry, "title") ? jstr(entry, "title") : "OpenBook",
              jstr(entry, "version") ? jstr(entry, "version") : "slot A");
    for (int i = 0; i < initrds->len && !rc; i++) {
        if (initrds->items[i]->t != J_STR) continue;
        snprintf(path, sizeof path, "openbook/a/%s", basename_of(initrds->items[i]->s));
        rc = add_file(L, path, 0, 0, initrds->items[i]->s, NULL, 0);
        sb_printf(&ent, "initrd /%s\n", path);
    }
    uint32_t bclen;
    uint8_t *bc = bootconfig_blob(L, &bclen);
    if (!rc) rc = add_file(L, "openbook/a/bootconfig.img", 0, 0, NULL, bc, bclen);
    sb_printf(&ent, "initrd /openbook/a/bootconfig.img\noptions %s\n",
              jstr(entry, "options") ? jstr(entry, "options") : "bootconfig");
    if (!rc) rc = add_file(L, "loader/entries/openbook-a.conf", 0, 1, NULL, (uint8_t *)ent.p, ent.n);
    if (L->shared_esp) {
        if (!rc) rc = add_file(L, "EFI/OpenBook/systemd-bootx64.efi", 1, 1, loader, NULL, 0);
    } else {
        struct sb lc = {0};
        sb_printf(&lc, "%sdefault openbook-a.conf\n",
                  jstr(L->inst, "loader_conf") ? jstr(L->inst, "loader_conf") : "timeout menu-hidden\n");
        if (!rc) rc = add_file(L, "loader/loader.conf", 0, 1, NULL, (uint8_t *)lc.p, lc.n);
        if (!rc) rc = add_file(L, "EFI/OpenBook/systemd-bootx64.efi", 0, 1, loader, NULL, 0);
        if (!rc) rc = add_file(L, "EFI/BOOT/BOOTX64.EFI", 0, 1, loader, NULL, 0);
    }
    if (rc) {
        *code = "no_source";
        snprintf(why, wl, "install data: missing loader file hashes");
        return -1;
    }
    // Amounts, for progress and the estimate.
    for (int i = 0; i < L->nparts; i++) {
        struct lpart *p = &L->p[i];
        if (p->content == C_COPY || p->content == C_SUPER) L->source_bytes += p->src_bytes;
        if (p->content == C_COPY) L->write_bytes += p->src_bytes;
        if (p->content == C_ZERO_ALL) L->write_bytes += p->bytes;
        if (p->content == C_ZERO_HEAD) L->write_bytes += p->bytes < MiB ? p->bytes : MiB;
    }
    struct jv *ext = jget(sup, "extents");
    for (int i = 0; ext && i < ext->len; i++) L->write_bytes += (uint64_t)jnum(ext->items[i], "bytes", 0);
    L->write_bytes += (uint64_t)jnum(sup, "metadata_bytes", 0);
    for (int i = 0; i < L->nfiles; i++) {
        L->write_bytes += L->f[i].bytes;
        if (L->f[i].src[0]) L->source_bytes += L->f[i].bytes;
    }
    return 0;
}

static const char *seg_kind(const struct part_info *p) {
    if (!strcmp(p->os, "Windows")) return "windows";
    if (!strcmp(p->os, "Linux")) return "linux";
    if (!strcmp(p->os, "OpenBook")) return "openbook";
    if (!strcmp(p->kind, "esp") || !strcmp(p->kind, "xbootldr")) return "efi";
    return "other";
}

static void segs_json(struct jw *w, const char *key, const struct disk *t, const struct layout *L, int after) {
    // Partitions and gaps in disk order, adjacent same kinds merged.
    struct {
        const char *kind;
        uint64_t bytes;
    } s[160];
    int n = 0;
    uint64_t cur = 0;
    if (after && L->whole) {
        s[n].kind = "openbook";
        s[n++].bytes = t->size;
    } else {
        for (int i = 0; i <= t->nparts && n < 150; i++) {
            uint64_t start = i < t->nparts ? t->parts[i].start : t->size;
            if (start > cur + 16 * MiB) {
                int ours = after && cur <= L->p[0].start && L->p[0].start < start;
                if (ours) {
                    uint64_t ob = 0;
                    for (int k = 0; k < L->nparts; k++) ob += L->p[k].bytes;
                    if (L->p[0].start - cur > 16 * MiB) {
                        s[n].kind = "free";
                        s[n++].bytes = L->p[0].start - cur;
                    }
                    s[n].kind = "openbook";
                    s[n++].bytes = ob;
                    uint64_t rest = start - (L->p[0].start + ob);
                    if (rest > 16 * MiB) {
                        s[n].kind = "free";
                        s[n++].bytes = rest;
                    }
                } else {
                    s[n].kind = "free";
                    s[n++].bytes = start - cur;
                }
            }
            if (i == t->nparts) break;
            s[n].kind = seg_kind(&t->parts[i]);
            s[n++].bytes = t->parts[i].bytes;
            cur = t->parts[i].start + t->parts[i].bytes;
        }
    }
    jw_arr(w, key);
    for (int i = 0; i < n;) {
        uint64_t b = s[i].bytes;
        int j = i + 1;
        while (j < n && !strcmp(s[j].kind, s[i].kind)) b += s[j++].bytes;
        jw_obj(w, NULL);
        jw_str(w, "kind", s[i].kind);
        jw_u64(w, "bytes", b);
        jw_str(w, "label", !strcmp(s[i].kind, "windows") ? "Windows" : !strcmp(s[i].kind, "linux") ? "Linux"
                           : !strcmp(s[i].kind, "openbook") ? "OpenBook" : !strcmp(s[i].kind, "efi") ? "EFI"
                           : !strcmp(s[i].kind, "free") ? "" : "Other");
        jw_endo(w);
        i = j;
    }
    jw_enda(w);
}

static void op(struct jw *w, const char *name, const char *fmt, ...) __attribute__((format(printf, 3, 4)));
static void op(struct jw *w, const char *name, const char *fmt, ...) {
    char t[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(t, sizeof t, fmt, ap);
    va_end(ap);
    jw_obj(w, NULL);
    jw_str(w, "op", name);
    jw_str(w, "text", t);
    jw_endo(w);
}

static void mib_str(uint64_t b, char *o, size_t n) {
    if (b >= 1024 * MiB) snprintf(o, n, "%.1f GiB", b / (1024.0 * MiB));
    else snprintf(o, n, "%.1f MiB", b / (double)MiB);
}

static void plan_core(struct layout *L, struct jw *w) {
    const struct disk *t = L->t;
    char a[32], b[32];
    jw_obj(w, NULL);
    jw_str(w, "schema", "openbook-install-plan/1");
    jw_str(w, "engine", ENGINE_VERSION);
    jw_str(w, "layout", L->r->layout);
    jw_obj(w, "request");
    jw_str(w, "target", L->r->target);
    jw_str(w, "layout", L->r->layout);
    jw_str(w, "locale", L->r->locale);
    jw_str(w, "keyboard", L->r->keyboard);
    jw_bool(w, "set_default", L->r->set_default);
    jw_endo(w);
    jw_obj(w, "seeds");
    jw_str(w, "disk_guid", L->r->disk_guid);
    jw_str(w, "serialno", L->r->serialno);
    jw_arr(w, "part_guids");
    for (int i = 0; i < L->nparts; i++) jw_str(w, NULL, L->r->part_guids[i]);
    jw_enda(w);
    jw_endo(w);
    jw_obj(w, "source");
    jw_str(w, "disk", L->src->disk->by_id);
    jw_str(w, "label", L->src->label);
    jw_str(w, "fingerprint", L->src->fingerprint);
    jw_str(w, "manifest_sha256", L->src->manifest_text_sha256);
    jw_endo(w);
    jw_obj(w, "target");
    jw_str(w, "by_id", t->by_id);
    jw_str(w, "name", t->name);
    jw_str(w, "model", t->model);
    jw_str(w, "serial", t->serial);
    jw_str(w, "wwn", t->wwn);
    jw_u64(w, "size_bytes", t->size);
    jw_int(w, "sector_size", t->sector);
    jw_str(w, "bus", t->bus);
    jw_bool(w, "external", t->external);
    jw_str(w, "table", t->table);
    jw_str(w, "table_sha256", t->table_sha256);
    jw_endo(w);
    jw_str(w, "confirm_text", t->model);
    jw_arr(w, L->whole ? "erases" : "keeps");
    for (int i = 0; i < t->nparts; i++) {
        const struct part_info *p = &t->parts[i];
        jw_obj(w, NULL);
        jw_int(w, "index", p->index);
        jw_str(w, "name", p->name);
        jw_str(w, "type", p->kind);
        jw_str(w, "fs", p->fs);
        jw_str(w, "label", p->label);
        jw_str(w, "os", p->os);
        jw_u64(w, "bytes", p->bytes);
        jw_bool(w, "encrypted", p->encrypted);
        jw_endo(w);
    }
    jw_enda(w);
    jw_arr(w, L->whole ? "keeps" : "erases");
    jw_enda(w);
    segs_json(w, "before", t, L, 0);
    segs_json(w, "after", t, L, 1);
    jw_arr(w, "partitions");
    for (int i = 0; i < L->nparts; i++) {
        struct lpart *p = &L->p[i];
        jw_obj(w, NULL);
        jw_int(w, "index", p->index);
        jw_str(w, "name", p->name);
        jw_str(w, "type_guid", p->type);
        jw_str(w, "partuuid", p->uuid);
        jw_u64(w, "start", p->start);
        jw_u64(w, "bytes", p->bytes);
        jw_str(w, "content", p->content == C_COPY ? "copy" : p->content == C_SUPER ? "super" : p->content == C_FAT_NEW
                             ? "fat32" : p->content == C_ZERO_ALL ? "zero" : "zero_head");
        if (p->src[0]) {
            jw_str(w, "source", p->src);
            jw_u64(w, "source_bytes", p->src_bytes);
            jw_str(w, "sha256", p->sha256);
        }
        jw_endo(w);
    }
    jw_enda(w);
    jw_arr(w, "files");
    for (int i = 0; i < L->nfiles; i++) {
        struct efile *f = &L->f[i];
        jw_obj(w, NULL);
        jw_str(w, "path", f->path);
        jw_str(w, "on", f->shared ? "existing_esp" : L->p[L->boot].name);
        jw_str(w, "source", f->src[0] ? f->src : "generated");
        jw_u64(w, "bytes", f->bytes);
        jw_str(w, "sha256", f->sha256);
        jw_bool(w, "after_verify", f->activate);
        jw_endo(w);
    }
    jw_enda(w);
    jw_obj(w, "boot");
    jw_str(w, "boot_part_uuid", L->boot_part_uuid);
    jw_str(w, "serialno", L->r->serialno);
    jw_str(w, "entry", "loader/entries/openbook-a.conf");
    jw_bool(w, "fallback_path", !L->shared_esp);
    jw_str(w, "nvram", E.efivars ? "planned" : "unavailable");
    jw_bool(w, "set_default", L->r->set_default);
    jw_endo(w);
    uint64_t verify = L->write_bytes;
    jw_u64(w, "bytes_to_write", L->write_bytes);
    jw_u64(w, "bytes_to_check", L->source_bytes);
    jw_int(w, "estimated_seconds", (long long)((L->source_bytes + L->write_bytes + verify) / (120.0 * 1e6)) + 10);
    jw_arr(w, "warnings");
    if (!E.efivars) jw_str(w, NULL, "nvram_unavailable");
    if (t->external) jw_str(w, NULL, "external");
    if (t->encrypted) jw_str(w, NULL, L->whole ? "encrypted_erased" : "encrypted_kept");
    jw_enda(w);
    // The operations, in order, as "View the plan" shows them (S5).
    jw_arr(w, "operations");
    if (L->whole) {
        op(w, "check_source", "Check the stick's partitions and boot files against its manifest (%s)",
           L->src->label);
        op(w, "recheck", "Re-check the disk's identity (serial %s, %llu bytes) and partition table (sha256 %.16s)",
           t->serial, (unsigned long long)t->size, t->table_sha256);
        op(w, "wipe_table", "Erase the partition table: the first and last MiB of %s (protective MBR, primary and "
                            "backup GPT)", t->by_id);
    } else {
        op(w, "check_source", "Check the stick's partitions and boot files against its manifest (%s)",
           L->src->label);
        op(w, "recheck", "Re-check the disk's identity (serial %s, %llu bytes) and partition table (sha256 %.16s)",
           t->serial, (unsigned long long)t->size, t->table_sha256);
        mib_str(t->largest.bytes, a, sizeof a);
        op(w, "use_free", "Use the free space at %llu (%s); existing partitions are not moved, resized or written",
           (unsigned long long)t->largest.start, a);
    }
    for (int i = 0; i < L->nparts; i++) {
        struct lpart *p = &L->p[i];
        mib_str(p->bytes, a, sizeof a);
        mib_str(p->src_bytes, b, sizeof b);
        switch (p->content) {
        case C_COPY:
            op(w, "copy", "Copy %s (%s, sha256 %.16s) from the stick to partition %d \"%s\" at %llu (%s)", p->src, b,
               p->sha256, p->index, p->name, (unsigned long long)p->start, a);
            break;
        case C_ZERO_ALL:
            op(w, "zero", "Zero partition %d \"%s\" at %llu (%s)", p->index, p->name, (unsigned long long)p->start, a);
            break;
        case C_ZERO_HEAD:
            op(w, "zero", "Zero the first MiB of partition %d \"%s\" at %llu (%s)%s", p->index, p->name,
               (unsigned long long)p->start, a,
               !strcmp(p->name, "userdata") || !strcmp(p->name, "metadata") ? "; Android formats it on first boot" : "");
            break;
        case C_SUPER: {
            struct jv *ext = jget(jget(L->inst, "super"), "extents");
            op(w, "super", "Write partition %d \"super\" at %llu (%s): %d logical partitions from the stick's super, "
                           "then its metadata for this size (sha256 %.16s)",
               p->index, (unsigned long long)p->start, a, ext ? ext->len : 0,
               jstr(jget(L->inst, "super"), "metadata_sha256") ? jstr(jget(L->inst, "super"), "metadata_sha256") : "");
            break;
        }
        case C_FAT_NEW:
            op(w, "format", "Format partition %d \"%s\" at %llu (%s) as FAT32, label OPENBOOK", p->index, p->name,
               (unsigned long long)p->start, a);
            break;
        default:
            break;
        }
    }
    for (int i = 0; i < L->nfiles; i++)
        if (!L->f[i].activate)
            op(w, "file", "Write %s on %s (%u bytes, sha256 %.16s)", L->f[i].path,
               L->f[i].shared ? "the existing EFI partition" : L->p[L->boot].name, L->f[i].bytes, L->f[i].sha256);
    if (L->whole)
        op(w, "write_table", "Write a new GPT (disk GUID %s) with %d partitions; boot_part_uuid %s",
           L->r->disk_guid, L->nparts, L->boot_part_uuid);
    else
        op(w, "add_table", "Add %d partitions to the existing GPT (backup first, then primary); boot_part_uuid %s",
           L->nparts, L->boot_part_uuid);
    op(w, "verify", "Read back every written partition and file and compare its sha256");
    for (int i = 0; i < L->nfiles; i++)
        if (L->f[i].activate)
            op(w, "activate", "After verification: write %s on %s (%u bytes)", L->f[i].path,
               L->f[i].shared ? "the existing EFI partition" : L->p[L->boot].name, L->f[i].bytes);
    if (E.efivars)
        op(w, "nvram", "Add the firmware boot entry \"OpenBook\" -> \\EFI\\OpenBook\\systemd-bootx64.efi%s",
           L->r->set_default ? " and make it the first in BootOrder" : "");
    else
        op(w, "nvram", "No firmware boot entry: this kernel has no efivarfs (docs/installer.md decision 6)%s",
           L->shared_esp ? "; pick OpenBook from the firmware's boot menu or add an entry in its setup"
                         : "; the firmware boots the disk through the fallback path EFI/BOOT/BOOTX64.EFI");
    op(w, "report", "Save the install report and log to openbook/logs/ on the stick and on the new %s",
       L->p[L->boot].name);
    jw_enda(w);
    jw_endo(w);
}

int plan_build(const struct plan_req *r, struct disk *d, int n, struct source *src, struct sb *out,
               char plan_sha256[65], const char **code, char *why, size_t wl) {
    struct layout L;
    if (compute_layout(r, d, n, src, &L, code, why, wl)) {
        layout_free(&L);
        return -1;
    }
    struct jw w = {0};
    plan_core(&L, &w);
    sha256_hex(w.b.p, w.b.n, plan_sha256);
    char ts[32];
    utc_stamp(ts, sizeof ts, 0);
    sb_printf(out, "{\"plan_sha256\":\"%s\",\"created\":\"%s\",%s", plan_sha256, ts, w.b.p + 1);
    sb_free(&w.b);
    layout_free(&L);
    return 0;
}

int plan_req_from_json(const struct jv *plan, struct plan_req *r) {
    memset(r, 0, sizeof *r);
    struct jv *q = jget(plan, "request"), *s = jget(plan, "seeds");
    if (!q || !s) return -1;
    snprintf(r->target, sizeof r->target, "%s", jstr(q, "target") ? jstr(q, "target") : "");
    snprintf(r->layout, sizeof r->layout, "%s", jstr(q, "layout") ? jstr(q, "layout") : "");
    snprintf(r->locale, sizeof r->locale, "%s", jstr(q, "locale") ? jstr(q, "locale") : "");
    snprintf(r->keyboard, sizeof r->keyboard, "%s", jstr(q, "keyboard") ? jstr(q, "keyboard") : "");
    r->set_default = jbool(q, "set_default", 0);
    snprintf(r->disk_guid, sizeof r->disk_guid, "%s", jstr(s, "disk_guid") ? jstr(s, "disk_guid") : "");
    snprintf(r->serialno, sizeof r->serialno, "%s", jstr(s, "serialno") ? jstr(s, "serialno") : "");
    struct jv *g = jget(s, "part_guids");
    for (int i = 0; g && i < g->len && i < 24; i++)
        if (g->items[i]->t == J_STR) snprintf(r->part_guids[i], sizeof r->part_guids[i], "%s", g->items[i]->s);
    // Unused seeds (more entries than partitions) only need to be valid GUIDs.
    for (int i = g ? g->len : 0; i < 24; i++) snprintf(r->part_guids[i], 37, "00000000-0000-4000-8000-%012d", i);
    return r->target[0] && r->layout[0] && r->disk_guid[0] ? 0 : -1;
}

// ------------------------------------------------------------------ apply
static const char *const STEPS[] = {"check_source", "prepare_disk", "boot_images", "system",
                                    "boot_entry",   "verify",       "report"};
static char step_state[7][12];
static double step_t0[7], step_secs[7];
static uint64_t prog_done, prog_total;
static uint64_t step_base, step_total[7];  // the running step's own bytes, for "2.1 GB of 4.6 GB" under a step
static int cur_step_i = -1;
static double prog_last, prog_start;
static const char *cur_step = "";

static void step(int i, const char *state) {
    snprintf(step_state[i], sizeof step_state[i], "%s", state);
    if (!strcmp(state, "running")) {
        step_t0[i] = now_s();
        cur_step = STEPS[i];
        cur_step_i = i;
        step_base = prog_done;
    } else if (step_t0[i]) {
        step_secs[i] = now_s() - step_t0[i];
    }
    char e[160];
    snprintf(e, sizeof e, "{\"event\":\"step\",\"step\":\"%s\",\"state\":\"%s\"}", STEPS[i], state);
    emit_event(e);
    LOG("step %s: %s", STEPS[i], state);
}

static void progress(uint64_t add, int force) {
    prog_done += add;
    double t = now_s();
    if (!force && t - prog_last < 0.5) return;
    prog_last = t;
    double pct = prog_total ? 100.0 * prog_done / prog_total : 0;
    if (pct > 100) pct = 100;
    double el = t - prog_start, eta = pct > 1 ? el * (100 - pct) / pct : -1;
    uint64_t sd = prog_done - step_base, st = cur_step_i >= 0 ? step_total[cur_step_i] : 0;
    if (sd > st) st = sd;
    char e[320];
    snprintf(e, sizeof e,
             "{\"event\":\"progress\",\"step\":\"%s\",\"done\":%llu,\"total\":%llu,\"pct\":%.1f,\"eta_s\":%d,"
             "\"all_done\":%llu,\"all_total\":%llu}",
             cur_step, (unsigned long long)sd, (unsigned long long)st, pct, (int)(eta < 0 ? -1 : eta),
             (unsigned long long)prog_done, (unsigned long long)prog_total);
    emit_event(e);
}

// Hash n bytes at off (feeding progress); out = hex.
static int hash_region(int fd, uint64_t off, uint64_t n, char out[65]) {
    static uint8_t buf[4 << 20];
    struct sha256 c;
    sha256_init(&c);
    for (uint64_t done = 0; done < n;) {
        size_t k = n - done < sizeof buf ? n - done : sizeof buf;
        if (pread_all(fd, buf, k, off + done)) return -1;
        sha256_update(&c, buf, k);
        done += k;
        progress(k, 0);
    }
    sha256_final_hex(&c, out);
    return 0;
}

static int copy_region(int sfd, uint64_t soff, int dfd, uint64_t doff, uint64_t n, char out[65]) {
    static uint8_t buf[4 << 20];
    struct sha256 c;
    sha256_init(&c);
    for (uint64_t done = 0; done < n;) {
        size_t k = n - done < sizeof buf ? n - done : sizeof buf;
        if (pread_all(sfd, buf, k, soff + done)) return -1;
        sha256_update(&c, buf, k);
        if (pwrite_all(dfd, buf, k, doff + done)) return -1;
        done += k;
        progress(k, 0);
    }
    sha256_final_hex(&c, out);
    return 0;
}

void drop_cache(int fd) {
    fsync(fd);
    ioctl(fd, BLKFLSBUF, 0);  // needs CAP_SYS_ADMIN; fadvise below works without
    posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED);
}

struct verified {
    char what[96];
    uint64_t bytes;
    char sha256[65];
    int ok;
};

static int write_files(struct layout *L, int fd, int activate, char *err, size_t el) {
    struct fat boot, shared;
    struct lpart *bp = &L->p[L->boot];
    if (fat_open(&boot, fd, bp->start, bp->bytes)) {
        snprintf(err, el, "cannot open the new %s FAT: %s", bp->name, strerror(errno));
        return -1;
    }
    int have_shared = 0, rc = 0;
    for (int i = 0; i < L->nfiles && !rc; i++) {
        struct efile *f = &L->f[i];
        if (f->activate != activate) continue;
        struct fat *v = &boot;
        if (f->shared) {
            if (!have_shared) {
                if (fat_open(&shared, fd, L->shared_esp->start, L->shared_esp->bytes)) {
                    snprintf(err, el, "cannot open the existing EFI partition: %s", strerror(errno));
                    rc = -1;
                    break;
                }
                have_shared = 1;
            }
            v = &shared;
        }
        if (fat_write(v, f->path, f->data, f->bytes)) {
            snprintf(err, el, "writing %s: %s", f->path, strerror(errno));
            rc = -1;
        }
        LOG("wrote %s%s (%u bytes)", f->shared ? "existing ESP: " : "", f->path, f->bytes);
        progress(f->bytes, 0);
    }
    fat_close(&boot);
    if (have_shared) fat_close(&shared);
    return rc;
}

static int verify_files(struct layout *L, int fd, int activate, struct verified *v, int *nv, char *err, size_t el) {
    struct fat boot, shared;
    struct lpart *bp = &L->p[L->boot];
    if (fat_open(&boot, fd, bp->start, bp->bytes)) {
        snprintf(err, el, "cannot re-open the new %s FAT", bp->name);
        return -1;
    }
    int have_shared = L->shared_esp && !fat_open(&shared, fd, L->shared_esp->start, L->shared_esp->bytes);
    int rc = 0;
    for (int i = 0; i < L->nfiles; i++) {
        struct efile *f = &L->f[i];
        if (f->activate != activate) continue;
        uint32_t len = 0;
        uint8_t *d = fat_read(f->shared ? (have_shared ? &shared : &boot) : &boot, f->path, &len);
        struct verified *x = &v[(*nv)++];
        snprintf(x->what, sizeof x->what, "%s%s", f->shared ? "esp:" : "", f->path);
        x->bytes = len;
        if (d) sha256_hex(d, len, x->sha256);
        x->ok = d && len == f->bytes && !strcmp(x->sha256, f->sha256);
        free(d);
        progress(f->bytes, 0);
        if (!x->ok) {
            snprintf(err, el, "read-back of %s does not match", f->path);
            rc = -1;
        }
    }
    fat_close(&boot);
    if (have_shared) fat_close(&shared);
    return rc;
}

static void report_write(struct layout *L, int tfd, const char *json, const char *ts) {
    char path[96];
    // On the new boot partition.
    if (tfd >= 0 && L && L->boot >= 0) {
        struct fat f;
        struct lpart *bp = &L->p[L->boot];
        if (!fat_open(&f, tfd, bp->start, bp->bytes) && fat_exists(&f, "openbook/a/kernel", NULL)) {
            snprintf(path, sizeof path, "openbook/logs/install-%s.json", ts);
            fat_write(&f, path, json, strlen(json));
            snprintf(path, sizeof path, "openbook/logs/install-%s.log", ts);
            fat_write(&f, path, g_install_log.p ? g_install_log.p : "", g_install_log.n);
            fat_close(&f);
            fsync(tfd);
        }
    }
}

static void report_to_stick(struct source *s, const char *json, const char *ts) {
    if (!s || !s->disk || E.logs_mode) return;  // the "save logs" helper owns the stick's ESP on such a boot
    int fd = open(s->disk->dev, O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        LOG("report: cannot open the stick for writing: %s", strerror(errno));
        return;
    }
    struct fat f;
    uint64_t off = s->esp->first * s->disk->sector, size = (s->esp->last - s->esp->first + 1) * s->disk->sector;
    drop_cache(fd);
    if (!fat_open(&f, fd, off, size)) {
        char path[96];
        snprintf(path, sizeof path, "openbook/logs/install-%s.json", ts);
        if (fat_write(&f, path, json, strlen(json))) LOG("report: writing %s on the stick failed", path);
        snprintf(path, sizeof path, "openbook/logs/install-%s.log", ts);
        fat_write(&f, path, g_install_log.p ? g_install_log.p : "", g_install_log.n);
        fat_close(&f);
    }
    fsync(fd);
    close(fd);
}

int apply_run(const struct plan_req *r, const char *expect_sha, const char *typed, const char *confirm_disk,
              struct sb *result) {
    double t0 = now_s();
    char ts[32], started[32], err[300] = "";
    utc_stamp(ts, sizeof ts, 1);
    utc_stamp(started, sizeof started, 0);
    for (int i = 0; i < 7; i++) {
        snprintf(step_state[i], sizeof step_state[i], "pending");
        step_t0[i] = step_secs[i] = 0;
    }
    prog_done = prog_total = 0;
    prog_start = prog_last = now_s();
    const char *code = NULL, *failed = NULL;
    int fd = -1, verified_ok = 0, nv = 0;
    struct verified *v = calloc(64, sizeof *v);
    struct disk *d = NULL;
    int n = disks_scan(&d);
    struct source src;
    source_open(&src, d, n);
    struct layout L;
    int have_layout = 0;
    struct sb plan = {0};
    char sha[65] = "";
    LOG("openbook-install %s: apply %s on %s (%s), SELinux %s", ENGINE_VERSION, r->layout, r->target,
        src.label[0] ? src.label : "no source", E.selinux);

    // ---- the plan, re-computed with the confirmed seeds
    if (plan_build(r, d, n, &src, &plan, sha, &code, err, sizeof err)) goto fail_early;
    if (expect_sha && strcmp(expect_sha, sha)) {
        code = "plan_changed";
        snprintf(err, sizeof err, "the plan changed since it was shown (now %.16s, confirmed %.16s): the disk or the "
                                  "stick changed. Look at the disk again.", sha, expect_sha);
        goto fail_early;
    }
    if (compute_layout(r, d, n, &src, &L, &code, err, sizeof err)) goto fail_early;
    have_layout = 1;
    // ---- S3: typed confirmation, or the unattended pair --confirm-disk + OPENBOOK_INSTALL_ERASE
    if (typed) {
        if (!normalized_equal(typed, L.t->model)) {
            code = "confirm_mismatch";
            snprintf(err, sizeof err, "the typed name does not match the disk's name");
            goto fail_early;
        }
    } else {
        const char *env = getenv("OPENBOOK_INSTALL_ERASE");
        const char *cd = confirm_disk ? confirm_disk : "";
        if (!strncmp(cd, "/dev/disk/by-id/", 16)) cd += 16;
        if (env && !strncmp(env, "/dev/disk/by-id/", 16)) env += 16;
        if (strcmp(cd, L.t->by_id) || !env || strcmp(env, L.t->by_id)) {
            code = "confirm_mismatch";
            snprintf(err, sizeof err, "unattended install needs --confirm-disk /dev/disk/by-id/%s and "
                                      "OPENBOOK_INSTALL_ERASE=/dev/disk/by-id/%s", L.t->by_id, L.t->by_id);
            goto fail_early;
        }
    }
    // ---- S8
    if (!L.pw.known) {
        if (g_power_override_set) {
            L.pw = g_power_override;
            LOG("power from the app: AC %s, battery %d %%", L.pw.ac ? "on" : "off", L.pw.battery_pct);
        } else {
            LOG("power supplies unreadable and none given: the power rule (S8) is not checked");
        }
    }
    if (!L.pw.ok) {
        code = "power";
        snprintf(err, sizeof err, "connect the charger: the battery is at %d %%", L.pw.battery_pct);
        goto fail_early;
    }
    prog_total = L.source_bytes + 2 * L.write_bytes;
    // Each step's own amount: check_source reads the sources, boot_images and system write, verify reads back.
    memset(step_total, 0, sizeof step_total);
    step_total[0] = L.source_bytes;
    for (int i = 0; i < L.nparts; i++) {
        struct lpart *p = &L.p[i];
        if (p->content == C_COPY) step_total[2] += p->src_bytes;
        if (p->content == C_ZERO_ALL) step_total[2] += p->bytes;
        if (p->content == C_ZERO_HEAD) step_total[2] += p->bytes < MiB ? p->bytes : MiB;
    }
    step_total[3] = L.write_bytes - step_total[2];
    for (int i = 0; i < L.nfiles; i++) {
        if (!L.f[i].activate) step_total[4] += L.f[i].bytes;
        step_total[3] -= L.f[i].bytes < step_total[3] ? L.f[i].bytes : step_total[3];
    }
    step_total[5] = L.write_bytes;
    cur_step_i = -1;
    step_base = 0;
    LOG("plan %s: %d partitions, %llu bytes to write, target %s (%s, %llu bytes)", sha, L.nparts,
        (unsigned long long)L.write_bytes, L.t->by_id, L.t->model, (unsigned long long)L.t->size);

    // ---- 1. check_source (S10)
    step(0, "running");
    for (int i = 0; i < L.nparts; i++) {
        struct lpart *p = &L.p[i];
        if (p->content != C_COPY && p->content != C_SUPER) continue;
        const struct gpt_part *sp = gpt_find(&src.disk->gpt, p->src);
        char got[65];
        if (!sp || hash_region(src.fd, sp->first * src.disk->sector, p->src_bytes, got)) {
            snprintf(err, sizeof err, "cannot read %s on the stick: %s", p->src, strerror(errno));
            goto fail;
        }
        if (strcmp(got, p->sha256)) {
            snprintf(err, sizeof err, "the stick's %s does not match its manifest (sha256 %.16s, expected %.16s): "
                                      "the stick may be failing or badly written", p->src, got, p->sha256);
            goto fail;
        }
        LOG("source %s: %llu bytes, sha256 ok", p->src, (unsigned long long)p->src_bytes);
    }
    {
        struct fat sf;
        uint64_t off = src.esp->first * src.disk->sector, size = (src.esp->last - src.esp->first + 1) * src.disk->sector;
        if (fat_open(&sf, src.fd, off, size)) {
            snprintf(err, sizeof err, "cannot read the stick's EFI partition");
            goto fail;
        }
        for (int i = 0; i < L.nfiles; i++) {
            struct efile *f = &L.f[i];
            if (!f->src[0]) continue;
            uint32_t len;
            uint8_t *data = fat_read(&sf, f->src, &len);
            char got[65] = "";
            if (data) sha256_hex(data, len, got);
            if (!data || len != f->bytes || strcmp(got, f->sha256)) {
                free(data);
                fat_close(&sf);
                snprintf(err, sizeof err, "the stick's %s does not match its manifest", f->src);
                goto fail;
            }
            f->data = data;
            progress(len, 0);
        }
        // super metadata for the installed size
        struct jv *sup = jget(L.inst, "super");
        const char *mf = jstr(sup, "metadata_file");
        uint32_t len = 0;
        uint8_t *meta = mf ? fat_read(&sf, mf, &len) : NULL;
        char got[65] = "";
        if (meta) sha256_hex(meta, len, got);
        fat_close(&sf);
        if (!meta || len != (uint32_t)jnum(sup, "metadata_bytes", 0) || !jstr(sup, "metadata_sha256") ||
            strcmp(got, jstr(sup, "metadata_sha256"))) {
            free(meta);
            snprintf(err, sizeof err, "the stick's super metadata (%s) does not match its manifest", mf ? mf : "?");
            goto fail;
        }
        L.super_meta = meta;
        L.super_meta_len = len;
    }
    step(0, "done");

    // ---- 2. prepare_disk (S1 at open time, S4)
    step(1, "running");
    fd = disk_open(L.t, 1);
    if (fd < 0) {
        snprintf(err, sizeof err, "cannot open %s for writing: %s%s", L.t->dev, strerror(errno),
                 errno == EBUSY ? " (in use: a partition is mounted or held)" : "");
        goto fail;
    }
    {
        char now_hash[65];
        disk_table_hash(fd, L.t, now_hash);
        if (strcmp(now_hash, L.t->table_sha256)) {
            snprintf(err, sizeof err, "the disk's partition table changed since the plan; nothing was written");
            goto fail;
        }
    }
    if (L.whole) {
        LOG("wiping the partition table of %s", L.t->by_id);
        if (gpt_wipe(fd, L.t->sector, L.t->size / L.t->sector)) {
            snprintf(err, sizeof err, "wiping the table: %s", strerror(errno));
            goto fail;
        }
        fsync(fd);
    }
    step(1, "done");

    // ---- 3. boot_images
    step(2, "running");
    for (int i = 0; i < L.nparts; i++) {
        struct lpart *p = &L.p[i];
        if (p->content == C_COPY) {
            const struct gpt_part *sp = gpt_find(&src.disk->gpt, p->src);
            char got[65];
            if (zero_range(fd, p->start, p->bytes < MiB ? p->bytes : MiB) ||
                copy_region(src.fd, sp->first * src.disk->sector, fd, p->start, p->src_bytes, got)) {
                snprintf(err, sizeof err, "copying %s: %s", p->src, strerror(errno));
                goto fail;
            }
            if (strcmp(got, p->sha256)) {
                snprintf(err, sizeof err, "%s changed while it was copied", p->src);
                goto fail;
            }
            LOG("copied %s -> partition %d \"%s\" (%llu bytes)", p->src, p->index, p->name,
                (unsigned long long)p->src_bytes);
        } else if (p->content == C_ZERO_ALL || p->content == C_ZERO_HEAD) {
            uint64_t z = p->content == C_ZERO_ALL || p->bytes < MiB ? p->bytes : MiB;
            if (zero_range(fd, p->start, z)) {
                snprintf(err, sizeof err, "zeroing %s: %s", p->name, strerror(errno));
                goto fail;
            }
            progress(z, 0);
        }
    }
    fsync(fd);
    step(2, "done");

    // ---- 4. system: super's logical partitions, then its metadata for the installed size
    step(3, "running");
    for (int i = 0; i < L.nparts; i++) {
        struct lpart *p = &L.p[i];
        if (p->content != C_SUPER) continue;
        const struct gpt_part *sp = gpt_find(&src.disk->gpt, p->src);
        struct jv *sup = jget(L.inst, "super"), *ext = jget(sup, "extents");
        for (int k = 0; ext && k < ext->len; k++) {
            struct jv *e = ext->items[k];
            uint64_t so = (uint64_t)jnum(e, "src", 0), dO = (uint64_t)jnum(e, "dst", 0), b = (uint64_t)jnum(e, "bytes", 0);
            char got[65];
            if (dO + b > p->bytes || so + b > p->src_bytes) {
                snprintf(err, sizeof err, "super extent %s out of range", jstr(e, "name") ? jstr(e, "name") : "?");
                goto fail;
            }
            if (copy_region(src.fd, sp->first * src.disk->sector + so, fd, p->start + dO, b, got)) {
                snprintf(err, sizeof err, "copying %s: %s", jstr(e, "name"), strerror(errno));
                goto fail;
            }
            if (jstr(e, "sha256") && strcmp(got, jstr(e, "sha256"))) {
                snprintf(err, sizeof err, "%s does not match the manifest", jstr(e, "name"));
                goto fail;
            }
            LOG("super: %s, %llu bytes at %llu", jstr(e, "name"), (unsigned long long)b, (unsigned long long)dO);
        }
        if (pwrite_all(fd, L.super_meta, L.super_meta_len, p->start)) {
            snprintf(err, sizeof err, "writing super metadata: %s", strerror(errno));
            goto fail;
        }
        progress(L.super_meta_len, 0);
        LOG("super: metadata for %llu bytes written", (unsigned long long)p->bytes);
    }
    fsync(fd);
    step(3, "done");

    // ---- 5. boot_entry: the boot partition's FAT and files, then the partition table
    step(4, "running");
    {
        struct lpart *bp = &L.p[L.boot];
        uint32_t volid;
        random_bytes(&volid, sizeof volid);
        if (fat_format32(fd, bp->start, bp->bytes, L.t->sector, "OPENBOOK", volid)) {
            snprintf(err, sizeof err, "formatting %s: %s", bp->name, strerror(errno));
            goto fail;
        }
        if (write_files(&L, fd, 0, err, sizeof err)) goto fail;
        struct gpt_part gp[24];
        memset(gp, 0, sizeof gp);
        for (int i = 0; i < L.nparts; i++) {
            gp[i].index = L.p[i].index;
            guid_from_str(L.p[i].type, gp[i].type);
            guid_from_str(L.p[i].uuid, gp[i].uniq);
            gp[i].first = L.p[i].start / L.t->sector;
            gp[i].last = (L.p[i].start + L.p[i].bytes) / L.t->sector - 1;
            snprintf(gp[i].name, sizeof gp[i].name, "%s", L.p[i].name);
        }
        fsync(fd);
        int rc = L.whole ? gpt_write_new(fd, L.t->sector, L.t->size / L.t->sector, L.disk_guid, gp, L.nparts)
                         : gpt_write_add(fd, &L.t->gpt, gp, L.nparts);
        if (rc) {
            snprintf(err, sizeof err, "writing the partition table: %s", strerror(errno));
            goto fail;
        }
        fsync(fd);
        LOG("partition table %s: %d partitions", L.whole ? "written" : "extended", L.nparts);
    }
    step(4, "done");

    // ---- 6. verify (S9), then activate
    step(5, "running");
    drop_cache(fd);
    {
        struct gpt g;
        if (gpt_read(fd, L.t->sector, L.t->size / L.t->sector, &g)) {
            snprintf(err, sizeof err, "the new partition table does not read back: %s", g.why);
            goto fail;
        }
        for (int i = 0; i < L.nparts; i++) {
            const struct gpt_part *q = gpt_find_uuid(&g, L.p[i].uuid);
            struct verified *x = &v[nv++];
            snprintf(x->what, sizeof x->what, "gpt:%s", L.p[i].name);
            x->bytes = L.p[i].bytes;
            x->ok = q && q->index == L.p[i].index && q->first * L.t->sector == L.p[i].start &&
                    (q->last + 1) * L.t->sector == L.p[i].start + L.p[i].bytes && !strcmp(q->name, L.p[i].name);
            if (!x->ok) {
                gpt_free(&g);
                snprintf(err, sizeof err, "partition %s is not in the table as planned", L.p[i].name);
                goto fail;
            }
        }
        gpt_free(&g);
    }
    for (int i = 0; i < L.nparts; i++) {
        struct lpart *p = &L.p[i];
        if (p->content == C_COPY) {
            struct verified *x = &v[nv++];
            snprintf(x->what, sizeof x->what, "%s", p->name);
            x->bytes = p->src_bytes;
            if (hash_region(fd, p->start, p->src_bytes, x->sha256) || strcmp(x->sha256, p->sha256)) {
                snprintf(err, sizeof err, "read-back of %s does not match (sha256 %.16s)", p->name, x->sha256);
                goto fail;
            }
            x->ok = 1;
        } else if (p->content == C_SUPER) {
            struct jv *sup = jget(L.inst, "super"), *ext = jget(sup, "extents");
            for (int k = 0; ext && k < ext->len; k++) {
                struct jv *e = ext->items[k];
                struct verified *x = &v[nv++];
                snprintf(x->what, sizeof x->what, "super:%s", jstr(e, "name") ? jstr(e, "name") : "?");
                x->bytes = (uint64_t)jnum(e, "bytes", 0);
                if (hash_region(fd, p->start + (uint64_t)jnum(e, "dst", 0), x->bytes, x->sha256) ||
                    (jstr(e, "sha256") && strcmp(x->sha256, jstr(e, "sha256")))) {
                    snprintf(err, sizeof err, "read-back of %s does not match", x->what);
                    goto fail;
                }
                x->ok = 1;
            }
            struct verified *x = &v[nv++];
            snprintf(x->what, sizeof x->what, "super:metadata");
            x->bytes = L.super_meta_len;
            if (hash_region(fd, p->start, x->bytes, x->sha256) || strcmp(x->sha256, jstr(sup, "metadata_sha256"))) {
                snprintf(err, sizeof err, "read-back of the super metadata does not match");
                goto fail;
            }
            x->ok = 1;
        }
    }
    if (verify_files(&L, fd, 0, v, &nv, err, sizeof err)) goto fail;
    LOG("verified %d partitions and files", nv);
    // Activate: the loader entry and fallback path only now (S9).
    if (write_files(&L, fd, 1, err, sizeof err)) goto fail;
    drop_cache(fd);
    if (verify_files(&L, fd, 1, v, &nv, err, sizeof err)) goto fail;
    verified_ok = 1;
    if (ioctl(fd, BLKRRPART, 0) == 0) LOG("the kernel re-read the partition table");
    step(5, "done");
    goto report;

fail_early:
    failed = "plan";
    LOG("refused (%s): %s", code ? code : "error", err);
    goto out_json;
fail:
    for (int i = 0; i < 7; i++)
        if (!strcmp(step_state[i], "running")) {
            failed = STEPS[i];
            step(i, "failed");
        }
    if (!failed) failed = "unknown";
    LOG("FAILED in %s: %s", failed, err);
    code = code ? code : "io";
report:
    step(6, "running");
out_json:;
    int reporting = !failed || strcmp(failed, "plan");
    // The report is this step's output: it is "done" in the report it writes.
    if (reporting) snprintf(step_state[6], sizeof step_state[6], "done");
    char finished[32];
    utc_stamp(finished, sizeof finished, 0);
    struct jw w = {0};
    jw_obj(&w, NULL);
    jw_str(&w, "schema", "openbook-install-report/1");
    jw_str(&w, "engine", ENGINE_VERSION);
    jw_bool(&w, "ok", verified_ok);
    jw_bool(&w, "verified", verified_ok);
    jw_str(&w, "code", verified_ok ? NULL : (code ? code : "io"));
    jw_str(&w, "error", verified_ok ? NULL : err);
    jw_str(&w, "failed_step", verified_ok ? NULL : failed);
    jw_str(&w, "started", started);
    jw_str(&w, "finished", finished);
    jw_dbl(&w, "seconds", now_s() - t0, 1);
    jw_str(&w, "plan_sha256", sha);
    jw_str(&w, "selinux", E.selinux);
    jw_obj(&w, "steps");
    for (int i = 0; i < 7; i++) {
        jw_obj(&w, STEPS[i]);
        jw_str(&w, "state", step_state[i]);
        jw_dbl(&w, "seconds", step_secs[i], 1);
        jw_endo(&w);
    }
    jw_endo(&w);
    jw_arr(&w, "verified_items");
    for (int i = 0; i < nv; i++) {
        jw_obj(&w, NULL);
        jw_str(&w, "what", v[i].what);
        jw_u64(&w, "bytes", v[i].bytes);
        jw_str(&w, "sha256", v[i].sha256[0] ? v[i].sha256 : NULL);
        jw_bool(&w, "ok", v[i].ok);
        jw_endo(&w);
    }
    jw_enda(&w);
    jw_str(&w, "boot_entry", verified_ok ? "loader/entries/openbook-a.conf" : NULL);
    jw_str(&w, "nvram", E.efivars ? "not_implemented" : "unavailable");
    jw_bool(&w, "fallback_path", have_layout && !L.shared_esp && verified_ok);
    char rp[96], lp[96];
    snprintf(rp, sizeof rp, "openbook/logs/install-%s.json", ts);
    snprintf(lp, sizeof lp, "openbook/logs/install-%s.log", ts);
    jw_str(&w, "report", rp);
    jw_str(&w, "log", lp);
    if (plan.p) jw_raw(&w, "plan", plan.p);
    jw_endo(&w);
    if (verified_ok) report_write(&L, fd, w.b.p, ts);
    if (reporting) {
        report_to_stick(&src, w.b.p, ts);
        step(6, "done");
    }
    (void)step_state;
    sb_add(result, w.b.p, w.b.n);
    sb_free(&w.b);
    sb_free(&plan);
    if (fd >= 0) {
        fsync(fd);
        close(fd);
    }
    if (have_layout) layout_free(&L);
    source_close(&src);
    disks_free(d, n);
    free(v);
    progress(0, 1);
    return verified_ok ? 0 : -1;
}
