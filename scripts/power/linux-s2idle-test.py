#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""linux-s2idle.py's ANAL-257 pieces on a fake sysfs: dGPU discovery, the driverless and eco phases and their undo,
the internal-NVMe guard and the openbook_sleep_diag log parser. No root, no device is touched."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("ls", Path(__file__).with_name("linux-s2idle.py"))
ls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ls)


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class FakeSys:
    """The G14's dGPU: 0000:64:00.0 (display) and .1 (HDMI audio) below root port 0000:00:03.1."""

    def __init__(self, root, display_driver="nouveau", mux="1", eco="0"):
        self.sys = Path(root) / "sys"
        dev = self.sys / "devices/pci0000:00/0000:00:03.1"
        for bdf, vendor, cls, drv in (("0000:00:03.1", "0x1022", "0x060400", "pcieport"),
                                      ("0000:64:00.0", "0x10de", "0x030000", display_driver),
                                      ("0000:64:00.1", "0x10de", "0x040300", "snd_hda_intel")):
            d = dev if bdf == "0000:00:03.1" else dev / bdf
            put(d / "vendor", vendor)
            put(d / "class", cls)
            put(d / "power_state", "D0")
            put(d / "power/runtime_status", "active")
            put(d / "power/control", "on")
            put(d / "remove", "")
            (self.sys / "bus/pci/devices").mkdir(parents=True, exist_ok=True)
            os.symlink(d, self.sys / "bus/pci/devices" / bdf)
            if drv:
                put(self.sys / f"bus/pci/drivers/{drv}/bind", "")
                put(self.sys / f"bus/pci/drivers/{drv}/unbind", "")
                os.symlink(self.sys / f"bus/pci/drivers/{drv}", d / "driver")
        put(self.sys / "bus/pci/drivers/nouveau/bind", "")
        put(self.sys / "bus/pci/drivers/nouveau/unbind", "")
        put(self.sys / "bus/pci/rescan", "")
        put(self.sys / "module/snd_hda_intel/parameters/power_save", "0")
        put(self.sys / "devices/platform/asus-nb-wmi/dgpu_disable", eco)
        put(self.sys / "devices/platform/asus-nb-wmi/gpu_mux_mode", mux)

    def text(self, rel):
        return (self.sys / rel).read_text().strip()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = ls.SYS

    def tearDown(self):
        ls.SYS = self.old
        self.tmp.cleanup()

    def fake(self, **kw):
        f = FakeSys(self.tmp.name, **kw)
        ls.SYS = str(f.sys)
        return f


class DgpuTests(Base):
    def test_finds_display_audio_and_bridge(self):
        self.fake()
        g = ls.find_dgpu()
        self.assertEqual(g, {"display": ["0000:64:00.0"], "other": ["0000:64:00.1"], "bridge": "0000:00:03.1"})
        st = ls.dgpu_state(g)
        self.assertEqual([x["driver"] for x in st["functions"]], ["nouveau", "snd_hda_intel"])
        self.assertEqual(st["bridge"]["driver"], "pcieport")

    def test_driverless_applies_the_hook_and_undoes_it_in_reverse(self):
        f = self.fake()
        b = ls.Binds()
        self.assertIsNone(ls.prep_driverless(ls.find_dgpu(), b))
        self.assertEqual(f.text("bus/pci/drivers/snd_hda_intel/unbind"), "0000:64:00.1")
        self.assertEqual(f.text("bus/pci/drivers/nouveau/unbind"), "0000:64:00.0")
        self.assertEqual(f.text("bus/pci/devices/0000:64:00.0/power/control"), "auto")
        self.assertEqual(f.text("bus/pci/devices/0000:64:00.1/power/control"), "auto")
        self.assertEqual(f.text("module/snd_hda_intel/parameters/power_save"), "10")
        msgs = b.restore()
        self.assertEqual([m.split()[0] for m in msgs], ["set", "set", "set", "bind", "bind"])
        self.assertEqual(f.text("module/snd_hda_intel/parameters/power_save"), "0")
        self.assertEqual(f.text("bus/pci/devices/0000:64:00.0/power/control"), "on")
        self.assertEqual(f.text("bus/pci/drivers/nouveau/bind"), "0000:64:00.0")
        self.assertEqual(f.text("bus/pci/drivers/snd_hda_intel/bind"), "0000:64:00.1")

    def test_never_unbinds_the_nvidia_driver(self):
        f = self.fake(display_driver="nvidia")
        b = ls.Binds()
        for prep in (ls.prep_driverless, ls.prep_nouveau):
            self.assertRegex(prep(ls.find_dgpu(), b), "driven by nvidia")
        self.assertEqual(b.undo, [])
        self.assertEqual(f.text("bus/pci/drivers/snd_hda_intel/unbind"), "")

    def test_wait_reports_timeout(self):
        self.fake()
        reached, after = ls.wait_dgpu_asleep(ls.find_dgpu(), timeout=0)
        self.assertFalse(reached)


