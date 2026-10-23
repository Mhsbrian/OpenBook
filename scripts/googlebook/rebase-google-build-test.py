#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""rebase-google-build.py: the three-way property merge and the fail-closed delta checks, on synthetic trees."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rebase", HERE / "rebase-google-build.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def lines(*items):
    return [f"{x}\n" for x in items]


class Merge(unittest.TestCase):
    OLD = lines("ro.build.id=OLD", "ro.build.date=1", "a=1", "ro.dalvik.vm.native.bridge=libhoudini.so",
                "ro.berberis.is_2nd_native_bridge=true", "ro.berberis.version=16.0.0", "b=2", "c=3")
    NEW = lines("ro.build.id=NEW", "ro.build.date=2", "a=1", "ro.dalvik.vm.native.bridge=libhoudini.so",
                "ro.berberis.is_2nd_native_bridge=true", "ro.berberis.version=16.0.0", "b=2", "c=3")

    def test_openbook_edits_land_on_the_new_build(self):
        ours = lines("ro.build.id=OLD", "ro.build.date=1", "a=1", "ro.dalvik.vm.native.bridge=libberberis_arm64.so",
                     "ro.berberis.is_2nd_native_bridge=false", "b=2", "ro.berberis.flags=disable-ir-check", "c=3")
        self.assertEqual(r.merge3(self.OLD, ours, self.NEW),
                         lines("ro.build.id=NEW", "ro.build.date=2", "a=1",
                               "ro.dalvik.vm.native.bridge=libberberis_arm64.so",
                               "ro.berberis.is_2nd_native_bridge=false", "b=2",
                               "ro.berberis.flags=disable-ir-check", "c=3"))

    def test_append_at_end(self):
        self.assertEqual(r.merge3(self.OLD, self.OLD + lines("z=9"), self.NEW), self.NEW + lines("z=9"))

    def test_edit_of_a_line_google_changed_is_refused(self):
        ours = lines("ro.build.id=OURS") + self.OLD[1:]
        with self.assertRaisesRegex(ValueError, "overlaps an upstream change"):
            r.merge3(self.OLD, ours, self.NEW)

    def test_edit_next_to_a_google_change_is_refused(self):
        ours = self.OLD[:2] + lines("inserted=1") + self.OLD[2:]
        new = self.OLD[:2] + lines("a=CHANGED") + self.OLD[3:]
        with self.assertRaisesRegex(ValueError, "overlaps an upstream change"):
            r.merge3(self.OLD, ours, new)


def row(path, mode=0o100644, size=1, ctx="u:object_r:system_file:s0"):
    hexp = path.encode().hex()
    return [f"I {hexp} {mode} 0 0 1 {size} 1230768000 0",
            f"X {hexp} {b'security.selinux'.hex()} {ctx.encode().hex()}"]


class Delta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.trees = {k: t / k for k in ("old", "ours", "new")}
        files = {
            "old": {"keep": "k", "patched": "orig", "gone": "g", "build.prop": "id=OLD\nx=1\nbridge=houdini\n"},
            "ours": {"keep": "k", "patched": "OPENBOOK", "added": "new file", "build.prop": "id=OLD\nx=1\nbridge=berberis\n"},
            "new": {"keep": "k2", "patched": "orig", "gone": "g", "build.prop": "id=NEW\nx=1\nbridge=houdini\n"},
        }
        self.rows = {}
        for k, fs in files.items():
            (self.trees[k] / "system").mkdir(parents=True)
            rows = {}
            for name, text in fs.items():
                (self.trees[k] / "system" / name).write_text(text)
                rows[f"/system/{name}"] = sorted(row(f"/system/{name}", size=len(text)))
            self.rows[k] = rows
        r.MERGEABLE = {"/system/build.prop"}

    def tearDown(self):
        self.tmp.cleanup()

    def delta(self):
        return r.plan_delta(self.rows["old"], self.rows["ours"], self.rows["new"],
                            self.trees["old"], self.trees["ours"], self.trees["new"])

    def test_rebased_rows(self):
        expected, actions = self.delta()
        self.assertEqual(actions["added"], ["/system/added"])
        self.assertEqual(actions["removed"], ["/system/gone"])
        self.assertEqual(actions["changed"], ["/system/build.prop", "/system/patched"])
        merged = b"id=NEW\nx=1\nbridge=berberis\n"
        self.assertEqual(actions["merged"]["/system/build.prop"], merged)
        self.assertEqual(expected["/system/keep"], self.rows["new"]["/system/keep"])  # Google's new bytes
        self.assertEqual(expected["/system/patched"], self.rows["ours"]["/system/patched"])
        self.assertNotIn("/system/gone", expected)
        self.assertIn(f" {len(merged)} ", expected["/system/build.prop"][0])

    def test_google_changing_a_patched_file_is_refused(self):
        (self.trees["new"] / "system/patched").write_text("google changed it")
        with self.assertRaisesRegex(ValueError, "/system/patched: OpenBook changes it, but NEW changed it too"):
            self.delta()

    def test_google_adding_an_openbook_path_is_refused(self):
        self.rows["new"]["/system/added"] = self.rows["ours"]["/system/added"]
        with self.assertRaisesRegex(ValueError, "NEW already has it"):
            self.delta()

    def test_google_changing_a_removed_file_is_refused(self):
        (self.trees["new"] / "system/gone").write_text("changed")
        with self.assertRaisesRegex(ValueError, "OpenBook removes it, but NEW changed it"):
            self.delta()

    def test_relabelled_mergeable_file_is_refused(self):
        self.rows["new"]["/system/build.prop"] = sorted(row("/system/build.prop", size=22, ctx="u:object_r:other:s0"))
        with self.assertRaisesRegex(ValueError, "unchanged ownership, mode and labels"):
            self.delta()


if __name__ == "__main__":
    unittest.main()
