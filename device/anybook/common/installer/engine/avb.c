// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Android Verified Boot pieces for a rebuilt product partition (ANAL-211, product.c): the dm-verity hashtree in
// avbtool's layout (add_hashtree_footer: salted SHA-256 over 4 KiB blocks, the level closest to the root first, each
// level padded to a block), the AVB footer, and a vbmeta image with one partition's hashtree descriptor replaced.
//
// The images are signed with the build's key, which a user's computer does not have, so the rebuilt vbmeta is
// unsigned (algorithm NONE). On OpenBook that is the orange state already: the loader reports an unlocked device,
// first-stage init allows the verification error, and still sets up dm-verity from these descriptors, so every
// block of product is checked against the new root digest (docs/installer.md section 2.1). The digest and size the
// loader passes in bootconfig are recomputed from the new image, so libfs_avb's digest check passes.
#include "common.h"

#include <stdlib.h>
#include <string.h>

static uint32_t be32(const uint8_t *p) { return (uint32_t)p[0] << 24 | p[1] << 16 | p[2] << 8 | p[3]; }
static uint64_t be64(const uint8_t *p) { return (uint64_t)be32(p) << 32 | be32(p + 4); }
static void put32(uint8_t *p, uint32_t v) {
    p[0] = v >> 24;
    p[1] = v >> 16;
    p[2] = v >> 8;
    p[3] = v;
}
static void put64(uint8_t *p, uint64_t v) {
    put32(p, v >> 32);
    put32(p + 4, (uint32_t)v);
}

// ------------------------------------------------------------------ vbmeta images
size_t avb_vbmeta_size(const uint8_t *vb, size_t n) {
    if (n < 256 || memcmp(vb, "AVB0", 4)) return 0;
    uint64_t a = be64(vb + 12), x = be64(vb + 20);
    if (a > n || x > n || 256 + a + x > n || a % 64 || x % 64) return 0;
    return 256 + a + x;
}

int avb_find_hashtree(const uint8_t *vb, size_t n, const char *partition, struct avb_ht *ht) {
    size_t total = avb_vbmeta_size(vb, n);
    if (!total) return -1;
    uint64_t auth = be64(vb + 12), aux = be64(vb + 20), doff = be64(vb + 96), dsize = be64(vb + 104);
    if (doff > aux || dsize > aux - doff) return -1;
    const uint8_t *d = vb + 256 + auth + doff, *end = d + dsize;
    while (end - d >= 16) {
        uint64_t tag = be64(d), len = be64(d + 8);
        if (len > (uint64_t)(end - d - 16) || len % 8) return -1;
        if (tag == 1 && len >= 164) {  // hashtree
            const uint8_t *h = d + 16;
            uint32_t nl = be32(h + 88), sl = be32(h + 92), rl = be32(h + 96);
            if ((uint64_t)164 + nl + sl + rl <= len && nl < sizeof ht->partition && sl <= sizeof ht->salt &&
                rl <= sizeof ht->root && nl == strlen(partition) && !memcmp(h + 164, partition, nl)) {
                memset(ht, 0, sizeof *ht);
                ht->dm_verity_version = be32(h);
                ht->image_size = be64(h + 4);
                ht->tree_offset = be64(h + 12);
                ht->tree_size = be64(h + 20);
                ht->data_block_size = be32(h + 28);
                ht->hash_block_size = be32(h + 32);
                ht->fec_num_roots = be32(h + 36);
                ht->fec_offset = be64(h + 40);
                ht->fec_size = be64(h + 48);
                memcpy(ht->hash_alg, h + 56, 32);
                memcpy(ht->partition, h + 164, nl);
                ht->salt_len = sl;
                memcpy(ht->salt, h + 164 + nl, sl);
                ht->root_len = rl;
                memcpy(ht->root, h + 164 + nl + sl, rl);
                ht->flags = be32(h + 100);
                ht->desc_off = d - vb;
                ht->desc_len = 16 + len;
                return 0;
            }
        }
        d += 16 + len;
    }
    return -1;
}

// Write ht's sizes, FEC fields and root digest into the hashtree descriptor at desc (name, salt and lengths unchanged).
static void patch_ht(uint8_t *desc, const struct avb_ht *ht) {
    uint8_t *h = desc + 16;
    put64(h + 4, ht->image_size);
    put64(h + 12, ht->tree_offset);
    put64(h + 20, ht->tree_size);
    put32(h + 36, ht->fec_num_roots);
    put64(h + 40, ht->fec_offset);
    put64(h + 48, ht->fec_size);
    memcpy(h + 164 + be32(h + 88) + be32(h + 92), ht->root, ht->root_len);
}

