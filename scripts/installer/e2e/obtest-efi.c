// SPDX-License-Identifier: Apache-2.0
// Test-only UEFI apps for the installer's end-to-end runs in QEMU/OVMF (ANAL-192, scripts/installer/e2e-qemu.sh).
// Never shipped. Freestanding C, built with the host gcc and the PE linker (ld -m i386pep); no gnu-efi, no edk2.
//
//   -DOBTEST_MARK=\"NAME\"   a stand-in for another OS's boot manager (e.g. Windows Boot Manager on a Windows-like
//                           ESP): prints "OBTEST-MARK NAME <the file it was started from>" on the console (OVMF
//                           mirrors it to the serial port) and powers the machine off.
//   -DOBTEST_ADDBOOT         what a user does in the firmware setup for an alongside install, where OpenBook adds no
//                           firmware boot entry (no efivarfs in our kernel, docs/installer.md 12.2): finds the
//                           filesystem holding \EFI\OpenBook\systemd-bootx64.efi, writes Boot1000 "OpenBook" for it,
//                           puts it first in BootOrder, prints "OBTEST-ADDBOOT ok ..." and powers off.
#include <stddef.h>
#include <stdint.h>

#define EFIAPI __attribute__((ms_abi))
typedef uint64_t UINTN;
typedef UINTN EFI_STATUS;
typedef void *EFI_HANDLE;
typedef uint16_t CHAR16;
typedef struct { uint32_t a; uint16_t b, c; uint8_t d[8]; } EFI_GUID;
#define EFI_ERR(s) ((s) >> 63)

typedef struct { uint64_t sig; uint32_t rev, size, crc, reserved; } EFI_TABLE_HEADER;
typedef struct OUT {
    void *reset;
    EFI_STATUS(EFIAPI *output_string)(struct OUT *, const CHAR16 *);
} OUT;
typedef struct {
    EFI_TABLE_HEADER hdr;
    void *get_time, *set_time, *get_wakeup_time, *set_wakeup_time, *set_virtual_address_map, *convert_pointer;
    EFI_STATUS(EFIAPI *get_variable)(const CHAR16 *, const EFI_GUID *, uint32_t *, UINTN *, void *);
    void *get_next_variable_name;
    EFI_STATUS(EFIAPI *set_variable)(const CHAR16 *, const EFI_GUID *, uint32_t, UINTN, const void *);
    void *get_next_high_monotonic_count;
    void(EFIAPI *reset_system)(int, EFI_STATUS, UINTN, void *);
} RT;
typedef struct {
    EFI_TABLE_HEADER hdr;
    void *raise_tpl, *restore_tpl, *allocate_pages, *free_pages, *get_memory_map;
    EFI_STATUS(EFIAPI *allocate_pool)(int, UINTN, void **);
    EFI_STATUS(EFIAPI *free_pool)(void *);
    void *create_event, *set_timer, *wait_for_event, *signal_event, *close_event, *check_event;
    void *install_protocol_interface, *reinstall_protocol_interface, *uninstall_protocol_interface;
    EFI_STATUS(EFIAPI *handle_protocol)(EFI_HANDLE, const EFI_GUID *, void **);
    void *reserved, *register_protocol_notify, *locate_handle, *locate_device_path, *install_configuration_table;
    void *load_image, *start_image, *exit, *unload_image, *exit_boot_services, *get_next_monotonic_count;
    EFI_STATUS(EFIAPI *stall)(UINTN);
    void *set_watchdog_timer, *connect_controller, *disconnect_controller, *open_protocol, *close_protocol;
    void *open_protocol_information, *protocols_per_handle;
    EFI_STATUS(EFIAPI *locate_handle_buffer)(int, const EFI_GUID *, void *, UINTN *, EFI_HANDLE **);
} BS;
typedef struct {
    EFI_TABLE_HEADER hdr;
    CHAR16 *vendor;
    uint32_t revision;
    EFI_HANDLE con_in_handle;
    void *con_in;
    EFI_HANDLE con_out_handle;
    OUT *con_out;
    EFI_HANDLE std_err_handle;
    OUT *std_err;
    RT *rt;
    BS *bs;
} ST;
typedef struct FILE {
    uint64_t revision;
    EFI_STATUS(EFIAPI *open)(struct FILE *, struct FILE **, const CHAR16 *, uint64_t, uint64_t);
    EFI_STATUS(EFIAPI *close)(struct FILE *);
} FILE;
typedef struct SFS {
    uint64_t revision;
    EFI_STATUS(EFIAPI *open_volume)(struct SFS *, FILE **);
} SFS;
typedef struct {
    uint32_t revision;
    EFI_HANDLE parent;
    ST *system_table;
    EFI_HANDLE device;
    uint8_t *file_path;
} LOADED_IMAGE;

