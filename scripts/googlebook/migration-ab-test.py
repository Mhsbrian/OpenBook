#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Two-slot fresh install (migrate.install_ab) and its planner's helpers, on synthetic regular files only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = load("migration", "migrate.py")
b = load("ab_install", "build-ruby-ab-install.py")
MIB = m.MIB
EFI_TYPE, LINUX_TYPE = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b", "0fc63daf-8483-4772-8e79-3d69d8477de4"
LPTOOLS = Path.home() / "anybook/aosp/src/out/host/linux-x86"


def rows_at(spec, uuids):
    rows, at = [], MIB
    for name, mib in spec:
        rows.append(dict(name=name, type=EFI_TYPE if name == "EFI" else LINUX_TYPE, partuuid=uuids[name],
                         offset=at, length=mib * MIB))
        at += mib * MIB
    return rows


def write_gpt(path, rows, size):
    with patch.object(m, "AB_MIN_USERDATA", MIB):
        _, headers = m.ab_target_gpt(dict(partitions=rows, first_usable_lba=34,
                                          disk_guid="5f1b8c2e-0d9a-4e47-9a43-1f9d2b7c6e01"), size)
    fd = os.open(path, os.O_RDWR)
    try:
        for offset, data in headers:
            m.write_at(fd, offset, data)
    finally:
        os.close(fd)


