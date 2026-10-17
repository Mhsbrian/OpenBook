// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Helpers: string builder, JSON writer and reader, SHA-256, CRC-32, GUIDs, I/O, logging, environment.
#include "common.h"

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/random.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#ifdef __ANDROID__
#include <sys/system_properties.h>
#endif

// ------------------------------------------------------------------ string builder
void sb_add(struct sb *b, const char *s, size_t n) {
    if (b->n + n + 1 > b->cap) {
        size_t cap = b->cap ? b->cap : 256;
        while (cap < b->n + n + 1) cap *= 2;
        char *p = realloc(b->p, cap);
        if (!p) abort();
        b->p = p;
        b->cap = cap;
    }
    memcpy(b->p + b->n, s, n);
    b->n += n;
    b->p[b->n] = 0;
}

void sb_puts(struct sb *b, const char *s) { sb_add(b, s, strlen(s)); }

void sb_printf(struct sb *b, const char *fmt, ...) {
    char tmp[1024];
    va_list ap;
    va_start(ap, fmt);
    int k = vsnprintf(tmp, sizeof tmp, fmt, ap);
    va_end(ap);
    if (k < 0) return;
    if ((size_t)k < sizeof tmp) {
        sb_add(b, tmp, k);
        return;
    }
    char *big = malloc(k + 1);
    if (!big) abort();
    va_start(ap, fmt);
    vsnprintf(big, k + 1, fmt, ap);
    va_end(ap);
    sb_add(b, big, k);
    free(big);
}

void sb_json_str(struct sb *b, const char *s) {
    if (!s) {
        sb_puts(b, "null");
        return;
    }
    sb_add(b, "\"", 1);
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
        if (*p == '"' || *p == '\\') {
            char e[2] = {'\\', (char)*p};
            sb_add(b, e, 2);
        } else if (*p == '\n') {
            sb_add(b, "\\n", 2);
        } else if (*p == '\r') {
            sb_add(b, "\\r", 2);
        } else if (*p == '\t') {
            sb_add(b, "\\t", 2);
        } else if (*p < 0x20) {
            sb_printf(b, "\\u%04x", *p);
        } else {
            sb_add(b, (const char *)p, 1);
        }
    }
    sb_add(b, "\"", 1);
}

void sb_free(struct sb *b) {
    free(b->p);
    b->p = NULL;
    b->n = b->cap = 0;
}

// ------------------------------------------------------------------ JSON writer
static void jw_key(struct jw *w, const char *key) {
    if (w->depth > 0 && w->need_comma[w->depth]) sb_add(&w->b, ",", 1);
    if (w->depth > 0) w->need_comma[w->depth] = 1;
    if (key) {
        sb_json_str(&w->b, key);
        sb_add(&w->b, ":", 1);
    }
}

void jw_obj(struct jw *w, const char *key) {
    jw_key(w, key);
    sb_add(&w->b, "{", 1);
    w->need_comma[++w->depth] = 0;
}

void jw_arr(struct jw *w, const char *key) {
    jw_key(w, key);
    sb_add(&w->b, "[", 1);
    w->need_comma[++w->depth] = 0;
}

void jw_endo(struct jw *w) {
    sb_add(&w->b, "}", 1);
    w->depth--;
}

void jw_enda(struct jw *w) {
    sb_add(&w->b, "]", 1);
    w->depth--;
}

void jw_end(struct jw *w) { jw_endo(w); }

void jw_str(struct jw *w, const char *key, const char *v) {
    jw_key(w, key);
    sb_json_str(&w->b, v);
}

void jw_int(struct jw *w, const char *key, long long v) {
    jw_key(w, key);
    sb_printf(&w->b, "%lld", v);
}

void jw_u64(struct jw *w, const char *key, uint64_t v) {
    jw_key(w, key);
    sb_printf(&w->b, "%llu", (unsigned long long)v);
}

void jw_dbl(struct jw *w, const char *key, double v, int decimals) {
    jw_key(w, key);
    sb_printf(&w->b, "%.*f", decimals, v);
}

void jw_bool(struct jw *w, const char *key, int v) {
    jw_key(w, key);
    sb_puts(&w->b, v ? "true" : "false");
}

