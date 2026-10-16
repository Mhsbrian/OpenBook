#!/usr/bin/env python3
"""Check that system_dlkm's GKI modules are signed with the key whose certificate is built into our vmlinux.

usage: kernel-g14-sigcheck.py --dist DIST --cert signing_key.x509 --tools DIR --out OUT_PREFIX

  --dist   G14 dist: vmlinux, system_dlkm.flatten.erofs.img, bm/vendor_dlkm.img
  --cert   the module-signing certificate of the same Kleaf build (DER), from
           bazel-bin/common/kernel_x86_64/certs/signing_key.x509. Only the public certificate is read.
  --tools  Kleaf's host tools (fsck.erofs)

Checks: the certificate's DER bytes are inside vmlinux (it is the key the kernel trusts); every module in
system_dlkm carries a PKCS#7 signature whose key id is that certificate's serial; every vendor_dlkm module is
unsigned (vendor modules may then use KMI-listed symbols only, MODULE_SIG_PROTECT). Writes OUT_PREFIX.json and
OUT_PREFIX.md. Needs openssl and modinfo: the anybook-kernel image has them.
"""
import argparse
import json
import os
import re
import subprocess
import tempfile


def sh(*cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def modinfo(path, field):
    return sh("modinfo", "-F", field, path).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("dist", "cert", "tools", "out"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()

    der = open(a.cert, "rb").read()
    text = sh("openssl", "x509", "-inform", "DER", "-in", a.cert, "-noout", "-subject", "-serial",
              "-fingerprint", "-sha256", "-ext", "subjectKeyIdentifier")
    serial = re.search(r"serial=([0-9A-F]+)", text).group(1)
    skid = re.search(r"Subject Key Identifier:\s*\n\s*([0-9A-F:]+)", text).group(1).replace(":", "").lower()
    subject = re.search(r"subject=(.*)", text).group(1).strip()
    fpr = re.search(r"Fingerprint=([0-9A-F:]+)", text).group(1)
    in_vmlinux = der in open(os.path.join(a.dist, "vmlinux"), "rb").read()

    res = {"cert": {"subject": subject, "serial": serial, "skid": skid, "sha256_fingerprint": fpr,
                    "in_vmlinux": in_vmlinux}, "system_dlkm": {}, "vendor_dlkm": {}}
    problems = [] if in_vmlinux else ["the certificate is not in vmlinux"]
    with tempfile.TemporaryDirectory() as t:
        for part, img in (("system_dlkm", "system_dlkm.flatten.erofs.img"), ("vendor_dlkm", "bm/vendor_dlkm.img")):
            root = os.path.join(t, part)
            sh(os.path.join(a.tools, "fsck.erofs"), f"--extract={root}", os.path.join(a.dist, img))
            mods = sorted(os.path.join(dp, f) for dp, _, fs in os.walk(root) for f in fs if f.endswith(".ko"))
            keys, signers, unsigned = {}, set(), []
            for m in mods:
                k = modinfo(m, "sig_key").replace(":", "").upper()
                if not k:
                    unsigned.append(os.path.basename(m))
                    continue
                keys.setdefault(k, []).append(os.path.basename(m))
                signers.add(modinfo(m, "signer"))
            res[part] = {"image": img, "modules": len(mods), "signed": sum(len(v) for v in keys.values()),
                         "unsigned": len(unsigned), "sig_keys": {k: len(v) for k, v in keys.items()},
                         "signers": sorted(signers), "unsigned_modules": unsigned[:10]}
    s, v = res["system_dlkm"], res["vendor_dlkm"]
    if s["unsigned"] or set(s["sig_keys"]) != {serial}:
        problems.append(f"system_dlkm: {s['unsigned']} unsigned, keys {list(s['sig_keys'])} (want {serial})")
    if v["signed"]:
        problems.append(f"vendor_dlkm: {v['signed']} signed modules (expected none)")
    res["problems"] = problems
    res["ok"] = not problems
    json.dump(res, open(a.out + ".json", "w"), indent=1)
    md = ["# Module signing check (ANAL-198)", "",
          f"- Certificate: `{subject}`, serial `{serial}`, SKID `{skid}`, SHA-256 `{fpr}`",
          f"- Built into vmlinux (DER bytes present): {'yes' if in_vmlinux else 'NO'}",
          f"- system_dlkm (`{s['image']}`): {s['modules']} modules, {s['signed']} signed with serial "
          f"{', '.join(s['sig_keys']) or '-'} by {', '.join(s['signers']) or '-'}; {s['unsigned']} unsigned",
          f"- vendor_dlkm (`{v['image']}`): {v['modules']} modules, {v['signed']} signed, {v['unsigned']} unsigned",
          "", f"**{'OK' if not problems else 'PROBLEMS: ' + '; '.join(problems)}**"]
    open(a.out + ".md", "w").write("\n".join(md) + "\n")
    print("\n".join(md))
    raise SystemExit(0 if not problems else 1)


if __name__ == "__main__":
    main()
