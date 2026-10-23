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


class AppendMerge(unittest.TestCase):
    """OpenBook's SELinux rules and labels are appended to Google's policy files and carried by re-appending."""
    SE = "system/etc/selinux"

    def setUp(self):
        import hashlib
        self.h = hashlib
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.trees = {k: t / k for k in ("old", "ours", "new")}
        plat = {"old": b"(type a)\n", "ours": b"(type a)\n(type openbook_updater)\n", "new": b"(type a)\n(type b)\n"}
        fc = {"old": b"/system u:object_r:system_file:s0\n",
              "ours": b"/system u:object_r:system_file:s0\n/system/bin/openbook-updater u:object_r:openbook_updater_exec:s0\n",
              "new": b"/system u:object_r:system_file:s0\n/system/bin/new u:object_r:new_exec:s0\n"}
        mapping = {"old": b"(mapping 1)\n", "ours": b"(mapping 1)\n", "new": b"(mapping 2)\n"}
        self.rows = {}
        for k, tree in self.trees.items():
            se = tree / self.SE
            (se / "mapping").mkdir(parents=True)
            files = {"plat_sepolicy.cil": plat[k], "plat_file_contexts": fc[k], "mapping/202604.cil": mapping[k],
                     "plat_sepolicy_and_mapping.sha256": (hashlib.sha256(plat[k] + mapping[k]).hexdigest() + "\n").encode()}
            self.rows[k] = {}
            for name, data in files.items():
                (se / name).write_bytes(data)
                self.rows[k][f"/{self.SE}/{name}"] = sorted(row(f"/{self.SE}/{name}", size=len(data)))
        self.plat, self.mapping = plat, mapping

    def tearDown(self):
        self.tmp.cleanup()

    def delta(self):
        return r.plan_delta(self.rows["old"], self.rows["ours"], self.rows["new"], *self.trees.values())

    def test_openbook_tail_is_reappended_and_hash_recomputed(self):
        expected, actions = self.delta()
        merged = actions["merged"]
        self.assertEqual(merged[r.PLAT], b"(type a)\n(type b)\n(type openbook_updater)\n")
        self.assertTrue(merged["/system/etc/selinux/plat_file_contexts"].endswith(
            b"/system/bin/new u:object_r:new_exec:s0\n/system/bin/openbook-updater u:object_r:openbook_updater_exec:s0\n"))
        want = self.h.sha256(merged[r.PLAT] + self.mapping["new"]).hexdigest() + "\n"
        self.assertEqual(merged[r.POLICY_HASH].decode(), want)            # NEW's mapping, merged policy
        self.assertIn(f" {len(merged[r.PLAT])} ", expected[r.PLAT][0])

    def test_an_edit_that_is_not_an_append_is_refused(self):
        (self.trees["ours"] / self.SE / "plat_sepolicy.cil").write_bytes(b"(type changed)\n(type openbook_updater)\n")
        with self.assertRaisesRegex(ValueError, "not a pure append"):
            self.delta()


