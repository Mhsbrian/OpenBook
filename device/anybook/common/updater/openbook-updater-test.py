#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""openbook-updater (notice + download) on a synthetic listing and release, host side.

The laptop's own run (mksh, toybox, one-true-awk, curl) is the target environment; these tests pin
the behaviour: which build is chosen, when it downloads, how it verifies, resumes, stops and refuses.
OPENBOOK_UPDATER_TEST_ENV=$(engine-test-env.sh) runs every process of the engine (its locking re-exec
included) on Android's own mksh R59, one-true-awk and toybox, built from the AOSP tree; without it,
the host's sh and tools. openbook-updater-device-test.sh runs the scenarios on a device itself.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().with_name("openbook-updater")
DEVICE_ENV = os.environ.get("OPENBOOK_UPDATER_TEST_ENV")          # bin dir: sh, awk, toybox applets
SHELL = str(Path(DEVICE_ENV) / "sh") if DEVICE_ENV else "sh"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.bin / "getprop").write_text('#!/bin/sh\ncase $1 in ro.product.device) echo "$OBU_DEVICE" ;;'
                                          ' ro.build.version.incremental) echo "$OBU_BUILD" ;;'
                                          ' ro.build.id) echo "$OBU_BUILD_ID" ;; esac\n')
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

    def env(self, build="16658739", device="ruby", build_id="CL3B.260622.276.R4", reserve_kb=0, **extra):
        path = f"{self.bin}:{DEVICE_ENV}:{os.environ['PATH']}" if DEVICE_ENV else f"{self.bin}:{os.environ['PATH']}"
        return dict(os.environ, PATH=path, OBU_DEVICE=device, OBU_BUILD=build,
                    OBU_BUILD_ID=build_id, OPENBOOK_UPDATER_DIR=str(self.dir),
                    OPENBOOK_UPDATER_RESERVE_KB=str(reserve_kb), **extra)

    def run_updater(self, *args, listing=None, **env):
        cmd = [SHELL, str(SCRIPT)] + (["--listing", str(listing)] if listing else []) + list(args)
        return subprocess.run(cmd, env=self.env(**env), capture_output=True, text=True, timeout=120)

    def state(self):
        return dict(l.split("=", 1) for l in (self.dir / "state").read_text().splitlines())

    def release_record(self):
        return dict(l.split("=", 1) for l in (self.dir / "release").read_text().splitlines())



