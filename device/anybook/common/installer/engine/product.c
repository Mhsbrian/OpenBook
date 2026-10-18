// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// A new product partition with the user's own Google apps package (ANAL-211, docs/gapps.md section 5): the stick's
// product image plus the staged package's files (gapps.c) and this install's manifest of them
// (/product/etc/openbook/gapps-manifest.json), written straight onto the target's super:
//   - the EROFS image grows in place of a copy (erofs.c): the stick's blocks unchanged except the directories that
//     gain entries and the superblock; the new files, directories and inodes after them;
//   - a new dm-verity hashtree over the whole new image, with the stick's salt (avb.c), and the partition's own
//     vbmeta and AVB footer at its end, as avbtool add_hashtree_footer lays them out. No FEC: the stick's product has
//     2 FEC roots, the rebuilt one none (FEC repairs errors; dm-verity still detects every changed block);
//   - product_a moves to one new extent after super's other partitions, in super's metadata (lp.c);
//   - vbmeta_a: the stick's, with product's hashtree descriptor replaced, unsigned; the bootconfig's
//     androidboot.vbmeta.digest and .size are recomputed from it (install.c).
// Every input is checked while it is read: the stick's product extent against its manifest hash, every staged file
// against the package check's manifest. Nothing here writes outside the target's super and vbmeta_a.
#include "common.h"

#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define BS 4096u

void gp_free(struct gapps_product *g) {
    if (!g) return;
    json_free(g->manifest);
    free(g->mtext);
    free(g->files);
    free(g->stage);
    free(g->lp);
    free(g->vbmeta_src);
    free(g->footer_vb);
    free(g->vbmeta_new);
    erofs_merge_free(g->em);
    memset(g, 0, sizeof *g);
}

