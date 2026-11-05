#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/perf/app-perf.py's parsers and attribution, on synthetic device output (no device).
python3 tests/perf/app-perf-test.py (tests/run.sh runs it)"""
import importlib.util
import itertools
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("app_perf", os.path.join(HERE, "..", "..", "scripts", "perf",
                                                                        "app-perf.py"))
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)

PKG = "org.example.app"
APK = f"/data/app/~~aaaa==/{PKG}-bbbb==/base.apk"
AM_COLD = """Starting: Intent { cmp=org.example.app/.Main }
Status: ok
LaunchState: COLD
Activity: org.example.app/.Main
TotalTime: 459
WaitTime: 463
Complete
"""


class AmStart(unittest.TestCase):
    def test_cold(self):
        r = P.parse_am_start(AM_COLD)
        self.assertTrue(r["ok"])
        self.assertEqual((r["launch_state"], r["total_ms"], r["wait_ms"]), ("COLD", 459, 463))

    def test_brought_to_front_has_no_time(self):
        r = P.parse_am_start("Starting: Intent { cmp=org.example.app/.Main }\n"
                             "Warning: Activity not started, its current task has been brought to the front\n"
                             "Status: ok\nLaunchState: UNKNOWN (0)\nActivity: org.example.app/.Main\nWaitTime: 3\n"
                             "Complete\n")
        self.assertFalse(r["ok"])
        self.assertIsNone(r["total_ms"])
        self.assertEqual(len(r["warnings"]), 1)

    def test_error(self):
        r = P.parse_am_start("Starting: Intent { cmp=org.example.app/.Nope }\n"
                             "Error type 3\nError: Activity class {org.example.app/.Nope} does not exist.\n")
        self.assertFalse(r["ok"])
        self.assertIn("does not exist", r["error"])


class Launch(unittest.TestCase):
    def test_samples_and_am(self):
        text = ("@s 1000 epp=24:balance_performance maxfreq_khz=2000000\n@t0 1001\n"
                "@s 1011 epp=24:performance maxfreq_khz=5100000\n" + AM_COLD +
                "@s 1021 epp=16:performance,8:balance_performance maxfreq_khz=4800000\n@t1 1050 rc=0\n")
        r = P.parse_launch(text)
        self.assertEqual(r["am"]["total_ms"], 459)
        self.assertEqual((r["t0_cs"], r["t1_cs"], r["rc"]), (1001, 1050, 0))
        self.assertEqual(r["epp_seen"], ["balance_performance", "performance"])
        self.assertEqual(r["maxfreq_khz"], 5100000)
        self.assertEqual(r["samples"][2]["epp"], {"performance": 16, "balance_performance": 8})

    def test_no_epp_in_a_vm(self):
        r = P.parse_launch("@s 5 epp=na maxfreq_khz=0\n@t0 6\n" + AM_COLD + "@t1 9 rc=0\n")
        self.assertEqual(r["epp_seen"], [])
        self.assertIsNone(r["maxfreq_khz"])


class Stats(unittest.TestCase):
    def test_keeps_spread_and_missing(self):
        s = P.stats([300, None, 250, 900, 260])
        self.assertEqual((s["n"], s["missing"], s["median"], s["min"], s["max"], s["spread"]),
                         (4, 1, 280.0, 250, 900, 650))

    def test_empty(self):
        self.assertEqual(P.stats([None, None]), {"n": 0, "missing": 2})


class Package(unittest.TestCase):
    DUMP = f"""Activity Resolver Table:
Packages:
  Package [{PKG}] (2d47b80):
    appId=10126
    codePath=/data/app/~~aaaa==/{PKG}-bbbb==
    extractNativeLibs=false
    primaryCpuAbi=arm64-v8a
    secondaryCpuAbi=null
    versionCode=4021 minSdk=26 targetSdk=35
    versionName=4.2.1 (beta 2)
    splits=[base, config.arm64_v8a, config.en]
    installerPackageName=org.example.store
    lastUpdateTime=2026-11-03 21:02:48
    User 0: ceDataInode=1 installed=true
  Package [{PKG}] (1111111):
    versionName=1.0
Hidden system packages:
  Package [{PKG}] (99):
    versionName=0.9
"""

    def test_first_block(self):
        r = P.parse_dumpsys_package(self.DUMP, PKG)
        self.assertEqual(r["versionName"], "4.2.1 (beta 2)")
        self.assertEqual((r["versionCode"], r["targetSdk"]), (4021, 35))
        self.assertEqual(r["primaryCpuAbi"], "arm64-v8a")
        self.assertIsNone(r["secondaryCpuAbi"])
        self.assertEqual(r["installerPackageName"], "org.example.store")

    def test_other_package_ignored(self):
        self.assertEqual(P.parse_dumpsys_package(self.DUMP, "org.example.other"), {})


class Apk(unittest.TestCase):
    def test_listing(self):
        r = P.parse_apk_listing("lib/arm64-v8a/libflutter.so\nlib/arm64-v8a/libapp.so\nlib/x86_64/libapp.so\n"
                                "classes.dex\nclasses2.dex\nlib/arm64-v8a/notes.txt\n")
        self.assertEqual(r, {"abis": {"arm64-v8a": ["libapp.so", "libflutter.so"], "x86_64": ["libapp.so"]},
                             "dex": 2})

    def test_framework_hints(self):
        self.assertEqual(P.framework_hints(["libflutter.so", "libapp.so"]), ["Flutter"])
        self.assertEqual(P.framework_hints(["libil2cpp.so", "libunity.so", "libmain.so"]), ["Unity"])
        self.assertEqual(P.framework_hints(["libhermes.so"]), ["React Native"])
        self.assertEqual(P.framework_hints(["libQt6Core_arm64-v8a.so"]), ["Qt"])
        self.assertEqual(P.framework_hints(["libsqlite.so"]), [])

    def test_native_code(self):
        self.assertEqual(P.native_code("arm64-v8a", {"arm64-v8a": []}), "translated (arm64-v8a)")
        self.assertEqual(P.native_code("x86_64", {"x86_64": [], "arm64-v8a": []}), "x86_64")
        self.assertEqual(P.native_code(None, {}), "none")
        self.assertEqual(P.native_code(None, {"mips": []}), "unknown")


class ArtDump(unittest.TestCase):
    DUMP = f"""[{PKG}]
  path: {APK}
    x86_64: [status=speed-profile] [reason=install] [primary-abi]
      [location is /data/app/~~aaaa==/{PKG}-bbbb==/oat/x86_64/base.odex]
  path: /data/app/~~aaaa==/{PKG}-bbbb==/split_feature.apk
    x86_64: [status=verify] [reason=install] [primary-abi]
      [location is /data/app/~~aaaa==/{PKG}-bbbb==/oat/x86_64/split_feature.odex]
  known secondary dex files:
    /data/user/0/{PKG}/code_cache/plugin.jar
      x86_64: [status=run-from-apk] [reason=unknown]
"""

    def test_primary_files(self):
        f = P.parse_art_dump(self.DUMP)
        self.assertEqual([(x["path"].rsplit("/", 1)[-1], x["status"], x["reason"]) for x in f],
                         [("base.apk", "speed-profile", "install"), ("split_feature.apk", "verify", "install")])
        self.assertEqual(P.dexopt_summary(f), "speed-profile/install, verify/install")
        self.assertEqual(P.dexopt_summary([]), "na")


SEP = P.SEP
CSV = f"""Cmdline: /system/bin/simpleperf record -a -e cpu-clock -f 1000 --duration 22 -o /data/local/tmp/perf.data
Arch: x86_64
Event: cpu-clock (type 1, config 0x0, config1 0x0, config2: 0x0)
Samples: 1000
Event count: 1000000000

