// SPDX-License-Identifier: Apache-2.0
// Disposable VM only. Runs as hal_camera_default under the candidate policy.
// Exit 0 means the kernel permitted the operations that camera23 failed on the
// G14. This does not open a video device or establish camera frame delivery.
#define _GNU_SOURCE
#include <fcntl.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/xattr.h>
#include <unistd.h>

static int exact_file(const char *path, const char *expected) {
    char value[128] = {0};
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;
    ssize_t n = read(fd, value, sizeof(value) - 1);
    close(fd);
    if (n < 0) return 0;
    // proc attr/current may include a trailing newline.
    value[strcspn(value, "\n")] = 0;
    return strcmp(value, expected) == 0;
}

int main(void) {
    if (!exact_file("/proc/self/attr/current", "u:r:hal_camera_default:s0")) return 10;
    // The HAL may not read selinuxfs. Verify enforcing from the VM's existing
    // shell diagnostics and compiled policy, without a test-only allow rule.
    // Match the failed FMQ allocation size in the physical camera23 log.
    const size_t size = 266240;
    int fd = memfd_create("MessageQueue", MFD_CLOEXEC | MFD_ALLOW_SEALING);
    if (fd < 0) return 20;
    if (ftruncate(fd, size)) return 21;
    char label[128] = {0};
    ssize_t n = fgetxattr(fd, "security.selinux", label, sizeof(label) - 1);
    if (n < 0) return 22;
    if (strcmp(label, "u:object_r:hal_camera_default_tmpfs:s0")) return 23;
    unsigned char *writer = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (writer == MAP_FAILED) return 24;
    unsigned char *reader = mmap(NULL, size, PROT_READ, MAP_SHARED, fd, 0);
    if (reader == MAP_FAILED) return 25;
    for (size_t i = 0; i < size; ++i) writer[i] = (unsigned char)(i * 17 + 3);
    for (size_t i = 0; i < size; ++i)
        if (reader[i] != (unsigned char)(i * 17 + 3)) return 26;
    munmap(reader, size);
    munmap(writer, size);
    close(fd);
    return 0;
}
