// SPDX-License-Identifier: Apache-2.0
// Regular-file FAT fixture only. No physical devices or root needed.
#define main logger_main
#include "usb-log.c"
#undef main
#include <assert.h>
int main(int argc, char **argv) {
    assert(argc == 2);
    assert(field("PARTNAME=EFI\nPARTUUID=abcd\n", "PARTNAME", "EFI"));
    assert(field("PARTUUID=ABCD\n", "PARTUUID", "abcd"));
    assert(!field("NOTPARTUUID=abcd\n", "PARTUUID", "abcd"));
    assert(!field("PARTUUID=abcde\n", "PARTUUID", "abcd"));
    assert(!field("PARTNAME=EFIX\n", "PARTNAME", "EFI"));
    assert(!field("PARTUUID=abcd\nPARTUUID=abcd", "PARTUUID", "abcd"));
    int fd = open(argv[1], O_CREAT | O_EXCL | O_RDWR, 0600);
    assert(fd >= 0 && !ftruncate(fd, 64 * MiB));
    assert(!fat_format32(fd, 0, 64 * MiB, 512, "LOGTEST", 1));
    struct fat f;
    assert(!fat_open(&f, fd, 0, 64 * MiB));
    strcpy(session, "openbook/logs/ruby-test");
    assert(save_fat(&f, "test.txt", "data", 4)); // missing research marker
    const char *bad = "{\"schema\": \"openbook-ruby-live-research/2\", \"installable\": false}";
    assert(!fat_replace(&f, "ruby/RESEARCH.json", bad, strlen(bad)));
    assert(save_fat(&f, "test.txt", "data", 4)); // incompatible schema
    const char *good = "{\"schema\": \"openbook-ruby-live-research/1\", \"installable\": false}";
    assert(!fat_replace(&f, "ruby/RESEARCH.json", good, strlen(good)));
    assert(!save_fat(&f, "test.txt", "data", 4));
    assert(save_fat(&f, "test.txt", "REPLACED", 8)); // preserve previous evidence
    uint32_t n;
    char *v = (char *)fat_read(&f, "openbook/logs/ruby-test/test.txt", &n);
    assert(v && n == 4 && !memcmp(v, "data", 4)); free(v);
    assert(save_fat(&f, "large.txt", "x", CHUNK + 1));
    saved = LIMIT - 1;
    assert(save_fat(&f, "limit.txt", "xx", 2));
    saved = 0;
    char *fill = calloc(1, 33 * MiB);
    assert(fill && !fat_replace(&f, "fill", fill, 33 * MiB)); free(fill);
    assert(save_fat(&f, "reserve.txt", "x", 1)); // preserve bootloader space
    assert(!fat_exists(&f, "openbook/logs/ruby-test/reserve.txt", NULL));
    assert(!fat_flush(&f)); fat_close(&f); close(fd);
    puts("USB log FAT checks passed: identity marker, schema, immutable evidence, chunk/session caps, reserve");
    return 0;
}
