#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Add OpenBook Update, the owner-visible on-laptop updater (ANAL-229), to a Ruby candidate's system.

Through the same exact-inventory reassembler as every OpenBook candidate (build-input-candidate.py),
`system` gains:
  /system/priv-app/OpenBookUpdate-v<versionCode>/OpenBookUpdate.apk   the signed app (OpenBook app key)
  /system/etc/permissions/privapp-permissions-org.openbook.update.xml  REBOOT, its only privileged permission
  /system/etc/default-permissions/default-permissions-org.openbook.update.xml   notifications from a first boot
  /system/etc/sysconfig/sysconfig-org.openbook.update.xml              power-save exemption; full users only
and these files change:
  plat_sepolicy.cil and its hash   + the openbook_update_app domain (app-sepolicy.cil), compiled with the
                                     image's exact policy inputs, neverallows included
  plat_seapp_contexts              + the line selecting that domain for the package and seinfo "openbook",
                                     checked with checkseapp against the compiled policy
  plat_mac_permissions.xml         + the OpenBook app certificate as seinfo "openbook", before </policy>
rebase-google-build.py carries all of them onto later Google builds (added paths; appended policy, file
contexts and app contexts; the inserted signer).

Fail-closed checks before anything is built:
  - every source matches its reviewed SHA-256 in device/anybook/common/updater/app-pins.json, the APK
    included (the APK is byte-reproducible: device/anybook/common/updater/app/build.sh);
  - the APK is signed (v2/v3) with exactly the committed certificate, is org.openbook.update, is not
    debuggable, and carries the engine pinned in pins.json;
  - the privileged permissions it requests, judged by the image's own permission definitions
    (framework-res.apk), are exactly the allow-list.
--vm-check adds a disposable test service that reports the app's state to the serial console and opens
it for a screenshot; such a candidate is marked not deployable.

--adapter (phase 3) also adds openbook-adapt, the AOSP AVB test key it signs with, and the firmware-safety
rules (ANAL-251) it checks every adapted release with (/system/etc/openbook/firmware-safety.json). The
finished candidate must pass those rules itself, or the laptop would hold every release: build it on a base
whose Google security chip tools are neutralised (build-safety-candidate.py). Both checks run over system,
system_ext, product and vendor, APEX init scripts included: check-firmware-safety.py, and the adapter's own
`openbook-adapt firmware-safety`, which also reads what init reads beyond *.rc.

usage: build-update-app-candidate.py --base STAGED_CANDIDATE --base-sha256 SHA --tools AOSP_HOST_BIN
                                     --inventory erofs-inventory --key AVB_KEY --apk OpenBookUpdate.apk --out DIR
