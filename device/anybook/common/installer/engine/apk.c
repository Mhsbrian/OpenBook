// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// What the bring-your-own GApps step records about each APK (ANAL-211, gapps.c): its package name, version, SDK
// levels and shared user ID from the binary AndroidManifest.xml, its native libraries' ABIs (and the ELF machine
// of every x86_64 library), and the certificate that signs it, as `apksigner verify --print-certs` reports it: the
// first certificate of the signer from the APK Signature Scheme v3.1, v3 or v2 block (the one whose SDK range covers
// this system), else from the v1 JAR signature (PKCS #7). Signatures are not verified here: PackageManager does that
// when it scans the app. The input is untrusted; every offset is checked against its container.
#include "archive.h"

#include <stdlib.h>
#include <string.h>

static uint16_t le16(const uint8_t *p) { return p[0] | p[1] << 8; }
static uint32_t le32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t le64(const uint8_t *p) { return le32(p) | (uint64_t)le32(p + 4) << 32; }

int elf_machine(const uint8_t *h, size_t n, int *cls) {
    *cls = 0;
    if (n < 20 || memcmp(h, "\x7f" "ELF", 4) || h[5] != 1) return 0;  // little-endian only
    *cls = h[4];
    return le16(h + 18);
}

// ------------------------------------------------------------------ binary XML (AndroidManifest.xml)
#define R_NAME 0x01010003
#define R_SHARED_USER 0x0101000b
#define R_HAS_CODE 0x0101000c
#define R_MIN_SDK 0x0101020c
#define R_VERSION_CODE 0x0101021b
#define R_VERSION_NAME 0x0101021c
#define R_TARGET_SDK 0x01010270
#define R_VERSION_MAJOR 0x01010576

struct pool {
    const uint8_t *base;  // the string pool chunk
    uint32_t size, count, flags, strings_start;
    const uint8_t *offsets;
};

// String i of the pool, as ASCII-safe UTF-8 in out ("" if out of range).
static void pool_str(const struct pool *p, uint32_t i, char *out, size_t on) {
    out[0] = 0;
    if (!p->base || i >= p->count || 28 + 4ull * p->count > p->size) return;
    uint64_t off = (uint64_t)p->strings_start + le32(p->offsets + 4 * i);
    if (off + 2 > p->size) return;
    const uint8_t *s = p->base + off, *end = p->base + p->size;
    size_t o = 0;
    if (p->flags & (1 << 8)) {  // UTF-8: char count, byte count, bytes
        int k = (s[0] & 0x80) ? 2 : 1;
        if (s + k >= end) return;
        const uint8_t *b = s + k;
        uint32_t blen = b[0];
        if (blen & 0x80) {
            if (b + 1 >= end) return;
            blen = (blen & 0x7f) << 8 | b[1];
            b += 2;
        } else {
            b += 1;
        }
        if (b + blen > end) return;
        for (uint32_t j = 0; j < blen && o + 1 < on; j++) out[o++] = b[j] >= 0x20 && b[j] < 0x7f ? b[j] : '?';
    } else {  // UTF-16
        uint32_t len = le16(s);
        const uint8_t *c = s + 2;
        if (len & 0x8000) {
            if (s + 4 > end) return;
            len = (len & 0x7fff) << 16 | le16(s + 2);
            c = s + 4;
        }
        if (c + 2ull * len > end) return;
        for (uint32_t j = 0; j < len && o + 1 < on; j++) {
            uint16_t ch = le16(c + 2 * j);
            out[o++] = ch >= 0x20 && ch < 0x7f ? (char)ch : '?';
        }
    }
    out[o] = 0;
}

