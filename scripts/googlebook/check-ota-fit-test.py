#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit checks for check-ota-fit.py on synthetic payload manifests, against the v2 layout and the v1 one it replaced."""
import copy
import importlib.util
from pathlib import Path
import unittest


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fit = load("fit", "check-ota-fit.py")
plan = load("plan", "plan-ruby-ab.py")
MiB, GiB = plan.MiB, plan.GiB
GROUP = "google_dynamic_partitions"
CAP = plan.GOOGLE_GROUP_MAX
TODAY = {"system": 1133674496, "system_ext": 252346368, "product": 1971519488, "vendor": 164626432,
         "vendor_dlkm": 53645312, "system_dlkm": 18165760}


# --- a minimal protobuf encoder, the inverse of check-ota-fit's decoder
def varint(v):
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        out.append(b | (0x80 if v else 0))
        if not v:
            return bytes(out)


def field(num, value):
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, int):
        return varint(num << 3) + varint(value)
    if isinstance(value, str):
        value = value.encode()
    return varint(num << 3 | 2) + varint(len(value)) + value


def manifest(partitions, groups, minor=0, vabc="lz4", partial=False):
    """partitions: [(name, new, old, cow_or_None)], groups: [(name, size, [names])]"""
    out = field(12, minor)
    for name, new, old, cow in partitions:
        body = field(1, name) + field(7, field(1, new))
        if old:
            body += field(6, field(1, old))
        if cow is not None:
            body += field(19, cow)
        out += field(13, body)
    dpm = b"".join(field(1, field(1, g) + field(2, s) + b"".join(field(3, n) for n in ns)) for g, s, ns in groups)
    dpm += field(3, True) + field(4, vabc) + field(5, 2)
    out += field(15, dpm)
    if partial:
        out += field(16, True)
    return fit.parse_manifest(out)


def candidate():
    sizes = {"EFI": 256 * MiB, "misc": 4 * MiB, "boot_a": 64 * MiB, "init_boot_a": 8 * MiB,
             "vendor_boot_a": 64 * MiB, "vbmeta_a": 1 * MiB, "metadata": 64 * MiB, "super": 3520 * MiB,
             "userdata": 8 * GiB}
    gpt, lba = [], 34
    for name, size in sizes.items():
        gpt.append(dict(name=name, first_lba=lba, last_lba=lba + size // 512 - 1))
        lba += size // 512
    return dict(image_sha256="x", gpt=gpt)


V2 = plan.plan(candidate(), 1000204886016)


def v1_layout():
    """The v1 plan: 12 GiB super, no pvmfw/recovery/ota_recovery, Google-short vbmeta."""
    v1 = copy.deepcopy(V2)
    v1["partitions"] = [r for r in v1["partitions"]
                        if not r["name"].startswith(("pvmfw_", "recovery_", "ota_recovery_"))]
    for r in v1["partitions"]:
        if r["name"] == "super":
            r["length"] = 12 * GiB
    v1.pop("ota_capacity")
    return v1


def boot_chain(extra=()):
    return [("boot", 30 * MiB, 0, None), ("init_boot", 3 * MiB, 0, None), ("vendor_boot", 1 * MiB, 0, None),
            ("vbmeta", 8192, 0, None), *extra]


def full(sizes=TODAY, cow=None, extra=(), **kw):
    parts = [(n, s, 0, cow(s) if cow else None) for n, s in sizes.items()] + boot_chain(extra)
    return manifest(parts, [(GROUP, CAP, list(sizes))], **kw)


class Fit(unittest.TestCase):
    def test_small_incremental_fits(self):
        parts = [(n, s, s, s // 80) for n, s in TODAY.items()] + \
                [(n, s, s, None) for n, s, _, _ in boot_chain()]
        r = fit.check(V2, manifest(parts, [(GROUP, CAP, list(TODAY))], minor=8))
        self.assertTrue(r["fits"], r["problems"])
        self.assertEqual(r["kind"], "incremental")
        self.assertTrue(r["snapshot"]["fits_in_super"])

    def test_large_full_update_that_grows_fits_in_super(self):
        grown = dict(TODAY, system=TODAY["system"] + 3 * GiB, product=TODAY["product"] + 2 * GiB)
        r = fit.check(V2, full(grown, cow=lambda s: s), installed_sizes=TODAY)
        self.assertTrue(r["fits"], r["problems"])
        self.assertEqual(r["kind"], "full")
        self.assertEqual(r["snapshot"]["would_need_data_bytes"], 0)

    def test_worst_case_whole_group_rewrite_fits_v2_but_not_v1(self):
        # Installed slot at the group cap, new slot at the cap, every block rewritten (no COW estimate).
        whole = {n: CAP // 6 // 4096 * 4096 for n in TODAY}
        m = full(whole)
        self.assertTrue(fit.check(V2, m)["snapshot"]["fits_in_super"])
        r1 = fit.check(v1_layout(), m)
        self.assertFalse(r1["fits"])
        self.assertGreater(r1["snapshot"]["would_need_data_bytes"], 10 * GiB)  # v1 leaned on /data

    def test_google_shaped_payload_needs_v2_partitions(self):
        extra = (("pvmfw", 974848, 0, None), ("recovery", 30 * MiB, 0, None), ("ota_recovery", 100 * MiB, 0, None))
        m = full(extra=extra)
        self.assertTrue(fit.check(V2, m)["fits"])
        problems = fit.check(v1_layout(), m)["problems"]
        self.assertTrue(any("pvmfw" in p for p in problems) and any("ota_recovery" in p for p in problems))

    def test_static_image_larger_than_partition(self):
        m = full(extra=())
        m["partitions"] = [dict(p, new_size=200 * MiB) if p["name"] == "boot" else p for p in m["partitions"]]
        self.assertTrue(any(p.startswith("boot:") for p in fit.check(V2, m)["problems"]))

    def test_missing_dynamic_partition_is_refused(self):
        partial_set = {n: s for n, s in TODAY.items() if n != "vendor"}
        problems = fit.check(V2, full(partial_set))["problems"]
        self.assertTrue(any("missing from the payload" in p and "vendor" in p for p in problems))

    def test_group_overflow(self):
        m = full()
        m["groups"][0]["size"] = 1 * GiB
        self.assertTrue(any("> group size" in p for p in fit.check(V2, m)["problems"]))

    def test_format_checks(self):
        self.assertTrue(any("partial update" in p for p in fit.check(V2, full(partial=True))["problems"]))
        self.assertTrue(any("compression" in p for p in fit.check(V2, full(vabc="lzma9"))["problems"]))
        self.assertTrue(any("non-zero minor" in p for p in fit.check(V2, full(minor=8))["problems"]))


if __name__ == "__main__":
    unittest.main()