Container only (inst-docker.sh); regular image files.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "device/anybook/common/updater"
spec = importlib.util.spec_from_file_location("builder", HERE / "build-input-candidate.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
g = b.load("guard", "build-ota-guard-candidate.py")
sb = b.load("safety_builder", "build-safety-candidate.py")

PACKAGE = "org.openbook.update"
SEINFO = "openbook"
# A new directory per app version: Android caches parsed packages and trusts unchanged paths and file
# times (fixed in Android images) while the build fingerprint stays Google's, so a changed APK at the same
# path could be read from the stale cache. (The builder of the next version removes this directory.)
APP_DIR_FORMAT = "/system/priv-app/OpenBookUpdate-v{version}"
PRIVAPP = "/system/etc/permissions/privapp-permissions-org.openbook.update.xml"
DEFAULTS = "/system/etc/default-permissions/default-permissions-org.openbook.update.xml"
SYSCONFIG = "/system/etc/sysconfig/sysconfig-org.openbook.update.xml"
SE = "/system/etc/selinux"
SEAPP = f"{SE}/plat_seapp_contexts"
MAC = f"{SE}/plat_mac_permissions.xml"
PINNED = {"cil": "app-sepolicy.cil", "seapp": "app-seapp_contexts", "privapp": "privapp-permissions-org.openbook.update.xml",
          "defaults": "default-permissions-org.openbook.update.xml", "sysconfig": "sysconfig-org.openbook.update.xml",
          "cert": "openbook-update.x509.pem"}
PRIVILEGED_FLAG = 0x10
# Phase 3 on the laptop: openbook-adapt (a static Go binary, pinned in adapt/adapter-pins.json) and the AVB key
# it signs the laptop's own vbmeta with. That key is AOSP's published test key, which OpenBook's images are
# signed with today (bootsync checks it); its hash is pinned so no other private key can ever ship here.
ADAPTER = "/system/bin/openbook-adapt"
ADAPTER_DIR = "/system/etc/openbook"
AVB_KEY_PATH = "/system/etc/openbook/avb/testkey_rsa4096.pem"
AOSP_AVB_TEST_KEY_SHA256 = "6a224754880a57ab9cbd308267cd157d94cf05a1c8cb851aec4090e045d24121"
SAFETY_RULES_PATH = "/system/etc/openbook/firmware-safety.json"
ADDED_EXEC_CONTEXT = "u:object_r:system_file:s0"
DERIVED_HEADER = "; Every app domain's own statements, as this image's policy gives Google's app domains (derived):\n"
SCOPE = ("OpenBook Update: a privileged app in its own domain (priv_app_all) with binder calls to update_engine; "
         "it watches update_engine and restarts into an installed update after the owner confirms")
VM_CHECK_RC = b"""# Disposable VM test only (OpenBook Update): report the app to the serial console. Never deploy.
service openbook_update_vmlog /system/bin/sh -c "logcat -G 16M; logcat -v threadtime -s OpenBookUpdate:* openbook-updater:* AndroidRuntime:E | sed 's/^/OBU_LIVE /'"
    user shell
    group shell log readproc
    seclabel u:r:shell:s0
    console ttyS0
    disabled

service openbook_update_vmcheck /system/bin/sh /system/etc/openbook-update-vmcheck.sh
    user shell
    group shell log readproc
    seclabel u:r:shell:s0
    console ttyS0
    disabled
    oneshot

# The live log from boot (it captures the app's boot work). The report waits until the base image's own
# console service (openbook.ruby.probe) has ended: its exit takes the shared console from services
# started before it.
on property:sys.boot_completed=1
    start openbook_update_vmlog

on property:sys.boot_completed=1 && property:init.svc.openbook.ruby.probe=stopped
    start openbook_update_vmcheck
"""
VM_CHECK_SH = b"""#!/system/bin/sh
# Disposable VM test only (OpenBook Update): the app's installation, domain, boot work and first screen,
# reported to the serial console (OBU_* lines; the app's own log streams as OBU_LIVE). Never deploy.
sleep 30
echo "OBU_VMCHECK begin"
echo "OBU_HSUM $(getprop ro.fw.mu.headless_system_user)"
echo "OBU_PRIVAPP_ENFORCEMENT $(getprop ro.control_privapp_permissions)"
pm list users | sed 's/^/OBU_USERS /'
owner=$(pm list users | sed -n 's/.*UserInfo{\\([1-9][0-9]*\\):.*/\\1/p' | head -1)
echo "OBU_OWNER ${owner:-none}"
echo "OBU_CURRENT $(am get-current-user)"
dumpsys package org.openbook.update | grep -E 'codePath=|versionName=|privateFlags=|android.permission.(REBOOT|POST_NOTIFICATIONS):|User [0-9]+: .*installed=' | sed 's/^ */OBU_PKG /'
dumpsys deviceidle whitelist | grep openbook | sed 's/^/OBU_IDLE /'
procs() { for p in $(pidof org.openbook.update); do echo "$1 pid=$p label=$(cat /proc/$p/attr/current 2>&1) name=org.openbook.update"; done; }
procs OBU_PS
if [ -n "$owner" ]; then
    am start -W --user "$owner" -n org.openbook.update/.ui.MainActivity | sed 's/^/OBU_START /'
    sleep 45
    procs OBU_PS2
    # The refresh OpenBook's update tooling sends; only the shell or the system may (DUMP).
    am broadcast --user "$owner" -a org.openbook.update.action.REFRESH -n org.openbook.update/.work.RefreshReceiver | sed 's/^/OBU_REFRESH /'
    sleep 10
fi
logcat -d -s OpenBookUpdate:* | sed 's/^/OBU_LOG /'
logcat -d -b all | grep 'avc:' | grep 'denied' | grep -E 'openbook_update_app|openbook.update' | sed 's/^/OBU_AVC /'
echo "OBU_VMCHECK done"
# (QEMU shows a screen only where the vendor drives the virtual display; OpenBook's drives AMD's.)
echo "OBU_SCREEN_READY"
sleep 30
"""


# The statements Android's app macros give every app domain (app_domain(), userfaultfd_use(), the
# per-domain neverallows), read from this image's own policy: those Google's app domains all share, with
# the domain's name as a placeholder. Generated attributes (base_typeattr_N) are compared by their
# expression, members sorted. OpenBook's domain gets exactly these, so it follows Google's policy as it changes.
TEMPLATE_DOMAINS = ("vmlauncher_app", "priv_app", "priv_app_36", "untrusted_app", "platform_app", "gmscore_app")
DOMAIN = "openbook_update_app"
OPERATORS = {"and", "or", "not", "xor", "all"}


def sexp(text):
    tokens = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text)
    stack = [[]]
    for t in tokens:
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(t)
    return stack[0][0] if len(stack[0]) == 1 else stack[0]


