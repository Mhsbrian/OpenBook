// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Archive reading for the bring-your-own GApps step (ANAL-211, gapps.c): zip (stored and deflate, zip64 sizes and
// offsets), xz (the LZMA SDK's decoder, external/lzma), brotli (external/brotli's decoder) and tar (ustar, GNU long
// names, pax path and size). Everything is a pull stream (struct src), so a package of any size is read once, in
// order, with bounded memory. The input is untrusted: every length is checked against what contains it, the
// output of a compressed entry may not exceed its declared size, and a zip entry's CRC-32 is checked at its end.
#include "archive.h"

#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <7zCrc.h>
#include <Alloc.h>
#include <Xz.h>
#include <XzCrc64.h>
#include <brotli/decode.h>

static uint16_t le16(const uint8_t *p) { return p[0] | p[1] << 8; }
static uint32_t le32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t le64(const uint8_t *p) { return le32(p) | (uint64_t)le32(p + 4) << 32; }

ssize_t src_read_full(struct src *s, void *buf, size_t n) {
    size_t done = 0;
    while (done < n) {
        ssize_t r = s->read(s, (uint8_t *)buf + done, n - done);
        if (r < 0) return -1;
        if (r == 0) break;
        done += r;
    }
    return done;
}

// ------------------------------------------------------------------ zip
#define ZIP_MAX_ENTRIES 200000

static int zip_fail(char *why, size_t wl, const char *m) {
    snprintf(why, wl, "%s", m);
    return -1;
}

int zip_open(struct zip *z, int fd, uint64_t size, char *why, size_t wl) {
    memset(z, 0, sizeof *z);
    z->fd = fd;
    z->size = size;
    if (size < 22) return zip_fail(why, wl, "not a zip file (too short)");
    // The end-of-central-directory record is in the last 64 KiB + 22 bytes.
    size_t tail = size < 65536 + 22 ? size : 65536 + 22;
    uint8_t *t = malloc(tail);
    if (!t || pread_all(fd, t, tail, size - tail)) {
        free(t);
        return zip_fail(why, wl, "cannot read the zip file");
    }
    long eocd = -1;
    for (long i = (long)tail - 22; i >= 0; i--)
        if (le32(t + i) == 0x06054b50 && i + 22 + le16(t + i + 20) <= (long)tail) {
            eocd = i;
            break;
        }
    if (eocd < 0) {
        free(t);
        return zip_fail(why, wl, "not a zip file (no end of central directory)");
    }
    uint64_t n = le16(t + eocd + 10), cdsize = le32(t + eocd + 12), cdoff = le32(t + eocd + 16);
    uint64_t eocd_abs = size - tail + eocd;
    if (n == 0xffff || cdsize == 0xffffffff || cdoff == 0xffffffff) {  // zip64: locator right before the EOCD
        uint8_t loc[20], rec[56];
        if (eocd_abs < 20 || pread_all(fd, loc, 20, eocd_abs - 20) || le32(loc) != 0x07064b50) {
            free(t);
            return zip_fail(why, wl, "zip64 archive without its locator");
        }
        uint64_t roff = le64(loc + 8);
        if (roff + 56 > size || pread_all(fd, rec, 56, roff) || le32(rec) != 0x06064b50) {
            free(t);
            return zip_fail(why, wl, "zip64 archive without its end record");
        }
        n = le64(rec + 32);
        cdsize = le64(rec + 40);
        cdoff = le64(rec + 48);
    }
    free(t);
    z->cd_offset = cdoff;
    if (n > ZIP_MAX_ENTRIES || cdoff > size || cdsize > size - cdoff || cdsize > 256 * MiB)
        return zip_fail(why, wl, "the zip's central directory is out of range");
    uint8_t *cd = malloc(cdsize ? cdsize : 1);
    if (!cd || pread_all(fd, cd, cdsize, cdoff)) {
        free(cd);
        return zip_fail(why, wl, "cannot read the zip's central directory");
    }
    z->e = calloc(n ? n : 1, sizeof *z->e);
    uint64_t p = 0;
    for (uint64_t i = 0; i < n; i++) {
        if (p + 46 > cdsize || le32(cd + p) != 0x02014b50) {
            free(cd);
            zip_close(z);
            return zip_fail(why, wl, "the zip's central directory is damaged");
        }
        const uint8_t *h = cd + p;
        struct zentry *e = &z->e[z->n];
        uint16_t nl = le16(h + 28), xl = le16(h + 30), cl = le16(h + 32);
        if (p + 46 + nl + xl + cl > cdsize) {
            free(cd);
            zip_close(z);
            return zip_fail(why, wl, "the zip's central directory is damaged");
        }
        e->flags = le16(h + 8);
        e->method = le16(h + 10);
        e->crc = le32(h + 16);
        e->csize = le32(h + 20);
        e->usize = le32(h + 24);
        e->lho = le32(h + 42);
        e->name_bad = nl == 0 || nl >= sizeof e->name;
        memcpy(e->name, h + 46, nl < sizeof e->name ? nl : sizeof e->name - 1);
        for (int k = 0; k < nl && k < (int)sizeof e->name; k++)
            if (!h[46 + k]) e->name_bad = 1;  // an embedded NUL would hide the rest of the name
        // zip64 extra field: the values that are 0xffffffff in the header, in this order
        for (uint64_t x = 0; x + 4 <= xl;) {
            const uint8_t *f = h + 46 + nl + x;
            uint16_t id = le16(f), sz = le16(f + 2);
            if (x + 4 + sz > xl) break;
            if (id == 1) {
                const uint8_t *v = f + 4, *end = f + 4 + sz;
                if (e->usize == 0xffffffff && v + 8 <= end) e->usize = le64(v), v += 8;
                if (e->csize == 0xffffffff && v + 8 <= end) e->csize = le64(v), v += 8;
                if (e->lho == 0xffffffff && v + 8 <= end) e->lho = le64(v), v += 8;
            }
            x += 4 + sz;
        }
        z->n++;
        p += 46 + nl + xl + cl;
    }
    free(cd);
    return 0;
}