static const EFI_GUID __attribute__((unused)) SFS_GUID = {0x964e5b22, 0x6459, 0x11d2, {0x8e, 0x39, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}};
static const EFI_GUID __attribute__((unused)) DP_GUID = {0x09576e91, 0x6d3f, 0x11d2, {0x8e, 0x39, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}};
static const EFI_GUID __attribute__((unused)) LI_GUID = {0x5b1b31a1, 0x9562, 0x11d2, {0x8e, 0x3f, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}};
static const EFI_GUID __attribute__((unused)) GLOBAL = {0x8be4df61, 0x93ca, 0x11d2, {0xaa, 0x0d, 0x00, 0xe0, 0x98, 0x03, 0x2b, 0x8c}};

static ST *g;

// gcc may emit these even when freestanding.
void *memset(void *d, int c, size_t n) {
    for (size_t i = 0; i < n; i++) ((uint8_t *)d)[i] = (uint8_t)c;
    return d;
}
void *memcpy(void *d, const void *s, size_t n) {
    for (size_t i = 0; i < n; i++) ((uint8_t *)d)[i] = ((const uint8_t *)s)[i];
    return d;
}

static void put(const char *s) {  // ASCII to UCS-2, in chunks
    CHAR16 b[128];
    while (*s) {
        unsigned n = 0;
        while (*s && n < 120) {
            if (*s == '\n') b[n++] = '\r';
            b[n++] = (unsigned char)*s++;
        }
        b[n] = 0;
        g->con_out->output_string(g->con_out, b);
    }
}

static __attribute__((unused)) void put_hex(uint64_t v) {
    char b[19] = "0x", *p = b + 2;
    for (int i = 60; i >= 0; i -= 4) *p++ = "0123456789abcdef"[(v >> i) & 15];
    *p = 0;
    put(b);
}

// The file path nodes (type 4, subtype 4) of a device path, as ASCII.
static void put_file_path(const uint8_t *dp) {
    for (int guard = 0; dp && guard < 64; guard++) {
        uint16_t len = dp[2] | dp[3] << 8;
        if (dp[0] == 0x7f || len < 4) break;
        if (dp[0] == 4 && dp[1] == 4) {
            char b[256];
            unsigned n = 0;
            for (unsigned i = 4; i + 1 < len && n < sizeof b - 1; i += 2) {
                uint16_t c = dp[i] | dp[i + 1] << 8;
                if (!c) break;
                b[n++] = c < 128 ? (char)c : '?';
            }
            b[n] = 0;
            put(b);
        }
        dp += len;
    }
}

static void off(void) {
    g->bs->stall(500000);
    g->rt->reset_system(2 /* EfiResetShutdown */, 0, 0, NULL);
}

#ifdef OBTEST_ADDBOOT
static const CHAR16 TARGET[] = u"\\EFI\\OpenBook\\systemd-bootx64.efi";

static UINTN dp_len(const uint8_t *dp) {  // without the end node
    UINTN n = 0;
    for (int guard = 0; guard < 64; guard++) {
        uint16_t len = dp[n + 2] | dp[n + 3] << 8;
        if (dp[n] == 0x7f || len < 4) break;
        n += len;
    }
    return n;
}