def render(node):
    return "(" + " ".join(render(c) for c in node) + ")" if isinstance(node, list) else node


def normalize(node):
    if not isinstance(node, list):
        return node
    kids = [normalize(c) for c in node]
    if kids and all(not isinstance(k, list) for k in kids) and kids[0] not in OPERATORS:
        kids = sorted(kids)
    return kids


def domain_atom(domain):
    """The domain and its per-domain types (D_userfaultfd, D_wrapfd, D_block_io_uring)."""
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(domain)}(?=(?:_userfaultfd|_wrapfd|_block_io_uring)?(?![A-Za-z0-9_]))")


def shared_app_statements(plat_text, templates=TEMPLATE_DOMAINS):
    """Sorted statements (placeholder @D@; generated attributes as {expression}) all template domains share."""
    lines = plat_text.splitlines()
    attrs = {}
    for line in lines:
        m = re.match(r"\(typeattributeset (base_typeattr_\d+) (.+)\)$", line)
        if m:
            attrs[m.group(1)] = m.group(2)
    common = None
    for d in templates:
        atom = domain_atom(d)
        found = set()
        for line in lines:
            if line.startswith(("(typeattributeset", "(typeattribute ", ";")):   # declared per instance
                continue

            def attr(m):
                expr = attrs.get(m.group(0))
                return "{" + render(normalize(sexp(atom.sub("@D@", expr)))) + "}" if expr else m.group(0)

            out = re.sub(r"base_typeattr_\d+", attr, line)
            out = atom.sub("@D@", out)
            if "@D@" in out:
                found.add(out)
        common = found if common is None else common & found
    return sorted(common or ())


def app_domain_statements(plat_text, domain=DOMAIN):
    """The shared app-domain statements instantiated for [domain], generated attributes declared."""
    shared = shared_app_statements(plat_text)
    required = {"(type @D@)", "(typetransition @D@ tmpfs file appdomain_tmpfs)",
                "(allow @D@ appdomain_tmpfs (file (read write getattr map execute)))"}
    if not required <= set(shared):
        raise ValueError("Google's app domains no longer share the expected statements; review app-sepolicy.cil")
    out, names = [], {}
    for statement in shared:
        def declare(m):
            expr = m.group(1).replace("@D@", domain)
            if expr not in names:
                names[expr] = f"{domain}_x{len(names) + 1}"
                out.append(f"(typeattribute {names[expr]})")
                out.append(f"(typeattributeset {names[expr]} {expr})")
            return names[expr]
        out.append(re.sub(r"\{(.+?\))\}", declare, statement).replace("@D@", domain))
    return out


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sources(src_dir=SRC):
    """The integration sources and the APK pin, each checked against app-pins.json."""
    pins = json.loads((src_dir / "app-pins.json").read_text())
    if pins.get("schema") != "openbook-update-app-pins/1" or set(pins["files"]) != set(PINNED.values()):
        raise ValueError("Unrecognized app pin file")
    out = {}
    for key, name in PINNED.items():
        data = (src_dir / name).read_bytes()
        if sha(data) != pins["files"][name]:
            raise ValueError(f"{name} differs from its reviewed pin in app-pins.json")
        out[key] = data
    out["apk_pin"] = pins["apk"]
    out["engine_pin"] = json.loads((src_dir / "pins.json").read_text())["files"]["openbook-updater"]
    return out