void jw_null(struct jw *w, const char *key) {
    jw_key(w, key);
    sb_puts(&w->b, "null");
}

void jw_raw(struct jw *w, const char *key, const char *json) {
    jw_key(w, key);
    sb_puts(&w->b, json);
}

// ------------------------------------------------------------------ JSON reader
struct jp {
    const char *s;
    size_t i;
    char *err;
    size_t errlen;
    int depth;
};

static void jp_ws(struct jp *p) {
    while (p->s[p->i] == ' ' || p->s[p->i] == '\n' || p->s[p->i] == '\r' || p->s[p->i] == '\t') p->i++;
}

static struct jv *jv_new(int t) {
    struct jv *v = calloc(1, sizeof *v);
    if (!v) abort();
    v->t = t;
    return v;
}

static int jp_fail(struct jp *p, const char *what) {
    if (p->err && !p->err[0]) snprintf(p->err, p->errlen, "%s at offset %zu", what, p->i);
    return -1;
}

static void utf8_put(struct sb *b, unsigned cp) {
    char o[4];
    if (cp < 0x80) {
        o[0] = cp;
        sb_add(b, o, 1);
    } else if (cp < 0x800) {
        o[0] = 0xC0 | (cp >> 6);
        o[1] = 0x80 | (cp & 0x3F);
        sb_add(b, o, 2);
    } else if (cp < 0x10000) {
        o[0] = 0xE0 | (cp >> 12);
        o[1] = 0x80 | ((cp >> 6) & 0x3F);
        o[2] = 0x80 | (cp & 0x3F);
        sb_add(b, o, 3);
    } else {
        o[0] = 0xF0 | (cp >> 18);
        o[1] = 0x80 | ((cp >> 12) & 0x3F);
        o[2] = 0x80 | ((cp >> 6) & 0x3F);
        o[3] = 0x80 | (cp & 0x3F);
        sb_add(b, o, 4);
    }
}

static int jp_string(struct jp *p, char **out) {
    struct sb b = {0};
    if (p->s[p->i] != '"') return jp_fail(p, "expected string");
    p->i++;
    for (;;) {
        char c = p->s[p->i];
        if (!c) {
            sb_free(&b);
            return jp_fail(p, "unterminated string");
        }
        p->i++;
        if (c == '"') break;
        if (c != '\\') {
            sb_add(&b, &c, 1);
            continue;
        }
        char e = p->s[p->i++];
        switch (e) {
        case '"': case '\\': case '/': sb_add(&b, &e, 1); break;
        case 'n': sb_add(&b, "\n", 1); break;
        case 't': sb_add(&b, "\t", 1); break;
        case 'r': sb_add(&b, "\r", 1); break;
        case 'b': sb_add(&b, "\b", 1); break;
        case 'f': sb_add(&b, "\f", 1); break;
        case 'u': {
            unsigned cp = 0;
            for (int k = 0; k < 4; k++) {
                char h = p->s[p->i++];
                cp <<= 4;
                if (h >= '0' && h <= '9') cp |= h - '0';
                else if (h >= 'a' && h <= 'f') cp |= h - 'a' + 10;
                else if (h >= 'A' && h <= 'F') cp |= h - 'A' + 10;
                else {
                    sb_free(&b);
                    return jp_fail(p, "bad \\u escape");
                }
            }
            if (cp >= 0xD800 && cp < 0xDC00 && p->s[p->i] == '\\' && p->s[p->i + 1] == 'u') {
                unsigned lo = 0;
                p->i += 2;
                for (int k = 0; k < 4; k++) {
                    char h = p->s[p->i++];
                    lo <<= 4;
                    if (h >= '0' && h <= '9') lo |= h - '0';
                    else if (h >= 'a' && h <= 'f') lo |= h - 'a' + 10;
                    else if (h >= 'A' && h <= 'F') lo |= h - 'A' + 10;
                }
                cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
            }
            utf8_put(&b, cp);
            break;
        }
        default:
            sb_free(&b);
            return jp_fail(p, "bad escape");
        }
    }
    if (!b.p) sb_add(&b, "", 0);
    *out = b.p;
    return 0;
}

