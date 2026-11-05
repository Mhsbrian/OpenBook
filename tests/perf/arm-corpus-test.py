#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/perf/arm-corpus.py and scripts/perf/simd-bench/check-isa.py on synthetic output (no device,
no toolchain). python3 tests/perf/arm-corpus-test.py (tests/run.sh runs it)"""
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import types
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PERF = os.path.join(HERE, "..", "..", "scripts", "perf")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


C = load("arm_corpus", os.path.join(PERF, "arm-corpus.py"))
ISA = load("check_isa", os.path.join(PERF, "simd-bench", "check-isa.py"))

COREMARK = """2K performance run parameters for coremark.
CoreMark Size    : 666
Total ticks      : 21640
Total time (secs): 21.640000
Iterations/Sec   : 27726.432532
Iterations       : 600000
Compiler version : Clang 21.0.0
Correct operation validated. See README.md for run and reporting rules.
CoreMark 1.0 : 27726.432532 / Clang 21.0.0 -O2 / Heap
"""
SIMD_ARM = """@mask pid 2690's current affinity mask: 80
{"tool":"simd-bench","version":1,"arch":"aarch64","hwcap":"0x9fb","cpu":7,"allowed_cpus":1,"crc":1,"aes":1,"repeats":5,"scale":1,"elements":16384,"aes_reference_ok":1}
{"kernel":"triad_f32","class":"baseline","checksum":"0xf7b7aeb7eff29531","ok":true,"calls":80000,"ns_per_elem_median":0.400000,"ns_per_elem_min":0.39,"cpu":7}
{"kernel":"aes128","class":"optional","checksum":"0x90a34a9b41000a6b","ok":true,"calls":90000,"ns_per_elem_median":0.460000,"ns_per_elem_min":0.45,"cpu":7}
@rc 0
"""
SIMD_X86 = SIMD_ARM.replace('"aarch64"', '"x86_64"').replace("0.400000", "0.080000").replace("0.460000", "0.069000")


class CorpusTest(unittest.TestCase):
    def test_the_corpus_parses_and_every_app_has_both_abis(self):
        rows = C.load_corpus()
        self.assertTrue(rows)
        for rid in {r["id"] for r in rows}:
            for abi in C.ABIS:
                r = C.row_for(rows, rid, abi)
                self.assertIn(r["abi"], ("fat", abi))
        for r in rows:
            self.assertEqual(len(r["sha256"]), 64 if r["sha256"] != "-" else 1, r["id"])
            if r["source"] == "fdroid" or r["source"].startswith("github:"):
                self.assertEqual(len(r["signer_sha256"]), 64, r["id"])
            self.assertIn(r["task"], ("startup", "glmark2", "bench"))

    def test_row_for_prefers_the_abi_specific_build(self):
        rows = [{"id": "x", "abi": "arm64-v8a"}, {"id": "x", "abi": "x86_64"}, {"id": "y", "abi": "fat"}]
        self.assertEqual(C.row_for(rows, "x", "x86_64")["abi"], "x86_64")
        self.assertEqual(C.row_for(rows, "y", "arm64-v8a")["abi"], "fat")
        with self.assertRaises(C.Fail):
            C.row_for(rows, "z", "x86_64")

    def test_a_malformed_row_is_an_error(self):
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as f:
            f.write("# c\nid\tpackage\nx\ty\tz\n")
        try:
            with self.assertRaises(C.Fail):
                C.load_corpus(f.name)
        finally:
            os.remove(f.name)


class JournalTest(unittest.TestCase):
    def test_only_this_devices_installs_are_mine_and_drop_cleans_up(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "j.json")
            a, b = C.Journal(path, "dev-a"), C.Journal(path, "dev-b")
            a.put("org.x", {"id": "x"})
            self.assertIn("org.x", a.mine())
            self.assertEqual(b.mine(), {})
            a.drop("org.x")
            with open(path) as f:
                self.assertEqual(json.load(f), {})


class PermissionsTest(unittest.TestCase):
    def test_only_ungranted_unfixed_runtime_permissions(self):
        dump = """    Package [org.x] (abc):
      runtime permissions:
        android.permission.POST_NOTIFICATIONS: granted=false, flags=[ USER_SENSITIVE_WHEN_GRANTED]
        android.permission.CAMERA: granted=false, flags=[ USER_SET|USER_FIXED]
        android.permission.RECORD_AUDIO: granted=false
        android.permission.ACCESS_LOCAL_NETWORK: granted=true, flags=[ REVOKE_WHEN_REQUESTED]
      enabledComponents:
        android.permission.READ_CONTACTS: granted=false
"""
        self.assertEqual(C.ungranted_runtime_permissions(dump),
                         ["android.permission.POST_NOTIFICATIONS", "android.permission.RECORD_AUDIO"])
        every = C.runtime_permissions(dump)
        self.assertEqual(sorted(every), ["android.permission.ACCESS_LOCAL_NETWORK", "android.permission.CAMERA",
                                         "android.permission.POST_NOTIFICATIONS", "android.permission.RECORD_AUDIO"])
        self.assertEqual(every["android.permission.CAMERA"], "granted=false, flags=[ USER_SET|USER_FIXED]")


class PackageDumpTest(unittest.TestCase):
    def test_saved_dump_keeps_only_the_packages_section(self):
        dump = """Activity Resolver Table:
  Schemes:
      https:
        1a2b org.example.game/.Main filter 3c4d
Queries:
  system apps queryable: false
  queries via component:
    org.owner.browser:
      org.example.game
Packages:
  Package [org.example.game] (5e6f):
    primaryCpuAbi=arm64-v8a
    runtime permissions:
      android.permission.CAMERA: granted=false, flags=[ USER_SET|USER_FIXED]
Dexopt state:
  [org.example.game]