def adapter_pin(src_dir=SRC):
    pin = json.loads((src_dir / "adapt" / "adapter-pins.json").read_text())
    if pin.get("schema") != "openbook-adapter-pins/1":
        raise ValueError("Unrecognized adapter pin file")
    return pin


def adapter_additions(adapter, avb_key, pin, vm_check, rules):
    """The files that let the laptop adapt Google's releases: the pinned binary, the AOSP AVB test key and the
    firmware-safety rules it checks each adapted release with."""
    if sha(adapter) != pin["sha256"]:
        raise ValueError("openbook-adapt differs from its pin in adapt/adapter-pins.json")
    if not vm_check and not (pin.get("worktree_clean") and pin.get("reproducible_check") and pin.get("static")):
        raise ValueError("A deployable candidate needs openbook-adapt pinned from a clean, reproducible static build")
    if sha(avb_key) != AOSP_AVB_TEST_KEY_SHA256:
        raise ValueError("Only AOSP's published AVB test key may ship in the image")
    if rules != sb.check.POLICY.read_bytes():
        raise ValueError("The firmware-safety rules must be device/anybook/common/safety/firmware-safety.json")
    return {ADAPTER: (adapter, 0o755, ADDED_EXEC_CONTEXT), ADAPTER_DIR: None, f"{ADAPTER_DIR}/avb": None,
            AVB_KEY_PATH: avb_key, SAFETY_RULES_PATH: rules}


def der(pem):
    """The DER bytes of a PEM file holding exactly one certificate and nothing else."""
    import base64
    m = re.fullmatch(rb"\s*-----BEGIN CERTIFICATE-----([A-Za-z0-9+/=\s]+)-----END CERTIFICATE-----\s*", pem)
    if not m:
        raise ValueError("Expected exactly one PEM certificate")
    return base64.b64decode(b"".join(m.group(1).split()), validate=True)


def apk_signers(data):
    """DER certificates in the APK Signing Block's v2 and v3 signers (format: source.android.com, APK
    Signature Scheme v2/v3). Integrity is the pinned SHA-256; this proves which key signed the bytes."""
    eocd = data.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise ValueError("Not a ZIP archive")
    cd = struct.unpack_from("<I", data, eocd + 16)[0]
    if data[cd - 16:cd] != b"APK Sig Block 42":
        raise ValueError("The APK has no APK Signing Block (v2/v3)")
    size = struct.unpack_from("<Q", data, cd - 24)[0]
    start = cd - size - 8
    if start < 0 or struct.unpack_from("<Q", data, start)[0] != size:
        raise ValueError("Malformed APK Signing Block")
    pairs, i, blocks = data[start + 8:cd - 24], 0, {}
    while i < len(pairs):
        n = struct.unpack_from("<Q", pairs, i)[0]
        blocks[struct.unpack_from("<I", pairs, i + 8)[0]] = pairs[i + 12:i + 8 + n]
        i += 8 + n

    def items(buf):
        off = 0
        while off < len(buf):
            n = struct.unpack_from("<I", buf, off)[0]
            yield buf[off + 4:off + 4 + n]
            off += 4 + n

    def first(buf):
        return next(items(buf))

    certs = {}
    for name, block_id in (("v2", 0x7109871A), ("v3", 0xF05368C0)):
        if block_id not in blocks:
            continue
        found = set()
        for signer in items(first(blocks[block_id])):
            signed = first(signer)
            parts = items(signed)
            next(parts)                                         # digests
            found |= set(items(next(parts)))                    # certificates
        certs[name] = found
    if not certs:
        raise ValueError("The APK has no v2 or v3 signature")
    return certs