static EFI_STATUS add_boot(void) {
    UINTN n = 0;
    EFI_HANDLE *hs = NULL;
    EFI_STATUS s = g->bs->locate_handle_buffer(2 /* ByProtocol */, &SFS_GUID, NULL, &n, &hs);
    if (EFI_ERR(s)) return s;
    for (UINTN i = 0; i < n; i++) {
        SFS *fs;
        FILE *root, *f;
        uint8_t *dp;
        if (EFI_ERR(g->bs->handle_protocol(hs[i], &SFS_GUID, (void **)&fs)) || EFI_ERR(fs->open_volume(fs, &root)))
            continue;
        s = root->open(root, &f, TARGET, 1 /* read */, 0);
        if (EFI_ERR(s)) {
            root->close(root);
            continue;
        }
        f->close(f);
        root->close(root);
        if (EFI_ERR(g->bs->handle_protocol(hs[i], &DP_GUID, (void **)&dp))) continue;
        // EFI_LOAD_OPTION: attributes, FilePathListLength, Description, FilePathList (partition path + file + end)
        static uint8_t opt[1024];
        static const CHAR16 desc[] = u"OpenBook";
        UINTN pl = dp_len(dp), fl = 4 + sizeof TARGET, total;
        uint8_t *p = opt;
        *(uint32_t *)p = 1; /* LOAD_OPTION_ACTIVE */
        p += 4;
        *(uint16_t *)p = (uint16_t)(pl + fl + 4);
        p += 2;
        for (unsigned k = 0; k < sizeof desc; k++) *p++ = ((const uint8_t *)desc)[k];
        for (UINTN k = 0; k < pl; k++) *p++ = dp[k];
        *p++ = 4, *p++ = 4, *p++ = (uint8_t)fl, *p++ = (uint8_t)(fl >> 8);
        for (unsigned k = 0; k < sizeof TARGET; k++) *p++ = ((const uint8_t *)TARGET)[k];
        *p++ = 0x7f, *p++ = 0xff, *p++ = 4, *p++ = 0;
        total = (UINTN)(p - opt);
        s = g->rt->set_variable(u"Boot1000", &GLOBAL, 7 /* NV|BS|RT */, total, opt);
        if (EFI_ERR(s)) return s;
        uint16_t order[64];
        UINTN osz = sizeof order - 2;
        uint32_t attr;
        if (EFI_ERR(g->rt->get_variable(u"BootOrder", &GLOBAL, &attr, &osz, order + 1))) osz = 0;
        order[0] = 0x1000;
        UINTN m = 1;
        for (UINTN k = 1; k <= osz / 2; k++)
            if (order[k] != 0x1000) order[m++] = order[k];
        s = g->rt->set_variable(u"BootOrder", &GLOBAL, 7, m * 2, order);
        if (EFI_ERR(s)) return s;
        put("OBTEST-ADDBOOT ok: Boot1000 \"OpenBook\" -> ");
        put_file_path(opt + 6 + sizeof desc);
        put(", first of ");
        put_hex(m);
        put(" in BootOrder\n");
        return 0;
    }
    return 14; /* EFI_NOT_FOUND */
}
#endif

EFI_STATUS EFIAPI efi_main(EFI_HANDLE image, ST *st) {
    g = st;
#ifdef OBTEST_MARK
    LOADED_IMAGE *li = NULL;
    put("\nOBTEST-MARK " OBTEST_MARK " ");
    if (!EFI_ERR(g->bs->handle_protocol(image, &LI_GUID, (void **)&li)) && li) put_file_path(li->file_path);
    put("\n");
#endif
#ifdef OBTEST_ADDBOOT
    (void)image;
    EFI_STATUS s = add_boot();
    if (s) {
        put("OBTEST-ADDBOOT failed: ");
        put_hex(s);
        put("\n");
    }
#endif
    off();
    return 0;
}
