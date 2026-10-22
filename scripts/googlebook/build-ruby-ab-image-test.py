#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit checks for build-ruby-ab-image.py: bootsync-identical padding and boot image extraction.

The assembled image is judged by openbook-bootsync itself (`status` reports slot A
in_sync); these cover the extraction rules on synthetic v4 images."""
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location("abimg", Path(__file__).with_name("build-ruby-ab-image.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def boot_v4(kernel=b"", ramdisk=b""):
    h = bytearray(4096)
    h[:8] = b"ANDROID!"
    struct.pack_into("<II", h, 8, len(kernel), len(ramdisk))
    struct.pack_into("<I", h, 40, 4)
    body = kernel + b"\0" * (-len(kernel) % 4096)
    return bytes(h) + body + ramdisk


def vendor_boot_v4(fragments, bootconfig=b"androidboot.hardware=openbook\n", cmdline=b"bootconfig"):
    page = 4096
    h = bytearray(page)
    h[:8] = b"VNDRBOOT"
    struct.pack_into("<II", h, 8, 4, page)
    h[28:28 + len(cmdline)] = cmdline
    section = b"".join(fragments)
    es = 108
    table = bytearray()
    off = 0
    for frag in fragments:
        entry = bytearray(es)
        struct.pack_into("<II", entry, 0, len(frag), off)
        table += entry
        off += len(frag)
    struct.pack_into("<I", h, 24, len(section))       # vendor ramdisk size
    struct.pack_into("<I", h, 2096, 2128)              # header size
    struct.pack_into("<I", h, 2100, 0)                 # dtb size
    struct.pack_into("<IIII", h, 2112, len(table), len(fragments), es, len(bootconfig))
    def pad(b):
        return b + b"\0" * (-len(b) % page)
    return bytes(h) + pad(section) + pad(bytes(table)) + pad(bootconfig)


class Padding(unittest.TestCase):
    def test_matches_bootsync_padded(self):
        self.assertEqual(m.padded(b"abcd"), b"abcd")                    # aligned: unchanged
        self.assertEqual(m.padded(b"abc"), b"abc" + b"\0" * 5)          # 1 pad + 4
        self.assertEqual(m.padded(b"a"), b"a" + b"\0" * 7)              # 3 pad + 4


class Extract(unittest.TestCase):
    def test_kernel_ramdisks_and_static_bootconfig(self):
        boot = boot_v4(kernel=b"K" * 5000)
        init_boot = boot_v4(ramdisk=b"R" * 13)
        vend = vendor_boot_v4([b"V1" * 3, b"V2V"])
        kernel, ramdisk, vram, vcmd, vbc = m.extract_boot(boot, init_boot, vend)
        self.assertEqual(kernel, b"K" * 5000)
        self.assertEqual(ramdisk, m.padded(b"R" * 13))
        self.assertEqual(vram, m.padded(b"V1" * 3) + m.padded(b"V2V"))   # each fragment padded, in order
        self.assertEqual(vcmd, "bootconfig")
        self.assertEqual(vbc, {"androidboot.hardware": "openbook"})

    def test_refuses_wrong_formats(self):
        good_boot, good_init = boot_v4(kernel=b"K"), boot_v4(ramdisk=b"R")
        vend = vendor_boot_v4([b"V"])
        with self.assertRaisesRegex(ValueError, "boot_a"):
            m.extract_boot(b"\0" * 8192, good_init, vend)
        with self.assertRaisesRegex(ValueError, "init_boot_a"):
            m.extract_boot(good_boot, b"\0" * 8192, vend)
        with self.assertRaisesRegex(ValueError, "vendor_boot_a"):
            m.extract_boot(good_boot, good_init, b"\0" * 8192)


if __name__ == "__main__":
    unittest.main()