Overhead{SEP}Pid{SEP}Shared Object{SEP}Symbol{SEP}EventCount{SEP}EventName
60.00%{SEP}100{SEP}unknown{SEP}unknown[+40ee1601]{SEP}600000000{SEP}cpu-clock
10.00%{SEP}100{SEP}unknown{SEP}unknown[+deadbeef]{SEP}100000000{SEP}cpu-clock
5.00%{SEP}100{SEP}/system/lib64/libberberis_arm64.so{SEP}berberis::x86_64::FoldInsns(berberis::x86_64::MachineIR*){SEP}50000000{SEP}cpu-clock
2.00%{SEP}100{SEP}/system/lib64/libberberis_arm64.so{SEP}berberis::Interpreter::Run(std::map<int, int>){SEP}20000000{SEP}cpu-clock
3.00%{SEP}100{SEP}/system/lib64/libberberis_arm64.so{SEP}berberis::ExecuteGuest(berberis::ThreadState*){SEP}30000000{SEP}cpu-clock
5.00%{SEP}100{SEP}/system/lib64/libberberis_proxy_libGLESv2.so{SEP}glDrawArrays{SEP}50000000{SEP}cpu-clock
5.00%{SEP}101{SEP}/apex/com.android.art/lib64/libart.so{SEP}art::gc::Heap::Collect{SEP}50000000{SEP}cpu-clock
4.00%{SEP}101{SEP}[JIT app cache]{SEP}void org.example.app.Main.loop(){SEP}40000000{SEP}cpu-clock
3.00%{SEP}101{SEP}[kernel.kallsyms]{SEP}clear_page_erms{SEP}30000000{SEP}cpu-clock
3.00%{SEP}101{SEP}/vendor/lib64/libvulkan_radeon.so{SEP}radv_CmdDraw{SEP}30000000{SEP}cpu-clock
"""
MAPS = """@pid 100
40daa000-411aa000 r-xs 00000000 00:01 2138                               /memfd:exec (deleted)
4a401000-4a405000 r-xp 00000000 fe:07 21496557                           /system/lib64/libberberis_exec_region.so
@pid 101
7000000-7100000 r-xp 00000000 00:01 9 /memfd:jit-cache (deleted)
"""


class Cpu(unittest.TestCase):
    def test_csv(self):
        head, rows = P.parse_simpleperf_csv(CSV)
        self.assertEqual(head["Samples"], "1000")
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[3]["Symbol"], "berberis::Interpreter::Run(std::map<int, int>)")

    def test_maps(self):
        m = P.parse_maps(MAPS)
        self.assertEqual(P.region_of(m["100"], 0x40ee1601), "/memfd:exec (deleted)")
        self.assertIsNone(P.region_of(m["100"], 0xdeadbeef))
        self.assertIsNone(P.region_of(m.get("999"), 0x40ee1601))

    def test_categories(self):
        c = P.categorize
        self.assertEqual(c("unknown", "unknown[+1]", "/memfd:exec (deleted)"), "translated")
        self.assertEqual(c("unknown", "unknown[+1]", None), "unknown")
        self.assertEqual(c("unknown", "unknown[+1]", "/memfd:jit-cache (deleted)"), "java")
        self.assertEqual(c("unknown", "unknown[+1]", "[anon:swiftshader_jit]"), "graphics")
        self.assertEqual(c("unknown", "unknown[+1]", "/system/lib64/libhwui.so"), "graphics")
        self.assertEqual(c("/system/lib64/libberberis_exec_region.so"), "translated")
        self.assertEqual(c("/system/lib64/libberberis_arm64.so", "berberis::intrinsics::FAdd"), "translator-helpers")
        self.assertEqual(c("/system/lib64/libberberis_arm64.so",
                           "berberis::TranslationCache::GetHostCodePtr(unsigned long)"), "translator-runtime")
        self.assertEqual(c("/system/lib64/libberberis_arm64.so", "berberis::LiteTranslator::ExitRegion(unsigned long)"),
                         "translator-compile")
        self.assertEqual(c("/system/lib64/libndk_translation.so", ""), "translator-runtime")
        self.assertEqual(c("/data/app/~~a==/org.example.app-b==/lib/x86_64/libgame.so"), "app-native")
        self.assertEqual(c("/data/app/~~a==/org.example.app-b==/oat/x86_64/base.odex"), "java")
        self.assertEqual(c("/system/framework/x86_64/boot-framework.oat"), "java")
        self.assertEqual(c("/vendor/lib64/hw/vulkan.pastel.so"), "graphics")
        self.assertEqual(c("/apex/com.android.runtime/lib64/bionic/libc.so"), "system-native")
        self.assertEqual(c("[kernel.kallsyms]"), "kernel")
        self.assertEqual(c("//anon"), "unknown")

    def test_attribution(self):
        _, rows = P.parse_simpleperf_csv(CSV)
        a = P.cpu_attribution(rows, P.parse_maps(MAPS))
        self.assertEqual(a["event_total"], 1_000_000_000)
        s = {k: round(v, 3) for k, v in a["share"].items()}
        self.assertEqual((s["translated"], s["unknown"], s["translator-compile"], s["translator-interpret"],
                          s["translator-runtime"], s["bridge-proxies"], s["java"], s["kernel"], s["graphics"]),
                         (0.6, 0.1, 0.05, 0.02, 0.03, 0.05, 0.09, 0.03, 0.03))
        g = {k: round(v, 3) for k, v in a["groups"].items()}
        self.assertEqual(g, {"arm_code": 0.62, "translation_overhead": 0.05, "bridge_runtime": 0.08})
        self.assertEqual(a["top_translator_and_unknown"][0]["category"], "unknown")
        self.assertAlmostEqual(sum(a["share"].values()), 1.0)

    def test_no_rows(self):
        a = P.cpu_attribution([], {})
        self.assertEqual(a["event_total"], 0)
        self.assertIsNone(a["share"]["translated"])


STATS_LOG = """I/berberis(  100): berberis.stats: on; block at 0x7f0000001000 (layout OBSTAT2, 3 counters, 74 bytes)
I/berberis( 4321): openbook-stats v1 pid=100 t_ms=2001 installed_lite=10 installed_heavy=0 dispatcher_flushes=1
I/berberis( 4321): openbook-stats v1 pid=100 t_ms=4002 installed_lite=25 installed_heavy=2 dispatcher_flushes=3
I/berberis( 4322): openbook-stats v1 pid=101 t_ms=2000 installed_lite=7 entries_invalidated
I/berberis( 4322): openbook-stats v1 pid=101 t_ms=1999 installed_lite=5
I/berberis( 4323): openbook-stats v1 t_ms=2000 installed_lite=5
"""
GAME = "/data/app/~~a==/org.example.app-b==/lib/arm64/libgame.so"
PERF_MAP = """0x40e00000 0x200 b/arm64/libgame.so_lite_0x7100001000+48@0x1000
0x40e00200 0x100 b/arm64/libgame.so_heavy_0x7100002000+96@0x2000
0x40e00300 0x80 _lite_range_0x5000+8@0x0
0x40e00380 0x40 lite_0x6000+4
not a perf map line
0x40e00400 0x0 x_lite_0x1+4@0x0
0x40e00440 0x40 4/libsqlite.so_lite_0x7000+4@0x10
"""
STATS_NAMES = ["installed_lite", "installed_heavy", "dispatcher_flushes"]
BLOCK_ADDR = 0x7f0000001000


def stats_block(values, enabled=1, names=STATS_NAMES, owner=100, baseline=None):
    """The OBSTAT2 block as a process holds it in memory."""
    text = " ".join(names).encode() + b"\0"
    u64 = lambda v: v.to_bytes(8, "little")
    return (b"OBSTAT2\0" + u64(len(values)) + u64(len(text)) + u64(enabled) + u64(owner) +
            u64(1 if baseline else 0) + b"".join(u64(v) for v in values) +
            b"".join(u64(v) for v in (baseline or [0] * len(values))) + text)


TRANSLATED_MAPS = MAPS + f"""@pid 100
7100000000-7100100000 r-xp 00000000 fe:07 1 {GAME}
"""


def row(pid, sym, n, dso="unknown"):
    return {"Pid": pid, "Shared Object": dso, "Symbol": sym, "EventCount": str(n)}


class TranslatorProfile(unittest.TestCase):
    def test_block_addresses(self):
        log = (STATS_LOG + "11-04 12:49:25.954  2001  2001 I berberis: berberis.stats: on; block at 0x7f30aa (layout "
               "OBSTAT2, 26 counters, 714 bytes)\n")
        self.assertEqual(P.parse_stats_addresses(log), {"100": BLOCK_ADDR, "2001": 0x7f30aa})

    def test_block(self):
        b = stats_block([25, 2, 3], owner=200, baseline=[20, 2, 1])
        h = P.parse_stats_header(b[:48].hex())
        self.assertEqual((h["count"], h["enabled"], h["owner_pid"], h["baseline_valid"]), (3, 1, 200, 1))
        body = b[48:48 + P.stats_body_size(h)].hex()
        # xxd -p wraps its output; the parser joins the lines.
        wrapped = "\n".join(body[i:i + 60] for i in range(0, len(body), 60))
        counters, baseline = P.parse_stats_body(wrapped, h)
        self.assertEqual(counters, {"installed_lite": 25, "installed_heavy": 2, "dispatcher_flushes": 3})
        self.assertEqual(baseline, {"installed_lite": 20, "installed_heavy": 2, "dispatcher_flushes": 1})

    def test_origin(self):
        c, z = {"installed_lite": 25}, {"installed_lite": 0}
        own = P.stats_origin("100", {"owner_pid": 100, "baseline_valid": 0}, c, z)
        self.assertEqual(own, {"counts_from": "process start"})
        forked = P.stats_origin("200", {"owner_pid": 200, "baseline_valid": 1}, c, {"installed_lite": 20})
        self.assertEqual(forked["since_fork"], {"installed_lite": 5})
        self.assertIn("fork from its parent", forked["counts_from"])
        cloned = P.stats_origin("300", {"owner_pid": 100, "baseline_valid": 0}, c, z)
        self.assertIn("inherited from pid 100 with no baseline", cloned["counts_from"])
        self.assertNotIn("since_fork", cloned)

    def test_bad_blocks(self):
        with self.assertRaisesRegex(ValueError, "no OBSTAT2"):
            P.parse_stats_header(bytes(48).hex())  # memory at a wrong address
        with self.assertRaisesRegex(ValueError, "no OBSTAT2"):
            P.parse_stats_header(stats_block([1, 2, 3])[:32].hex())  # cut short
        with self.assertRaisesRegex(ValueError, "no OBSTAT2"):
            P.parse_stats_header((b"OBSTAT1\0" + bytes(40)).hex())  # the earlier layout
        with self.assertRaisesRegex(ValueError, "implausible"):
            P.parse_stats_header((b"OBSTAT2\0" + (10**6).to_bytes(8, "little") + bytes(32)).hex())
        b = stats_block([1, 2, 3])
        h = P.parse_stats_header(b[:48].hex())
        with self.assertRaisesRegex(ValueError, "cut short"):
            P.parse_stats_body(b[48:72].hex(), h)
        b = stats_block([1, 2, 3], names=["a", "b"])
        with self.assertRaisesRegex(ValueError, "2 names for 3 counters"):
            P.parse_stats_body(b[48:].hex(), P.parse_stats_header(b[:48].hex()))

    def test_stats_keeps_the_latest_whole_line_per_pid(self):
        st = P.parse_translator_stats(STATS_LOG)
        self.assertEqual(sorted(st), ["100", "101"])  # the line without pid= is skipped
        self.assertEqual(st["100"], {"t_ms": 4002, "installed_lite": 25, "installed_heavy": 2, "dispatcher_flushes": 3})
        self.assertEqual(st["101"], {"t_ms": 1999, "installed_lite": 5})  # the cut-short line is skipped

    def test_perf_map(self):
        m = P.parse_perf_map(PERF_MAP)
        self.assertEqual(len(m), 5)
        self.assertEqual(m[0], (0x40e00000, 0x40e00200, "lite", "b/arm64/libgame.so", 0x7100001000, 48, 0x1000))
        self.assertEqual(m[1][2:4], ("heavy", "b/arm64/libgame.so"))
        self.assertEqual(m[2][2:4], ("lite_range", ""))          # anonymous mapping: "_" and no name
        self.assertEqual(m[3][2:], ("lite", "", 0x6000, 4, None))  # address not in any mapping; no offset (old patch)
        self.assertEqual(m[4][2:4], ("lite", "4/libsqlite.so"))   # a library name with "lite" in it

    def test_tiers_and_regions(self):
        rows = [row("100", "unknown[+40e00010]", 600), row("100", "unknown[+40e00250]", 300),
                row("100", "unknown[+40f00000]", 100),   # translated, but no perf-map entry covers it
                row("100", "unknown[+deadbeef]", 50),    # not translated
                row("100", "berberis::ExecuteGuest", 40, "/system/lib64/libberberis_arm64.so")]
        t = P.tier_attribution(rows, P.parse_maps(TRANSLATED_MAPS), {"100": P.parse_perf_map(PERF_MAP)})
        self.assertEqual(t["translated_events"], 1000)
        self.assertEqual(t["events_by_tier"], {"lite": 600, "heavy": 300, "unattributed": 100})
        self.assertAlmostEqual(t["share_by_tier"]["lite"], 0.6)
        top = t["top_regions"]
        self.assertEqual((top[0]["region"], top[0]["tier"], top[0]["events"], top[0]["guest_bytes"]),
                         (f"{GAME}@0x1000", "lite", 600, 48))
        self.assertTrue(top[0]["comparable_across_launches"])
        self.assertAlmostEqual(top[0]["share_of_translated"], 0.6)
        self.assertEqual((top[1]["region"], top[1]["tier"]), (f"{GAME}@0x2000", "heavy"))
        self.assertEqual(t["regions_with_samples"], 2)

    def test_anonymous_regions_stay_distinct_and_process_local(self):
        """The review's reproduction (PR #190): two guest JIT regions in anonymous memory, with the old patch's
        '@0x0' and the new patch's no offset. Each keeps its own name and size, marked not comparable."""
        maps = P.parse_maps("""@pid 100
4000-5000 r-xp 00000000 00:00 0 /memfd:exec (deleted)
7000-9000 r-xp 00000000 00:00 0
""")
        rows = [row("100", f"unknown[+{a:x}]", 10) for a in (0x4010, 0x4110)]
        for pm in ("0x4000 0x100 _lite_0x7000+16@0x0\n0x4100 0x100 _lite_0x8000+32@0x0\n",
                   "0x4000 0x100 _lite_0x7000+16\n0x4100 0x100 _lite_0x8000+32\n"):
            t = P.tier_attribution(rows, maps, {"100": P.parse_perf_map(pm)})
            self.assertEqual(t["regions_with_samples"], 2, pm)
            regs = sorted(t["top_regions"], key=lambda r: r["guest_bytes"])
            self.assertEqual([(r["guest_bytes"], r["events"]) for r in regs], [(16, 10), (32, 10)])
            self.assertEqual({r["comparable_across_launches"] for r in regs}, {False})
            self.assertIn("guest 0x7000+16", regs[0]["region"])

    def test_same_offset_in_two_processes_is_one_comparable_region(self):
        """The library offset is the identity: the same code in two processes (at different addresses) is one."""
        maps = P.parse_maps(TRANSLATED_MAPS + f"""@pid 200
50000000-50100000 r-xs 00000000 00:01 2 /memfd:exec (deleted)
7200000000-7200100000 r-xp 00000000 fe:07 1 {GAME}
""")
        pm200 = "0x50000000 0x200 b/arm64/libgame.so_lite_0x7200001000+48@0x1000\n"
        t = P.tier_attribution([row("100", "unknown[+40e00010]", 6), row("200", "unknown[+50000010]", 4)], maps,
                               {"100": P.parse_perf_map(PERF_MAP), "200": P.parse_perf_map(pm200)})
        self.assertEqual(t["regions_with_samples"], 1)
        self.assertEqual(t["top_regions"][0]["events"], 10)

    def test_newer_entry_for_the_same_host_range_wins(self):
        m = P.parse_perf_map("0x1000 0x100 x_lite_0x10+4@0x10\n0x1000 0x100 x_heavy_0x10+4@0x10\n")
        index = sorted((e + (n,) for n, e in enumerate(m)), key=lambda e: e[0])
        self.assertEqual(P.perf_map_lookup(index, 0x1080)[2], "heavy")
        self.assertIsNone(P.perf_map_lookup(index, 0x1100))
        self.assertIsNone(P.perf_map_lookup([], 0x1080))

    def test_no_perf_map_means_unattributed(self):
        rows = [row("100", "unknown[+40e00010]", 600)]
        t = P.tier_attribution(rows, P.parse_maps(TRANSLATED_MAPS), {})
        self.assertEqual(t["events_by_tier"], {"lite": 0, "heavy": 0, "unattributed": 600})
        self.assertEqual(t["top_regions"], [])