int gp_plan(struct gapps_product *g, const char *sha, struct source *src, const struct jv *inst, const uint8_t *meta,
            uint32_t meta_len, const char **code, char *why, size_t wl) {
    memset(g, 0, sizeof *g);
    snprintf(g->sha, sizeof g->sha, "%s", sha);
    *code = "no_gapps";
    g->manifest = gapps_load(sha, g->dir, sizeof g->dir, &g->mtext, &g->mlen, why, wl);
    if (!g->manifest) return -1;
    *code = "no_source";
    // product's extent in the stick's super (slot A on a stick)
    const char *slot = jstr(jget(inst, "bootconfig"), "androidboot.slot_suffix");
    snprintf(g->part, sizeof g->part, "product%s", slot ? slot : "_a");
    struct jv *ext = jget(jget(inst, "super"), "extents");
    struct jv *pe = NULL;
    for (int i = 0; ext && i < ext->len; i++)
        if (jstr(ext->items[i], "name") && !strcmp(jstr(ext->items[i], "name"), g->part)) pe = ext->items[i];
    const struct gpt_part *sp = gpt_find(&src->disk->gpt, "super"), *vp = gpt_find(&src->disk->gpt, "vbmeta_a");
    struct jv *vm = jget(jget(src->manifest, "partitions"), "vbmeta_a");
    if (!pe || !jstr(pe, "sha256") || !sp || !vp || !vm || !jstr(vm, "sha256")) {
        snprintf(why, wl, "install data: no %s extent or vbmeta_a on the stick", g->part);
        return -1;
    }
    uint64_t sector = src->disk->sector;
    g->src_off = sp->first * sector + (uint64_t)jnum(pe, "src", 0);
    g->src_bytes = (uint64_t)jnum(pe, "bytes", 0);
    g->old_dst = (uint64_t)jnum(pe, "dst", 0);
    snprintf(g->src_sha, sizeof g->src_sha, "%s", jstr(pe, "sha256"));
    // The stick's vbmeta (checked against its manifest) and product's footer.
    g->vbmeta_src_len = (size_t)jnum(vm, "bytes", 0);
    if (!g->vbmeta_src_len || g->vbmeta_src_len > MiB) {
        snprintf(why, wl, "install data: unexpected vbmeta_a size");
        return -1;
    }
    g->vbmeta_src = malloc(g->vbmeta_src_len);
    char got[65];
    if (pread_all(src->fd, g->vbmeta_src, g->vbmeta_src_len, vp->first * sector)) {
        snprintf(why, wl, "cannot read the stick's vbmeta_a: %s", strerror(errno));
        return -1;
    }
    sha256_hex(g->vbmeta_src, g->vbmeta_src_len, got);
    if (strcmp(got, jstr(vm, "sha256"))) {
        snprintf(why, wl, "the stick's vbmeta_a does not match its manifest");
        return -1;
    }
    if (avb_find_hashtree(g->vbmeta_src, g->vbmeta_src_len, "product", &g->ht_old)) {
        snprintf(why, wl, "the stick's vbmeta has no hashtree descriptor for product");
        return -1;
    }
    uint8_t foot[64];
    uint64_t orig, vbo, vbs;
    if (g->src_bytes < BS || pread_all(src->fd, foot, 64, g->src_off + g->src_bytes - 64) ||
        avb_read_footer(foot, &orig, &vbo, &vbs) || orig != g->ht_old.image_size || vbs > 65536 ||
        vbo + vbs > g->src_bytes) {
        snprintf(why, wl, "the stick's %s has no AVB footer that matches its vbmeta", g->part);
        return -1;
    }
    if (g->ht_old.data_block_size != BS || g->ht_old.hash_block_size != BS || strcmp(g->ht_old.hash_alg, "sha256") ||
        g->ht_old.root_len != 32) {
        snprintf(why, wl, "product's hashtree is not sha256 over 4 KiB blocks");
        return -1;
    }
    g->footer_vb = malloc(vbs);
    g->footer_vb_len = vbs;
    if (pread_all(src->fd, g->footer_vb, vbs, g->src_off + vbo)) {
        snprintf(why, wl, "cannot read the stick's %s footer", g->part);
        return -1;
    }
    // The files: the package's, then this install's manifest of them.
    struct jv *files = jget(g->manifest, "files");
    g->nfiles = files->len + 1;
    g->files = calloc(g->nfiles, sizeof *g->files);
    g->stage = calloc(g->nfiles, sizeof *g->stage);
    for (int i = 0; i < files->len; i++) {
        const char *rel = jstr(files->items[i], "path"), *st = jstr(files->items[i], "stage"), *h = jstr(files->items[i], "sha256");
        if (!rel || !st || !h || strlen(h) != 64 || strncmp(st, "files/", 6) || strchr(st + 6, '/') ||
            strstr(rel, "..")) {
            *code = "no_gapps";
            snprintf(why, wl, "the staged package's manifest is damaged");
            return -1;
        }
        g->files[i].rel = rel;
        g->files[i].bytes = (uint64_t)jnum(files->items[i], "bytes", 0);
        snprintf(g->stage[i].path, sizeof g->stage[i].path, "%s/%s", g->dir, st);
        snprintf(g->stage[i].sha256, sizeof g->stage[i].sha256, "%s", h);
        g->gapps_bytes += g->files[i].bytes;
    }
    g->files[files->len].rel = "etc/openbook/gapps-manifest.json";
    g->files[files->len].bytes = g->mlen;
    sha256_hex(g->mtext, g->mlen, g->stage[files->len].sha256);
    *code = "gapps_clash";
    if (erofs_merge_plan(src->fd, g->src_off, g->ht_old.image_size, g->files, g->nfiles, &g->em, why, wl)) return -1;
    *code = "no_space";
    g->image_bytes = erofs_merge_bytes(g->em);
    g->tree_bytes = avb_tree_size(g->image_bytes, BS);
    g->vbmeta_off = g->image_bytes + g->tree_bytes;
    g->part_bytes = g->vbmeta_off + (g->footer_vb_len + BS - 1) / BS * BS + BS;
    if (lp_relocate(meta, meta_len, g->part, g->part_bytes, &g->lp, &g->old_dst_meta, &g->new_dst, why, wl)) return -1;
    if (g->old_dst_meta != g->old_dst) {
        *code = "no_source";
        snprintf(why, wl, "install data: %s is at %llu in super's metadata, %llu in the manifest", g->part,
                 (unsigned long long)g->old_dst_meta, (unsigned long long)g->old_dst);
        return -1;
    }
    g->lp_len = meta_len;
    sha256_hex(g->lp, g->lp_len, g->lp_sha);
    g->ht_new = g->ht_old;
    g->ht_new.image_size = g->image_bytes;
    g->ht_new.tree_offset = g->image_bytes;
    g->ht_new.tree_size = g->tree_bytes;
    g->ht_new.fec_num_roots = 0;
    g->ht_new.fec_offset = 0;
    g->ht_new.fec_size = 0;
    *code = NULL;
    return 0;
}

