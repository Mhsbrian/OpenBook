// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// FAT12/16/32 on a byte range of a file descriptor (a partition of a whole disk, or an image file), without a
// kernel mount: format a new FAT32 volume, look up and read files, create directories and write files (long file
// names included). Used for the new ESP or XBOOTLDR partition, for adding EFI/OpenBook/ to an existing ESP when
// installing alongside, and for reading the stick's ESP (MANIFEST.json, kernel, ramdisks, systemd-boot) and writing
// its logs. The installer never needs mount permissions this way, and the same code runs in the host tests, where
// fsck.fat and mtools check its output.
#include "common.h"

#include <ctype.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static uint16_t rd16(const uint8_t *p) { return p[0] | p[1] << 8; }
static uint32_t rd32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
static void wr16(uint8_t *p, uint16_t v) {
    p[0] = v;
    p[1] = v >> 8;
}
static void wr32(uint8_t *p, uint32_t v) {
    p[0] = v;
    p[1] = v >> 8;
    p[2] = v >> 16;
    p[3] = v >> 24;
}

// ------------------------------------------------------------------ format
int fat_format32(int fd, uint64_t off, uint64_t size, uint32_t bps, const char *label, uint32_t volid) {
    uint32_t total = size / bps, reserved = 32, nfats = 2, spc = 0, fatsz = 0, clusters = 0;
    // 4 KiB clusters if the volume is large enough for FAT32 with them (512 MiB: yes), else smaller ones.
    for (uint32_t s = 4096 / bps ? 4096 / bps : 1; s >= 1; s /= 2) {
        // The smallest FAT that holds 4 bytes for every cluster left after it.
        uint64_t fz;
        for (fz = 1;; fz++) {
            uint64_t data = total - reserved - nfats * fz;
            uint64_t cl = data / s;
            if ((cl + 2) * 4 <= fz * bps) break;
        }
        uint32_t cl = (total - reserved - nfats * fz) / s;
        if (cl >= 65525 && cl < 0x0FFFFFF5) {
            spc = s;
            fatsz = fz;
            clusters = cl;
            break;
        }
        if (s == 1) break;
    }
    if (!spc) {
        errno = EINVAL;
        return -1;  // too small (or too large) for FAT32
    }
    uint8_t *bs = calloc(1, bps);
    uint8_t *fsinfo = calloc(1, bps);
    if (!bs || !fsinfo) return -1;
    bs[0] = 0xEB;
    bs[1] = 0x58;
    bs[2] = 0x90;
    memcpy(bs + 3, "MSWIN4.1", 8);
    wr16(bs + 11, bps);
    bs[13] = spc;
    wr16(bs + 14, reserved);
    bs[16] = nfats;
    wr16(bs + 17, 0);
    wr16(bs + 19, 0);
    bs[21] = 0xF8;
    wr16(bs + 22, 0);
    wr16(bs + 24, 63);
    wr16(bs + 26, 255);
    wr32(bs + 28, (uint32_t)(off / bps));
    wr32(bs + 32, total);
    wr32(bs + 36, fatsz);
    wr16(bs + 40, 0);
    wr16(bs + 42, 0);
    wr32(bs + 44, 2);
    wr16(bs + 48, 1);
    wr16(bs + 50, 6);
    bs[64] = 0x80;
    bs[66] = 0x29;
    wr32(bs + 67, volid);
    char lab[11];
    memset(lab, ' ', 11);
    for (int i = 0; i < 11 && label && label[i]; i++) lab[i] = toupper((unsigned char)label[i]);
    memcpy(bs + 71, lab, 11);
    memcpy(bs + 82, "FAT32   ", 8);
    bs[510] = 0x55;
    bs[511] = 0xAA;
    wr32(fsinfo, 0x41615252);
    wr32(fsinfo + 484, 0x61417272);
    wr32(fsinfo + 488, clusters - 1);  // all free but the root directory's cluster
    wr32(fsinfo + 492, 3);
    wr32(fsinfo + 508, 0xAA550000);
    int rc = zero_range(fd, off, ((uint64_t)reserved + (uint64_t)nfats * fatsz + spc) * bps);
    if (!rc) rc = pwrite_all(fd, bs, bps, off);
    if (!rc) rc = pwrite_all(fd, fsinfo, bps, off + bps);
    if (!rc) rc = pwrite_all(fd, bs, bps, off + 6ull * bps);
    if (!rc) rc = pwrite_all(fd, fsinfo, bps, off + 7ull * bps);
    uint8_t fat0[12];
    wr32(fat0, 0x0FFFFFF8);
    wr32(fat0 + 4, 0x0FFFFFFF);
    wr32(fat0 + 8, 0x0FFFFFFF);
    for (uint32_t i = 0; !rc && i < nfats; i++)
        rc = pwrite_all(fd, fat0, sizeof fat0, off + ((uint64_t)reserved + (uint64_t)i * fatsz) * bps);
    // The volume label as the first root directory entry.
    if (!rc && label && *label) {
        uint8_t e[32] = {0};
        memcpy(e, lab, 11);
        e[11] = 0x08;
        rc = pwrite_all(fd, e, 32, off + ((uint64_t)reserved + (uint64_t)nfats * fatsz) * bps);
    }
    free(bs);
    free(fsinfo);
    return rc;
}