static int axml_parse(const uint8_t *x, size_t n, struct apk_info *a) {
    if (n < 8 || le16(x) != 0x0003 || le32(x + 4) > n) {
        snprintf(a->why, sizeof a->why, "AndroidManifest.xml is not binary XML");
        return -1;
    }
    n = le32(x + 4);
    struct pool pool = {0};
    const uint8_t *resmap = NULL;
    uint32_t nres = 0;
    int depth = 0, seen_manifest = 0;
    uint32_t vc_low = 0, vc_high = 0;
    a->has_code = 1;
    for (size_t off = le16(x + 2); off + 8 <= n;) {
        const uint8_t *c = x + off;
        uint16_t type = le16(c), hsize = le16(c + 2);
        uint32_t size = le32(c + 4);
        if (size < 8 || size > n - off || hsize > size) break;
        if (type == 0x0001 && size >= 28) {
            pool.base = c;
            pool.size = size;
            pool.count = le32(c + 8);
            pool.flags = le32(c + 16);
            pool.strings_start = le32(c + 20);
            pool.offsets = c + hsize;
            if ((uint64_t)hsize + 4ull * pool.count > size) pool.base = NULL;
        } else if (type == 0x0180) {
            resmap = c + hsize;
            nres = (size - hsize) / 4;
        } else if (type == 0x0102 && size >= hsize + 20) {
            depth++;
            const uint8_t *ext = c + hsize;
            char ename[64];
            pool_str(&pool, le32(ext + 4), ename, sizeof ename);
            uint16_t astart = le16(ext + 8), asize = le16(ext + 10), acount = le16(ext + 12);
            if (asize < 20 || (uint64_t)hsize + astart + (uint64_t)asize * acount > size) {
                snprintf(a->why, sizeof a->why, "AndroidManifest.xml: damaged element");
                return -1;
            }
            int is_manifest = depth == 1 && !strcmp(ename, "manifest");
            int is_sdk = depth == 2 && !strcmp(ename, "uses-sdk");
            int is_app = depth == 2 && !strcmp(ename, "application");
            if (depth == 2 && (!strcmp(ename, "uses-permission") || !strcmp(ename, "uses-permission-sdk-23"))) a->nperms++;
            if (is_manifest) seen_manifest = 1;
            for (int i = 0; i < acount && (is_manifest || is_sdk || is_app); i++) {
                const uint8_t *at = ext + astart + (size_t)i * asize;
                uint32_t name = le32(at + 4), raw = le32(at + 8), data = le32(at + 16);
                uint8_t dtype = at[15];
                uint32_t rid = resmap && name < nres ? le32(resmap + 4 * name) : 0;
                char aname[64], sval[160] = "";
                pool_str(&pool, name, aname, sizeof aname);
                if (dtype == 0x03) pool_str(&pool, raw != 0xffffffff ? raw : data, sval, sizeof sval);
                int is_int = dtype >= 0x10 && dtype <= 0x1f;
                if (is_manifest) {
                    if (!rid && !strcmp(aname, "package")) snprintf(a->package, sizeof a->package, "%s", sval);
                    else if (!rid && !strcmp(aname, "split")) snprintf(a->split, sizeof a->split, "%s", sval);
                    else if (rid == R_VERSION_CODE && is_int) vc_low = data;
                    else if (rid == R_VERSION_MAJOR && is_int) vc_high = data;
                    else if (rid == R_VERSION_NAME) {
                        if (dtype == 0x03) snprintf(a->version_name, sizeof a->version_name, "%s", sval);
                        else if (dtype == 0x01) snprintf(a->version_name, sizeof a->version_name, "@0x%08x", data);
                    } else if (rid == R_SHARED_USER && dtype == 0x03) {
                        snprintf(a->shared_user, sizeof a->shared_user, "%s", sval);
                    }
                } else if (is_sdk) {
                    int v = is_int ? (int)data : dtype == 0x03 ? -1 : 0;  // a string here is a preview codename
                    if (rid == R_MIN_SDK) a->min_sdk = v;
                    else if (rid == R_TARGET_SDK) a->target_sdk = v;
                } else if (is_app && rid == R_HAS_CODE && dtype == 0x12) {
                    a->has_code = data != 0;
                }
            }
        } else if (type == 0x0103) {
            depth--;
        }
        off += size;
    }
    a->version_code = (long long)vc_high << 32 | vc_low;
    if (!seen_manifest || !a->package[0]) {
        snprintf(a->why, sizeof a->why, "AndroidManifest.xml has no <manifest package>");
        return -1;
    }
    return 0;
}