int avb_rebuild_unsigned(const uint8_t *vb, size_t n, const struct avb_ht *nht, uint8_t **out, size_t *olen) {
    struct avb_ht old;
    if (avb_find_hashtree(vb, n, nht->partition, &old) || old.salt_len != nht->salt_len ||
        old.root_len != nht->root_len || nht->root_len != 32)
        return -1;
    uint64_t auth = be64(vb + 12), doff = be64(vb + 96), dsize = be64(vb + 104);
    uint64_t aux = (dsize + 63) / 64 * 64;
    uint8_t *o = calloc(1, 256 + aux);
    if (!o) return -1;
    memcpy(o, vb, 256);
    put64(o + 12, 0);    // no authentication block
    put64(o + 20, aux);  // descriptors only
    put32(o + 28, 0);    // AVB_ALGORITHM_TYPE_NONE
    put64(o + 32, 0);    // hash
    put64(o + 40, 0);
    put64(o + 48, 0);    // signature
    put64(o + 56, 0);
    put64(o + 64, dsize);  // public key: none (avbtool puts the offsets after the descriptors)
    put64(o + 72, 0);
    put64(o + 80, dsize);
    put64(o + 88, 0);
    put64(o + 96, 0);    // descriptors first in the auxiliary block
    put64(o + 104, dsize);
    memcpy(o + 256, vb + 256 + auth + doff, dsize);
    patch_ht(o + 256 + (old.desc_off - (256 + auth + doff)), nht);
    *out = o;
    *olen = 256 + aux;
    return 0;
}

int avb_patch_footer_vbmeta(uint8_t *vb, size_t n, const struct avb_ht *nht) {
    struct avb_ht old;
    if (avb_find_hashtree(vb, n, nht->partition, &old) || old.salt_len != nht->salt_len ||
        old.root_len != nht->root_len || be32(vb + 28) != 0 || be64(vb + 12) != 0)
        return -1;  // a partition's own vbmeta is unsigned when its descriptors live in the top-level vbmeta
    patch_ht(vb + old.desc_off, nht);
    return 0;
}

int avb_read_footer(const uint8_t f[64], uint64_t *orig, uint64_t *vbo, uint64_t *vbs) {
    if (memcmp(f, "AVBf", 4) || be32(f + 4) != 1) return -1;
    *orig = be64(f + 12);
    *vbo = be64(f + 20);
    *vbs = be64(f + 28);
    return 0;
}

void avb_footer(uint8_t f[64], uint64_t orig, uint64_t vbo, uint64_t vbs) {
    memset(f, 0, 64);
    memcpy(f, "AVBf", 4);
    put32(f + 4, 1);  // footer version 1.0
    put32(f + 8, 0);
    put64(f + 12, orig);
    put64(f + 20, vbo);
    put64(f + 28, vbs);
}

// ------------------------------------------------------------------ hashtree (avbtool generate_hash_tree)
uint64_t avb_tree_size(uint64_t image_size, uint32_t bs) {
    uint64_t total = 0, size = image_size;
    while (size > bs) {
        uint64_t blocks = (size + bs - 1) / bs, level = (blocks * 32 + bs - 1) / bs * bs;
        total += level;
        size = level;
    }
    return total;
}

int ht_init(struct ht_builder *h, uint64_t image_size, uint32_t bs, const uint8_t *salt, size_t sl) {
    memset(h, 0, sizeof *h);
    if (image_size % bs || image_size <= bs || sl > sizeof h->salt) return -1;
    h->bs = bs;
    memcpy(h->salt, salt, sl);
    h->salt_len = sl;
    h->blocks = image_size / bs;
    uint64_t size = image_size;
    while (size > bs && h->nlevels < 16) {
        uint64_t blocks = (size + bs - 1) / bs;
        h->level_size[h->nlevels] = (blocks * 32 + bs - 1) / bs * bs;
        size = h->level_size[h->nlevels++];
    }
    for (int i = 0; i < h->nlevels; i++) {
        h->level_off[i] = 0;
        for (int k = i + 1; k < h->nlevels; k++) h->level_off[i] += h->level_size[k];
        h->tree_size += h->level_size[i];
    }
    h->tree = calloc(1, h->tree_size);
    return h->tree ? 0 : -1;
}

static void salted(const struct ht_builder *h, const uint8_t *data, size_t n, uint8_t out[32]) {
    struct sha256 c;
    sha256_init(&c);
    sha256_update(&c, h->salt, h->salt_len);
    sha256_update(&c, data, n);
    sha256_final(&c, out);
}

int ht_add_block(struct ht_builder *h, const uint8_t *block) {
    if (h->done >= h->blocks) return -1;
    salted(h, block, h->bs, h->tree + h->level_off[0] + h->done * 32);
    h->done++;
    return 0;
}

int ht_finish(struct ht_builder *h, uint8_t root[32]) {
    if (h->done != h->blocks) return -1;
    for (int lv = 1; lv < h->nlevels; lv++) {
        // level lv hashes the blocks of level lv-1 (its whole padded size)
        uint64_t src = h->level_off[lv - 1], nblk = h->level_size[lv - 1] / h->bs;
        for (uint64_t b = 0; b < nblk; b++) salted(h, h->tree + src + b * h->bs, h->bs, h->tree + h->level_off[lv] + b * 32);
    }
    // the root hashes the top level's block(s)
    salted(h, h->tree + h->level_off[h->nlevels - 1], h->level_size[h->nlevels - 1], root);
    return 0;
}

void ht_free(struct ht_builder *h) {
    free(h->tree);
    h->tree = NULL;
}
