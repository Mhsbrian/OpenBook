// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// UEFI boot entries through efivarfs (docs/installer.md S11): read the Boot#### variables and BootOrder, and create
// one Boot#### entry ("OpenBook" -> HD(partition)/\EFI\OpenBook\systemd-bootx64.efi) and add it to BootOrder: at
// the end, so the system that starts now stays the default and OpenBook is in the firmware's boot menu, or first
// only when the user agreed (set_default; owner decision 2026-10-17). Every other entry keeps its place. Nothing else
// is written: no other Boot#### entry, no BootNext, no Secure Boot or firmware setting.
//
// efivarfs file format: a 4-byte little-endian attribute word, then the variable's data; each write() replaces the
// whole variable. Boot#### and BootOrder live under the EFI global variable GUID, which efivarfs leaves removable
// (not immutable). The kernel since 6.0 (efivarfs) is the only interface: there is no efibootmgr on Android.
#include "common.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define EFI_GLOBAL "8be4df61-93ca-11d2-aa0d-00e098032b8c"
#define EFI_VARIABLE_NON_VOLATILE 0x1u
#define EFI_VARIABLE_BOOTSERVICE_ACCESS 0x2u
#define EFI_VARIABLE_RUNTIME_ACCESS 0x4u
#define LOAD_OPTION_ACTIVE 0x1u

static void var_path(char *out, size_t n, const char *name) {
    snprintf(out, n, "%s/%s-" EFI_GLOBAL, E.efivars_dir, name);
}

static int read_var(const char *name, uint32_t *attr, uint8_t **data, size_t *len) {
    char p[600];
    var_path(p, sizeof p, name);
    size_t n;
    char *raw = read_file(p, &n);
    if (!raw) return -1;
    if (n < 4) {
        free(raw);
        errno = EINVAL;
        return -1;
    }
    memcpy(attr, raw, 4);
    *len = n - 4;
    *data = malloc(*len ? *len : 1);
    memcpy(*data, raw + 4, *len);
    free(raw);
    return 0;
}

// One write() of attribute word + data, as efivarfs requires. excl: create a new variable only.
static int write_var(const char *name, uint32_t attr, const void *data, size_t len, int excl) {
    char p[600];
    var_path(p, sizeof p, name);
    int fd = open(p, O_WRONLY | O_CLOEXEC | (excl ? O_CREAT | O_EXCL : 0), 0644);
    if (fd < 0) return -1;
    uint8_t *buf = malloc(len + 4);
    memcpy(buf, &attr, 4);
    memcpy(buf + 4, data, len);
    ssize_t r = write(fd, buf, len + 4);
    int e = errno;
    free(buf);
    close(fd);
    if (r != (ssize_t)(len + 4)) {
        errno = r < 0 ? e : EIO;
        return -1;
    }
    return 0;
}

static size_t put_ucs2(uint8_t *o, const char *s) {
    size_t n = 0;
    for (; *s; s++) {
        o[n++] = (uint8_t)*s;
        o[n++] = 0;
    }
    o[n++] = 0;
    o[n++] = 0;
    return n;
}

// EFI_LOAD_OPTION: Attributes, FilePathListLength, Description (UCS-2), FilePathList:
// HD(partition number, start LBA, size LBA, GPT unique GUID, GPT) / File(path) / End.
static size_t make_load_option(uint8_t *o, const char *desc, uint32_t partnum, uint64_t start, uint64_t size,
                               const uint8_t guid[16], const char *path) {
    uint8_t dp[1024];
    size_t d = 0;
    dp[d++] = 0x04;  // media device path
    dp[d++] = 0x01;  // hard drive
    dp[d++] = 42;
    dp[d++] = 0;
    memcpy(dp + d, &partnum, 4);
    d += 4;
    memcpy(dp + d, &start, 8);
    d += 8;
    memcpy(dp + d, &size, 8);
    d += 8;
    memcpy(dp + d, guid, 16);
    d += 16;
    dp[d++] = 0x02;  // MBR type: GPT
    dp[d++] = 0x02;  // signature type: GUID
    size_t fstart = d;
    dp[d++] = 0x04;  // media device path
    dp[d++] = 0x04;  // file path
    d += 2;
    d += put_ucs2(dp + d, path);
    uint16_t flen = d - fstart;
    memcpy(dp + fstart + 2, &flen, 2);
    dp[d++] = 0x7F;  // end of hardware device path
    dp[d++] = 0xFF;
    dp[d++] = 0x04;
    dp[d++] = 0x00;
    size_t n = 0;
    uint32_t attrs = LOAD_OPTION_ACTIVE;
    memcpy(o + n, &attrs, 4);
    n += 4;
    uint16_t dplen = d;
    memcpy(o + n, &dplen, 2);
    n += 2;
    n += put_ucs2(o + n, desc);
    memcpy(o + n, dp, d);
    return n + d;
}

