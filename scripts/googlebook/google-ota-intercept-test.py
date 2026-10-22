#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""capture-google-ota.py (offer parsing) and inspect-google-ota.py (zip + payload reading) on synthetic OTAs."""
import base64
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import tempfile
import threading
import unittest
import zipfile

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cap = load("cap", "capture-google-ota.py")
ins = load("ins", "inspect-google-ota.py")
srv = load("srv", "serve-payload.py")


def varint(v):
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        out.append(b | (0x80 if v else 0))
        if not v:
            return bytes(out)


def field(num, value):
    if isinstance(value, int):
        return varint(num << 3) + varint(value)
    if isinstance(value, str):
        value = value.encode()
    return varint(num << 3 | 2) + varint(len(value)) + value


def payload(parts, minor=8):
    """CrAU v2 header + manifest; parts: [(name, old_size, old_hash_bytes, new_size, new_hash_bytes)]."""
    m = field(12, minor)
    for name, osz, oh, nsz, nh in parts:
        body = field(1, name) + field(7, field(1, nsz) + field(2, nh))
        if osz:
            body += field(6, field(1, osz) + field(2, oh))
        m += field(13, body)
    m += field(15, field(1, field(1, "google_dynamic_partitions") + field(2, 12880707584) + field(3, "system"))
               + field(3, 1) + field(4, "lz4"))
    return b"CrAU" + struct.pack(">QQI", 2, len(m), 0) + m + os.urandom(4096)


class Inspect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.stock = t / "stock"
        cls.stock.mkdir()
        old = os.urandom(8192)
        (cls.stock / "system.img").write_bytes(old + b"\0" * 4096)  # stock image longer than the old partition
        cls.payload = payload([("system", 8192, hashlib.sha256(old).digest(), 12288, os.urandom(32)),
                               ("boot", 4096, os.urandom(32), 4096, os.urandom(32))])
        digest = hashlib.sha256(cls.payload).digest()
        props = f"FILE_HASH={base64.b64encode(digest).decode()}\nFILE_SIZE={len(cls.payload)}\n"
        meta = ("ota-type=AB\npost-build=Lenovo/ruby/ruby:17/XX1A.261101.001/17000000:user/release-keys\n"
                "post-build-incremental=17000000\npre-build-incremental=16452207\npre-device=ruby\n")
        cls.zips = {}
        for name, z64 in (("plain", False), ("zip64", True)):
            path = t / f"{name}.zip"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr(zipfile.ZipInfo("META-INF/com/android/metadata"), meta, zipfile.ZIP_DEFLATED)
                z.writestr("payload_properties.txt", props)
                with z.open(zipfile.ZipInfo("payload.bin"), "w", force_zip64=z64) as f:
                    f.write(cls.payload)
            cls.zips[name] = path

    def check(self, info):
        self.assertEqual(info["kind"], "incremental")
        self.assertEqual((info["pre_build_incremental"], info["post_build_incremental"]), ("16452207", "17000000"))
        self.assertEqual(info["payload_bytes"], len(self.payload))
        rows = {r["name"]: r for r in info["partitions"]}
        self.assertTrue(rows["system"]["stock_matches"])
        self.assertFalse(rows["boot"]["stock_matches"])  # no stock boot.img here
        self.assertFalse(info["stock_source_matches"])

    def test_local_zip_and_zip64(self):
        for name, path in self.zips.items():
            with self.subTest(name):
                self.check(ins.inspect(ins.Source(str(path)), self.stock))

    def test_over_http_ranges_and_download(self):
        root = Path(self.tmp.name) / "served"
        root.mkdir(exist_ok=True)
        (root / "payload.bin").write_bytes(self.zips["zip64"].read_bytes())  # the server serves this name only
        (root / "payload_properties.txt").write_text("x")
        ready, box = threading.Event(), {}
        threading.Thread(target=srv.serve, args=(root, "127.0.0.1", 0, 5, lambda a: (box.update(a=a), ready.set())),
                         daemon=True).start()
        ready.wait(5)
        src = ins.Source(f"http://127.0.0.1:{box['a'][1]}/payload.bin")
        info = ins.inspect(src, self.stock)
        self.check(info)
        out = Path(self.tmp.name) / "dl"
        out.mkdir(exist_ok=True)
        d = ins.download(src, info, out)
        self.assertTrue(d["size_matches"] and d["hash_matches"])
        self.assertEqual((out / "payload.bin").read_bytes(), self.payload)

    def test_tampered_stock_is_caught(self):
        bad = Path(self.tmp.name) / "bad"
        bad.mkdir(exist_ok=True)
        (bad / "system.img").write_bytes(os.urandom(12288))
        rows = {r["name"]: r for r in ins.inspect(ins.Source(str(self.zips["plain"])), bad)["partitions"]}
        self.assertFalse(rows["system"]["stock_matches"])


class Capture(unittest.TestCase):
    LOG = """10-22 08:30:12.100  1200  1300 I SystemUpdate: Checking for system update
10-22 08:30:15.200   553   553 I update_engine: [INFO:update_attempter_android.cc(251)] ApplyPayload(https://ota.googlezip.net/packages/ota-api/package/abcdef0123456789.zip, 1234, 987654321) FILE_HASH=AbC= FILE_SIZE=987654321 METADATA_HASH=XyZ= METADATA_SIZE=120000
10-22 08:30:16.300   553   553 E update_engine: [ERROR:delta_performer.cc] Mandatory metadata signature validation failed
10-22 08:30:16.400  3000  3000 I update_engine_client: onPayloadApplicationComplete(ErrorCode::kDownloadMetadataSignatureMismatch (26))
10-22 08:30:17.000  1200  1300 I SystemUpdate: target CL3B.261101.005 build 17000000
10-22 08:30:18.000   900   900 I ActivityManager: unrelated line
"""

    def test_parse_offer(self):
        o = cap.parse(self.LOG)
        self.assertEqual(o["url"], "https://ota.googlezip.net/packages/ota-api/package/abcdef0123456789.zip")
        self.assertEqual((o["offset"], o["size"]), (1234, 987654321))
        self.assertEqual(o["headers"]["FILE_SIZE"], "987654321")
        self.assertEqual(o["headers"]["METADATA_SIZE"], "120000")
        self.assertEqual(o["result"], "kDownloadMetadataSignatureMismatch")
        self.assertIn("17000000", o["builds"])
        self.assertEqual(len(o["lines"]), 5)

    def test_redaction(self):
        self.assertEqual(cap.redact("https://ota.googlezip.net/packages/ota-api/package/abc.zip?x=1"),
                         "https://ota.googlezip.net/…/abc.zip")

    def test_other_google_downloads_are_not_offers(self):
        log = ("10-22 19:10:01.000 1200 1300 I SodaDownload: fetching "
               "https://dl.google.com/android/soda/soda-en-US-v3072.zip done\n")
        o = cap.parse(log)
        self.assertIsNone(o["url"])
        self.assertEqual(o["other_downloads"], ["https://dl.google.com/…/soda-en-US-v3072.zip"])

    def test_ota_like_url_without_update_engine(self):
        o = cap.parse("10-22 08:30:12.100 1200 1300 I SystemUpdate: url "
                      "https://ota.googlezip.net/packages/ota-api/package/abc.zip\n")
        self.assertEqual(o["source"], "GMS log (OTA-like URL)")

    def test_no_offer(self):
        self.assertIsNone(cap.parse("10-22 08:30:18.000 900 900 I ActivityManager: nothing")["url"])


if __name__ == "__main__":
    unittest.main()