class Updater(Base):
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
        self.assertIn("does not match Google's MD5", r.stdout)
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

    def test_escaped_slashes_are_read_and_other_escapes_refused(self):
        # Valid JSON may write "/" as "\\/" (org.json, PHP); any other escape in a value is refused.
        path = self.root / "listing.json"
        path.write_text(json.dumps([self.entry(16999999)]).replace("/", "\\/"))
        r = self.run_updater("check", build="16452207", listing=path)
        self.assertEqual(r.returncode, 10, r.stdout + r.stderr)
        self.assertEqual(self.state()["url"], f"file://{self.release}")
        quoted = self.entry(16999999, url=f"file://{self.release}")
        path.write_text(json.dumps([quoted]).replace("recovery.zip", 'recovery\\u002ezip'))
        r = self.run_updater("check", build="16452207", listing=path)
        self.assertEqual(r.returncode, 9, r.stdout + r.stderr)          # the URL is dropped, never guessed

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

    def test_release_kinds(self):
        # running build ID -> Google's newer build ID -> kind. The train is the first three characters
        # (year letter, product letter, quarter); only the same train is taken by the laptop itself.
        cases = [("CL3B.260622.271.R1", "CL3B.260622.276.R4", "monthly"),   # Google's real 16452207 -> 16658739
                 ("CL3B.260622.276.R4", "CL3B.260622.301", "monthly"),
                 ("CL3B.260622.276.R4", "CL3C.260722.140", "monthly"),      # another variant, same train
                 ("CL3B.260622.276.R4", "CL4A.260915.088", "quarterly"),    # the next quarter
                 ("CL3B.260622.276.R4", "DL1A.270101.010", "quarterly"),    # next year's first quarter
                 ("CL3B.260622.276.R4", "DL2A.270301.010", "quarterly"),    # (a new Android version, perhaps)
                 ("CL3B.260622.276.R4", "CP4A.260915.088", "unknown"),      # another product
                 ("CL3B.260622.276.R4", "BL2A.260801.005", "unknown"),      # an earlier train
                 ("CL3B.260622.276.R4", "CL2A.260801.005", "unknown"),      # an earlier quarter
                 ("CL3B.260622.276.R4", "CL3B.260522.100", "unknown"),      # an earlier branch date
                 ("CL3B.260622.276.R4", "", "unknown"),                     # no build ID in the listing
                 ("eng.builder", "CL3B.260722.140", "unknown")]             # unparseable running ID
        for running_id, latest_id, kind in cases:
            with self.subTest(latest_id=latest_id):
                entry = self.entry(16999999, build=latest_id)
                if not latest_id:
                    entry["buildidentifier"] = "16999999"
                r = self.run_updater("check", build_id=running_id, listing=self.listing([entry]))
                self.assertEqual(r.returncode, 10, r.stdout + r.stderr)
                s = self.state()
                self.assertEqual((s["kind"], s["latest_id"], s["running_id"]), (kind, latest_id, running_id))
                self.assertIn(f"update available ({kind})", r.stdout)
                self.assertEqual(self.release_record()["kind"], kind)

    def test_only_monthly_releases_are_downloaded(self):
        for build in ("CL4A.260915.088", "DL2A.270301.010", "garbage"):
            with self.subTest(build=build):
                r = self.run_updater("download", listing=self.listing([self.entry(16999999, build=build)]))
                self.assertEqual(r.returncode, 8, r.stdout + r.stderr)
                self.assertEqual(self.state()["result"], "held")
                self.assertFalse((self.dir / "16999999").exists())

    def test_each_download_records_its_release(self):
        listing = self.listing([self.entry(16999999, build="CL3B.260722.140")])
        self.assertEqual(self.run_updater("download", listing=listing).returncode, 0)
        info = dict(l.split("=", 1) for l in (self.dir / "16999999" / "release.info").read_text().splitlines())
        self.assertEqual((info["number"], info["latest_id"], info["kind"]), ("16999999", "CL3B.260722.140", "monthly"))
        # Installed since: the download and its record go.
        self.assertEqual(self.run_updater("check", build="16999999", listing=listing).returncode, 0)
        self.assertFalse((self.dir / "16999999").exists())

    def test_release_file_survives_later_runs(self):
        listing = self.listing([self.entry(16999999, build="CL3B.260722.140")])
        self.assertEqual(self.run_updater("download", listing=listing).returncode, 0)
        self.assertEqual(self.run_updater("check", listing=self.root / "absent.json").returncode, 2)   # a failed check
        rel = self.release_record()
        self.assertEqual((rel["number"], rel["kind"], rel["md5"]), ("16999999", "monthly", self.md5))
        self.assertTrue((self.dir / "16999999" / "recovery.zip.md5").is_file())         # the download stays
        up = self.run_updater("check", build="16999999", listing=listing)               # after installing it
        self.assertEqual(up.returncode, 0)
        self.assertEqual(self.release_record()["number"], "16999999")
        self.assertNotIn("kind", self.release_record())

    def test_listing_refusals_are_not_checksum_failures(self):
        cases = {"malformed md5": self.entry(16658739, md5="xyz"),
                 "foreign host": self.entry(16658739, url="https://example.com/recovery.zip")}
        for label, entry in cases.items():
            with self.subTest(label):
                r = self.run_updater("check", build="16452207", listing=self.listing([entry]))
                self.assertEqual(r.returncode, 9, r.stdout + r.stderr)
                self.assertEqual(self.state()["result"], "error:9")

    def test_control_characters_never_forge_a_row(self):
        # A raw newline and the row separator inside a BETA entry's channel must not fake a STABLE row.
        forged = ("BETA\n16999999\x1f16999999_CL3B.260722.140\x1fSTABLE\x1f\x1fhttps://dl.google.com/forged\x1f"
                  + "0" * 32)
        entry = self.entry(16658739)
        entry["channel"] = "@CHANNEL@"
        path = self.root / "listing.json"
        path.write_bytes(json.dumps([entry]).replace("@CHANNEL@", forged).encode())
        r = self.run_updater("check", build="16452207", listing=path)
        self.assertEqual(r.returncode, 7, r.stdout + r.stderr)                          # no STABLE row at all

    def fake_curl(self):
        # A transfer that writes part of the release, then stalls like a slow network.
        (self.bin / "curl").write_text(
            '#!/bin/sh\necho $$ > "$OBU_CURL_PID"\n'
            'case " $* " in *" -I "*|*" -fsSIL "*) printf "HTTP/1.1 200 OK\\r\\ncontent-length: 300000\\r\\n\\r\\n"; exit 0 ;; esac\n'
            'while [ $# -gt 1 ]; do [ "$1" = -o ] && out=$2; shift; done\n'
            'head -c 4096 /dev/zero >> "$out"\nexec sleep 120\n')
        (self.bin / "curl").chmod(0o755)

    def test_stop_ends_the_transfer_and_keeps_the_partial(self):
        self.fake_curl()
        pid_file = self.root / "curl.pid"
        listing = self.listing([self.entry(16999999, build="CL3B.260722.140")])
        cmd = [SHELL, str(SCRIPT), "--listing", str(listing), "download"]
        proc = subprocess.Popen(cmd, env=self.env(OBU_CURL_PID=str(pid_file)), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        part = self.dir / "16999999" / "recovery.zip.part"
        deadline = time.monotonic() + 30
        while not (part.exists() and part.stat().st_size >= 4096):    # the download is under way
            self.assertLess(time.monotonic(), deadline, "the download never started")
            time.sleep(0.05)
        curl_pid = int(pid_file.read_text())
        t0 = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        out, _ = proc.communicate(timeout=20)
        self.assertLess(time.monotonic() - t0, 10, "the stop waited for the transfer")
        self.assertEqual(proc.returncode, 130, out)
        self.assertIn("stopped on request; the partial download of 16999999_CL3B.260722.140 is kept", out)
        with self.assertRaises(ProcessLookupError):                  # the transfer ended with it
            os.kill(curl_pid, 0)
        self.assertEqual(part.stat().st_size, 4096)
        s = self.state()
        self.assertEqual((s["result"], s["build"], s["part"]), ("stopped", "16999999_CL3B.260722.140", str(part)))
        (self.bin / "curl").unlink()                                  # the lock was released with the run
        self.assertEqual(self.run_updater("check", listing=listing).returncode, 10)

    def slow_md5(self):
        # md5sum that takes its time, as on a multi-gigabyte release.
        (self.bin / "md5sum").write_text('#!/bin/sh\necho $$ > "$OBU_MD5_PID"\nexec sleep 120\n')
        (self.bin / "md5sum").chmod(0o755)

    def test_stop_during_verification_ends_the_checksum(self):
        self.slow_md5()
        pid_file = self.root / "md5.pid"
        listing = self.listing([self.entry(16999999, build="CL3B.260722.140")])
        proc = subprocess.Popen([SHELL, str(SCRIPT), "--listing", str(listing), "download"],
                                env=self.env(OBU_MD5_PID=str(pid_file)), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        deadline = time.monotonic() + 30
        while not pid_file.exists():
            self.assertLess(time.monotonic(), deadline, "verification never started")
            time.sleep(0.05)
        proc.send_signal(signal.SIGTERM)
        out, _ = proc.communicate(timeout=20)
        self.assertEqual(proc.returncode, 130, out)
        with self.assertRaises(ProcessLookupError):                  # the checksum ended with it
            os.kill(int(pid_file.read_text()), 0)
        self.assertEqual(self.state()["result"], "stopped")
        self.assertIn("kept and verified on the next run", out)
        (self.bin / "md5sum").unlink()                               # the next run verifies and finishes
        r = self.run_updater("download", listing=listing)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state()["result"], "downloaded")

    def test_a_download_without_its_marker_is_verified_not_fetched_again(self):
        listing = self.listing([self.entry(16999999, build="CL3B.260722.140")])
        self.assertEqual(self.run_updater("download", listing=listing).returncode, 0)
        (self.dir / "16999999" / "recovery.zip.md5").unlink()        # stopped between the rename and the marker
        os.remove(self.root / "recovery.zip")                        # Google's file is gone: no refetch possible
        r = self.run_updater("download", listing=listing)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("already downloaded and verified", r.stdout)
        self.assertTrue((self.dir / "16999999" / "recovery.zip.md5").is_file())

    def test_status_before_and_after(self):
        self.assertIn("never-run", self.run_updater("status").stdout)
        self.run_updater("check", listing=self.listing([self.entry(16658739)]))
        self.assertIn("result=up-to-date", self.run_updater("status").stdout)


# A stand-in for openbook-adapt: each command leaves what the real one leaves, or fails as told by
# FAKE_ADAPT_HOLD (exit 8 with a reason), FAKE_ADAPT_FAIL (exit 1) or FAKE_ADAPT_SLEEP (seconds, for a stop).
FAKE_ADAPT = r"""#!/usr/bin/env python3
import json, os, sys, time
cmd, args = sys.argv[1], sys.argv[2:]
opt = {args[i]: args[i + 1] for i in range(0, len(args) - 1) if args[i].startswith("--")}
if os.environ.get("FAKE_ADAPT_SLEEP") and cmd == "adapt":
    time.sleep(float(os.environ["FAKE_ADAPT_SLEEP"]))
if os.environ.get("FAKE_ADAPT_HOLD") and cmd == "adapt":
    print("openbook-adapt: held: " + os.environ["FAKE_ADAPT_HOLD"], file=sys.stderr); sys.exit(8)
if os.environ.get("FAKE_ADAPT_FAIL") and cmd == "adapt":
    print("openbook-adapt: the rebuilt system differs", file=sys.stderr); sys.exit(1)
def mk(d): os.makedirs(d, exist_ok=False)
if cmd == "reconstruct":
    assert os.path.isfile(opt["--release"]) and os.path.isfile(opt["--layer"] + "/layer.json")
    mk(opt["--out"]); open(opt["--out"] + "/reconstruct.json", "w").write("{}")
elif cmd == "adapt":
    assert opt["--ours-root"] and os.path.isfile(opt["--key"])
    open(opt["--progress"], "w").write("build\n")
    mk(opt["--work"]); mk(opt["--out"])
    open(opt["--out"] + "/adapt.json", "w").write(json.dumps({"complete": True}))
    open(opt["--out"] + "/system.img", "w").write("img")
elif cmd == "payload":
    mk(opt["--out"]); open(opt["--out"] + "/payload.bin", "w").write("payload")
    json.dump({"signed": False, "metadata_hash_to_sign": "aa", "payload_hash_to_sign": "bb"}, open(opt["--out"] + "/payload.json", "w"))
elif cmd == "payload-sign":
    assert os.path.getsize(opt["--metadata-signature"]) and os.path.getsize(opt["--payload-signature"])
    d = json.load(open(opt["--dir"] + "/payload.json")); d["signed"] = True
    json.dump(d, open(opt["--dir"] + "/payload.json", "w"))
else:
    sys.exit(2)
"""


class Adapt(Base):
    def setUp(self):
        super().setUp()
        (self.bin / "openbook-adapt").write_text(FAKE_ADAPT)
        (self.bin / "openbook-adapt").chmod(0o755)
        self.layer = self.root / "layer"
        self.layer.mkdir()
        (self.layer / "layer.json").write_text("{}")
        self.key = self.root / "avb.pem"
        self.key.write_text("key")

    def env(self, **extra):
        extra.setdefault("OPENBOOK_ADAPT", str(self.bin / "openbook-adapt"))
        extra.setdefault("OPENBOOK_LAYER", str(self.layer))
        extra.setdefault("OPENBOOK_AVB_KEY", str(self.key))
        extra.setdefault("OPENBOOK_OURS_ROOT", str(self.root))
        return super().env(**extra)

    def downloaded(self):
        r = self.run_updater("download", listing=self.listing([self.entry(16658740)]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return self.dir / "16658740"

    def test_adapt_keeps_the_payload_and_records_and_is_idempotent(self):
        d = self.downloaded()
        r = self.run_updater("adapt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        s = self.state()
        self.assertEqual((s["result"], s["build"]), ("adapted", "16658740_CL3B.260622.276.R4"))
        self.assertTrue((d / "adapted/payload/payload.bin").is_file())
        self.assertTrue((d / "adapted/adapt.json").is_file() and (d / "adapted/reconstruct.json").is_file())
        self.assertFalse((d / "adapt.tmp").exists() or (d / "adapted/system.img").exists())
        self.assertFalse((self.dir / "adapt-progress").exists())
        r = self.run_updater("adapt")
        self.assertEqual(r.returncode, 0)
        self.assertIn("already adapted", r.stdout)

    def test_a_held_release_records_the_reason(self):
        d = self.downloaded()
        why = "/system/build.prop: OpenBook changes it, but Google changed it too"
        r = self.run_updater("adapt", FAKE_ADAPT_HOLD=why)
        self.assertEqual(r.returncode, 8, r.stdout + r.stderr)
        s = self.state()
        self.assertEqual((s["result"], s["detail"]), ("adapt-held", why))
        self.assertFalse((d / "adapted").exists() or (d / "adapt.tmp").exists())
        # Held for this layer: no new attempt, even when the adapter would now succeed.
        self.run_updater("check", listing=self.listing([self.entry(16658740)]))
        r = self.run_updater("adapt")
        self.assertEqual(r.returncode, 8, r.stdout + r.stderr)
        self.assertIn("still held", r.stdout)
        self.assertEqual(self.state()["detail"], why)
        # A new system (another layer) tries again.
        (self.layer / "layer.json").write_text('{"next": 1}')
        self.assertEqual(self.run_updater("adapt").returncode, 0)
        self.assertFalse((d / "adapt-held").exists())

    def test_a_fault_is_error_11(self):
        self.downloaded()
        r = self.run_updater("adapt", FAKE_ADAPT_FAIL="1")
        self.assertEqual(r.returncode, 11, r.stdout + r.stderr)
        self.assertEqual(self.state()["result"], "error:11")
        self.assertIn("rebuilt system differs", self.state()["detail"])

    def test_not_possible_without_the_adapter_or_a_download(self):
        r = self.run_updater("adapt", OPENBOOK_ADAPT=str(self.root / "missing"))
        self.assertEqual(r.returncode, 2)
        r = self.run_updater("adapt")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no verified download", self.state()["detail"])

    def test_space_is_checked_first(self):
        d = self.downloaded()
        r = self.run_updater("adapt", reserve_kb=10**15)
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertFalse((d / "adapt.tmp").exists())

    def test_sign_needs_the_apps_signatures(self):
        d = self.downloaded()
        self.assertEqual(self.run_updater("adapt").returncode, 0)
        self.assertEqual(self.run_updater("sign").returncode, 2)
        p = d / "adapted/payload"
        (p / "metadata.sig").write_bytes(b"m" * 512)
        (p / "payload.sig").write_bytes(b"p" * 512)
        r = self.run_updater("sign")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state()["result"], "ready")
        self.assertTrue(json.loads((p / "payload.json").read_text())["signed"])

    def test_a_newer_download_removes_an_older_adaptation(self):
        d = self.downloaded()
        self.assertEqual(self.run_updater("adapt").returncode, 0)
        r = self.run_updater("download", listing=self.listing([self.entry(16658741)]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(d.exists())

    def test_stop_during_adaptation(self):
        d = self.downloaded()
        p = subprocess.Popen([SHELL, str(SCRIPT), "adapt"], env=self.env(FAKE_ADAPT_SLEEP="30"),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(100):
            if (d / "adapt.tmp/google").exists():
                break
            time.sleep(0.1)
        time.sleep(0.5)
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 130, out)
        self.assertEqual(self.state()["result"], "stopped")
        r = self.run_updater("adapt")                      # starts again from the beginning
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
