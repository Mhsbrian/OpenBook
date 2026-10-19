// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// openbook-bootsync (ANAL-223, docs/installer.md section 2.5): keeps systemd-boot's copy of the boot images on the EFI
// system partition in step with Android's A/B slots.
//
// systemd-boot does not read boot_a/init_boot_a/vendor_boot_a: it loads the kernel, the two ramdisks and a bootconfig
// blob from the ESP (openbook/<slot>/), through one Boot Loader Spec entry per slot (loader/entries/openbook-<slot>.conf).
// update_engine writes the other slot's partitions; this tool then makes the ESP follow:
//
//   activate SLOT   SLOT's images are checked against SLOT's vbmeta (hash descriptors, digest, signing key), exported
//                   to openbook/SLOT/ with a bootconfig for SLOT, and entry openbook-SLOT+3.conf is written. Then
//                   loader.conf gets "preferred openbook-SLOT.conf" next to "default openbook-<current>.conf".
//                   systemd-boot boots the preferred entry while it has tries left and counts them down itself
//                   (+3 -> +2-1 -> ...). An entry with no tries left is skipped, so the default (the slot that last
//                   booted fine) starts again: that is the rollback. SLOT == the current slot cancels a pending switch.
//   mark-good       the running slot booted (markBootSuccessful): its entry loses its counter (openbook-SLOT.conf),
//                   it becomes the default, and after an update the other slot's entry goes (the virtual A/B merge
//                   overwrites that slot's system).
//   disable SLOT    SLOT's entry goes (setSlotAsUnbootable); never the running slot's.
//   status          read-only: both slots, the ESP, and the slot systemd-boot will start next.
//
// The boot control HAL (android.hardware.boot-service.openbook) runs it for setActiveBootSlot, markBootSuccessful and
// setSlotAsUnbootable. On a system without it (the first update onto an older OpenBook), scripts/g14-adb.sh runs the
// new image's copy once as root after update_engine finished.
//
// Every ESP change is crash-ordered (fat_replace and friends in the install engine's fat.c): new files and the new
// entry exist before loader.conf points at them, and each step ends with an fsync. Nothing is mounted: the ESP is
// opened O_EXCL (refused while mounted) and written at its offsets. Partitions are /dev/block/by-name/<name>, which
// ueventd links for the boot disk only (androidboot.boot_part_uuid).
//
//   openbook-bootsync [--current SLOT] [--by-name DIR | --disk IMAGE] [--tries N] [--allow-new-key] [--json]
//                     [--test-stop-after files|entry|loader] status | activate SLOT | mark-good | disable SLOT
// --disk: host tests, a whole-disk image file whose partitions are found by GPT name. --current: the running slot
// (default ro.boot.slot_suffix). --json: the result as JSON on stdout; the log is on stderr. Exit 0 on success, 1 when
// refused or failed (nothing changed unless the log says which step ran), 2 on usage errors, 75 after a test stop.
#include "common.h"

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define EXIT_TEST_STOP 75
#define MAX_ENTRIES 32

static const char *g_byname = "/dev/block/by-name";
static const char *g_disk;
static int g_disk_fd = -1, g_rw, g_tries = 3, g_allow_new_key, g_json;
static const char *g_stop_after = "";
static struct gpt g_gpt;
static char g_cur;  // 'a' or 'b'