void zip_close(struct zip *z) {
    free(z->e);
    z->e = NULL;
    z->n = 0;
}

const struct zentry *zip_find(const struct zip *z, const char *name) {
    for (int i = 0; i < z->n; i++)
        if (!z->e[i].name_bad && !strcmp(z->e[i].name, name)) return &z->e[i];
    return NULL;
}

// Where an entry's data starts (after its local header), or -1.
static int64_t zip_data_offset(const struct zip *z, const struct zentry *e) {
    uint8_t lh[30];
    if (e->lho + 30 > z->size || pread_all(z->fd, lh, 30, e->lho) || le32(lh) != 0x04034b50) return -1;
    uint64_t d = e->lho + 30 + le16(lh + 26) + le16(lh + 28);
    if (d > z->size || e->csize > z->size - d) return -1;
    return (int64_t)d;
}

static ssize_t zs_read(struct src *base, uint8_t *buf, size_t n) {
    struct zstream *s = (struct zstream *)base;
    if (s->failed) return -1;
    if (s->done) return 0;
    if (n > s->uleft) n = s->uleft;
    if (!n) {
        // All declared bytes delivered: a deflate stream must end here, and the CRC must match.
        if (s->method == 8 && !s->zend) {
            uint8_t extra;
            s->zs.next_out = &extra;
            s->zs.avail_out = 1;
            for (;;) {
                if (!s->zs.avail_in && s->cleft) {
                    size_t k = s->cleft < sizeof s->in ? s->cleft : sizeof s->in;
                    if (pread_all(s->fd, s->in, k, s->off)) goto bad;
                    s->off += k;
                    s->cleft -= k;
                    s->zs.next_in = s->in;
                    s->zs.avail_in = k;
                }
                int r = inflate(&s->zs, Z_NO_FLUSH);
                if (r == Z_STREAM_END && s->zs.avail_out == 1) break;
                if (r != Z_OK || s->zs.avail_out == 0 || (!s->zs.avail_in && !s->cleft)) goto bad;
            }
        }
        if (s->crc != s->want_crc) goto bad;
        s->done = 1;
        return 0;
    }
    if (s->method == 0) {
        if (pread_all(s->fd, buf, n, s->off)) goto bad;
        s->off += n;
        s->uleft -= n;
        s->crc = crc32(s->crc, buf, n);
        return n;
    }
    s->zs.next_out = buf;
    s->zs.avail_out = n;
    while (s->zs.avail_out == n) {
        if (!s->zs.avail_in && s->cleft) {
            size_t k = s->cleft < sizeof s->in ? s->cleft : sizeof s->in;
            if (pread_all(s->fd, s->in, k, s->off)) goto bad;
            s->off += k;
            s->cleft -= k;
            s->zs.next_in = s->in;
            s->zs.avail_in = k;
        }
        int r = inflate(&s->zs, Z_NO_FLUSH);
        if (r == Z_STREAM_END) {
            s->zend = 1;
            break;
        }
        if (r != Z_OK && !(r == Z_BUF_ERROR && s->zs.avail_in)) goto bad;
        if (!s->zs.avail_in && !s->cleft && s->zs.avail_out == n) goto bad;  // ran out of input
    }
    size_t got = n - s->zs.avail_out;
    if (s->zend && got < n && s->uleft != got) goto bad;  // the stream ended before its declared size
    s->uleft -= got;
    s->crc = crc32(s->crc, buf, got);
    return got;
bad:
    s->failed = 1;
    return -1;
}