# /proc/PID/maps around libberberis_arm64.so, as a Digitalis process on the VM had it (ANAL-384): the block is a static
# in the library's writable data. SCAN_BASE is the .data page; the .bss follows it.
SCAN_BASE = BLOCK_ADDR - 0x88
LIB_MAPS = f"""7f0000000000-7f0000000400 r--p 00278000 fe:0c 21566263  /system/lib64/libberberis_arm64.so
7f0000000400-7f0000000c00 ---p 00000000 00:00 0
{SCAN_BASE:x}-{SCAN_BASE + 0x1000:x} rw-p 002cc000 fe:0c 21566263  /system/lib64/libberberis_arm64.so
{SCAN_BASE + 0x1000:x}-{SCAN_BASE + 0x4000:x} rw-p 00000000 00:00 0  [anon:.bss]
{SCAN_BASE + 0x4000:x}-{SCAN_BASE + 0x5000:x} rw-p 00000000 00:00 0  [anon:libc_malloc]
7f1000000000-7f1000001000 rw-p 00010000 fe:0c 1  /system/lib64/libc.so
"""


class BlockScan(unittest.TestCase):
    def test_ranges_are_the_librarys_writable_data_and_its_bss(self):
        self.assertEqual(P.block_scan_ranges(LIB_MAPS), [(SCAN_BASE, SCAN_BASE + 0x1000),
                                                         (SCAN_BASE + 0x1000, SCAN_BASE + 0x4000)])
        self.assertEqual(P.block_scan_ranges("garbage\n"), [])
        other = LIB_MAPS.replace("libberberis_arm64.so", "libberberis_riscv64.so")
        self.assertEqual(P.block_scan_ranges(other), [])

    def test_find_skips_unaligned_and_implausible_headers(self):
        good = stats_block([1, 2, 3])
        bad = b"OBSTAT2\0" + (999).to_bytes(8, "little") + bytes(32)  # count out of range
        data = b"xOBSTAT2\0" + bytes(7) + bad + good
        base = 0x1000
        self.assertEqual(P.find_stats_block(data, base), base + 16 + len(bad))
        self.assertIsNone(P.find_stats_block(bytes(64), base))
        self.assertIsNone(P.find_stats_block(good[:20], base))


class PropsDevice:
    """getprop/setprop, the app's data directory and logcat, for TranslatorProps."""

    def __init__(self, props=None, maps=None, getprop_fails=False, memory=None):
        self.props = dict(props or {})
        self.files = dict(maps or {})
        self.memory = dict(memory or {})  # pid -> {address: bytes}
        self.parents = {}  # pid -> ppid
        self.getprop_fails, self.notes, self.log = getprop_fails, {}, []

    def sh(self, cmd, timeout=120, check=True):
        self.log.append(cmd)
        w = cmd.split()
        if w[0] == "getprop":
            return ("", 1) if self.getprop_fails else (self.props.get(w[1], "") + "\n", 0)
        if w[0] == "setprop":
            self.props[w[1]] = cmd.split(None, 2)[2].strip("'")
            return "", 0
        if w[0] == "cat":
            path = w[1].strip("'")
            if path.startswith("/proc/") and path.endswith("/stat"):
                pid = path.split("/")[2]
                ppid = self.parents.get(pid)
                return (f"{pid} (app proc) S {ppid} 1 1 0\n", 0) if ppid else ("No such process", 1)
            return (self.files[path], 0) if path in self.files else ("No such file", 1)
        if w[0] == "rm":
            self.files.pop(w[2].strip("'"), None)
            return "", 0
        if w[0] == "ls":
            n = sum(1 for f in self.files if f.rsplit("/", 1)[-1].startswith("perf-"))
            return f"{n}\n", 0 if n else 1
        if w[0] == "logcat":
            return STATS_LOG, 0
        if w[0] == "xxd":  # xxd -s ADDR -l LEN -p /proc/PID/mem
            addr, n, pid = int(w[2]), int(w[4]), w[6].split("/")[2]
            for base, data in self.memory.get(pid, {}).items():
                if base <= addr < base + len(data):
                    return data[addr - base:addr - base + n].hex() + "\n", 0
            return "xxd: /proc/x/mem: Input/output error", 1
        raise AssertionError(cmd)


class TranslatorPropsRun(unittest.TestCase):
    def test_set_collect_restore(self):
        mp = f"/data/data/{PKG}/perf-100.map"
        memory = {"100": {BLOCK_ADDR: stats_block([25, 2, 3])},
                  # forked from the app zygote (pid 90): no log line; the block is found in libberberis's data,
                  # with its own counts after a baseline
                  "102": {SCAN_BASE: bytes(BLOCK_ADDR - SCAN_BASE) + stats_block([7, 0, 1], owner=102,
                                                                                  baseline=[4, 0, 0])},
                  "103": {SCAN_BASE: bytes(0x1000)}}               # no block in its data
        zmap = f"/data/data/{PKG}/perf-90.map"
        dev = PropsDevice({"berberis.stats": "", "berberis.profiling": "1"},
                          {mp: PERF_MAP, zmap: "0x60000000 0x80 b/arm64/libgame.so_lite_0x7100003000+8@0x3000\n",
                           "/proc/102/maps": LIB_MAPS, "/proc/103/maps": LIB_MAPS},
                          memory=memory)
        dev.parents = {"100": "1", "102": "90", "103": "90"}
        tp = P.TranslatorProps(dev, PKG)
        tp.set()
        self.assertEqual(dev.props, {"berberis.stats": "1", "berberis.profiling": PKG})
        seen = {"100": PKG, "102": PKG + ":sandboxed", "103": PKG + ":other"}
        with tempfile.TemporaryDirectory() as t:
            res = tp.collect(t, seen)
            self.assertTrue(os.path.exists(f"{t}/perf-100.map"))
            with open(f"{t}/translator-stats.txt") as f:
                self.assertIn("@pid 100 @0x7f0000001000 enabled=1 owner=100 baseline_valid=0 installed_lite=25",
                              f.read())
            self.assertTrue(os.path.exists(f"{t}/perf-90.map"))
        st = res["stats"]
        self.assertEqual(sorted(st), ["100", "102", "103"])  # pid 101's log line isn't the app's
        self.assertEqual(st["100"]["counters"], {"installed_lite": 25, "installed_heavy": 2, "dispatcher_flushes": 3})
        self.assertTrue(st["100"]["enabled"])
        self.assertEqual(st["100"]["counts_from"], "process start")
        self.assertEqual(st["102"]["counters"]["installed_lite"], 7)
        self.assertEqual(st["102"]["since_fork"]["installed_lite"], 3)
        self.assertEqual(st["100"]["address_from"], "logged")
        self.assertEqual(st["102"]["address_from"], "found in libberberis_arm64.so's data")
        self.assertEqual(st["102"]["address"], hex(BLOCK_ADDR))
        self.assertIn("no block", st["103"]["error"])
        cov = res["perf_map_coverage"]
        self.assertEqual(cov["100"]["tier_profile"], "own map")
        self.assertEqual(cov["100"]["own_map_regions"], 5)
        self.assertEqual(cov["102"]["tier_profile"], "parent's map only (code it inherited)")  # an isolated process
        self.assertEqual(cov["102"]["parent_map_regions"], 1)
        # A sample in code the zygote translated before the fork is placed through the zygote's map.
        z = P.tier_attribution([row("102", "unknown[+60000010]", 9)], P.parse_maps(f"""@pid 102
60000000-60100000 r-xs 00000000 00:01 2 /memfd:exec (deleted)
7100000000-7100100000 r-xp 00000000 fe:07 1 {GAME}
"""), tp.perf_maps)
        self.assertEqual(z["events_by_tier"]["lite"], 9)
        self.assertEqual(z["top_regions"][0]["region"], f"{GAME}@0x3000")
        rows = [row("100", "unknown[+40e00010]", 600)]
        self.assertEqual(tp.tiers(rows, P.parse_maps(TRANSLATED_MAPS))["events_by_tier"]["lite"], 600)
        how = tp.restore({"100": PKG})
        self.assertEqual(dev.props, {"berberis.stats": "", "berberis.profiling": "1"})  # what they were
        self.assertNotIn(mp, dev.files)
        self.assertNotIn(zmap, dev.files)  # the zygote's map, read for inherited code, goes too
        self.assertIn("perf maps removed", how)
        self.assertNotIn("NOT restored", how)

    def test_unreadable_property_stops_before_any_change(self):
        dev = PropsDevice({"berberis.stats": "9"}, getprop_fails=True)
        tp = P.TranslatorProps(dev, PKG)
        with self.assertRaises(P.Fail):
            tp.set()
        self.assertFalse(any(c.startswith("setprop") for c in dev.log))
        self.assertEqual(tp.restore({}), "nothing set")

    def test_unreadable_memory_is_an_error_not_a_zero(self):
        dev = PropsDevice()  # the address is logged, but the process's memory can't be read
        tp = P.TranslatorProps(dev, PKG)
        tp.set()
        with tempfile.TemporaryDirectory() as t:
            res = tp.collect(t, {"100": PKG})
        self.assertIn("can't read /proc/100/mem", res["stats"]["100"]["error"])
        self.assertNotIn("counters", res["stats"]["100"])

    def test_no_address_logged_says_why(self):
        dev = PropsDevice()
        dev.sh = (lambda orig: lambda cmd, timeout=120, check=True: ("", 0) if cmd.startswith("logcat")
                  else orig(cmd, timeout, check))(dev.sh)
        tp = P.TranslatorProps(dev, PKG)
        tp.set()
        with tempfile.TemporaryDirectory() as t:
            res = tp.collect(t, {"555": PKG})
        self.assertIn("no address logged and none in libberberis_arm64.so's data", res["stats"]["555"]["error"])

    def test_log_line_rotated_out_the_block_is_found_in_memory(self):
        # ANAL-384's VM run: Chromium's start-up lines were gone from the 256 KiB main log 20 s later.
        dev = PropsDevice(maps={"/proc/100/maps": LIB_MAPS},
                          memory={"100": {SCAN_BASE: bytes(BLOCK_ADDR - SCAN_BASE) + stats_block([25, 2, 3])}})
        dev.sh = (lambda orig: lambda cmd, timeout=120, check=True: ("E/berberis(  100): Unknown function\n", 0)
                  if cmd.startswith("logcat") else orig(cmd, timeout, check))(dev.sh)
        tp = P.TranslatorProps(dev, PKG)
        tp.set()
        with tempfile.TemporaryDirectory() as t:
            res = tp.collect(t, {"100": PKG})
        st = res["stats"]["100"]
        self.assertEqual(st["counters"]["installed_lite"], 25)
        self.assertEqual(st["counts_from"], "process start")
        self.assertEqual(st["address_from"], "found in libberberis_arm64.so's data")
        # Only the library's writable mappings are read: the .data page and the .bss after it.
        reads = [c for c in dev.log if c.startswith("xxd") and "-l 48 " not in c]
        self.assertEqual(reads[0], f"xxd -s {SCAN_BASE} -l 4096 -p /proc/100/mem")


