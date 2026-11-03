#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Tests for scripts/g14-lock.sh on this host (no device): contention, nesting, and a multi-step session that is
signalled while a foreground and a background worker run. The lock must not be free until every process of the
session is gone and its clean-up is done.   python3 tests/g14-lock-test.py (tests/run.sh runs it)"""
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

LOCK = Path(__file__).resolve().parents[1] / "scripts" / "g14-lock.sh"


class Lock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if k != "OPENBOOK_G14_LOCK_OWNER"}
        self.env.update(OPENBOOK_G14_LOCK=str(self.t / "g14.lock"), OPENBOOK_G14_LOCK_GRACE="2")
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
                p.wait()
        subprocess.run(["pkill", "-f", str(self.t)], check=False)
        self.tmp.cleanup()

    def run_lock(self, owner, *cmd, **kw):
        return subprocess.run([str(LOCK), "run", owner, "--", *cmd], env=self.env, capture_output=True, text=True,
                              timeout=20, **kw)

    def start(self, owner, script):
        s = self.t / f"{owner}.sh"
        s.write_text(script)
        p = subprocess.Popen([str(LOCK), "run", owner, "--", "bash", str(s)], env=self.env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(p)
        return p

    def wait_for(self, path, timeout=5):
        end = time.monotonic() + timeout
        while not path.exists():
            self.assertLess(time.monotonic(), end, f"{path.name} never appeared")
            time.sleep(0.02)

    def alive(self, pidfile):
        try:
            os.kill(int(pidfile.read_text()), 0)
            return True
        except ProcessLookupError:
            return False

    def free(self):
        return self.run_lock("probe", "true").returncode == 0

    def test_contention_nesting_and_exit_status(self):
        p = self.start("A", f"touch {self.t}/up; sleep 30\n")
        self.wait_for(self.t / "up")
        busy = self.run_lock("B", "true")
        self.assertEqual(busy.returncode, 75)
        self.assertIn("owner=A", busy.stderr)
        st = subprocess.run([str(LOCK), "status"], env=self.env, capture_output=True, text=True)
        self.assertEqual(st.returncode, 75)
        p.send_signal(signal.SIGTERM)
        p.wait(10)
        self.assertEqual(self.run_lock("N", str(LOCK), "run", "N", "--", "true").returncode, 0)
        self.assertEqual(self.run_lock("N", str(LOCK), "run", "other", "--", "true").returncode, 2)
        self.assertEqual(self.run_lock("E", "sh", "-c", "exit 7").returncode, 7)

    def test_signalled_multi_step_session(self):
        # A shell session: a background worker, then a foreground worker; each would mark "finished" if left alone.
        # The session's clean-up takes 1 s, and the lock must still be held while it runs.
        p = self.start("S", f"""
trap 'sleep 1; touch {self.t}/cleaned; exit 143' TERM
bash -c 'echo $$ > {self.t}/bg.pid; sleep 3; touch {self.t}/bg-finished' &
bash -c 'echo $$ > {self.t}/fg.pid; sleep 3; touch {self.t}/fg-finished' &
wait
""")
        self.wait_for(self.t / "bg.pid")
        self.wait_for(self.t / "fg.pid")
        p.send_signal(signal.SIGTERM)
        time.sleep(0.3)
        self.assertIsNone(p.poll(), "the lock went before the session's clean-up finished")
        self.assertFalse(self.free(), "another task got the G14 during the session's clean-up")
        self.assertEqual(p.wait(10), 143)
        self.assertTrue((self.t / "cleaned").exists())
        self.assertFalse(self.alive(self.t / "bg.pid"))
        self.assertFalse(self.alive(self.t / "fg.pid"))
        self.assertTrue(self.free())
        time.sleep(3.2)
        self.assertFalse((self.t / "bg-finished").exists())
        self.assertFalse((self.t / "fg-finished").exists())

    def test_lock_waits_for_cleanup_after_the_session_shell_dies(self):
        # What a G14 session looks like: a shell (dies at once on TERM) running gpu-diag.sh (cleans up for a while,
        # restoring what it changed). The lock must stay held through that clean-up, and a second signal to the
        # wrapper must not reach the clean-up.
        (self.t / "worker.py").write_text(f"""
import signal, time, pathlib
t = pathlib.Path({str(self.t)!r})
hits = []
def on_term(sig, frame):
    hits.append(sig)
    (t / "terms").write_text(str(len(hits)))
signal.signal(signal.SIGTERM, on_term)
(t / "worker.up").write_text("y")
while not hits:
    time.sleep(0.05)