// ------------------------------------------------------------------ open
int fat_probe(int fd, uint64_t off, uint64_t size, char *label, size_t labellen) {
    uint8_t bs[512];
    if (label && labellen) label[0] = 0;
    if (size < 512 * 16 || pread_all(fd, bs, 512, off)) return 0;
    if (bs[510] != 0x55 || bs[511] != 0xAA) return 0;
    uint32_t bps = rd16(bs + 11), spc = bs[13], res = rd16(bs + 14), nf = bs[16];
    if (bps < 512 || bps > 4096 || (bps & (bps - 1)) || !spc || (spc & (spc - 1)) || !res || nf < 1 || nf > 2)
        return 0;
    uint32_t root_entries = rd16(bs + 17), fatsz = rd16(bs + 22) ? rd16(bs + 22) : rd32(bs + 36);
    uint32_t total = rd16(bs + 19) ? rd16(bs + 19) : rd32(bs + 32);
    if (!fatsz || !total) return 0;
    uint32_t rds = (root_entries * 32 + bps - 1) / bps;
    if (total <= res + nf * fatsz + rds) return 0;
    uint32_t cl = (total - res - nf * fatsz - rds) / spc;
    int type = cl < 4085 ? 12 : cl < 65525 ? 16 : 32;
    if (label && labellen) {
        const uint8_t *l = type == 32 ? bs + 71 : bs + 43;
        int sig = type == 32 ? bs[66] : bs[38];
        if (sig == 0x29) {
            char t[12];
            memcpy(t, l, 11);
            t[11] = 0;
            trim(t);
            if (strcmp(t, "NO NAME")) snprintf(label, labellen, "%s", t);
        }
    }
    return type;
}

int fat_open(struct fat *f, int fd, uint64_t off, uint64_t size) {
    memset(f, 0, sizeof *f);
    uint8_t bs[512];
    f->fd = fd;
    f->off = off;
    f->size = size;
    f->type = fat_probe(fd, off, size, f->label, sizeof f->label);
    if (!f->type) {
        errno = EINVAL;
        return -1;
    }
    pread_all(fd, bs, 512, off);
    f->bps = rd16(bs + 11);
    f->spc = bs[13];
    f->cluster_bytes = f->bps * f->spc;
    f->reserved = rd16(bs + 14);
    f->nfats = bs[16];
    f->root_entries = rd16(bs + 17);
    f->fat_sectors = rd16(bs + 22) ? rd16(bs + 22) : rd32(bs + 36);
    f->total_sectors = rd16(bs + 19) ? rd16(bs + 19) : rd32(bs + 32);
    f->root_dir_sectors = (f->root_entries * 32 + f->bps - 1) / f->bps;
    f->first_data_sector = f->reserved + f->nfats * f->fat_sectors + f->root_dir_sectors;
    f->nclusters = (f->total_sectors - f->first_data_sector) / f->spc;
    if ((uint64_t)f->total_sectors * f->bps > size) {
        errno = EINVAL;
        return -1;
    }
    if (f->type == 32) {
        f->root_cluster = rd32(bs + 44);
        f->fsinfo_sector = rd16(bs + 48);
        uint16_t flags = rd16(bs + 40);
        if (flags & 0x80) {  // FAT mirroring off: read the active FAT
            uint32_t active = flags & 0x0F;
            f->reserved += 0;  // reads below use the active copy
            (void)active;
        }
    }
    size_t fb = (size_t)f->fat_sectors * f->bps;
    f->fatbuf = malloc(fb);
    if (!f->fatbuf || pread_all(fd, f->fatbuf, fb, off + (uint64_t)f->reserved * f->bps)) {
        free(f->fatbuf);
        f->fatbuf = NULL;
        return -1;
    }
    f->hint = 2;
    return 0;
}