class Power(unittest.TestCase):
    def test_power(self):
        text = ("amd_pstate_status=active\nplatform_profile=balanced\n"
                "platform_profile_choices=quiet,balanced,performance\n"
                "policy policy0 cpus=0 driver=amd-pstate-epp governor=powersave epp=balance_performance "
                "epp_choices=default,performance max_khz=5157000 scaling_max_khz=5157000 cur_khz=1600000 boost=1\n"
                "policy policy4 cpus=4 driver=amd-pstate-epp governor=powersave epp=performance max_khz=3300000 "
                "scaling_max_khz=3300000 cur_khz=1600000 boost=1\n"
                "cpu cpu0 online=na prefcore_ranking=236 highest_perf=236 max_khz=5157000\n"
                "cpu cpu4 online=1 prefcore_ranking=145 highest_perf=145 max_khz=3300000\n")
        r = P.parse_power(text)
        self.assertEqual((r["amd_pstate_status"], r["platform_profile"]), ("active", "balanced"))
        self.assertEqual(r["epp_counts"], {"balance_performance": 1, "performance": 1})
        self.assertEqual(r["cpus_by_max_khz"], {"5157000": ["cpu0"], "3300000": ["cpu4"]})
        self.assertEqual(r["policies"][1]["epp"], "performance")


def write_runs(t, runs):
    dirs = []
    for name, run in runs.items():
        os.makedirs(f"{t}/{name}")
        if run:
            with open(f"{t}/{name}/run.json", "w") as f:
                json.dump(run, f)
        dirs.append(f"{t}/{name}")
    return dirs


FX_ARM = {"versionName": "159.0.0", "versionCode": 1590020, "primaryCpuAbi": "arm64-v8a"}
FX_X64 = {"versionName": "159.0.0", "versionCode": 1590010, "primaryCpuAbi": "x86_64"}
CR_ARM = {"versionName": "159.0.8141.0", "versionCode": 814100074, "primaryCpuAbi": "arm64-v8a"}
CR_X64 = {"versionName": "159.0.8142.0", "versionCode": 814200079, "primaryCpuAbi": "x86_64"}
FX, CR = "org.mozilla.fennec_fdroid", "org.chromium.chrome"


def start_run(pkg, app, cold, label="open, as found", **extra):
    return {"command": "start", "outcome": "ok", "result": {"package": pkg, "app": app, "label": label,
            "cold": {"total_ms": P.stats(cold)}, "warm": {"total_ms": P.stats([])}, **extra}}


def cpu_run(pkg, app, label="open, as found"):
    return {"command": "cpu", "outcome": "ok", "result": {"package": pkg, "app": app, "label": label,
            "attribution": P.cpu_attribution(P.parse_simpleperf_csv(CSV)[1], P.parse_maps(MAPS))}}


def table(runs):
    with tempfile.TemporaryDirectory() as t:
        dirs = write_runs(t, runs)
        err = tempfile.TemporaryFile("w+")
        with mock.patch.object(P.sys, "stderr", err):
            out = P.cmd_table(dirs)
        err.seek(0)
        skipped = err.read()
        err.close()
    return out, skipped


def rows_of(out, pkg):
    return [l for l in out.splitlines() if l.startswith(f"| {pkg} |")]


class Table(unittest.TestCase):
    def test_table(self):
        out, _ = table({
            "inv": {"command": "inventory", "outcome": "ok", "result": {"apps": [
                {"package": PKG, "version": "4.2.1", "versionCode": 4021, "primaryCpuAbi": "arm64-v8a",
                 "native_code": "translated (arm64-v8a)", "framework_hint": ["Flutter"],
                 "dexopt": "speed-profile/install"}]}},
            "start": start_run(PKG, {"versionName": "4.2.1", "versionCode": 4021, "primaryCpuAbi": "arm64-v8a"},
                               [900, 1000, 1100], label="home feed"),
            "cpu": cpu_run(PKG, {"versionName": "4.2.1", "versionCode": 4021, "primaryCpuAbi": "arm64-v8a"},
                           label="home feed"),
            "bad": None,
        })
        row = rows_of(out, PKG)
        self.assertEqual(len(row), 1, out)
        self.assertIn("| 4.2.1 (4021) | translated (arm64-v8a) | home feed | as found | Flutter | speed-profile/install | "
                      "1000 (900–1100, n=3) | na |", row[0])
        self.assertIn("ARM 62.0%, compile 5.0%, bridge 8.0%", row[0])

    def test_same_version_other_abi_is_another_row(self):
        """Firefox 159.0.0 switched from the ARM build to the x86_64 build: two rows, each with its own build."""
        out, _ = table({"before": start_run(FX, FX_ARM, [504]), "after": start_run(FX, FX_X64, [244]),
                        "cpu-before": cpu_run(FX, FX_ARM), "cpu-after": cpu_run(FX, FX_X64)})
        rows = rows_of(out, FX)
        self.assertEqual(len(rows), 2, out)
        arm = [r for r in rows if "(1590020)" in r][0]
        x64 = [r for r in rows if "(1590010)" in r][0]
        self.assertIn("| 159.0.0 (1590020) | translated (arm64-v8a) |", arm)
        self.assertIn("| 504 (504–504, n=1) |", arm)
        self.assertIn("| 159.0.0 (1590010) | x86_64 |", x64)
        self.assertIn("| 244 (244–244, n=1) |", x64)
        self.assertTrue(all("ARM 62.0%" in r for r in rows))

    def test_other_version_is_another_row_without_inventory(self):
        """Chromium 8141 (ARM) to 8142 (x86_64), no inventory: rows come from the runs alone."""
        out, _ = table({"before": start_run(CR, CR_ARM, [540]), "after": start_run(CR, CR_X64, [235])})
        rows = rows_of(out, CR)
        self.assertEqual(len(rows), 2, out)
        self.assertIn("| 159.0.8141.0 (814100074) | translated (arm64-v8a) | open, as found | as found | na | na | 540 ",
                      rows[0])
        self.assertIn("| 159.0.8142.0 (814200079) | x86_64 | open, as found | as found | na | na | 235 ", rows[1])

    def test_inventory_does_not_relabel_other_builds(self):
        """An inventory of the ARM build fills in only the ARM rows; the later x86_64 run keeps its own facts, and a
        newer inventory of the x86_64 build doesn't rewrite the ARM rows."""
        inv = lambda app, fw, dx: {"command": "inventory", "outcome": "ok", "result": {"apps": [
            {"package": CR, "version": app["versionName"], "versionCode": app["versionCode"],
             "primaryCpuAbi": app["primaryCpuAbi"], "native_code": P.native_code(app["primaryCpuAbi"], {}),
             "framework_hint": [fw], "dexopt": dx}]}}
        out, _ = table({"inv-arm": inv(CR_ARM, "Chromium", "verify/install"),
                        "inv-x64": inv(CR_X64, "Chromium", "speed-profile/bg-dexopt"),
                        "before": start_run(CR, CR_ARM, [540]), "after": start_run(CR, CR_X64, [235])})
        rows = rows_of(out, CR)
        self.assertEqual(len(rows), 2, out)
        self.assertIn("| translated (arm64-v8a) | open, as found | as found | Chromium | verify/install | 540 ", rows[0])
        self.assertIn("| x86_64 | open, as found | as found | Chromium | speed-profile/bg-dexopt | 235 ", rows[1])

    def test_inventory_alone_gets_its_row(self):
        out, _ = table({"inv": {"command": "inventory", "outcome": "ok", "result": {"apps": [
            {"package": FX, "version": "159.0.0", "versionCode": 1590010, "primaryCpuAbi": "x86_64",
             "native_code": "x86_64", "framework_hint": ["Gecko"], "dexopt": "verify/install"}]}}})
        rows = rows_of(out, FX)
        self.assertEqual(len(rows), 1)
        self.assertIn("| 159.0.0 (1590010) | x86_64 | - | as found | Gecko | verify/install | na | na | na |", rows[0])

    def test_record_without_app_facts(self):
        out, _ = table({"old": start_run(PKG, None, [700])})
        self.assertIn("| na (na) | none | open, as found |", rows_of(out, PKG)[0])

    def test_settings_get_their_own_rows_and_invalid_runs_are_skipped(self):
        app = {"versionName": "1.0", "versionCode": 1, "primaryCpuAbi": "x86_64"}
        out, skipped = table({
            "base": start_run(PKG, app, [1000], label="open"),
            "fixed": start_run(PKG, app, [700], label="open", power_change={
                "before": {"kind": "fixed-performance", "value": "false"}, "set": "true"}),
            "prof": start_run(PKG, app, [800], label="open", power_change={
                "before": {"kind": "platform-profile", "value": "balanced"}, "set": "performance"}),
            "invalid": {"command": "start", "outcome": "invalid: input on the laptop", "result": None},
            "partial": {"command": "start", "outcome": "ok", "result": {"label": "no package"}},
        })
        rows = rows_of(out, PKG)
        self.assertEqual(len(rows), 3, out)
        self.assertTrue(any("| as found |" in r and "| 1000 (1000–1000, n=1) |" in r for r in rows))
        self.assertTrue(any("| fixed-performance |" in r and "| 700 " in r for r in rows))
        self.assertTrue(any("| platform-profile=performance |" in r and "| 800 " in r for r in rows))
        self.assertIn("invalid: input on the laptop", skipped)
        self.assertIn("incomplete start record", skipped)


