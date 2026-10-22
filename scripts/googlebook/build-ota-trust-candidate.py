#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replace Ruby's OTA trust anchor with an OpenBook update certificate.

update_engine checks payload metadata against /system/etc/security/otacerts.zip
before it allocates space or opens a partition. Ruby's archive holds a single
Google certificate. With an OpenBook certificate in its place, stock Google
OTAs fail that first check, while OpenBook-signed payloads still verify. App
and Mainline (APEX) updates are verified with their own keys, not this archive.

The only key input is a public certificate; no private key enters this tool.
The base is camera25 unless --base-sha256 pins another reviewed Ruby image
(for example the current release), so the certificate is a one-file layer.
--input-correction also applies RB01's libinputflinger patch to camera25. --vm-test adds a disposable harness: after boot, the stock
update_engine_client runs the reviewed test payloads, using shell Binder
grants. That image carries an experimental marker that installer packaging
refuses. Never deploy it. --stock-trust, only allowed with --vm-test, keeps
Google's archive so the same harness runs as a control.
"""
import argparse
import base64
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import re
import struct
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


b = load("builder", "build-input-candidate.py")
g = load("guard", "build-ota-guard-candidate.py")

OTACERTS = "/system/etc/security/otacerts.zip"
STOCK_OTACERTS_SHA256 = "640c923ab47c6b220263cec685de5a0deb6cdec7695742776a87719bde2d5bdb"
STOCK_ENTRY = "projects/chromeos-release-bot/locations/us/keyRings/RubyMPKeys/releasekey.x509.pem"
# update_engine reads every archive entry whose name ends in x509.pem.
ENTRY = "openbook/releasekey.x509.pem"
TEST_DIR = "/system/etc/openbook-ota-test"
CASES = ("foreign-static", "openbook-static", "openbook-vab")

# Disposable A/B apply harness: a one-shot that stages the OpenBook-signed payload
# from a second drive into /data/ota_package (where real OTAs live, so the
# ota_package_file label is correct) and applies it through the stock
# update_engine_client. The boot HAL then runs bootsync activate on the target
# slot. VM only; never deployed.
APPLY_SERVICE = """
# Disposable VM only: apply the OpenBook-signed A/B OTA payload.
# init mounts the payload drive with the ota_package_file label (so update_engine
# may read it) and starts the driver as shell, which the trust harness already
# proved can drive update_engine_client. No staging copy, no shell mount.
service openbook.ota-apply /system/bin/sh /system/etc/openbook-ota-test/apply.sh
    user shell
    group shell system log readproc
    seclabel u:r:shell:s0
    console ttyS0
    disabled
    oneshot

on property:sys.boot_completed=1
    mkdir /mnt/otapayload 0771 root system
    # NVMe instance numbers follow probe completion, not PCI slot order (seen both ways), so try both.
    # Only the payload drive (a bare ext4) mounts: the system disk is in use and is not ext4.
    mount ext4 /dev/block/nvme0n1 /mnt/otapayload ro context=u:object_r:ota_package_file:s0
    mount ext4 /dev/block/nvme1n1 /mnt/otapayload ro context=u:object_r:ota_package_file:s0
    start openbook.ota-apply
"""

APPLY_POLICY = """
; Disposable VM apply harness only: let init label the payload drive ota_package_file
; via the context= mount option, so update_engine may read the payload.
; The full documented permission set for an `-o context=` ext4 mount, so there is
; no run-by-run denial chase: the mounting domain (init) needs the filesystem
; mount/relabel perms to the target context, and the context type must associate.
(allow init ota_package_file (filesystem (mount remount unmount relabelfrom relabelto getattr)))
(allow ota_package_file ota_package_file (filesystem (associate)))
; The shell driver reads the payload headers and hashes the payload on that drive.
(allow shell ota_package_file (dir (search getattr open read)))
(allow shell ota_package_file (file (read open getattr)))
"""

# Production: the owner's OTA path. The owner's paired debugging shell (adb) may drive the stock
# update_engine, which streams the payload over HTTP from the owner's build host, the standard A/B delivery:
# no staging file on the device, and no access to /data/local/tmp (which AOSP forbids other domains to open).
# update_engine still installs only payloads signed for the installed otacerts (the OpenBook certificate), so
# this adds a delivery path, not a trust path. Delivery: scripts/googlebook/g14-ota.sh.
OWNER_OTA_POLICY = """
; OpenBook owner OTA path (production): adb shell may drive update_engine; it streams the payload over HTTP.
(allow shell update_engine (binder (call transfer)))
(allow update_engine shell (binder (call transfer)))
(allow shell update_engine (fd (use)))
(allow update_engine shell (fd (use)))
"""
OWNER_OTA_SCOPE = ("production owner OTA path: adb shell may drive update_engine, which streams the payload "
                   "over HTTP from the owner's host; installs still require the OpenBook signature")
OWNER_VM_URL = "http://10.0.2.2:8090/payload.bin"  # the VM rehearsal's host, over QEMU user networking

APPLY_SCRIPT = """# Disposable VM only: apply the OpenBook-signed A/B OTA payload from the mounted drive.
DONE=/data/local/tmp/openbook-ota-apply.done
[ -e $DONE ] && exit 0
touch $DONE
say() { echo "OTAAPPLY $*"; }
waited=0
until logcat -d -b main -s update_engine:I | grep -q "Terminating cleanup previous update" || [ $waited -ge 300 ]; do
  sleep 5; waited=$((waited + 5))