class InsertMerge(unittest.TestCase):
    """OpenBook's app signer is inserted before </policy> and carried onto Google's new signer list."""
    OLD = b'<?xml version="1.0"?><policy><signer signature="aa"><seinfo value="platform"/></signer></policy>'
    CERT = r.app.der((r.app.SRC / "openbook-update.x509.pem").read_bytes()).hex().encode()
    BLOCK = b'<signer signature="' + CERT + b'"><seinfo value="openbook"/></signer>'
    NEW = b'<?xml version="1.0"?><policy><signer signature="aa"><seinfo value="platform"/></signer>' \
          b'<signer signature="cc"><seinfo value="media"/></signer></policy>'

    def ours(self):
        return self.OLD.replace(b"</policy>", self.BLOCK + b"</policy>")

    def test_the_block_lands_before_the_new_marker(self):
        self.assertEqual(r.reinsert(self.OLD, self.ours(), self.NEW, b"</policy>"),
                         self.NEW.replace(b"</policy>", self.BLOCK + b"</policy>"))

    def test_other_edits_are_refused(self):
        edited = self.ours().replace(b'value="platform"', b'value="changed"')
        with self.assertRaisesRegex(ValueError, "not one block"):
            r.reinsert(self.OLD, edited, self.NEW, b"</policy>")
        elsewhere = self.OLD.replace(b"<policy>", b"<policy>" + self.BLOCK)
        with self.assertRaisesRegex(ValueError, "not one block"):
            r.reinsert(self.OLD, elsewhere, self.NEW, b"</policy>")

    def test_google_shipping_the_block_or_dropping_the_marker_is_refused(self):
        with self.assertRaisesRegex(ValueError, "already contains"):
            r.reinsert(self.OLD, self.ours(), self.NEW.replace(b"</policy>", self.BLOCK + b"</policy>"), b"</policy>")
        with self.assertRaisesRegex(ValueError, "not exactly one </policy>"):
            r.reinsert(self.OLD, self.ours(), b"<policy/>", b"</policy>")
        with self.assertRaisesRegex(ValueError, "not exactly one </policy>"):
            r.reinsert(self.OLD, self.ours(), self.NEW + b"<!-- </policy> -->", b"</policy>")

    def test_the_merged_signer_must_be_the_openbook_certificate(self):
        r.check_signers(self.NEW.replace(b"</policy>", self.BLOCK + b"</policy>"))
        with self.assertRaisesRegex(ValueError, "exactly the OpenBook certificate"):
            r.check_signers(self.NEW.replace(b"</policy>", self.BLOCK.replace(self.CERT, b"0b") + b"</policy>"))
        with self.assertRaisesRegex(ValueError, "exactly the OpenBook certificate"):
            r.check_signers(self.NEW.replace(b"</policy>", self.BLOCK * 2 + b"</policy>"))

    def test_plan_delta_carries_signer_and_app_context(self):
        se = "system/etc/selinux"
        seapp = {"old": b"user=_app domain=untrusted_app\n",
                 "ours": b"user=_app domain=untrusted_app\nuser=_app seinfo=openbook name=org.openbook.update domain=openbook_update_app\n",
                 "new": b"user=_app domain=untrusted_app\nuser=_app domain=new_app\n"}
        mac = {"old": self.OLD, "ours": self.ours(), "new": self.NEW}
        with tempfile.TemporaryDirectory() as tmp:
            trees, rows = {}, {}
            for k in ("old", "ours", "new"):
                trees[k] = Path(tmp) / k
                (trees[k] / se).mkdir(parents=True)
                rows[k] = {}
                for name, data in (("plat_seapp_contexts", seapp[k]), ("plat_mac_permissions.xml", mac[k])):
                    (trees[k] / se / name).write_bytes(data)
                    rows[k][f"/{se}/{name}"] = sorted(row(f"/{se}/{name}", size=len(data)))
            expected, actions = r.plan_delta(rows["old"], rows["ours"], rows["new"], trees["old"], trees["ours"], trees["new"])
        self.assertEqual(actions["merged"][r.SEAPP], seapp["new"] + seapp["ours"][len(seapp["old"]):])
        self.assertEqual(actions["merged"]["/system/etc/selinux/plat_mac_permissions.xml"],
                         self.NEW.replace(b"</policy>", self.BLOCK + b"</policy>"))


class AppDomain(unittest.TestCase):
    """OpenBook's app domain must keep every statement Google's app domains share in the NEW policy."""
    def policy(self, extra=""):
        lines = []
        for d in r.app.TEMPLATE_DOMAINS:
            lines += [f"(type {d})", f"(typetransition {d} tmpfs file appdomain_tmpfs)",
                      f"(allow {d} appdomain_tmpfs (file (read write getattr map execute)))"]
            if extra:
                lines.append(extra.replace("@D@", d))
        return ("\n".join(lines) + "\n").encode()

    def test_the_app_domain_block_follows_googles_app_domains(self):
        new = self.policy()
        own = "(typeattributeset appdomain (openbook_update_app))\n"
        tail = (own + r.app.DERIVED_HEADER + "\n".join(r.app.app_domain_statements(new.decode())) + "\n").encode()
        r.check_app_domain(new, new + tail)                                # exact: accepted
        newer = self.policy("(allow @D@ new_type (file (read)))")
        with self.assertRaisesRegex(ValueError, "differs"):
            r.check_app_domain(newer, newer + tail)                        # stale block: refused
        regenerated = r.rederive_app_domain(newer, tail)
        self.assertIn(b"(allow openbook_update_app new_type (file (read)))", regenerated)
        self.assertTrue(regenerated.startswith(own.encode()))              # the repository's part, verbatim
        r.check_app_domain(newer, newer + regenerated)
        # Google drops a statement from all app domains: the block drops it too.
        dropped = r.rederive_app_domain(new, regenerated)
        self.assertNotIn(b"new_type", dropped)
        r.check_app_domain(new, new + b"(type unrelated)\n")             # no OpenBook app domain: nothing to check


if __name__ == "__main__":
    unittest.main()