// ------------------------------------------------------------------ build (apply)
struct gp_io {
    struct gapps_product *g;
    int dst;
    uint64_t at;  // next byte to write, relative to the partition
    struct ht_builder ht;
    struct sha256 part;
    void (*progress)(uint64_t);
    // the staged file being read
    int cur, cur_fd;
    struct sha256 cur_hash;
    uint64_t cur_done;
    char err[300];
};

static int emit(void *arg, const uint8_t *buf, size_t n) {
    struct gp_io *io = arg;
    if (pwrite_all(io->dst, buf, n, io->g->dst_abs + io->at)) {
        snprintf(io->err, sizeof io->err, "writing product: %s", strerror(errno));
        return -1;
    }
    for (size_t o = 0; o < n; o += BS) ht_add_block(&io->ht, buf + o);
    sha256_update(&io->part, buf, n);
    io->at += n;
    if (io->progress) io->progress(n);
    return 0;
}

static int finish_file(struct gp_io *io) {
    if (io->cur < 0) return 0;
    char h[65];
    sha256_final_hex(&io->cur_hash, h);
    if (io->cur_fd >= 0) close(io->cur_fd);
    io->cur_fd = -1;
    int f = io->cur;
    io->cur = -1;
    if (io->cur_done != io->g->files[f].bytes || strcmp(h, io->g->stage[f].sha256)) {
        snprintf(io->err, sizeof io->err, "the staged %s changed since the package was checked", io->g->files[f].rel);
        return -1;
    }
    return 0;
}

static int data(void *arg, int f, uint64_t pos, uint8_t *buf, size_t n) {
    struct gp_io *io = arg;
    struct gapps_product *g = io->g;
    if (f != io->cur) {
        if (finish_file(io)) return -1;
        io->cur = f;
        io->cur_done = 0;
        sha256_init(&io->cur_hash);
        io->cur_fd = f == g->nfiles - 1 ? -1 : open(g->stage[f].path, O_RDONLY | O_CLOEXEC);
        if (f != g->nfiles - 1 && io->cur_fd < 0) {
            snprintf(io->err, sizeof io->err, "cannot read the staged %s: %s", g->files[f].rel, strerror(errno));
            return -1;
        }
    }
    if (pos != io->cur_done) return -1;
    if (f == g->nfiles - 1) {
        if (pos + n > g->mlen) return -1;
        memcpy(buf, g->mtext + pos, n);
    } else if (pread_all(io->cur_fd, buf, n, pos)) {
        snprintf(io->err, sizeof io->err, "cannot read the staged %s: %s", g->files[f].rel, strerror(errno));
        return -1;
    }
    sha256_update(&io->cur_hash, buf, n);
    io->cur_done += n;
    return 0;
}

int gp_verify_staged(struct gapps_product *g, void (*progress)(uint64_t), char *err, size_t el) {
    static uint8_t buf[1 << 20];
    for (int f = 0; f < g->nfiles - 1; f++) {
        int fd = open(g->stage[f].path, O_RDONLY | O_CLOEXEC);
        if (fd < 0) {
            snprintf(err, el, "the staged %s is missing: check the package again", g->files[f].rel);
            return -1;
        }
        struct sha256 h;
        sha256_init(&h);
        uint64_t done = 0;
        for (;;) {
            ssize_t r = read(fd, buf, sizeof buf);
            if (r < 0 && errno == EINTR) continue;
            if (r <= 0) break;
            sha256_update(&h, buf, r);
            done += r;
            if (progress) progress(r);
        }
        close(fd);
        char hex[65];
        sha256_final_hex(&h, hex);
        if (done != g->files[f].bytes || strcmp(hex, g->stage[f].sha256)) {
            snprintf(err, el, "the staged %s does not match the package check (sha256 %.16s): check the package again",
                     g->files[f].rel, hex);
            return -1;
        }
    }
    return 0;
}