"""
        saved = C.package_section(dump)
        self.assertNotIn("org.owner.browser", saved)  # another installed app, from Queries:
        self.assertNotIn("Activity Resolver Table", saved)
        self.assertTrue(saved.startswith("Packages:\n"))
        self.assertIn("primaryCpuAbi=arm64-v8a", saved)
        self.assertEqual(C.runtime_permissions(saved), C.runtime_permissions(dump))
        self.assertEqual(C.package_section("no sections\n"), "")


class ExeTest(unittest.TestCase):
    def test_coremark_parse(self):
        r = C.parse_coremark(COREMARK)
        self.assertAlmostEqual(r["iterations_per_sec"], 27726.432532)
        self.assertTrue(r["valid"])
        short = COREMARK.replace("Correct operation validated.", "ERROR! Must execute for at least 10 secs")
        self.assertFalse(C.parse_coremark(short)["valid"])

    def test_simd_parse_and_a_wrong_checksum(self):
        r = C.parse_simd(SIMD_ARM)
        self.assertTrue(r["valid"])
        self.assertEqual(r["header"]["arch"], "aarch64")
        self.assertFalse(C.parse_simd(SIMD_ARM.replace('"ok":true', '"ok":false', 1))["valid"])
        self.assertFalse(C.parse_simd("")["valid"])

    def test_taskset_mask(self):
        self.assertEqual(C.parse_taskset("pid 2690's current affinity mask: 80"), 0x80)
        self.assertIsNone(C.parse_taskset("taskset: bad"))

    def test_core_classes_g14_and_vm(self):
        g14 = "\n".join([f"cpu cpu{i} online=1 prefcore_ranking=na highest_perf=na max_khz=5157000" for i in range(8)] +
                        [f"cpu cpu{i} online=1 prefcore_ranking=na highest_perf=na max_khz=3293000" for i in range(8, 24)])
        cls = C.core_classes(g14.replace("cpu cpu0 online=1", "cpu cpu0 online=na"))
        self.assertEqual([c["class"] for c in cls], ["fast", "efficient"])
        self.assertEqual((cls[0]["cpu"], cls[1]["cpu"]), (7, 23))
        vm = "\n".join(f"cpu cpu{i} online=1 prefcore_ranking=na highest_perf=na max_khz=na" for i in range(4))
        self.assertEqual([(c["class"], c["cpu"]) for c in C.core_classes(vm)], [("all", 3)])

    def test_run_order_alternates_abi_order_by_round(self):
        cls = [{"class": "fast", "cpu": 7}, {"class": "efficient", "cpu": 23}]
        plan = C.run_order(2, cls, ["coremark"])
        self.assertEqual(len(plan), 2 * 2 * 1 * 2)
        r1 = [p[3] for p in plan if p[0] == 1 and p[1]["class"] == "fast"]
        r2 = [p[3] for p in plan if p[0] == 2 and p[1]["class"] == "fast"]
        self.assertEqual(r1, list(C.ABIS))
        self.assertEqual(r2, list(C.ABIS[::-1]))

    def test_perf_stat_wrap_parse_and_exit_status(self):
        w = C.perf_wrap("/d/bin/coremark-arm64 0x0 0x0 0x66 600000")
        self.assertNotIn("'", w)  # it goes inside run_workload's sh -c '...'
        self.assertTrue(w.startswith("simpleperf stat --csv -e cpu-cycles,instructions,branch-misses,"
                                     "stalled-cycles-frontend -- sh -c \""))
        # The innermost shell gets $? (escaped once for the middle shell), so the benchmark's own status is printed.
        middle = C.perf_wrap("(exit 3)").split(" -- ", 1)[1]  # what the middle shell runs, simpleperf left out
        out = subprocess.run(["sh", "-c", middle], capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), "@wrc 3")
        text = (COREMARK + "@wrc 0\nPerformance counter statistics,\n22532752,cpu-cycles,2.751608,GHz,\n"
                "35356380,instructions,4.318,G/sec,\n141284,branch-misses,3.384,M/sec,\n"
                "21077398,stalled-cycles-frontend,504.903,M/sec,\nTotal test time,0.009751,seconds,\n@rc 0\n")
        p = C.parse_perf_stat(text)
        self.assertEqual(p["cpu-cycles"], 22532752)
        self.assertEqual(p["stalled-cycles-frontend"], 21077398)
        self.assertAlmostEqual(p["ipc"], 35356380 / 22532752, places=4)
        self.assertIsNone(C.parse_perf_stat(COREMARK))
        self.assertTrue(C.perf_complete(p))
        # The Checker's case (PR #191 review): a record with only some of the counters doesn't count.
        partial = C.parse_perf_stat("Performance counter statistics,\n141284,branch-misses,3.384,M/sec,\n")
        self.assertEqual(partial, {"branch-misses": 141284})
        self.assertFalse(C.perf_complete(partial))
        self.assertFalse(C.perf_complete(None))
        self.assertFalse(C.perf_complete({k: v for k, v in p.items() if k != "stalled-cycles-frontend"}))
        self.assertEqual(C.perf_run(text, True), (p, True))
        self.assertFalse(C.perf_run(text, False)[1])  # the benchmark's own validation still decides
        cut = text.replace("21077398,stalled-cycles-frontend,504.903,M/sec,\n", "")
        self.assertFalse(C.perf_run(cut, True)[1])
        self.assertFalse(C.perf_run(text.replace("@wrc 0\n", ""), True)[1])
        self.assertEqual(C.run_rc(text), 0)
        self.assertEqual(C.run_rc("@wrc 2\n@rc 0\n"), 2)  # simpleperf's 0 doesn't hide the benchmark's failure
        self.assertEqual(C.run_rc("@rc 1\n"), 1)
        ok = {"valid": True, "mask_ok": True, "rc": 0}
        runs = [{"class": "fast", "bench": "coremark", "abi": "arm64-v8a", "perf": dict(p, instructions=v), **ok}
                for v in (10, 30, 20)]
        runs.append({"class": "fast", "bench": "coremark", "abi": "arm64-v8a", "perf": dict(p, instructions=999),
                     **ok, "rc": 1})
        s = C.summarize_perf(runs)
        self.assertEqual(s["fast/coremark/arm64-v8a"]["n"], 3)
        self.assertEqual(s["fast/coremark/arm64-v8a"]["median"]["instructions"], 20)

    def test_summary_ratio_is_translated_over_native_speed_from_valid_runs_only(self):
        ok = {"valid": True, "mask_ok": True, "rc": 0}
        runs = [
            {"class": "all", "bench": "coremark", "abi": "arm64-v8a", "iterations_per_sec": 10000.0, **ok},
            {"class": "all", "bench": "coremark", "abi": "x86_64", "iterations_per_sec": 25000.0, **ok},
            # exe2's case: an x86_64 run under CoreMark's 10-second minimum fails validation and must not count.
            {"class": "all", "bench": "coremark", "abi": "x86_64", "iterations_per_sec": 99999.0, **ok, "valid": False},
            {"class": "all", "bench": "coremark", "abi": "x86_64", "iterations_per_sec": 99999.0, **ok, "mask_ok": False},
        ]
        for abi, text in (("arm64-v8a", SIMD_ARM), ("x86_64", SIMD_X86)):
            p = C.parse_simd(text)
            runs.append({"class": "all", "bench": "simd", "abi": abi, "kernels": p["kernels"], **ok})
        s = C.summarize_exe(runs)
        self.assertAlmostEqual(s["by_class"]["all/coremark"]["translated_over_native"], 0.4)
        self.assertEqual(s["by_class"]["all/coremark"]["excluded"], {"arm64-v8a": 0, "x86_64": 2})
        self.assertAlmostEqual(s["by_class"]["all/simd"]["kernels"]["triad_f32"]["translated_over_native"], 0.2)
        self.assertTrue(s["simd_same"])
        runs[-1]["kernels"]["aes128"] = dict(runs[-1]["kernels"]["aes128"], checksum="0x1")
        self.assertFalse(C.summarize_exe(runs)["simd_same"])
        only_invalid = [dict(r, valid=False) for r in runs[:2]]
        self.assertIsNone(C.summarize_exe(only_invalid)["by_class"]["all/coremark"]["translated_over_native"])


def disasm(fmt, kernels):
    out = [f"simd-bench:\tfile format {fmt}", "", "Disassembly of section .text:", ""]
    addr = 0x1000
    for name, insns in kernels.items():
        out.append(f"{addr:016x} <{name}>:")
        for i in insns:
            out.append(f"    {addr:x}:      \t{i.replace(' ', chr(9), 1)}")
            addr += 4
        out.append("")
    return "\n".join(out)


X86_PACKED = {
    "k_triad_f32": ["movups (%rsi), %xmm0", "mulps %xmm1, %xmm0", "addps %xmm2, %xmm0"],
    "k_dot_f32": ["mulps %xmm1, %xmm0", "addps %xmm0, %xmm3"],
    "k_dot_i8": ["pmovsxbw (%rdi), %xmm0", "pmullw %xmm1, %xmm0", "paddd %xmm0, %xmm2"],
    "k_blur_u8": ["paddw %xmm1, %xmm0", "psrlw $2, %xmm0", "packuswb %xmm1, %xmm0"],
    "k_minmax_f32": ["minps %xmm1, %xmm0", "maxps %xmm1, %xmm2"],
    "k_swizzle_u8": ["pshufb %xmm1, %xmm0"],
    "k_triad_scalar": ["movss (%rsi), %xmm0", "mulss %xmm1, %xmm0", "addss %xmm2, %xmm0"],
    "k_crc32c": ["crc32q (%rdi), %rax"],
    "k_aes128": ["aesenc %xmm1, %xmm0"],
}


class IsaTest(unittest.TestCase):
    def test_packed_x86_kernels_pass(self):
        report, failures = ISA.check(disasm("elf64-x86-64", X86_PACKED))
        self.assertEqual(failures, [])
        self.assertEqual(report["kernels"]["k_triad_scalar"]["packed_fp"], 0)

    def test_scalar_sse_in_every_kernel_fails_although_it_uses_xmm(self):
        # The Checker's fixture: only scalar mulss/addss on xmm registers in every baseline kernel.
        scalar = {k: (["movss (%rsi), %xmm0", "mulss %xmm1, %xmm0", "addss %xmm2, %xmm0"] if k in ISA.REQUIRED else v)
                  for k, v in X86_PACKED.items()}
        _, failures = ISA.check(disasm("elf64-x86-64", scalar))
        for k in ISA.REQUIRED:
            self.assertTrue(any(f.startswith(f"x86_64: {k} lacks packed") for f in failures), k)

    def test_arm64_lane_arrangements_and_a_vectorized_control(self):
        arm = {
            "k_triad_f32": ["ldr q0, [x1, x8]", "fmul v1.4s, v1.4s, v0.4s", "fadd v1.4s, v2.4s, v1.4s"],
            "k_dot_f32": ["fmul v1.4s, v1.4s, v0.4s", "fadd v3.4s, v3.4s, v1.4s"],
            "k_dot_i8": ["smull v2.8h, v0.8b, v1.8b", "saddw v4.4s, v4.4s, v2.4h"],
            "k_blur_u8": ["ushll v1.8h, v0.8b, #0", "uaddw v1.8h, v1.8h, v2.8b", "rshrn v0.8b, v1.8h, #2"],
            "k_minmax_f32": ["fminnm v0.4s, v0.4s, v1.4s", "fmaxnm v2.4s, v2.4s, v1.4s"],
            "k_swizzle_u8": ["tbl v1.16b, { v1.16b }, v0.16b"],
            "k_triad_scalar": ["fmul s1, s0, s2", "fadd s1, s1, s3"],
            "k_crc32c": ["crc32cx w0, w0, x8"],
            "k_aes128": ["aese v0.16b, v1.16b"],
        }
        report, failures = ISA.check(disasm("elf64-littleaarch64", arm))
        self.assertEqual(failures, [])
        self.assertEqual(ISA.functions(disasm("elf64-littleaarch64", arm))["k_triad_f32"][1], "fmul v1.4s, v1.4s, v0.4s")
        arm["k_triad_scalar"] = ["fmul v1.4s, v0.4s, v2.4s"]
        arm["k_triad_f32"] = ["fmul s1, s1, s0", "fadd s1, s1, s2"]  # scalarized: s-registers only
        _, failures = ISA.check(disasm("elf64-littleaarch64", arm))
        self.assertTrue(any("k_triad_scalar has 1 packed" in f for f in failures))
        self.assertTrue(any("aarch64: k_triad_f32 lacks packed" in f for f in failures))
        del arm["k_dot_f32"]
        _, failures = ISA.check(disasm("elf64-littleaarch64", arm))
        self.assertTrue(any("k_dot_f32 not found" in f for f in failures))


# ---- a simulated device: the package manager, the gate's activity token and benchmark processes ----

PKG = "org.example.test"


class Clock:
    """Replaces arm-corpus's time module: sleep advances the clock, so timeouts run instantly."""
    def __init__(self):
        self.t = 1000.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