done
say idle waited=${waited}s slot=$(getprop ro.boot.slot_suffix) vab=$(getprop ro.virtual_ab.enabled)
say otacerts=$(sha256sum /system/etc/security/otacerts.zip | cut -d' ' -f1)
say payload=$(sha256sum /mnt/otapayload/payload.bin | cut -d' ' -f1)
# update_engine_client expects newline-separated key=value headers (not comma-joined).
timeout 14400 update_engine_client --update --follow \\
  --payload=file:///mnt/otapayload/payload.bin \\
  --headers="$(cat /mnt/otapayload/payload_properties.txt)"; rc=$?; say update exit=$rc
logcat -d -b main -b system -s update_engine:V update_engine_client:V bootsync:V | sed 's/^/OTALOG /'
say end
# As the system updater does after UPDATED_NEED_REBOOT: an orderly reboot (shell holds REBOOT).
[ $rc -eq 0 ] && { sleep 5; svc power reboot; }
"""

# Owner mode (VM rehearsal of OWNER_OTA_POLICY): update_engine streams the payload over HTTP from the
# rehearsal's host, as on the laptop; only the headers come from the payload drive.
OWNER_APPLY_SCRIPT = (APPLY_SCRIPT
    .replace("timeout 14400 update_engine_client",
             "n=0; until ip -4 addr 2>/dev/null | grep -q 'inet 10\\.0\\.2\\.' || [ $n -ge 300 ]; do sleep 5; "
             "n=$((n + 5)); done; say network=$(ip -4 addr 2>/dev/null | grep -o 'inet 10\\.0\\.2\\.[0-9]*') "
             f"waited=${{n}}s url={OWNER_VM_URL}\ntimeout 14400 update_engine_client", 1)
    .replace("--payload=file:///mnt/otapayload/payload.bin", f"--payload={OWNER_VM_URL}"))


TEST_SERVICE = """
# Disposable VM only: stock update_engine_client against reviewed test payloads.
service openbook.ota-trust-test /system/bin/sh /system/etc/openbook-ota-test/run.sh
    user shell
    group shell system log readproc
    seclabel u:r:shell:s0
    console ttyS0
    disabled
    oneshot

on property:sys.boot_completed=1
    start openbook.ota-trust-test
"""

TEST_SCRIPT = """# Disposable VM only: stock update_engine_client against reviewed test payloads.
# Once per boot: a system_server restart sets sys.boot_completed again.
DONE=/data/local/tmp/openbook-ota-trust.done
[ -e $DONE ] && exit 0
touch $DONE
D=/system/etc/openbook-ota-test
say() { echo "OTATRUST $*"; }
# update_engine refuses requests while its boot-time cleanup runs.
waited=0
until logcat -d -b main -s update_engine:I | grep -q "Terminating cleanup previous update" || [ $waited -ge 300 ]; do
  sleep 5; waited=$((waited + 5))
done
say idle waited=${waited}s
say begin otacerts=$(sha256sum /system/etc/security/otacerts.zip | cut -d' ' -f1)
say props slot=$(getprop ro.boot.slot_suffix) secure=$(getprop ro.secure) vab=$(getprop ro.virtual_ab.enabled)
for c in CASES; do
  update_engine_client --verify --metadata=$D/$c.metadata; say verify $c exit=$?
  update_engine_client --allocate --metadata=$D/$c.metadata --headers="$(cat $D/$c.headers)"; say allocate $c exit=$?
  timeout 180 update_engine_client --update --follow --payload=file://$D/$c.payload \\
    --headers="$(cat $D/$c.headers)"; say update $c exit=$?