time.sleep(1.0)                      # the clean-up
(t / "cleaned").write_text("y")
""")
        p = self.start("C", f"python3 {self.t}/worker.py\necho never\n")
        self.wait_for(self.t / "worker.up")
        p.send_signal(signal.SIGTERM)
        time.sleep(0.2)
        p.send_signal(signal.SIGTERM)
        time.sleep(0.4)
        self.assertIsNone(p.poll(), "the lock went while the clean-up ran")
        self.assertFalse(self.free(), "another task got the G14 during the clean-up")
        self.assertEqual(p.wait(10), 143)
        self.assertTrue((self.t / "cleaned").exists())
        self.assertEqual((self.t / "terms").read_text(), "1", "the second signal reached the clean-up")
        self.assertTrue(self.free())

    def test_grace_runs_from_the_signal_even_for_a_living_leader(self):
        # The Checker's case: the session leader itself ignores TERM. With a 2 s grace the whole session is killed
        # about 2 s after the signal, and only then is the lock free.
        (self.t / "stubborn.py").write_text(
            "import os,signal,time,pathlib\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            f"pathlib.Path({str(self.t / 'stubborn.pid')!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n")
        p = subprocess.Popen([str(LOCK), "run", "G", "--", "python3", str(self.t / "stubborn.py")], env=self.env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(p)
        self.wait_for(self.t / "stubborn.pid")
        t0 = time.monotonic()
        p.send_signal(signal.SIGTERM)
        time.sleep(1.0)
        self.assertIsNone(p.poll(), "the lock went before the grace ran out")
        self.assertFalse(self.free())
        p.wait(10)
        took = time.monotonic() - t0
        self.assertLess(took, 3.5, f"the grace (2 s) was not enforced: {took:.1f} s")
        self.assertFalse(self.alive(self.t / "stubborn.pid"))
        self.assertTrue(self.free())

    def test_interrupt_reaches_foreground_worker(self):
        # As the Checker's probe: a session whose foreground worker ignores nothing; INT to the lock wrapper.
        p = self.start("I", f"python3 -c \"import os,time,pathlib; pathlib.Path('{self.t}/w.pid').write_text(str(os.getpid())); "
                            f"time.sleep(2); pathlib.Path('{self.t}/w-finished').write_text('y')\"\n:\n")
        self.wait_for(self.t / "w.pid")
        p.send_signal(signal.SIGINT)
        p.wait(10)
        self.assertFalse(self.alive(self.t / "w.pid"))
        self.assertTrue(self.free())
        time.sleep(2.2)
        self.assertFalse((self.t / "w-finished").exists())

    def test_leftovers_end_with_the_session(self):
        # The session exits normally but leaves a process behind: it ends before the lock goes.
        r = self.run_lock("L", "bash", "-c", f"bash -c 'echo $$ > {self.t}/left.pid; exec sleep 60' & sleep 0.3")
        self.assertEqual(r.returncode, 0)
        self.assertIn("ending what the session left running", r.stderr)
        self.assertFalse(self.alive(self.t / "left.pid"))

    def test_stubborn_leftover_is_killed_after_grace(self):
        r = self.run_lock("K", "bash", "-c",
                          f"bash -c 'trap \"\" TERM; echo $$ > {self.t}/k.pid; while :; do sleep 0.1; done' & sleep 0.3")
        self.assertIn("KILL", r.stderr)
        self.assertFalse(self.alive(self.t / "k.pid"))

    def test_daemon_that_leaves_the_group_never_holds_the_lock(self):
        # Like the adb server: it calls setsid itself, so it is not session work and must not keep the lock.
        r = self.run_lock("D", "bash", "-c", f"setsid -f bash -c 'echo $$ > {self.t}/d.pid; exec sleep 30' "
                                             f"</dev/null >/dev/null 2>&1; sleep 0.3")
        self.assertEqual(r.returncode, 0)
        self.wait_for(self.t / "d.pid")
        self.assertTrue(self.alive(self.t / "d.pid"))
        self.assertTrue(self.free())
        os.kill(int((self.t / "d.pid").read_text()), signal.SIGTERM)

    def test_pending_gpu_diag_cleanup_holds_the_g14(self):
        # A gpu-diag run that could not confirm its sampler stopped: nothing but gpu-diag.sh (which reaps first)
        # gets the G14, and status says why, until the record is gone.
        rec = self.t / "g14.lock.pending-cleanup"
        rec.write_text("/data/local/tmp/openbook-gpu-diag\n")
        other = self.run_lock("U", "true")
        self.assertEqual(other.returncode, 75)
        self.assertIn("gpu-diag.sh reap", other.stderr)
        st = subprocess.run([str(LOCK), "status"], env=self.env, capture_output=True, text=True)
        self.assertEqual(st.returncode, 75)
        self.assertIn("clean-up pending", st.stdout)
        diag = self.t / "gpu-diag.sh"
        diag.write_text("#!/bin/sh\necho reaped\n")
        diag.chmod(0o755)
        r = self.run_lock("gpu-diag", str(diag))
        self.assertEqual((r.returncode, r.stdout), (0, "reaped\n"))
        rec.unlink()
        self.assertTrue(self.free())


if __name__ == "__main__":
    unittest.main(verbosity=1)