// ------------------------------------------------------------------ DER (certificates)
// One TLV at *p; returns 0 and advances *p past it, value in [*v, *v + *vl).
static int der(const uint8_t **p, const uint8_t *end, uint8_t *tag, const uint8_t **v, size_t *vl) {
    const uint8_t *q = *p;
    if (end - q < 2) return -1;
    *tag = *q++;
    size_t len = *q++;
    if (len & 0x80) {
        int k = len & 0x7f;
        if (k < 1 || k > 4 || end - q < k) return -1;
        len = 0;
        while (k--) len = len << 8 | *q++;
    }
    if ((size_t)(end - q) < len) return -1;
    *v = q;
    *vl = len;
    *p = q + len;
    return 0;
}

static void subject_of(const uint8_t *cert, size_t n, char *out, size_t on) {
    out[0] = 0;
    const uint8_t *p = cert, *end = cert + n, *v;
    size_t vl;
    uint8_t t;
    if (der(&p, end, &t, &v, &vl) || t != 0x30) return;  // Certificate
    p = v;
    end = v + vl;
    if (der(&p, end, &t, &v, &vl) || t != 0x30) return;  // TBSCertificate
    const uint8_t *q = v, *qe = v + vl;
    int field = 0;
    const uint8_t *subj = NULL;
    size_t subjl = 0;
    while (q < qe) {
        if (der(&q, qe, &t, &v, &vl)) return;
        if (field == 0 && t == 0xa0) continue;  // [0] version
        field++;  // 1 serial, 2 signature, 3 issuer, 4 validity, 5 subject
        if (field == 5) {
            subj = v;
            subjl = vl;
            break;
        }
    }
    if (!subj) return;
    struct {
        const char *k;
        char v[96];
    } rdn[16];
    int nr = 0;
    const uint8_t *s = subj, *se = subj + subjl;
    while (s < se && nr < 16) {
        const uint8_t *setv, *seqv, *oidv, *valv;
        size_t setl, seql, oidl, vall;
        uint8_t t1, t2, t3, t4;
        if (der(&s, se, &t1, &setv, &setl) || t1 != 0x31) return;
        const uint8_t *a = setv;
        if (der(&a, setv + setl, &t2, &seqv, &seql) || t2 != 0x30) return;
        const uint8_t *b = seqv;
        if (der(&b, seqv + seql, &t3, &oidv, &oidl) || t3 != 0x06 || der(&b, seqv + seql, &t4, &valv, &vall)) return;
        static const struct {
            uint8_t last;
            const char *k;
        } names[] = {{3, "CN"}, {11, "OU"}, {10, "O"}, {7, "L"}, {8, "ST"}, {6, "C"}, {5, "SERIALNUMBER"}};
        const char *k = NULL;
        if (oidl == 3 && oidv[0] == 0x55 && oidv[1] == 0x04)
            for (size_t i = 0; i < ARRAY_LEN(names); i++)
                if (oidv[2] == names[i].last) k = names[i].k;
        if (!k) continue;
        rdn[nr].k = k;
        size_t o = 0;
        for (size_t i = 0; i < vall && o + 1 < sizeof rdn[nr].v; i++)
            rdn[nr].v[o++] = valv[i] >= 0x20 && valv[i] < 0x7f && valv[i] != ',' ? valv[i] : '?';
        rdn[nr].v[o] = 0;
        nr++;
    }
    // As apksigner and X500Principal print it: the last RDN first.
    size_t o = 0;
    for (int i = nr - 1; i >= 0 && o + 1 < on; i--)
        o += snprintf(out + o, on - o, "%s%s=%s", o ? ", " : "", rdn[i].k, rdn[i].v);
}

static void set_cert(struct apk_info *a, const char *scheme, const uint8_t *cert, size_t n) {
    snprintf(a->scheme, sizeof a->scheme, "%s", scheme);
    sha256_hex(cert, n, a->cert_sha256);
    subject_of(cert, n, a->cert_subject, sizeof a->cert_subject);
}

// A u32-length-prefixed field at *p within [*p, end).
static int lp32(const uint8_t **p, const uint8_t *end, const uint8_t **v, uint32_t *len) {
    if (end - *p < 4) return -1;
    uint32_t l = le32(*p);
    if ((uint64_t)(end - *p - 4) < l) return -1;
    *v = *p + 4;
    *len = l;
    *p += 4 + l;
    return 0;
}