def parse_permission_levels(xmltree):
    """{permission: protectionLevel} from `aapt2 dump xmltree` of a manifest. An element's attributes
    follow its E: line, before any child element."""
    levels, tag, name, level = {}, None, None, 0

    def close():
        if tag == "permission" and name:
            levels[name] = level

    for line in xmltree.splitlines():
        element = re.match(r"\s*E: (\S+)", line)
        if element:
            close()
            tag, name, level = element.group(1), None, 0
            continue
        attr = re.match(r"\s*A: (?:\S*:)?(name|protectionLevel)\(0x[0-9a-f]+\)=(.*)$", line)
        if attr and tag == "permission":
            if attr.group(1) == "name":
                quoted = re.match(r'"([^"]+)"', attr.group(2))
                name = quoted.group(1) if quoted else None
            else:
                value = re.match(r"(?:\(type 0x[0-9a-f]+\))?(0x[0-9a-f]+|\d+)", attr.group(2))
                level = int(value.group(1), 0) if value else 0
    close()
    return levels


def framework_permissions(tools, framework_res):
    """The image's own permission definitions (framework-res.apk)."""
    out = subprocess.run([str(tools / "aapt2"), "dump", "xmltree", "--file", "AndroidManifest.xml", str(framework_res)],
                         check=True, capture_output=True, text=True).stdout
    levels = parse_permission_levels(out)
    if not levels.get("android.permission.REBOOT", 0) & PRIVILEGED_FLAG:
        raise ValueError("Could not read the image's permission definitions")
    return levels


def manifest_permissions(xmltree):
    """(requested, defined) from `aapt2 dump xmltree` of an APK manifest: every <uses-permission> and
    <uses-permission-sdk-23> name, and every <permission> the APK defines itself."""
    requested, defined, tag = set(), set(), None
    for line in xmltree.splitlines():
        element = re.match(r"\s*E: (\S+)", line)
        if element:
            tag = element.group(1)
            continue
        attr = re.match(r'\s*A: (?:\S*:)?name\(0x[0-9a-f]+\)="([^"]+)"', line)
        if attr and tag in ("uses-permission", "uses-permission-sdk-23"):
            requested.add(attr.group(1))
        elif attr and tag == "permission":
            defined.add(attr.group(1))
    return sorted(requested), sorted(defined)


def apk_facts(tools, apk_path):
    badging = subprocess.run([str(tools / "aapt2"), "dump", "badging", str(apk_path)],
                             check=True, capture_output=True, text=True).stdout
    tree = subprocess.run([str(tools / "aapt2"), "dump", "xmltree", "--file", "AndroidManifest.xml", str(apk_path)],
                          check=True, capture_output=True, text=True).stdout
    m = re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'", badging, re.M)
    if not m:
        raise ValueError("Cannot read the APK's package")
    requested, defined = manifest_permissions(tree)
    return dict(package=m.group(1), version_code=int(m.group(2)), version_name=m.group(3),
                debuggable="application-debuggable" in badging or "android:debuggable" in tree,
                shared_user="sharedUserId" in tree, requested=requested, defined=defined)


def apksigner_verify(tools, apk_path, cert_sha256):
    """Android's own signature verification (AOSP host apksigner): it verifies, with exactly one signer and
    the OpenBook certificate, through v3 (the scheme Android 9+ uses), and has no v3.1 block (no key
    rotation is expected). For minSdk 36 apksigner does not report the v2 signature it skips."""
    # The AOSP tree's own JDK (tools is <aosp>/out/host/linux-x86/bin); HOME differs inside the container.
    java = Path(os.environ.get("OPENBOOK_JDK", Path(tools).resolve().parents[3] / "prebuilts/jdk/jdk21/linux-x86/bin"))
    env = dict(os.environ, PATH=f"{java}:{os.environ.get('PATH', '')}")
    out = subprocess.run([str(tools / "apksigner"), "verify", "--min-sdk-version", "36", "-v", "--print-certs", str(apk_path)],
                         capture_output=True, text=True, env=env)
    text = out.stdout + out.stderr
    lines = [l.strip() for l in text.splitlines()]
    want = ["Verifies", "Verified using v3 scheme (APK Signature Scheme v3): true",
            "Verified using v3.1 scheme (APK Signature Scheme v3.1): false", "Number of signers: 1"]
    digests = set(re.findall(r"^(?:V[0-9.]+ )?Signer(?: #\d+)?:? certificate SHA-256 digest: ([0-9a-f]{64})$", text, re.M))
    if out.returncode != 0 or any(k not in lines for k in want) or digests != {cert_sha256}:
        raise ValueError(f"apksigner does not verify the APK as signed by the OpenBook certificate only:\n{text}")
    return lines