class Sim:
    def __init__(self):
        self.pkgs = {}            # installed package -> sha256 of its base APK
        self.flags = {}           # permission -> flags text
        self.pm_answers = []      # queued pm-list outcomes: "fail" (no answer) or None (answer normally)
        self.install_ok = True
        self.uninstall_ok = True
        self.offline = False      # every command fails, as on a lost wireless link
        self.token = "100"
        self.token_after = None   # (n, value): the activity token changes at the n-th idle check
        self.idle_checks = 0
        self.alive = False        # benchmark processes exist
        self.dies_on = {"TERM"}   # signals that end them
        self.start_lost = False   # the start's answer is lost although the benchmark started
        self.done = False         # the benchmark wrote its result
        self.find_fail = False
        self.signal_at = None     # raise KeyboardInterrupt at this idle check
        self.events = []
        self.started = []         # every shell command, in order
        self.engine_arch = "arm64"  # what the benchmark reports it was built for
        self.app_alive = False      # the benchmark app's process
        self.app_survives = False   # force-stop doesn't end it
        self.stop_fails_for = 0     # force-stops that get no answer
        self.ps_command_fails = False  # ps itself fails on the device (adb answers)
        self.ps_fails_for = 0       # process listings that get no answer
        self.clear_fails = False
        self.launch_ok = True
        self.result_appears = True
        self.stale_log = []         # what logcat still holds after a clear (nothing, unless the clear failed)
        self.log = []
        self.launch_pid = 4320
        self.extra_process = False  # the listing shows a second process of the package
        self.bench_polls = 0

    def __call__(self, kind, x):
        if kind == "sh":
            self.started.append(x)
        if self.offline:
            raise C.Fail("adb: no answer (simulated)")
        if kind == "run":
            return self.run(x)
        return self.sh(x)

    def run(self, args):
        self.events.append(("run", args[0]))
        if args[0] == "install":
            if self.install_ok:
                self.pkgs[PKG] = C.sha256_file(args[-1])
                return "Success\n", 0
            return "Failure [INSTALL_FAILED_INTERNAL_ERROR]\n", 1
        if args[0] == "uninstall":
            if self.uninstall_ok:
                self.pkgs.pop(args[1], None)
                return "Success\n", 0
            return "Failure [DELETE_FAILED_INTERNAL_ERROR]\n", 1
        return "", 0

    def sh(self, cmd):
        if cmd.startswith("pm list packages"):
            self.events.append(("pm-list",))
            if self.pm_answers and self.pm_answers.pop(0) == "fail":
                raise C.Fail("adb: no answer (simulated)")
            return ("".join(f"package:{p}\n" for p in self.pkgs) + "@rc 0\n@end\n"), 0
        if "sha256sum" in cmd:
            return (f"{self.pkgs[PKG]}  /data/app/x/base.apk\n@end\n" if PKG in self.pkgs else "@end\n"), 0
        if cmd.startswith("dumpsys package"):
            perms = {"android.permission.POST_NOTIFICATIONS": self.flags.get("POST", "[ USER_SENSITIVE_WHEN_DENIED]")}
            body = "".join(f"        {k}: granted=false, flags={v}\n" for k, v in perms.items())
            return (f"Packages:\n  Package [{PKG}] (1):\n    versionCode=1 minSdk=26 targetSdk=35\n"
                    f"    primaryCpuAbi=arm64-v8a\n    versionName=1.0\n      runtime permissions:\n{body}"), 0
        if cmd.startswith("pm set-permission-flags"):
            self.events.append(("set-flags",))
            self.flags["POST"] = "[ USER_SET|USER_FIXED|USER_SENSITIVE_WHEN_DENIED]"
            return "", 0
        if "gpu-diag-device.sh idle" in cmd:
            self.idle_checks += 1
            if self.signal_at == self.idle_checks:
                raise KeyboardInterrupt("signal 15")
            if self.token_after and self.idle_checks >= self.token_after[0]:
                self.token = self.token_after[1]
            return (f"idle_ms=99999999 wakefulness=Awake keyguard_showing=false audio_started=0 "
                    f"user_activity_uptime_ms={self.token}\n"), 0
        if "device.sh pids" in cmd:
            return "", 0
        if "nohup taskset" in cmd:
            self.events.append(("start",))
            self.alive = True
            if self.start_lost:
                raise C.Fail("adb: no answer (simulated)")
            return "@pid 4242\n", 0
        if "/proc/[0-9]*" in cmd:
            if self.find_fail:
                raise C.Fail("adb: no answer (simulated)")
            return ("@pid 4242\n@pid 4243\n" if self.alive else "") + "@scanned 57\n@end\n", 0
        m = re.search(r"kill -(\w+)", cmd)
        if m:
            self.events.append(("kill", m.group(1)))
            if m.group(1) in self.dies_on:
                self.alive = False
            return "", 0
        if cmd.startswith("cat "):
            if self.done:
                self.alive = False
                return "@mask pid 4242's current affinity mask: 80\nresult\n@rc 0\n@end\n", 0
            return "@mask pid 4242's current affinity mask: 80\n@end\n", 0
        if cmd.startswith("rm -rf"):
            self.events.append(("rm",))
            return "", 0
        if cmd.startswith("cmd package resolve-activity"):
            return f"{PKG}/com.godot.game.GodotAppLauncher\n", 0
        if cmd == "logcat -c":
            if self.clear_fails:
                return "logcat: failed to clear\n", 1
            self.log = list(self.stale_log)
            return "", 0
        if cmd.startswith("am start -W -S"):
            self.events.append(("am-start",))
            self.bench_polls = 0
            self.launch_pid += 1
            if not self.launch_ok:
                return "Error: Activity not started, unable to resolve Intent\n", 0
            self.app_alive = True
            return "Status: ok\nLaunchState: COLD\nActivity: x\nTotalTime: 500\nWaitTime: 501\nComplete\n", 0
        if cmd.startswith("logcat -d -v threadtime -s godot"):
            self.bench_polls += 1
            pid = self.launch_pid
            lines = list(self.log)
            if self.app_alive:
                lines.append(f"11-04 13:00:00.000  {pid}  4340 I godot   : OPENBOOK_BENCH start pid={pid} "
                             f"arch={self.engine_arch} renderer=mobile driver=vulkan adapter=AMD")
                if self.bench_polls >= 3 and self.result_appears:
                    lines.append(f"11-04 13:01:10.000  {pid}  4340 I godot   : OPENBOOK_BENCH result pid={pid} "
                                 f"frames=3600 window_s=59.998 fps_avg=60.00 p50_ms=16.6 p95_ms=17.1 p99_ms=21.3 "
                                 f"max_ms=40.2 crossing_frame_ms=16.7 engine_process_ms_avg=3.1 "
                                 f"arch={self.engine_arch} size=(2880.0, 1800.0)")
            return "\n".join(lines) + "\n", 0
        if cmd.startswith("am force-stop"):
            self.events.append(("force-stop",))
            if self.stop_fails_for > 0:
                self.stop_fails_for -= 1
                raise C.Fail("adb: no answer (simulated)")
            if not self.app_survives:
                self.app_alive = False
            return "", 0
        if cmd.startswith("l=$(ps -A -o PID,NAME)"):
            if self.ps_fails_for > 0:
                self.ps_fails_for -= 1
                raise C.Fail("adb: no answer (simulated)")
            if self.ps_command_fails:
                return "@ps-failed 1\n", 1
            if self.extra_process and self.app_alive:
                return f"@header\n@pid {self.launch_pid}\n@pid 9999\n@end\n", 0
            return "@header\n" + (f"@pid {self.launch_pid}\n" if self.app_alive else "") + "@end\n", 0
        return "", 0
        return "", 0


