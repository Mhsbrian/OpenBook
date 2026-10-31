// SPDX-License-Identifier: Apache-2.0
// gfx-nsbind: run COMMAND with FILE bind-mounted over TARGET in a mount namespace of its own (ANAL-177). The
// graphics check uses it to run dEQP-VK through Android's own Vulkan loader against a second RADV build (Mesa's
// android-strict off, Vulkan 1.4) without touching the system: the bind mount exists only for COMMAND and its
// children, never propagates back (the new namespace is made a recursive slave first), and ends with them.
// Root only. Build: gcc -static -O2 -Wall -o gfx-nsbind gfx-nsbind.c
//   gfx-nsbind FILE TARGET COMMAND [ARG...]
#define _GNU_SOURCE
#include <errno.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <sys/mount.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 4) {
        fprintf(stderr, "usage: gfx-nsbind FILE TARGET COMMAND [ARG...]\n");
        return 2;
    }
    if (unshare(CLONE_NEWNS)) { fprintf(stderr, "gfx-nsbind: unshare: %s\n", strerror(errno)); return 1; }
    if (mount(NULL, "/", NULL, MS_REC | MS_SLAVE, NULL)) {
        fprintf(stderr, "gfx-nsbind: make / a recursive slave: %s\n", strerror(errno));
        return 1;
    }
    if (mount(argv[1], argv[2], NULL, MS_BIND, NULL)) {
        fprintf(stderr, "gfx-nsbind: bind %s over %s: %s\n", argv[1], argv[2], strerror(errno));
        return 1;
    }
    execvp(argv[3], argv + 3);
    fprintf(stderr, "gfx-nsbind: exec %s: %s\n", argv[3], strerror(errno));
    return 127;
}