static uint32_t fat_get(struct fat *f, uint32_t c) {
    if (f->type == 32) return rd32(f->fatbuf + 4 * c) & 0x0FFFFFFF;
    if (f->type == 16) return rd16(f->fatbuf + 2 * c);
    uint32_t o = c + c / 2;
    uint16_t v = rd16(f->fatbuf + o);
    return c & 1 ? v >> 4 : v & 0xFFF;
}

static void fat_set(struct fat *f, uint32_t c, uint32_t v) {
    f->dirty = 1;
    if (f->type == 32) {
        uint32_t old = rd32(f->fatbuf + 4 * c);
        wr32(f->fatbuf + 4 * c, (old & 0xF0000000) | (v & 0x0FFFFFFF));
    } else if (f->type == 16) {
        wr16(f->fatbuf + 2 * c, v);
    } else {
        uint32_t o = c + c / 2;
        uint16_t cur = rd16(f->fatbuf + o);
        cur = c & 1 ? (cur & 0x000F) | (v << 4) : (cur & 0xF000) | (v & 0xFFF);
        wr16(f->fatbuf + o, cur);
    }
}

static int is_eoc(struct fat *f, uint32_t v) {
    return f->type == 32 ? v >= 0x0FFFFFF8 : f->type == 16 ? v >= 0xFFF8 : v >= 0xFF8;
}

static uint32_t eoc(struct fat *f) { return f->type == 32 ? 0x0FFFFFFF : f->type == 16 ? 0xFFFF : 0xFFF; }

static uint64_t cl_off(struct fat *f, uint32_t c) {
    return f->off + ((uint64_t)f->first_data_sector + (uint64_t)(c - 2) * f->spc) * f->bps;
}

static int valid_cl(struct fat *f, uint32_t c) { return c >= 2 && c < f->nclusters + 2; }

int fat_flush(struct fat *f) {
    if (!f->dirty) return 0;
    size_t fb = (size_t)f->fat_sectors * f->bps;
    for (uint32_t i = 0; i < f->nfats; i++)
        if (pwrite_all(f->fd, f->fatbuf, fb, f->off + ((uint64_t)f->reserved + (uint64_t)i * f->fat_sectors) * f->bps))
            return -1;
    if (f->type == 32 && f->fsinfo_sector) {
        uint8_t fi[512];
        uint64_t at = f->off + (uint64_t)f->fsinfo_sector * f->bps;
        if (!pread_all(f->fd, fi, 512, at) && rd32(fi) == 0x41615252 && rd32(fi + 484) == 0x61417272) {
            uint32_t freec = 0;
            for (uint32_t c = 2; c < f->nclusters + 2; c++) freec += fat_get(f, c) == 0;
            wr32(fi + 488, freec);
            wr32(fi + 492, f->hint);
            if (pwrite_all(f->fd, fi, 512, at)) return -1;
        }
    }
    f->dirty = 0;
    return 0;
}

void fat_close(struct fat *f) {
    if (f->fatbuf) fat_flush(f);
    free(f->fatbuf);
    f->fatbuf = NULL;
}

// ------------------------------------------------------------------ directories
struct dirbuf {
    uint8_t *data;
    uint32_t len;
    uint32_t first;  // 0: the fixed FAT12/16 root directory
    uint32_t *cl;
    int ncl;
};

static void dir_free(struct dirbuf *d) {
    free(d->data);
    free(d->cl);
    memset(d, 0, sizeof *d);
}

static int dir_load(struct fat *f, uint32_t first, struct dirbuf *d) {
    memset(d, 0, sizeof *d);
    d->first = first;
    if (first == 0 && f->type != 32) {
        d->len = f->root_dir_sectors * f->bps;
        d->data = malloc(d->len);
        if (!d->data) return -1;
        return pread_all(f->fd, d->data, d->len,
                         f->off + ((uint64_t)f->reserved + (uint64_t)f->nfats * f->fat_sectors) * f->bps);
    }
    if (first == 0) first = d->first = f->root_cluster;
    for (uint32_t c = first; valid_cl(f, c); c = fat_get(f, c)) {
        if (d->ncl > 65536) return -1;  // a loop
        d->cl = realloc(d->cl, (d->ncl + 1) * sizeof *d->cl);
        d->data = realloc(d->data, d->len + f->cluster_bytes);
        if (!d->cl || !d->data) return -1;
        d->cl[d->ncl++] = c;
        if (pread_all(f->fd, d->data + d->len, f->cluster_bytes, cl_off(f, c))) return -1;
        d->len += f->cluster_bytes;
        uint32_t n = fat_get(f, c);
        if (is_eoc(f, n)) break;
    }
    return d->ncl ? 0 : -1;
}