def check_apk(a, src, apk, framework_res):
    """The pinned APK, examined as the very bytes that were hash-checked (a copy in the output directory)."""
    if sha(apk) != src["apk_pin"]["sha256"]:
        raise ValueError("The APK differs from its reviewed pin in app-pins.json")
    cert = der(src["cert"])
    if src["apk_pin"].get("engine_sha256") != src["engine_pin"] or src["apk_pin"].get("signing_certificate_sha256") != sha(cert):
        raise ValueError("app-pins.json's engine or certificate differs from pins.json or the committed certificate")
    checked = a.out / "checked-OpenBookUpdate.apk"
    checked.write_bytes(apk)
    certs = apk_signers(apk)
    if set(certs) != {"v2", "v3"} or any(found != {cert} for found in certs.values()):
        raise ValueError("The APK is not signed (v2 and v3) with exactly the OpenBook app certificate")
    verified = apksigner_verify(a.tools, checked, sha(cert))
    with zipfile.ZipFile(checked) as z:
        if sha(z.read("assets/openbook-updater")) != src["engine_pin"]:
            raise ValueError("The APK's engine differs from its pin in pins.json")
    facts = apk_facts(a.tools, checked)
    if facts["package"] != PACKAGE or facts["debuggable"] or facts["shared_user"]:
        raise ValueError("The APK must be a release build of org.openbook.update without a shared user ID")
    if (facts["version_code"], facts["version_name"]) != (src["apk_pin"]["version_code"], src["apk_pin"]["version_name"]):
        raise ValueError("The APK's version differs from its pin")
    levels = framework_permissions(a.tools, framework_res)
    unknown = [p for p in facts["requested"] if p not in levels and p not in facts["defined"]]
    if unknown:
        raise ValueError(f"The APK requests permissions this image does not define: {unknown}")
    # This image does not enforce the privileged allow-list (ro.control_privapp_permissions is unset), so
    # this check is the gate: every signature or internal framework permission requested is allow-listed.
    special = sorted(p for p in facts["requested"] if p in levels and levels[p] & 0xF in (2, 3, 4))
    allowed = sorted(e.get("name") for e in ET.fromstring(src["privapp"]).iter("permission"))
    if special != allowed or any(not levels[p] & PRIVILEGED_FLAG for p in special):
        raise ValueError(f"Signature/privileged permissions requested {special} differ from the allow-list {allowed}")
    return dict(facts, privileged=special, signature_schemes=sorted(certs), apksigner=verified)


def xml(data, name):
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"{name} is not well-formed XML: {e}") from None


def deployable_pin(pin):
    """An APK pin from a clean, reproducible build (pin-update-app.py without --development)."""
    return pin.get("development_build") is False and pin.get("worktree_clean") is True and pin.get("reproducible_check") is True


def check_xml(src):
    """The three permission/config files: the shapes Android's SystemConfig reads, for this package only."""
    privapp = xml(src["privapp"], "privapp-permissions")
    if privapp.tag != "permissions" or [(e.tag, e.get("package")) for e in privapp] != [("privapp-permissions", PACKAGE)] \
            or any(p.tag != "permission" for p in privapp[0]):
        raise ValueError("privapp-permissions must cover only org.openbook.update")
    defaults = xml(src["defaults"], "default-permissions")
    if defaults.tag != "exceptions" or [(e.tag, e.get("package")) for e in defaults] != [("exception", PACKAGE)]:
        raise ValueError("default-permissions must cover only org.openbook.update")
    grants = [(p.get("name"), p.get("fixed")) for p in defaults.iter("permission")]
    if grants != [("android.permission.POST_NOTIFICATIONS", "false")]:
        raise ValueError("default-permissions may only pre-grant notifications, not fixed")
    config = xml(src["sysconfig"], "sysconfig")
    if config.tag != "config" or {e.get("package") for e in config} != {PACKAGE} \
            or sorted(e.tag for e in config) != ["allow-in-power-save", "install-in-user-type"]:
        raise ValueError("sysconfig must only exempt org.openbook.update from power saving and choose its users")
    users = [(u.tag, u.get("user-type")) for u in config.find("install-in-user-type")]
    if users != [("install-in", "FULL"), ("do-not-install-in", "android.os.usertype.full.GUEST")]:
        raise ValueError("OpenBook Update installs for full users, not guests, and nowhere else")