static struct jv *jp_value(struct jp *p) {
    jp_ws(p);
    if (++p->depth > 64) {
        jp_fail(p, "nesting too deep");
        return NULL;
    }
    struct jv *v = NULL;
    char c = p->s[p->i];
    if (c == '{') {
        v = jv_new(J_OBJ);
        p->i++;
        jp_ws(p);
        if (p->s[p->i] == '}') {
            p->i++;
            goto out;
        }
        for (;;) {
            char *k;
            jp_ws(p);
            if (jp_string(p, &k)) goto bad;
            jp_ws(p);
            if (p->s[p->i] != ':') {
                free(k);
                jp_fail(p, "expected ':'");
                goto bad;
            }
            p->i++;
            struct jv *x = jp_value(p);
            if (!x) {
                free(k);
                goto bad;
            }
            v->keys = realloc(v->keys, (v->len + 1) * sizeof *v->keys);
            v->items = realloc(v->items, (v->len + 1) * sizeof *v->items);
            v->keys[v->len] = k;
            v->items[v->len++] = x;
            jp_ws(p);
            if (p->s[p->i] == ',') {
                p->i++;
                continue;
            }
            if (p->s[p->i] == '}') {
                p->i++;
                break;
            }
            jp_fail(p, "expected ',' or '}'");
            goto bad;
        }
    } else if (c == '[') {
        v = jv_new(J_ARR);
        p->i++;
        jp_ws(p);
        if (p->s[p->i] == ']') {
            p->i++;
            goto out;
        }
        for (;;) {
            struct jv *x = jp_value(p);
            if (!x) goto bad;
            v->items = realloc(v->items, (v->len + 1) * sizeof *v->items);
            v->items[v->len++] = x;
            jp_ws(p);
            if (p->s[p->i] == ',') {
                p->i++;
                continue;
            }
            if (p->s[p->i] == ']') {
                p->i++;
                break;
            }
            jp_fail(p, "expected ',' or ']'");
            goto bad;
        }
    } else if (c == '"') {
        v = jv_new(J_STR);
        if (jp_string(p, &v->s)) goto bad;
    } else if (!strncmp(p->s + p->i, "true", 4)) {
        v = jv_new(J_BOOL);
        v->b = 1;
        p->i += 4;
    } else if (!strncmp(p->s + p->i, "false", 5)) {
        v = jv_new(J_BOOL);
        p->i += 5;
    } else if (!strncmp(p->s + p->i, "null", 4)) {
        v = jv_new(J_NULL);
        p->i += 4;
    } else if (c == '-' || (c >= '0' && c <= '9')) {
        char *end;
        v = jv_new(J_NUM);
        v->n = strtod(p->s + p->i, &end);
        p->i = end - p->s;
    } else {
        jp_fail(p, "unexpected character");
        return NULL;
    }
out:
    p->depth--;
    return v;
bad:
    json_free(v);
    return NULL;
}

struct jv *json_parse(const char *text, char *err, size_t errlen) {
    struct jp p = {.s = text, .err = err, .errlen = errlen};
    if (err && errlen) err[0] = 0;
    struct jv *v = jp_value(&p);
    if (!v) return NULL;
    jp_ws(&p);
    if (p.s[p.i]) {
        jp_fail(&p, "trailing data");
        json_free(v);
        return NULL;
    }
    return v;
}

void json_free(struct jv *v) {
    if (!v) return;
    for (int i = 0; i < v->len; i++) {
        if (v->keys) free(v->keys[i]);
        json_free(v->items[i]);
    }
    free(v->keys);
    free(v->items);
    free(v->s);
    free(v);
}

struct jv *jget(const struct jv *o, const char *key) {
    if (!o || o->t != J_OBJ) return NULL;
    for (int i = 0; i < o->len; i++)
        if (!strcmp(o->keys[i], key)) return o->items[i];
    return NULL;
}

const char *jstr(const struct jv *o, const char *key) {
    struct jv *v = jget(o, key);
    return v && v->t == J_STR ? v->s : NULL;
}

double jnum(const struct jv *o, const char *key, double def) {
    struct jv *v = jget(o, key);
    return v && v->t == J_NUM ? v->n : def;
}

int jbool(const struct jv *o, const char *key, int def) {
    struct jv *v = jget(o, key);
    return v && v->t == J_BOOL ? v->b : def;
}

