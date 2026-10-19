// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// openbook-install: the OpenBook install engine (ANAL-191, docs/installer.md section 3.5 and 5). Plain C with libc
// only, so the same sources build for Android (Soong, /system_ext/bin/openbook-install) and for the host tests
// (gcc, image files; scripts/installer/engine-test.sh).
#pragma once
#define _GNU_SOURCE
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <strings.h>

#define MiB (1024ull * 1024ull)
#define ARRAY_LEN(a) (sizeof(a) / sizeof((a)[0]))

// ------------------------------------------------------------------ string builder
struct sb {
    char *p;
    size_t n, cap;
};
void sb_add(struct sb *b, const char *s, size_t n);
void sb_puts(struct sb *b, const char *s);
void sb_printf(struct sb *b, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
void sb_json_str(struct sb *b, const char *s);  // a quoted, escaped JSON string ("null" for NULL)
void sb_free(struct sb *b);

// ------------------------------------------------------------------ JSON writer (commas handled for you)
struct jw {
    struct sb b;
    int depth;
    int need_comma[64];
};
void jw_obj(struct jw *w, const char *key);  // key NULL inside arrays and at the top level
void jw_arr(struct jw *w, const char *key);
void jw_end(struct jw *w);                   // closes the innermost object or array (tracked by caller)
void jw_endo(struct jw *w);
void jw_enda(struct jw *w);
void jw_str(struct jw *w, const char *key, const char *v);
void jw_int(struct jw *w, const char *key, long long v);
void jw_u64(struct jw *w, const char *key, uint64_t v);
void jw_dbl(struct jw *w, const char *key, double v, int decimals);
void jw_bool(struct jw *w, const char *key, int v);
void jw_null(struct jw *w, const char *key);
void jw_raw(struct jw *w, const char *key, const char *json);

// ------------------------------------------------------------------ JSON reader (small DOM)
enum { J_NULL, J_BOOL, J_NUM, J_STR, J_ARR, J_OBJ };
struct jv {
    int t;
    int b;
    double n;
    char *s;
    int len;
    char **keys;        // J_OBJ
    struct jv **items;  // J_ARR, J_OBJ
};
struct jv *json_parse(const char *text, char *err, size_t errlen);
void json_free(struct jv *v);
struct jv *jget(const struct jv *o, const char *key);
const char *jstr(const struct jv *o, const char *key);  // NULL unless a string
double jnum(const struct jv *o, const char *key, double def);
int jbool(const struct jv *o, const char *key, int def);

// ------------------------------------------------------------------ hashing, CRC, GUIDs
struct sha256 {
    uint32_t h[8];
    uint64_t len;
    uint8_t buf[64];
    size_t used;
};
void sha256_init(struct sha256 *c);
void sha256_update(struct sha256 *c, const void *data, size_t n);
void sha256_final(struct sha256 *c, uint8_t out[32]);
void sha256_final_hex(struct sha256 *c, char out[65]);
void sha256_hex(const void *data, size_t n, char out[65]);
uint32_t crc32_buf(uint32_t crc, const void *data, size_t n);  // crc starts at 0
void guid_to_str(const uint8_t g[16], char out[37]);            // GPT mixed-endian bytes -> canonical text
int guid_from_str(const char *s, uint8_t g[16]);
void guid_random(uint8_t g[16]);                                 // version 4
void random_bytes(void *buf, size_t n);

// ------------------------------------------------------------------ I/O
int pread_all(int fd, void *buf, size_t n, uint64_t off);
int pwrite_all(int fd, const void *buf, size_t n, uint64_t off);
int zero_range(int fd, uint64_t off, uint64_t n);
int read_text(const char *path, char *buf, size_t n);  // trimmed; -1 if unreadable
char *read_file(const char *path, size_t *len);         // malloc'd, NUL-terminated
int write_file(const char *path, const void *data, size_t n);
void trim(char *s);
void human_bytes(uint64_t n, char *out, size_t outlen);  // decimal GB/MB like disk vendors, "1.0 TB"
void utc_stamp(char *out, size_t n, int compact);        // 2026-10-17T12:00:00Z or 20261017T120000Z
double now_s(void);

// ------------------------------------------------------------------ logging and events
// The log goes to stderr (CLI), to the daemon's ring buffer, and to the install log. Events are JSON lines on the
// event fd (apply in the daemon), or nothing.
extern int g_event_fd;   // -1: no events
extern FILE *g_logfile;  // NULL: none
extern struct sb g_install_log;
void logf_(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
#define LOG(...) logf_(__VA_ARGS__)
void emit_event(const char *json);  // one line, without the trailing newline

// ------------------------------------------------------------------ environment (Android or a test root)
struct env {
    const char *root;            // "" on a device; a fixture directory in host tests
    char boot_part_uuid[96];     // ro.boot.boot_part_uuid / --boot-part-uuid
    int live;                    // ro.boot.openbook.live
    int logs_mode;               // ro.boot.openbook.logs (the "save logs" helper owns the stick's ESP)
    char selinux[16];
    int efivars;                 // /sys/firmware/efi/efivars is an efivarfs mount (or --efivars DIR in tests)
    char efivars_dir[512];
};
extern struct env E;
void env_init(const char *root, const char *boot_part_uuid);
void env_set_efivars_dir(const char *dir);  // host tests: a plain directory stands in for efivarfs
void env_path(char *out, size_t n, const char *fmt, ...) __attribute__((format(printf, 3, 4)));
int prop_get(const char *name, char *out, size_t n);  // 0 and out = "" if unset

// ------------------------------------------------------------------ GPT
#define GPT_MAX_PARTS 128
struct gpt_part {
    int index;           // 1-based GPT entry number
    uint8_t type[16], uniq[16];
    uint64_t first, last;  // LBAs, inclusive
    uint64_t attrs;
    char name[73];       // UTF-8 (ASCII subset), from UTF-16
};
struct gpt {
    int valid;
    uint32_t sector;     // logical sector size
    uint64_t sectors;    // device size in sectors
    uint8_t disk_guid[16];
    uint64_t first_usable, last_usable, entries_lba, alt_lba;
    uint32_t n_entries, entry_size;
    int nparts;
    struct gpt_part p[GPT_MAX_PARTS];
    uint8_t *raw_entries;  // n_entries * entry_size, as on disk
    char why[160];         // when !valid
};
int gpt_read(int fd, uint32_t sector, uint64_t sectors, struct gpt *g);  // 0 = a valid primary GPT
void gpt_free(struct gpt *g);
const struct gpt_part *gpt_find(const struct gpt *g, const char *name);
const struct gpt_part *gpt_find_uuid(const struct gpt *g, const char *uuid);
// Write a GPT holding exactly parts[] (a new table, protective MBR included), backup first, then primary.
int gpt_write_new(int fd, uint32_t sector, uint64_t sectors, const uint8_t disk_guid[16], const struct gpt_part *parts,
                  int n);
// Add entries to an existing valid GPT (free slots), backup first, then primary. MBR untouched.
int gpt_write_add(int fd, const struct gpt *g, const struct gpt_part *add, int n);
int gpt_wipe(int fd, uint32_t sector, uint64_t sectors);  // protective MBR, primary and backup GPT zeroed
// type GUIDs
extern const char *const GUID_ESP, *const GUID_XBOOTLDR, *const GUID_LINUX, *const GUID_MSDATA, *const GUID_MSRES,
    *const GUID_MSRECOVERY, *const GUID_SWAP, *const GUID_LVM, *const GUID_LUKS, *const GUID_APFS,
    *const GUID_LINUX_ROOT_X64, *const GUID_LINUX_HOME;
const char *gpt_type_kind(const uint8_t type[16]);  // esp, xbootldr, msdata, linux, ... (PROTOCOL.md)

// ------------------------------------------------------------------ FAT12/16/32 (no kernel mount needed)
struct fat {
    int fd;
    uint64_t off, size;  // the partition, in bytes on fd
    uint32_t bps, spc, cluster_bytes;
    uint32_t reserved, nfats, fat_sectors, root_entries, root_dir_sectors, first_data_sector, total_sectors;
    uint32_t nclusters, root_cluster, fsinfo_sector;
    int type;  // 12, 16, 32
    uint8_t *fatbuf;
    int dirty;
    uint32_t hint;
    char label[12];
};
int fat_format32(int fd, uint64_t off, uint64_t size, uint32_t bps, const char *label, uint32_t volid);
int fat_open(struct fat *f, int fd, uint64_t off, uint64_t size);
void fat_close(struct fat *f);  // flushes FATs and FSInfo if dirty
int fat_flush(struct fat *f);
// Read a whole file (path with '/' separators, case-insensitive). Returns malloc'd data or NULL.
uint8_t *fat_read(struct fat *f, const char *path, uint32_t *len);
int fat_exists(struct fat *f, const char *path, int *is_dir);
int fat_write(struct fat *f, const char *path, const void *data, uint32_t len);  // creates parent dirs, replaces
int fat_mkdirs(struct fat *f, const char *path);
int fat_list(struct fat *f, const char *dir, void (*cb)(const char *name, int is_dir, uint32_t size, void *arg),
             void *arg);
int fat_probe(int fd, uint64_t off, uint64_t size, char *label, size_t labellen);  // 12/16/32 or 0
// Crash-ordered changes for a volume a boot loader reads (openbook-bootsync): the new data and its FAT chain first,
// then the directory entry, then the old chain is freed, with an fsync between each.
int fat_replace(struct fat *f, const char *path, const void *data, uint32_t len);  // creates parent dirs
int fat_rename(struct fat *f, const char *path, const char *new_name);              // in the same directory
int fat_unlink(struct fat *f, const char *path);
uint64_t fat_free_bytes(struct fat *f);

// ------------------------------------------------------------------ disks
struct part_info {
    int index;
    char name[73];
    const char *kind;  // gpt_type_kind / mbr
    char type_guid[37];
    char uuid[37];
    char fs[16];
    char label[64];
    char os[24];
    uint64_t start, bytes;
    int encrypted, mounted;
};
struct free_ext {
    uint64_t start, bytes;  // bytes, 1 MiB aligned
};
struct disk {
    char name[32];       // nvme0n1
    char dev[160];       // device node path
    char syspath[512];   // resolved /sys/block/<name> path
    char by_id[160];     // udev-style, without /dev/disk/by-id/
    char model[96], vendor[64], serial[96], wwn[96];
    char bus[16];        // nvme, usb, sata, mmc, virtio, scsi
    uint64_t size;
    uint32_t sector;
    int removable, read_only, rotational;
    int boot_disk;       // holds the boot_part_uuid partition (the OpenBook stick)
    int mounted;         // a partition is mounted, used by dm, or swap
    int external;        // USB or Thunderbolt and not the boot disk
    char table[8];       // gpt, mbr, none
    struct gpt gpt;
    int nparts;
    struct part_info parts[GPT_MAX_PARTS];
    uint64_t free_bytes;
    struct free_ext largest;
    int esp_index;       // GPT index of the first ESP, 0 if none
    int android_names;   // has partitions named like ours (super, userdata, boot_a, ...)
    int encrypted;
    char os_list[96];    // "Windows,Linux"
    char table_sha256[65];  // primary + backup GPT area (S4)
};
int disks_scan(struct disk **out);  // all whole disks; returns count
void disks_free(struct disk *d, int n);
struct disk *disk_by_id(struct disk *d, int n, const char *by_id);
void disk_json(struct jw *w, const struct disk *d, uint64_t min_bytes);
int disk_open(const struct disk *d, int writable);  // read-only, or O_RDWR|O_EXCL on a block device
int disk_layout_ok(const struct disk *d, const char *layout, uint64_t min_bytes, const char **why);
void disk_table_hash(int fd, const struct disk *d, char out[65]);

// ------------------------------------------------------------------ the stick (install source)
struct source {
    int ok;
    char why[200];
    struct disk *disk;     // the boot disk
    int fd;
    char manifest_text_sha256[65];
    struct jv *manifest;   // openbook/MANIFEST.json
    struct jv *install;    // manifest.install
    const struct gpt_part *esp;
    char label[96], fingerprint[256];
};
int source_open(struct source *s, struct disk *d, int n);
void source_close(struct source *s);

// ------------------------------------------------------------------ app add-ons (addon.c, ANAL-210)
#define ADDON_MAX 4        // per install
#define ADDON_MAX_FILES 8  // per add-on
// The image's catalogue /system_ext/etc/openbook/addons/<name>.json, validated; NULL (and why) if there is none.
struct jv *addon_catalog(const char *name, char *why, size_t wl);
// 1 if the stick's openbook/addons/<name>/ holds every catalogued file at the catalogued size (sha256: check_source).
int addon_on_stick(struct source *s, const struct jv *cat, char *why, size_t wl);
uint64_t addon_bytes(const struct jv *cat);
void addons_json(struct jw *w, const char *key, struct source *s);  // every catalogued add-on, and if the stick has it

// ------------------------------------------------------------------ bring your own Google apps (ANAL-211)
#define GAPPS_SDK 37  // the SDK of the images this engine ships in; ro.build.version.sdk wins when it is set
// gapps.c: check a package the user supplied (LiteGapps layout) and stage what it may install below
// /data/misc/openbook_install/gapps/<manifest sha256>/ with its install manifest gapps.json. Fills w (an open
// object) with the result; 0 if accepted (manifest_sha set).
int gapps_check(const char *path, const char *display_name, struct jw *w, char manifest_sha[65]);
// The staged package by its manifest's sha256 (checked): the parsed manifest, its directory, and its exact text.
struct jv *gapps_load(const char *sha, char *dir, size_t dl, char **text, size_t *tlen, char *why, size_t wl);

// avb.c: vbmeta images, dm-verity hashtrees (avbtool's layout) and AVB footers.
struct avb_ht {
    uint32_t dm_verity_version, data_block_size, hash_block_size, fec_num_roots, flags;
    uint64_t image_size, tree_offset, tree_size, fec_offset, fec_size;
    char hash_alg[33];
    char partition[64];
    uint8_t salt[256], root[64];
    uint32_t salt_len, root_len;
    size_t desc_off, desc_len;  // where the descriptor is in the vbmeta image
};
size_t avb_vbmeta_size(const uint8_t *vb, size_t n);  // header + authentication + auxiliary blocks; 0 if invalid
int avb_find_hashtree(const uint8_t *vb, size_t n, const char *partition, struct avb_ht *ht);
// A copy of the vbmeta image with partition nht->partition's hashtree descriptor replaced by nht, unsigned.
int avb_rebuild_unsigned(const uint8_t *vb, size_t n, const struct avb_ht *nht, uint8_t **out, size_t *olen);
int avb_patch_footer_vbmeta(uint8_t *vb, size_t n, const struct avb_ht *nht);  // a partition's own (unsigned) vbmeta
int avb_read_footer(const uint8_t f[64], uint64_t *orig, uint64_t *vbmeta_off, uint64_t *vbmeta_size);
void avb_footer(uint8_t f[64], uint64_t orig, uint64_t vbmeta_off, uint64_t vbmeta_size);
uint64_t avb_tree_size(uint64_t image_size, uint32_t block_size);
struct ht_builder {
    uint32_t bs;
    uint8_t salt[256];
    size_t salt_len;
    uint64_t blocks, done, tree_size;
    int nlevels;
    uint64_t level_size[16], level_off[16];
    uint8_t *tree;
};
int ht_init(struct ht_builder *h, uint64_t image_size, uint32_t bs, const uint8_t *salt, size_t salt_len);
int ht_add_block(struct ht_builder *h, const uint8_t *block);  // every data block, in order
int ht_finish(struct ht_builder *h, uint8_t root[32]);
void ht_free(struct ht_builder *h);

// lp.c: super's metadata with one partition moved to a single new extent of new_bytes after all the others.
int lp_relocate(const uint8_t *meta, size_t len, const char *part, uint64_t new_bytes, uint8_t **out,
                uint64_t *old_off, uint64_t *new_off, char *why, size_t wl);

// erofs.c: add files to an existing EROFS image, keeping its blocks.
struct emfile {
    const char *rel;  // below the image's root
    uint64_t bytes;
};
struct erofs_merge;
int erofs_merge_plan(int fd, uint64_t off, uint64_t image_bytes, const struct emfile *files, int nfiles,
                     struct erofs_merge **out, char *why, size_t wl);
uint64_t erofs_merge_bytes(const struct erofs_merge *m);
uint64_t erofs_merge_orig_bytes(const struct erofs_merge *m);
int erofs_merge_new_inodes(const struct erofs_merge *m);
int erofs_merge_rewritten_dirs(const struct erofs_merge *m);
// Streams the new image in order through emit (whole blocks); data supplies file f's bytes at pos.
int erofs_merge_write(struct erofs_merge *m, int fd, uint64_t off, struct sha256 *src_hash,
                      int (*data)(void *arg, int file, uint64_t pos, uint8_t *buf, size_t n),
                      int (*emit)(void *arg, const uint8_t *buf, size_t n), void *arg);
void erofs_merge_free(struct erofs_merge *m);

// product.c: the new product partition, vbmeta and super metadata for a plan with a package.
struct gp_stage {
    char path[800];
    char sha256[65];
};
struct gapps_product {
    char sha[65], dir[700];
    struct jv *manifest;
    char *mtext;
    size_t mlen;
    char part[40];                      // product_a
    uint64_t src_off, src_bytes;        // the extent on the stick (absolute offset on the stick)
    char src_sha[65];
    uint64_t old_dst, old_dst_meta, new_dst, dst_abs;  // in the installed super; dst_abs on the target
    uint8_t *vbmeta_src;
    size_t vbmeta_src_len;
    uint8_t *footer_vb;
    size_t footer_vb_len;
    struct avb_ht ht_old, ht_new;
    int nfiles;  // the package's files + gapps-manifest.json
    struct emfile *files;
    struct gp_stage *stage;
    uint64_t gapps_bytes;
    struct erofs_merge *em;
    uint64_t image_bytes, tree_bytes, vbmeta_off, part_bytes;
    uint8_t *lp;
    uint32_t lp_len;
    char lp_sha[65];
    // after gp_build
    char part_sha[65], root_hex[65], vbmeta_digest[65];
    uint8_t *vbmeta_new;
    size_t vbmeta_new_len;
};
int gp_plan(struct gapps_product *g, const char *sha, struct source *src, const struct jv *inst, const uint8_t *meta,
            uint32_t meta_len, const char **code, char *why, size_t wl);
int gp_verify_staged(struct gapps_product *g, void (*progress)(uint64_t), char *err, size_t el);
int gp_build(struct gapps_product *g, int src_fd, int dst_fd, uint64_t super_start, void (*progress)(uint64_t),
             char *err, size_t el);
uint8_t *gp_vbmeta_partition(const struct gapps_product *g, size_t *len);
void gp_json(struct jw *w, const struct gapps_product *g);
void gp_free(struct gapps_product *g);

// ------------------------------------------------------------------ hardware check
void hwinfo_json(struct jw *w, struct disk *d, int n);

// ------------------------------------------------------------------ plan and apply
struct plan_req {
    char image_base[32];  // empty: legacy AOSP request; otherwise openbook-aosp (ANAL-228)
    char target[160];
    char layout[16];      // whole | alongside
    char locale[32];
    char keyboard[32];
    int set_default;
    char addons[ADDON_MAX][32];  // add-ons the user ticked (ANAL-210); none: the plan is as before add-ons existed
    int naddons;
    char gapps[65];  // a checked Google apps package (ANAL-211), by its manifest's sha256; "": as before
    int gapps_confirmed;  // the user confirmed the uncertified-device warning (the app; the CLI's --gapps implies it)
    // seeds: random per plan, kept by apply so the plan can be re-computed exactly
    char disk_guid[37];
    char serialno[17];
    char part_guids[24][37];
};
struct power {
    int ac, battery_pct, have_battery, ok;
    int known;  // 0: power supplies present but unreadable (Android: only the health HAL may read them)
};
void power_read(struct power *p);
// The app's reading (BatteryManager), sent with "apply"; used when power_read() cannot read the supplies.
extern struct power g_power_override;
extern int g_power_override_set;
int plan_seed(struct plan_req *r);
// Compute the plan JSON. Returns 0 and fills *out (and plan_sha256), or -1 with code/why.
int plan_build(const struct plan_req *r, struct disk *disks, int n, struct source *src, struct sb *out,
               char plan_sha256[65], const char **code, char *why, size_t whylen);
int plan_req_from_json(const struct jv *plan, struct plan_req *r);
int plan_req_add_addon(struct plan_req *r, const char *name);  // -1: not a valid name, a duplicate, or too many
int apply_run(const struct plan_req *r, const char *expect_sha256, const char *typed_or_null,
              const char *confirm_disk_or_null, struct sb *result_json);
int normalized_equal(const char *a, const char *b);  // case-insensitive, whitespace ignored
// fsync, then drop the cached blocks of fd's device, so the next reads come from the disk. Before writing the
// stick's ESP: the live system may have mounted that partition since (a different block device, its own cache).
void drop_cache(int fd);

// ------------------------------------------------------------------ UEFI boot entries (efivar.c)
struct nvram_result {
    int created;        // the Boot#### variable exists and reads back as written
    int num;            // its number, -1 if none
    const char *order;  // where it went in BootOrder: "first", "last" or "failed"; NULL if not created
    char why[200];
};
// Create one Boot#### entry: desc -> HD(partnum, start_lba, size_lba, guid)/path, and add it to BootOrder: first with
// the user's consent (set_first, S11), otherwise last. No other variable or entry changes.
int nvram_add_entry(const char *desc, uint32_t partnum, uint64_t start_lba, uint64_t size_lba, const uint8_t guid[16],
                    const char *path, int set_first, struct nvram_result *res);
void nvram_json(struct jw *w);  // "nvram": BootOrder, BootCurrent and every Boot#### entry, read-only

// ------------------------------------------------------------------ daemon
int daemon_main(const char *socket_path);