EPP_ON = "@v performance\n" * 4 + "@end\n"


class FakeDevice:
    """Just enough of a laptop for Power and Recorder: sysfs EPP and platform profile, fixed performance mode, an
    identity, and one simpleperf process. Every shell command is logged in order."""

    def __init__(self, ident=("SER1", "uuid-1", "aid-1"), epp="balance_performance", profile="balanced",
                 supported=True):
        self.serial, self.rooted, self.busy, self.notes = "fake", False, None, {}
        self.ident, self.base_epp, self.profile, self.supported = ident, epp, profile, supported
        self.fixed, self.log = False, []
        self.fail = {}         # command prefix -> times it fails before it works
        self.epp_unreadable = False
        self.rec_alive, self.rec_dies_on, self.rec_data = False, ("INT", "TERM", "KILL"), None
        self.probe_fails_after_kill = 0
        self.timeouts, self.find_times_out_while_alive = {}, False

    def _fails(self, key):
        n = self.fail.get(key, 0)
        if n:
            self.fail[key] = n - 1
        return n > 0

    def root(self):
        self.rooted = True

    def unroot(self):
        self.log.append("unroot")
        self.rooted = False

    def helper(self, args, timeout=120, check=True):
        return self.sh(f"sh {P.D}/device.sh {args}", timeout, check)

    @staticmethod
    def _kind(cmd):
        if cmd.startswith("for p in /proc/[0-9]*"):
            return "find"
        if cmd.startswith("rm -f") and "simpleperf record" in cmd:
            return "start"
        if cmd.startswith("if [ -e /proc/4242 ]"):
            return "probe"
        if cmd.startswith("kill -"):
            return "kill"
        return None

    def sh(self, cmd, timeout=120, check=True):
        """Device.sh, plus adb timeouts: self.timeouts[kind] = N makes the next N commands of that kind raise Fail as
        Device.run does. A timed-out start still starts the recorder (the answer is lost on the way back); a
        timed-out kill isn't delivered."""
        self.log.append(cmd)
        kind = self._kind(cmd)
        if kind == "find" and self.find_times_out_while_alive and self.rec_alive:
            raise P.Fail(f"adb shell {cmd[:40]}: no answer in {timeout} s")
        if kind in ("find", "probe", "kill") and self.timeouts.get(kind, 0):
            self.timeouts[kind] -= 1
            raise P.Fail(f"adb shell {cmd[:40]}: no answer in {timeout} s")
        out, rc = self._sh(cmd)
        if kind == "start" and self.timeouts.get("start", 0):
            self.timeouts["start"] -= 1
            raise P.Fail(f"adb shell {cmd[:40]}: no answer in {timeout} s")
        if check and rc:
            raise P.Fail(f"fake: {cmd[:60]}: exit {rc}")
        return out, rc

    def _sh(self, cmd):
        if cmd == P.EPP_READ:
            if self.epp_unreadable:
                return "@err /sys/devices/system/cpu/cpufreq/policy0/energy_performance_preference\n@end\n", 0
            v = "performance" if self.fixed else self.base_epp
            return "".join(f"@v {v}\n" for _ in range(4)) + "@end\n", 0
        if "getprop ro.serialno" in cmd:
            s, b, a = self.ident
            return f"s={s}\nb={b}\na={a}\n@end\n", 0
        if cmd == f"cat {P.Power.PROFILE}":
            return (self.profile + "\n", 0) if self.profile else ("", 1)
        if cmd == f"cat {P.Power.PROFILE}_choices":
            return "quiet balanced performance\n", 0
        if cmd.startswith("echo ") and cmd.endswith(f"> {P.Power.PROFILE}"):
            if self._fails("profile-write"):
                return "", 1
            self.profile = cmd.split("'")[1]
            return "", 0
        if cmd.startswith("cmd power set-fixed-performance-mode-enabled"):
            v = cmd.split()[3]
            if not self.supported or self._fails(f"fixed-{v}"):
                return "Failed to set FIXED_PERFORMANCE mode\n", 255
            self.fixed = v == "true"
            return "", 0
        if cmd.startswith("for p in /proc/[0-9]*"):  # find_recorders
            if self._fails("find"):
                return "", 1
            return ("@pid 4242\n" if self.rec_alive else "") + "@end\n", 0
        if cmd.startswith("rm -f") and "simpleperf record" in cmd:
            self.rec_alive, self.rec_data = True, cmd.split(" -o ")[1].split()[0]
            if self._fails("start-answer"):
                return "", 1
            return "@pid 4242\n", 0
        if cmd.startswith("if [ -e /proc/4242 ]"):  # Recorder.state
            if self._fails("probe"):
                return "", 1
            if not self.rec_alive:
                return "@gone\n@end\n", 0
            return f"@cmd simpleperf record -a -o {self.rec_data} \n@end\n", 0
        if cmd.startswith("kill -"):
            if cmd.split()[1][1:] in self.rec_dies_on:
                self.rec_alive = False
            if self.probe_fails_after_kill:
                self.fail["probe"] = self.probe_fails_after_kill
            return "", 0
        return "", 0


def pcache_listing(pkg=PKG, data=("directory", 10123), code_cache=("directory", 10123), cache=("directory", 10123),
                   entries=(("regular file", 4096, "b0123abcd-0.pcache"), ("regular file", 280, "b0123abcd-0.pidx"),
                            ("regular empty file", 0, "b0123abcd-0.lock")), end=True, count=None, extra=()):
    """pcache_listing_cmd's output for a cache as described; count overrides ls's count, extra adds lines."""
    d = f"/data/data/{pkg}"
    lines = []
    for path, st in ((d, data), (f"{d}/code_cache", code_cache), (f"{d}/code_cache/berberis", cache)):
        lines.append(f"@missing {path}" if st is None else f"@dir {st[0]}|{st[1]}|{path}")
    n = 0
    if cache is not None and cache[0] == "directory":
        lines += [f"@entry {k}|{s}|{d}/code_cache/berberis/{name}" for k, s, name in entries]
        n = len(entries)
        lines.append(f"@count {n if count is None else count}")
    lines += list(extra)
    return "\n".join(lines + ([f"@end {n}"] if end else [])) + "\n"


class PcacheDevice:
    """berberis.pcache, am force-stop, and an app's cache directory, for PcacheProp and pcache_clear. Every command is
    logged in order."""

    def __init__(self, prop="", listing=None, getprop_fails=False, setprop_ignored=False, restore_fails=False,
                 listing_rc=0, survivor=False, ps_fails=False):
        self.props = {"berberis.pcache": prop}
        self.listing = listing if listing is not None else pcache_listing()
        self.getprop_fails, self.setprop_ignored, self.restore_fails = getprop_fails, setprop_ignored, restore_fails
        self.listing_rc = listing_rc
        self.survivor = survivor  # a process of the app that force-stop doesn't end
        self.ps_fails = ps_fails
        self.notes, self.log, self.rooted, self.busy, self.sets = {}, [], False, None, 0

    def root(self):
        self.rooted = True

    def unroot(self):
        self.rooted = False

    def sh(self, cmd, timeout=120, check=True):
        self.log.append(cmd)
        if cmd.startswith("getprop "):
            return ("", 1) if self.getprop_fails else (self.props.get(cmd.split()[1], "") + "\n", 0)
        if cmd.startswith("setprop "):
            self.sets += 1
            if self.restore_fails and self.sets > 1:
                return "setprop: failed", 1
            if not self.setprop_ignored:
                self.props[cmd.split()[1]] = cmd.split(None, 2)[2].strip("'")
            return "", 0
        if cmd.startswith("am force-stop"):
            return "", 0
        if cmd.startswith("l=$(ps -A -o PID,NAME)"):
            if self.ps_fails:
                return "@ps-failed 1\n", 1
            return "@header\n" + ("@pid 4321\n" if self.survivor else "") + "@end\n", 0
        if cmd.startswith("e=0; for p in '/data/data/"):
            return self.listing, self.listing_rc
        if cmd.startswith("rm -f -- "):
            self.listing = pcache_listing(cache=None)
            return "", 0
        if cmd.startswith("rm -f "):  # the recorder's files
            return "", 0
        raise AssertionError(cmd)