struct load_option {
    int num;
    uint32_t attrs;
    char desc[128];
    int hd;  // has a GPT hard-drive node
    uint32_t partnum;
    uint64_t start, size;
    char guid[37];
    char path[256];
};

static void parse_load_option(const uint8_t *b, size_t len, struct load_option *lo) {
    if (len < 6) return;
    memcpy(&lo->attrs, b, 4);
    uint16_t dplen;
    memcpy(&dplen, b + 4, 2);
    size_t i = 6, o = 0;
    while (i + 1 < len && (b[i] || b[i + 1])) {
        if (o + 1 < sizeof lo->desc) lo->desc[o++] = b[i + 1] ? '?' : (char)b[i];
        i += 2;
    }
    lo->desc[o] = 0;
    i += 2;
    size_t end = i + dplen <= len ? i + dplen : len;
    while (i + 4 <= end) {
        uint8_t t = b[i], st = b[i + 1];
        uint16_t nl;
        memcpy(&nl, b + i + 2, 2);
        if (nl < 4 || i + nl > end) break;
        if (t == 0x04 && st == 0x01 && nl >= 42 && b[i + 40] == 0x02) {
            lo->hd = 1;
            memcpy(&lo->partnum, b + i + 4, 4);
            memcpy(&lo->start, b + i + 8, 8);
            memcpy(&lo->size, b + i + 16, 8);
            guid_to_str(b + i + 24, lo->guid);
        } else if (t == 0x04 && st == 0x04) {
            size_t p = 0;
            for (size_t k = i + 4; k + 1 < i + nl && (b[k] || b[k + 1]) && p + 1 < sizeof lo->path; k += 2)
                lo->path[p++] = b[k + 1] ? '?' : (char)b[k];
            lo->path[p] = 0;
        } else if (t == 0x7F) {
            break;
        }
        i += nl;
    }
}

static int list_boot(struct load_option *out, int max) {
    DIR *d = opendir(E.efivars_dir);
    if (!d) return -1;
    struct dirent *e;
    int n = 0;
    while ((e = readdir(d)) && n < max) {
        unsigned num;
        char tail[64];
        if (strlen(e->d_name) != 8 + 1 + 36 || sscanf(e->d_name, "Boot%4X-%63s", &num, tail) != 2 ||
            strcmp(tail, EFI_GLOBAL) || strncmp(e->d_name, "Boot", 4))
            continue;
        char name[16];
        snprintf(name, sizeof name, "Boot%04X", num);
        if (strncmp(e->d_name, name, 8)) continue;  // e.g. BootNext, BootOrder
        uint32_t attr;
        uint8_t *data;
        size_t len;
        if (read_var(name, &attr, &data, &len)) continue;
        memset(&out[n], 0, sizeof out[n]);
        out[n].num = num;
        parse_load_option(data, len, &out[n]);
        free(data);
        n++;
    }
    closedir(d);
    return n;
}

// BootOrder's entries; 0 if there is none. -1 if it can't be read whole (an odd length, or more than max entries):
// the caller must then not write it, since writing back a shortened list would drop entries.
static int read_order(uint16_t *order, int max) {
    uint32_t attr;
    uint8_t *data;
    size_t len;
    if (read_var("BootOrder", &attr, &data, &len)) return errno == ENOENT ? 0 : -1;
    if (len % 2 || len / 2 > (size_t)max) {
        free(data);
        errno = len % 2 ? EINVAL : E2BIG;
        return -1;
    }
    int n = 0;
    for (size_t i = 0; i < len; i += 2) memcpy(&order[n++], data + i, 2);
    free(data);
    return n;
}