class EcoTests(Base):
    def test_eco_removes_sets_and_always_restores(self):
        f = self.fake()
        b, st = ls.Binds(), {}
        self.assertIsNone(ls.prep_eco(ls.find_dgpu(), b, st))
        self.assertEqual(f.text("devices/platform/asus-nb-wmi/dgpu_disable"), "1")
        self.assertEqual(f.text("bus/pci/devices/0000:64:00.0/remove"), "1")
        msgs = ls.restore_eco(st)
        self.assertEqual(f.text("devices/platform/asus-nb-wmi/dgpu_disable"), "0")
        self.assertEqual(f.text("bus/pci/rescan"), "1")
        self.assertIn("dgpu_disable 0: ok", msgs)
        self.assertEqual(ls.restore_eco(st), [])

    def test_eco_refuses_dgpu_mux_and_already_disabled(self):
        f = self.fake(mux="0")
        self.assertRegex(ls.prep_eco(ls.find_dgpu(), ls.Binds(), {}), "gpu_mux_mode")
        self.assertEqual(f.text("devices/platform/asus-nb-wmi/dgpu_disable"), "0")
        self.tmp.cleanup()
        self.tmp = tempfile.TemporaryDirectory()
        f = self.fake(eco="1")
        self.assertRegex(ls.prep_eco(ls.find_dgpu(), ls.Binds(), {}), "not touching")
        self.assertEqual(f.text("devices/platform/asus-nb-wmi/dgpu_disable"), "1")


class NvmeGuardTests(Base):
    def test_finds_nvme_directly_through_dm_crypt_and_swap(self):
        f = self.fake()
        put(f.sys / "class/block/dm-0/slaves/nvme0n1p2", "")
        put(f.sys / "class/block/dm-1/slaves/sda2", "")
        mounts = ("/dev/sda1 /run/archiso/bootmnt iso9660 ro 0 0\n/dev/dm-1 /mnt/usb ext4 rw 0 0\n"
                  "/dev/dm-0 /mnt/x btrfs rw 0 0\nnone /sys/kernel/debug debugfs rw 0 0\n"
                  "/dev/nvme0n1p1 /mnt/esp vfat rw 0 0\n")
        swaps = "Filename Type Size Used Priority\n/dev/nvme0n1p3 partition 100 0 -2\n"
        self.assertEqual(ls.nvme_in_use(mounts, swaps),
                         [("/dev/dm-0", "/mnt/x"), ("/dev/nvme0n1p1", "/mnt/esp"), ("/dev/nvme0n1p3", "swap")])
        self.assertEqual(ls.nvme_in_use("/dev/sda1 / ext4 rw 0 0\n", ""), [])


class ParserTests(unittest.TestCase):
    def test_reads_sleep_diag_and_old_snapshot_lines(self):
        log = "\n".join([
            "[ 10.0] openbook_sleep_diag: suspend 1: PTM turned off on 2 of 2 function(s) that had it on",
            "[ 10.1] openbook_sleep_diag: suspend: usb4 0000:67:00.5 1022:151c driver thunderbolt kernel D0 ...",
            "[ 10.2] amd_pmc AMDI000A:00: SMU idlemask s0i3: 0xffef9afd",
            "[ 10.3] openbook_sleep_diag: s0i3-entry 1: 0000:00:00.0 1022:1507 pci kernel D0 pmcsr no-pm-cap",
            "[ 10.3] openbook_sleep_diag: s0i3-entry: usb4 0000:67:00.5 1022:151c driver thunderbolt",
            "[ 10.4] openbook_sleep_diag: s0i3-entry 1: 39 PCI functions, 17 not in D3, 0 with PTM on",
            "[ 20.0] amd_pmc AMDI000A:00: Last suspend didn't reach deepest state",
            "[ 20.1] openbook_sleep_diag: resume 1: PTM restored on 2 of 2 function(s)",
        ])
        c = ls.parse_cycle_log(log)
        self.assertEqual(c["idlemask_entry"], "0xffef9afd")
        self.assertTrue(c["not_deepest_warning"])
        self.assertEqual(c["snapshot_not_in_d3"], ["0000:00:00.0 1022:1507 pci kernel D0 pmcsr no-pm-cap"])
        self.assertEqual(c["snapshot_summary"], "39 PCI functions, 17 not in D3, 0 with PTM on")
        self.assertEqual(len(c["ptm"]), 2)
        self.assertEqual(len(c["usb4"]), 2)
        old = ls.parse_cycle_log("openbook_s0i3_snapshot: s0i3-entry: 0000:00:08.0 1022:1509 D0\n"
                                 "openbook_s0i3_snapshot: s0i3-entry: 39 PCI functions, 17 not in D3\n")
        self.assertEqual(old["snapshot_not_in_d3"], ["0000:00:08.0 1022:1509 D0"])
        self.assertEqual(old["snapshot_summary"], "39 PCI functions, 17 not in D3")


if __name__ == "__main__":
    unittest.main()