static int dir_store(struct fat *f, struct dirbuf *d) {
    if (d->first == 0 && f->type != 32)
        return pwrite_all(f->fd, d->data, d->len,
                          f->off + ((uint64_t)f->reserved + (uint64_t)f->nfats * f->fat_sectors) * f->bps);
    for (int i = 0; i < d->ncl; i++)
        if (pwrite_all(f->fd, d->data + (size_t)i * f->cluster_bytes, f->cluster_bytes, cl_off(f, d->cl[i])))
            return -1;
    return 0;
}

static uint32_t alloc_one(struct fat *f) {
    for (uint32_t k = 0; k < f->nclusters; k++) {
        uint32_t c = 2 + (f->hint - 2 + k) % f->nclusters;
        if (fat_get(f, c) == 0) {
            f->hint = c + 1 < f->nclusters + 2 ? c + 1 : 2;
            return c;
        }
    }
    return 0;
}

static int dir_extend(struct fat *f, struct dirbuf *d) {
    if (d->first == 0 && f->type != 32) {
        errno = ENOSPC;  // the fixed root directory is full
        return -1;
    }
    uint32_t c = alloc_one(f);
    if (!c) {
        errno = ENOSPC;
        return -1;
    }
    fat_set(f, c, eoc(f));
    fat_set(f, d->cl[d->ncl - 1], c);
    d->cl = realloc(d->cl, (d->ncl + 1) * sizeof *d->cl);
    d->data = realloc(d->data, d->len + f->cluster_bytes);
    if (!d->cl || !d->data) return -1;
    d->cl[d->ncl++] = c;
    memset(d->data + d->len, 0, f->cluster_bytes);
    d->len += f->cluster_bytes;
    return 0;
}

struct dent {
    char name[256];
    uint32_t pos;     // offset of the short entry in the dirbuf
    uint32_t lfn_pos; // offset of the first LFN entry (== pos without LFN)
    uint32_t first;   // first cluster
    uint32_t size;
    uint8_t attr;
    char short_name[12];  // 11 raw bytes
};

static uint8_t lfn_sum(const uint8_t *s11) {
    uint8_t sum = 0;
    for (int i = 0; i < 11; i++) sum = ((sum & 1) << 7) + (sum >> 1) + s11[i];
    return sum;
}

// Iterate entries; cb returns nonzero to stop.
static int dir_iter(struct dirbuf *d, int (*cb)(struct dent *e, void *arg), void *arg) {
    uint16_t lfn[260];
    int lfn_ok = 0, lfn_n = 0;
    uint8_t lfn_ck = 0;
    uint32_t lfn_start = 0;
    for (uint32_t pos = 0; pos + 32 <= d->len; pos += 32) {
        uint8_t *e = d->data + pos;
        if (e[0] == 0x00) break;
        if (e[0] == 0xE5) {
            lfn_ok = 0;
            continue;
        }
        if (e[11] == 0x0F) {
            int seq = e[0] & 0x1F;
            if (e[0] & 0x40) {
                memset(lfn, 0, sizeof lfn);
                lfn_n = seq;
                lfn_ok = 1;
                lfn_ck = e[13];
                lfn_start = pos;
            }
            if (!lfn_ok || seq < 1 || seq > 20 || e[13] != lfn_ck) {
                lfn_ok = 0;
                continue;
            }
            static const int offs[13] = {1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30};
            for (int k = 0; k < 13; k++) lfn[(seq - 1) * 13 + k] = rd16(e + offs[k]);
            continue;
        }
        struct dent de = {0};
        de.pos = pos;
        de.attr = e[11];
        de.first = rd16(e + 26) | (uint32_t)rd16(e + 20) << 16;
        de.size = rd32(e + 28);
        memcpy(de.short_name, e, 11);
        if (lfn_ok && lfn_ck == lfn_sum(e)) {
            size_t o = 0;
            for (int k = 0; k < lfn_n * 13 && lfn[k] && lfn[k] != 0xFFFF && o + 4 < sizeof de.name; k++) {
                unsigned c = lfn[k];
                if (c < 0x80) de.name[o++] = c;
                else if (c < 0x800) {
                    de.name[o++] = 0xC0 | (c >> 6);
                    de.name[o++] = 0x80 | (c & 0x3F);
                } else {
                    de.name[o++] = 0xE0 | (c >> 12);
                    de.name[o++] = 0x80 | ((c >> 6) & 0x3F);
                    de.name[o++] = 0x80 | (c & 0x3F);
                }
            }
            de.name[o] = 0;
            de.lfn_pos = lfn_start;
        } else {
            char base[9], ext[4];
            memcpy(base, e, 8);
            base[8] = 0;
            memcpy(ext, e + 8, 3);
            ext[3] = 0;
            if ((uint8_t)base[0] == 0x05) base[0] = (char)0xE5;
            trim(base);
            trim(ext);
            if (e[12] & 0x08)
                for (char *p = base; *p; p++) *p = tolower((unsigned char)*p);
            if (e[12] & 0x10)
                for (char *p = ext; *p; p++) *p = tolower((unsigned char)*p);
            snprintf(de.name, sizeof de.name, "%s%s%s", base, ext[0] ? "." : "", ext);
            de.lfn_pos = pos;
        }
        lfn_ok = 0;
        if ((de.attr & 0x08) && !(de.attr & 0x10)) continue;  // volume label
        if (cb(&de, arg)) return 1;
    }
    return 0;
}

