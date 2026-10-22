#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit checks for build-ota-trust-candidate.py and the reassembler's added-path rows.

The full image build, EROFS comparison and VM behavior are exercised on real
images (see docs/googlebook-ota-trust.md)."""
import argparse
import base64
import hashlib
import importlib.util
import io
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import unittest.mock
import zipfile

spec = importlib.util.spec_from_file_location("trust", Path(__file__).with_name("build-ota-trust-candidate.py"))
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
b = t.b


def row(path, mode, nlink=1, size=0):
    return f"I {path.encode().hex()} {mode} 0 0 {nlink} {size} 1230768000 0"


BASE = sorted([row("", 0o040755, 3), row("/system", 0o040755, 3), row("/system/etc", 0o040755, 2),
               row("/system/etc/hosts", 0o100644, 1, 10)])


def payload(signature=b"s" * 8):
    manifest = b"m" * 20
    body = b"CrAU" + struct.pack(">QQI", 2, len(manifest), len(signature)) + manifest + signature + b"data"
    meta = 24 + len(manifest)
    props = (f"FILE_HASH={base64.b64encode(hashlib.sha256(body).digest()).decode()}\n"
             f"FILE_SIZE={len(body)}\n"
             f"METADATA_HASH={base64.b64encode(hashlib.sha256(body[:meta]).digest()).decode()}\n"
             f"METADATA_SIZE={meta}\n")
    return body, props


class AdditionRows(unittest.TestCase):
    def test_directory_and_files_get_fixed_ownership_label_and_parent_link(self):
        rows = b.addition_metadata(BASE, {"/system/etc/t": None, "/system/etc/t/a": b"abc"})
        parsed = {bytes.fromhex(r.split(" ")[1]).decode(): r.split(" ") for r in rows if r.startswith("I ")}
        self.assertEqual(parsed["/system/etc"][5], "3")
        self.assertEqual(parsed["/system/etc/t"][2:7], [str(0o040755), "0", "0", "2", "0"])
        self.assertEqual(parsed["/system/etc/t/a"][2:7], [str(0o100644), "0", "0", "1", "3"])
        labels = [r for r in rows if r.startswith("X ")]
        self.assertEqual(len(labels), 2)
        self.assertTrue(all(bytes.fromhex(r.split(" ")[3]) == b"u:object_r:system_file:s0" for r in labels))
        self.assertEqual(b.addition_metadata(BASE, {}), BASE)

    def test_refuses_existing_orphan_non_directory_parent_and_whitespace(self):
        for additions in ({"/system/etc/hosts": b"x"}, {"/system/none/a": b"x"},
                          {"/system/etc/hosts/a": b"x"}, {"/system/etc/a b": b"x"}):
            with self.assertRaises(ValueError):
                b.addition_metadata(BASE, additions)


class TrustArchive(unittest.TestCase):
    def test_single_deterministic_stored_entry_that_update_engine_reads(self):
        first, second = t.archive(b"PEM"), t.archive(b"PEM")
        self.assertEqual(first, second)
        with zipfile.ZipFile(io.BytesIO(first)) as z:
            [info] = z.infolist()
            self.assertTrue(info.filename.endswith("x509.pem"))
            self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
            self.assertEqual(z.read(info), b"PEM")


@unittest.skipUnless(shutil.which("openssl"), "openssl required")
class Certificate(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def make(self, name, *key):
        subprocess.run(["openssl", "req", "-x509", "-nodes", "-days", "1", "-subj", f"/CN={name}",
                        *key, "-keyout", str(self.dir / f"{name}.key"), "-out", str(self.dir / f"{name}.pem")],
                       check=True, capture_output=True)
        path = self.dir / f"{name}.pem"
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_accepts_pinned_rsa_certificate(self):
        path, digest = self.make("ok", "-newkey", "rsa:2048")
        pem, record = t.certificate("openssl", path, digest)
        self.assertEqual(pem, path.read_bytes())
        self.assertEqual((record["subject"], record["rsa_bits"]), ("CN=ok", 2048))

    def test_refuses_wrong_pin_key_material_and_non_rsa(self):
        path, digest = self.make("rsa", "-newkey", "rsa:2048")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            t.certificate("openssl", path, "0" * 64)
        bundle = self.dir / "bundle.pem"
        bundle.write_bytes(path.read_bytes() + (self.dir / "rsa.key").read_bytes())
        with self.assertRaisesRegex(ValueError, "no key material"):
            t.certificate("openssl", bundle, hashlib.sha256(bundle.read_bytes()).hexdigest())
        path, digest = self.make("ec", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256")
        with self.assertRaisesRegex(ValueError, "RSA"):
            t.certificate("openssl", path, digest)


class TestPayloads(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        for case in t.CASES:
            body, props = payload()
            (self.dir / f"{case}.bin").write_bytes(body)
            (self.dir / f"{case}.properties").write_text(props)

    def test_metadata_is_header_manifest_and_signature(self):
        files, record = t.test_payloads(self.dir)
        body = (self.dir / "foreign-static.bin").read_bytes()
        self.assertEqual(files[f"{t.TEST_DIR}/foreign-static.metadata"], body[:24 + 20 + 8])
        self.assertEqual(record["foreign-static"]["metadata_size"], 44)
        self.assertEqual(len(files), 3 * len(t.CASES))

    def test_refuses_properties_for_another_payload(self):
        (self.dir / "openbook-vab.bin").write_bytes(payload(b"x" * 8)[0])
        with self.assertRaisesRegex(ValueError, "openbook-vab: properties"):
            t.test_payloads(self.dir)


class Modes(unittest.TestCase):
    def test_stock_trust_is_a_vm_control_and_excludes_a_certificate(self):
        base = dict(cert=None, cert_sha256=None, input_correction=False, vm_test_signer=None)
        with self.assertRaisesRegex(ValueError, "control only"):
            t.build(argparse.Namespace(**base, vm_test=None, stock_trust=True))
        with self.assertRaisesRegex(ValueError, "Supply --cert"):
            t.build(argparse.Namespace(**base, vm_test=Path("x"), stock_trust=False))
        with self.assertRaisesRegex(ValueError, "Supply --cert"):
            t.build(argparse.Namespace(**{**base, "cert": Path("c")}, vm_test=Path("x"), stock_trust=True))
        with self.assertRaisesRegex(ValueError, "--vm-test-signer"):
            t.build(argparse.Namespace(**base, vm_test=Path("x"), stock_trust=True))


class TrustedCases(unittest.TestCase):
    """The harness trusts openbook-* payloads only when their signer is the installed certificate."""

    def transform_record(self, installed, signer):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        source = root / "source"
        (source / "system/etc/security").mkdir(parents=True)
        (source / "system/etc/init").mkdir(parents=True)
        stock = io.BytesIO()
        with zipfile.ZipFile(stock, "w") as z:
            z.writestr(t.STOCK_ENTRY, b"google")
        (source / t.OTACERTS.lstrip("/")).write_bytes(stock.getvalue())
        (source / "system/etc/init/update_engine.rc").write_text(t.g.q.STOCK_RC)
        payloads = root / "payloads"; payloads.mkdir()
        for case in t.CASES:
            body, props = payload()
            (payloads / f"{case}.bin").write_bytes(body)
            (payloads / f"{case}.properties").write_text(props)
        (root / "installed.pem").write_bytes(installed)
        (root / "signer.pem").write_bytes(signer)
        seen = {}

        def fake_build_system(a, transform, schema):
            seen["result"] = transform(source)
        a = argparse.Namespace(cert=root / "installed.pem", cert_sha256="pin", stock_trust=False,
                               input_correction=False, vm_test=payloads, vm_test_signer=root / "signer.pem")
        with unittest.mock.patch.object(t, "STOCK_OTACERTS_SHA256", hashlib.sha256(stock.getvalue()).hexdigest()), \
                unittest.mock.patch.object(t, "certificate", return_value=(installed, {"certificate_sha256": "c"})), \
                unittest.mock.patch.object(t.g, "test_policy", return_value=({}, {"scope": "test"})), \
                unittest.mock.patch.object(t.b, "build_system", fake_build_system):
            t.build(a)
        replacements, annotations, additions = seen["result"]
        return annotations["experimental_ota_trust_test"]["trusted_cases"]

    def test_matching_signer_trusts_openbook_cases(self):
        self.assertEqual(self.transform_record(b"PEM-A", b"PEM-A"), ["openbook-static", "openbook-vab"])

    def test_release_certificate_trusts_no_test_payload(self):
        self.assertEqual(self.transform_record(b"PEM-RELEASE", b"PEM-TEST"), [])


class StageBase(unittest.TestCase):
    def test_refuses_a_source_that_differs_from_its_pin(self):
        spec = importlib.util.spec_from_file_location("stage", Path(__file__).with_name("stage-base.py"))
        stage = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stage)
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        (root / "ruby-live.img").write_bytes(b"image")
        (root / "manifest.json").write_text('{"image_sha256": "%s"}' % hashlib.sha256(b"image").hexdigest())
        with self.assertRaisesRegex(ValueError, "differs from its pin"):
            stage.stage(root, "0" * 64, root, root / "out")
        self.assertFalse((root / "out").exists())



class ApplyMode(unittest.TestCase):
    """--apply-from-drive swaps in the mount+apply harness and bakes no payloads."""

    def test_refuses_combining_with_vm_test(self):
        base = dict(cert=Path("c"), cert_sha256="s", stock_trust=False, input_correction=False,
                    vm_test=Path("x"), vm_test_signer=Path("y"), apply_from_drive=True)
        with self.assertRaisesRegex(ValueError, "pick one"):
            t.build(argparse.Namespace(**base))

    def test_apply_mounts_payload_with_ota_label_and_applies(self):
        # init mounts the drive with the ota_package_file label; the driver runs as shell.
        self.assertIn("context=u:object_r:ota_package_file:s0", t.APPLY_SERVICE)
        self.assertIn("mount ext4 /dev/block/nvme1n1 /mnt/otapayload", t.APPLY_SERVICE)
        self.assertIn("mount ext4 /dev/block/nvme0n1 /mnt/otapayload", t.APPLY_SERVICE)  # numbering varies
        self.assertIn("seclabel u:r:shell:s0", t.APPLY_SERVICE)
        self.assertIn("update_engine_client --update", t.APPLY_SCRIPT)
        self.assertIn("payload=file:///mnt/otapayload/payload.bin", t.APPLY_SCRIPT)
        self.assertNotIn("CASES", t.APPLY_SCRIPT)  # no baked test payloads

if __name__ == "__main__":
    unittest.main()
