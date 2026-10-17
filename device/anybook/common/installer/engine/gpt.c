// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// GPT: read, write a new table, add entries to an existing one, wipe. Writes go backup first, then primary (and
// the protective MBR last for a new table), so a cut leaves at most one damaged copy (docs/installer.md S9).
#include "common.h"

#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

const char *const GUID_ESP = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b";
const char *const GUID_XBOOTLDR = "bc13c2ff-59e6-4262-a352-b275fd6f7172";
const char *const GUID_LINUX = "0fc63daf-8483-4772-8e79-3d69d8477de4";
const char *const GUID_MSDATA = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7";
const char *const GUID_MSRES = "e3c9e316-0b5c-4db8-817d-f92df00215ae";
const char *const GUID_MSRECOVERY = "de94bba4-06d1-4d40-a16a-bfd50179d6ac";
const char *const GUID_SWAP = "0657fd6d-a4ab-43c4-84e5-0933c84b4f4f";
const char *const GUID_LVM = "e6d6d379-f507-44c2-a23c-238f2a3df928";
const char *const GUID_LUKS = "ca7d7ccb-63ed-4c53-861c-1742536059cc";
const char *const GUID_APFS = "7c3457ef-0000-11aa-aa11-00306543ecac";
const char *const GUID_LINUX_ROOT_X64 = "4f68bce3-e8cd-4db1-96e7-fbcaf984b709";
const char *const GUID_LINUX_HOME = "933ac7e1-2eb4-4f13-b844-0e14e2aef915";

struct hdr {
    char sig[8];
    uint32_t revision, header_size, header_crc, reserved;
    uint64_t my_lba, alt_lba, first_usable, last_usable;
    uint8_t disk_guid[16];
    uint64_t entries_lba;
    uint32_t n_entries, entry_size, entries_crc;
} __attribute__((packed));

struct ent {
    uint8_t type[16], uniq[16];
    uint64_t first, last, attrs;
    uint16_t name[36];
} __attribute__((packed));

const char *gpt_type_kind(const uint8_t type[16]) {
    char s[37];
    guid_to_str(type, s);
    if (!strcmp(s, GUID_ESP)) return "esp";
    if (!strcmp(s, GUID_XBOOTLDR)) return "xbootldr";
    if (!strcmp(s, GUID_MSDATA)) return "msdata";
    if (!strcmp(s, GUID_MSRES)) return "msreserved";
    if (!strcmp(s, GUID_MSRECOVERY)) return "msrecovery";
    if (!strcmp(s, GUID_SWAP)) return "linux_swap";
    if (!strcmp(s, GUID_LVM)) return "linux_lvm";
    if (!strcmp(s, GUID_LUKS)) return "luks";
    if (!strcmp(s, GUID_APFS)) return "apple";
    if (!strcmp(s, GUID_LINUX) || !strcmp(s, GUID_LINUX_ROOT_X64) || !strcmp(s, GUID_LINUX_HOME)) return "linux";
    // systemd's discoverable partition types for other architectures and /usr, /var, /srv, verity...
    // all share no common prefix; anything else is "other".
    return "other";
}

static void name_from_utf16(const void *raw, char *out, size_t outlen) {
    uint16_t u[36];
    memcpy(u, raw, sizeof u);
    size_t o = 0;
    for (int i = 0; i < 36 && u[i] && o + 4 < outlen; i++) {
        unsigned c = u[i];
        if (c < 0x80) {
            out[o++] = c;
        } else if (c < 0x800) {
            out[o++] = 0xC0 | (c >> 6);
            out[o++] = 0x80 | (c & 0x3F);
        } else {
            out[o++] = 0xE0 | (c >> 12);
            out[o++] = 0x80 | ((c >> 6) & 0x3F);
            out[o++] = 0x80 | (c & 0x3F);
        }
    }
    out[o] = 0;
}

static void name_to_utf16(const char *s, void *raw) {
    uint16_t u[36] = {0};
    for (int i = 0; i < 36 && s[i]; i++) u[i] = (unsigned char)s[i];  // our names are ASCII
    memcpy(raw, u, sizeof u);
}