class FakeDevice:
    def __init__(self, sim):
        self.sim, self.serial, self.busy, self.notes, self.rooted = sim, "fake", None, {}, False

    def sh(self, cmd, timeout=120, check=True):
        out, rc = self.sim("sh", cmd)
        if check and rc:
            raise C.Fail(f"exit {rc}")
        return out, rc

    def run(self, *args, timeout=120, check=True):
        out, rc = self.sim("run", args)
        return types.SimpleNamespace(stdout=out, stderr="", returncode=rc)

    def helper(self, args, timeout=120, check=True):
        return self.sh(f"sh {C.AP.D}/device.sh {args}", check=check)

    def unroot(self):
        pass


class DeviceTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saved = (C.STORE, C.time, C.AP.D)
        C.STORE, C.time, C.AP.D = self.tmp.name, Clock(), C.D
        self.addCleanup(self.restore)
        apk = os.path.join(self.tmp.name, "t.apk")
        with zipfile.ZipFile(apk, "w") as z:
            z.writestr("lib/arm64-v8a/libt.so", b"a")
            z.writestr("lib/x86_64/libt.so", b"x")
        self.apk_sha = C.sha256_file(apk)
        self.rows = [{"id": "t", "package": PKG, "abi": "fat", "version_name": "1.0", "version_code": "1",
                      "file": "t.apk", "sha256": "-", "signer_sha256": "-", "source": "build:x", "task": "bench"}]
        self.sim = Sim()
        self.dev = FakeDevice(self.sim)
        self.journal = C.Journal(os.path.join(self.tmp.name, "journal.json"), "dev-a")
        self.out = os.path.join(self.tmp.name, "out")
        os.makedirs(self.out)

    def restore(self):
        C.STORE, C.time, C.AP.D = self.saved

    def args(self, **kw):
        return types.SimpleNamespace(id="t", abi="arm64-v8a", idle_min=0, ids=[], **kw)

    def writes(self):
        return [e for e in self.sim.events if e[0] in ("run", "set-flags")]