class Pcache(unittest.TestCase):
    def test_values(self):
        dev = PcacheDevice()
        self.assertEqual(P.PcacheProp(dev, PKG, "on").value, f"on:{PKG}")
        self.assertEqual(P.PcacheProp(dev, PKG, "verify").value, f"verify:{PKG}")
        self.assertEqual(P.PcacheProp(dev, PKG, "off").value, "off")
        for bad_mode in ("ON", "yes", ""):
            with self.assertRaises(P.Fail):
                P.PcacheProp(dev, PKG, bad_mode)
        for bad_pkg in ("", "app", "org.example/../x", "org.example app", "org.example.app;rm"):
            with self.assertRaises(P.Fail):
                P.PcacheProp(dev, bad_pkg, "on")

    def test_set_then_finish_stops_the_app_before_putting_the_property_back(self):
        dev = PcacheDevice(prop="")
        pc = P.PcacheProp(dev, PKG, "on")
        pc.set()
        self.assertEqual(dev.props["berberis.pcache"], f"on:{PKG}")
        res = pc.finish()
        self.assertEqual(dev.props["berberis.pcache"], "")
        stop = next(i for i, c in enumerate(dev.log) if c.startswith("am force-stop"))
        restore = max(i for i, c in enumerate(dev.log) if c.startswith("setprop"))
        self.assertLess(stop, restore)
        self.assertEqual(res["restore"], "restored to ''")
        self.assertTrue(res["stopped"].startswith("confirmed"))
        self.assertNotIn("pcache_stop_unconfirmed", dev.notes)
        self.assertEqual(res["cache_after"], {"exists": True, "files": 3, "bytes": 4376,
                                              "names": ["b0123abcd-0.lock", "b0123abcd-0.pcache", "b0123abcd-0.pidx"]})
        self.assertNotIn("pcache_restore_failed", dev.notes)

    def test_unreadable_property_changes_nothing(self):
        dev = PcacheDevice(prop="on", getprop_fails=True)
        pc = P.PcacheProp(dev, PKG, "on")
        with self.assertRaises(P.Fail):
            pc.set()
        self.assertFalse(any(c.startswith("setprop") for c in dev.log))
        self.assertEqual(pc.finish()["restore"], "nothing set")

    def test_a_value_that_doesnt_take_is_put_back(self):
        dev = PcacheDevice(prop="off", setprop_ignored=True)
        pc = P.PcacheProp(dev, PKG, "verify")
        with self.assertRaisesRegex(P.Fail, "didn't take"):
            pc.set()
        self.assertEqual(pc.finish()["restore"], "restored to 'off'")

    def test_a_failed_restore_is_reported(self):
        dev = PcacheDevice(prop="", restore_fails=True)
        pc = P.PcacheProp(dev, PKG, "on")
        pc.set()
        self.assertTrue(pc.finish()["restore"].startswith("NOT restored"))
        self.assertTrue(dev.notes["pcache_restore_failed"])

    def _start_args(self, mode):
        return mock.Mock(package=PKG, component=None, label="", fixed_performance=False, platform_profile=None,
                         pcache=mode, runs=3, warm_runs=0, settle=0, idle_min=0, extra=[], period=0.1, timeout=10)

    def test_an_interrupted_start_still_stops_the_app_and_puts_the_property_back(self):
        dev = PcacheDevice(prop="")
        dev.helper = lambda args, timeout=120, check=True: ("", 0)

        def interrupted(*_):
            raise KeyboardInterrupt("signal 15")
        with mock.patch.object(P, "Gate"), mock.patch.object(P, "component", lambda *a: f"{PKG}/.Main"), \
                mock.patch.object(P, "app_facts", lambda *a: {}), mock.patch.object(P, "identity", lambda *a: {}), \
                mock.patch.object(P, "launch_once", interrupted), tempfile.TemporaryDirectory() as t:
            with self.assertRaises(KeyboardInterrupt):
                P.cmd_start(dev, self._start_args("on"), t, mock.Mock(restore=lambda: "nothing to restore"))
        self.assertEqual(dev.props["berberis.pcache"], "")
        stop = max(i for i, c in enumerate(dev.log) if c.startswith("am force-stop"))
        restore = max(i for i, c in enumerate(dev.log) if c.startswith("setprop"))
        self.assertLess(stop, restore)

    def test_a_failed_cpu_run_still_puts_the_property_back(self):
        dev = PcacheDevice(prop="on")  # an earlier value is restored, not cleared

        def helper(args, timeout=120, check=True):
            if args.startswith("launch"):
                raise P.Fail("adb: no answer")
            return "", 0
        dev.helper = helper
        rec = mock.Mock(pid=None, data="d", log="l")
        rec.resolve.return_value = "not started"
        a = mock.Mock(package=PKG, component=None, label="", seconds=1, event="cpu-clock", freq=10, translator=False,
                      pcache="verify", idle_min=0, extra=[], period=0.1, timeout=10)
        with mock.patch.object(P, "Gate"), mock.patch.object(P, "component", lambda *x: f"{PKG}/.Main"), \
                mock.patch.object(P, "app_facts", lambda *x: {}), mock.patch.object(P, "identity", lambda *x: {}), \
                mock.patch.object(P, "Recorder", lambda *x: rec), mock.patch.object(P.time, "sleep", lambda s: None), \
                tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(P.Fail, "no answer"):
                P.cmd_cpu(dev, a, t)
        self.assertEqual(dev.props["berberis.pcache"], "on")
        self.assertIn(f"setprop berberis.pcache 'verify:{PKG}'", dev.log)

    def test_a_process_left_running_fails_the_run_and_the_property_still_goes_back(self):
        for dev in (PcacheDevice(prop="", survivor=True), PcacheDevice(prop="", ps_fails=True)):
            pc = P.PcacheProp(dev, PKG, "on")
            pc.set()
            with mock.patch.object(P.time, "sleep", lambda s: None):
                res = pc.finish()
            self.assertTrue(res["stopped"].startswith("NOT confirmed"))
            self.assertTrue(dev.notes["pcache_stop_unconfirmed"])
            self.assertEqual(dev.props["berberis.pcache"], "")
            self.assertEqual(res["restore"], "restored to ''")

    def test_an_unconfirmed_stop_through_cmd_start_fails_the_run(self):
        dev = PcacheDevice(prop="", survivor=True)
        dev.helper = lambda args, timeout=120, check=True: ("", 0)
        launch = {"am": {"total_ms": 500, "launch_state": "COLD", "ok": True}, "epp_seen": [], "raw": ""}
        with mock.patch.object(P, "Gate"), mock.patch.object(P, "component", lambda *a: f"{PKG}/.Main"), \
                mock.patch.object(P, "app_facts", lambda *a: {}), mock.patch.object(P, "identity", lambda *a: {}), \
                mock.patch.object(P, "launch_once", lambda *a: dict(launch)), \
                mock.patch.object(P.time, "sleep", lambda s: None), tempfile.TemporaryDirectory() as t:
            res = P.cmd_start(dev, self._start_args("on"), t, mock.Mock(restore=lambda: "nothing to restore"))
        self.assertTrue(res["pcache"]["stopped"].startswith("NOT confirmed"))
        self.assertTrue(dev.notes["pcache_stop_unconfirmed"])
        self.assertEqual(dev.props["berberis.pcache"], "")

    def test_main_fails_a_run_whose_stop_or_restore_wasnt_confirmed(self):
        for flag, key in (("pcache_stop_unconfirmed", "pcache_stop"), ("pcache_restore_failed", "pcache_restore")):
            dev = FakeDevice()

            def fake_start(d, a, out, power, flag=flag):
                d.notes[flag] = True
                return {}
            with journal_dir() as j, tempfile.TemporaryDirectory() as t, \
                    mock.patch.object(P, "cmd_start", fake_start), mock.patch.object(P, "setup", lambda d: None), \
                    mock.patch.object(P, "cleanup", lambda d: "ok"):
                out = os.path.join(t, "run")
                rc = run_main(["--serial", "fake", "--journal", os.path.join(j, "power.json"), "start", out, PKG,
                               "--pcache", "on"], dev)
                with open(os.path.join(out, "run.json")) as f:
                    run = json.load(f)
            self.assertEqual(rc, P.FAILED, flag)
            self.assertIn("FAILED", run[key])

    def test_listing_accepts_only_the_apps_own_cache(self):
        self.assertEqual(P.parse_pcache_listing(pcache_listing(cache=None), PKG),
                         {"exists": False, "files": 0, "bytes": 0, "names": []})
        self.assertEqual(P.parse_pcache_listing(pcache_listing(entries=()), PKG)["files"], 0)
        bad = {
            "no answer": pcache_listing(end=False),
            "data directory is a link": pcache_listing(data=("symbolic link", 10123)),
            "code_cache is a link": pcache_listing(code_cache=("symbolic link", 10123)),
            "cache is a link": pcache_listing(cache=("symbolic link", 10123)),
            "cache owned by another uid": pcache_listing(cache=("directory", 10124)),
            "code_cache owned by another uid": pcache_listing(code_cache=("directory", 1000)),
            "a system uid": pcache_listing(data=("directory", 1000), code_cache=("directory", 1000),
                                           cache=("directory", 1000)),
            "a link inside": pcache_listing(entries=(("symbolic link", 10, "b0123abcd-0.pcache"),)),
            "a directory inside": pcache_listing(entries=(("directory", 4096, "b0123abcd-0.pcache"),)),
            "another file": pcache_listing(entries=(("regular file", 10, "notes.txt"),)),
            "a hidden file": pcache_listing(entries=(("regular file", 10, ".b0123abcd-0.pcache"),)),
            "an entry stat failed": pcache_listing(extra=(f"@error /data/data/{PKG}/code_cache/berberis/b1.pcache",)),
            "a directory stat failed": pcache_listing(extra=(f"@error /data/data/{PKG}/code_cache",)),
            "ls counted more": pcache_listing(count=4),
            "a stray line": pcache_listing(extra=("b0123abcd-0.pcache",)),
            "entries for a missing directory": pcache_listing(cache=None).replace("@end 0", "@entry regular file|1|"
                                                                                   f"/data/data/{PKG}/code_cache/"
                                                                                   "berberis/b1.pcache\n@end 1"),
        }
        for what, text in bad.items():
            with self.assertRaises(P.Fail, msg=what):
                P.parse_pcache_listing(text, PKG)
        with self.assertRaisesRegex(P.Fail, "exit 1"):
            P.parse_pcache_listing(pcache_listing(), PKG, rc=1)
        # A directory listed twice, or out of order.
        twice = pcache_listing().replace(f"@dir directory|10123|/data/data/{PKG}/code_cache\n",
                                         f"@dir directory|10123|/data/data/{PKG}\n")
        with self.assertRaises(P.Fail):
            P.parse_pcache_listing(twice, PKG)

    def test_clear_removes_exactly_the_listed_files(self):
        dev = PcacheDevice()
        res = P.pcache_clear(dev, PKG)
        self.assertEqual(res["removed"], 3)
        self.assertFalse(res["after"]["exists"])
        rm = [c for c in dev.log if c.startswith("rm ")][0]
        c = f"/data/data/{PKG}/code_cache/berberis"
        self.assertEqual(rm, " && ".join([f"rm -f -- '{c}/{n}'" for n in res["before"]["names"]] +
                                         [f"rmdir -- '{c}'"]))

    def test_clear_refuses_a_failed_listing_and_removes_nothing(self):
        for dev in (PcacheDevice(listing_rc=1),
                    PcacheDevice(listing=pcache_listing(extra=(f"@error /data/data/{PKG}/code_cache/berberis/x",)))):
            with self.assertRaises(P.Fail):
                P.pcache_clear(dev, PKG)
            self.assertFalse(any(c.startswith("rm") for c in dev.log))

    def test_listing_command_in_a_real_shell(self):
        """The generated command, run by sh over a copy of the layout, with stat and ls failing on demand."""
        with tempfile.TemporaryDirectory() as t:
            root = os.path.join(t, "data")
            c = os.path.join(root, PKG, "code_cache", "berberis")
            os.makedirs(c)
            for name, size in (("b0123abcd-0.pcache", 7), ("b0123abcd-0.pidx", 3), ("b0123abcd-0.lock", 0)):
                with open(os.path.join(c, name), "wb") as f:
                    f.write(b"x" * size)
            fake = os.path.join(t, "bin")
            os.makedirs(fake)
            real_stat = subprocess.run(["sh", "-c", "command -v stat"], capture_output=True, text=True).stdout.strip()
            with open(os.path.join(fake, "stat"), "w") as f:
                f.write(f"#!/bin/sh\ncase \"$*\" in *\"$FAIL_STAT\"*) [ -n \"$FAIL_STAT\" ] && "
                        f"{{ echo 'stat: I/O error' >&2; exit 1; }};; esac\nexec {real_stat} \"$@\"\n")
            os.chmod(os.path.join(fake, "stat"), 0o755)
            uid = os.getuid()
            cmd = P.pcache_listing_cmd(PKG).replace("/data/data/", root + "/")

            def listing(fail=""):
                env = dict(os.environ, PATH=fake + ":" + os.environ["PATH"], FAIL_STAT=fail)
                r = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True, env=env)
                return r.stdout.replace(root + "/", "/data/data/").replace(f"|{uid}|", "|10123|"), r.returncode
            text, rc = listing()
            self.assertEqual(rc, 0)
            self.assertEqual(P.parse_pcache_listing(text, PKG, rc),
                             {"exists": True, "files": 3, "bytes": 10,
                              "names": ["b0123abcd-0.lock", "b0123abcd-0.pcache", "b0123abcd-0.pidx"]})
            text, rc = listing("b0123abcd-0.pidx")  # one entry's stat fails
            self.assertEqual(rc, 1)
            self.assertIn("@error", text)
            with self.assertRaises(P.Fail):
                P.parse_pcache_listing(text, PKG, rc)

    def test_clear_refuses_an_unexpected_cache_and_removes_nothing(self):
        dev = PcacheDevice(listing=pcache_listing(entries=(("regular file", 10, "b0123abcd-0.pcache"),
                                                           ("regular file", 10, "keep-me.db"))))
        with self.assertRaises(P.Fail):
            P.pcache_clear(dev, PKG)
        self.assertFalse(any(c.startswith("rm") for c in dev.log))


