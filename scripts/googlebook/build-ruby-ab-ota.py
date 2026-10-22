#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build an OpenBook-signed Virtual A/B OTA payload for a Ruby A/B device.

A full update_engine payload for a release: the dynamic partition `system`
(Virtual A/B) and the static boot chain (`boot`, `init_boot`, `vendor_boot`,
`vbmeta`). update_engine applies it into the other slot — a `system_b` snapshot
in super plus the `_b` boot/vbmeta partitions — then bootsync activates that
slot and one reboot switches. The payload is signed with the OpenBook OTA key
through scripts/googlebook/sign-ota-payload.sh (the key never leaves the host)
and verified against the public certificate images install.

Runs on the host (delta_generator, openssl, the signer); writes a payload
directory, no device. The signing step refuses a container or a key under
~/anybook, so keep this on the host too.
"""
import argparse
import base64
import hashlib
import json
import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
# A full Virtual A/B payload: system is dynamic (snapshotted in super); the boot
# chain is static (written to the _b partitions).
DYNAMIC = ("system",)
STATIC = ("boot", "init_boot", "vendor_boot", "vbmeta")
MAX_TIMESTAMP = 4102444800  # 2100-01-01, so the anti-downgrade check passes


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def payload_checks(data, props, names, signature_verifies):
    """Read a signed payload back independently: header, partition set, signature, properties."""
    manifest_size = struct.unpack(">Q", data[12:20])[0] if len(data) >= 20 else 0
    manifest = data[24:24 + manifest_size]
    prop = dict(line.split("=", 1) for line in props.splitlines() if "=" in line)
    return {
        "crau_v2": data[:4] == b"CrAU" and len(data) >= 24 and struct.unpack(">Q", data[4:12])[0] == 2,
        "all_partitions_present": all(n.encode() in manifest for n in names),
        "metadata_signature_verifies_against_cert": signature_verifies,
        "properties_match_payload": prop.get("FILE_SIZE") == str(len(data))
            and prop.get("FILE_HASH") == base64.b64encode(hashlib.sha256(data).digest()).decode(),
    }


def build(a):
    for name in (*DYNAMIC, *STATIC):
        if not (a.release / f"{name}.img").is_file():
            raise ValueError(f"missing release image {name}.img")
    a.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    group = a.group
    group_size = a.group_size
    dyn = a.out / "dynamic_partition_info.txt"
    dyn.write_text(
        f"super_partition_groups={group}\n"
        f"{group}_size={group_size}\n"
        f"{group}_partition_list={':'.join(DYNAMIC)}\n"
        "virtual_ab=true\nvirtual_ab_compression=true\n")

    names = [*DYNAMIC, *STATIC]
    parts = ":".join(str(a.release / f"{n}.img") for n in names)
    unsigned = a.out / "payload.unsigned.bin"
    subprocess.run([str(a.delta_generator), f"--new_partitions={parts}",
                    f"--partition_names={':'.join(names)}", "--major_version=2", "--minor_version=0",
                    f"--max_timestamp={MAX_TIMESTAMP}", f"--dynamic_partition_info_file={dyn}",
                    f"--out_file={unsigned}"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Sign + verify against the certificate through the audited host signer.
    signed_dir = a.out / "signed"
    subprocess.run([str(HERE / "sign-ota-payload.sh"), str(a.delta_generator), str(a.key), str(a.cert),
                    str(unsigned), str(signed_dir)], check=True, stdout=subprocess.DEVNULL)
    payload = signed_dir / "payload.bin"
    props = (signed_dir / "payload_properties.txt").read_text()

    # Independent read-back: header, partition set, VAB flag, and signature verifies against the cert.
    data = payload.read_bytes()
    cert_pub = a.out / "cert.pub.pem"
    cert_pub.write_text(subprocess.check_output(["openssl", "x509", "-in", str(a.cert), "-noout", "-pubkey"], text=True))
    verify = subprocess.run([str(a.delta_generator), f"--in_file={payload}", f"--public_key={cert_pub}"],
                            capture_output=True)
    manifest_size = struct.unpack(">Q", data[12:20])[0]
    sig_size = struct.unpack(">I", data[20:24])[0]
    checks = payload_checks(data, props, names, verify.returncode == 0)
    result = dict(schema="openbook-ruby-ab-ota/1", payload_sha256=sha(payload), payload_bytes=len(data),
                  metadata_size=manifest_size, metadata_signature_size=sig_size,
                  dynamic=list(DYNAMIC), static=list(STATIC),
                  release_image_sha256={n: sha(a.release / f"{n}.img") for n in names},
                  certificate_sha256=sha(a.cert), checks=checks, passed=all(checks.values()))
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    (a.out / "payload_properties.txt").write_text(props)
    print(json.dumps(dict(passed=result["passed"], checks=checks, payload_bytes=len(data))))
    if not result["passed"]:
        raise SystemExit("payload verification failed")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--release", type=Path, required=True, help="dir with system/boot/init_boot/vendor_boot/vbmeta .img")
    p.add_argument("--delta-generator", type=Path, required=True)
    p.add_argument("--key", type=Path, required=True, help="OpenBook OTA private key (host, 0600, outside repos)")
    p.add_argument("--cert", type=Path, required=True, help="OpenBook OTA public certificate")
    p.add_argument("--group", default="google_dynamic_partitions")
    p.add_argument("--group-size", type=int, default=12880707584)
    p.add_argument("--out", type=Path, required=True)
    build(p.parse_args())
