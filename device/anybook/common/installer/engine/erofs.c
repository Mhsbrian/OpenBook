// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Add files to an existing EROFS image without rebuilding it (ANAL-211, product.c). The image's own blocks are kept
// byte for byte, so its compressed files are never decompressed or re-encoded; what changes:
//   - the new files' data, the new and changed directories, and the new inodes are appended after the image's last
//     block (EROFS addresses inodes by nid = byte offset / 32, so new inodes can live anywhere after the metadata
//     start, and dirents carry 64-bit nids);
//   - every existing directory that gains an entry is rewritten in place as a flat (uncompressed, not inline)
//     directory pointing at its new blocks: the same inode slot, the new size and block address, and its link count
//     raised by the new subdirectories. Its old inline tail stays behind, unreferenced;
//   - the superblock's block and inode counts, and its CRC-32C (sb_csum).
// New inodes are extended (64-byte) flat inodes owned by root, files 0644 and directories 0755, with the image's
// build time. Their extended attributes are copied byte for byte from the nearest existing directory above them,
// so they carry the same SELinux label (on product: u:object_r:system_file:s0 for priv-app/, app/ and etc/, as
// file_contexts says for /product(/.*)?) and the same name filter. Directory entries are sorted by name and packed
// into blocks the way mkfs.erofs does, so the kernel's binary search works.
// Format: external/erofs-utils/include/erofs_fs.h (1.8.3). Only 4 KiB blocks and the features that do not change how
// directories and inodes are found are accepted.
#include "common.h"

#include <stdlib.h>
#include <string.h>

#define BS 4096u
#define EROFS_MAGIC 0xE0F5E1E2
#define KNOWN_INCOMPAT 0x7fu  // zero padding, compression configs/big pcluster, chunks, device table, ztailpacking,
                              // fragments/dedupe, xattr prefixes (none of them change directories or inode lookup)

static uint16_t le16(const uint8_t *p) { return p[0] | p[1] << 8; }
static uint32_t le32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t le64(const uint8_t *p) { return le32(p) | (uint64_t)le32(p + 4) << 32; }
static void put16(uint8_t *p, uint16_t v) { p[0] = v, p[1] = v >> 8; }
static void put32(uint8_t *p, uint32_t v) {
    for (int i = 0; i < 4; i++) p[i] = v >> (8 * i);
}
static void put64(uint8_t *p, uint64_t v) {
    put32(p, (uint32_t)v);
    put32(p + 4, v >> 32);
}

struct dent {
    char name[256];
    uint64_t nid;
    uint8_t type;  // 1 file, 2 dir
    struct enode *node;  // a new child: its nid is assigned later
};

struct enode {
    char name[256];
    int is_dir;
    int64_t orig_nid;  // -1: new
    uint64_t nid;      // final nid (orig_nid for existing nodes)
    struct enode *parent;
    struct enode **kids;
    int nkids, kcap;
    int file;          // index into the files, for new files
    uint64_t size;     // file size, or the (re)written directory's size
    uint32_t blkaddr, nblocks;
    int rewrite;       // an existing directory that gains entries
    int new_subdirs;
    struct dent *ents;
    int nents;
    uint8_t xattr[256];  // the donor's xattr body
    int xsize;
    uint32_t ino;
};

struct patch {
    uint64_t off;  // in the image
    uint8_t b[64];
    int n;
};

struct erofs_merge {
    int fd;
    uint64_t off;  // the original image's offset on fd (plan time)
    uint8_t sb[128];
    uint32_t meta_blkaddr, orig_blocks, total_blocks, root_nid;
    uint64_t inos, build_time;
    uint32_t build_nsec;
    struct enode *root;
    struct enode **order;  // every node, depth first, sorted
    int norder, ocap;
    const struct emfile *files;
    int nfiles;
    struct enode **file_nodes;  // by file index
    struct patch *patches;
    int npatches, pcap;
    uint32_t dir_start, dir_blocks, inode_start, inode_blocks;
    uint8_t *dirbuf, *inodebuf;
    int new_inodes, rewritten_dirs;
    char why[300];
};