// The first certificate of the signer of a v2 (v3 = 0) or v3/v3.1 block whose SDK range covers sdk.
static int scheme_cert(const uint8_t *val, uint32_t vlen, int v3, int sdk, const uint8_t **cert, uint32_t *clen) {
    const uint8_t *p = val, *end = val + vlen, *signers;
    uint32_t sl;
    if (lp32(&p, end, &signers, &sl)) return -1;
    for (const uint8_t *s = signers; s < signers + sl;) {
        const uint8_t *signer, *sd;
        uint32_t len, sdl;
        if (lp32(&s, signers + sl, &signer, &len)) return -1;
        const uint8_t *q = signer, *qe = signer + len;
        if (lp32(&q, qe, &sd, &sdl)) return -1;
        if (v3) {
            if (qe - q < 8) return -1;
            uint32_t mn = le32(q), mx = le32(q + 4);
            if ((uint32_t)sdk < mn || (uint32_t)sdk > mx) continue;
        }
        const uint8_t *d = sd, *de = sd + sdl, *digests, *certs, *c;
        uint32_t dl, cl, l;
        if (lp32(&d, de, &digests, &dl) || lp32(&d, de, &certs, &cl)) return -1;
        const uint8_t *cp = certs;
        if (lp32(&cp, certs + cl, &c, &l) || !l) return -1;
        *cert = c;
        *clen = l;
        return 0;
    }
    return -1;
}

static int signing_block_cert(int fd, uint64_t cd_off, struct apk_info *a, int sdk) {
    uint8_t foot[24];
    if (cd_off < 32 || pread_all(fd, foot, 24, cd_off - 24) || memcmp(foot + 8, "APK Sig Block 42", 16)) return -1;
    uint64_t bsize = le64(foot);
    if (bsize < 24 || bsize > 64 * MiB || bsize + 8 > cd_off) return -1;
    uint64_t start = cd_off - bsize - 8;
    uint8_t *b = malloc(bsize + 8);
    if (!b || pread_all(fd, b, bsize + 8, start) || le64(b) != bsize) {
        free(b);
        return -1;
    }
    const uint8_t *pairs = b + 8, *pend = b + bsize + 8 - 24;
    const uint8_t *v31 = NULL, *v3 = NULL, *v2 = NULL;
    uint32_t l31 = 0, l3 = 0, l2 = 0;
    for (const uint8_t *p = pairs; pend - p >= 12;) {
        uint64_t len = le64(p);
        if (len < 4 || len > (uint64_t)(pend - p - 8)) break;
        uint32_t id = le32(p + 8);
        const uint8_t *v = p + 12;
        uint32_t vl = (uint32_t)(len - 4);
        if (id == 0x1b93ad61) v31 = v, l31 = vl;
        else if (id == 0xf05368c0) v3 = v, l3 = vl;
        else if (id == 0x7109871a) v2 = v, l2 = vl;
        p += 8 + len;
    }
    const uint8_t *cert;
    uint32_t cl;
    int rc = -1;
    if (v31 && !scheme_cert(v31, l31, 1, sdk, &cert, &cl)) set_cert(a, "v3.1", cert, cl), rc = 0;
    else if (v3 && !scheme_cert(v3, l3, 1, sdk, &cert, &cl)) set_cert(a, "v3", cert, cl), rc = 0;
    else if (v2 && !scheme_cert(v2, l2, 0, sdk, &cert, &cl)) set_cert(a, "v2", cert, cl), rc = 0;
    free(b);
    return rc;
}

