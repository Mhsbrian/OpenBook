#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""openbook-updater (phase 1: notice + download) on a synthetic listing and release, host side.

The laptop's own run (mksh, toybox, one-true-awk, curl) is the target environment; these tests pin
the behaviour: which build is chosen, when it downloads, how it verifies, resumes and refuses.
OPENBOOK_UPDATER_TEST_SHELL picks the shell (default sh; use mksh where installed). mksh-only behaviour
(32-bit arithmetic, close-on-exec descriptors) is covered by openbook-updater-device-test.sh on the laptop.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().with_name("openbook-updater")
SHELL = os.environ.get("OPENBOOK_UPDATER_TEST_SHELL", "sh")


class Updater(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.bin / "getprop").write_text('#!/bin/sh\ncase $1 in ro.product.device) echo "$OBU_DEVICE" ;;'
                                          ' ro.build.version.incremental) echo "$OBU_BUILD" ;; esac\n')
        (self.bin / "getprop").chmod(0o755)
        self.dir = self.root / "state"
        self.release = self.root / "recovery.zip"
        self.release.write_bytes(os.urandom(300_000))
        self.md5 = hashlib.md5(self.release.read_bytes()).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def listing(self, entries, compact=False):
        path = self.root / "listing.json"
        path.write_text(json.dumps(entries, indent=None if compact else 1))
        return path

    def entry(self, number, channel="STABLE", device="ruby", url=None, md5=None, build="CL3B.260622.276.R4"):
        return dict(device=device, channel=channel, buildidentifier=f"{number}_{build}", dateupdated="2026-10-22",
                    url=url or f"file://{self.release}", md5=md5 or self.md5, filesize=19069493760, zipfilesize=1)

    def run_updater(self, *args, build="16658739", device="ruby", listing=None, reserve_kb=0, **extra):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", OBU_DEVICE=device, OBU_BUILD=build,
                   OPENBOOK_UPDATER_DIR=str(self.dir), OPENBOOK_UPDATER_RESERVE_KB=str(reserve_kb), **extra)
        cmd = [SHELL, str(SCRIPT)] + (["--listing", str(listing)] if listing else []) + list(args)
        return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)

    def state(self):
        return dict(l.split("=", 1) for l in (self.dir / "state").read_text().splitlines())

    def test_up_to_date(self):
        r = self.run_updater("check", listing=self.listing([self.entry(16658739), self.entry(16452207)]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        s = self.state()
        self.assertEqual((s["result"], s["running"], s["latest"]), ("up-to-date", "16658739", "16658739_CL3B.260622.276.R4"))

    def test_update_available_picks_newest_stable_for_this_device(self):
        entries = [self.entry(16452207), self.entry(16658739),
                   self.entry(16999999, channel="BETA"),            # not STABLE
                   self.entry(17000000, device="lapis"),            # another device
                   dict(device="ruby", channel="STABLE", buildidentifier="garbage")]  # no build number
        for compact in (False, True):
            with self.subTest(compact=compact):
                r = self.run_updater("check", build="16452207", listing=self.listing(entries, compact))
                self.assertEqual(r.returncode, 10, r.stdout + r.stderr)
                s = self.state()
                self.assertEqual((s["result"], s["latest"], s["md5"]),
                                 ("update-available", "16658739_CL3B.260622.276.R4", self.md5))

    def test_download_verifies_and_is_idempotent(self):
        listing = self.listing([self.entry(16658739)])
        r = self.run_updater("download", build="16452207", listing=listing)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = self.dir / "16658739" / "recovery.zip"
        self.assertEqual(got.read_bytes(), self.release.read_bytes())
        self.assertEqual((self.state()["result"], self.state()["verified"]), ("downloaded", "16658739_CL3B.260622.276.R4"))
        again = self.run_updater("download", build="16452207", listing=listing)
        self.assertEqual(again.returncode, 0)
        self.assertIn("already downloaded and verified", again.stdout)

    def test_md5_mismatch_is_refused_and_cleaned(self):
        r = self.run_updater("download", build="16452207", listing=self.listing([self.entry(16658739, md5="0" * 32)]))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse((self.dir / "16658739" / "recovery.zip").exists())
        self.assertFalse((self.dir / "16658739" / "recovery.zip.part").exists())
        self.assertEqual(self.state()["result"], "error:4")

    def test_resume_and_complete_partial(self):
        listing = self.listing([self.entry(16658739)])
        part = self.dir / "16658739" / "recovery.zip.part"
        for label, prefix in (("resume", 123_457), ("complete", self.release.stat().st_size)):
            with self.subTest(label):
                part.parent.mkdir(parents=True, exist_ok=True)
                (part.parent / "recovery.zip").unlink(missing_ok=True)
                part.write_bytes(self.release.read_bytes()[:prefix])
                r = self.run_updater("download", build="16452207", listing=listing)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual((part.parent / "recovery.zip").read_bytes(), self.release.read_bytes())
                self.assertIn(f"resuming at {prefix}" if label == "resume" else "already complete", r.stdout)

    def test_not_enough_space(self):
        r = self.run_updater("download", build="16452207", listing=self.listing([self.entry(16658739)]),
                             reserve_kb=10**12)
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertFalse((self.dir / "16658739" / "recovery.zip.part").exists())

    def test_second_run_is_refused_while_one_holds_the_lock(self):
        self.dir.mkdir()
        with open(self.dir / "lock", "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r = self.run_updater("check", listing=self.listing([self.entry(16658739)]))
        self.assertEqual(r.returncode, 6)

    def test_untrusted_sources_are_refused(self):
        cases = {"malformed md5": self.entry(16658739, md5="xyz"),
                 "foreign host": self.entry(16658739, url="https://example.com/recovery.zip")}
        for label, entry in cases.items():
            with self.subTest(label):
                r = self.run_updater("check", build="16452207", listing=self.listing([entry]))
                self.assertEqual(r.returncode, 4, r.stdout + r.stderr)

    def test_non_numeric_running_build_and_missing_listing(self):
        r = self.run_updater("check", build="eng.builder", listing=self.listing([self.entry(16658739)]))
        self.assertEqual(r.returncode, 2)
        r = self.run_updater("check", listing=self.root / "absent.json")
        self.assertEqual(r.returncode, 2)

    def test_oversized_partial_is_discarded_and_older_downloads_pruned(self):
        listing = self.listing([self.entry(16658739)])
        old = self.dir / "16452207"
        old.mkdir(parents=True)
        (old / "recovery.zip").write_bytes(b"old release")
        (old / "recovery.zip.md5").write_text("0" * 32 + "\n")
        keep = self.dir / "notes"          # not an updater download: never touched
        keep.mkdir()
        part = self.dir / "16658739" / "recovery.zip.part"
        part.parent.mkdir()
        part.write_bytes(self.release.read_bytes() + b"stale tail")
        r = self.run_updater("download", build="16452207", listing=listing)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("discarding a partial download larger than the release", r.stdout)
        self.assertEqual((part.parent / "recovery.zip").read_bytes(), self.release.read_bytes())
        self.assertFalse(old.exists())
        self.assertTrue(keep.is_dir())

    def test_reserve_above_32_bits_is_not_wrapped(self):
        # mksh wraps 4294968296 to 1000; the awk comparison must still refuse.
        r = self.run_updater("download", build="16452207", listing=self.listing([self.entry(16658739)]),
                             reserve_kb=4294968296)
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)

    def test_help_plain_http_and_unlisted_device(self):
        help_text = self.run_updater("--help").stdout
        self.assertIn("usage: openbook-updater", help_text)
        self.assertNotIn("set -u", help_text)
        r = self.run_updater("check", listing="http://dl.google.com/listing.json")
        self.assertEqual(r.returncode, 2)
        r = self.run_updater("check", device="lapis", listing=self.listing([self.entry(16658739)]))
        self.assertEqual(r.returncode, 7)

    def test_entry_with_empty_fields_keeps_its_url_and_md5(self):
        entry = self.entry(16658739)
        entry["dateupdated"] = ""          # an empty field must not shift the ones after it
        del entry["channel"]
        entry["channel"] = "STABLE"
        r = self.run_updater("check", build="16452207", listing=self.listing([entry]))
        self.assertEqual(r.returncode, 10, r.stdout + r.stderr)
        self.assertEqual((self.state()["url"], self.state()["md5"]), (f"file://{self.release}", self.md5))

    def test_tampered_download_is_rehashed_and_fetched_again(self):
        listing = self.listing([self.entry(16658739)])
        self.assertEqual(self.run_updater("download", build="16452207", listing=listing).returncode, 0)
        zip_path = self.dir / "16658739" / "recovery.zip"
        zip_path.write_bytes(b"planted, but next to a valid-looking marker")
        r = self.run_updater("download", build="16452207", listing=listing)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no longer matches Google's MD5", r.stdout)
        self.assertEqual(zip_path.read_bytes(), self.release.read_bytes())

    def test_installed_builds_are_pruned_when_up_to_date(self):
        old = self.dir / "16658739"
        old.mkdir(parents=True)
        (old / "recovery.zip").write_bytes(b"installed release")
        r = self.run_updater("check", build="16658739", listing=self.listing([self.entry(16658739)]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(old.exists())

    def test_failed_download_keeps_the_partial_for_resume(self):
        missing = self.root / "gone.zip"
        listing = self.listing([self.entry(16658739, url=f"file://{missing}")])
        part = self.dir / "16658739" / "recovery.zip.part"
        part.parent.mkdir(parents=True)
        part.write_bytes(b"first megabytes")
        r = self.run_updater("download", build="16452207", listing=listing)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(part.read_bytes(), b"first megabytes")
        self.assertEqual(self.state()["result"], "error:3")
        self.assertIn("latest", self.state())          # the check's context is kept

    def test_listing_as_file_url(self):
        listing = self.listing([self.entry(16658739)])
        r = self.run_updater("check", listing=f"file://{listing}")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_error_before_check_starts_a_fresh_state(self):
        self.assertEqual(self.run_updater("download", build="16452207",
                                          listing=self.listing([self.entry(16658739)])).returncode, 0)
        r = self.run_updater("check", listing=self.root / "absent.json")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("verified", self.state())

    FAST = dict(OPENBOOK_UPDATER_FIRST_DELAY="0", OPENBOOK_UPDATER_INTERVAL="0", OPENBOOK_UPDATER_STEP="0",
                OPENBOOK_UPDATER_CYCLES="2")

    def test_watch_only_notices(self):
        listing = self.listing([self.entry(16658739)])
        (self.dir).mkdir(exist_ok=True)
        (self.dir / "consent").write_text("auto_download=1\n")          # no longer a switch: watch never downloads
        r = self.run_updater("watch", build="16452207", listing=listing, **self.FAST)
        self.assertEqual(r.returncode, 10, r.stdout + r.stderr)           # update available, nothing fetched
        self.assertIn("check 2 finished (exit 10)", r.stdout)
        self.assertFalse((self.dir / "16658739").exists())

    def test_watch_first_check_is_on_time(self):
        import time
        t0 = time.monotonic()
        r = self.run_updater("watch", listing=self.listing([self.entry(16658739)]), OPENBOOK_UPDATER_FIRST_DELAY="2",
                             OPENBOOK_UPDATER_INTERVAL="3600", OPENBOOK_UPDATER_STEP="900", OPENBOOK_UPDATER_CYCLES="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertLess(time.monotonic() - t0, 30)                         # not one 900 s step

    def test_watch_survives_failures_and_holds_no_lock_between_cycles(self):
        r = self.run_updater("watch", listing=self.root / "absent.json", **self.FAST)
        self.assertIn("check 1 finished (exit 2)", r.stdout)               # a failed cycle ...
        self.assertIn("check 2 finished (exit 2)", r.stdout)               # ... does not end the service
        self.dir.mkdir(exist_ok=True)
        with open(self.dir / "lock", "w") as held:                         # a manual run holding the lock
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r = self.run_updater("watch", listing=self.listing([self.entry(16658739)]), **self.FAST)
        self.assertIn("check 1 finished (exit 6)", r.stdout)               # that cycle yields, the watcher lives

    def test_logcat_path_does_not_recurse(self):
        (self.bin / "log").write_text('#!/bin/sh\necho "LOGCAT $*" >> "$OBU_LOGCAT"\n')
        (self.bin / "log").chmod(0o755)
        sink = self.root / "logcat.txt"
        r = self.run_updater("check", listing=self.listing([self.entry(16658739)]), ANDROID_ROOT="/system",
                             OBU_LOGCAT=str(sink))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sink.read_text().count("LOGCAT -t openbook-updater up to date"), 1)

    def test_status_before_and_after(self):
        self.assertIn("never-run", self.run_updater("status").stdout)
        self.run_updater("check", listing=self.listing([self.entry(16658739)]))
        self.assertIn("result=up-to-date", self.run_updater("status").stdout)


if __name__ == "__main__":
    unittest.main()
