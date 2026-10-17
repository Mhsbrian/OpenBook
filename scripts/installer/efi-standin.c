// SPDX-License-Identifier: Apache-2.0
//
// A stand-in for "Windows Boot Manager" in the QEMU tests: wizard-qemu.py mkwin puts it at
// EFI/Microsoft/Boot/bootmgfw.efi (and EFI/BOOT/BOOTX64.EFI) on the Windows-like disk. A UEFI application that prints
// which Boot#### started it and the firmware's BootOrder on the console (OVMF mirrors it on the serial port), waits
// 3 s and returns EFI_SUCCESS. EDK2's boot manager then shows its boot menu, which lists the BootOrder entries.
// Freestanding: no headers, no libraries.
//
//   clang --target=x86_64-unknown-windows -ffreestanding -fshort-wchar -mno-red-zone -nostdlib -fuse-ld=lld \
//         -Wl,-entry:efi_main -Wl,-subsystem:efi_application -o bootmgfw.efi efi-standin.c
typedef unsigned long long u64;
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef u64 status;

struct header {
    u64 signature;
    u32 revision, size, crc32, reserved;
};
struct text_out {
    void *reset;
    status (*output_string)(struct text_out *self, const u16 *s);
};
struct guid {
    u32 a;
    u16 b, c;
    u8 d[8];
};
struct runtime {
    struct header h;
    void *get_time, *set_time, *get_wakeup_time, *set_wakeup_time, *set_virtual_address_map, *convert_pointer;
    status (*get_variable)(const u16 *name, const struct guid *vendor, u32 *attributes, u64 *size, void *data);
};
struct boot {
    struct header h;
    void *before_stall[28];  // RaiseTPL ... GetNextMonotonicCount
    status (*stall)(u64 microseconds);
};
struct system_table {
    struct header h;
    u16 *firmware_vendor;
    u32 firmware_revision;
    void *console_in_handle, *con_in, *console_out_handle;
    struct text_out *con_out;
    void *standard_error_handle, *std_err;
    struct runtime *runtime;
    struct boot *boot;
};

static const struct guid efi_global = {0x8be4df61, 0x93ca, 0x11d2, {0xaa, 0x0d, 0x00, 0xe0, 0x98, 0x03, 0x2b, 0x8c}};

static void put(u16 *o, int *n, const char *s) {
    while (*s) o[(*n)++] = (u8)*s++;
}

static void hex4(u16 *o, int *n, u16 v) {
    for (int i = 12; i >= 0; i -= 4) o[(*n)++] = "0123456789ABCDEF"[(v >> i) & 15];
}

status efi_main(void *image, struct system_table *st) {
    u16 line[512], cur, order[128];
    int n = 0;
    u32 attr;
    u64 size = sizeof cur;
    put(line, &n, "\r\nOPENBOOK-TEST windows-standin started: BootCurrent=");
    if (st->runtime->get_variable(u"BootCurrent", &efi_global, &attr, &size, &cur) == 0) hex4(line, &n, cur);
    else put(line, &n, "none");
    put(line, &n, " BootOrder=");
    size = sizeof order;
    if (st->runtime->get_variable(u"BootOrder", &efi_global, &attr, &size, order) == 0) {
        for (u64 i = 0; i < size / 2; i++) {
            if (i) put(line, &n, ",");
            hex4(line, &n, order[i]);
        }
    } else {
        put(line, &n, "none");
    }
    put(line, &n, "\r\nOPENBOOK-TEST windows-standin: returning to the firmware\r\n");
    line[n] = 0;
    st->con_out->output_string(st->con_out, line);
    st->boot->stall(3000000);
    return 0;
}