// v1: META-INF/<name>.RSA|.DSA|.EC, PKCS #7 SignedData: the first certificate of its [0] certificates.
static int v1_cert(const struct zip *z, struct apk_info *a) {
    for (int i = 0; i < z->n; i++) {
        const char *nm = z->e[i].name;
        size_t l = strlen(nm);
        if (z->e[i].name_bad || strncmp(nm, "META-INF/", 9) || strchr(nm + 9, '/')) continue;
        if (!(l > 4 && (!strcasecmp(nm + l - 4, ".RSA") || !strcasecmp(nm + l - 4, ".DSA"))) &&
            !(l > 3 && !strcasecmp(nm + l - 3, ".EC")))
            continue;
        size_t n;
        uint8_t *p7 = zip_read_all(z, &z->e[i], 4 * MiB, &n);
        if (!p7) continue;
        const uint8_t *p = p7, *end = p7 + n, *v;
        size_t vl;
        uint8_t t;
        int ok = 0;
        if (!der(&p, end, &t, &v, &vl) && t == 0x30) {  // ContentInfo
            const uint8_t *q = v, *qe = v + vl;
            if (!der(&q, qe, &t, &v, &vl) && t == 0x06 && !der(&q, qe, &t, &v, &vl) && t == 0xa0) {
                const uint8_t *r = v, *re = v + vl;
                if (!der(&r, re, &t, &v, &vl) && t == 0x30) {  // SignedData
                    const uint8_t *s = v, *se = v + vl;
                    // version, digestAlgorithms, encapContentInfo, then [0] certificates
                    for (int k = 0; k < 3 && !der(&s, se, &t, &v, &vl); k++) {}
                    const uint8_t *c0 = s;
                    if (!der(&s, se, &t, &v, &vl) && t == 0xa0) {
                        const uint8_t *c = v, *cstart = v;
                        if (!der(&c, v + vl, &t, &v, &vl) && t == 0x30) {
                            set_cert(a, "v1", cstart, c - cstart);
                            ok = 1;
                        }
                    }
                    (void)c0;
                }
            }
        }
        free(p7);
        if (ok) return 0;
    }
    return -1;
}

int apk_inspect(int fd, uint64_t size, struct apk_info *a) {
    memset(a, 0, sizeof *a);
    struct zip z;
    if (zip_open(&z, fd, size, a->why, sizeof a->why)) return -1;
    const struct zentry *m = zip_find(&z, "AndroidManifest.xml");
    size_t mlen;
    uint8_t *mx = m ? zip_read_all(&z, m, 16 * MiB, &mlen) : NULL;
    if (!mx) {
        snprintf(a->why, sizeof a->why, m ? "AndroidManifest.xml cannot be read" : "no AndroidManifest.xml");
        zip_close(&z);
        return -1;
    }
    int rc = axml_parse(mx, mlen, a);
    free(mx);
    if (rc) {
        zip_close(&z);
        return -1;
    }
    // Native libraries: lib/<abi>/<name>.so
    for (int i = 0; i < z.n; i++) {
        const struct zentry *e = &z.e[i];
        if (e->name_bad || strncmp(e->name, "lib/", 4)) continue;
        const char *abi = e->name + 4, *sl = strchr(abi, '/');
        if (!sl || sl == abi || (size_t)(sl - abi) >= sizeof a->abis[0]) continue;
        const char *file = sl + 1;
        size_t fl = strlen(file);
        if (!fl || strchr(file, '/') || fl < 4 || strcmp(file + fl - 3, ".so")) continue;
        char ab[16];
        snprintf(ab, sizeof ab, "%.*s", (int)(sl - abi), abi);
        int have = 0;
        for (int k = 0; k < a->nabis; k++)
            if (!strcmp(a->abis[k], ab)) have = 1;
        if (!have && a->nabis < APK_MAX_ABIS) snprintf(a->abis[a->nabis++], sizeof a->abis[0], "%s", ab);
        if (strcmp(ab, "x86_64")) continue;
        a->x86_64_libs++;
        struct zstream s;
        uint8_t h[64];
        int cls = 0, mach = 0;
        if (!zs_open(&s, &z, e)) {
            ssize_t r = src_read_full(&s.base, h, sizeof h);
            if (r > 0) mach = elf_machine(h, r, &cls);
            zs_close(&s);
        }
        if (mach != 62 || cls != 2) {
            if (!a->bad_elf) snprintf(a->bad_elf_name, sizeof a->bad_elf_name, "%s", e->name);
            a->bad_elf++;
        }
    }
    char sdk[16];
    prop_get("ro.build.version.sdk", sdk, sizeof sdk);
    int api = atoi(sdk) > 0 ? atoi(sdk) : GAPPS_SDK;
    if (signing_block_cert(fd, z.cd_offset, a, api)) v1_cert(&z, a);
    zip_close(&z);
    return 0;
}