struct find_arg {
    const char *name;
    struct dent found;
    int hit;
};

static int find_cb(struct dent *e, void *arg) {
    struct find_arg *a = arg;
    if (!strcasecmp(e->name, a->name)) {
        a->found = *e;
        a->hit = 1;
        return 1;
    }
    return 0;
}

// Walk path; on success *dir is the containing directory's first cluster (0 = root) and *e the entry. For the root
// itself (path "" or "/") returns 1 with e->attr = 0x10, first = 0.
static int lookup(struct fat *f, const char *path, uint32_t *dir, struct dent *e) {
    char buf[512];
    snprintf(buf, sizeof buf, "%s", path);
    uint32_t cur = 0;
    struct dent ent = {.attr = 0x10, .first = 0};
    char *save = NULL;
    *dir = 0;
    for (char *tok = strtok_r(buf, "/", &save); tok; tok = strtok_r(NULL, "/", &save)) {
        if (!(ent.attr & 0x10)) return 0;
        struct dirbuf d;
        if (dir_load(f, cur, &d)) {
            dir_free(&d);
            return -1;
        }
        struct find_arg a = {.name = tok};
        dir_iter(&d, find_cb, &a);
        dir_free(&d);
        if (!a.hit) return 0;
        *dir = cur;
        ent = a.found;
        cur = ent.first;
    }
    *e = ent;
    return 1;
}

int fat_exists(struct fat *f, const char *path, int *is_dir) {
    uint32_t dir;
    struct dent e;
    int r = lookup(f, path, &dir, &e);
    if (r == 1 && is_dir) *is_dir = !!(e.attr & 0x10);
    return r == 1;
}

uint8_t *fat_read(struct fat *f, const char *path, uint32_t *len) {
    uint32_t dir;
    struct dent e;
    if (lookup(f, path, &dir, &e) != 1 || (e.attr & 0x10)) return NULL;
    uint8_t *buf = malloc(e.size ? e.size : 1);
    if (!buf) return NULL;
    uint32_t done = 0, c = e.first;
    while (done < e.size) {
        if (!valid_cl(f, c)) {
            free(buf);
            errno = EIO;
            return NULL;
        }
        // Read a run of consecutive clusters at once.
        uint32_t run = 1;
        while (done + run * f->cluster_bytes < e.size && fat_get(f, c + run - 1) == c + run) run++;
        uint32_t want = e.size - done < run * f->cluster_bytes ? e.size - done : run * f->cluster_bytes;
        if (pread_all(f->fd, buf + done, want, cl_off(f, c))) {
            free(buf);
            return NULL;
        }
        done += want;
        uint32_t last = c + run - 1;
        c = fat_get(f, last);
        if (done < e.size && is_eoc(f, c)) {
            free(buf);
            errno = EIO;
            return NULL;
        }
    }
    if (len) *len = e.size;
    return buf;
}

struct list_arg {
    void (*cb)(const char *, int, uint32_t, void *);
    void *arg;
};

static int list_cb(struct dent *e, void *arg) {
    struct list_arg *a = arg;
    if (!strcmp(e->name, ".") || !strcmp(e->name, "..")) return 0;
    a->cb(e->name, !!(e->attr & 0x10), e->size, a->arg);
    return 0;
}

int fat_list(struct fat *f, const char *dirpath, void (*cb)(const char *, int, uint32_t, void *), void *arg) {
    uint32_t dir;
    struct dent e;
    if (lookup(f, dirpath, &dir, &e) != 1 || !(e.attr & 0x10)) return -1;
    struct dirbuf d;
    if (dir_load(f, e.first, &d)) {
        dir_free(&d);
        return -1;
    }
    struct list_arg a = {cb, arg};
    dir_iter(&d, list_cb, &a);
    dir_free(&d);
    return 0;
}