int zs_open(struct zstream *s, const struct zip *z, const struct zentry *e) {
    memset(s, 0, sizeof *s);
    s->base.read = zs_read;
    s->fd = z->fd;
    int64_t d = zip_data_offset(z, e);
    if (d < 0 || (e->method != 0 && e->method != 8) || (e->flags & 1)) return -1;  // encrypted: refused
    if (e->method == 0 && e->csize != e->usize) return -1;
    s->off = d;
    s->cleft = e->csize;
    s->uleft = e->usize;
    s->method = e->method;
    s->want_crc = e->crc;
    s->crc = crc32(0, NULL, 0);
    if (e->method == 8) {
        if (inflateInit2(&s->zs, -15) != Z_OK) return -1;
        s->zinit = 1;
    }
    return 0;
}

void zs_close(struct zstream *s) {
    if (s->zinit) inflateEnd(&s->zs);
    s->zinit = 0;
}

// Read a whole (small) entry. Returns malloc'd data, NUL-terminated, or NULL.
uint8_t *zip_read_all(const struct zip *z, const struct zentry *e, uint64_t max, size_t *len) {
    if (e->usize > max) return NULL;
    struct zstream s;
    if (zs_open(&s, z, e)) return NULL;
    uint8_t *b = malloc(e->usize + 1);
    ssize_t r = b ? src_read_full(&s.base, b, e->usize) : -1;
    uint8_t end;
    if (r != (ssize_t)e->usize || s.base.read(&s.base, &end, 1) != 0) {
        zs_close(&s);
        free(b);
        return NULL;
    }
    zs_close(&s);
    b[e->usize] = 0;
    if (len) *len = e->usize;
    return b;
}

// ------------------------------------------------------------------ xz (LZMA SDK) and brotli
struct xzs {
    struct src base;
    struct src *in;
    CXzUnpacker u;
    uint8_t buf[1 << 16];
    size_t pos, len;
    int in_end, finished, failed;
};

static ssize_t xz_read(struct src *base, uint8_t *out, size_t n) {
    struct xzs *x = (struct xzs *)base;
    if (x->failed) return -1;
    for (;;) {
        if (x->finished) return 0;
        if (x->pos == x->len && !x->in_end) {
            ssize_t r = x->in->read(x->in, x->buf, sizeof x->buf);
            if (r < 0) {
                x->failed = 1;
                return -1;
            }
            x->pos = 0;
            x->len = r;
            if (!r) x->in_end = 1;
        }
        SizeT dl = n, sl = x->len - x->pos;
        ECoderStatus st;
        SRes res = XzUnpacker_Code(&x->u, out, &dl, x->buf + x->pos, &sl, x->in_end, CODER_FINISH_ANY, &st);
        x->pos += sl;
        if (res != SZ_OK) {
            x->failed = 1;
            return -1;
        }
        if (dl) return dl;
        if (x->in_end && x->pos == x->len) {
            if (!XzUnpacker_IsStreamWasFinished(&x->u)) {
                x->failed = 1;
                return -1;
            }
            x->finished = 1;
        } else if (!sl && st != CODER_STATUS_NEEDS_MORE_INPUT && x->pos < x->len) {
            x->failed = 1;  // no progress
            return -1;
        }
    }
}