class TwoSlotInstall(unittest.TestCase):
    USB = [("EFI", 2), ("misc", 1), ("boot_a", 2), ("init_boot_a", 1), ("vendor_boot_a", 1),
           ("vbmeta_a", 1), ("metadata", 1), ("super", 4), ("userdata", 1)]
    TARGET = [("EFI", 2), ("misc", 1), ("boot_a", 3), ("boot_b", 3), ("vbmeta_a", 1), ("vbmeta_b", 1),
              ("metadata", 1), ("super", 6), ("userdata", 1)]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        rnd = random.Random(229)
        uid = lambda: "%08x-%04x-4%03x-8%03x-%012x" % (rnd.getrandbits(32), rnd.getrandbits(16), rnd.getrandbits(12),
                                                       rnd.getrandbits(12), rnd.getrandbits(48))
        # The USB: single-slot layout, every partition distinct pseudo-random bytes.
        self.usb = self.root / "usb.img"
        usb_rows = rows_at(self.USB, {n: uid() for n, _ in self.USB})
        size = 16 * MIB
        with self.usb.open("wb") as f:
            f.truncate(size)
        write_gpt(self.usb, usb_rows, size)
        fd = os.open(self.usb, os.O_RDWR)
        try:
            self.usb_gpt = m.read_gpt(fd)
            for r in self.usb_gpt["rows"]:
                m.write_at(fd, m.extent(r)[0], rnd.randbytes(m.extent(r)[1]))
            self.pin = dict(schema="openbook-ruby-migration-source/1", build="synthetic", image_bytes=size,
                            gpt=[{k: r[k] for k in ("name", "first_lba", "last_lba", "partuuid")}
                                 for r in self.usb_gpt["rows"]],
                            payload_readback={r["name"]: m.digest(fd, *m.extent(r))
                                              for r in self.usb_gpt["rows"] if r["name"] in m.STATIC})
        finally:
            os.close(fd)
        self.raw_pin = json.dumps(self.pin).encode()
        self.usb_part = {r["name"]: m.extent(r) for r in self.usb_gpt["rows"]}
        # The plan: a two-slot layout tiled by usb / bundle / zero writes.
        self.rows = rows_at(self.TARGET, {n: uid() for n, _ in self.TARGET})
        blobs = {"EFI": rnd.randbytes(64 << 10), "vbmeta_a": rnd.randbytes(4096), "super": rnd.randbytes(256 << 10)}
        bundle, writes = bytearray(), []

        def from_bundle(part, at, blob):
            writes.append(dict(partition=part, at=at, length=len(blob), offset=len(bundle),
                               sha256=hashlib.sha256(blob).hexdigest(), **{"from": "bundle"}))
            bundle.extend(blob)

        def from_usb(part, at, source, offset, length):
            o = self.usb_part[source][0] + offset
            data = self.usb.read_bytes()[o:o + length]
            writes.append(dict(partition=part, at=at, length=length, source=source, offset=offset,
                               sha256=hashlib.sha256(data).hexdigest(), **{"from": "usb"}))

        def zero(part, at, length):
            writes.append(dict(partition=part, at=at, length=length, **{"from": "zero"}))

        from_bundle("EFI", 0, blobs["EFI"]); zero("EFI", 64 << 10, 2 * MIB - (64 << 10))
        zero("misc", 0, MIB)
        from_usb("boot_a", 0, "boot_a", 0, 2 * MIB); zero("boot_a", 2 * MIB, MIB)
        zero("boot_b", 0, 3 * MIB)
        from_bundle("vbmeta_a", 0, blobs["vbmeta_a"]); zero("vbmeta_a", 4096, MIB - 4096)
        zero("vbmeta_b", 0, MIB)
        zero("metadata", 0, MIB)
        from_bundle("super", 0, blobs["super"]); zero("super", 256 << 10, MIB - (256 << 10))
        from_usb("super", MIB, "super", 2 * MIB, MIB)     # extents need not keep the USB's order
        from_usb("super", 2 * MIB, "super", 0, MIB)
        zero("super", 3 * MIB, 3 * MIB)
        zero("userdata", 0, 4 * MIB); zero("userdata", -4 * MIB, 4 * MIB)
        self.bundle = self.root / "ab-bundle.bin"
        self.bundle.write_bytes(bytes(bundle))
        self.blobs = blobs
        self.plan = dict(schema=m.AB_SCHEMA, release="RB-TEST", variant="vm", bundle_file="ab-bundle.bin",
                         source_pin_sha256=hashlib.sha256(self.raw_pin).hexdigest(), source_build="synthetic",
                         bundle_bytes=len(bundle), bundle_sha256=hashlib.sha256(bundle).hexdigest(),
                         disk_guid="0b8f2d4e-6a1c-4f3b-9e7d-2c5a8b1f0e93", first_usable_lba=34,
                         partitions=self.rows, writes=writes)
        self.target = self.root / "target.img"
        self.target.write_bytes(b"\xa5" * (64 * MIB))  # a used SSD: stale bytes everywhere

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, plan=None, pin_sha=None, target=None):
        src = os.open(self.usb, os.O_RDONLY)
        dst = os.open(target or self.target, os.O_RDWR)
        bun = os.open(self.bundle, os.O_RDONLY)
        try:
            with patch.object(m, "AB_MIN_USERDATA", MIB):
                return m.install_ab(src, dst, self.pin, plan or self.plan, bun, self.root,
                                    pin_sha or hashlib.sha256(self.raw_pin).hexdigest())
        finally:
            os.close(src); os.close(dst); os.close(bun)

    def at(self, name, rel, length):
        r = next(r for r in self.rows if r["name"] == name)
        data = self.target.read_bytes()
        return data[r["offset"] + rel:r["offset"] + rel + length]

    def test_installs_exactly_the_planned_disk(self):
        result = self.install()
        usb = self.usb.read_bytes()
        boot, sup = self.usb_part["boot_a"], self.usb_part["super"]
        self.assertEqual(self.at("EFI", 0, 64 << 10), self.blobs["EFI"])
        self.assertEqual(self.at("boot_a", 0, 2 * MIB), usb[boot[0]:boot[0] + 2 * MIB])
        self.assertEqual(self.at("super", 0, 256 << 10), self.blobs["super"])
        self.assertEqual(self.at("super", MIB, MIB), usb[sup[0] + 2 * MIB:sup[0] + 3 * MIB])
        self.assertEqual(self.at("super", 2 * MIB, MIB), usb[sup[0]:sup[0] + MIB])
        for name, rel, n in (("misc", 0, MIB), ("boot_a", 2 * MIB, MIB), ("boot_b", 0, 3 * MIB),
                             ("vbmeta_b", 0, MIB), ("metadata", 0, MIB), ("super", 3 * MIB, 3 * MIB)):
            self.assertEqual(self.at(name, rel, n), bytes(n), name)
        # userdata grows to the disk, as plan-ruby-ab.py lays it out; its edges are reset, the rest is not erased.
        ud = result["layout"][-1]
        self.assertEqual(ud["offset"] + ud["length"], (64 * MIB - 34 * 512) // MIB * MIB)
        data = self.target.read_bytes()
        self.assertEqual(data[ud["offset"]:ud["offset"] + 4 * MIB], bytes(4 * MIB))
        fd = os.open(self.target, os.O_RDONLY)
        try:
            gpt = m.read_gpt(fd, names=tuple(r["name"] for r in self.rows))
        finally:
            os.close(fd)
        self.assertEqual([r["partuuid"] for r in gpt["rows"]], [r["partuuid"] for r in self.rows])
        self.assertTrue(result["complete"] and result["source_unchanged"])

    def test_gpt_follows_the_disk_size(self):
        for size in (64 * MIB, 64 * MIB + 7 * 512, 1000204886016, 512110190592):
            with self.subTest(size=size), patch.object(m, "AB_MIN_USERDATA", MIB):
                rows, headers = m.ab_target_gpt(self.plan, size)
                self.assertEqual([(r["name"], r["offset"]) for r in rows], [(r["name"], r["offset"]) for r in self.rows])
                self.assertEqual([r["length"] for r in rows[:-1]], [r["length"] for r in self.rows[:-1]])
                self.assertEqual(rows[-1]["offset"] + rows[-1]["length"], (size - 34 * 512) // MIB * MIB)
                disk = self.root / f"gpt-{size}.img"
                with disk.open("wb") as f:
                    f.truncate(size)
                fd = os.open(disk, os.O_RDWR)
                try:
                    for offset, data in headers:
                        m.write_at(fd, offset, data)
                    gpt = m.read_gpt(fd, names=None)
                finally:
                    os.close(fd)
                    disk.unlink()
                self.assertEqual(gpt["used_bytes"], size)
                self.assertEqual(gpt["rows"][-1]["last_lba"] + 1, (size - 34 * 512) // MIB * MIB // 512)

    def unchanged(self):
        return self.target.read_bytes() == b"\xa5" * (64 * MIB)

    def test_plan_is_bound_to_this_usb_system(self):
        with self.assertRaisesRegex(ValueError, "different USB system"):
            self.install(pin_sha="0" * 64)
        self.assertTrue(self.unchanged())

    def test_changed_bundle_is_refused(self):
        data = bytearray(self.bundle.read_bytes()); data[100] ^= 1
        self.bundle.write_bytes(bytes(data))
        with self.assertRaisesRegex(ValueError, "bundle changed"):
            self.install()
        self.assertTrue(self.unchanged())

    def test_gaps_overlaps_and_missing_resets_are_refused(self):
        cases = {"gap": lambda w: [x for x in w if not (x["partition"] == "boot_b")],
                 "overlap": lambda w: w + [dict(partition="misc", at=0, length=4096, **{"from": "zero"})],
                 "edges": lambda w: [x for x in w if not (x["partition"] == "userdata" and x["at"] < 0)]}
        for label, change in cases.items():
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    self.install(plan=dict(self.plan, writes=change(list(self.plan["writes"]))))
                self.assertTrue(self.unchanged())

    def test_changed_usb_is_refused_before_writing(self):
        fd = os.open(self.usb, os.O_RDWR)
        try:
            m.write_at(fd, self.usb_part["super"][0] + 12345, b"\0")
        finally:
            os.close(fd)
        with self.assertRaisesRegex(ValueError, "Source system changed: super"):
            self.install()
        self.assertTrue(self.unchanged())

    def test_target_too_small_is_refused(self):
        small = self.root / "small.img"
        small.write_bytes(b"\xa5" * (16 * MIB))
        with self.assertRaisesRegex(ValueError, "too small"):
            self.install(target=small)
        self.assertEqual(small.read_bytes(), b"\xa5" * (16 * MIB))

    def no_partition_table(self):
        data = self.target.read_bytes()
        return data[:34 * 512] == bytes(34 * 512) and data[-33 * 512:] == bytes(33 * 512)

    def test_readback_failure_stops_without_a_partition_table(self):
        real = m.digest
        boot = next(r for r in self.rows if r["name"] == "boot_a")

        def lying(fd, start, length):
            return "0" * 64 if start == boot["offset"] and length == 2 * MIB and os.fstat(fd).st_size == 64 * MIB \
                else real(fd, start, length)
        with patch.object(m, "digest", lying), self.assertRaisesRegex(ValueError, "Readback failed: boot_a"):
            self.install()
        self.assertTrue(self.no_partition_table())

    def test_power_cut_mid_install_leaves_no_partition_table(self):
        real, calls = m.write_at, []

        def cut(fd, start, data):
            calls.append(start)
            if len(calls) == 8:  # after the old table is cleared, before the new one
                raise OSError("power lost")
            return real(fd, start, data)
        with patch.object(m, "write_at", cut), self.assertRaises(OSError):
            self.install()
        self.assertTrue(self.no_partition_table())


class PlannerHelpers(unittest.TestCase):
    def test_subtract(self):
        self.assertEqual(b.subtract([(0, 100)], [(10, 10), (50, 60)]), [(0, 10), (20, 30)])
        self.assertEqual(b.subtract([(0, 10), (20, 10)], [(5, 20)]), [(0, 5), (25, 5)])
        self.assertEqual(b.subtract([(0, 10)], []), [(0, 10)])

    def test_data_extents_of_a_sparse_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sparse.img"
            with path.open("wb") as f:
                f.truncate(8 * MIB)
                f.seek(MIB); f.write(b"x" * 4096)
                f.seek(5 * MIB); f.write(b"y" * 8192)
            fd = os.open(path, os.O_RDONLY)
            try:
                got = b.data_extents(fd, 0, 8 * MIB)
                inside = b.data_extents(fd, 4 * MIB, 4 * MIB)
            finally:
                os.close(fd)
        self.assertEqual(sum(n for _, n in got), 4096 + 8192)
        self.assertEqual([o for o, _ in got], [MIB, 5 * MIB])
        self.assertEqual(inside, [(5 * MIB, 8192)])

    @unittest.skipUnless((LPTOOLS / "bin/lpmake").exists(), "AOSP lpmake/lpdump not built")
    def test_lp_parser_agrees_with_lpdump(self):
        env = dict(os.environ, LD_LIBRARY_PATH=str(LPTOOLS / "lib64"))
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "system.img").write_bytes(os.urandom(3 * MIB))
            (t / "vendor.img").write_bytes(os.urandom(MIB))
            subprocess.run([str(LPTOOLS / "bin/lpmake"), "--metadata-size", "65536", "--metadata-slots", "3",
                            "--virtual-ab", "--device", f"super:{32 * MIB}", "--group", f"g_a:{16 * MIB}",
                            "--group", f"g_b:{16 * MIB}",
                            "--partition", f"system_a:readonly:{3 * MIB}:g_a", "--image", f"system_a={t / 'system.img'}",
                            "--partition", f"vendor_a:readonly:{MIB}:g_a", "--image", f"vendor_a={t / 'vendor.img'}",
                            "--output", str(t / "super.img")], check=True, env=env, capture_output=True)
            fd = os.open(t / "super.img", os.O_RDONLY)
            try:
                mine, first = b.lp_extents(fd, 0)
                for name, src in (("system_a", "system.img"), ("vendor_a", "vendor.img")):
                    data = b"".join(m.read_at(fd, o, n) for o, n in mine[name])
                    self.assertEqual(data, (t / src).read_bytes())
            finally:
                os.close(fd)
            with patch.dict(os.environ, env):
                self.assertEqual(b.lpdump_extents(LPTOOLS / "bin/lpdump", t / "super.img"),
                                 {k: v for k, v in mine.items() if v})
            self.assertGreater(first, 0)
            self.assertLessEqual(first, min(o for v in mine.values() for o, _ in v))


if __name__ == "__main__":
    unittest.main()