// ------------------------------------------------------------------ creating entries
static void dos_time(uint8_t *t2, uint8_t *d2) {
    time_t now = time(NULL);
    struct tm tm;
    gmtime_r(&now, &tm);
    wr16(t2, tm.tm_hour << 11 | tm.tm_min << 5 | tm.tm_sec / 2);
    wr16(d2, (tm.tm_year + 1900 - 1980) << 9 | (tm.tm_mon + 1) << 5 | tm.tm_mday);
}

static int short_char_ok(unsigned char c) {
    if (c >= 'A' && c <= 'Z') return 1;
    if (c >= '0' && c <= '9') return 1;
    if (c >= 128) return 0;
    return strchr("!#$%&'()-@^_`{}~", c) != NULL;
}

// Fill raw[11] and the NT case byte if name is a clean 8.3 name; return 1 if so (no LFN needed).
static int clean_83(const char *name, uint8_t raw[11], uint8_t *ntcase) {
    const char *dot = strrchr(name, '.');
    size_t bl = dot ? (size_t)(dot - name) : strlen(name), el = dot ? strlen(dot + 1) : 0;
    if (!bl || bl > 8 || el > 3 || (dot && !el) || strchr(name, '.') != dot) return 0;
    int bup = 0, blo = 0, eup = 0, elo = 0;
    memset(raw, ' ', 11);
    for (size_t i = 0; i < bl; i++) {
        unsigned char c = name[i];
        if (islower(c)) blo = 1;
        if (isupper(c)) bup = 1;
        if (!short_char_ok(toupper(c))) return 0;
        raw[i] = toupper(c);
    }
    for (size_t i = 0; i < el; i++) {
        unsigned char c = dot[1 + i];
        if (islower(c)) elo = 1;
        if (isupper(c)) eup = 1;
        if (!short_char_ok(toupper(c))) return 0;
        raw[8 + i] = toupper(c);
    }
    if ((bup && blo) || (eup && elo)) return 0;
    *ntcase = (blo ? 0x08 : 0) | (elo ? 0x10 : 0);
    if (raw[0] == 0xE5) raw[0] = 0x05;
    return 1;
}

struct short_arg {
    const uint8_t *raw;
    int clash;
};

static int short_cb(struct dent *e, void *arg) {
    struct short_arg *a = arg;
    if (!memcmp(e->short_name, a->raw, 11)) a->clash = 1;
    return a->clash;
}

static void make_short(struct dirbuf *d, const char *name, uint8_t raw[11]) {
    char base[16] = {0}, ext[4] = {0};
    const char *dot = strrchr(name, '.');
    int bi = 0, ei = 0;
    for (const char *p = name; *p && (!dot || p < dot) && bi < 6; p++) {
        unsigned char c = toupper((unsigned char)*p);
        if (c == ' ' || c == '.') continue;
        base[bi++] = short_char_ok(c) ? c : '_';
    }
    if (!bi) base[bi++] = '_';
    for (const char *p = dot ? dot + 1 : ""; *p && ei < 3; p++) {
        unsigned char c = toupper((unsigned char)*p);
        if (c == ' ') continue;
        ext[ei++] = short_char_ok(c) ? c : '_';
    }
    for (int n = 1; n < 1000000; n++) {
        char tail[12];
        snprintf(tail, sizeof tail, "~%d", n);
        int keep = 8 - (int)strlen(tail);
        if (keep > bi) keep = bi;
        memset(raw, ' ', 11);
        memcpy(raw, base, keep);
        memcpy(raw + keep, tail, strlen(tail));
        memcpy(raw + 8, ext, ei);
        struct short_arg a = {raw, 0};
        dir_iter(d, short_cb, &a);
        if (!a.clash) return;
    }
}

// Find n free consecutive 32-byte slots (extending the directory if needed); returns the offset.
static int64_t find_slots(struct fat *f, struct dirbuf *d, int n) {
    for (;;) {
        int run = 0;
        for (uint32_t pos = 0; pos + 32 <= d->len; pos += 32) {
            uint8_t c = d->data[pos];
            if (c == 0x00) {
                // Everything after the end marker is free; make sure n entries fit.
                if ((d->len - pos) / 32 >= (uint32_t)(n - run)) return pos - run * 32;
                break;
            }
            if (c == 0xE5) {
                if (++run == n) return pos - (n - 1) * 32;
            } else {
                run = 0;
            }
        }
        if (dir_extend(f, d)) return -1;
    }
}

