#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/gpu-diag-summary.py on synthetic sampler output (no device).
python3 tests/gpu-diag-summary-test.py (tests/run.sh runs it)"""
import importlib.util
import os
import re
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "summary", os.path.join(os.path.dirname(__file__), "..", "scripts", "gpu-diag-summary.py"))
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

PKG = "org.example.game"
LAYER = f"1 SurfaceView[{PKG}/{PKG}.Main](BLAST)#9"
VS = 8_333_333  # 120 Hz


def ring(presents, pending=0):
    """FrameTracker rows (127, oldest first) ending with these presents; older rows unused (0)."""
    rows = [(0, 0, 0)] * (127 - len(presents) - pending)
    rows += [(a - 5_000_000, a, a - 2_000_000) for a in presents]
    rows += [(presents[-1] + VS * (i + 1), S.PENDING, S.PENDING) for i in range(pending)]
    return rows[-127:]


def sampler(samples, abort=None, end=True, period=0.5):
    """device.sh sample text from [(up_cs, presents)] for one layer."""
    out = [f"@begin phase=measure up_cs={samples[0][0] - 1} period={period} ua=1 vsync_ns={VS}",
           "@layers up_cs=0 1", f"@layer {LAYER}"]
    for up, presents in samples:
        out += [f"@t up_cs={up}", f"@L {LAYER}", str(VS)]
        out += ["\t".join(str(x) for x in r) for r in ring(presents)] + ["", f"@Le s={up} e={up + 2} rc=0"]
    if abort:
        out.append(f"@abort {abort}")
    if end:
        out.append(f"@end phase=measure up_cs={samples[-1][0] + 1}")
    return "\n".join(out) + "\n"


def steady(n, start=10**12, step=VS):
    return [start + i * step for i in range(n)]


def windows(frames, per=30):
    """Overlapping samples of the last 100 frames, every `per` frames, each taken just after its newest frame
    (up_cs on the same clock as the present times)."""
    return [(frames[k - 1] // 10**7, frames[max(0, k - 100):k]) for k in range(per, len(frames) + 1, per)]


def timestats(total, layer=LAYER):
    return (f"SurfaceFlinger TimeStats:\n\ndisplayRefreshRate = 120 fps\nrenderRate = 120 fps\nuid = 10200\n"
            f"layerName = {layer}\npackageName = {PKG}\ngameMode = Unsupported\ntotalFrames = {total}\n"
            f"droppedFrames = 0\nlateAcquireFrames = 0\nbadDesiredPresentFrames = 0\naverageFPS = 120.000\n")


class Pacing(unittest.TestCase):
    def test_steady_120hz(self):
        p = S.pacing(S.parse_samples(sampler(windows(steady(1201)))))
        info = p["layers"][p["primary"]]
        self.assertEqual(info["coverage_gaps"], 0)
        self.assertAlmostEqual(info["fps"], 120.0, delta=0.1)
        self.assertEqual(info["missed_vsync"], 0)
        self.assertEqual(info["refresh_hz"], 120.0)
        self.assertAlmostEqual(info["frame_ms"]["p99"], VS / 1e6, places=3)

    def test_long_frame_counts_as_missed(self):
        f = steady(600)
        f = f[:300] + [x + 2 * VS for x in f[300:]]  # one frame took 3 vsyncs
        info = S.pacing(S.parse_samples(sampler(windows(f))))["layers"][LAYER]
        self.assertEqual(info["missed_vsync"], 1)
        self.assertAlmostEqual(info["frame_ms"]["max"], 3 * VS / 1e6, places=3)
        self.assertEqual(info["over_cadence"], 1)

    def test_dumps_a_window_apart_are_a_gap(self):
        # Two dumps 1 s apart at 120 Hz: the 64-display-frame window (533 ms) can't reach back, whatever the rows.
        f = steady(400)
        text = sampler([(100, f[0:64]), (200, f[120:184])])
        self.assertEqual(S.pacing(S.parse_samples(text))["layers"][LAYER]["coverage_gaps"], 1)

    def test_gap_hidden_by_pending_frames_is_flagged(self):
        # The Checker's case: the second dump's newest frames are still pending (FrameTimeline leaves them out) and
        # it does not reach back to the first. The rows can't show the loss; the dumps' spacing does.
        f = steady(400)
        parsed = S.parse_samples(sampler([(100, f[0:64]), (200, f[136:200])]))
        parsed["samples"][1]["layers"][LAYER] = ring(f[136:197], pending=3)
        self.assertEqual(S.pacing(parsed)["layers"][LAYER]["coverage_gaps"], 1)

    def test_delayed_dump_is_a_gap(self):
        # The Checker's case: 64 rows per dump at 120 Hz; dump 2 starts 0.40 s after dump 1 but only snapshots and
        # returns at 0.60 s, 72 display frames later, so 8 frames are never seen. Start-to-start spacing (0.40 s)
        # looks fine; start-of-first to end-of-second (0.61 s) doesn't.
        starts = [10000, 10040] + list(range(10085, 11011, 25))
        ends = [10015, 10060] + [cs + 1 for cs in starts[2:]]
        newest = [0, 72] + [round((cs - 10000) * 1.2) for cs in starts[2:]]
        out = [f"@begin phase=measure up_cs=10000 period=0.25 ua=1 kerr=0 vsync_ns={VS}"]
        for cs, ce, nw in zip(starts, ends, newest):
            out += [f"@t up_cs={cs}", f"@L {LAYER}", str(VS)]
            for i in range(nw - 63, nw + 1):
                a = 100_000_000_000 + i * VS
                out.append(f"{a - 5_000_000}\t{a}\t{a - 2_000_000}")
            out += ["", f"@Le s={cs} e={ce} rc=0"]
        out.append(f"@end phase=measure up_cs={starts[-1] + 1} kerr=0")
        info = S.pacing(S.parse_samples("\n".join(out) + "\n"))["layers"][LAYER]
        self.assertEqual(info["coverage_gaps"], 1)

    def test_malformed_timing_is_rejected(self):
        # The producer bug the Checker found: up_cs under a newline IFS wrote both /proc/uptime fields. Read as
        # centiseconds, "48.05" made a 610 ms span look like 16 ms. Such records must be gaps and make the run
        # invalid, never be read by prefix.
        starts = [("100.00 20000 200.00", "100.15 20115 201.00"), ("100.40 20240 202.00", "100.60 20360 203.00")]
        out = [f"@begin phase=measure up_cs=10000 period=0.25 ua=1 vsync_ns={VS}"]
        for cs, (a, b) in zip((10000, 10040), starts):
            out += [f"@t up_cs={cs}", f"@L {LAYER}", str(VS), "", f"@Le s={a} e={b} rc=0"]
        parsed = S.parse_samples("\n".join(out) + "\n")
        self.assertEqual(len(parsed["malformed"]), 2)
        self.assertEqual(S.layer_frames(parsed)[1].get(LAYER), 2)
        for bad in ("@Le s=10040 e=10000 rc=0", "@Le s=10000 e=10015", "@Le s=10000 e=10015 rc=0 x", "@t up_cs=48.05 22405"):
            self.assertEqual(len(S.parse_samples(bad + "\n")["malformed"]), 1, bad)
        with tempfile.TemporaryDirectory() as d:
            Run().good(d)
            m = open(os.path.join(d, "measure.txt")).read().replace(" rc=0", " rc=0 junk", 1)
            Run().write(d, {"measure.txt": m})
            s = S.summarise(d)
            self.assertTrue(any("malformed sampler line" in w for w in s["invalid_because"]), s["invalid_because"])

    def test_untimed_or_failed_dumps_are_gaps(self):
        text = sampler(windows(steady(300)))
        untimed = "\n".join(ln for ln in text.splitlines() if not ln.startswith("@Le")) + "\n"
        self.assertGreater(S.pacing(S.parse_samples(untimed))["layers"][LAYER]["coverage_gaps"], 0)
        failed = text.replace(" rc=0", " rc=1", 1)
        self.assertEqual(S.pacing(S.parse_samples(failed))["layers"][LAYER]["coverage_gaps"], 1)

    def test_close_dumps_are_continuous_even_without_shared_frames(self):
        # 0.4 s apart (< 64 vsyncs): nothing can be lost, even though an idle layer shares no frame between them.
        f = steady(400)
        text = sampler([(100, f[0:20]), (140, f[60:80]), (180, f[110:130])])
        self.assertEqual(S.pacing(S.parse_samples(text))["layers"][LAYER]["coverage_gaps"], 0)

    def test_unparsable_dump_line_counts_as_a_gap(self):
        parsed = S.parse_samples(sampler(windows(steady(300))).replace("\t", "\tx", 1))
        self.assertGreaterEqual(S.pacing(parsed)["layers"][LAYER]["coverage_gaps"], 1)

    def test_frames_in_part_of_the_interval_only(self):
        f = steady(600)
        samples = windows(f)
        # the layer has frames only from the middle of the interval: earlier samples saw nothing of it
        parsed = S.parse_samples(sampler(samples))
        for smp in parsed["samples"][: len(samples) // 2]:
            smp["layers"][LAYER] = [(0, 0, 0)] * 127
        info = S.pacing(parsed)["layers"][LAYER]
        self.assertLess(info["covered"], 0.9)

    def test_pending_fences_are_not_frames(self):
        text = sampler([(100, steady(10))]).replace(f"@L {LAYER}\n{VS}\n", f"@L {LAYER}\n{VS}\n", 1)
        parsed = S.parse_samples(text)
        parsed["samples"][0]["layers"][LAYER] = ring(steady(10), pending=3)
        self.assertEqual(len(S.valid_frames(parsed["samples"][0]["layers"][LAYER])), 10)

    def test_no_samples_is_none_not_zero(self):
        p = S.pacing(S.parse_samples("@begin phase=measure up_cs=1 period=0.5 ua=1 vsync_ns=8333333\n"))
        self.assertIsNone(p["primary"])


class Logcat(unittest.TestCase):
    LOG = "\n".join([
        f"11-02 11:52:30.000  1000   600   620 I ActivityManager: Start proc 6846:{PKG}/u0a200 for top-activity",
        "11-02 11:52:31.207 10200  6846  6873 I Game: OpenGL renderer: ANGLE (NVIDIA, Vulkan 1.4.354 (NVIDIA NVIDIA "
        "GeForce RTX 5070 Ti Laptop GPU (NVK NV1B5) (0x00002F58)), NVK-26.0.128.5)",
        "11-02 11:52:31.300 10300  7000  7000 I Other: ANGLE (AMD, Vulkan 1.4 (AMD Radeon 890M (RADV STRIX1)))",
    ])

    def test_renderer_from_the_apps_own_pids(self):
        r = S.app_logcat(self.LOG, PKG)
        self.assertEqual(r["pids"], ["6846"])
        self.assertEqual(r["gpu_seen"], "nvidia")

    def test_unknown_renderer_is_unverified(self):
        self.assertIsNone(S.app_logcat(self.LOG.splitlines()[0], PKG)["gpu_seen"])

    def test_driver_selection_is_not_verification(self):
        log = self.LOG.splitlines()[0] + "\n" + (
            "11-02 11:52:31.000 10200  6846  6873 V GraphicsEnvironment: Updatable driver package search path: "
            "/vendor/app/OpenBookNvk/lib/x86_64:org.openbook.nvk\n"
            "11-02 11:52:31.100 10200  6846  6873 D libEGL  : loaded /vendor/lib64/egl/libEGL_angle.so (NVIDIA)\n")
        r = S.app_logcat(log, PKG)
        self.assertIsNone(r["gpu_seen"])
        self.assertTrue(any("org.openbook.nvk" in x for x in r["selection_facts"]))

    def test_child_gpu_process_counts(self):
        log = (f"11-02 11:52:30.000  1000   600   620 I ActivityManager: Start proc 7100:{PKG}:privileged_process0/u0a200"
               " for service\n11-02 11:52:31.000 10200  7100  7120 I chromium: GL_RENDERER: ANGLE (AMD, Vulkan 1.4 "
               "(AMD Radeon 890M (RADV STRIX1)), radv-26.2.5)\n")
        self.assertEqual(S.app_logcat(log, PKG)["gpu_seen"], "radeon")

    def test_other_renderer_is_not_ours(self):
        log = self.LOG.splitlines()[0] + ("\n11-02 11:52:31.000 10200  6846  6873 I Game: GL_RENDERER: ANGLE (Google, "
                                         "Vulkan 1.3 (SwiftShader Device (Subzero)), SwiftShader driver)\n")
        self.assertEqual(S.app_logcat(log, PKG)["gpu_seen"], "other")


class AppThroughput(unittest.TestCase):
    def vk(self, t, fps, frames, ms):
        return f"      {t:.3f}  6846  6873 I vulkanExample: fps {fps} frames {frames} ms {ms}"

    def test_vulkan_example_windows_inside_the_interval_only(self):
        log = "\n".join([
            self.vk(1000.5, 900, 900, 1000.0),    # warm-up: before the interval
            self.vk(1001.2, 800, 800, 1000.0),    # straddles the start (window 1000.2-1001.2): excluded
            self.vk(1002.2, 500, 500, 1000.0),
            self.vk(1003.2, 700, 701, 1001.5),
            self.vk(1004.0, 999, 999, 1000.0),    # straddles the end: excluded
            "      1002.500  7000  7001 I Other: fps 5 frames 5 ms 1000.0",
        ])
        r = S.app_throughput(log, 1000.9, 1003.9)
        self.assertEqual(r["windows"], 2)
        self.assertEqual(r["source"], "vulkanExample")
        self.assertAlmostEqual(r["fps"], round((500 + 701) / 2.0015, 1))
        self.assertEqual((r["min"], r["max"]), (500.0, 700.0))

    def test_glmark2_reports_are_kept_not_aggregated(self):
        # The Checker's boundary case: a scene requested for 10 s actually ran 1000-1012 after a stall and is logged
        # at 1012; scoring began at 1002. "logged - duration" would wrongly place it inside the interval, and its
        # requested length is the wrong weight. So glmark2 gives no app FPS; its reports stay as logged.
        log = ("      1012.000  6900  6901 I glmark2 : [build] duration=10 FPS: 100 FrameTime: 10.000 ms\n"
               "      1024.500  6900  6901 I glmark2 : [build] duration=10 FPS: 200 FrameTime: 5.000 ms\n")
        self.assertIsNone(S.app_throughput(log, 1002.0, 1030.0))
        self.assertEqual(S.glmark2_reports(log),
                         [{"logged": 1012.0, "scene": "build", "fps": 100, "frame_ms": 10.0},
                          {"logged": 1024.5, "scene": "build", "fps": 200, "frame_ms": 5.0}])

    def test_nothing_logged_is_none(self):
        self.assertIsNone(S.app_throughput("", 1.0, 2.0))
        self.assertIsNone(S.app_throughput(self.vk(5.0, 1, 1, 1000.0), None, 9.0))


class Routing(unittest.TestCase):
    def rt(self, **st):
        base = {"updatable_driver_all_apps": "null", "updatable_driver_production_opt_in_apps": "null",
                "updatable_driver_prerelease_opt_in_apps": "null", "updatable_driver_production_opt_out_apps": "null",
                "updatable_driver_production_denylist": "null", "updatable_driver_production_allowlist": "null"}
        base.update(st)
        offered = base.pop("offered", "org.openbook.nvk")
        text = "\n".join(f"setting {k}={v}" for k, v in base.items())
        text += f"\nprop [ro.gfx.driver.0]: [{offered}]\n"
        return S.routing(text, PKG)["expected"]

    def test_order(self):
        self.assertEqual(self.rt(offered=""), "radeon")
        self.assertEqual(self.rt(updatable_driver_production_allowlist=PKG), "nvidia")
        self.assertEqual(self.rt(updatable_driver_production_allowlist=PKG,
                                 updatable_driver_production_opt_out_apps=PKG), "radeon")
        self.assertEqual(self.rt(updatable_driver_production_opt_in_apps=f"a.b,{PKG}"), "nvidia")
        self.assertEqual(self.rt(updatable_driver_production_opt_in_apps=PKG, updatable_driver_all_apps="3"), "radeon")
        self.assertEqual(self.rt(), "radeon")
        self.assertEqual(self.rt(updatable_driver_production_allowlist=PKG,
                                 updatable_driver_production_denylist=PKG), "radeon")


class Run(unittest.TestCase):
    def write(self, d, files):
        for k, v in files.items():
            with open(os.path.join(d, k), "w") as f:
                f.write(v)

    def good(self, d, fps_step=VS, ts=None, extra_meta=""):
        frames = steady(601, step=fps_step)
        n = 600 - 40 + 1  # frames scored between the first and last sample
        span = (frames[-1] - frames[0]) / 1e9 + 1.0
        self.write(d, {
            "meta.txt": f"pkg={PKG} gpu=nvidia\nlabel=STK fixed replay\nts_clear_up_s=100.00\n"
                        f"ts_dump_up_s={100 + span:.2f}\n{extra_meta}exit=0\n",
            "measure.txt": sampler(windows(frames, per=40)),
            "timestats.txt": timestats(ts if ts is not None else round(n * 1.05)),
            "logcat.txt": Logcat.LOG,
        })
        return S.summarise(d)

    def test_timestats_must_agree(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(self.good(d)["valid"])
        with tempfile.TemporaryDirectory() as d:
            s = self.good(d, ts=300)
            self.assertTrue(any("fewer than" in w for w in s["invalid_because"]), s["invalid_because"])
        with tempfile.TemporaryDirectory() as d:
            s = self.good(d, ts=2000)
            self.assertTrue(any("frames may be missing" in w for w in s["invalid_because"]), s["invalid_because"])
        with tempfile.TemporaryDirectory() as d:
            self.good(d)
            self.write(d, {"timestats.txt": timestats(560, layer="another layer#1")})
            s = S.summarise(d)
            self.assertTrue(any("no TimeStats record" in w for w in s["invalid_because"]), s["invalid_because"])

    def test_app_fps_reaches_the_summary_and_table(self):
        with tempfile.TemporaryDirectory() as d:
            self.good(d)
            m = open(os.path.join(d, "measure.txt")).read()
            first, last = re.findall(r"@t up_cs=(\d+)", m)[0], re.findall(r"@t up_cs=(\d+)", m)[-1]
            b, e = int(first) / 100.0, int(last) / 100.0
            m = m.replace("@begin phase=measure", f"@begin phase=measure epoch={b:.3f}", 1)
            m = m.replace("@end phase=measure", f"@end phase=measure epoch={e:.3f}", 1)
            log = "\n".join(AppThroughput().vk(b + k, 400, 400, 1000.0) for k in range(1, 4))
            self.write(d, {"measure.txt": m, "app-logcat.txt": log + "\n"})
            s = S.summarise(d)
        self.assertEqual(s["app_fps"]["fps"], 400.0)
        self.assertIn("app FPS", S.table([s]))

    def test_app_failures_invalidate(self):
        cases = {
            "app error": "11-02 11:52:32.000 10200  6846  6873 E Game: vkQueueSubmit returned VK_ERROR_DEVICE_LOST (-4)",
            "crash/ANR": f"11-02 11:52:32.000  1000   600   620 E ActivityManager: ANR in {PKG}",
            "rendering error": "11-02 11:52:32.000 10200  6846  6873 W Game: kartDirt shader is missing, fallback to solid",
        }
        for what, line in cases.items():
            with tempfile.TemporaryDirectory() as d:
                self.good(d)
                with open(os.path.join(d, "logcat.txt"), "a") as f:
                    f.write("\n" + line + "\n")
                s = S.summarise(d)
                self.assertFalse(s["valid"], what)
                self.assertTrue(any(w.startswith(what) for w in s["invalid_because"]), (what, s["invalid_because"]))
        with tempfile.TemporaryDirectory() as d:          # another app's ANR is not this run's failure
            self.good(d)
            with open(os.path.join(d, "logcat.txt"), "a") as f:
                f.write("\n11-02 11:52:32.000  1000   600   620 E ActivityManager: ANR in com.other.app\n")
            self.assertTrue(S.summarise(d)["valid"])
        with tempfile.TemporaryDirectory() as d:          # the sampler's own count of the app's errors grew
            self.good(d)
            m = open(os.path.join(d, "measure.txt")).read()
            m = m.replace("ua=1 vsync_ns", "ua=1 apperr=0 vsync_ns", 1).replace("@end phase=measure", "@end phase=measure apperr=2")
            self.write(d, {"measure.txt": m})
            self.assertTrue(any("2 app error line(s) during measurement" in w for w in S.summarise(d)["invalid_because"]))

    def test_gpu_errors_invalidate(self):
        with tempfile.TemporaryDirectory() as d:
            self.good(d)
            m = open(os.path.join(d, "measure.txt")).read()
            m = m.replace("ua=1 vsync_ns", "ua=1 kerr=4 vsync_ns", 1).replace("@end phase=measure", "@end phase=measure kerr=5")
            self.write(d, {"measure.txt": m})
            s = S.summarise(d)
            self.assertTrue(any("1 kernel GPU error line(s) during measurement" in w for w in s["invalid_because"]))
        with tempfile.TemporaryDirectory() as d:
            self.good(d)
            rep = "openbook-pc-setup: dgpu-report: health state=d0-driver driver=nvidia refs=2 nvrm=9 xid={} klog_s=0-9\n"
            self.write(d, {"dgpu-before.txt": rep.format(3), "dgpu-after.txt": rep.format(5)})
            s = S.summarise(d)
            self.assertTrue(any("2 new Xid(s)" in w for w in s["invalid_because"]), s["invalid_because"])

    def test_valid_run_and_table(self):
        runs = []
        with tempfile.TemporaryDirectory() as t:
            for i, fps_step in enumerate((VS, VS, 2 * VS)):
                d = os.path.join(t, f"r{i}")
                os.mkdir(d)
                frames = steady(601, step=fps_step)
                span = (frames[-1] - frames[0]) / 1e9 + 1.0
                self.write(d, {
                    "meta.txt": f"run_id=r{i} pkg={PKG} gpu=nvidia\nlabel=STK fixed replay\nexit=0\n"
                                f"ts_clear_up_s=100.00\nts_dump_up_s={100 + span:.2f}\n",
                    "measure.txt": sampler(windows(frames, per=40 if fps_step == VS else 20)),
                    "timestats.txt": timestats(610),
                    "logcat.txt": Logcat.LOG,
                    "am-start.txt": "Status: ok\nLaunchState: COLD\nTotalTime: 812\nWaitTime: 815\n",
                    "dgpu-before.txt": "openbook-pc-setup: dgpu-report: health state=d3cold driver=nvidia refs=0 "
                                       "runtime_d3=Enabled vram=Off nvrm=3 xid=0 klog_s=0-900\n",
                })
                runs.append(S.summarise(d))
        self.assertTrue(all(r["valid"] for r in runs), [r["invalid_because"] for r in runs])
        self.assertEqual(runs[0]["dgpu_before"]["state"], "d3cold")
        self.assertEqual(runs[0]["start"]["total_ms"], 812)
        tab = S.table(runs)
        self.assertIn("| STK fixed replay | nvidia | 3 |", tab)
        self.assertIn("120.0, 60.0–120.0; 120.0 / 120.0 / 60.0", tab)

    def test_aborted_run_is_not_scored(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, {"meta.txt": f"pkg={PKG} gpu=radeon\nexit=3\n",
                           "measure.txt": sampler(windows(steady(200)), abort="user-activity up_cs=9", end=False),
                           "logcat.txt": Logcat.LOG})
            s = S.summarise(d)
        self.assertFalse(s["valid"])
        self.assertTrue(any("aborted" in w for w in s["invalid_because"]))
        self.assertTrue(any("renderer nvidia, expected radeon" in w for w in s["invalid_because"]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
