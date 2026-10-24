#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""build-update-app-candidate.py: its fail-closed checks on synthetic inputs, and the committed sources."""
import importlib.util
from pathlib import Path
import struct
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("app", HERE / "build-update-app-candidate.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def lp(*items):
    return b"".join(struct.pack("<I", len(x)) + x for x in items)


def signed_apk(certs_by_scheme):
    """A minimal ZIP with an APK Signing Block holding signers with the given certificates."""
    pairs = b""
    for block_id, certs in certs_by_scheme.items():
        signed_data = lp(lp(), lp(*certs), b"\0" * 8)          # digests, certificates, (v3: sdk range)
        signer = lp(signed_data, lp(), lp(b"key"))             # signed data, signatures, public key
        value = lp(lp(signer))
        pairs += struct.pack("<QI", len(value) + 4, block_id) + value
    size = len(pairs) + 8 + 16
    block = struct.pack("<Q", size) + pairs + struct.pack("<Q", size) + b"APK Sig Block 42"
    cd = len(block)
    eocd = b"PK\x05\x06" + b"\0" * 12 + struct.pack("<I", cd) + b"\0\0"
    return block + eocd


class Checks(unittest.TestCase):
    def test_committed_sources_match_their_pins(self):
        src = m.sources()
        m.check_xml(src)
        self.assertEqual(m.seapp_line(src["seapp"].decode().strip()).split()[4], "domain=openbook_update_app")

    def test_signers_are_read_from_v2_and_v3(self):
        apk = signed_apk({0x7109871A: [b"certA"], 0xF05368C0: [b"certA"]})
        self.assertEqual(m.apk_signers(apk), {"v2": {b"certA"}, "v3": {b"certA"}})
        self.assertEqual(m.apk_signers(signed_apk({0x7109871A: [b"certA", b"certB"]})), {"v2": {b"certA", b"certB"}})
        with self.assertRaisesRegex(ValueError, "no APK Signing Block"):
            m.apk_signers(b"PK\x05\x06" + b"\0" * 12 + struct.pack("<I", 0) + b"\0\0")

    def test_permission_levels(self):
        tree = '''      E: permission (line=1)
        A: http://schemas.android.com/apk/res/android:name(0x01010003)="android.permission.REBOOT" (Raw: "x")
        A: http://schemas.android.com/apk/res/android:protectionLevel(0x01010009)=0x00000012
      E: permission (line=2)
        A: android:name(0x01010003)="android.permission.INTERNET"
        A: android:protectionLevel(0x01010009)=(type 0x11)0x1000
        E: meta-data (line=3)
          A: android:name(0x01010003)="not.a.permission"
      E: uses-permission (line=4)
        A: android:name(0x01010003)="android.permission.CAMERA"
'''
        self.assertEqual(m.parse_permission_levels(tree), {"android.permission.REBOOT": 0x12, "android.permission.INTERNET": 0x1000})

    def test_app_context_line_is_exact(self):
        good = ("user=_app seinfo=openbook isPrivApp=true name=org.openbook.update domain=openbook_update_app "
                "type=privapp_data_file levelFrom=all")
        self.assertEqual(m.seapp_line(good), good)
        for bad in (good.replace("seinfo=openbook ", ""), good.replace("levelFrom=all", "levelFrom=none"),
                    good + " extra=1", good.replace("org.openbook.update", "org.openbook.*")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                m.seapp_line(bad)
        self.assertTrue(m.updated_seapp("user=_app domain=x\n", good).endswith(good.encode() + b"\n"))
        with self.assertRaisesRegex(ValueError, "already"):
            m.updated_seapp("x domain=openbook_update_app\n", good)

    def test_signer_insertion(self):
        base = b'<?xml version="1.0"?><policy><signer signature="aa"><seinfo value="platform"/></signer></policy>'
        out = m.updated_mac_permissions(base, b"\x0b\x01")
        self.assertEqual(out, base.replace(b"</policy>", b'<signer signature="0b01"><seinfo value="openbook"/></signer></policy>'))
        with self.assertRaises(ValueError):
            m.updated_mac_permissions(out, b"\x0b\x01")                  # already present

    def test_requested_permissions_include_sdk23_requests(self):
        tree = '''N: android=http://schemas.android.com/apk/res/android (line=2)
  E: manifest (line=2)
    E: uses-permission (line=3)
      A: http://schemas.android.com/apk/res/android:name(0x01010003)="android.permission.INTERNET" (Raw: "x")
    E: uses-permission-sdk-23 (line=4)
      A: http://schemas.android.com/apk/res/android:name(0x01010003)="android.permission.INSTALL_PACKAGES" (Raw: "x")
    E: permission (line=5)
      A: http://schemas.android.com/apk/res/android:name(0x01010003)="org.openbook.update.OWN" (Raw: "x")
    E: application (line=6)
      E: activity (line=7)
        A: http://schemas.android.com/apk/res/android:name(0x01010003)="org.openbook.update.ui.MainActivity" (Raw: "x")
'''
        self.assertEqual(m.manifest_permissions(tree),
                         (["android.permission.INSTALL_PACKAGES", "android.permission.INTERNET"], ["org.openbook.update.OWN"]))

    def test_strict_parsing_of_certificate_and_context(self):
        pem = m.SRC.joinpath("openbook-update.x509.pem").read_bytes()
        self.assertEqual(len(m.der(pem)) > 100, True)
        for bad in (pem + pem, pem + b"junk", b"no certificate"):
            with self.subTest(bad=bad[-12:]), self.assertRaises(ValueError):
                m.der(bad)
        line = m.sources()["seapp"].decode().strip()
        with self.assertRaisesRegex(ValueError, "Duplicate key"):
            m.seapp_line(line + " domain=priv_app")

    def test_app_domain_statements_are_those_googles_app_domains_share(self):
        lines = []
        for d in m.TEMPLATE_DOMAINS:
            lines += [f"(type {d})", f"(type {d}_userfaultfd)", f"(typetransition {d} tmpfs file appdomain_tmpfs)",
                      f"(allow {d} appdomain_tmpfs (file (read write getattr map execute)))",
                      f"(typeattribute base_typeattr_{len(lines)})",
                      f"(typeattributeset base_typeattr_{len(lines)} (and (domain ) (not (crash_dump {d} simpleperf ))))",
                      f"(neverallow base_typeattr_{len(lines)} {d} (process (ptrace)))"]
        lines.append("(allow vmlauncher_app crosvm_exec (file (execute)))")       # one domain's own rule: not shared
        out = m.app_domain_statements("\n".join(lines) + "\n")
        self.assertIn("(typetransition openbook_update_app tmpfs file appdomain_tmpfs)", out)
        self.assertIn("(type openbook_update_app_userfaultfd)", out)
        self.assertIn("(typeattributeset openbook_update_app_x1 (and (domain) (not (openbook_update_app crash_dump simpleperf))))", out)
        self.assertIn("(neverallow openbook_update_app_x1 openbook_update_app (process (ptrace)))", out)
        self.assertEqual(sum(1 for l in out if l.startswith("(typeattribute ")), 1)   # declared once
        self.assertFalse(any("crosvm" in l for l in out))

    def test_app_domain_statements_on_the_real_policy(self):
        plat = Path.home() / "anybook/installer/work/anal229-app/probe/system/system/etc/selinux/plat_sepolicy.cil"
        if not plat.is_file():
            self.skipTest("no extracted Ruby policy on this host")
        text = plat.read_text()
        out = m.app_domain_statements(text)
        self.assertIn("(allow openbook_update_app appdomain (memfd_file (read write getattr map execute)))", out)
        # Derived for one of Google's own domains from the others, every rule is what Google gave it.
        shared = m.shared_app_statements(text, tuple(d for d in m.TEMPLATE_DOMAINS if d != "gmscore_app"))
        plain = [x.replace("@D@", "gmscore_app") for x in shared if "{" not in x]
        self.assertTrue(set(plain) <= set(text.splitlines()), set(plain) - set(text.splitlines()))

    def test_only_a_clean_reproducible_pin_is_deployable(self):
        good = dict(development_build=False, worktree_clean=True, reproducible_check=True)
        self.assertTrue(m.deployable_pin(good))
        for change in (dict(development_build=True), dict(worktree_clean=False), dict(reproducible_check=False)):
            with self.subTest(change=change):
                self.assertFalse(m.deployable_pin(dict(good, **change)))
        self.assertFalse(m.deployable_pin({}))                       # an old pin without the fields

    def test_adapter_additions_are_pinned_and_ship_only_the_aosp_test_key(self):
        import hashlib
        binary = b"\x7fELF static openbook-adapt"
        key = Path.home() / "anybook/aosp/src/external/avb/test/data/testkey_rsa4096.pem"
        if not key.is_file():
            self.skipTest("no AOSP tree here")
        pin = dict(schema="openbook-adapter-pins/1", sha256=hashlib.sha256(binary).hexdigest(), worktree_clean=True,
                   reproducible_check=True, static=True)
        rules = m.sb.check.POLICY.read_bytes()
        out = m.adapter_additions(binary, key.read_bytes(), pin, vm_check=False, rules=rules)
        self.assertEqual(out[m.ADAPTER], (binary, 0o755, m.ADDED_EXEC_CONTEXT))
        self.assertEqual(out["/system/etc/openbook/firmware-safety.json"], rules)
        with self.assertRaisesRegex(ValueError, "must be device/anybook/common/safety/firmware-safety.json"):
            m.adapter_additions(binary, key.read_bytes(), pin, vm_check=False, rules=rules.replace(b"tpm|", b""))
        self.assertIsNone(out["/system/etc/openbook"])
        self.assertIsNone(out["/system/etc/openbook/avb"])
        self.assertEqual(out[m.AVB_KEY_PATH], key.read_bytes())
        with self.assertRaisesRegex(ValueError, "differs from its pin"):
            m.adapter_additions(binary + b"x", key.read_bytes(), pin, vm_check=False, rules=rules)
        with self.assertRaisesRegex(ValueError, "clean, reproducible static build"):
            m.adapter_additions(binary, key.read_bytes(), dict(pin, reproducible_check=False), vm_check=False, rules=rules)
        m.adapter_additions(binary, key.read_bytes(), dict(pin, reproducible_check=False), vm_check=True, rules=rules)  # VM only
        with self.assertRaisesRegex(ValueError, "Only AOSP's published AVB test key"):
            m.adapter_additions(binary, b"-----BEGIN PRIVATE KEY-----another key", pin, vm_check=False, rules=rules)

    def test_tampered_config_is_refused(self):
        src = m.sources()
        for key, old, new in (("privapp", b"org.openbook.update", b"com.example.other"),
                              ("privapp", b"<privapp-permissions ", b"<other-permissions "),
                              ("defaults", b'fixed="false"', b'fixed="true"'),
                              ("sysconfig", b'user-type="FULL"', b'user-type="SYSTEM"'),
                              ("sysconfig", b'        <do-not-install-in user-type="android.os.usertype.full.GUEST" />\n', b"")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.check_xml(dict(src, **{key: src[key].replace(old, new)}))


if __name__ == "__main__":
    unittest.main()
