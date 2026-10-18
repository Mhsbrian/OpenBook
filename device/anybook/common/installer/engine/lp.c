// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// super's logical-partition metadata (liblp, system/fs/fs_mgr/liblp/include/liblp/metadata_format.h, version 10.x)
// for a rebuilt product partition (ANAL-211, product.c). The installer writes the metadata region the stick carries
// for an installed super (openbook/install/super-metadata.img, made by lpmake in mklive.py); this moves one
// partition to a single new extent of a new size, after every allocated extent, and leaves every other partition,
// group and flag as it was. Each metadata copy (both geometries, primary and backup of every slot) is checked first;
// the copies must be identical, as lpmake writes them, and all get the new metadata with fresh SHA-256 checksums.
#include "common.h"

#include <stdlib.h>
#include <string.h>

#define LP_GEOMETRY_MAGIC 0x616c4467
#define LP_HEADER_MAGIC 0x414C5030

static uint32_t le32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t le64(const uint8_t *p) { return le32(p) | (uint64_t)le32(p + 4) << 32; }
static void put32(uint8_t *p, uint32_t v) {
    for (int i = 0; i < 4; i++) p[i] = v >> (8 * i);
}
static void put64(uint8_t *p, uint64_t v) {
    put32(p, (uint32_t)v);
    put32(p + 4, v >> 32);
}

static void sha_bin(const void *d, size_t n, uint8_t out[32]) {
    struct sha256 c;
    sha256_init(&c);
    sha256_update(&c, d, n);
    sha256_final(&c, out);
}

// A copy's header + tables size, after its checksums are checked; 0 if invalid.
static size_t meta_valid(const uint8_t *m, uint32_t max) {
    if (max < 128 || le32(m) != LP_HEADER_MAGIC || (m[4] | m[5] << 8) != 10) return 0;
    uint32_t hs = le32(m + 8), ts = le32(m + 44);
    if (hs < 128 || hs > 256 || (uint64_t)hs + ts > max) return 0;
    uint8_t h[256], d[32];
    memcpy(h, m, hs);
    memset(h + 12, 0, 32);
    sha_bin(h, hs, d);
    if (memcmp(d, m + 12, 32)) return 0;
    sha_bin(m + hs, ts, d);
    if (memcmp(d, m + 48, 32)) return 0;
    return hs + ts;
}