static int load_header(int fd, uint32_t sector, uint64_t lba, struct hdr *h, uint8_t **entries, char *why,
                       size_t wl) {
    uint8_t *sec = malloc(sector);
    if (!sec) return -1;
    if (pread_all(fd, sec, sector, lba * sector)) {
        snprintf(why, wl, "cannot read LBA %llu: %s", (unsigned long long)lba, strerror(errno));
        free(sec);
        return -1;
    }
    memcpy(h, sec, sizeof *h);
    free(sec);
    if (memcmp(h->sig, "EFI PART", 8)) {
        snprintf(why, wl, "no GPT header at LBA %llu", (unsigned long long)lba);
        return -1;
    }
    if (h->header_size < 92 || h->header_size > sector) {
        snprintf(why, wl, "GPT header size %u", h->header_size);
        return -1;
    }
    uint8_t raw[4096];
    pread_all(fd, raw, h->header_size, lba * sector);
    uint32_t want = h->header_crc;
    memset(raw + 16, 0, 4);
    if (crc32_buf(0, raw, h->header_size) != want) {
        snprintf(why, wl, "GPT header CRC mismatch at LBA %llu", (unsigned long long)lba);
        return -1;
    }
    if (h->my_lba != lba) {
        snprintf(why, wl, "GPT header at LBA %llu says it is at %llu", (unsigned long long)lba,
                 (unsigned long long)h->my_lba);
        return -1;
    }
    if (h->entry_size < 128 || h->entry_size % 8 || h->entry_size > 1024 || h->n_entries == 0 || h->n_entries > 1024) {
        snprintf(why, wl, "unexpected GPT entry array (%u x %u)", h->n_entries, h->entry_size);
        return -1;
    }
    size_t bytes = (size_t)h->n_entries * h->entry_size;
    uint8_t *e = calloc(1, bytes);
    if (!e || pread_all(fd, e, bytes, h->entries_lba * sector)) {
        snprintf(why, wl, "cannot read GPT entries");
        free(e);
        return -1;
    }
    if (crc32_buf(0, e, bytes) != h->entries_crc) {
        snprintf(why, wl, "GPT entries CRC mismatch");
        free(e);
        return -1;
    }
    *entries = e;
    return 0;
}

int gpt_read(int fd, uint32_t sector, uint64_t sectors, struct gpt *g) {
    memset(g, 0, sizeof *g);
    g->sector = sector;
    g->sectors = sectors;
    struct hdr h;
    uint8_t *e = NULL;
    if (sectors < 68) {
        snprintf(g->why, sizeof g->why, "disk too small for a GPT");
        return -1;
    }
    if (load_header(fd, sector, 1, &h, &e, g->why, sizeof g->why)) return -1;
    if (h.alt_lba >= sectors || h.last_usable >= sectors) {
        snprintf(g->why, sizeof g->why, "GPT is for a larger disk (backup at LBA %llu, disk has %llu sectors)",
                 (unsigned long long)h.alt_lba, (unsigned long long)sectors);
        free(e);
        return -1;
    }
    memcpy(g->disk_guid, h.disk_guid, 16);
    g->first_usable = h.first_usable;
    g->last_usable = h.last_usable;
    g->entries_lba = h.entries_lba;
    g->alt_lba = h.alt_lba;
    g->n_entries = h.n_entries;
    g->entry_size = h.entry_size;
    g->raw_entries = e;
    for (uint32_t i = 0; i < h.n_entries && g->nparts < GPT_MAX_PARTS; i++) {
        struct ent *x = (struct ent *)(e + (size_t)i * h.entry_size);
        static const uint8_t zero[16];
        if (!memcmp(x->type, zero, 16)) continue;
        struct gpt_part *p = &g->p[g->nparts++];
        p->index = i + 1;
        memcpy(p->type, x->type, 16);
        memcpy(p->uniq, x->uniq, 16);
        p->first = x->first;
        p->last = x->last;
        p->attrs = x->attrs;
        name_from_utf16(x->name, p->name, sizeof p->name);
    }
    g->valid = 1;
    return 0;
}

void gpt_free(struct gpt *g) {
    free(g->raw_entries);
    g->raw_entries = NULL;
}

const struct gpt_part *gpt_find(const struct gpt *g, const char *name) {
    for (int i = 0; i < g->nparts; i++)
        if (!strcmp(g->p[i].name, name)) return &g->p[i];
    return NULL;
}

const struct gpt_part *gpt_find_uuid(const struct gpt *g, const char *uuid) {
    for (int i = 0; i < g->nparts; i++) {
        char s[37];
        guid_to_str(g->p[i].uniq, s);
        if (!strcasecmp(s, uuid)) return &g->p[i];
    }
    return NULL;
}

static void finish(struct hdr *h, uint64_t my, uint64_t alt, uint64_t entries_lba) {
    h->my_lba = my;
    h->alt_lba = alt;
    h->entries_lba = entries_lba;
    h->header_crc = 0;
    h->header_crc = crc32_buf(0, h, 92);
}

static int write_header(int fd, uint32_t sector, const struct hdr *h) {
    uint8_t *sec = calloc(1, sector);
    if (!sec) return -1;
    memcpy(sec, h, 92);
    int rc = pwrite_all(fd, sec, sector, h->my_lba * sector);
    free(sec);
    return rc;
}

static int write_pmbr(int fd, uint32_t sector, uint64_t sectors) {
    uint8_t *mbr = calloc(1, sector);
    if (!mbr) return -1;
    uint8_t *pe = mbr + 446;
    pe[0] = 0x00;
    pe[1] = 0x00; pe[2] = 0x02; pe[3] = 0x00;  // CHS 0/0/2
    pe[4] = 0xEE;
    pe[5] = 0xFF; pe[6] = 0xFF; pe[7] = 0xFF;
    uint32_t start = 1, count = sectors - 1 > 0xFFFFFFFFull ? 0xFFFFFFFFu : (uint32_t)(sectors - 1);
    memcpy(pe + 8, &start, 4);
    memcpy(pe + 12, &count, 4);
    mbr[510] = 0x55;
    mbr[511] = 0xAA;
    int rc = pwrite_all(fd, mbr, sector, 0);
    free(mbr);
    return rc;
}

