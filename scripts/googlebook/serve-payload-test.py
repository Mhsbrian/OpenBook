#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""serve-payload.py against a real socket: full GETs, the Range forms update_engine uses, refusals, idle stop."""
import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

spec = importlib.util.spec_from_file_location("srv", Path(__file__).with_name("serve-payload.py"))
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)


class Serve(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.data = os.urandom(300_000)
        (root / "payload.bin").write_bytes(cls.data)
        (root / "payload_properties.txt").write_text("FILE_HASH=x\nFILE_SIZE=300000\n")
        (root / "secret.txt").write_text("not served")
        ready = threading.Event()
        cls.addr = None

        def on_ready(address):
            cls.addr = address
            ready.set()

        cls.thread = threading.Thread(target=srv.serve, args=(root, "127.0.0.1", 0, 3, on_ready), daemon=True)
        cls.thread.start()
        ready.wait(5)
        cls.base = f"http://127.0.0.1:{cls.addr[1]}"

    def get(self, path, rng=None, method="GET"):
        req = urllib.request.Request(self.base + path, method=method, headers={"Range": rng} if rng else {})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), r.read()

    def test_full_file(self):
        status, headers, body = self.get("/payload.bin")
        self.assertEqual((status, body), (200, self.data))
        self.assertEqual(headers["Accept-Ranges"], "bytes")

    def test_ranges(self):
        for rng, want in (("bytes=10-19", self.data[10:20]), ("bytes=299990-", self.data[299990:]),
                          ("bytes=-5", self.data[-5:]), ("bytes=0-999999", self.data)):
            status, headers, body = self.get("/payload.bin", rng)
            self.assertEqual((status, body), (206, want), rng)
            self.assertTrue(headers["Content-Range"].endswith("/300000"))

    def test_unsatisfiable_range(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.get("/payload.bin", "bytes=400000-")
        self.assertEqual(e.exception.code, 416)

    def test_only_the_two_files(self):
        for path in ("/secret.txt", "/../etc/passwd", "/"):
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.get(path)
            self.assertEqual(e.exception.code, 404, path)
        self.assertEqual(self.get("/payload_properties.txt")[0], 200)

    def test_head(self):
        status, headers, body = self.get("/payload.bin", method="HEAD")
        self.assertEqual((status, headers["Content-Length"], body), (200, "300000", b""))

    def test_zz_stops_when_idle(self):
        self.thread.join(10)  # idle_seconds=3
        self.assertFalse(self.thread.is_alive())


class Parse(unittest.TestCase):
    def test_parse_range(self):
        self.assertEqual(srv.parse_range("bytes=0-0", 10), (0, 0))
        self.assertEqual(srv.parse_range("bytes=-20", 10), (0, 9))
        self.assertIsNone(srv.parse_range("bytes=5-2", 10))
        self.assertIsNone(srv.parse_range("items=0-1", 10))
        self.assertIsNone(srv.parse_range("bytes=-", 10))


if __name__ == "__main__":
    unittest.main()