class InstallTest(DeviceTestBase):
    def test_a_failed_package_query_changes_nothing_even_if_the_next_one_would_show_an_owner_app(self):
        self.sim.pkgs[PKG] = "f" * 64            # an owner's copy is installed
        self.sim.pm_answers = ["fail", None]      # the Checker's case: no answer, then a good one
        with self.assertRaises(C.Fail):
            C.cmd_install(self.dev, self.args(), self.out, self.rows, self.journal)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.journal.mine(), {})

    def test_an_owner_app_is_refused(self):
        self.sim.pkgs[PKG] = "f" * 64
        with self.assertRaises(C.Invalid):
            C.cmd_install(self.dev, self.args(), self.out, self.rows, self.journal)
        self.assertEqual(self.writes(), [])

    def test_a_stale_journal_entry_doesnt_let_it_replace_a_reinstalled_owner_app(self):
        self.journal.put(PKG, {"id": "t", "apk_sha256s": [self.apk_sha], "state": "installed"})
        self.sim.pkgs[PKG] = "e" * 64             # the owner reinstalled their own build since
        with self.assertRaises(C.Invalid):
            C.cmd_install(self.dev, self.args(), self.out, self.rows, self.journal)
        self.assertEqual(self.writes(), [])

    def test_install_journals_first_and_fixes_permissions_with_a_read_back(self):
        res = C.cmd_install(self.dev, self.args(), self.out, self.rows, self.journal)
        self.assertEqual(res["primaryCpuAbi"], "arm64-v8a")
        self.assertEqual(res["permissions_denied_fixed"], ["android.permission.POST_NOTIFICATIONS"])
        self.assertIn("USER_FIXED", res["permission_flags_after"]["android.permission.POST_NOTIFICATIONS"])
        entry = self.journal.mine()[PKG]
        self.assertEqual((entry["state"], entry["apk_sha256s"]), ("installed", [self.apk_sha]))

    def test_a_failed_install_with_an_unanswered_check_keeps_the_journal(self):
        self.sim.install_ok = False
        self.sim.pm_answers = [None, "fail"]      # the check before succeeds, the one after doesn't
        with self.assertRaises(C.Fail):
            C.cmd_install(self.dev, self.args(), self.out, self.rows, self.journal)
        self.assertIn(PKG, self.journal.mine())