def seapp_line(line):
    pairs = [f.split("=", 1) for f in line.split()]
    if len({k for k, _ in pairs}) != len(pairs):
        raise ValueError(f"Duplicate key in the app context line: {line!r}")
    fields = dict(pairs)
    want = {"user": "_app", "seinfo": SEINFO, "isPrivApp": "true", "name": PACKAGE, "domain": "openbook_update_app",
            "type": "privapp_data_file", "levelFrom": "all"}
    if fields != want or line.count("\n") != 0:
        raise ValueError(f"Unexpected app context line: {line!r}")
    return line


def updated_seapp(current, line):
    if "openbook_update_app" in current:
        raise ValueError("plat_seapp_contexts already selects openbook_update_app")
    return (current + ("" if current.endswith("\n") or not current else "\n") + seapp_line(line) + "\n").encode()


def updated_mac_permissions(current, cert_der):
    """Insert the OpenBook signer before </policy>: a pure insertion, as rebase-google-build.py carries it."""
    if f'value="{SEINFO}"'.encode() in current or current.count(b"</policy>") != 1:
        raise ValueError("Unexpected plat_mac_permissions.xml (OpenBook signer present, or not one </policy>)")
    block = f'<signer signature="{cert_der.hex()}"><seinfo value="{SEINFO}"/></signer>'.encode()
    at = current.rindex(b"</policy>")
    updated = current[:at] + block + current[at:]
    root = ET.fromstring(updated)
    if [s.find("seinfo").get("value") for s in root.findall("signer")].count(SEINFO) != 1:
        raise ValueError("The OpenBook signer did not land in the policy")
    return updated


