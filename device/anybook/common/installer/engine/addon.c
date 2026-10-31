// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Optional app add-ons the installer can carry to the new disk (ANAL-210, docs/gapps.md section 6). The image
// catalogues each add-on in /system_ext/etc/openbook/addons/<name>.json (device/anybook/common/addons/): its APKs,
// each with the sha256 and size the image pins. A stick carries an add-on's files in openbook/addons/<name>/ on its
// EFI partition (scripts/microg/add-to-image.sh). When the user ticks it, the plan copies exactly the catalogued APKs
// to the same place on the new boot partition; check_source verifies them against the pins first, and the read-back
// verifies them again. openbook-addons installs them on the new system's first start. Nothing is added to a plan
// that does not ask for an add-on.
#include "common.h"

#include <dirent.h>
#include <stdlib.h>
#include <string.h>

static int valid(const char *s, const char *extra) {
    if (!s || !*s || strlen(s) > 100 || s[0] == '.') return 0;
    for (const char *p = s; *p; p++)
        if (!(*p >= 'a' && *p <= 'z') && !(*p >= 'A' && *p <= 'Z') && !(*p >= '0' && *p <= '9') && !strchr(extra, *p))
            return 0;
    return 1;
}

static int valid_sha(const char *s) {
    if (!s || strlen(s) != 64) return 0;
    for (const char *p = s; *p; p++)
        if (!((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'f'))) return 0;
    return 1;
}

struct jv *addon_catalog(const char *name, char *why, size_t wl) {
    if (!valid(name, "_-")) {
        snprintf(why, wl, "no add-on called \"%s\"", name ? name : "");
        return NULL;
    }
    char path[512], err[160];
    env_path(path, sizeof path, "/system_ext/etc/openbook/addons/%s.json", name);
    char *t = read_file(path, NULL);
    struct jv *c = t ? json_parse(t, err, sizeof err) : NULL;
    free(t);
    struct jv *files = jget(c, "files");
    int ok = c && jstr(c, "schema") && !strcmp(jstr(c, "schema"), "openbook-addon/1") && jstr(c, "name") &&
             !strcmp(jstr(c, "name"), name) && files && files->t == J_ARR && files->len >= 1 &&
             files->len <= ADDON_MAX_FILES;
    for (int i = 0; ok && i < files->len; i++) {
        struct jv *f = files->items[i];
        const char *fn = jstr(f, "file");
        size_t l = fn ? strlen(fn) : 0;
        ok = valid(fn, "._-") && l > 4 && !strcmp(fn + l - 4, ".apk") && valid_sha(jstr(f, "sha256")) &&
             jnum(f, "bytes", 0) > 0 && jnum(f, "bytes", 0) < 4e9;
    }
    if (!ok) {
        snprintf(why, wl, "this image has no valid catalogue for the add-on \"%s\" (%s)", name, path);
        json_free(c);
        return NULL;
    }
    return c;
}

struct listing {
    char names[64][128];
    uint32_t sizes[64];
    int n;
};

static void list_cb(const char *name, int is_dir, uint32_t size, void *arg) {
    struct listing *l = arg;
    if (is_dir || l->n >= 64) return;
    snprintf(l->names[l->n], sizeof l->names[l->n], "%s", name);
    l->sizes[l->n++] = size;
}

int addon_on_stick(struct source *s, const struct jv *cat, char *why, size_t wl) {
    const char *name = jstr(cat, "name");
    if (!s->disk || s->fd < 0 || !s->esp) {
        snprintf(why, wl, "not started from an OpenBook stick");
        return 0;
    }
    struct fat f;
    uint64_t off = s->esp->first * s->disk->sector, size = (s->esp->last - s->esp->first + 1) * s->disk->sector;
    if (fat_open(&f, s->fd, off, size)) {
        snprintf(why, wl, "the stick's EFI partition is not a FAT filesystem");
        return 0;
    }
    char dir[160];
    snprintf(dir, sizeof dir, "openbook/addons/%s", name);
    struct listing *l = calloc(1, sizeof *l);
    int found = l && fat_list(&f, dir, list_cb, l) == 0;
    free(f.fatbuf);  // read only: nothing to flush
    struct jv *files = jget(cat, "files");
    int ok = found;
    if (!found) snprintf(why, wl, "the stick does not carry the add-on (%s/)", dir);
    for (int i = 0; ok && i < files->len; i++) {
        const char *fn = jstr(files->items[i], "file");
        uint32_t want = (uint32_t)jnum(files->items[i], "bytes", 0);
        int hit = 0;
        for (int k = 0; k < l->n; k++)
            if (!strcasecmp(l->names[k], fn)) hit = l->sizes[k] == want ? 1 : -1;
        if (hit != 1) {
            snprintf(why, wl, hit ? "%s/%s on the stick is not the size this image expects (%u bytes)"
                                  : "%s/%s is missing on the stick", dir, fn, want);
            ok = 0;
        }
    }
    free(l);
    return ok;
}

uint64_t addon_bytes(const struct jv *cat) {
    uint64_t b = 0;
    struct jv *files = jget(cat, "files");
    for (int i = 0; files && i < files->len; i++) b += (uint64_t)jnum(files->items[i], "bytes", 0);
    return b;
}

void addons_json(struct jw *w, const char *key, struct source *s) {
    char dir[512];
    env_path(dir, sizeof dir, "/system_ext/etc/openbook/addons");
    DIR *d = opendir(dir);
    char *names[32];
    int n = 0;
    struct dirent *e;
    while (d && (e = readdir(d)) && n < 32) {
        size_t l = strlen(e->d_name);
        if (l > 5 && !strcmp(e->d_name + l - 5, ".json")) names[n++] = strndup(e->d_name, l - 5);
    }
    if (d) closedir(d);
    for (int i = 1; i < n; i++)  // sorted, so the list is stable
        for (int k = i; k > 0 && strcmp(names[k - 1], names[k]) > 0; k--) {
            char *t = names[k];
            names[k] = names[k - 1];
            names[k - 1] = t;
        }
    jw_arr(w, key);
    for (int i = 0; i < n; i++) {
        char why[300] = "";
        struct jv *c = addon_catalog(names[i], why, sizeof why);
        jw_obj(w, NULL);
        jw_str(w, "name", names[i]);
        if (c) {
            int ok = addon_on_stick(s, c, why, sizeof why);
            jw_str(w, "title", jstr(c, "title"));
            jw_str(w, "version", jstr(c, "version"));
            jw_u64(w, "bytes", addon_bytes(c));
            jw_bool(w, "on_stick", ok);
            jw_str(w, "why", ok ? NULL : why);
        } else {
            jw_bool(w, "on_stick", 0);
            jw_str(w, "why", why);
        }
        jw_endo(w);
        json_free(c);
        free(names[i]);
    }
    jw_enda(w);
}