class RemoveTest(DeviceTestBase):
    def setUp(self):
        super().setUp()
        self.journal.put(PKG, {"id": "t", "apk_sha256s": [self.apk_sha], "state": "installed"})
        self.sim.pkgs[PKG] = self.apk_sha

    def test_a_failed_uninstall_with_an_offline_check_keeps_the_journal(self):
        self.sim.uninstall_ok = False
        self.sim.pm_answers = [None, "fail"]      # present before; no answer after the uninstall
        res = C.cmd_remove(self.dev, self.args(), self.rows, self.journal)
        self.assertEqual(res["removed"], [])
        self.assertTrue(res["unresolved"])
        self.assertIn(PKG, self.journal.mine())

    def test_only_a_confirmed_removal_drops_the_entry(self):
        res = C.cmd_remove(self.dev, self.args(), self.rows, self.journal)
        self.assertEqual(res["removed"], [PKG])
        self.assertEqual(self.journal.mine(), {})

    def test_a_reinstalled_owner_app_is_left_alone_and_the_claim_dropped(self):
        self.sim.pkgs[PKG] = "e" * 64
        res = C.cmd_remove(self.dev, self.args(), self.rows, self.journal)
        self.assertEqual([e for e in self.sim.events if e[0] == "run"], [])
        self.assertTrue(res["left_alone"])
        self.assertEqual(self.journal.mine(), {})
        self.assertIn(PKG, self.sim.pkgs)

    def test_an_unanswered_query_removes_nothing(self):
        self.sim.pm_answers = ["fail"]
        res = C.cmd_remove(self.dev, self.args(), self.rows, self.journal)
        self.assertTrue(res["unresolved"])
        self.assertEqual([e for e in self.sim.events if e[0] == "run"], [])
        self.assertIn(PKG, self.journal.mine())


class WorkloadTest(DeviceTestBase):
    def test_the_start_puts_only_nohup_in_the_background(self):
        # A backgrounded list ("cd ... && nohup ... &") keeps adb's output open until the benchmark ends.
        g = self.gate()
        self.sim.done = True
        self.run_it(g)
        start = [c for c in self.started if "nohup" in c][0]
        self.assertRegex(start, r"\|\| exit 1; nohup taskset ")
        self.assertNotIn("&& nohup", start)
        self.assertRegex(start, r"< /dev/null & echo")

    def test_a_signal_during_the_start_still_stops_it(self):
        g = self.gate()
        orig = self.sim.sh

        def sh(cmd):
            if "nohup taskset" in cmd:
                self.sim.alive = True
                raise KeyboardInterrupt("signal 15")
            return orig(cmd)
        self.sim.sh = sh
        with self.assertRaises(KeyboardInterrupt):
            self.run_it(g)
        self.assertFalse(self.sim.alive)
        self.assertIsNone(self.dev.busy)

    def gate(self):
        return C.AP.Gate(self.dev, 0)

    @property
    def started(self):
        return self.sim.started

    def run_it(self, gate):
        return C.run_workload(self.dev, gate, f"{C.BIN}/simd-arm64 -r 5", "80", f"{C.OUTD}/r1.txt", timeout=60)

    def order(self, *kinds):
        return [e for e in self.sim.events if e[0] in kinds]

    def test_normal_completion_then_clean_up(self):
        g = self.gate()
        self.sim.done = True
        self.assertIn("@rc 0", self.run_it(g))
        self.assertIsNone(self.dev.busy)
        self.assertEqual(C.cleanup_device(self.dev), "ok")

    def test_input_while_it_runs_stops_it_before_its_directory_goes(self):
        g = self.gate()
        self.sim.token_after = (3, "555")         # someone touches the laptop during the run
        with self.assertRaises(C.Invalid):
            self.run_it(g)
        self.assertEqual(self.order("kill"), [("kill", "TERM")])
        self.assertIsNone(self.dev.busy)
        self.assertEqual(C.cleanup_device(self.dev), "ok")
        kinds = [e[0] for e in self.sim.events]
        self.assertLess(kinds.index("kill"), kinds.index("rm"))

    def test_a_signal_stops_it(self):
        g = self.gate()
        self.sim.signal_at = 3
        with self.assertRaises(KeyboardInterrupt):
            self.run_it(g)
        self.assertEqual(self.order("kill"), [("kill", "TERM")])
        self.assertFalse(self.sim.alive)

    def test_a_lost_link_keeps_its_files_and_marks_the_device_busy(self):
        g = self.gate()
        orig = self.sim.sh

        def sh(cmd):
            if cmd.startswith("cat "):
                self.sim.offline = True       # the link drops while the benchmark runs
            return orig(cmd)
        self.sim.sh = sh
        with self.assertRaises(C.Fail):
            self.run_it(g)
        self.assertTrue(self.dev.busy)
        self.sim.offline = False
        self.assertTrue(C.cleanup_device(self.dev).startswith("skipped"))
        self.assertNotIn(("rm",), self.sim.events)
        self.assertTrue(self.sim.alive)       # nothing claimed it stopped

    def test_a_lost_start_answer_is_adopted_and_stopped_on_input(self):
        g = self.gate()
        self.sim.start_lost = True
        self.sim.token_after = (3, "555")
        with self.assertRaises(C.Invalid):
            self.run_it(g)
        self.assertFalse(self.sim.alive)
        self.assertIsNone(self.dev.busy)

    def test_a_lost_start_answer_that_cant_be_checked_stays_busy(self):
        g = self.gate()
        self.sim.start_lost = True
        self.sim.find_fail = True
        with self.assertRaises(C.Fail):
            self.run_it(g)
        self.assertTrue(self.dev.busy)
        self.assertTrue(C.cleanup_device(self.dev).startswith("skipped"))

    def test_a_process_that_survives_kill_stays_busy(self):
        g = self.gate()
        self.sim.dies_on = set()
        self.sim.token_after = (3, "555")
        with self.assertRaises(C.Invalid):
            self.run_it(g)
        self.assertEqual([k[1] for k in self.order("kill")], ["TERM", "KILL"])
        self.assertIn("survived KILL", self.dev.busy)
        self.assertTrue(C.cleanup_device(self.dev).startswith("skipped"))
        self.assertNotIn(("rm",), self.sim.events)

    def test_a_timeout_stops_it(self):
        g = self.gate()
        with self.assertRaises(C.Fail):
            self.run_it(g)
        self.assertEqual(self.order("kill"), [("kill", "TERM")])
        self.assertIsNone(self.dev.busy)


