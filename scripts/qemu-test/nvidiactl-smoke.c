// SPDX-License-Identifier: Apache-2.0
// ANAL-297: the first ioctls into NVIDIA's open kernel driver, for the QEMU check (scripts/nvidia-open-guest-check.sh),
// where there is no NVIDIA GPU and a test build of nvidia.ko stays loaded anyway. Freestanding (no libc), so one
// static binary runs in any Android x86_64 guest:
//   clang --target=x86_64-linux-gnu -static -nostdlib -ffreestanding -fno-stack-protector -O2 -o nvidiactl-smoke \
//     nvidiactl-smoke.c
// Steps: open /dev/nvidiactl; NV_ESC_CHECK_VERSION_STR (strict) with the driver's own version; NV_ESC_RM_ALLOC of an
// RM client (NV01_ROOT_CLIENT) and NV_ESC_RM_FREE of it, which run NVIDIA's resource server and its dispatch, the
// code built with kCFI hashes but no kCFI checks (kernel/devices/anybook/nvidia_open/kcfi-hash-only.txt); open
// /dev/nvidia-modeset. Layouts from open-gpu-kernel-modules (nv-ioctl.h, nv-ioctl-numbers.h, nv_escape.h, nvos.h).
// Prints one ok/FAIL line per step; exit status is the number of failures. Only for a guest: never run it against a
// host whose NVIDIA GPU is in use.
typedef unsigned int u32;
typedef unsigned long long u64;

#define IOWR(type, nr, size) ((3u << 30) | ((u32)(size) << 16) | ((u32)(type) << 8) | (u32)(nr))
#define NV_IOCTL_MAGIC 'F'
#define NV_ESC_CHECK_VERSION_STR (200 + 10)
#define NV_ESC_RM_FREE 0x29
#define NV_ESC_RM_ALLOC 0x2B
#define NV01_ROOT_CLIENT 0x41
#ifndef NV_VERSION
#define NV_VERSION "615.78.08"
#endif

struct rm_api_version { u32 cmd; u32 reply; char version[64]; };                  // nv_ioctl_rm_api_version_t
struct nvos21 { u32 hRoot, hObjectParent, hObjectNew, hClass; u64 pAllocParms; u32 paramsSize, status; };
struct nvos00 { u32 hRoot, hObjectParent, hObjectOld, status; };
_Static_assert(sizeof(struct nvos21) == 32, "NVOS21_PARAMETERS");
_Static_assert(sizeof(struct nvos00) == 16, "NVOS00_PARAMETERS");

static long sys3(long n, long a, long b, long c)
{
    long r;
    __asm__ volatile("syscall" : "=a"(r) : "a"(n), "D"(a), "S"(b), "d"(c) : "rcx", "r11", "memory");
    return r;
}
static long sys_open(const char *p, long flags) { return sys3(257, -100, (long)p, flags); }   // openat(AT_FDCWD)
static long sys_ioctl(long fd, u32 cmd, void *arg) { return sys3(16, fd, cmd, (long)arg); }
static void sys_close(long fd) { sys3(3, fd, 0, 0); }

static unsigned long len(const char *s) { unsigned long n = 0; while (s[n]) n++; return n; }
static void out(const char *s) { sys3(1, 1, (long)s, len(s)); }
static void outn(long v)
{
    char b[24], *p = b + sizeof(b) - 1;
    int neg = v < 0;
    unsigned long u = neg ? -(unsigned long)v : (unsigned long)v;
    *p = 0;
    do { *--p = (char)('0' + u % 10); u /= 10; } while (u);
    if (neg) *--p = '-';
    out(p);
}
static void outx(u32 v)
{
    char b[11] = "0x00000000";
    for (int i = 0; i < 8; i++) b[9 - i] = "0123456789abcdef"[(v >> (4 * i)) & 15];
    out(b);
}
static int fails;
static void step(int ok, const char *what)
{
    out(ok ? "ok   " : "FAIL "); out(what); out("\n");
    if (!ok) fails++;
}

int main(void)
{
    long fd = sys_open("/dev/nvidiactl", 02 | 02000000);   // O_RDWR | O_CLOEXEC
    out("open /dev/nvidiactl: "); outn(fd); out("\n");
    step(fd >= 0, "open /dev/nvidiactl");
    if (fd >= 0) {
        struct rm_api_version v = { 0 };
        for (unsigned long i = 0; i < len(NV_VERSION); i++) v.version[i] = NV_VERSION[i];
        long r = sys_ioctl(fd, IOWR(NV_IOCTL_MAGIC, NV_ESC_CHECK_VERSION_STR, sizeof(v)), &v);
        out("CHECK_VERSION_STR " NV_VERSION ": rc="); outn(r); out(" reply="); outn(v.reply);
        out(" driver="); v.version[63] = 0; out(v.version); out("\n");
        step(r == 0 && v.reply == 1, "RM accepts this client's version (strict)");

        struct nvos21 a = { 0 };
        a.hClass = NV01_ROOT_CLIENT;
        r = sys_ioctl(fd, IOWR(NV_IOCTL_MAGIC, NV_ESC_RM_ALLOC, sizeof(a)), &a);
        out("RM_ALLOC NV01_ROOT_CLIENT: rc="); outn(r); out(" status="); outx(a.status);
        out(" hClient="); outx(a.hObjectNew); out("\n");
        step(r == 0 && a.status == 0 && a.hObjectNew != 0, "RM allocates a client");

        struct nvos00 f = { a.hObjectNew, a.hObjectNew, a.hObjectNew, 0 };
        r = sys_ioctl(fd, IOWR(NV_IOCTL_MAGIC, NV_ESC_RM_FREE, sizeof(f)), &f);
        out("RM_FREE: rc="); outn(r); out(" status="); outx(f.status); out("\n");
        step(r == 0 && f.status == 0, "RM frees the client");
        sys_close(fd);
    }
    long m = sys_open("/dev/nvidia-modeset", 02 | 02000000);
    out("open /dev/nvidia-modeset: "); outn(m); out("\n");
    step(m >= 0, "open /dev/nvidia-modeset");
    if (m >= 0) sys_close(m);
    out("nvidiactl-smoke: "); outn(fails); out(" failure(s)\n");
    return fails;
}

// The entry point: the kernel starts us with %rsp 16-byte aligned, and the call to main must keep the ABI's alignment.
__asm__(".globl _start\n"
        "_start:\n"
        "    xor %ebp, %ebp\n"
        "    and $-16, %rsp\n"
        "    call main\n"
        "    mov %eax, %edi\n"
        "    mov $60, %eax\n"      // exit
        "    syscall\n"
        "    hlt\n");