// Create an entry named name in dirbuf d; fills first cluster/size/attr.
static int add_entry(struct fat *f, struct dirbuf *d, const char *name, uint8_t attr, uint32_t first, uint32_t size) {
    uint8_t raw[11], nt = 0;
    int need_lfn = !clean_83(name, raw, &nt);
    if (!need_lfn) {
        struct short_arg a = {raw, 0};
        dir_iter(d, short_cb, &a);
        if (a.clash) need_lfn = 1;  // a different long name owns this short name
    }
    uint16_t u[256];
    int ul = 0;
    if (need_lfn) {
        make_short(d, name, raw);
        nt = 0;
        for (const unsigned char *p = (const unsigned char *)name; *p && ul < 255;) {
            unsigned c = *p++;
            if (c >= 0xE0 && p[0] && p[1]) {
                c = (c & 0x0F) << 12 | (p[0] & 0x3F) << 6 | (p[1] & 0x3F);
                p += 2;
            } else if (c >= 0xC0 && p[0]) {
                c = (c & 0x1F) << 6 | (p[0] & 0x3F);
                p += 1;
            }
            u[ul++] = c;
        }
    }
    int nlfn = need_lfn ? (ul + 12) / 13 : 0;
    int64_t at = find_slots(f, d, nlfn + 1);
    if (at < 0) return -1;
    uint8_t sum = lfn_sum(raw);
    for (int i = 0; i < nlfn; i++) {
        int seq = nlfn - i;  // stored last part first
        uint8_t *e = d->data + at + 32 * i;
        memset(e, 0, 32);
        e[0] = seq | (i == 0 ? 0x40 : 0);
        e[11] = 0x0F;
        e[13] = sum;
        static const int offs[13] = {1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30};
        for (int k = 0; k < 13; k++) {
            int ci = (seq - 1) * 13 + k;
            uint16_t ch = ci < ul ? u[ci] : ci == ul ? 0x0000 : 0xFFFF;
            wr16(e + offs[k], ch);
        }
    }
    uint8_t *e = d->data + at + 32 * nlfn;
    memset(e, 0, 32);
    memcpy(e, raw, 11);
    e[11] = attr;
    e[12] = nt;
    dos_time(e + 14, e + 16);
    memcpy(e + 18, e + 16, 2);
    memcpy(e + 22, e + 14, 2);
    memcpy(e + 24, e + 16, 2);
    wr16(e + 20, first >> 16);
    wr16(e + 26, first & 0xFFFF);
    wr32(e + 28, size);
    return 0;
}

static void free_chain(struct fat *f, uint32_t c) {
    for (int guard = 0; valid_cl(f, c) && guard < (int)f->nclusters; guard++) {
        uint32_t n = fat_get(f, c);
        fat_set(f, c, 0);
        if (is_eoc(f, n)) break;
        c = n;
    }
}

// Allocate a chain for len bytes and write data; returns the first cluster (0 for an empty file), or -1.
static int64_t write_chain(struct fat *f, const void *data, uint32_t len) {
    uint32_t need = (len + f->cluster_bytes - 1) / f->cluster_bytes;
    if (!need) return 0;
    uint32_t *cl = calloc(need, sizeof *cl);
    if (!cl) return -1;
    // Prefer one contiguous run.
    uint32_t got = 0, start = 0;
    for (uint32_t c = 2, run = 0; c < f->nclusters + 2; c++) {
        if (fat_get(f, c) == 0) {
            if (!run) start = c;
            if (++run == need) {
                for (uint32_t k = 0; k < need; k++) cl[k] = start + k;
                got = need;
                break;
            }
        } else {
            run = 0;
        }
    }
    if (!got) {
        for (uint32_t c = 2; c < f->nclusters + 2 && got < need; c++)
            if (fat_get(f, c) == 0) cl[got++] = c;
        if (got < need) {
            free(cl);
            errno = ENOSPC;
            return -1;
        }
    }
    for (uint32_t k = 0; k < need; k++) fat_set(f, cl[k], k + 1 < need ? cl[k + 1] : eoc(f));
    const uint8_t *p = data;
    for (uint32_t k = 0; k < need;) {
        uint32_t run = 1;
        while (k + run < need && cl[k + run] == cl[k] + run) run++;
        uint64_t off = (uint64_t)k * f->cluster_bytes;
        uint64_t n = (uint64_t)run * f->cluster_bytes;
        if (off + n > len) {
            // the last cluster: data, then zeros to the cluster end
            uint64_t have = len - off;
            if (have && pwrite_all(f->fd, p + off, have, cl_off(f, cl[k]))) goto fail;
            if (zero_range(f->fd, cl_off(f, cl[k]) + have, n - have)) goto fail;
        } else if (pwrite_all(f->fd, p + off, n, cl_off(f, cl[k]))) {
            goto fail;
        }
        k += run;
    }
    int64_t first = cl[0];
    free(cl);
    return first;
fail:
    free(cl);
    return -1;
}