static int fail(struct erofs_merge *m, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static int fail(struct erofs_merge *m, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(m->why, sizeof m->why, fmt, ap);
    va_end(ap);
    return -1;
}

struct einode {
    uint64_t pos;  // byte offset of the inode in the image
    int ext, layout, isize, xsize;
    uint16_t fmt, mode;
    uint64_t size;
    uint32_t raw, nlink;
    uint8_t raw_bytes[64 + 256];
};

static int read_inode(struct erofs_merge *m, uint64_t nid, struct einode *in) {
    memset(in, 0, sizeof *in);
    in->pos = (uint64_t)m->meta_blkaddr * BS + nid * 32;
    if (in->pos + 32 > (uint64_t)m->orig_blocks * BS) return fail(m, "inode %llu is outside the image", (unsigned long long)nid);
    size_t want = in->pos + sizeof in->raw_bytes <= (uint64_t)m->orig_blocks * BS ? sizeof in->raw_bytes
                                                                                    : (uint64_t)m->orig_blocks * BS - in->pos;
    if (pread_all(m->fd, in->raw_bytes, want, m->off + in->pos)) return fail(m, "cannot read the product image");
    const uint8_t *p = in->raw_bytes;
    in->fmt = le16(p);
    in->ext = in->fmt & 1;
    in->layout = (in->fmt >> 1) & 7;
    uint16_t xic = le16(p + 2);
    in->mode = le16(p + 4);
    in->isize = in->ext ? 64 : 32;
    in->xsize = xic ? 12 + 4 * (xic - 1) : 0;
    if (in->isize + in->xsize > (int)want || in->xsize > 256) return fail(m, "inode %llu is damaged", (unsigned long long)nid);
    if (in->ext) {
        in->size = le64(p + 8);
        in->raw = le32(p + 16);
        in->nlink = le32(p + 44);
    } else {
        in->nlink = le16(p + 6);
        in->size = le32(p + 8);
        in->raw = le32(p + 16);
    }
    return 0;
}

// An existing directory's entries.
static int read_dir(struct erofs_merge *m, const struct einode *in, struct dent **out, int *n) {
    *out = NULL;
    *n = 0;
    if ((in->mode & 0170000) != 0040000) return fail(m, "not a directory");
    if (in->size > 64 * MiB) return fail(m, "a directory of %llu bytes", (unsigned long long)in->size);
    uint8_t *d = malloc(in->size + 1);
    if (!d) return fail(m, "out of memory");
    uint64_t full = in->size / BS * BS, tail = in->size - full;
    if (in->layout == 0) {  // flat plain
        full = in->size;
        tail = 0;
    } else if (in->layout != 2) {
        free(d);
        return fail(m, "a directory with layout %d (compressed or chunked) is not supported", in->layout);
    }
    if (full && ((uint64_t)in->raw + (full + BS - 1) / BS > m->orig_blocks ||
                 pread_all(m->fd, d, full, m->off + (uint64_t)in->raw * BS))) {
        free(d);
        return fail(m, "cannot read a directory");
    }
    if (tail) {
        uint64_t at = in->pos + in->isize + in->xsize;
        if (at % BS + tail > BS || pread_all(m->fd, d + full, tail, m->off + at)) {
            free(d);
            return fail(m, "a directory's inline data is damaged");
        }
    }
    int cap = 0;
    for (uint64_t b = 0; b < in->size; b += BS) {
        const uint8_t *blk = d + b;
        uint32_t used = in->size - b < BS ? in->size - b : BS;
        if (used < 12) break;
        uint16_t first = le16(blk + 8);
        if (first % 12 || first < 12 || first > used) {
            free(d);
            free(*out);
            return fail(m, "a directory block is damaged");
        }
        int cnt = first / 12;
        for (int j = 0; j < cnt; j++) {
            const uint8_t *e = blk + 12 * j;
            uint32_t no = le16(e + 8), ne = j + 1 < cnt ? le16(e + 20) : used;
            if (no < first || ne > used || ne < no) {
                free(d);
                free(*out);
                return fail(m, "a directory entry is damaged");
            }
            uint32_t len = ne - no;
            while (len && blk[no + len - 1] == 0) len--;  // the block's last name ends at the first NUL
            if (!len || len > 255) {
                free(d);
                free(*out);
                return fail(m, "a directory entry name is damaged");
            }
            if (*n == cap) {
                cap = cap ? 2 * cap : 32;
                *out = realloc(*out, cap * sizeof **out);
            }
            struct dent *de = &(*out)[(*n)++];
            memset(de, 0, sizeof *de);
            memcpy(de->name, blk + no, len);
            de->nid = le64(e);
            de->type = e[10];
        }
    }
    free(d);
    return 0;
}

static struct enode *node_new(const char *name, int is_dir, int64_t orig, struct enode *parent) {
    struct enode *n = calloc(1, sizeof *n);
    snprintf(n->name, sizeof n->name, "%s", name);
    n->is_dir = is_dir;
    n->orig_nid = orig;
    n->nid = orig >= 0 ? (uint64_t)orig : 0;
    n->parent = parent;
    n->file = -1;
    if (parent) {
        if (parent->nkids == parent->kcap) {
            parent->kcap = parent->kcap ? 2 * parent->kcap : 8;
            parent->kids = realloc(parent->kids, parent->kcap * sizeof *parent->kids);
        }
        parent->kids[parent->nkids++] = n;
    }
    return n;
}

static struct enode *kid(struct enode *n, const char *name) {
    for (int i = 0; i < n->nkids; i++)
        if (!strcmp(n->kids[i]->name, name)) return n->kids[i];
    return NULL;
}

static int cmp_kid(const void *a, const void *b) {
    return strcmp((*(struct enode *const *)a)->name, (*(struct enode *const *)b)->name);
}
static int cmp_dent(const void *a, const void *b) { return strcmp(((const struct dent *)a)->name, ((const struct dent *)b)->name); }

static void walk(struct erofs_merge *m, struct enode *n) {
    if (m->norder == m->ocap) {
        m->ocap = m->ocap ? 2 * m->ocap : 64;
        m->order = realloc(m->order, m->ocap * sizeof *m->order);
    }
    m->order[m->norder++] = n;
    qsort(n->kids, n->nkids, sizeof *n->kids, cmp_kid);
    for (int i = 0; i < n->nkids; i++) walk(m, n->kids[i]);
}

static void free_node(struct enode *n) {
    for (int i = 0; i < n->nkids; i++) free_node(n->kids[i]);
    free(n->kids);
    free(n->ents);
    free(n);
}

void erofs_merge_free(struct erofs_merge *m) {
    if (!m) return;
    if (m->root) free_node(m->root);
    free(m->order);
    free(m->file_nodes);
    free(m->patches);
    free(m->dirbuf);
    free(m->inodebuf);
    free(m);
}

// Directory size when its sorted entries are packed into blocks (mkfs.erofs: a block holds whole entries).
static uint64_t dir_size(const struct dent *e, int n, uint32_t *blocks) {
    uint64_t full = 0;
    uint32_t used = 0, nb = 1;
    for (int i = 0; i < n; i++) {
        uint32_t need = 12 + strlen(e[i].name);
        if (used + need > BS) {
            nb++;
            full += BS;
            used = 0;
        }
        used += need;
    }
    *blocks = nb;
    return full + used;
}

static void dir_write(const struct dent *e, int n, uint8_t *out) {
    int i = 0;
    for (uint8_t *blk = out; i < n; blk += BS) {
        int start = i;
        uint32_t used = 0;
        while (i < n && used + 12 + strlen(e[i].name) <= BS) used += 12 + strlen(e[i++].name);
        uint32_t nameoff = 12 * (i - start);
        for (int k = start; k < i; k++) {
            uint8_t *d = blk + 12 * (k - start);
            uint64_t nid = e[k].node ? e[k].node->nid : e[k].nid;
            put64(d, nid);
            put16(d + 8, nameoff);
            d[10] = e[k].type;
            d[11] = 0;
            size_t l = strlen(e[k].name);
            memcpy(blk + nameoff, e[k].name, l);
            nameoff += l;
        }
    }
}

int erofs_merge_plan(int fd, uint64_t off, uint64_t image_bytes, const struct emfile *files, int nfiles,
                     struct erofs_merge **out, char *why, size_t wl) {
    struct erofs_merge *m = calloc(1, sizeof *m);
    *out = NULL;
    m->fd = fd;
    m->off = off;
    m->files = files;
    m->nfiles = nfiles;
    uint8_t blk0[BS];
    int rc = -1;
    if (image_bytes % BS || pread_all(fd, blk0, BS, off)) {
        fail(m, "cannot read the product image");
        goto out;
    }
    memcpy(m->sb, blk0 + 1024, 128);
    const uint8_t *sb = m->sb;
    if (le32(sb) != EROFS_MAGIC) {
        fail(m, "product is not an EROFS image");
        goto out;
    }
    if (sb[12] != 12 || sb[90] != 0) {
        fail(m, "product's EROFS block size is not 4 KiB");
        goto out;
    }
    if (le32(sb + 80) & ~KNOWN_INCOMPAT) {
        fail(m, "product's EROFS image uses features this installer does not know (0x%x)", le32(sb + 80));
        goto out;
    }
    if (sb[13]) {
        fail(m, "product's EROFS superblock has extension slots");
        goto out;
    }
    m->root_nid = le16(sb + 14);
    m->inos = le64(sb + 16);
    m->build_time = le64(sb + 24);
    m->build_nsec = le32(sb + 32);
    m->orig_blocks = le32(sb + 36);
    m->meta_blkaddr = le32(sb + 40);
    if ((uint64_t)m->orig_blocks * BS > image_bytes || !m->orig_blocks) {
        fail(m, "product's EROFS image is larger than its verified size");
        goto out;
    }
    m->orig_blocks = image_bytes / BS;  // new blocks start after everything dm-verity covered
    m->root = node_new("", 1, m->root_nid, NULL);
    // The tree of new paths, with the existing directories they go through.
    for (int i = 0; i < nfiles; i++) {
        char path[300], *save = NULL, *comp[16];
        int nc = 0;
        snprintf(path, sizeof path, "%s", files[i].rel);
        for (char *c = strtok_r(path, "/", &save); c && nc < 16; c = strtok_r(NULL, "/", &save)) comp[nc++] = c;
        struct enode *n = m->root;
        for (int k = 0; k < nc; k++) {
            int leaf = k == nc - 1;
            struct enode *c = kid(n, comp[k]);
            if (c) {
                if (leaf || !c->is_dir) {
                    fail(m, "%s is in the package twice", files[i].rel);
                    goto out;
                }
                n = c;
                continue;
            }
            int64_t found = -1;
            int ftype = 0;
            if (n->orig_nid >= 0) {
                struct einode in;
                struct dent *e;
                int ne;
                if (read_inode(m, n->orig_nid, &in) || read_dir(m, &in, &e, &ne)) goto out;
                for (int x = 0; x < ne; x++)
                    if (!strcmp(e[x].name, comp[k])) {
                        found = e[x].nid;
                        ftype = e[x].type;
                    }
                free(e);
            }
            if (found >= 0 && (leaf || ftype != 2)) {
                fail(m, "/product/%s already exists in this image", files[i].rel);
                goto out;
            }
            c = node_new(comp[k], !leaf, found, n);
            if (leaf) c->file = i;
            n = c;
        }
    }
    walk(m, m->root);
    m->file_nodes = calloc(nfiles ? nfiles : 1, sizeof *m->file_nodes);
    // Donor xattrs, existing directories' entries, and which existing directories are rewritten.
    for (int i = 0; i < m->norder; i++) {
        struct enode *n = m->order[i];
        if (n->file >= 0) m->file_nodes[n->file] = n;
        if (n->orig_nid >= 0) {
            struct einode in;
            if (read_inode(m, n->orig_nid, &in)) goto out;
            int has_new = 0;
            for (int k = 0; k < n->nkids; k++)
                if (n->kids[k]->orig_nid < 0) has_new = 1;
            if (has_new) {
                n->rewrite = 1;
                if (read_dir(m, &in, &n->ents, &n->nents)) goto out;
            }
            continue;
        }
        // a new node: the nearest existing directory above it gives its xattrs
        struct enode *d = n->parent;
        while (d && d->orig_nid < 0) d = d->parent;
        struct einode din;
        if (read_inode(m, d->orig_nid, &din)) goto out;
        memcpy(n->xattr, din.raw_bytes + din.isize, din.xsize);
        n->xsize = din.xsize;
    }
    // New directories' entries; new entries of rewritten ones.
    for (int i = 0; i < m->norder; i++) {
        struct enode *n = m->order[i];
        if (!n->is_dir || (n->orig_nid >= 0 && !n->rewrite)) continue;
        int base = n->nents;
        if (n->orig_nid < 0) {  // "." and ".."
            n->ents = realloc(n->ents, (n->nkids + 2) * sizeof *n->ents);
            memset(n->ents, 0, 2 * sizeof *n->ents);
            snprintf(n->ents[0].name, sizeof n->ents[0].name, ".");
            n->ents[0].type = 2;
            n->ents[0].node = n;
            snprintf(n->ents[1].name, sizeof n->ents[1].name, "..");
            n->ents[1].type = 2;
            if (n->parent->orig_nid >= 0) n->ents[1].nid = n->parent->orig_nid;
            else n->ents[1].node = n->parent;
            base = n->nents = 2;
        } else {
            n->ents = realloc(n->ents, (n->nents + n->nkids) * sizeof *n->ents);
        }
        for (int k = 0; k < n->nkids; k++) {
            struct enode *c = n->kids[k];
            if (c->orig_nid >= 0) continue;  // already listed
            struct dent *e = &n->ents[n->nents++];
            memset(e, 0, sizeof *e);
            snprintf(e->name, sizeof e->name, "%s", c->name);
            e->type = c->is_dir ? 2 : 1;
            e->node = c;
            if (c->is_dir) n->new_subdirs++;
        }
        (void)base;
        qsort(n->ents, n->nents, sizeof *n->ents, cmp_dent);
        n->size = dir_size(n->ents, n->nents, &n->nblocks);
        if (n->rewrite) m->rewritten_dirs++;
    }
    // Layout after the image: file data, directory blocks, inodes.
    uint64_t cur = m->orig_blocks;
    for (int f = 0; f < nfiles; f++) {
        struct enode *n = m->file_nodes[f];
        n->size = files[f].bytes;
        n->nblocks = (files[f].bytes + BS - 1) / BS;
        n->blkaddr = n->nblocks ? cur : 0xffffffff;
        cur += n->nblocks;
    }
    m->dir_start = cur;
    for (int i = 0; i < m->norder; i++) {
        struct enode *n = m->order[i];
        if (!n->is_dir || (n->orig_nid >= 0 && !n->rewrite)) continue;
        n->blkaddr = cur;
        cur += n->nblocks;
    }
    m->dir_blocks = cur - m->dir_start;
    m->inode_start = cur;
    uint64_t pos = cur * BS;
    uint32_t ino = m->inos;
    for (int i = 0; i < m->norder; i++) {
        struct enode *n = m->order[i];
        if (n->orig_nid >= 0) continue;
        uint32_t slot = (64 + n->xsize + 31) / 32 * 32;
        if (pos % BS + slot > BS) pos = (pos / BS + 1) * BS;
        n->nid = (pos - (uint64_t)m->meta_blkaddr * BS) / 32;
        n->ino = ++ino;
        pos += slot;
        m->new_inodes++;
    }
    m->inode_blocks = (pos + BS - 1) / BS - m->inode_start;
    m->total_blocks = m->inode_start + m->inode_blocks;
    if (cur > 0xfffffff0ull || m->total_blocks > 0xfffffff0ull) {
        fail(m, "the new product image would be too large for 32-bit block addresses");
        goto out;
    }
    // Directory blocks and inodes, now that every nid is known.
    m->dirbuf = calloc(m->dir_blocks ? m->dir_blocks : 1, BS);
    m->inodebuf = calloc(m->inode_blocks ? m->inode_blocks : 1, BS);
    for (int i = 0; i < m->norder; i++) {
        struct enode *n = m->order[i];
        if (n->is_dir && (n->orig_nid < 0 || n->rewrite))
            dir_write(n->ents, n->nents, m->dirbuf + (uint64_t)(n->blkaddr - m->dir_start) * BS);
        if (n->orig_nid < 0) {
            uint8_t *p = m->inodebuf + ((uint64_t)n->nid * 32 + (uint64_t)m->meta_blkaddr * BS - (uint64_t)m->inode_start * BS);
            put16(p, 1);  // extended, flat plain
            put16(p + 2, n->xsize ? (n->xsize - 12) / 4 + 1 : 0);
            put16(p + 4, n->is_dir ? 0040755 : 0100644);
            put64(p + 8, n->size);
            put32(p + 16, n->blkaddr);
            put32(p + 20, n->ino);
            put32(p + 24, 0);  // uid
            put32(p + 28, 0);  // gid
            put64(p + 32, m->build_time);
            put32(p + 40, m->build_nsec);
            put32(p + 44, n->is_dir ? 2 + n->new_subdirs : 1);
            memcpy(p + 64, n->xattr, n->xsize);
        } else if (n->rewrite) {
            struct einode in;
            if (read_inode(m, n->orig_nid, &in)) goto out;
            if (m->npatches == m->pcap) {
                m->pcap = m->pcap ? 2 * m->pcap : 16;
                m->patches = realloc(m->patches, m->pcap * sizeof *m->patches);
            }
            struct patch *pt = &m->patches[m->npatches++];
            pt->off = in.pos;
            pt->n = in.isize;
            memcpy(pt->b, in.raw_bytes, in.isize);
            put16(pt->b, in.fmt & ~0x000e);  // flat plain, same inode version
            if (in.ext) {
                put64(pt->b + 8, n->size);
                put32(pt->b + 44, in.nlink + n->new_subdirs);
            } else {
                put32(pt->b + 8, (uint32_t)n->size);
                put16(pt->b + 6, in.nlink + n->new_subdirs);
            }
            put32(pt->b + 16, n->blkaddr);
        }
    }
    rc = 0;
out:
    if (rc) {
        snprintf(why, wl, "%s", m->why);
        erofs_merge_free(m);
        return -1;
    }
    *out = m;
    return 0;
}

uint64_t erofs_merge_bytes(const struct erofs_merge *m) { return (uint64_t)m->total_blocks * BS; }
uint64_t erofs_merge_orig_bytes(const struct erofs_merge *m) { return (uint64_t)m->orig_blocks * BS; }
int erofs_merge_new_inodes(const struct erofs_merge *m) { return m->new_inodes; }
int erofs_merge_rewritten_dirs(const struct erofs_merge *m) { return m->rewritten_dirs; }

static uint32_t crc32c(uint32_t crc, const uint8_t *p, size_t n) {
    while (n--) {
        crc ^= *p++;
        for (int i = 0; i < 8; i++) crc = (crc >> 1) ^ ((crc & 1) ? 0x82F63B78 : 0);
    }
    return crc;
}

int erofs_merge_write(struct erofs_merge *m, int fd, uint64_t off, struct sha256 *src_hash,
                      int (*data)(void *arg, int file, uint64_t pos, uint8_t *buf, size_t n),
                      int (*emit)(void *arg, const uint8_t *buf, size_t n), void *arg) {
    enum { CHUNK = 256 };
    uint8_t *buf = malloc((size_t)CHUNK * BS);
    if (!buf) return -1;
    int rc = -1;
    // The image's own blocks, with the rewritten directories' inodes and the superblock.
    for (uint64_t b = 0; b < m->orig_blocks;) {
        uint64_t k = m->orig_blocks - b < CHUNK ? m->orig_blocks - b : CHUNK;
        if (pread_all(fd, buf, k * BS, off + b * BS)) goto out;
        if (src_hash) sha256_update(src_hash, buf, k * BS);  // the stick's bytes, before any change
        uint64_t lo = b * BS, hi = (b + k) * BS;
        for (int i = 0; i < m->npatches; i++) {
            const struct patch *p = &m->patches[i];
            for (int j = 0; j < p->n; j++)
                if (p->off + j >= lo && p->off + j < hi) buf[p->off + j - lo] = p->b[j];
        }
        if (b == 0) {
            uint8_t *sb = buf + 1024;
            if (le32(sb) != EROFS_MAGIC || memcmp(sb + 12, m->sb + 12, 4)) goto out;  // not the image planned for
            put64(sb + 16, m->inos + m->new_inodes);
            put32(sb + 36, m->total_blocks);
            if (le32(sb + 8) & 1) {  // sb_csum: CRC-32C of the superblock block from offset 1024, field zeroed
                put32(sb + 4, 0);
                put32(sb + 4, crc32c(0xffffffff, sb, BS - 1024));
            }
        }
        if (emit(arg, buf, k * BS)) goto out;
        b += k;
    }
    // New files' data, in block order.
    for (int f = 0; f < m->nfiles; f++) {
        const struct enode *n = m->file_nodes[f];
        for (uint64_t done = 0; done < (uint64_t)n->nblocks * BS;) {
            uint64_t left = (uint64_t)n->nblocks * BS - done, k = left < (uint64_t)CHUNK * BS ? left : (uint64_t)CHUNK * BS;
            uint64_t real = done >= n->size ? 0 : n->size - done < k ? n->size - done : k;
            if (real && data(arg, f, done, buf, real)) goto out;
            memset(buf + real, 0, k - real);
            if (emit(arg, buf, k)) goto out;
            done += k;
        }
    }
    if (m->dir_blocks && emit(arg, m->dirbuf, (size_t)m->dir_blocks * BS)) goto out;
    if (m->inode_blocks && emit(arg, m->inodebuf, (size_t)m->inode_blocks * BS)) goto out;
    rc = 0;
out:
    free(buf);
    return rc;
}