struct src *xz_stream_new(struct src *in) {
    static int tables;
    if (!tables) {
        CrcGenerateTable();
        Crc64GenerateTable();
        tables = 1;
    }
    struct xzs *x = calloc(1, sizeof *x);
    if (!x) return NULL;
    x->base.read = xz_read;
    x->in = in;
    XzUnpacker_Construct(&x->u, &g_Alloc);
    XzUnpacker_Init(&x->u);
    return &x->base;
}

void xz_stream_free(struct src *s) {
    if (!s) return;
    struct xzs *x = (struct xzs *)s;
    XzUnpacker_Free(&x->u);
    free(x);
}

struct brs {
    struct src base;
    struct src *in;
    BrotliDecoderState *st;
    uint8_t buf[1 << 16];
    const uint8_t *next;
    size_t avail;
    int in_end, finished, failed;
};

static ssize_t br_read(struct src *base, uint8_t *out, size_t n) {
    struct brs *b = (struct brs *)base;
    if (b->failed) return -1;
    if (b->finished) return 0;
    for (;;) {
        if (!b->avail && !b->in_end) {
            ssize_t r = b->in->read(b->in, b->buf, sizeof b->buf);
            if (r < 0) {
                b->failed = 1;
                return -1;
            }
            b->next = b->buf;
            b->avail = r;
            if (!r) b->in_end = 1;
        }
        size_t ao = n;
        uint8_t *no = out;
        BrotliDecoderResult r = BrotliDecoderDecompressStream(b->st, &b->avail, &b->next, &ao, &no, NULL);
        size_t got = n - ao;
        if (r == BROTLI_DECODER_RESULT_ERROR) {
            b->failed = 1;
            return -1;
        }
        if (r == BROTLI_DECODER_RESULT_SUCCESS) {
            // Nothing may follow the stream.
            if (b->avail) {
                b->failed = 1;
                return -1;
            }
            b->finished = 1;
            return got;
        }
        if (got) return got;
        if (r == BROTLI_DECODER_RESULT_NEEDS_MORE_INPUT && b->in_end) {
            b->failed = 1;  // truncated
            return -1;
        }
    }
}

struct src *br_stream_new(struct src *in) {
    struct brs *b = calloc(1, sizeof *b);
    if (!b) return NULL;
    b->base.read = br_read;
    b->in = in;
    b->st = BrotliDecoderCreateInstance(NULL, NULL, NULL);
    if (!b->st) {
        free(b);
        return NULL;
    }
    return &b->base;
}

void br_stream_free(struct src *s) {
    if (!s) return;
    struct brs *b = (struct brs *)s;
    BrotliDecoderDestroyInstance(b->st);
    free(b);
}

// ------------------------------------------------------------------ tar
static uint64_t tar_num(const uint8_t *f, int n, int *bad) {
    if (f[0] & 0x80) {  // base-256 (GNU, for sizes over 8 GiB)
        uint64_t v = f[0] & 0x7f;
        for (int i = 1; i < n; i++) {
            if (v >> 56) *bad = 1;
            v = v << 8 | f[i];
        }
        return v;
    }
    uint64_t v = 0;
    int i = 0;
    while (i < n && f[i] == ' ') i++;
    for (; i < n && f[i] >= '0' && f[i] <= '7'; i++) {
        if (v >> 60) *bad = 1;
        v = v * 8 + (f[i] - '0');
    }
    for (; i < n; i++)
        if (f[i] != ' ' && f[i] != 0) *bad = 1;
    return v;
}

// The entry's data, bounded to its size, for the callback.
struct tar_body {
    struct src base;
    struct src *in;
    uint64_t left;
};

static ssize_t tb_read(struct src *base, uint8_t *buf, size_t n) {
    struct tar_body *b = (struct tar_body *)base;
    if (!b->left) return 0;
    if (n > b->left) n = b->left;
    ssize_t r = b->in->read(b->in, buf, n);
    if (r <= 0) return -1;  // a tar entry may not end early
    b->left -= r;
    return r;
}

static int skip(struct src *s, uint64_t n) {
    uint8_t buf[8192];
    while (n) {
        size_t k = n < sizeof buf ? n : sizeof buf;
        if (src_read_full(s, buf, k) != (ssize_t)k) return -1;
        n -= k;
    }
    return 0;
}