static int mkdir_in(struct fat *f, uint32_t parent, const char *name, uint32_t *out) {
    struct dirbuf d;
    if (dir_load(f, parent, &d)) {
        dir_free(&d);
        return -1;
    }
    uint32_t c = alloc_one(f);
    if (!c) {
        dir_free(&d);
        errno = ENOSPC;
        return -1;
    }
    fat_set(f, c, eoc(f));
    uint8_t *blk = calloc(1, f->cluster_bytes);
    if (!blk) {
        dir_free(&d);
        return -1;
    }
    uint8_t *dot = blk, *dotdot = blk + 32;
    memset(dot, ' ', 11);
    dot[0] = '.';
    dot[11] = 0x10;
    dos_time(dot + 14, dot + 16);
    memcpy(dot + 18, dot + 16, 2);
    memcpy(dot + 22, dot + 14, 2);
    memcpy(dot + 24, dot + 16, 2);
    wr16(dot + 20, c >> 16);
    wr16(dot + 26, c & 0xFFFF);
    memcpy(dotdot, dot, 32);
    dotdot[1] = '.';
    uint32_t pc = (parent == f->root_cluster && f->type == 32) ? 0 : parent;
    wr16(dotdot + 20, pc >> 16);
    wr16(dotdot + 26, pc & 0xFFFF);
    int rc = pwrite_all(f->fd, blk, f->cluster_bytes, cl_off(f, c));
    free(blk);
    if (!rc) rc = add_entry(f, &d, name, 0x10, c, 0);
    if (!rc) rc = dir_store(f, &d);
    dir_free(&d);
    if (!rc) *out = c;
    return rc;
}

int fat_mkdirs(struct fat *f, const char *path) {
    char buf[512];
    snprintf(buf, sizeof buf, "%s", path);
    uint32_t cur = 0;
    char *save = NULL;
    for (char *tok = strtok_r(buf, "/", &save); tok; tok = strtok_r(NULL, "/", &save)) {
        struct dirbuf d;
        if (dir_load(f, cur, &d)) {
            dir_free(&d);
            return -1;
        }
        struct find_arg a = {.name = tok};
        dir_iter(&d, find_cb, &a);
        dir_free(&d);
        if (a.hit) {
            if (!(a.found.attr & 0x10)) {
                errno = ENOTDIR;
                return -1;
            }
            cur = a.found.first;
            if (cur == 0 && f->type == 32) cur = f->root_cluster;
            continue;
        }
        uint32_t c;
        if (mkdir_in(f, cur, tok, &c)) return -1;
        cur = c;
    }
    return 0;
}

int fat_write(struct fat *f, const char *path, const void *data, uint32_t len) {
    char dirpath[512], name[256];
    const char *slash = strrchr(path, '/');
    if (slash) {
        snprintf(dirpath, sizeof dirpath, "%.*s", (int)(slash - path), path);
        snprintf(name, sizeof name, "%s", slash + 1);
    } else {
        dirpath[0] = 0;
        snprintf(name, sizeof name, "%s", path);
    }
    if (!name[0]) {
        errno = EINVAL;
        return -1;
    }
    if (dirpath[0] && fat_mkdirs(f, dirpath)) return -1;
    uint32_t pdir;
    struct dent pe;
    if (lookup(f, dirpath, &pdir, &pe) != 1) return -1;
    uint32_t dcl = pe.first;
    struct dirbuf d;
    if (dir_load(f, dcl, &d)) {
        dir_free(&d);
        return -1;
    }
    struct find_arg a = {.name = name};
    dir_iter(&d, find_cb, &a);
    if (a.hit && (a.found.attr & 0x10)) {
        dir_free(&d);
        errno = EISDIR;
        return -1;
    }
    if (a.hit) free_chain(f, a.found.first);
    int64_t first = write_chain(f, data, len);
    if (first < 0) {
        dir_free(&d);
        return -1;
    }
    int rc;
    if (a.hit) {
        uint8_t *e = d.data + a.found.pos;
        wr16(e + 20, (uint32_t)first >> 16);
        wr16(e + 26, (uint32_t)first & 0xFFFF);
        wr32(e + 28, len);
        dos_time(e + 22, e + 24);
        rc = 0;
    } else {
        rc = add_entry(f, &d, name, 0x20, (uint32_t)first, len);
    }
    if (!rc) rc = dir_store(f, &d);
    dir_free(&d);
    if (!rc) rc = fat_flush(f);
    return rc;
}