void nvram_json(struct jw *w) {
    jw_obj(w, "nvram");
    jw_bool(w, "available", E.efivars);
    jw_str(w, "dir", E.efivars_dir);
    if (E.efivars) {
        uint16_t order[256];
        int no = read_order(order, 256);
        jw_arr(w, "boot_order");
        for (int i = 0; i < no; i++) {
            char s[8];
            snprintf(s, sizeof s, "%04X", order[i]);
            jw_str(w, NULL, s);
        }
        jw_enda(w);
        uint32_t attr;
        uint8_t *data;
        size_t len;
        if (!read_var("BootCurrent", &attr, &data, &len) && len >= 2) {
            uint16_t cur;
            memcpy(&cur, data, 2);
            char s[8];
            snprintf(s, sizeof s, "%04X", cur);
            jw_str(w, "boot_current", s);
            free(data);
        } else {
            jw_null(w, "boot_current");
        }
        if (!read_var("BootNext", &attr, &data, &len) && len >= 2) {
            uint16_t nx;
            memcpy(&nx, data, 2);
            char s[8];
            snprintf(s, sizeof s, "%04X", nx);
            jw_str(w, "boot_next", s);
            free(data);
        } else {
            jw_null(w, "boot_next");
        }
        struct load_option lo[64];
        int n = list_boot(lo, 64);
        jw_arr(w, "entries");
        for (int i = 0; i < n; i++) {
            char s[8];
            snprintf(s, sizeof s, "%04X", lo[i].num);
            jw_obj(w, NULL);
            jw_str(w, "num", s);
            jw_str(w, "description", lo[i].desc);
            jw_bool(w, "active", lo[i].attrs & LOAD_OPTION_ACTIVE);
            if (lo[i].hd) {
                jw_int(w, "partition", lo[i].partnum);
                jw_str(w, "partuuid", lo[i].guid);
            }
            jw_str(w, "path", lo[i].path);
            jw_endo(w);
        }
        jw_enda(w);
    }
    jw_endo(w);
}

int nvram_add_entry(const char *desc, uint32_t partnum, uint64_t start_lba, uint64_t size_lba, const uint8_t guid[16],
                    const char *path, int set_first, struct nvram_result *res) {
    memset(res, 0, sizeof *res);
    res->num = -1;
    if (!E.efivars) {
        snprintf(res->why, sizeof res->why, "no efivarfs");
        return -1;
    }
    struct load_option lo[256];
    int n = list_boot(lo, 256);
    if (n < 0) {
        snprintf(res->why, sizeof res->why, "cannot list %s: %s", E.efivars_dir, strerror(errno));
        return -1;
    }
    // BootOrder first: if it can't be read whole, nothing is written.
    uint16_t order[256], neworder[257];
    int no = read_order(order, 256);
    if (no < 0) {
        snprintf(res->why, sizeof res->why, "cannot read BootOrder: %s", strerror(errno));
        return -1;
    }
    uint8_t opt[2048];
    size_t len = make_load_option(opt, desc, partnum, start_lba, size_lba, guid, path);
    uint32_t attr = EFI_VARIABLE_NON_VOLATILE | EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS;
    // The lowest number that is neither a Boot#### variable nor in BootOrder (a stale reference stays as it is).
    // O_EXCL: an existing variable is never overwritten; one we couldn't list makes us try the next number.
    char name[16];
    int num = -1;
    for (int c = 0; c <= 0xFFFF && num < 0; c++) {
        int used = 0;
        for (int i = 0; i < n && !used; i++) used = lo[i].num == c;
        for (int i = 0; i < no && !used; i++) used = order[i] == c;
        if (used) continue;
        snprintf(name, sizeof name, "Boot%04X", c);
        if (!write_var(name, attr, opt, len, 1)) num = c;
        else if (errno != EEXIST) {
            snprintf(res->why, sizeof res->why, "creating %s: %s", name, strerror(errno));
            return -1;
        }
    }
    if (num < 0) {
        snprintf(res->why, sizeof res->why, "no free Boot#### number");
        return -1;
    }
    res->num = num;
    // Read back what the firmware stored.
    uint32_t rattr;
    uint8_t *rdata = NULL;
    size_t rlen = 0;
    if (read_var(name, &rattr, &rdata, &rlen) || rlen != len || memcmp(rdata, opt, len)) {
        if (rdata) free(rdata);
        snprintf(res->why, sizeof res->why, "%s does not read back as written", name);
        return -1;
    }
    free(rdata);
    res->created = 1;
    // BootOrder: OpenBook first with consent (S11), else last; the other entries keep their order. Created if absent.
    int k = 0;
    if (set_first) neworder[k++] = num;
    for (int i = 0; i < no; i++) neworder[k++] = order[i];
    if (!set_first) neworder[k++] = num;
    if (write_var("BootOrder", attr, neworder, k * 2, 0) && (errno != ENOENT || write_var("BootOrder", attr, neworder, k * 2, 1))) {
        snprintf(res->why, sizeof res->why, "writing BootOrder: %s", strerror(errno));
        res->order = "failed";
        return -1;
    }
    uint16_t check[257];
    int nc = read_order(check, 257);
    if (nc != k || memcmp(check, neworder, k * 2)) {
        snprintf(res->why, sizeof res->why, "BootOrder does not read back as written");
        res->order = "failed";
        return -1;
    }
    res->order = set_first ? "first" : "last";
    return 0;
}