int lp_relocate(const uint8_t *meta, size_t len, const char *part, uint64_t new_bytes, uint8_t **out,
                uint64_t *old_off, uint64_t *new_off, char *why, size_t wl) {
    *out = NULL;
    if (len < 12288 || le32(meta + 4096) != LP_GEOMETRY_MAGIC || memcmp(meta + 4096, meta + 8192, 4096)) {
        snprintf(why, wl, "super metadata: no valid geometry");
        return -1;
    }
    const uint8_t *g = meta + 4096;
    {
        uint8_t gg[52], d[32];
        uint32_t gs = le32(g + 4);
        if (gs != 52) {
            snprintf(why, wl, "super metadata: unexpected geometry size %u", gs);
            return -1;
        }
        memcpy(gg, g, 52);
        memset(gg + 8, 0, 32);
        sha_bin(gg, 52, d);
        if (memcmp(d, g + 8, 32)) {
            snprintf(why, wl, "super metadata: geometry checksum");
            return -1;
        }
    }
    uint32_t max = le32(g + 40), slots = le32(g + 44), lbs = le32(g + 48);
    if (!max || max % 512 || !slots || slots > 8 || 12288 + 2ull * slots * max > len || !lbs || new_bytes % lbs) {
        snprintf(why, wl, "super metadata: unexpected geometry (%u slots of %u bytes, block %u)", slots, max, lbs);
        return -1;
    }
    const uint8_t *m0 = meta + 12288;
    size_t used = meta_valid(m0, max);
    if (!used) {
        snprintf(why, wl, "super metadata: slot 0 is not valid");
        return -1;
    }
    for (uint32_t i = 1; i < 2 * slots; i++)
        if (memcmp(meta + 12288 + (size_t)i * max, m0, max)) {
            snprintf(why, wl, "super metadata: the metadata copies differ (copy %u)", i);
            return -1;
        }
    uint32_t hs = le32(m0 + 8);
    uint8_t *m = malloc(max);
    memcpy(m, m0, max);
    uint8_t *t = m + hs;
    uint32_t p_off = le32(m + 80), p_n = le32(m + 84), p_sz = le32(m + 88);
    uint32_t e_off = le32(m + 92), e_n = le32(m + 96), e_sz = le32(m + 100);
    uint32_t g_off = le32(m + 104), g_n = le32(m + 108), g_sz = le32(m + 112);
    uint32_t b_off = le32(m + 116), b_n = le32(m + 120), b_sz = le32(m + 124);
    uint32_t ts = le32(m + 44);
    if (p_sz < 52 || e_sz < 24 || g_sz < 48 || b_sz < 64 || b_n != 1 || (uint64_t)p_off + (uint64_t)p_n * p_sz > ts ||
        (uint64_t)e_off + (uint64_t)e_n * e_sz > ts || (uint64_t)g_off + (uint64_t)g_n * g_sz > ts ||
        (uint64_t)b_off + b_sz > ts) {
        free(m);
        snprintf(why, wl, "super metadata: unexpected tables (or more than one block device)");
        return -1;
    }
    const uint8_t *bd = t + b_off;
    uint64_t first = le64(bd), dev = le64(bd + 16);
    uint32_t align = le32(bd + 8), aoff = le32(bd + 12);
    if (!align) align = MiB;
    int target = -1;
    uint64_t end = first;  // sectors
    for (uint32_t i = 0; i < p_n; i++) {
        const uint8_t *pp = t + p_off + i * p_sz;
        uint32_t fe = le32(pp + 40), ne = le32(pp + 44);
        if ((uint64_t)fe + ne > e_n) {
            free(m);
            snprintf(why, wl, "super metadata: an extent index is out of range");
            return -1;
        }
        char name[37];
        memcpy(name, pp, 36);
        name[36] = 0;
        if (!strcmp(name, part)) target = i;
        for (uint32_t k = 0; k < ne; k++) {
            const uint8_t *e = t + e_off + (fe + k) * e_sz;
            if (le32(e + 8) == 0 && le64(e + 12) + le64(e) > end) end = le64(e + 12) + le64(e);  // linear
        }
    }
    if (target < 0) {
        free(m);
        snprintf(why, wl, "super metadata: no partition %s", part);
        return -1;
    }
    uint8_t *pp = t + p_off + target * p_sz;
    if (le32(pp + 44) != 1) {
        uint32_t ne = le32(pp + 44);
        free(m);
        snprintf(why, wl, "super metadata: %s has %u extents (one expected)", part, ne);
        return -1;
    }
    uint8_t *ext = t + e_off + le32(pp + 40) * e_sz;
    if (le32(ext + 8) != 0) {
        free(m);
        snprintf(why, wl, "super metadata: %s is not a linear extent", part);
        return -1;
    }
    *old_off = le64(ext + 12) * 512;
    // The first aligned sector after every allocated extent (liblp aligns to alignment + alignment_offset).
    uint64_t at = (end * 512 + align - 1 - aoff % align) / align * align + aoff % align;
    if (at < end * 512) at += align;
    if (at + new_bytes > dev) {
        free(m);
        snprintf(why, wl, "super has no room for a %llu-byte %s (free from %llu to %llu)", (unsigned long long)new_bytes,
                 part, (unsigned long long)at, (unsigned long long)dev);
        return -1;
    }
    // The group's maximum size, counting the new size.
    uint32_t gi = le32(pp + 48);
    if (gi < g_n) {
        uint64_t gmax = le64(t + g_off + gi * g_sz + 40), sum = new_bytes;
        for (uint32_t i = 0; i < p_n; i++) {
            const uint8_t *q = t + p_off + i * p_sz;
            if ((int)i == target || le32(q + 48) != gi) continue;
            for (uint32_t k = 0; k < le32(q + 44); k++) sum += le64(t + e_off + (le32(q + 40) + k) * e_sz) * 512;
        }
        if (gmax && sum > gmax) {
            free(m);
            snprintf(why, wl, "%s would grow its group past its maximum (%llu of %llu bytes)", part,
                     (unsigned long long)sum, (unsigned long long)gmax);
            return -1;
        }
    }
    put64(ext, new_bytes / 512);
    put64(ext + 12, at / 512);
    *new_off = at;
    uint8_t d[32];
    sha_bin(t, ts, d);
    memcpy(m + 48, d, 32);
    memset(m + 12, 0, 32);
    sha_bin(m, hs, d);
    memcpy(m + 12, d, 32);
    uint8_t *o = malloc(len);
    memcpy(o, meta, len);
    for (uint32_t i = 0; i < 2 * slots; i++) memcpy(o + 12288 + (size_t)i * max, m, max);
    free(m);
    (void)used;
    *out = o;
    return 0;
}