static void put32le(uint8_t *p, uint32_t v) {
    p[0] = v;
    p[1] = v >> 8;
    p[2] = v >> 16;
    p[3] = v >> 24;
}
static uint32_t rd32le(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
static uint32_t rd32be(const uint8_t *p) { return (uint32_t)p[0] << 24 | p[1] << 16 | p[2] << 8 | p[3]; }
static uint64_t rd64be(const uint8_t *p) { return (uint64_t)rd32be(p) << 32 | rd32be(p + 4); }
static uint64_t align_up(uint64_t v, uint64_t a) { return (v + a - 1) / a * a; }

// ------------------------------------------------------------------ partitions
struct part {
    int fd, own;
    uint64_t off, size;
    char name[48];
};

static int part_open(const char *name, int rw, struct part *p, char *why, size_t wl) {
    memset(p, 0, sizeof *p);
    p->fd = -1;
    snprintf(p->name, sizeof p->name, "%s", name);
    if (g_disk) {
        if (g_disk_fd < 0) {
            g_disk_fd = open(g_disk, (g_rw ? O_RDWR : O_RDONLY) | O_CLOEXEC);
            struct stat st;
            if (g_disk_fd < 0 || fstat(g_disk_fd, &st) || gpt_read(g_disk_fd, 512, st.st_size / 512, &g_gpt)) {
                snprintf(why, wl, "%s: no readable GPT (%s)", g_disk, g_gpt.why[0] ? g_gpt.why : strerror(errno));
                return -1;
            }
        }
        const struct gpt_part *gp = gpt_find(&g_gpt, name);
        if (!gp) {
            snprintf(why, wl, "no partition named %s on %s", name, g_disk);
            return -1;
        }
        p->fd = g_disk_fd;
        p->off = gp->first * 512;
        p->size = (gp->last - gp->first + 1) * 512;
        return 0;
    }
    char path[256];
    snprintf(path, sizeof path, "%s/%s", g_byname, name);
    // O_EXCL on a block device: refused while it is mounted or held, so nobody else has the ESP open for writing.
    p->fd = open(path, (rw ? O_RDWR | O_EXCL : O_RDONLY) | O_CLOEXEC);
    if (p->fd < 0) {
        snprintf(why, wl, "%s: %s", path, strerror(errno));
        return -1;
    }
    off_t end = lseek(p->fd, 0, SEEK_END);
    if (end <= 0) {
        snprintf(why, wl, "%s: no size", path);
        close(p->fd);
        p->fd = -1;
        return -1;
    }
    p->size = (uint64_t)end;
    p->own = 1;
    return 0;
}

static void part_close(struct part *p) {
    if (p->own && p->fd >= 0) close(p->fd);
    p->fd = -1;
}

static int part_read(struct part *p, uint64_t off, void *buf, size_t n) {
    if (off > p->size || n > p->size - off) {
        errno = ERANGE;
        return -1;
    }
    return pread_all(p->fd, buf, n, p->off + off);
}

// ------------------------------------------------------------------ key = value lists (bootconfig)
struct kv {
    int n;
    char *k[160], *v[160];
};

static int kv_find(const struct kv *m, const char *k) {
    for (int i = 0; i < m->n; i++)
        if (!strcmp(m->k[i], k)) return i;
    return -1;
}
static const char *kv_get(const struct kv *m, const char *k) {
    int i = kv_find(m, k);
    return i < 0 ? NULL : m->v[i];
}
static void kv_set(struct kv *m, const char *k, const char *v) {
    int i = kv_find(m, k);
    if (i >= 0) {
        free(m->v[i]);
        m->v[i] = strdup(v);
    } else if (m->n < (int)ARRAY_LEN(m->k)) {
        m->k[m->n] = strdup(k);
        m->v[m->n++] = strdup(v);
    }
}
static void kv_del(struct kv *m, const char *k) {
    int i = kv_find(m, k);
    if (i < 0) return;
    free(m->k[i]);
    free(m->v[i]);
    memmove(m->k + i, m->k + i + 1, (m->n - i - 1) * sizeof *m->k);
    memmove(m->v + i, m->v + i + 1, (m->n - i - 1) * sizeof *m->v);
    m->n--;
}
static void kv_free(struct kv *m) {
    for (int i = 0; i < m->n; i++) {
        free(m->k[i]);
        free(m->v[i]);
    }
    m->n = 0;
}

// "key = value" or key=value lines, quotes stripped (scripts/installer/bootconfig.py parse_text).
static void kv_parse(struct kv *m, const char *text, size_t n) {
    char *t = malloc(n + 1);
    if (!t) return;
    memcpy(t, text, n);
    t[n] = 0;
    char *save = NULL;
    for (char *line = strtok_r(t, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        trim(line);
        if (!line[0] || line[0] == '#') continue;
        char *eq = strchr(line, '=');
        if (!eq) continue;
        *eq = 0;
        char *k = line, *v = eq + 1;
        trim(k);
        trim(v);
        size_t vl = strlen(v);
        if (vl >= 2 && v[0] == '"' && v[vl - 1] == '"') {
            v[vl - 1] = 0;
            v++;
        }
        kv_set(m, k, v);
    }
    free(t);
}

// The blob a loader appends after the initrds: text, NUL, padding to 4, le32 size, le32 checksum, "#BOOTCONFIG\n".
static uint8_t *bc_blob(const struct kv *m, uint32_t *len) {
    struct sb t = {0};
    for (int i = 0; i < m->n; i++) {
        int quote = !m->v[i][0];
        for (const char *p = m->v[i]; *p; p++)
            if (strchr(" \t;#,{}=\"'", *p)) quote = 1;
        if (quote) sb_printf(&t, "%s = \"%s\"\n", m->k[i], m->v[i]);
        else sb_printf(&t, "%s = %s\n", m->k[i], m->v[i]);
    }
    sb_add(&t, "\0", 1);
    while (t.n % 4) sb_add(&t, "\0", 1);
    uint32_t size = t.n, sum = 0;
    for (size_t i = 0; i < t.n; i++) sum += (uint8_t)t.p[i];
    uint8_t tail[8];
    put32le(tail, size);
    put32le(tail + 4, sum);
    sb_add(&t, (char *)tail, 8);
    sb_add(&t, "#BOOTCONFIG\n", 12);
    *len = t.n;
    return (uint8_t *)t.p;
}

static int bc_read(struct kv *m, const uint8_t *buf, uint32_t n) {
    if (n < 20 || memcmp(buf + n - 12, "#BOOTCONFIG\n", 12)) return -1;
    uint32_t size = rd32le(buf + n - 20), sum = rd32le(buf + n - 16), s = 0;
    if (size > n - 20) return -1;
    const uint8_t *d = buf + n - 20 - size;
    for (uint32_t i = 0; i < size; i++) s += d[i];
    if (s != sum) return -1;
    kv_parse(m, (const char *)d, strnlen((const char *)d, size));
    return 0;
}

// ------------------------------------------------------------------ a slot's boot partitions, as a loader sees them
struct buf {
    uint8_t *p;
    uint32_t n;
};

struct slotimg {
    char slot;
    int ok;
    char why[300];
    struct buf kernel, vramdisk, ramdisk;  // ramdisks padded for unlz4 (scripts/installer/mkproto.py copy_padded)
    char vcmdline[2049];
    struct kv vbc;  // vendor_boot's bootconfig section: the product's static values
    int nfrag;
    uint8_t *vbmeta;
    size_t vbmeta_len;
    uint32_t algorithm;   // 0: unsigned
    char digest[65], key_sha[65], release[49];
    int hashes_checked;
};

static void padded(struct sb *o, const uint8_t *d, uint32_t n) {
    sb_add(o, (const char *)d, n);
    uint32_t pad = (4 - n % 4) % 4;
    if (pad) {
        static const char z[8];
        sb_add(o, z, pad + 4);
    }
}

static int read_buf(struct part *p, uint64_t off, uint64_t n, struct buf *b) {
    if (n > 512 * MiB) {
        errno = EFBIG;
        return -1;
    }
    b->p = malloc(n ? n : 1);
    b->n = n;
    return b->p && !part_read(p, off, b->p, n) ? 0 : -1;
}

// Hash descriptor check: sha256(salt || first image_size bytes of the partition) == digest (libavb's hash descriptor).
static int check_hash(struct part *p, const uint8_t *salt, uint32_t sl, const uint8_t *dg, uint32_t dl, uint64_t isz,
                      char *why, size_t wl) {
    if (dl != 32 || isz > p->size) {
        snprintf(why, wl, "%s: unexpected hash descriptor (digest %u bytes, image %llu bytes)", p->name, dl,
                 (unsigned long long)isz);
        return -1;
    }
    struct sha256 c;
    sha256_init(&c);
    sha256_update(&c, salt, sl);
    uint8_t *blk = malloc(4 * MiB), out[32];
    if (!blk) return -1;
    for (uint64_t o = 0; o < isz;) {
        size_t n = isz - o < 4 * MiB ? isz - o : 4 * MiB;
        if (part_read(p, o, blk, n)) {
            free(blk);
            snprintf(why, wl, "%s: read error at %llu", p->name, (unsigned long long)o);
            return -1;
        }
        sha256_update(&c, blk, n);
        o += n;
    }
    free(blk);
    sha256_final(&c, out);
    if (memcmp(out, dg, 32)) {
        snprintf(why, wl, "%s does not match its vbmeta hash descriptor (an incomplete or damaged write)", p->name);
        return -1;
    }
    return 0;
}

// Read slot s's vbmeta, boot, init_boot and vendor_boot. With verify, every hash descriptor is checked.
static int slot_load(char s, int verify, struct slotimg *si) {
    memset(si, 0, sizeof *si);
    si->slot = s;
    char n[48], *why = si->why;
    size_t wl = sizeof si->why;
    struct part vb, bt, ib, vd;
    vb.fd = bt.fd = ib.fd = vd.fd = -1;
    int rc = -1;
    // ---- vbmeta: one top-level struct (no chained partitions in this product), digest over header+auth+aux
    snprintf(n, sizeof n, "vbmeta_%c", s);
    if (part_open(n, 0, &vb, why, wl)) goto out;
    uint8_t h[256];
    if (part_read(&vb, 0, h, 256) || memcmp(h, "AVB0", 4)) {
        snprintf(why, wl, "%s: no vbmeta image (blank slot?)", n);
        goto out;
    }
    uint64_t auth = rd64be(h + 12), aux = rd64be(h + 20);
    if (auth > vb.size || aux > vb.size || 256 + auth + aux > vb.size) {
        snprintf(why, wl, "%s: vbmeta sizes out of range", n);
        goto out;
    }
    si->vbmeta_len = 256 + auth + aux;
    si->vbmeta = malloc(si->vbmeta_len);
    if (!si->vbmeta || part_read(&vb, 0, si->vbmeta, si->vbmeta_len)) goto out;
    sha256_hex(si->vbmeta, si->vbmeta_len, si->digest);
    si->algorithm = rd32be(h + 28);
    memcpy(si->release, h + 128, 47);
    si->release[47] = 0;
    const uint8_t *A = si->vbmeta + 256 + auth;
    uint64_t pko = rd64be(h + 64), pks = rd64be(h + 72), dof = rd64be(h + 96), dsz = rd64be(h + 104);
    if (pko + pks > aux || dof + dsz > aux) {
        snprintf(why, wl, "%s: vbmeta offsets out of range", n);
        goto out;
    }
    if (pks) sha256_hex(A + pko, pks, si->key_sha);
    // ---- the boot images
    snprintf(n, sizeof n, "boot_%c", s);
    if (part_open(n, 0, &bt, why, wl)) goto out;
    snprintf(n, sizeof n, "init_boot_%c", s);
    if (part_open(n, 0, &ib, why, wl)) goto out;
    snprintf(n, sizeof n, "vendor_boot_%c", s);
    if (part_open(n, 0, &vd, why, wl)) goto out;
    int seen = 0;
    const uint8_t *d = A + dof, *end = d + dsz;
    while (end - d >= 16) {
        uint64_t tag = rd64be(d), len = rd64be(d + 8);
        if (len > (uint64_t)(end - d - 16)) break;
        if (tag == 4) {
            snprintf(why, wl, "vbmeta_%c chains another partition; bootsync expects one top-level vbmeta", s);
            goto out;
        }
        if (tag == 2 && len >= 116) {  // hash descriptor
            uint64_t isz = rd64be(d + 16);
            uint32_t nl = rd32be(d + 56), sl = rd32be(d + 60), dl = rd32be(d + 64);
            if ((uint64_t)116 + nl + sl + dl > len) break;
            const uint8_t *nm = d + 132, *salt = nm + nl, *dg = salt + sl;
            struct part *p = NULL;
            if (nl == 4 && !memcmp(nm, "boot", 4)) p = &bt, seen |= 1;
            else if (nl == 9 && !memcmp(nm, "init_boot", 9)) p = &ib, seen |= 2;
            else if (nl == 11 && !memcmp(nm, "vendor_boot", 11)) p = &vd, seen |= 4;
            if (p && verify && check_hash(p, salt, sl, dg, dl, isz, why, wl)) goto out;
        }
        d += 16 + len;
    }
    if (seen != 7) {
        snprintf(why, wl, "vbmeta_%c has no hash descriptor for %s", s,
                 !(seen & 1) ? "boot" : !(seen & 2) ? "init_boot" : "vendor_boot");
        goto out;
    }
    si->hashes_checked = verify;
    // boot: the GKI kernel (boot image v4: 4096-byte header, kernel, no ramdisk)
    uint8_t bh[4096];
    if (part_read(&bt, 0, bh, sizeof bh) || memcmp(bh, "ANDROID!", 8) || rd32le(bh + 40) < 3) {
        snprintf(why, wl, "boot_%c: not a boot image v3/v4", s);
        goto out;
    }
    if (read_buf(&bt, 4096, rd32le(bh + 8), &si->kernel) || !si->kernel.n) {
        snprintf(why, wl, "boot_%c: no kernel", s);
        goto out;
    }
    // init_boot: the generic ramdisk
    if (part_read(&ib, 0, bh, sizeof bh) || memcmp(bh, "ANDROID!", 8) || rd32le(bh + 40) < 3) {
        snprintf(why, wl, "init_boot_%c: not a boot image v3/v4", s);
        goto out;
    }
    struct buf rd = {0};
    if (read_buf(&ib, 4096 + align_up(rd32le(bh + 8), 4096), rd32le(bh + 12), &rd) || !rd.n) {
        free(rd.p);
        snprintf(why, wl, "init_boot_%c: no ramdisk", s);
        goto out;
    }
    struct sb o = {0};
    padded(&o, rd.p, rd.n);
    free(rd.p);
    si->ramdisk.p = (uint8_t *)o.p;
    si->ramdisk.n = o.n;
    // vendor_boot v4: header, vendor ramdisk section, dtb, ramdisk table, bootconfig; each page aligned
    uint8_t vh[2128];
    if (part_read(&vd, 0, vh, sizeof vh) || memcmp(vh, "VNDRBOOT", 8) || rd32le(vh + 8) != 4) {
        snprintf(why, wl, "vendor_boot_%c: not a vendor boot image v4", s);
        goto out;
    }
    uint32_t page = rd32le(vh + 12), vrs = rd32le(vh + 24), hs = rd32le(vh + 2096), dtb = rd32le(vh + 2100);
    uint32_t ts = rd32le(vh + 2112), ne = rd32le(vh + 2116), es = rd32le(vh + 2120), bcs = rd32le(vh + 2124);
    if (!page || page > 1 << 20 || es < 12 || ne > 64 || (uint64_t)ne * es > ts) {
        snprintf(why, wl, "vendor_boot_%c: header out of range", s);
        goto out;
    }
    memcpy(si->vcmdline, vh + 28, 2048);
    si->vcmdline[2048] = 0;
    uint64_t vro = align_up(hs, page), dto = vro + align_up(vrs, page), tbo = dto + align_up(dtb, page),
             bco = tbo + align_up(ts, page);
    struct buf sec = {0}, tab = {0}, bcb = {0};
    if (read_buf(&vd, vro, vrs, &sec) || read_buf(&vd, tbo, ts, &tab) || read_buf(&vd, bco, bcs, &bcb)) {
        free(sec.p), free(tab.p), free(bcb.p);
        snprintf(why, wl, "vendor_boot_%c: sections out of range", s);
        goto out;
    }
    struct sb v = {0};
    int bad = 0;
    for (uint32_t i = 0; i < ne; i++) {
        uint32_t fs = rd32le(tab.p + i * es), fo = rd32le(tab.p + i * es + 4);
        if ((uint64_t)fo + fs > vrs) bad = 1;
        else padded(&v, sec.p + fo, fs);
    }
    if (!ne) padded(&v, sec.p, vrs);  // no table: one ramdisk
    si->nfrag = ne ? (int)ne : 1;
    kv_parse(&si->vbc, (const char *)bcb.p, strnlen((const char *)bcb.p, bcb.n));
    free(sec.p), free(tab.p), free(bcb.p);
    si->vramdisk.p = (uint8_t *)v.p;
    si->vramdisk.n = v.n;
    if (bad || !v.n) {
        snprintf(why, wl, "vendor_boot_%c: ramdisk table out of range", s);
        goto out;
    }
    si->ok = 1;
    rc = 0;
out:
    part_close(&vb), part_close(&bt), part_close(&ib), part_close(&vd);
    return rc;
}

static void slot_free(struct slotimg *si) {
    free(si->kernel.p), free(si->vramdisk.p), free(si->ramdisk.p), free(si->vbmeta);
    kv_free(&si->vbc);
}

// ------------------------------------------------------------------ the ESP: entries and loader.conf
struct entry {
    char file[128];  // loader/entries/<file>
    char slot;       // 'a'/'b', 0 for an entry that is not a slot entry (other systems, test entries)
    int counted, left, done;  // boot counting: openbook-b+LEFT[-DONE].conf
    char sort_key[64], version[64], id[128];
};

struct esp {
    struct part p;
    struct fat f;
    int open;
    struct entry e[MAX_ENTRIES];
    int ne;
    char *loader;  // loader/loader.conf, NUL-terminated (NULL: none)
    char def[128], pref[128];
};

// openbook-<a|b>[+LEFT[-DONE]].conf; the id systemd-boot uses is the name without the counter.
static int parse_name(const char *name, struct entry *e) {
    memset(e, 0, sizeof *e);
    snprintf(e->file, sizeof e->file, "%s", name);
    size_t l = strlen(name);
    if (l < 5 || strcasecmp(name + l - 5, ".conf")) return -1;
    char base[128];
    snprintf(base, sizeof base, "%.*s", (int)(l - 5), name);
    char *plus = strrchr(base, '+');
    if (plus) {
        char *dash = strchr(plus, '-'), *endp;
        long left = strtol(plus + 1, &endp, 10);
        long done = 0;
        if (endp == plus + 1 || left < 0) plus = NULL;
        else if (dash && endp == dash) {
            done = strtol(dash + 1, &endp, 10);
            if (endp == dash + 1 || *endp) plus = NULL;
        } else if (*endp) plus = NULL;
        if (plus) {
            e->counted = 1;
            e->left = (int)left;
            e->done = (int)done;
            *plus = 0;
        }
    }
    snprintf(e->id, sizeof e->id, "%s.conf", base);
    for (char *p = e->id; *p; p++) *p = tolower((unsigned char)*p);
    if (!strncmp(e->id, "openbook-", 9) && (e->id[9] == 'a' || e->id[9] == 'b') && !strcmp(e->id + 10, ".conf"))
        e->slot = e->id[9];
    return 0;
}

static void list_cb(const char *name, int is_dir, uint32_t size, void *arg) {
    struct esp *x = arg;
    if (is_dir || x->ne >= MAX_ENTRIES) return;
    if (!parse_name(name, &x->e[x->ne])) x->ne++;
}

static void entry_field(const char *text, const char *key, char *out, size_t n) {
    out[0] = 0;
    size_t kl = strlen(key);
    for (const char *l = text; l && *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : NULL) {
        if (!strncmp(l, key, kl) && (l[kl] == ' ' || l[kl] == '\t')) {
            const char *v = l + kl;
            while (*v == ' ' || *v == '\t') v++;
            size_t vl = strcspn(v, "\r\n");
            snprintf(out, n, "%.*s", (int)vl, v);
            return;
        }
    }
}

static void loader_field(const char *text, const char *key, char *out, size_t n) {
    entry_field(text ? text : "", key, out, n);
    for (char *p = out; *p; p++) *p = tolower((unsigned char)*p);
}

static int esp_load(struct esp *x, int rw, char *why, size_t wl) {
    if (!x->open) {
        if (part_open("EFI", rw, &x->p, why, wl)) {
            // An install alongside another system keeps its kernels on XBOOTLDR and has no loader.conf of its own.
            size_t l = strlen(why);
            snprintf(why + l, wl - l, " (bootsync handles whole-disk installs, whose ESP is the partition named EFI)");
            return -1;
        }
        if (fat_open(&x->f, x->p.fd, x->p.off, x->p.size)) {
            snprintf(why, wl, "EFI: not a FAT file system");
            part_close(&x->p);
            return -1;
        }
        x->open = 1;
    }
    x->ne = 0;
    free(x->loader);
    x->loader = NULL;
    fat_list(&x->f, "loader/entries", list_cb, x);
    for (int i = 0; i < x->ne; i++) {
        char path[192];
        snprintf(path, sizeof path, "loader/entries/%s", x->e[i].file);
        uint32_t n;
        char *t = (char *)fat_read(&x->f, path, &n);
        if (!t) continue;
        t = realloc(t, n + 1);
        t[n] = 0;
        entry_field(t, "sort-key", x->e[i].sort_key, sizeof x->e[i].sort_key);
        entry_field(t, "version", x->e[i].version, sizeof x->e[i].version);
        free(t);
    }
    uint32_t n;
    x->loader = (char *)fat_read(&x->f, "loader/loader.conf", &n);
    if (x->loader) {
        x->loader = realloc(x->loader, n + 1);
        x->loader[n] = 0;
    }
    loader_field(x->loader, "default", x->def, sizeof x->def);
    loader_field(x->loader, "preferred", x->pref, sizeof x->pref);
    return 0;
}

static void esp_close(struct esp *x) {
    if (x->open) {
        fat_close(&x->f);
        part_close(&x->p);
    }
    free(x->loader);
    memset(x, 0, sizeof *x);
}

static struct entry *slot_entry(struct esp *x, char s) {
    struct entry *best = NULL;
    for (int i = 0; i < x->ne; i++)
        if (x->e[i].slot == s && (!best || (best->counted && !x->e[i].counted))) best = &x->e[i];
    return best;
}

static const char *entry_state(const struct entry *e) {
    return !e ? "none" : !e->counted ? "good" : e->left == 0 ? "bad" : e->done ? "trying" : "pending";
}

// ---- which entry systemd-boot 262 starts (src/boot/boot.c: boot_entry_compare, config_select_default_entry),
// without EFI variables (LoaderEntryOneShot/Preferred/Default; OpenBook sets none) and without profiles.
static int vercmp(const char *a, const char *b) {  // a simplified strverscmp_improved: digit runs compare as numbers
    while (*a || *b) {
        if (isdigit((unsigned char)*a) && isdigit((unsigned char)*b)) {
            while (*a == '0') a++;
            while (*b == '0') b++;
            size_t la = strspn(a, "0123456789"), lb = strspn(b, "0123456789");
            if (la != lb) return la < lb ? -1 : 1;
            int c = strncmp(a, b, la);
            if (c) return c < 0 ? -1 : 1;
            a += la, b += lb;
            continue;
        }
        if (*a != *b) return (unsigned char)*a < (unsigned char)*b ? -1 : 1;
        a++, b++;
    }
    return 0;
}

static int entry_cmp(const void *pa, const void *pb) {
    const struct entry *a = *(const struct entry *const *)pa, *b = *(const struct entry *const *)pb;
    int ab = a->counted && a->left == 0, bb = b->counted && b->left == 0;
    if (ab != bb) return ab - bb;
    if (!a->sort_key[0] != !b->sort_key[0]) return !a->sort_key[0] - !b->sort_key[0];
    if (a->sort_key[0]) {
        int c = strcmp(a->sort_key, b->sort_key);
        if (c) return c;
        c = -vercmp(a->version, b->version);
        if (c) return c;
    }
    int c = -vercmp(a->id, b->id);
    if (c) return c;
    if (!a->counted || !b->counted) return 0;
    if (a->left != b->left) return b->left - a->left;
    return a->done - b->done;
}

static int glob_match(const char *pat, const char *s) {
    if (!*pat) return !*s;
    if (*pat == '*') return glob_match(pat + 1, s) || (*s && glob_match(pat, s + 1));
    if (*pat == '?') return *s && glob_match(pat + 1, s + 1);
    return *pat == *s && glob_match(pat + 1, s + 1);
}

static const struct entry *next_boot(struct esp *x) {
    const struct entry *v[MAX_ENTRIES];
    for (int i = 0; i < x->ne; i++) v[i] = &x->e[i];
    qsort(v, x->ne, sizeof v[0], entry_cmp);
    if (x->pref[0])
        for (int i = 0; i < x->ne; i++)
            if (glob_match(x->pref, v[i]->id) && !(v[i]->counted && v[i]->left == 0)) return v[i];
    if (x->def[0])
        for (int i = 0; i < x->ne; i++)
            if (glob_match(x->def, v[i]->id)) return v[i];
    return x->ne ? v[0] : NULL;
}

// loader.conf with its default and preferred lines replaced (pref NULL or "": no preferred line); other lines kept.
static char *loader_with(const char *cur, const char *def, const char *pref) {
    struct sb o = {0};
    const char *t = cur ? cur : "timeout menu-hidden\nconsole-mode keep\neditor no\n";
    for (const char *l = t; *l;) {
        size_t n = strcspn(l, "\n");
        int skip = (!strncasecmp(l, "default", 7) && (l[7] == ' ' || l[7] == '\t')) ||
                   (!strncasecmp(l, "preferred", 9) && (l[9] == ' ' || l[9] == '\t'));
        if (!skip && n) {
            sb_add(&o, l, n);
            sb_add(&o, "\n", 1);
        }
        l += n;
        if (*l == '\n') l++;
    }
    sb_printf(&o, "default %s\n", def);
    if (pref && *pref) sb_printf(&o, "preferred %s\n", pref);
    sb_add(&o, "\0", 1);
    return o.p;
}

// ------------------------------------------------------------------ results
static struct jw W;
static int g_steps;

static void step(const char *what) {
    g_steps++;
    LOG("step %d: %s", g_steps, what);
}

static int test_stop(const char *s) {
    if (strcmp(g_stop_after, s)) return 0;
    LOG("test stop after %s", s);
    return 1;
}

static int fail(const char *code, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static int fail(const char *code, const char *fmt, ...) {
    char msg[600];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof msg, fmt, ap);
    va_end(ap);
    LOG("refused (%s): %s", code, msg);
    jw_bool(&W, "ok", 0);
    jw_str(&W, "code", code);
    jw_str(&W, "error", msg);
    return 1;
}

static void entries_json(struct esp *x) {
    jw_arr(&W, "entries");
    for (int i = 0; i < x->ne; i++) {
        jw_obj(&W, NULL);
        jw_str(&W, "file", x->e[i].file);
        jw_str(&W, "id", x->e[i].id);
        if (x->e[i].slot) {
            char s[2] = {x->e[i].slot, 0};
            jw_str(&W, "slot", s);
        }
        jw_str(&W, "state", entry_state(&x->e[i]));
        if (x->e[i].counted) {
            jw_int(&W, "tries_left", x->e[i].left);
            jw_int(&W, "tries_done", x->e[i].done);
        }
        jw_endo(&W);
    }
    jw_enda(&W);
    jw_obj(&W, "loader_conf");
    jw_str(&W, "default", x->def[0] ? x->def : NULL);
    jw_str(&W, "preferred", x->pref[0] ? x->pref : NULL);
    jw_endo(&W);
    const struct entry *nb = next_boot(x);
    char s[2] = {nb ? nb->slot : 0, 0};
    jw_str(&W, "next_boot_entry", nb ? nb->file : NULL);
    jw_str(&W, "next_boot_slot", nb && nb->slot ? s : NULL);
    jw_u64(&W, "esp_free_bytes", x->open ? fat_free_bytes(&x->f) : 0);
}

// ------------------------------------------------------------------ what slot t's ESP files must hold
struct exp {
    struct buf bc;            // bootconfig blob
    char options[2400];       // the entry's kernel command line
    char version[96];
    char title[96], sort_key[64];
    char path[4][96];
    struct buf *data[4];
};

static const char *FILES[4] = {"kernel", "vendor_ramdisk.img", "ramdisk.img", "bootconfig.img"};

// The current entry's text, and the files its last initrd names (the bootconfig blob the loader passed).
static char *read_entry(struct esp *x, const struct entry *e) {
    char path[192];
    snprintf(path, sizeof path, "loader/entries/%s", e->file);
    uint32_t n;
    char *t = (char *)fat_read(&x->f, path, &n);
    if (!t) return NULL;
    t = realloc(t, n + 1);
    t[n] = 0;
    return t;
}

static void last_initrd(const char *text, char *out, size_t n) {
    out[0] = 0;
    for (const char *l = text; l && *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : NULL)
        if (!strncmp(l, "initrd", 6) && (l[6] == ' ' || l[6] == '\t')) {
            const char *v = l + 6;
            while (*v == ' ' || *v == '\t' || *v == '/') v++;
            snprintf(out, n, "%.*s", (int)strcspn(v, "\r\n"), v);
        }
}

static int has_token(const char *list, const char *tok, size_t tl) {
    for (const char *p = list; *p;) {
        while (*p == ' ') p++;
        size_t l = strcspn(p, " ");
        if (l == tl && !strncmp(p, tok, tl)) return 1;
        p += l;
    }
    return 0;
}

// Slot t's files from its images, the current entry (title, version, options beyond vendor_boot's, bootconfig)
// and the current slot's vendor_boot (which bootconfig keys were the product's static ones).
static int expected(struct esp *x, const struct slotimg *cur, const struct slotimg *t, struct exp *o, char *why,
                    size_t wl) {
    memset(o, 0, sizeof *o);
    struct entry *ce = slot_entry(x, cur->slot);
    if (!ce) {
        snprintf(why, wl, "the running slot %c has no loader entry on the ESP (not installed by the OpenBook installer?)",
                 cur->slot);
        return -1;
    }
    char *text = read_entry(x, ce);
    if (!text) {
        snprintf(why, wl, "loader/entries/%s: unreadable", ce->file);
        return -1;
    }
    char bcpath[160], opts[2400], ver[96];
    last_initrd(text, bcpath, sizeof bcpath);
    entry_field(text, "options", opts, sizeof opts);
    entry_field(text, "title", o->title, sizeof o->title);
    entry_field(text, "sort-key", o->sort_key, sizeof o->sort_key);
    entry_field(text, "version", ver, sizeof ver);
    free(text);
    uint32_t bn;
    uint8_t *bb = bcpath[0] ? fat_read(&x->f, bcpath, &bn) : NULL;
    struct kv bc = {0};
    if (!bb || bc_read(&bc, bb, bn)) {
        free(bb);
        snprintf(why, wl, "%s: not a bootconfig blob (the running entry's last initrd)", bcpath[0] ? bcpath : "none");
        return -1;
    }
    free(bb);
    // product static values: the current vendor_boot's are dropped unless the new one has them, the new one's win
    for (int i = 0; i < cur->vbc.n; i++)
        if (!kv_get(&t->vbc, cur->vbc.k[i])) kv_del(&bc, cur->vbc.k[i]);
    for (int i = 0; i < t->vbc.n; i++) kv_set(&bc, t->vbc.k[i], t->vbc.v[i]);
    char sfx[3] = {'_', t->slot, 0}, size[24];
    kv_set(&bc, "androidboot.slot_suffix", sfx);
    snprintf(size, sizeof size, "%zu", t->vbmeta_len);
    kv_set(&bc, "androidboot.vbmeta.size", size);
    kv_set(&bc, "androidboot.vbmeta.digest", t->digest);
    o->bc.p = bc_blob(&bc, &o->bc.n);
    kv_free(&bc);
    // kernel command line: the new vendor_boot's, plus whatever the running entry added to its own (a VM's console)
    struct sb ob = {0};
    sb_puts(&ob, t->vcmdline);
    for (const char *p = opts; *p;) {
        while (*p == ' ') p++;
        size_t l = strcspn(p, " ");
        if (l && !has_token(cur->vcmdline, p, l) && !has_token(t->vcmdline, p, l)) {
            sb_add(&ob, " ", 1);
            sb_add(&ob, p, l);
        }
        p += l;
    }
    sb_add(&ob, "\0", 1);
    snprintf(o->options, sizeof o->options, "%s", ob.p);
    sb_free(&ob);
    // "17 · slot A" -> "17 · slot B"
    char *sl = strstr(ver, "slot ");
    if (sl && (sl[5] == 'A' || sl[5] == 'B' || sl[5] == 'a' || sl[5] == 'b'))
        snprintf(o->version, sizeof o->version, "%.*sslot %c%s", (int)(sl - ver), ver, toupper(t->slot), sl + 6);
    else
        snprintf(o->version, sizeof o->version, "slot %c", toupper(t->slot));
    if (!o->title[0]) snprintf(o->title, sizeof o->title, "OpenBook");
    if (!o->sort_key[0]) snprintf(o->sort_key, sizeof o->sort_key, "openbook-1");
    for (int i = 0; i < 4; i++) snprintf(o->path[i], sizeof o->path[i], "openbook/%c/%s", t->slot, FILES[i]);
    o->data[0] = (struct buf *)&t->kernel;
    o->data[1] = (struct buf *)&t->vramdisk;
    o->data[2] = (struct buf *)&t->ramdisk;
    o->data[3] = &o->bc;
    return 0;
}

static char *entry_text(const struct exp *o, char s) {
    struct sb e = {0};
    sb_printf(&e, "title %s\nversion %s\nsort-key %s\nlinux /openbook/%c/kernel\n", o->title, o->version, o->sort_key, s);
    for (int i = 1; i < 4; i++) sb_printf(&e, "initrd /%s\n", o->path[i]);
    sb_printf(&e, "options %s\n", o->options);
    sb_add(&e, "\0", 1);
    return e.p;
}

// ESP files of slot s compared with what they should hold: "in_sync", "missing" or "differ".
static const char *files_state(struct esp *x, const struct exp *o, char *detail, size_t dl) {
    detail[0] = 0;
    int missing = 0, differ = 0;
    for (int i = 0; i < 4; i++) {
        uint32_t n;
        uint8_t *d = fat_read(&x->f, o->path[i], &n);
        if (!d) missing++;
        else if (n != o->data[i]->n || memcmp(d, o->data[i]->p, n)) {
            differ++;
            snprintf(detail + strlen(detail), dl - strlen(detail), "%s%s", detail[0] ? ", " : "", FILES[i]);
        }
        free(d);
    }
    return missing == 4 ? "missing" : missing || differ ? "differ" : "in_sync";
}

static int reopen_esp(struct esp *x, char *why, size_t wl) {
    fsync(x->p.fd);
    posix_fadvise(x->p.fd, x->p.off, x->p.size, POSIX_FADV_DONTNEED);  // read back from the disk, not the cache
    fat_close(&x->f);
    if (fat_open(&x->f, x->p.fd, x->p.off, x->p.size)) {
        snprintf(why, wl, "EFI: unreadable after writing");
        return -1;
    }
    return esp_load(x, 1, why, wl);
}

static int write_loader(struct esp *x, const char *def, const char *pref) {
    char *lc = loader_with(x->loader, def, pref);
    if (x->loader && !strcmp(lc, x->loader)) {
        free(lc);
        return 0;
    }
    int rc = fat_replace(&x->f, "loader/loader.conf", lc, strlen(lc));
    if (!rc) LOG("loader.conf: default %s%s%s", def, pref && *pref ? ", preferred " : "", pref && *pref ? pref : "");
    free(lc);
    return rc;
}

static int remove_entries(struct esp *x, char s, const char *why_msg) {
    for (int i = 0; i < x->ne; i++) {
        if (x->e[i].slot != s) continue;
        char path[192];
        snprintf(path, sizeof path, "loader/entries/%s", x->e[i].file);
        if (fat_unlink(&x->f, path)) {
            LOG("removing %s failed: %s", path, strerror(errno));
            return -1;
        }
        LOG("removed loader/entries/%s (%s)", x->e[i].file, why_msg);
    }
    return 0;
}

// ------------------------------------------------------------------ commands
static int cmd_status(void) {
    char why[300];
    struct esp x = {0};
    struct slotimg si[2];
    char cs[2] = {g_cur, 0};
    jw_str(&W, "current_slot", cs);
    if (esp_load(&x, 0, why, sizeof why)) return fail("no_esp", "%s", why);
    for (int k = 0; k < 2; k++) slot_load("ab"[k], 1, &si[k]);
    struct slotimg *cur = &si[g_cur - 'a'];
    jw_obj(&W, "slots");
    for (int k = 0; k < 2; k++) {
        char s = "ab"[k];
        struct slotimg *t = &si[k];
        jw_obj(&W, (char[2]){s, 0});
        jw_bool(&W, "images_ok", t->ok);
        if (!t->ok) jw_str(&W, "images_error", t->why);
        if (t->vbmeta) {
            jw_str(&W, "vbmeta_digest", t->digest);
            jw_str(&W, "vbmeta_key_sha256", t->key_sha[0] ? t->key_sha : NULL);
            jw_bool(&W, "vbmeta_signed", t->algorithm != 0);
            jw_str(&W, "vbmeta_release", t->release);
        }
        struct entry *e = slot_entry(&x, s);
        jw_str(&W, "entry", e ? e->file : NULL);
        jw_str(&W, "entry_state", entry_state(e));
        struct exp o;
        if (t->ok && cur->ok && !expected(&x, cur, t, &o, why, sizeof why)) {
            char d[200];
            jw_str(&W, "esp_files", files_state(&x, &o, d, sizeof d));
            if (d[0]) jw_str(&W, "esp_files_differ", d);
            free(o.bc.p);
        }
        jw_endo(&W);
    }
    jw_endo(&W);
    entries_json(&x);
    jw_bool(&W, "ok", 1);
    for (int k = 0; k < 2; k++) slot_free(&si[k]);
    esp_close(&x);
    return 0;
}

static int cmd_activate(char t) {
    char why[300];
    struct esp x = {0};
    struct slotimg cur, tg;
    int rc = 1;
    memset(&cur, 0, sizeof cur);
    memset(&tg, 0, sizeof tg);
    char ts[2] = {t, 0}, cs[2] = {g_cur, 0};
    jw_str(&W, "current_slot", cs);
    jw_str(&W, "slot", ts);
    if (esp_load(&x, 1, why, sizeof why)) return fail("no_esp", "%s", why);
    struct entry *ce = slot_entry(&x, g_cur);
    if (!ce) {
        rc = fail("no_current_entry", "the running slot %c has no loader entry on the ESP", g_cur);
        goto out;
    }
    char cid[64], tid[64];
    snprintf(cid, sizeof cid, "openbook-%c.conf", g_cur);
    snprintf(tid, sizeof tid, "openbook-%c.conf", t);
    if (t == g_cur) {  // cancel a pending switch: the running slot stays preferred
        step("keep the running slot");
        if (remove_entries(&x, g_cur == 'a' ? 'b' : 'a', "switch cancelled") ||
            write_loader(&x, ce->counted ? x.def[0] ? x.def : cid : cid, ce->counted ? cid : NULL)) {
            rc = fail("write_failed", "ESP: %s", strerror(errno));
            goto out;
        }
        if (reopen_esp(&x, why, sizeof why)) {
            rc = fail("write_failed", "%s", why);
            goto out;
        }
        entries_json(&x);
        jw_bool(&W, "ok", 1);
        rc = 0;
        goto out;
    }
    // ---- 1. check: everything is read and verified before anything is written
    step("check the new slot's boot images against its vbmeta");
    if (slot_load(g_cur, 0, &cur)) {
        rc = fail("current_slot_unreadable", "%s", cur.why);
        goto out;
    }
    if (slot_load(t, 1, &tg)) {
        rc = fail("slot_not_ready", "%s", tg.why);
        goto out;
    }
    jw_str(&W, "vbmeta_digest", tg.digest);
    jw_str(&W, "vbmeta_key_sha256", tg.key_sha[0] ? tg.key_sha : NULL);
    if (!tg.algorithm) {
        rc = fail("unsigned", "vbmeta_%c is unsigned", t);
        goto out;
    }
    if (cur.algorithm && strcmp(cur.key_sha, tg.key_sha) && !g_allow_new_key) {
        rc = fail("key_changed", "vbmeta_%c is signed with another key (%.16s) than the running slot's (%.16s); "
                  "--allow-new-key accepts it", t, tg.key_sha, cur.key_sha);
        goto out;
    }
    struct exp o;
    if (expected(&x, &cur, &tg, &o, why, sizeof why)) {
        rc = fail("no_current_entry", "%s", why);
        goto out;
    }
    uint64_t need = 16 * 4096, have = fat_free_bytes(&x.f);
    for (int i = 0; i < 4; i++) need += align_up(o.data[i]->n, x.f.cluster_bytes);
    if (have < need) {
        rc = fail("esp_full", "the ESP has %llu bytes free, slot %c needs %llu", (unsigned long long)have, t,
                  (unsigned long long)need);
        free(o.bc.p);
        goto out;
    }
    // ---- 2. the slot's old entry goes first: from here on no entry points at files that are being replaced
    step("remove the slot's old entry");
    if (remove_entries(&x, t, "replaced by this update")) {
        rc = fail("write_failed", "ESP: %s", strerror(errno));
        free(o.bc.p);
        goto out;
    }
    if (!strcmp(x.pref, tid) && write_loader(&x, x.def[0] ? x.def : cid, NULL)) {
        rc = fail("write_failed", "loader.conf: %s", strerror(errno));
        free(o.bc.p);
        goto out;
    }
    // ---- 3. files, then read back
    step("export the boot images");
    jw_arr(&W, "files");
    for (int i = 0; i < 4; i++) {
        char sha[65];
        sha256_hex(o.data[i]->p, o.data[i]->n, sha);
        jw_obj(&W, NULL);
        jw_str(&W, "path", o.path[i]);
        jw_u64(&W, "bytes", o.data[i]->n);
        jw_str(&W, "sha256", sha);
        jw_endo(&W);
        if (fat_replace(&x.f, o.path[i], o.data[i]->p, o.data[i]->n)) {
            jw_enda(&W);
            rc = fail("write_failed", "%s: %s", o.path[i], strerror(errno));
            free(o.bc.p);
            goto out;
        }
        LOG("wrote %s (%u bytes, sha256 %.16s)", o.path[i], o.data[i]->n, sha);
    }
    jw_enda(&W);
    char d[200];
    if (reopen_esp(&x, why, sizeof why) || strcmp(files_state(&x, &o, d, sizeof d), "in_sync")) {
        rc = fail("verify_failed", "openbook/%c/ does not read back as written (%s)", t, d[0] ? d : why);
        free(o.bc.p);
        goto out;
    }
    LOG("openbook/%c/ read back: in sync", t);
    if (test_stop("files")) {
        rc = EXIT_TEST_STOP;
        free(o.bc.p);
        goto out;
    }
    // ---- 4. the entry, with boot counting
    step("write the loader entry");
    char ename[64], epath[96];
    snprintf(ename, sizeof ename, "openbook-%c+%d.conf", t, g_tries);
    snprintf(epath, sizeof epath, "loader/entries/%s", ename);
    char *et = entry_text(&o, t);
    free(o.bc.p);
    uint32_t rn;
    uint8_t *rb = NULL;
    if (fat_replace(&x.f, epath, et, strlen(et)) || reopen_esp(&x, why, sizeof why) ||
        !(rb = fat_read(&x.f, epath, &rn)) || rn != strlen(et) || memcmp(rb, et, rn)) {
        rc = fail("write_failed", "%s: %s", epath, strerror(errno));
        free(et), free(rb);
        goto out;
    }
    free(et), free(rb);
    LOG("wrote %s", epath);
    jw_str(&W, "entry", ename);
    if (test_stop("entry")) {
        rc = EXIT_TEST_STOP;
        goto out;
    }
    // ---- 5. loader.conf: the new slot preferred, the running one the default (the rollback target)
    step("prefer the new slot in loader.conf");
    ce = slot_entry(&x, g_cur);
    if (write_loader(&x, ce && !ce->counted ? cid : x.def[0] ? x.def : cid, tid) || reopen_esp(&x, why, sizeof why)) {
        rc = fail("write_failed", "loader.conf: %s", why);
        goto out;
    }
    if (test_stop("loader")) {
        rc = EXIT_TEST_STOP;
        goto out;
    }
    const struct entry *nb = next_boot(&x);
    if (!nb || nb->slot != t) {
        rc = fail("not_next", "after the change systemd-boot would start %s, not slot %c", nb ? nb->file : "nothing", t);
        goto out;
    }
    entries_json(&x);
    jw_bool(&W, "ok", 1);
    rc = 0;
out:
    slot_free(&cur);
    slot_free(&tg);
    esp_close(&x);
    return rc;
}

static int cmd_mark_good(void) {
    char why[300];
    struct esp x = {0};
    int rc = 1;
    char cs[2] = {g_cur, 0}, cid[64], good[64];
    jw_str(&W, "current_slot", cs);
    snprintf(cid, sizeof cid, "openbook-%c.conf", g_cur);
    if (esp_load(&x, 1, why, sizeof why)) return fail("no_esp", "%s", why);
    struct entry *ce = slot_entry(&x, g_cur);
    if (!ce) {
        rc = fail("no_current_entry", "the running slot %c has no loader entry on the ESP", g_cur);
        goto out;
    }
    int after_update = 0, have_good = !ce->counted;
    snprintf(good, sizeof good, "openbook-%c.conf", g_cur);
    for (int i = 0; i < x.ne; i++) {  // a counted entry of the running slot: this is its first good boot
        if (x.e[i].slot != g_cur || !x.e[i].counted) continue;
        char path[192];
        snprintf(path, sizeof path, "loader/entries/%s", x.e[i].file);
        step("mark the running slot's entry good");
        // One counted entry becomes the good one; any other (a leftover of a cut) goes.
        int r = have_good ? fat_unlink(&x.f, path) : fat_rename(&x.f, path, good);
        if (r) {
            rc = fail("write_failed", "%s: %s", path, strerror(errno));
            goto out;
        }
        LOG("%s -> %s", x.e[i].file, have_good ? "removed (a good entry exists)" : good);
        after_update = 1;
        have_good = 1;
    }
    if (reopen_esp(&x, why, sizeof why)) {
        rc = fail("write_failed", "%s", why);
        goto out;
    }
    // loader.conf: the running slot is the default; a preferred entry that is the running one, bad or gone is dropped
    char other = g_cur == 'a' ? 'b' : 'a';
    struct entry *oe = slot_entry(&x, other);
    char pref[128];
    snprintf(pref, sizeof pref, "%s", x.pref);
    int pref_live = pref[0] && strcmp(pref, cid) && oe && !strcmp(pref, oe->id) && !(oe->counted && oe->left == 0);
    if (after_update) {
        step("remove the other slot's entry (the merge overwrites that slot)");
        if (remove_entries(&x, other, "the update to this slot booted")) {
            rc = fail("write_failed", "ESP: %s", strerror(errno));
            goto out;
        }
        pref_live = 0;
    }
    if ((x.loader || after_update || pref[0]) && write_loader(&x, cid, pref_live ? pref : NULL)) {
        rc = fail("write_failed", "loader.conf: %s", strerror(errno));
        goto out;
    }
    if (reopen_esp(&x, why, sizeof why)) {
        rc = fail("write_failed", "%s", why);
        goto out;
    }
    jw_bool(&W, "after_update", after_update);
    entries_json(&x);
    jw_bool(&W, "ok", 1);
    rc = 0;
out:
    esp_close(&x);
    return rc;
}

static int cmd_disable(char t) {
    char why[300];
    struct esp x = {0};
    char ts[2] = {t, 0}, cs[2] = {g_cur, 0}, cid[64], tid[64];
    jw_str(&W, "current_slot", cs);
    jw_str(&W, "slot", ts);
    if (t == g_cur) {
        LOG("slot %c is running: its entry stays", t);
        jw_bool(&W, "ok", 1);
        jw_bool(&W, "changed", 0);
        return 0;
    }
    snprintf(cid, sizeof cid, "openbook-%c.conf", g_cur);
    snprintf(tid, sizeof tid, "openbook-%c.conf", t);
    if (esp_load(&x, 1, why, sizeof why)) return fail("no_esp", "%s", why);
    int rc = 1;
    step("remove the slot's entry");
    if (remove_entries(&x, t, "slot set unbootable") ||
        (!strcmp(x.pref, tid) && write_loader(&x, x.def[0] ? x.def : cid, NULL)) || reopen_esp(&x, why, sizeof why)) {
        rc = fail("write_failed", "ESP: %s", strerror(errno));
        goto out;
    }
    entries_json(&x);
    jw_bool(&W, "ok", 1);
    rc = 0;
out:
    esp_close(&x);
    return rc;
}

static char parse_slot(const char *s) {
    if (!s) return 0;
    if (s[0] == '_') s++;
    if ((s[0] == 'a' || s[0] == 'b') && !s[1]) return s[0];
    return 0;
}

static int usage(void) {
    fprintf(stderr,
            "usage: openbook-bootsync [--current SLOT] [--by-name DIR | --disk IMAGE] [--tries N] [--allow-new-key]\n"
            "                         [--json] [--test-stop-after files|entry|loader]\n"
            "                         status | activate SLOT | mark-good | disable SLOT\n");
    return 2;
}

int main(int argc, char **argv) {
    const char *cur = NULL;
    int i = 1;
    for (; i < argc && argv[i][0] == '-'; i++) {
        const char *a = argv[i];
        if (!strcmp(a, "--current") && i + 1 < argc) cur = argv[++i];
        else if (!strcmp(a, "--by-name") && i + 1 < argc) g_byname = argv[++i];
        else if (!strcmp(a, "--disk") && i + 1 < argc) g_disk = argv[++i];
        else if (!strcmp(a, "--tries") && i + 1 < argc) g_tries = atoi(argv[++i]);
        else if (!strcmp(a, "--test-stop-after") && i + 1 < argc) g_stop_after = argv[++i];
        else if (!strcmp(a, "--allow-new-key")) g_allow_new_key = 1;
        else if (!strcmp(a, "--json")) g_json = 1;
        else return usage();
    }
    if (i >= argc || g_tries < 1 || g_tries > 9) return usage();
    const char *cmd = argv[i];
    char t = parse_slot(i + 1 < argc ? argv[i + 1] : NULL);
    char prop[16] = "";
    if (!cur) {
        prop_get("ro.boot.slot_suffix", prop, sizeof prop);
        cur = prop;
    }
    g_cur = parse_slot(cur);
    if (!g_cur) {
        fprintf(stderr, "openbook-bootsync: no current slot (ro.boot.slot_suffix is '%s'; use --current)\n", cur);
        return 2;
    }
    g_rw = strcmp(cmd, "status") != 0;
    jw_obj(&W, NULL);
    jw_str(&W, "schema", "openbook-bootsync/1");
    jw_str(&W, "command", cmd);
    int rc;
    if (!strcmp(cmd, "status")) rc = cmd_status();
    else if (!strcmp(cmd, "activate") && t) rc = cmd_activate(t);
    else if (!strcmp(cmd, "mark-good")) rc = cmd_mark_good();
    else if (!strcmp(cmd, "disable") && t) rc = cmd_disable(t);
    else return usage();
    jw_endo(&W);
    if (g_json) printf("%s\n", W.b.p);
    if (g_disk_fd >= 0) {
        fsync(g_disk_fd);
        close(g_disk_fd);
    }
    gpt_free(&g_gpt);
    return rc;
}