int gp_build(struct gapps_product *g, int src_fd, int dst_fd, uint64_t super_start, void (*progress)(uint64_t),
             char *err, size_t el) {
    struct gp_io io = {.g = g, .dst = dst_fd, .progress = progress, .cur = -1, .cur_fd = -1};
    g->dst_abs = super_start + g->new_dst;
    int rc = -1;
    LOG("product: building %s (%llu bytes) at %llu in super: the stick's image and %d files", g->part,
        (unsigned long long)g->part_bytes, (unsigned long long)g->new_dst, g->nfiles);
    uint8_t *blk = calloc(1, BS);
    sha256_init(&io.part);
    if (ht_init(&io.ht, g->image_bytes, BS, g->ht_old.salt, g->ht_old.salt_len)) {
        snprintf(err, el, "out of memory for product's hashtree");
        goto out;
    }
    // 1. The image: the stick's blocks (hashed as read, against the manifest), then the new ones.
    struct sha256 srch;
    sha256_init(&srch);
    if (erofs_merge_write(g->em, src_fd, g->src_off, &srch, data, emit, &io) || finish_file(&io)) {
        snprintf(err, el, "%s", io.err[0] ? io.err : "building product failed");
        goto out;
    }
    {  // the rest of the stick's extent (its old hashtree, FEC and footer) completes the source check
        static uint8_t buf[1 << 20];
        for (uint64_t o = erofs_merge_orig_bytes(g->em); o < g->src_bytes;) {
            size_t k = g->src_bytes - o < sizeof buf ? g->src_bytes - o : sizeof buf;
            if (pread_all(src_fd, buf, k, g->src_off + o)) {
                snprintf(err, el, "cannot read the stick's %s: %s", g->part, strerror(errno));
                goto out;
            }
            sha256_update(&srch, buf, k);
            o += k;
        }
        char h[65];
        sha256_final_hex(&srch, h);
        if (strcmp(h, g->src_sha)) {
            snprintf(err, el, "the stick's %s does not match its manifest (sha256 %.16s)", g->part, h);
            goto out;
        }
    }
    // 2. The hashtree, the partition's vbmeta, zeros, the AVB footer.
    if (ht_finish(&io.ht, g->ht_new.root)) {
        snprintf(err, el, "product's hashtree is incomplete");
        goto out;
    }
    for (int i = 0; i < 32; i++) snprintf(g->root_hex + 2 * i, 3, "%02x", g->ht_new.root[i]);
    if (pwrite_all(dst_fd, io.ht.tree, io.ht.tree_size, g->dst_abs + io.at)) {
        snprintf(err, el, "writing product's hashtree: %s", strerror(errno));
        goto out;
    }
    sha256_update(&io.part, io.ht.tree, io.ht.tree_size);
    io.at += io.ht.tree_size;
    if (progress) progress(io.ht.tree_size);
    if (avb_patch_footer_vbmeta(g->footer_vb, g->footer_vb_len, &g->ht_new)) {
        snprintf(err, el, "the stick's product footer cannot be updated");
        goto out;
    }
    uint64_t vb_block = (g->footer_vb_len + BS - 1) / BS * BS;
    uint8_t *vb = calloc(1, vb_block);
    memcpy(vb, g->footer_vb, g->footer_vb_len);
    int wr = pwrite_all(dst_fd, vb, vb_block, g->dst_abs + io.at);
    sha256_update(&io.part, vb, vb_block);
    free(vb);
    io.at += vb_block;
    memset(blk, 0, BS);
    avb_footer(blk + BS - 64, g->image_bytes, g->vbmeta_off, g->footer_vb_len);
    if (wr || io.at + BS != g->part_bytes || pwrite_all(dst_fd, blk, BS, g->dst_abs + io.at)) {
        snprintf(err, el, "writing product's footer: %s", strerror(errno));
        goto out;
    }
    sha256_update(&io.part, blk, BS);
    io.at += BS;
    sha256_final_hex(&io.part, g->part_sha);
    // 3. vbmeta_a with the new descriptor, and its digest for the bootconfig.
    free(g->vbmeta_new);
    if (avb_rebuild_unsigned(g->vbmeta_src, g->vbmeta_src_len, &g->ht_new, &g->vbmeta_new, &g->vbmeta_new_len) ||
        g->vbmeta_new_len > g->vbmeta_src_len) {
        snprintf(err, el, "cannot rebuild vbmeta");
        goto out;
    }
    sha256_hex(g->vbmeta_new, g->vbmeta_new_len, g->vbmeta_digest);
    LOG("product: %llu bytes (image %llu, hashtree %llu), root digest %s, at %llu in super; vbmeta digest %s",
        (unsigned long long)g->part_bytes, (unsigned long long)g->image_bytes, (unsigned long long)g->tree_bytes,
        g->root_hex, (unsigned long long)g->new_dst, g->vbmeta_digest);
    rc = 0;
out:
    if (io.cur_fd >= 0) close(io.cur_fd);
    ht_free(&io.ht);
    free(blk);
    return rc;
}