static char *read_small(struct src *s, uint64_t size, uint64_t max) {
    if (size > max) return NULL;
    char *b = malloc(size + 1);
    if (!b || src_read_full(s, b, size) != (ssize_t)size) {
        free(b);
        return NULL;
    }
    b[size] = 0;
    uint64_t pad = (512 - size % 512) % 512;
    if (skip(s, pad)) {
        free(b);
        return NULL;
    }
    return b;
}

int tar_walk(struct src *in, int (*cb)(void *arg, const char *path, char type, uint64_t size, struct src *body),
             void *arg, char *why, size_t wl) {
    uint8_t h[512];
    char *longname = NULL;
    int64_t pax_size = -1;
    int zeros = 0;
    for (;;) {
        ssize_t r = src_read_full(in, h, 512);
        if (r == 0 && zeros) break;  // some writers end after one zero block
        if (r != 512) {
            free(longname);
            snprintf(why, wl, r < 0 ? "the archive's data is damaged (decompression failed)" : "the tar archive ends early");
            return -1;
        }
        int allzero = 1;
        for (int i = 0; i < 512 && allzero; i++) allzero = !h[i];
        if (allzero) {
            if (++zeros == 2) break;
            continue;
        }
        zeros = 0;
        int bad = 0;
        uint64_t sum = tar_num(h + 148, 8, &bad), calc = 0;
        for (int i = 0; i < 512; i++) calc += (i >= 148 && i < 156) ? ' ' : h[i];
        if (bad || sum != calc) {
            free(longname);
            snprintf(why, wl, "the tar archive is damaged (header checksum)");
            return -1;
        }
        uint64_t size = tar_num(h + 124, 12, &bad);
        if (bad) {
            free(longname);
            snprintf(why, wl, "the tar archive is damaged (size field)");
            return -1;
        }
        char type = h[156] ? (char)h[156] : '0';
        if (type == 'L') {  // GNU long name: the next header's name
            free(longname);
            longname = read_small(in, size, 4096);
            if (!longname) {
                snprintf(why, wl, "the tar archive is damaged (long name)");
                return -1;
            }
            continue;
        }
        if (type == 'x' || type == 'g') {  // pax: path and size records apply to the next entry (x only)
            char *pax = read_small(in, size, 1 << 20);
            if (!pax) {
                free(longname);
                snprintf(why, wl, "the tar archive is damaged (pax header)");
                return -1;
            }
            for (char *p = pax; type == 'x' && *p;) {
                char *sp = strchr(p, ' ');
                long len = strtol(p, NULL, 10);
                if (!sp || len <= 0 || p + len > pax + size) break;
                char *kv = sp + 1, *end = p + len - 1;  // the record ends with \n
                char *eq = memchr(kv, '=', end - kv);
                if (eq) {
                    *end = 0;
                    *eq = 0;
                    if (!strcmp(kv, "path")) {
                        free(longname);
                        longname = strdup(eq + 1);
                    } else if (!strcmp(kv, "size")) {
                        pax_size = strtoll(eq + 1, NULL, 10);
                    }
                }
                p += len;
            }
            free(pax);
            continue;
        }
        if (pax_size >= 0) size = pax_size;
        char path[4200];
        if (longname) {
            snprintf(path, sizeof path, "%s", longname);
        } else {
            char name[101], prefix[156];
            memcpy(name, h, 100);
            name[100] = 0;
            prefix[0] = 0;
            if (!memcmp(h + 257, "ustar", 5)) {
                memcpy(prefix, h + 345, 155);
                prefix[155] = 0;
            }
            snprintf(path, sizeof path, "%s%s%s", prefix, prefix[0] ? "/" : "", name);
        }
        free(longname);
        longname = NULL;
        pax_size = -1;
        struct tar_body body = {.base.read = tb_read, .in = in, .left = size};
        // Only regular files carry data that matters; directories, links and devices are reported with size 0.
        int has_data = type == '0' || type == '7';
        int rc = cb(arg, path, has_data ? '0' : type, has_data ? size : 0, &body.base);
        if (rc < 0) {
            snprintf(why, wl, "stopped at %s", path);
            return -1;
        }
        if (skip(in, body.left) || skip(in, (512 - size % 512) % 512)) {
            snprintf(why, wl, "the tar archive ends early (in %s)", path);
            return -1;
        }
    }
    free(longname);
    return 0;
}
