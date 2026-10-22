#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replace Ruby's OTA trust anchor with an OpenBook update certificate.

update_engine checks payload metadata against /system/etc/security/otacerts.zip
before it allocates space or opens a partition. Ruby's archive holds a single
Google certificate. With an OpenBook certificate in its place, stock Google
OTAs fail that first check, while OpenBook-signed payloads still verify. App
and Mainline (APEX) updates are verified with their own keys, not this archive.

The only key input is a public certificate; no private key enters this tool.
--input-correction also applies RB01's libinputflinger patch, reproducing
RB01's system. --vm-test adds a disposable harness: after boot, the stock
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
    replacement, cert_record = None, None
    if a.cert:
        pem, cert_record = certificate("openssl", a.cert, a.cert_sha256)
        replacement = archive(pem)

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
        if a.vm_test:
            rc = source / "system/etc/init/update_engine.rc"
            if rc.read_text() != g.q.STOCK_RC:
                raise ValueError("Unrecognized stock init contract")
            replacements["/system/etc/init/update_engine.rc"] = (g.q.STOCK_RC + TEST_SERVICE).encode()
            policy_files, policy_record = g.test_policy(a, source)
            replacements.update(policy_files)
            files, payloads = test_payloads(a.vm_test)
            additions = {TEST_DIR: None, f"{TEST_DIR}/run.sh": TEST_SCRIPT.encode(), **files}
            annotations["experimental_ota_trust_test"] = dict(
                deployment_eligible=False, hardware_validated=False, unattended_safe=False,
                trust="stock" if a.stock_trust else "openbook", payloads=payloads,
                test_harness_policy=policy_record,
                files={n: hashlib.sha256(d).hexdigest() for n, d in {**replacements, **additions}.items()
                       if d is not None})
        return replacements, annotations, additions

    schema = "openbook-ruby-ota-trust-test/1" if a.vm_test else "openbook-ruby-ota-trust-candidate/1"
    b.build_system(a, transform, schema)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "tools", "inventory", "key", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--cert", type=Path, help="OpenBook OTA certificate (public PEM)")
    p.add_argument("--cert-sha256")
    p.add_argument("--input-correction", action="store_true", help="Also apply RB01's libinputflinger patch")
    p.add_argument("--vm-test", type=Path, help="Disposable payload directory from make-ota-test-payloads.sh")
    p.add_argument("--stock-trust", action="store_true", help="VM-test control: keep Google's archive")
    a = p.parse_args()
    if a.cert and not a.cert_sha256:
        p.error("--cert requires --cert-sha256")
    if not Path("/.dockerenv").exists():
        p.error("Use inst-docker.sh; disposable regular images only")
    os.umask(0o077)
    build(a)
