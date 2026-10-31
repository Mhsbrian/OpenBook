// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// The install source: the OpenBook stick this session booted from (the disk holding the ESP whose PARTUUID is
// androidboot.boot_part_uuid). Its ESP carries openbook/MANIFEST.json (scripts/installer/mklive.py): the hashes of
// the stick's partitions and, since ANAL-191, an "install" section with everything a target disk needs (layout,
// super metadata for the installed size, loader files, bootconfig).
#include "common.h"

#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int source_open(struct source *s, struct disk *d, int n) {
    memset(s, 0, sizeof *s);
    s->fd = -1;
    for (int i = 0; i < n; i++)
        if (d[i].boot_disk) s->disk = &d[i];
    if (!s->disk) {
        snprintf(s->why, sizeof s->why, E.boot_part_uuid[0] ? "the boot disk (PARTUUID %s) was not found"
                                                            : "not started from an OpenBook stick (no boot_part_uuid)",
                 E.boot_part_uuid);
        return -1;
    }
    s->fd = disk_open(s->disk, 0);
    if (s->fd < 0) {
        snprintf(s->why, sizeof s->why, "cannot open the stick %s: %s", s->disk->dev, strerror(errno));
        return -1;
    }
    s->esp = gpt_find_uuid(&s->disk->gpt, E.boot_part_uuid);
    struct fat f;
    uint64_t off = s->esp->first * s->disk->sector, size = (s->esp->last - s->esp->first + 1) * s->disk->sector;
    if (fat_open(&f, s->fd, off, size)) {
        snprintf(s->why, sizeof s->why, "the stick's EFI partition is not a FAT filesystem");
        return -1;
    }
    uint32_t len;
    uint8_t *m = fat_read(&f, "openbook/MANIFEST.json", &len);
    fat_close(&f);
    if (!m) {
        snprintf(s->why, sizeof s->why, "openbook/MANIFEST.json is missing on the stick");
        return -1;
    }
    char *txt = malloc(len + 1);
    memcpy(txt, m, len);
    txt[len] = 0;
    free(m);
    sha256_hex(txt, len, s->manifest_text_sha256);
    char err[160];
    s->manifest = json_parse(txt, err, sizeof err);
    free(txt);
    if (!s->manifest) {
        snprintf(s->why, sizeof s->why, "MANIFEST.json: %s", err);
        return -1;
    }
    snprintf(s->label, sizeof s->label, "%s", jstr(s->manifest, "label") ? jstr(s->manifest, "label") : "");
    snprintf(s->fingerprint, sizeof s->fingerprint, "%s",
             jstr(s->manifest, "fingerprint") ? jstr(s->manifest, "fingerprint") : "");
    s->install = jget(s->manifest, "install");
    if (!s->install || !jstr(s->install, "schema") || strcmp(jstr(s->install, "schema"), "openbook-install-source/1")) {
        snprintf(s->why, sizeof s->why, "this stick (%s) carries no install data: it was built before the installer",
                 s->label);
        return -1;
    }
    // Every source partition the manifest names must be on the stick.
    struct jv *parts = jget(s->manifest, "partitions");
    if (!parts || parts->t != J_OBJ) {
        snprintf(s->why, sizeof s->why, "MANIFEST.json has no partition hashes");
        return -1;
    }
    for (int i = 0; i < parts->len; i++) {
        const struct gpt_part *p = gpt_find(&s->disk->gpt, parts->keys[i]);
        uint64_t want = (uint64_t)jnum(parts->items[i], "bytes", 0);
        if (!p || (p->last - p->first + 1) * s->disk->sector < want) {
            snprintf(s->why, sizeof s->why, "the stick has no partition %s of %llu bytes", parts->keys[i],
                     (unsigned long long)want);
            return -1;
        }
    }
    s->ok = 1;
    return 0;
}

void source_close(struct source *s) {
    if (s->fd >= 0) close(s->fd);
    json_free(s->manifest);
    memset(s, 0, sizeof *s);
    s->fd = -1;
}
