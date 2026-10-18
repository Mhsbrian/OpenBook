// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Archive and APK reading for the bring-your-own GApps step (ANAL-211): zipr.c and apk.c, used by gapps.c.
#pragma once
#include "common.h"

#include <sys/types.h>
#include <zlib.h>

// A pull stream: read() returns the number of bytes read, 0 at the end, -1 on an error.
struct src {
    ssize_t (*read)(struct src *s, uint8_t *buf, size_t n);
};
ssize_t src_read_full(struct src *s, void *buf, size_t n);  // < n only at the end

struct zentry {
    char name[512];
    int name_bad;  // empty, too long or with a NUL: never matched
    uint16_t method, flags;
    uint32_t crc;
    uint64_t csize, usize, lho;
};
struct zip {
    int fd;
    uint64_t size, cd_offset;
    int n;
    struct zentry *e;
};
int zip_open(struct zip *z, int fd, uint64_t size, char *why, size_t wl);
void zip_close(struct zip *z);
const struct zentry *zip_find(const struct zip *z, const char *name);
uint8_t *zip_read_all(const struct zip *z, const struct zentry *e, uint64_t max, size_t *len);

struct zstream {
    struct src base;
    int fd, method, zinit, zend, done, failed;
    uint64_t off, cleft, uleft;
    uint32_t crc, want_crc;
    z_stream zs;
    uint8_t in[1 << 16];
};
int zs_open(struct zstream *s, const struct zip *z, const struct zentry *e);
void zs_close(struct zstream *s);

struct src *xz_stream_new(struct src *in);
void xz_stream_free(struct src *s);
struct src *br_stream_new(struct src *in);
void br_stream_free(struct src *s);

// Calls cb for every entry: type '0' (a regular file, with its data in body), '5' (directory), or the tar type
// character of anything else ('1' hard link, '2' symlink, '3'/'4' devices, '6' FIFO...), with size 0. cb returns <0
// to stop.
int tar_walk(struct src *in, int (*cb)(void *arg, const char *path, char type, uint64_t size, struct src *body),
             void *arg, char *why, size_t wl);

// ------------------------------------------------------------------ APKs (apk.c)
#define APK_MAX_ABIS 8
struct apk_info {
    char package[160];
    char split[96];         // "" for a base APK
    long long version_code; // versionCodeMajor << 32 | versionCode
    char version_name[96];
    int min_sdk, target_sdk; // 0 if absent; -1 if a codename
    char shared_user[160];
    int has_code;            // <application android:hasCode>, default 1
    int nperms;              // <uses-permission> count
    char abis[APK_MAX_ABIS][16];
    int nabis;
    int x86_64_libs, bad_elf;      // lib/x86_64/*.so count, and how many are not ELF64 x86-64
    char bad_elf_name[160];
    char scheme[8];          // v3.1, v3, v2, v1
    char cert_sha256[65];    // the signer's certificate, as apksigner prints it
    char cert_subject[256];
    char why[200];           // why parsing failed
};
// 0: parsed (fields filled); -1: not a valid APK (why).
int apk_inspect(int fd, uint64_t size, struct apk_info *a);
// The ELF machine of a library: 62 x86-64, 183 AArch64, 40 ARM, 3 i386, 0 if not ELF; *cls: 1 = 32-bit, 2 = 64-bit.
int elf_machine(const uint8_t *h, size_t n, int *cls);