int gpt_write_new(int fd, uint32_t sector, uint64_t sectors, const uint8_t disk_guid[16], const struct gpt_part *parts,
                  int n) {
    const uint32_t N = 128, ES = 128;
    size_t bytes = N * ES;
    uint64_t esect = (bytes + sector - 1) / sector;
    uint8_t *e = calloc(1, esect * sector);
    if (!e) return -1;
    for (int i = 0; i < n; i++) {
        int slot = parts[i].index - 1;
        if (slot < 0 || slot >= (int)N) {
            free(e);
            errno = EINVAL;
            return -1;
        }
        struct ent *x = (struct ent *)(e + slot * ES);
        memcpy(x->type, parts[i].type, 16);
        memcpy(x->uniq, parts[i].uniq, 16);
        x->first = parts[i].first;
        x->last = parts[i].last;
        x->attrs = parts[i].attrs;
        name_to_utf16(parts[i].name, x->name);
    }
    struct hdr h = {0};
    memcpy(h.sig, "EFI PART", 8);
    h.revision = 0x00010000;
    h.header_size = 92;
    h.first_usable = 2 + esect;
    h.last_usable = sectors - 2 - esect;
    memcpy(h.disk_guid, disk_guid, 16);
    h.n_entries = N;
    h.entry_size = ES;
    h.entries_crc = crc32_buf(0, e, bytes);
    struct hdr primary = h, backup = h;
    finish(&backup, sectors - 1, 1, sectors - 1 - esect);
    finish(&primary, 1, sectors - 1, 2);
    int rc = pwrite_all(fd, e, esect * sector, backup.entries_lba * sector);
    if (!rc) rc = write_header(fd, sector, &backup);
    if (!rc) fsync(fd);
    if (!rc) rc = pwrite_all(fd, e, esect * sector, 2ull * sector);
    if (!rc) rc = write_header(fd, sector, &primary);
    if (!rc) rc = write_pmbr(fd, sector, sectors);
    free(e);
    return rc;
}

int gpt_write_add(int fd, const struct gpt *g, const struct gpt_part *add, int n) {
    size_t bytes = (size_t)g->n_entries * g->entry_size;
    uint64_t esect = (bytes + g->sector - 1) / g->sector;
    uint8_t *e = calloc(1, esect * g->sector);
    if (!e) return -1;
    memcpy(e, g->raw_entries, bytes);
    for (int i = 0; i < n; i++) {
        int slot = add[i].index - 1;
        struct ent *x = (struct ent *)(e + (size_t)slot * g->entry_size);
        static const uint8_t zero[16];
        if (slot < 0 || slot >= (int)g->n_entries || memcmp(x->type, zero, 16)) {
            free(e);
            errno = EEXIST;
            return -1;
        }
        memset(x, 0, g->entry_size);
        memcpy(x->type, add[i].type, 16);
        memcpy(x->uniq, add[i].uniq, 16);
        x->first = add[i].first;
        x->last = add[i].last;
        x->attrs = add[i].attrs;
        name_to_utf16(add[i].name, x->name);
    }
    // The primary header as it is on disk, with the new entries CRC.
    struct hdr h;
    if (pread_all(fd, &h, sizeof h, 1ull * g->sector)) {
        free(e);
        return -1;
    }
    h.entries_crc = crc32_buf(0, e, bytes);
    struct hdr primary = h, backup = h;
    // Backup entries: where the existing backup header says, if it is valid; else right before the backup header.
    uint64_t bentries = g->alt_lba - esect;
    struct hdr old;
    uint8_t *olde = NULL;
    char why[160];
    if (!load_header(fd, g->sector, g->alt_lba, &old, &olde, why, sizeof why)) {
        bentries = old.entries_lba;
        free(olde);
    }
    finish(&backup, g->alt_lba, 1, bentries);
    finish(&primary, 1, g->alt_lba, g->entries_lba);
    int rc = pwrite_all(fd, e, esect * g->sector, bentries * g->sector);
    if (!rc) rc = write_header(fd, g->sector, &backup);
    if (!rc) fsync(fd);
    if (!rc) rc = pwrite_all(fd, e, esect * g->sector, g->entries_lba * g->sector);
    if (!rc) rc = write_header(fd, g->sector, &primary);
    free(e);
    return rc;
}

int gpt_wipe(int fd, uint32_t sector, uint64_t sectors) {
    uint64_t size = sectors * sector;
    // The first and last MiB: protective MBR, both GPT copies (also on 4Kn disks) and old boot code.
    if (zero_range(fd, 0, size < MiB ? size : MiB)) return -1;
    if (size > 2 * MiB && zero_range(fd, size - MiB, MiB)) return -1;
    return 0;
}