def journal_dir():
    return tempfile.TemporaryDirectory()


def run_main(argv, dev):
    with mock.patch.object(P, "Device", lambda serial, adb: dev), \
            mock.patch.object(P.sys, "argv", ["app-perf"] + argv), \
            mock.patch.object(P.sys, "stdout", open(os.devnull, "w")) as out, \
            mock.patch.object(P.sys, "stderr", out):
        try:
            return P.main()
        finally:
            out.close()


class Recovery(unittest.TestCase):
    def setUp(self):
        self.patches = [mock.patch.object(P.time, "sleep", lambda s: None)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_epp_read(self):
        self.assertEqual(P.parse_epp_read("@v performance\n@v balance_power\n@v performance\n@end\n"),
                         "1:balance_power,2:performance")
        self.assertEqual(P.parse_epp_read("@end\n"), "na")
        with self.assertRaisesRegex(P.Fail, "can't read"):
            P.parse_epp_read("@v performance\n@err /sys/x\n@end\n")
        with self.assertRaisesRegex(P.Fail, "no complete answer"):
            P.parse_epp_read("@v performance\n")
        with self.assertRaisesRegex(P.Fail, "no complete answer"):
            P.parse_epp_read("sh: /data/local/tmp/openbook-app-perf/device.sh: not found\n")

    def test_identity(self):
        a = P.device_identity(FakeDevice())
        self.assertEqual(a, P.device_identity(FakeDevice()))
        self.assertNotEqual(a, P.device_identity(FakeDevice(ident=("SER2", "uuid-1", "aid-1"))))
        self.assertNotIn("SER1", a)
        with self.assertRaisesRegex(P.Fail, "can't identify"):
            P.device_identity(FakeDevice(ident=("", "", "aid-1")))

    def test_failed_restore_then_fresh_restore(self):
        """The reviewed failure: the run's restore fails and its clean-up removes the device helper; a fresh
        `restore` then reads the EPP itself, puts the mode back, checks the EPP and drops the journal."""
        dev = FakeDevice()
        with journal_dir() as t:
            j = f"{t}/journal"
            pw = P.Power(dev, j)
            pw.apply("fixed-performance", "true")
            self.assertTrue(dev.fixed)
            dev.fail["fixed-false"] = 2
            with self.assertRaises(P.Fail):
                pw.restore()
            self.assertTrue(os.path.exists(j))
            P.cleanup(dev)  # the run's clean-up: rm -rf of the helper directory, unroot
            self.assertIn(f"rm -rf {P.D}", dev.log)
            self.assertEqual(run_main(["--serial", "fake", "--journal", j, "restore"], dev), P.RESTORE_FAILED)
            self.assertTrue(os.path.exists(j))
            self.assertEqual(run_main(["--serial", "fake", "--journal", j, "restore"], dev), 0)
            self.assertFalse(os.path.exists(j))
            self.assertFalse(dev.fixed)
            self.assertEqual(pw.epp(), "4:balance_performance")
            self.assertFalse(any("device.sh" in c for c in dev.log if c.startswith("sh ")))

    def test_unreadable_epp_keeps_the_journal(self):
        dev = FakeDevice()
        with journal_dir() as t:
            j = f"{t}/journal"
            P.Power(dev, j).apply("fixed-performance", "true")
            dev.epp_unreadable = True
            self.assertEqual(run_main(["--serial", "fake", "--journal", j, "restore"], dev), P.RESTORE_FAILED)
            self.assertTrue(os.path.exists(j))

    def test_journal_of_another_device_is_refused(self):
        a, b = FakeDevice(profile="balanced"), FakeDevice(ident=("SER2", "uuid-2", "aid-2"), profile="quiet")
        with journal_dir() as t:
            j = f"{t}/journal"
            P.Power(a, j).apply("platform-profile", "performance")
            self.assertEqual(a.profile, "performance")
            self.assertEqual(run_main(["--serial", "fake", "--journal", j, "restore"], b), P.RESTORE_FAILED)
            self.assertEqual(b.profile, "quiet")
            self.assertFalse(any(c.endswith(f"> {P.Power.PROFILE}") for c in b.log))
            self.assertTrue(os.path.exists(j))
            self.assertEqual(run_main(["--serial", "fake", "--journal", j, "restore"], a), 0)
            self.assertEqual(a.profile, "balanced")
            self.assertFalse(os.path.exists(j))

    def test_journal_without_device_is_refused(self):
        dev = FakeDevice(profile="performance")
        with journal_dir() as t:
            j = f"{t}/journal"
            with open(j, "w") as f:
                json.dump({"kind": "platform-profile", "value": "balanced", "epp": "na", "serial": "fake"}, f)
            self.assertEqual(run_main(["--serial", "fake", "--journal", j, "restore"], dev), P.RESTORE_FAILED)
            self.assertEqual(dev.profile, "performance")
            self.assertTrue(os.path.exists(j))

    def test_unsupported_mode_changes_nothing(self):
        dev = FakeDevice(supported=False)
        with journal_dir() as t:
            j = f"{t}/journal"
            with self.assertRaisesRegex(P.Fail, "fixed performance mode false"):
                P.Power(dev, j).apply("fixed-performance", "true")
            self.assertFalse(os.path.exists(j))


class Recording(unittest.TestCase):
    def setUp(self):
        clock = itertools.count(0, 0.5)
        self.patches = [mock.patch.object(P.time, "sleep", lambda s: None),
                        mock.patch.object(P.time, "time", lambda: next(clock))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_input_during_recording_stops_the_recorder_before_its_files_go(self):
        dev = FakeDevice()
        rec = P.Recorder(dev, f"{P.D}/perf.data", f"{P.D}/record.log")
        rec.start("cpu-clock", 1000, 22)
        self.assertEqual(rec.pid, "4242")

        def gate():
            raise P.Invalid("input on the laptop during the recording")
        with self.assertRaises(P.Invalid):
            rec.wait(52, gate)
        self.assertTrue(rec.alive())
        self.assertEqual(rec.stop(), "stopped with SIGINT")
        kill = dev.log.index("kill -INT 4242")
        dev.sh(f"rm -f {rec.data} {rec.log}")
        self.assertLess(kill, len(dev.log) - 1)

    def test_escalates_to_kill(self):
        dev = FakeDevice()
        dev.rec_dies_on = ("KILL",)
        rec = P.Recorder(dev, "d", "l")
        rec.start("cpu-clock", 1000, 22)
        self.assertEqual(rec.stop(), "stopped with SIGKILL")
        sent = [c for c in dev.log if c.startswith("kill -")]
        self.assertEqual(sent[0], "kill -INT 4242")
        self.assertIn("kill -TERM 4242", sent)
        self.assertEqual(sent[-1], "kill -KILL 4242")

    def test_survivor_keeps_files_and_root(self):
        dev = FakeDevice()
        dev.rec_dies_on = ()
        dev.rooted = True
        rec = P.Recorder(dev, "d", "l")
        rec.start("cpu-clock", 1000, 22)
        with self.assertRaisesRegex(P.Fail, "still running after INT, TERM and KILL"):
            rec.stop()
        self.assertTrue(dev.busy)
        self.assertIn("skipped", P.cleanup(dev))
        self.assertNotIn(f"rm -rf {P.D}", dev.log)
        self.assertTrue(dev.rooted)

    def started(self, **kw):
        dev = FakeDevice()
        for k, v in kw.items():
            setattr(dev, k, v)
        dev.rooted = True
        rec = P.Recorder(dev, P.RECORDER_DATA, f"{P.D}/record.log")
        rec.start("cpu-clock", 1000, 22)
        return dev, rec

    def test_failed_probe_before_stop_is_not_gone(self):
        """The reviewed defect: a status probe that fails must not read as 'ended'. No signal is guessed at, the
        files and root stay, and the outcome is recorded; once the device answers again, stop() confirms the end and
        the clean-up runs."""
        dev, rec = self.started()
        dev.fail["probe"] = 99
        with self.assertRaisesRegex(P.Fail, "can't be read"):
            rec.stop()
        self.assertFalse(any(c.startswith("kill ") for c in dev.log))
        self.assertIn("can't be read", dev.busy)
        self.assertIn("can't be read", dev.notes["recorder"])
        self.assertIn("skipped", P.cleanup(dev))
        self.assertNotIn(f"rm -rf {P.D}", dev.log)
        self.assertTrue(dev.rooted)
        dev.fail["probe"] = 0
        self.assertEqual(rec.stop(), "stopped with SIGINT")
        self.assertIsNone(dev.busy)
        self.assertEqual(P.cleanup(dev), "ok")
        self.assertIn(f"rm -rf {P.D}", dev.log)
        self.assertFalse(dev.rooted)

    def test_one_failed_probe_is_retried(self):
        dev, rec = self.started()
        dev.fail["probe"] = 1
        self.assertEqual(rec.stop(), "stopped with SIGINT")
        self.assertIsNone(dev.busy)

    def test_failed_probes_after_a_signal(self):
        dev, rec = self.started(probe_fails_after_kill=99)
        with self.assertRaisesRegex(P.Fail, "can't be read"):
            rec.stop()
        self.assertTrue(dev.busy)
        self.assertIn("skipped", P.cleanup(dev))
        self.assertTrue(dev.rooted)
        dev.probe_fails_after_kill, dev.fail["probe"] = 0, 0
        self.assertEqual(rec.stop(), "already ended")
        self.assertIsNone(dev.busy)
        self.assertEqual(P.cleanup(dev), "ok")

    def test_wait_does_not_end_on_a_failed_probe(self):
        dev, rec = self.started()
        dev.fail["probe"] = 99
        with self.assertRaisesRegex(P.Fail, "not confirmed finished"):
            rec.wait(5, lambda: None)

    def test_lost_start_answer_adopts_the_recorder(self):
        dev = FakeDevice()
        dev.fail["start-answer"] = 1
        rec = P.Recorder(dev, P.RECORDER_DATA, f"{P.D}/record.log")
        with self.assertRaisesRegex(P.Fail, "adopted pid 4242: stopped with SIGINT"):
            rec.start("cpu-clock", 1000, 22)
        self.assertFalse(dev.rec_alive)
        self.assertIsNone(dev.busy)
        self.assertEqual(rec.stop(), "already ended")

    def test_lost_start_answer_and_no_check_is_busy(self):
        dev = FakeDevice()
        dev.fail["start-answer"], dev.fail["find"] = 1, 0
        rec = P.Recorder(dev, P.RECORDER_DATA, f"{P.D}/record.log")
        orig = dev._sh

        def sh(cmd):  # the first find (before starting) answers; the one after the lost answer fails
            if cmd.startswith("for p in /proc/[0-9]*") and dev.rec_alive:
                return "", 1
            return orig(cmd)
        dev._sh = sh
        with self.assertRaisesRegex(P.Fail, "can't be checked"):
            rec.start("cpu-clock", 1000, 22)
        self.assertTrue(dev.busy)

    def test_an_earlier_recorder_blocks_a_new_one(self):
        dev = FakeDevice()
        dev.rec_alive, dev.rec_data = True, P.RECORDER_DATA
        rec = P.Recorder(dev, P.RECORDER_DATA, f"{P.D}/record.log")
        with self.assertRaisesRegex(P.Fail, "earlier run's simpleperf"):
            rec.start("cpu-clock", 1000, 22)
        self.assertFalse(any("simpleperf record" in c for c in dev.log))
        self.assertIn("skipped", P.cleanup(dev))

    def test_cleanup_checks_for_recorders(self):
        dev = FakeDevice()
        dev.rooted = True
        dev.fail["find"] = 1
        self.assertIn("can't check", P.cleanup(dev))
        self.assertNotIn(f"rm -rf {P.D}", dev.log)
        self.assertTrue(dev.rooted)

    def cpu_device(self, input_at=4):
        """A FakeDevice that also answers cmd_cpu's gate, launch, pids and maps; input appears at the input_at-th
        gate check (None: never)."""
        dev = FakeDevice()
        state = {"idle_calls": 0, "launched": False}
        base = dev._sh
        dev.props = {"berberis.stats": "", "berberis.profiling": ""}

        def sh(cmd):
            if cmd.startswith("getprop "):
                return dev.props.get(cmd.split()[1], "") + "\n", 0
            if cmd.startswith("setprop "):
                _, name, value = cmd.split(None, 2)
                dev.props[name] = value.strip("'")
                return "", 0
            if cmd.endswith("gpu-diag-device.sh idle"):
                state["idle_calls"] += 1
                token = "999" if input_at and state["idle_calls"] >= input_at else "100"
                return (f"user_activity_uptime_ms={token} idle_ms=900000\nwakefulness=Awake\n"
                        "keyguard_showing=false\naudio_started=0\n"), 0
            if "device.sh pids" in cmd:
                return ("500 " + PKG + "\n" if state["launched"] else ""), 0
            if cmd.startswith("l=$(ps -A -o PID,NAME)"):  # the gate's strict query
                return "@header\n" + ("@pid 500\n" if state["launched"] else "") + "@end\n", 0
            if "resolve-activity" in cmd:
                return f"{PKG}/.Main\n", 0
            if "device.sh launch" in cmd:
                state["launched"] = True
                return "@t0 1\n" + AM_COLD + "@t1 2 rc=0\n", 0
            if "device.sh maps" in cmd:
                return MAPS, 0
            return base(cmd)
        dev._sh = sh
        args = mock.Mock(package=PKG, idle_min=10, component=None, label="", seconds=20, event="cpu-clock", freq=1000,
                         period=0.1, extra=[], timeout=120, translator=False, pcache=None)
        return dev, args

    @staticmethod
    def removed_data(log):
        return [i for i, c in enumerate(log) if c.startswith("rm -f") and "perf.data" in c and "simpleperf" not in c]

    def test_cpu_run_cancelled_mid_recording(self):
        """cmd_cpu itself: input during the recording stops the run; the recorder is stopped, then its files are
        removed, then the app is stopped, then adbd unroots."""
        dev, a = self.cpu_device()
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(P.Invalid, "during the recording"):
                P.cmd_cpu(dev, a, t)
        log = dev.log
        kill = log.index("kill -INT 4242")
        rm = self.removed_data(log)[0]
        stop_app = log.index(f"am force-stop '{PKG}'")
        self.assertLess(kill, rm)
        self.assertLess(rm, stop_app)
        self.assertLess(stop_app, log.index("unroot"))
        self.assertFalse(dev.rec_alive)
        self.assertEqual(dev.notes["recorder"], "pid 4242: stopped with SIGINT")

    def test_cpu_translator_props_put_back_when_cancelled(self):
        """cpu --translator: the properties are set as root before the launch, and put back to what they were even
        when input stops the run, after the app is stopped and before adbd unroots."""
        dev, a = self.cpu_device()
        a.translator = True
        dev.props["berberis.profiling"] = "1"
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(P.Invalid, "during the recording"):
                P.cmd_cpu(dev, a, t)
        log = dev.log
        set_stats = log.index("setprop berberis.stats '1'")
        launch = next(i for i, c in enumerate(log) if "device.sh launch" in c)
        put_back = log.index("setprop berberis.profiling '1'")
        self.assertLess(set_stats, launch)
        self.assertLess(log.index(f"am force-stop '{PKG}'"), put_back)
        self.assertLess(put_back, log.index("unroot"))
        self.assertEqual(dev.props, {"berberis.stats": "", "berberis.profiling": "1"})
        self.assertIn("berberis.stats restored", dev.notes["translator_props"])

    def test_start_times_out_after_starting(self):
        """The reviewed lost-start case: the start command times out after the recorder began. It's found,
        adopted and stopped before anything is removed."""
        dev, rec = FakeDevice(), None
        dev.timeouts["start"] = 1
        rec = P.Recorder(dev, P.RECORDER_DATA, f"{P.D}/record.log")
        with self.assertRaisesRegex(P.Fail, "adopted pid 4242: stopped with SIGINT"):
            rec.start("cpu-clock", 1000, 22)
        self.assertFalse(dev.rec_alive)
        self.assertIsNone(dev.busy)

    def test_cpu_start_and_search_time_out(self):
        """cmd_cpu with the start's answer lost and the search for the recorder timing out too: nothing is removed
        and adbd stays root while it's unresolved; once adb answers again, resolve() stops it and clean-up runs."""
        dev, a = self.cpu_device(input_at=None)
        dev.timeouts["start"], dev.find_times_out_while_alive = 1, True
        dev.rooted = True
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(P.Fail, "can't be checked"):
                P.cmd_cpu(dev, a, t)
        self.assertTrue(dev.rec_alive)
        self.assertEqual(self.removed_data(dev.log), [])
        self.assertNotIn("unroot", dev.log)
        self.assertTrue(dev.rooted)
        self.assertIn("can't be checked", dev.busy)
        self.assertIn("skipped", P.cleanup(dev))
        self.assertNotIn(f"rm -rf {P.D}", dev.log)
        # Later, adb answers again: the same recorder object finds, adopts and stops it, then clean-up runs.
        dev.find_times_out_while_alive = False
        rec = P.Recorder(dev, P.RECORDER_DATA, f"{P.D}/record.log")
        rec.owns_busy = True
        self.assertEqual(rec.resolve(), "adopted pid 4242: stopped with SIGINT")
        self.assertIsNone(dev.busy)
        self.assertEqual(P.cleanup(dev), "ok")
        self.assertFalse(dev.rooted)

    def test_probe_times_out(self):
        """The reviewed status case: probes that time out make the state unknown. No signal is sent and the files
        and root stay; when adb answers again the stop completes and clean-up runs."""
        dev, rec = self.started()
        dev.timeouts["probe"] = 99
        with self.assertRaisesRegex(P.Fail, "can't be read"):
            rec.stop()
        self.assertFalse(any(c.startswith("kill ") for c in dev.log))
        self.assertIn("skipped", P.cleanup(dev))
        self.assertTrue(dev.rooted)
        dev.timeouts["probe"] = 0
        self.assertEqual(rec.stop(), "stopped with SIGINT")
        self.assertEqual(P.cleanup(dev), "ok")

    def test_wait_times_out_on_probes(self):
        dev, rec = self.started()
        dev.timeouts["probe"] = 999
        with self.assertRaisesRegex(P.Fail, "not confirmed finished"):
            rec.wait(5, lambda: None)
        self.assertTrue(dev.busy)

    def test_kill_times_out(self):
        dev, rec = self.started()
        dev.timeouts["kill"] = 1  # SIGINT is lost; TERM gets through
        self.assertEqual(rec.stop(), "stopped with SIGTERM")
        self.assertIsNone(dev.busy)

    def test_cleanup_search_times_out(self):
        dev = FakeDevice()
        dev.rooted = True
        dev.timeouts["find"] = 1
        self.assertIn("can't check", P.cleanup(dev))
        self.assertNotIn(f"rm -rf {P.D}", dev.log)
        self.assertTrue(dev.rooted)


class Wrapper(unittest.TestCase):
    def test_journal_blocks_runs(self):
        """A kept power journal refuses every command but restore, before touching the device."""
        with tempfile.TemporaryDirectory() as t:
            j = f"{t}/journal"
            with open(j, "w") as f:
                f.write('{"kind": "platform-profile", "value": "balanced"}')
            r = subprocess.run([sys.executable, spec.origin, "--serial", "test-serial", "--adb", "/bin/false",
                                "--journal", j, "start", f"{t}/out", PKG], capture_output=True, text=True)
            self.assertEqual(r.returncode, P.RESTORE_FAILED, r.stderr)
            self.assertIn("restore", r.stderr)
            self.assertFalse(os.path.exists(f"{t}/out"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