// ------------------------------------------------------------------ SHA-256 (FIPS 180-4)
static const uint32_t K256[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98,
    0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8,
    0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819,
    0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
    0xc67178f2};

#define ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static void sha256_block(struct sha256 *c, const uint8_t *p) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++) w[i] = (uint32_t)p[4 * i] << 24 | p[4 * i + 1] << 16 | p[4 * i + 2] << 8 | p[4 * i + 3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = ROR(w[i - 15], 7) ^ ROR(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = ROR(w[i - 2], 17) ^ ROR(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = c->h[0], b = c->h[1], cc = c->h[2], d = c->h[3], e = c->h[4], f = c->h[5], g = c->h[6], h = c->h[7];
    for (int i = 0; i < 64; i++) {
        uint32_t S1 = ROR(e, 6) ^ ROR(e, 11) ^ ROR(e, 25);
        uint32_t ch = (e & f) ^ (~e & g);
        uint32_t t1 = h + S1 + ch + K256[i] + w[i];
        uint32_t S0 = ROR(a, 2) ^ ROR(a, 13) ^ ROR(a, 22);
        uint32_t mj = (a & b) ^ (a & cc) ^ (b & cc);
        uint32_t t2 = S0 + mj;
        h = g;
        g = f;
        f = e;
        e = d + t1;
        d = cc;
        cc = b;
        b = a;
        a = t1 + t2;
    }
    c->h[0] += a;
    c->h[1] += b;
    c->h[2] += cc;
    c->h[3] += d;
    c->h[4] += e;
    c->h[5] += f;
    c->h[6] += g;
    c->h[7] += h;
}

void sha256_init(struct sha256 *c) {
    static const uint32_t H0[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                                   0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    memcpy(c->h, H0, sizeof H0);
    c->len = 0;
    c->used = 0;
}

void sha256_update(struct sha256 *c, const void *data, size_t n) {
    const uint8_t *p = data;
    c->len += n;
    if (c->used) {
        size_t k = 64 - c->used < n ? 64 - c->used : n;
        memcpy(c->buf + c->used, p, k);
        c->used += k;
        p += k;
        n -= k;
        if (c->used == 64) {
            sha256_block(c, c->buf);
            c->used = 0;
        }
    }
    while (n >= 64) {
        sha256_block(c, p);
        p += 64;
        n -= 64;
    }
    if (n) {
        memcpy(c->buf, p, n);
        c->used = n;
    }
}

void sha256_final_hex(struct sha256 *c, char out[65]) {
    uint64_t bits = c->len * 8;
    uint8_t pad = 0x80;
    sha256_update(c, &pad, 1);
    uint8_t z = 0;
    while (c->used != 56) sha256_update(c, &z, 1);
    uint8_t L[8];
    for (int i = 0; i < 8; i++) L[i] = bits >> (56 - 8 * i);
    sha256_update(c, L, 8);
    for (int i = 0; i < 8; i++) snprintf(out + 8 * i, 9, "%08x", c->h[i]);
}

void sha256_hex(const void *data, size_t n, char out[65]) {
    struct sha256 c;
    sha256_init(&c);
    sha256_update(&c, data, n);
    sha256_final_hex(&c, out);
}

// ------------------------------------------------------------------ CRC-32 (GPT)
uint32_t crc32_buf(uint32_t crc, const void *data, size_t n) {
    static uint32_t table[256];
    static int init;
    if (!init) {
        for (uint32_t i = 0; i < 256; i++) {
            uint32_t c = i;
            for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & -(c & 1));
            table[i] = c;
        }
        init = 1;
    }
    const uint8_t *p = data;
    crc = ~crc;
    while (n--) crc = table[(crc ^ *p++) & 0xFF] ^ (crc >> 8);
    return ~crc;
}

// ------------------------------------------------------------------ GUIDs
void guid_to_str(const uint8_t g[16], char out[37]) {
    snprintf(out, 37, "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x", g[3], g[2], g[1], g[0],
             g[5], g[4], g[7], g[6], g[8], g[9], g[10], g[11], g[12], g[13], g[14], g[15]);
}