class ProcessListingTest(unittest.TestCase):
    """The generated listing commands, run in a real shell with a fake ps first on PATH."""

    def run_sh(self, cmd, ps_script):
        with tempfile.TemporaryDirectory() as d:
            ps = os.path.join(d, "ps")
            with open(ps, "w") as f:
                f.write("#!/bin/sh\n" + ps_script)
            os.chmod(ps, 0o755)
            env = dict(os.environ, PATH=d + os.pathsep + os.environ["PATH"])
            r = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True, env=env)
            return r.stdout, r.returncode

    def pids(self, ps_script):
        return C.parse_app_pids(*self.run_sh(C.app_pids_cmd(PKG), ps_script))

    def test_a_failing_ps_is_unknown_not_none(self):
        self.assertIsNone(self.pids("exit 1\n"))

    def test_an_empty_listing_without_a_header_is_unknown(self):
        self.assertIsNone(self.pids("exit 0\n"))

    def test_a_real_listing(self):
        listing = f"printf 'PID NAME\\n1 init\\n4321 {PKG}\\n4322 {PKG}:render\\n4323 {PKG}x\\n'\n"
        self.assertEqual(self.pids(listing), ["4321", "4322"])
        self.assertEqual(self.pids("printf 'PID NAME\\n1 init\\n'\n"), [])

    def test_a_proc_scan_that_saw_nothing_is_unknown(self):
        self.assertIsNone(C.parse_workloads("@scanned 0\n@end\n", 0))
        self.assertIsNone(C.parse_workloads("@end\n", 0))
        self.assertEqual(C.parse_workloads("@pid 7\n@scanned 40\n@end\n", 0), ["7"])
        out, rc = self.run_sh(C.find_workloads_cmd(), "exit 0\n")  # the host's own /proc
        self.assertEqual(C.parse_workloads(out, rc), [])


class LocalShellDevice(FakeDevice):
    """Listing commands run in a real shell with a failing ps; everything else answers like the simulated device."""

    def __init__(self, sim, ps_dir):
        super().__init__(sim)
        self.ps_dir = ps_dir

    def sh(self, cmd, timeout=120, check=True):
        if cmd.startswith("l=$(ps -A -o PID,NAME)"):
            env = dict(os.environ, PATH=self.ps_dir + os.pathsep + os.environ["PATH"])
            r = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True, env=env)
            return r.stdout, r.returncode
        return super().sh(cmd, timeout, check)


class BenchParseTest(unittest.TestCase):
    LOG = ("11-04 13:03:58.872  2307  2347 I godot   : OPENBOOK_BENCH start pid=2307 arch=arm64 renderer=mobile "
           "driver=vulkan adapter=AMD\n"
           "11-04 13:04:00.000  2307  2347 I godot   : OPENBOOK_BENCH level loaded pid=2307 points=9 path_m=289\n"
           "11-04 13:05:10.000  2307  2347 I godot   : OPENBOOK_BENCH result pid=2307 frames=29 window_s=59.91 "
           "fps_avg=0.48 p50_ms=1269.856 p95_ms=7742.363 p99_ms=23086.868 max_ms=23086.868 crossing_frame_ms=2001.0 "
           "engine_process_ms_avg=2381.590 arch=arm64 size=(1920.0, 1200.0)\n"
           "11-04 12:00:00.000  1111  1112 I godot   : OPENBOOK_BENCH result pid=1111 frames=1 arch=arm64\n"
           "11-04 12:00:01.000  2307  1112 I godot   : OPENBOOK_BENCH error pid=1111 forged\n")

    def test_only_the_launched_process_lines_count(self):
        got = C.parse_bench(self.LOG, 2307)
        self.assertEqual(got["start"]["arch"], "arm64")
        self.assertEqual(got["result"]["frames"], 29)
        self.assertAlmostEqual(got["result"]["p99_ms"], 23086.868)
        self.assertEqual(got["result"]["size"], "(1920.0, 1200.0)")
        self.assertEqual(got["level loaded"]["points"], 9)
        self.assertNotIn("error", got)            # its printed pid isn't the launched process
        self.assertEqual(C.parse_bench(self.LOG, 1111)["result"]["frames"], 1)
        self.assertEqual(C.parse_bench(self.LOG, 5555), {})

    def test_error_line(self):
        got = C.parse_bench("11-04 13:00:00.000  7  2 I godot : OPENBOOK_BENCH error pid=7 no path (0 points)", 7)
        self.assertIn("no path", got["error"]["text"])


