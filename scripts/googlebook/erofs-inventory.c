// SPDX-License-Identifier: Apache-2.0
// Read-only inode/xattr inventory using the same EROFS library as the builder.
// Paths and xattrs are hex encoded, avoiding newline/escaping ambiguities.
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "erofs/config.h"
#include "erofs/io.h"
#include "erofs/dir.h"
#include "erofs/xattr.h"

static struct erofs_sb_info sbi;
struct walk { struct erofs_dir_context ctx; const char *path; };
static void hex(const void *v, size_t n) {
    const unsigned char *s = v;
    for (size_t i = 0; i < n; ++i) printf("%02x", s[i]);
}
static void must(int rc) {
    if (rc < 0) { fprintf(stderr, "erofs error %d\n", rc); exit(1); }
}
static void visit(erofs_nid_t nid, const char *path);
static int child(struct erofs_dir_context *ctx) {
    if (ctx->dot_dotdot) return 0;
    const char *parent = ((struct walk *)ctx)->path;
    char *path = NULL;
    if (asprintf(&path, "%s/%.*s", parent, ctx->de_namelen, ctx->dname) < 0) exit(1);
    visit(ctx->de_nid, path); free(path); return 0;
}
static void visit(erofs_nid_t nid, const char *path) {
    struct erofs_inode ino = {.sbi = &sbi, .nid = nid};
    must(erofs_read_inode_from_disk(&ino));
    printf("I "); hex(path, strlen(path));
    printf(" %u %u %u %u %llu %llu %u\n", ino.i_mode, ino.i_uid, ino.i_gid,
           ino.i_nlink, (unsigned long long)(S_ISDIR(ino.i_mode) ? 0 : ino.i_size),
           (unsigned long long)ino.i_mtime, ino.i_mtime_nsec);
    int len = erofs_listxattr(&ino, NULL, 0); must(len);
    char *names = malloc(len ? len : 1); if (!names) exit(1);
    must(erofs_listxattr(&ino, names, len));
    for (int at = 0; at < len; at += strlen(names + at) + 1) {
        int size = erofs_getxattr(&ino, names + at, NULL, 0); must(size);
        char *value = malloc(size ? size : 1); if (!value) exit(1);
        must(erofs_getxattr(&ino, names + at, value, size));
        printf("X "); hex(path, strlen(path)); printf(" "); hex(names + at, strlen(names + at));
        printf(" "); hex(value, size); printf("\n"); free(value);
    }
    free(names);
    if (S_ISDIR(ino.i_mode)) {
        struct walk w = {.ctx = {.dir = &ino, .cb = child}, .path = path};
        must(erofs_iterate_dir(&w.ctx, false));
    }
    free(ino.xattr_shared_xattrs);
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    erofs_init_configure();
    must(erofs_dev_open(&sbi, argv[1], O_RDONLY));
    must(erofs_read_superblock(&sbi));
    visit(sbi.root_nid, "");
    erofs_put_super(&sbi); erofs_dev_close(&sbi); erofs_exit_configure();
    return 0;
}