done
logcat -d -b main -b system -s update_engine:V update_engine_client:V | sed 's/^/OTALOG /'
say end
""".replace("CASES", " ".join(CASES))


def certificate(tools_openssl, path, expected_sha256):
    """One public RSA certificate, pinned by file hash; refuses any private key material."""
    data = b.p.regular(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("Certificate differs from supplied SHA-256")
    if data.count(b"-----BEGIN CERTIFICATE-----") != 1 or b"PRIVATE KEY" in data:
        raise ValueError("Expected exactly one PEM certificate and no key material")
    text = subprocess.check_output([tools_openssl, "x509", "-in", str(path), "-noout", "-text"], text=True)
    bits = re.search(r"Public-Key: \((\d+) bit\)", text)
    if "rsaEncryption" not in text or not bits or int(bits[1]) not in (2048, 4096):
        raise ValueError("Expected an RSA-2048 or RSA-4096 certificate")
    der = subprocess.check_output([tools_openssl, "x509", "-in", str(path), "-outform", "DER"])
    subject = subprocess.check_output([tools_openssl, "x509", "-in", str(path), "-noout", "-subject",
                                       "-nameopt", "RFC2253"], text=True).strip().removeprefix("subject=")
    return data, dict(certificate_sha256=hashlib.sha256(data).hexdigest(),
                      der_sha256=hashlib.sha256(der).hexdigest(), subject=subject, rsa_bits=int(bits[1]))


def archive(certificate_pem):
    """Deterministic stored zip with one entry, matching the stock archive's form."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as z:
        info = zipfile.ZipInfo(ENTRY, date_time=(2009, 1, 1, 0, 0, 0))
        info.external_attr = 0o100644 << 16
        info.create_system = 3
        z.writestr(info, certificate_pem)
    return buffer.getvalue()


def test_payloads(directory):
    """Full payload, metadata prefix and headers per case, checked against their properties."""
    files, record = {}, {}
    for case in CASES:
        payload = b.p.regular(directory / f"{case}.bin").read_bytes()
        headers = b.p.regular(directory / f"{case}.properties").read_text()
        if payload[:4] != b"CrAU" or struct.unpack(">Q", payload[4:12])[0] != 2:
            raise ValueError(f"{case}: not a major-version-2 payload")
        manifest_size, = struct.unpack(">Q", payload[12:20])
        signature_size, = struct.unpack(">I", payload[20:24])
        metadata_size = 24 + manifest_size
        expected = {
            "FILE_HASH": base64.b64encode(hashlib.sha256(payload).digest()).decode(),
            "FILE_SIZE": str(len(payload)),
            "METADATA_HASH": base64.b64encode(hashlib.sha256(payload[:metadata_size]).digest()).decode(),
            "METADATA_SIZE": str(metadata_size),
        }
        if headers != "".join(f"{k}={v}\n" for k, v in expected.items()):
            raise ValueError(f"{case}: properties do not describe this payload")
        files[f"{TEST_DIR}/{case}.payload"] = payload
        files[f"{TEST_DIR}/{case}.metadata"] = payload[:metadata_size + signature_size]
        files[f"{TEST_DIR}/{case}.headers"] = headers.encode()
        record[case] = dict(payload_sha256=hashlib.sha256(payload).hexdigest(),
                            metadata_size=metadata_size, metadata_signature_size=signature_size)
    return files, record