def build(a):
    src = sources()
    check_xml(src)
    apk = b.p.regular(a.apk).read_bytes()
    cert_der = der(src["cert"])
    line = seapp_line(src["seapp"].decode().strip())
    vm_check = getattr(a, "vm_check", False)

    if not vm_check and not deployable_pin(src["apk_pin"]):
        raise ValueError("A deployable candidate needs an APK pinned from a clean, reproducible build "
                         "(pin-update-app.py without --development); other pins are for --vm-check only")

    def transform(source):
        se = source / SE.lstrip("/")
        if b"openbook_update_app" in (se / "plat_sepolicy.cil").read_bytes():
            raise ValueError("The base policy already has the openbook_update_app domain")
        apk_record = check_apk(a, src, apk, source / "system/framework/framework-res.apk")
        derived = app_domain_statements((se / "plat_sepolicy.cil").read_text())
        rules = (src["cil"].decode().rstrip("\n") + "\n" + DERIVED_HEADER + "\n".join(derived) + "\n")
        policy_files, policy_record = g.test_policy(a, source, "", base=rules, scope=SCOPE)
        policy_record["derived_app_domain_statements"] = len(derived)
        replacements = dict(policy_files)
        replacements[SEAPP] = updated_seapp((se / "plat_seapp_contexts").read_text(), line)
        checked = a.out / "seapp-check"
        checked.mkdir()
        (checked / "plat_seapp_contexts").write_bytes(replacements[SEAPP])
        b.p.h.run(a.tools / "checkseapp", "-p", a.out / "probe-policy.bin", "-o", checked / "out",
                  checked / "plat_seapp_contexts")
        replacements[MAC] = updated_mac_permissions((se / "plat_mac_permissions.xml").read_bytes(), cert_der)
        app_dir = APP_DIR_FORMAT.format(version=apk_record["version_code"])
        additions = {app_dir: None, f"{app_dir}/OpenBookUpdate.apk": apk, PRIVAPP: src["privapp"], DEFAULTS: src["defaults"],
                     SYSCONFIG: src["sysconfig"]}
        adapter_record = None
        if getattr(a, "adapter", None):
            pin = adapter_pin()
            rules = sb.check.POLICY.read_bytes()
            additions.update(adapter_additions(b.p.regular(a.adapter).read_bytes(), b.p.regular(a.key).read_bytes(), pin,
                                               vm_check, rules))
            adapter_record = dict(sha256=pin["sha256"], go=pin.get("go"), built_from_commit=pin.get("commit"),
                                  avb_test_key_sha256=AOSP_AVB_TEST_KEY_SHA256, firmware_safety_rules_sha256=sha(rules))
        record = dict(
            deployment_eligible=not vm_check, phase=2, hardware_validated=False,
            package=PACKAGE, version_name=apk_record["version_name"], version_code=apk_record["version_code"],
            apk_sha256=sha(apk), engine_sha256=src["engine_pin"],
            signing_certificate_sha256=sha(cert_der), signature_schemes=apk_record["signature_schemes"],
            requested_permissions=apk_record["requested"], privileged_permissions=apk_record["privileged"],
            selinux=dict(domain="openbook_update_app", seinfo=SEINFO, seapp_context=line, policy=policy_record,
                         seapp_checked=True),
            added_files={n: "dir" if v is None else sha(v if isinstance(v, bytes) else v[0]) for n, v in additions.items()},
            changed_files=sorted(replacements))
        if adapter_record:
            record["adapter"] = adapter_record
        annotations = {"openbook_update_app": record}
        if vm_check:
            additions["/system/etc/init/openbook-update-vmcheck.rc"] = VM_CHECK_RC
            additions["/system/etc/openbook-update-vmcheck.sh"] = VM_CHECK_SH
            annotations["experimental_update_app_vmcheck"] = dict(
                deployment_eligible=False, scope="disposable VM report of OpenBook Update to the serial console",
                added_files={n: sha(additions[n]) for n in ("/system/etc/init/openbook-update-vmcheck.rc",
                                                             "/system/etc/openbook-update-vmcheck.sh")})
        return replacements, annotations, additions

    if getattr(a, "adapter", None):
        sb.check.load_policy()  # the rules and OpenBook's replacements match their pins
    b.build_system(a, transform, "openbook-ruby-update-app-candidate/1")
    if getattr(a, "adapter", None):
        # The adapter holds any release that fails its rules: this one must pass them.
        old = json.loads(b.p.regular(a.base / "manifest.json").read_text())
        sb.safety_check(a, old, sb.check.load_policy())
        shutil.rmtree(a.out / "safety-check")
        laptop_safety_check(a, old)


def laptop_safety_check(a, old):
    """The adapter's own check on the candidate (openbook-adapt firmware-safety, exit 8 on findings): what the
    laptop applies to every release it adapts."""
    parts = [f"system={a.out / 'rebuilt'}"] + [f"{n}={a.base / f'logical/{n}_a.img'}" for n in sb.CHECKED
                                              if n in old["logical_sha256"]]
    work = a.out / "safety-check-laptop"
    r = subprocess.run([str(b.p.regular(a.adapter)), "firmware-safety", "--rules", str(sb.check.POLICY),
                        "--fsck", str(a.tools / "fsck.erofs"), "--work", str(work),
                        "--output", str(a.out / "firmware-safety-laptop.json"), *parts],
                       env=dict(os.environ, LD_LIBRARY_PATH=str(a.tools.parent / "lib64")), capture_output=True, text=True)
    shutil.rmtree(work, ignore_errors=True)
    if r.returncode != 0:
        (a.out / "manifest.json").rename(a.out / "manifest.rejected.json")
        raise ValueError(f"The laptop's firmware-safety check failed (exit {r.returncode}): {(r.stdout + r.stderr)[-1500:]}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("base", "tools", "inventory", "key", "apk", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--base-sha256", required=True)
    p.add_argument("--vm-check", action="store_true", help="add the disposable serial-console report (not deployable)")
    p.add_argument("--adapter", type=Path, help="openbook-adapt (adapt/build.sh), pinned in adapt/adapter-pins.json: "
                   "the laptop adapts Google's releases itself (phase 3)")
    args = p.parse_args()
    if not Path("/.dockerenv").exists():
        p.error("Use inst-docker.sh; regular images only")
    os.umask(0o077)
    build(args)