static int hexv(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

int guid_from_str(const char *s, uint8_t g[16]) {
    uint8_t b[16];
    int k = 0;
    for (const char *p = s; *p && k < 16; p++) {
        if (*p == '-') continue;
        int h = hexv(p[0]), l = hexv(p[1]);
        if (h < 0 || l < 0) return -1;
        b[k++] = h << 4 | l;
        p++;
    }
    if (k != 16 || strlen(s) != 36) return -1;
    // canonical text order -> GPT mixed endian
    g[0] = b[3]; g[1] = b[2]; g[2] = b[1]; g[3] = b[0];
    g[4] = b[5]; g[5] = b[4];
    g[6] = b[7]; g[7] = b[6];
    memcpy(g + 8, b + 8, 8);
    return 0;
}

void random_bytes(void *buf, size_t n) {
    size_t done = 0;
    while (done < n) {
        ssize_t r = getrandom((char *)buf + done, n - done, 0);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) abort();
        done += r;
    }
}

void guid_random(uint8_t g[16]) {
    uint8_t b[16];
    random_bytes(b, 16);
    b[6] = (b[6] & 0x0F) | 0x40;  // version 4 (text byte 6)
    b[8] = (b[8] & 0x3F) | 0x80;  // variant 1
    char s[37];
    snprintf(s, sizeof s, "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x", b[0], b[1], b[2],
             b[3], b[4], b[5], b[6], b[7], b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]);
    guid_from_str(s, g);
}

// ------------------------------------------------------------------ I/O
int pread_all(int fd, void *buf, size_t n, uint64_t off) {
    size_t done = 0;
    while (done < n) {
        ssize_t r = pread(fd, (char *)buf + done, n - done, off + done);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) {
            if (r == 0) errno = EIO;
            return -1;
        }
        done += r;
    }
    return 0;
}

int pwrite_all(int fd, const void *buf, size_t n, uint64_t off) {
    size_t done = 0;
    while (done < n) {
        ssize_t r = pwrite(fd, (const char *)buf + done, n - done, off + done);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) {
            if (r == 0) errno = EIO;
            return -1;
        }
        done += r;
    }
    return 0;
}

int zero_range(int fd, uint64_t off, uint64_t n) {
    static uint8_t zeros[1 << 20];
    for (uint64_t done = 0; done < n;) {
        size_t k = n - done < sizeof zeros ? n - done : sizeof zeros;
        if (pwrite_all(fd, zeros, k, off + done)) return -1;
        done += k;
    }
    return 0;
}

void trim(char *s) {
    size_t n = strlen(s);
    while (n && isspace((unsigned char)s[n - 1])) s[--n] = 0;
    size_t i = 0;
    while (s[i] && isspace((unsigned char)s[i])) i++;
    if (i) memmove(s, s + i, n - i + 1);
}

int read_text(const char *path, char *buf, size_t n) {
    buf[0] = 0;
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    ssize_t r = read(fd, buf, n - 1);
    close(fd);
    if (r < 0) return -1;
    buf[r] = 0;
    trim(buf);
    return 0;
}

char *read_file(const char *path, size_t *len) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return NULL;
    struct sb b = {0};
    char tmp[65536];
    for (;;) {
        ssize_t r = read(fd, tmp, sizeof tmp);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) break;
        sb_add(&b, tmp, r);
    }
    close(fd);
    if (!b.p) sb_add(&b, "", 0);
    if (len) *len = b.n;
    return b.p;
}

int write_file(const char *path, const void *data, size_t n) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0640);
    if (fd < 0) return -1;
    int rc = pwrite_all(fd, data, n, 0);
    if (!rc) rc = fsync(fd);
    close(fd);
    return rc;
}

void human_bytes(uint64_t n, char *out, size_t outlen) {
    const char *u[] = {"B", "kB", "MB", "GB", "TB"};
    double v = n;
    int i = 0;
    while (v >= 1000 && i < 4) {
        v /= 1000;
        i++;
    }
    if (i == 0) snprintf(out, outlen, "%llu B", (unsigned long long)n);
    else snprintf(out, outlen, v < 10 ? "%.1f %s" : "%.0f %s", v, u[i]);
}

void utc_stamp(char *out, size_t n, int compact) {
    time_t t = time(NULL);
    struct tm tm;
    gmtime_r(&t, &tm);
    strftime(out, n, compact ? "%Y%m%dT%H%M%SZ" : "%Y-%m-%dT%H:%M:%SZ", &tm);
}