def build(a):
    if a.stock_trust and not a.vm_test:
        raise ValueError("--stock-trust is a VM-test control only")
    if a.stock_trust == bool(a.cert):
        raise ValueError("Supply --cert, or --stock-trust for the control")
    if getattr(a, "owner_ota_policy", False) and a.vm_test:
        raise ValueError("--owner-ota-policy is proven with --apply-from-drive, not the trust harness")
    if getattr(a, 'apply_from_drive', False) and a.vm_test:
        raise ValueError("--apply-from-drive and --vm-test are different VM harnesses; pick one")
    if bool(a.vm_test) != bool(getattr(a, "vm_test_signer", None)):
        raise ValueError("--vm-test needs --vm-test-signer, the certificate of the openbook-* test payloads")
    replacement, cert_record = None, None
    if a.cert:
        pem, cert_record = certificate("openssl", a.cert, a.cert_sha256)
        replacement = archive(pem)
    trusted = []
    if a.vm_test and replacement and b.p.regular(a.vm_test_signer).read_bytes() == pem:
        trusted = [c for c in CASES if c.startswith("openbook-")]

    def transform(source):
        stock = source / OTACERTS.lstrip("/")
        if b.p.h.audit.sha(stock) != STOCK_OTACERTS_SHA256:
            raise ValueError("Unrecognized stock OTA trust archive")
        with zipfile.ZipFile(stock) as z:
            if z.namelist() != [STOCK_ENTRY]:
                raise ValueError("Unexpected stock OTA trust entries")
        replacements, annotations, additions = {}, {}, {}
        if replacement:
            replacements[OTACERTS] = replacement
            annotations["ota_trust_anchor"] = dict(
                cert_record, archive_entry=ENTRY, archive_sha256=hashlib.sha256(replacement).hexdigest(),
                replaced_sha256=STOCK_OTACERTS_SHA256, replaced_entry=STOCK_ENTRY,
                stock_ota_accepted=False, hardware_validated=False)
        if a.input_correction:
            patched, offset = b.patcher.patch((source / b.TARGET.lstrip("/")).read_bytes())
            replacements[b.TARGET] = patched
            annotations["input_correction"] = dict(
                source_sha256=b.patcher.SOURCE_SHA256, output_sha256=hashlib.sha256(patched).hexdigest(),
                offset=offset, bytes=8, hardware_validated=False)
        owner = getattr(a, "owner_ota_policy", False)
        if owner and not (a.vm_test or getattr(a, "apply_from_drive", False)):
            # Production release: the owner OTA path only.
            policy_files, policy_record = g.test_policy(a, source, "", base=OWNER_OTA_POLICY, scope=OWNER_OTA_SCOPE)
            replacements.update(policy_files)
            annotations["owner_ota_path"] = dict(policy=policy_record, delivery="HTTP from the owner's host",
                                                 deployment_eligible=True, hardware_validated=False)
        if a.vm_test or getattr(a, 'apply_from_drive', False):
            rc = source / "system/etc/init/update_engine.rc"
            if rc.read_text() != g.q.STOCK_RC:
                raise ValueError("Unrecognized stock init contract")
            service = APPLY_SERVICE if getattr(a, 'apply_from_drive', False) else TEST_SERVICE
            replacements["/system/etc/init/update_engine.rc"] = (g.q.STOCK_RC + service).encode()
            if owner:
                # Production rules for the update itself; disposable rules only deliver the payload.
                policy_files, policy_record = g.test_policy(
                    a, source, APPLY_POLICY, base=OWNER_OTA_POLICY,
                    scope=OWNER_OTA_SCOPE + "; plus disposable payload-drive mount for the headers (VM only)")
            else:
                policy_files, policy_record = g.test_policy(
                    a, source, APPLY_POLICY if getattr(a, 'apply_from_drive', False) else "")
            replacements.update(policy_files)
            if getattr(a, 'apply_from_drive', False):
                # The payload and its headers ride on the drive: nothing payload-specific is baked
                # into this system, so it can be the exact source of an incremental payload.
                additions = {TEST_DIR: None,
                             f"{TEST_DIR}/apply.sh": (OWNER_APPLY_SCRIPT if owner else APPLY_SCRIPT).encode()}
                marker, payloads = "experimental_ota_apply_test", {}
            else:
                files, payloads = test_payloads(a.vm_test)
                additions = {TEST_DIR: None, f"{TEST_DIR}/run.sh": TEST_SCRIPT.encode(), **files}
                marker = "experimental_ota_trust_test"
            annotations[marker] = dict(
                deployment_eligible=False, hardware_validated=False, unattended_safe=False,
                trust="stock" if a.stock_trust else "openbook", trusted_cases=trusted, payloads=payloads,
                test_harness_policy=policy_record,
                files={n: hashlib.sha256(d).hexdigest() for n, d in {**replacements, **additions}.items()
                       if d is not None})
        return replacements, annotations, additions

    schema = ("openbook-ruby-ota-apply-test/1" if getattr(a, 'apply_from_drive', False) else
              "openbook-ruby-ota-trust-test/1" if a.vm_test else "openbook-ruby-ota-trust-candidate/1")
    b.build_system(a, transform, schema)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "tools", "inventory", "key", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--base-sha256", help="Pin of a reviewed base other than camera25")
    p.add_argument("--cert", type=Path, help="OpenBook OTA certificate (public PEM)")
    p.add_argument("--cert-sha256")
    p.add_argument("--input-correction", action="store_true", help="Also apply RB01's libinputflinger patch")
    p.add_argument("--vm-test", type=Path, help="Disposable payload directory from make-ota-test-payloads.sh")
    p.add_argument("--vm-test-signer", type=Path, help="Certificate that signed the openbook-* test payloads")
    p.add_argument("--owner-ota-policy", action="store_true",
                   help="Production: the owner's adb shell may drive update_engine, which streams the payload "
                        "over HTTP from the owner's host (installs still require the OpenBook signature)")
    p.add_argument("--apply-from-drive", action="store_true",
                   help="Disposable A/B apply harness: apply the payload (+ payload_properties.txt) on the drive")
    p.add_argument("--stock-trust", action="store_true", help="VM-test control: keep Google's archive")
    a = p.parse_args()
    if a.cert and not a.cert_sha256:
        p.error("--cert requires --cert-sha256")
    if not Path("/.dockerenv").exists():
        p.error("Use inst-docker.sh; disposable regular images only")
    os.umask(0o077)
    build(a)