// The vbmeta_a partition's content: the new vbmeta, padded with zeros to the stick's vbmeta_a size.
uint8_t *gp_vbmeta_partition(const struct gapps_product *g, size_t *len) {
    uint8_t *p = calloc(1, g->vbmeta_src_len);
    if (!p || !g->vbmeta_new) {
        free(p);
        return NULL;
    }
    memcpy(p, g->vbmeta_new, g->vbmeta_new_len);
    *len = g->vbmeta_src_len;
    return p;
}

void gp_json(struct jw *w, const struct gapps_product *g) {
    jw_obj(w, "gapps");
    jw_str(w, "manifest_sha256", g->sha);
    struct jv *pkg = jget(g->manifest, "package");
    jw_obj(w, "package");
    jw_str(w, "file", jstr(pkg, "file"));
    jw_u64(w, "bytes", (uint64_t)jnum(pkg, "bytes", 0));
    jw_str(w, "sha256", jstr(pkg, "sha256"));
    jw_str(w, "name", jstr(pkg, "name"));
    jw_str(w, "version", jstr(pkg, "version"));
    jw_endo(w);
    jw_int(w, "files", g->nfiles - 1);
    jw_u64(w, "bytes", g->gapps_bytes);
    struct jv *apps = jget(g->manifest, "apps");
    jw_arr(w, "apps");
    for (int i = 0; apps && i < apps->len; i++) {
        struct jv *a = apps->items[i];
        jw_obj(w, NULL);
        jw_str(w, "dir", jstr(a, "dir"));
        jw_str(w, "package", jstr(a, "package"));
        jw_str(w, "version_name", jstr(a, "version_name"));
        jw_int(w, "version_code", (long long)jnum(a, "version_code", 0));
        jw_bool(w, "privileged", jbool(a, "privileged", 0));
        jw_str(w, "native", jstr(a, "native"));
        jw_str(w, "signer_sha256", jstr(a, "signer_sha256"));
        jw_str(w, "signer", jstr(a, "signer"));
        jw_endo(w);
    }
    jw_enda(w);
    jw_endo(w);
    jw_obj(w, "product");
    jw_str(w, "partition", g->part);
    jw_u64(w, "stick_bytes", g->src_bytes);
    jw_u64(w, "stick_image_bytes", g->ht_old.image_size);
    jw_u64(w, "bytes", g->part_bytes);
    jw_u64(w, "image_bytes", g->image_bytes);
    jw_u64(w, "hashtree_bytes", g->tree_bytes);
    jw_int(w, "fec_roots", 0);
    jw_int(w, "new_inodes", erofs_merge_new_inodes(g->em));
    jw_int(w, "rewritten_directories", erofs_merge_rewritten_dirs(g->em));
    jw_u64(w, "super_offset_before", g->old_dst);
    jw_u64(w, "super_offset", g->new_dst);
    jw_str(w, "super_metadata_sha256", g->lp_sha);
    jw_str(w, "vbmeta", "unsigned");
    jw_endo(w);
}