double now_s(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}

// ------------------------------------------------------------------ logging and events
int g_event_fd = -1;
FILE *g_logfile;
struct sb g_install_log;

void logf_(const char *fmt, ...) {
    char msg[2048], line[2200];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof msg, fmt, ap);
    va_end(ap);
    time_t t = time(NULL);
    struct tm tm;
    gmtime_r(&t, &tm);
    char ts[16];
    strftime(ts, sizeof ts, "%H:%M:%S", &tm);
    snprintf(line, sizeof line, "%s %s", ts, msg);
    fprintf(stderr, "%s\n", line);
    if (g_logfile) {
        fprintf(g_logfile, "%s\n", line);
        fflush(g_logfile);
    }
    sb_puts(&g_install_log, line);
    sb_puts(&g_install_log, "\n");
    if (g_event_fd >= 0) {
        struct sb e = {0};
        sb_puts(&e, "{\"event\":\"log\",\"line\":");
        sb_json_str(&e, line);
        sb_puts(&e, "}");
        emit_event(e.p);
        sb_free(&e);
    }
}

void emit_event(const char *json) {
    if (g_event_fd < 0) return;
    size_t n = strlen(json);
    char *buf = malloc(n + 2);
    if (!buf) return;
    memcpy(buf, json, n);
    buf[n] = '\n';
    size_t done = 0;
    while (done < n + 1) {
        ssize_t r = write(g_event_fd, buf + done, n + 1 - done);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) break;
        done += r;
    }
    free(buf);
}

// ------------------------------------------------------------------ environment
struct env E;

void env_path(char *out, size_t n, const char *fmt, ...) {
    char rel[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(rel, sizeof rel, fmt, ap);
    va_end(ap);
    snprintf(out, n, "%s%s", E.root, rel);
}

int prop_get(const char *name, char *out, size_t n) {
    out[0] = 0;
#ifdef __ANDROID__
    char v[PROP_VALUE_MAX];
    if (__system_property_get(name, v) > 0) snprintf(out, n, "%s", v);
#else
    // Host tests: OPENBOOK_PROP_<name with . -> _>
    char key[160];
    snprintf(key, sizeof key, "OPENBOOK_PROP_%s", name);
    for (char *p = key; *p; p++)
        if (*p == '.') *p = '_';
    const char *v = getenv(key);
    if (v) snprintf(out, n, "%s", v);
#endif
    return 0;
}

void env_init(const char *root, const char *boot_part_uuid) {
    memset(&E, 0, sizeof E);
    E.root = root ? root : "";
    char v[96];
    if (boot_part_uuid && *boot_part_uuid) {
        snprintf(E.boot_part_uuid, sizeof E.boot_part_uuid, "%s", boot_part_uuid);
    } else {
        prop_get("ro.boot.boot_part_uuid", v, sizeof v);
        snprintf(E.boot_part_uuid, sizeof E.boot_part_uuid, "%s", v);
    }
    for (char *p = E.boot_part_uuid; *p; p++) *p = tolower((unsigned char)*p);
    prop_get("ro.boot.openbook.live", v, sizeof v);
    E.live = !strcmp(v, "1");
    prop_get("ro.boot.openbook.logs", v, sizeof v);
    E.logs_mode = !strcmp(v, "1");
    char path[512], buf[64] = "";
    env_path(path, sizeof path, "/sys/fs/selinux/enforce");
#ifdef __ANDROID__
    if (1) {  // selinuxfs is not readable from the daemon's domain
#else
    if (read_text(path, buf, sizeof buf)) {
#endif
        // No access to selinuxfs: init enforces unless the loader asked for permissive (userdebug only).
        prop_get("ro.boot.selinux", v, sizeof v);
        snprintf(E.selinux, sizeof E.selinux, "%s", !strcmp(v, "permissive") ? "permissive" : "enforcing");
    } else {
        snprintf(E.selinux, sizeof E.selinux, "%s", !strcmp(buf, "1") ? "enforcing" : "permissive");
    }
    env_path(path, sizeof path, "/sys/firmware/efi/efivars");
    struct statfs sf;
    E.efivars = !statfs(path, &sf) && sf.f_type == 0xde5e81e4;  // EFIVARFS_MAGIC
}