class BenchTest(DeviceTestBase):
    def setUp(self):
        super().setUp()
        self.journal.put(PKG, {"id": "t", "apk_sha256s": [self.apk_sha], "state": "installed"})
        self.sim.pkgs[PKG] = self.apk_sha

    def args(self, **kw):
        return types.SimpleNamespace(id="t", idle_min=0, runs=1, timeout=60, poll=1.0, settle=0.0, **kw)

    def bench(self):
        return C.cmd_bench(self.dev, self.args(), self.out, self.rows, self.journal)

    def running_mark(self):
        return self.journal.mine()[PKG].get("running")

    def test_a_valid_run_is_this_launchs_result_and_the_app_is_confirmed_stopped(self):
        res = self.bench()
        run = res["runs"][0]
        self.assertTrue(res["valid"])
        self.assertTrue(run["arch_ok"])
        self.assertEqual(run["result"]["pid"], run["pid"])
        self.assertEqual(run["stopped"], "confirmed")
        self.assertFalse(self.sim.app_alive)
        self.assertIsNone(self.running_mark())

    def test_an_old_result_left_in_the_log_never_counts(self):
        # The Checker's case: the clear "succeeded" but an old run's result is still there.
        self.sim.stale_log = ["11-04 12:00:00.000  1111  1112 I godot   : OPENBOOK_BENCH result pid=1111 frames=9 "
                              "arch=arm64"]
        self.sim.result_appears = False           # this launch never finishes
        with self.assertRaises(C.Fail):
            self.bench()
        self.assertFalse(self.sim.app_alive)

    def test_a_failed_log_clear_starts_nothing(self):
        self.sim.clear_fails = True
        with self.assertRaises(C.Fail):
            self.bench()
        self.assertNotIn(("am-start",), self.sim.events)

    def test_a_launched_process_that_cant_be_singled_out_fails_the_run(self):
        self.sim.extra_process = True
        with self.assertRaises(C.Fail):
            self.bench()
        self.assertIsNone(self.running_mark())

    def test_a_failed_launch_fails_the_run_and_still_stops_the_app(self):
        self.sim.launch_ok = False
        with self.assertRaises(C.Fail):
            self.bench()
        self.assertIn(("force-stop",), self.sim.events)
        self.assertIsNone(self.running_mark())

    def test_a_native_engine_in_a_translated_install_is_invalid(self):
        self.sim.engine_arch = "x86_64"         # the simulator's dumpsys says primaryCpuAbi=arm64-v8a
        self.assertFalse(self.bench()["valid"])

    def test_input_then_a_stop_that_cant_be_confirmed_keeps_the_mark_and_the_next_command_stops_it(self):
        self.sim.token_after = (3, "555")
        self.sim.app_survives = True
        with self.assertRaises(C.Invalid):
            self.bench()
        self.assertTrue(self.dev.busy)
        self.assertTrue(self.running_mark())
        self.assertTrue(self.dev.notes.get("apps"))
        # The next command: the app now stops.
        self.sim.app_survives = False
        dev2 = FakeDevice(self.sim)
        done = C.recover_apps(dev2, self.journal)
        self.assertIsNone(dev2.busy)
        self.assertIsNone(self.running_mark())
        self.assertTrue(any("stopped and confirmed" in d for d in done))

    def test_a_transient_adb_failure_while_stopping_is_retried(self):
        self.sim.stop_fails_for = 1
        self.sim.ps_fails_for = 1
        res = self.bench()
        self.assertTrue(res["valid"])
        self.assertEqual(res["runs"][0]["stopped"], "confirmed")

    def test_a_stop_that_never_confirms_after_a_result_fails_the_run(self):
        self.sim.app_survives = True
        with self.assertRaises(C.Fail):
            self.bench()
        self.assertTrue(self.dev.busy)
        self.assertTrue(self.running_mark())

    def test_a_lost_link_during_a_run_is_an_adb_failure_and_keeps_the_mark(self):
        orig = self.sim.sh

        def sh(cmd):
            if cmd.startswith("logcat -d -v threadtime"):
                self.sim.offline = True
            return orig(cmd)
        self.sim.sh = sh
        with self.assertRaises(C.Fail):
            self.bench()
        self.assertTrue(self.running_mark())
        self.assertTrue(self.dev.busy)

    def test_a_failing_ps_with_a_failing_stop_never_confirms(self):
        # The Checker's case: force-stop fails and ps itself fails while the app is still alive.
        d = tempfile.mkdtemp(dir=self.tmp.name)
        with open(os.path.join(d, "ps"), "w") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(os.path.join(d, "ps"), 0o755)
        self.dev = LocalShellDevice(self.sim, d)
        self.sim.app_survives = True
        with self.assertRaises(C.Fail):
            self.bench()
        self.assertTrue(self.sim.app_alive)
        self.assertTrue(self.running_mark())
        self.assertTrue(self.dev.busy)
        self.assertTrue(C.cleanup_device(self.dev).startswith("skipped"))

    def test_a_ps_that_fails_on_the_device_is_retried_and_stays_unconfirmed(self):
        self.sim.ps_command_fails = True
        with self.assertRaises(C.Fail):
            self.bench()
        self.assertTrue(self.running_mark())
        self.sim.ps_command_fails = False
        dev2 = FakeDevice(self.sim)
        C.recover_apps(dev2, self.journal)
        self.assertIsNone(self.running_mark())

    def test_a_signal_during_a_run_stops_the_app(self):
        self.sim.signal_at = 3
        with self.assertRaises(KeyboardInterrupt):
            self.bench()
        self.assertFalse(self.sim.app_alive)
        self.assertIsNone(self.running_mark())

    def test_a_package_that_isnt_this_tools_install_is_refused(self):
        self.sim.pkgs[PKG] = "e" * 64
        with self.assertRaises(C.Invalid):
            self.bench()
        self.assertNotIn(("am-start",), self.sim.events)

    def test_a_row_without_a_benchmark_is_refused(self):
        rows = [dict(self.rows[0], task="startup")]
        with self.assertRaises(C.Fail):
            C.cmd_bench(self.dev, self.args(), self.out, rows, self.journal)


if __name__ == "__main__":
    unittest.main(verbosity=1)
