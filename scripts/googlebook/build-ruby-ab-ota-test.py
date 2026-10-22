#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit checks for build-ruby-ab-ota.py's payload read-back (the real build runs delta_generator)."""
import base64
import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location("ota", Path(__file__).with_name("build-ruby-ab-ota.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

NAMES = list(m.DYNAMIC) + list(m.STATIC)


def payload(names=NAMES, version=2):
    manifest = (" ".join(names)).encode()
    body = b"CrAU" + struct.pack(">QQI", version, len(manifest), 256) + manifest + b"\0" * 256
    props = (f"FILE_SIZE={len(body)}\n"
             f"FILE_HASH={base64.b64encode(hashlib.sha256(body).digest()).decode()}\n")
    return body, props


class Checks(unittest.TestCase):
    def test_all_pass_for_a_well_formed_signed_payload(self):
        body, props = payload()
        c = m.payload_checks(body, props, NAMES, True)
        self.assertTrue(all(c.values()), c)

    def test_missing_partition_is_caught(self):
        body, props = payload(names=["system", "boot"])  # no init_boot/vendor_boot/vbmeta
        c = m.payload_checks(body, props, NAMES, True)
        self.assertFalse(c["all_partitions_present"])

    def test_unsigned_or_wrong_key_is_caught(self):
        body, props = payload()
        self.assertFalse(m.payload_checks(body, props, NAMES, False)["metadata_signature_verifies_against_cert"])

    def test_tampered_payload_breaks_properties(self):
        body, props = payload()
        c = m.payload_checks(body + b"x", props, NAMES, True)  # size/hash no longer match props
        self.assertFalse(c["properties_match_payload"])

    def test_wrong_major_version_is_caught(self):
        body, props = payload(version=1)
        self.assertFalse(m.payload_checks(body, props, NAMES, True)["crau_v2"])


class PartitionSet(unittest.TestCase):
    def test_every_googlebook_dynamic_partition_is_in_the_payload(self):
        # update_engine builds the new slot's partition table from exactly this list.
        self.assertEqual(set(m.DYNAMIC),
                         {"system", "system_ext", "product", "vendor", "vendor_dlkm", "system_dlkm"})

    def test_partition_list_is_space_separated(self):
        text = m.dynamic_partition_info("google_dynamic_partitions", 12880707584)
        line = next(x for x in text.splitlines() if x.startswith("google_dynamic_partitions_partition_list="))
        self.assertEqual(line.split("=", 1)[1].split(" "), list(m.DYNAMIC))
        self.assertIn("virtual_ab=true", text)
        self.assertIn("virtual_ab_compression_method=lz4", text)  # not delta_generator's slow gz default

    def test_delta_minor_version_is_a_delta_version(self):
        self.assertGreaterEqual(m.DELTA_MINOR_VERSION, 2)  # 0 is full-only


if __name__ == "__main__":
    unittest.main()
