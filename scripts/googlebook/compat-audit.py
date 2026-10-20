#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Audit retained Ruby trees against an existing OpenBook PRODUCT_OUT.

Runs native checkvintf (including APEX fragments and kernel requirements) and
strict secilc for stock OpenBook, stock Ruby, and the proposed mixed tuple.
Also tests a tightly scoped reduction of OpenBook's debug-only policy grants.
No downloads, device writes, source edits or installation. Local output contains
extracted APEX payloads and compiled policy: do not redistribute that directory.
Only report.json and sanitized diagnostic logs are suitable for review.

This examines the supplied extracted trees; it does not attest their provenance
against the recovery disk. Pair with recovery-preflight and retained extraction
records. Even all static checks passing does not establish boot compatibility.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[2]
POLICY_PROFILE = REPO / "config/image-bases/ruby-vendor-policy.json"
PROBE_POLICY = REPO / "config/image-bases/ruby-probe.cil"
SERVICE_PROFILE = REPO / "config/image-bases/ruby-framework-services.txt"
DESKTOP_POLICY = REPO / "config/image-bases/ruby-desktop-services.cil"
PC_INIT = REPO / "config/image-bases/ruby-pc-init.rc"
ZRAM_INIT = REPO / "device/anybook/common/pc/init.openbook.zram.rc"
CAMERA_SOURCE = REPO / "device/anybook/common/pc/camera"
CAMERA_FILES = (
    "bin/hw/android.hardware.camera.provider-V1-external-service",
    "etc/init/android.hardware.camera.provider-V1-external-service.rc",
    "etc/vintf/manifest.xml",
    "etc/external_camera_config.xml",
    "etc/permissions/android.hardware.camera.external.xml",
    "lib64/android.hardware.camera.provider-V1-external-impl.so",
    "lib64/camera.device-external-impl.so",
    "etc/selinux/vendor_service_contexts",
)
PARTS = ("system", "system_ext", "product", "vendor", "odm")


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def camera_contract(vendor):
    """Fail before packaging a webcam image with a missing provider or access rule.

    VINTF, policy compilation and a guest boot still validate the native ABI and
    service startup. This only verifies the required PC integration inputs.
    """
    missing = [name for name in CAMERA_FILES if not (vendor / name).is_file()]
    if missing:
        raise ValueError(f"Rebuild the PC vendor with camera support; missing {missing}")
    manifest = ET.parse(vendor / "etc/vintf/manifest.xml").getroot()
    hals = [h for h in manifest.findall("hal") if h.findtext("name") == "android.hardware.camera.provider"]
    # assemble_vintf normalizes source <interface> entries to <fqname>.
    instances = set()
    for hal in hals:
        instances.update(e.text for e in hal.findall("fqname"))
        instances.update(f"{i.findtext('name')}/{e.text}" for i in hal.findall("interface")
                         for e in i.findall("instance"))
    if len(hals) != 1 or hals[0].get("format") != "aidl" or \
            hals[0].findtext("name") != "android.hardware.camera.provider" or \
            ([v.text for v in hals[0].findall("version")] or ["1"]) != ["1"] or \
            instances != {"ICameraProvider/external/0"}:
        raise ValueError("Unexpected external camera VINTF contract")
    config = ET.parse(vendor / "etc/external_camera_config.xml").getroot()
    ignored = config.find("Provider/ignore")
    if ignored is None or list(ignored):
        raise ValueError("PC webcam must not exclude boot-assigned video node numbers")
    rules = [line.split() for line in (vendor / "etc/ueventd.rc").read_text().splitlines()
             if line.strip().startswith("/dev/video")]
    if rules != [["/dev/video*", "0660", "root", "camera"]]:
        raise ValueError("Camera video nodes must be restricted to root:camera 0660")
    name = "android.hardware.camera.provider.ICameraProvider/external/0"
    labels = [line.split() for line in (vendor / "etc/selinux/vendor_service_contexts").read_text().splitlines()
              if line.split() and line.split()[0] == name]
    if labels != [[name, "u:object_r:hal_camera_service:s0"]]:
        raise ValueError("External camera service needs the exact hal_camera_service label")
    features = {e.get("name") for e in ET.parse(
        vendor / "etc/permissions/android.hardware.camera.external.xml").getroot().findall("feature")}
    if not {"android.hardware.camera.any", "android.hardware.camera.external"}.issubset(features):
        raise ValueError("Missing external camera framework features")
    if sha(vendor / "etc/external_camera_config.xml") != sha(CAMERA_SOURCE / "external_camera_config.xml"):
        raise ValueError("Rebuild vendor: camera configuration differs from the reviewed source")
    return {"provider": name,
            "files": {name: sha(vendor / name) for name in CAMERA_FILES},
            "video_node_access": "0660 root camera", "ignored_video_nodes": [],
            "physical_capture_validated": False}


def kernel_release(path):
    tail = b""
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            data = tail + chunk
            match = re.search(rb"Linux version ([0-9][^\x00\s]+) ", data)
            if match:
                return match[1].decode("ascii")
            tail = data[-4096:]
    raise ValueError(f"No Linux release banner in {path}")


def properties(root):
    result = {}
    for path in (root / "build.prop", root / "etc/build.prop"):
        if path.is_file():
            for line in path.read_text().splitlines():
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if any(s in k for s in ("fingerprint", "version.sdk", "version.security_patch", "api_level")):
                        result[k] = v
    return result


def reduce_policy(text, profile):
    """Remove exact grants, requiring the reviewed count. Never adds permission."""
    lines = text.splitlines(keepends=True)
    for rule in profile["remove"]:
        if not rule["statement"].startswith("(allow "):
            raise ValueError("Reduction profile may only remove allow statements")
        count = sum(line.strip() == rule["statement"] for line in lines)
        if count != rule["count"]:
            raise ValueError(f"Policy drift: expected {rule['count']} occurrences, got {count}: {rule['statement']}")
        lines = [line for line in lines if line.strip() != rule["statement"]]
    return "".join(lines)


def framework_service_contexts(vendor, ruby, profile):
    """Restore exact original labels for retained framework services, not allows."""
    def entries(text):
        return [line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    original, current = entries(ruby), entries(vendor)
    added = []
    for entry in entries(profile):
        if len(entry) != 2 or original.count(entry) != 1:
            raise ValueError("Ruby framework service label drift")
        conflicts = [item for item in current if item[0] == entry[0]]
        if conflicts and conflicts != [entry]:
            raise ValueError("Conflicting vendor service label")
        if not conflicts:
            added.append(" ".join(entry))
            current.append(entry)
    return vendor + "\n# Retained Ruby framework service labels\n" + "\n".join(added) + "\n"


def policy_inputs(maps):
    roots = {n: p / "etc/selinux" for n, p in maps.items()}
    version = (roots["vendor"] / "plat_sepolicy_vers.txt").read_text().strip()
    if not re.fullmatch(r"[0-9.]+", version):
        raise ValueError("Invalid vendor policy mapping version")
    genfs = (roots["vendor"] / "genfs_labels_version.txt").read_text().strip()
    if not genfs.isdigit():
        raise ValueError("Invalid genfs version")
    required = [roots["system"] / "plat_sepolicy.cil", roots["system"] / f"mapping/{version}.cil",
                roots["vendor"] / "plat_pub_versioned.cil", roots["vendor"] / "vendor_sepolicy.cil"]
    if int(genfs) >= 202504:
        required.append(roots["system"] / f"plat_sepolicy_genfs_{genfs}.cil")
    for path in required:
        if not path.is_file():
            raise ValueError(f"Required policy input missing: {path}")
    optional = []
    for part, names in (
        ("system", [f"mapping/{version}.compat.cil"]),
        ("system_ext", ["system_ext_sepolicy.cil", f"mapping/{version}.cil", f"mapping/{version}.compat.cil"]),
        ("product", ["product_sepolicy.cil", f"mapping/{version}.cil"]),
        ("odm", ["odm_sepolicy.cil"]),
    ):
        optional.extend(roots[part] / n for n in names if (roots[part] / n).is_file())
    return version, required + optional


def validate_desktop_policy(original, subset):
    """Only existing statements or flat attribute membership subsets may pass."""
    lines = original.splitlines()
    for line in subset.splitlines():
        if not line.strip() or line.lstrip().startswith(";"):
            continue
        members = re.fullmatch(r"\(typeattributeset (\w+) \(([\w ]+)\)\)", line)
        if members:
            prefix = f"(typeattributeset {members[1]} ("
            originals = [v for v in lines if v.startswith(prefix)]
            if len(originals) != 1 or not set(members[2].split()).issubset(
                    set(originals[0][len(prefix):-2].split())):
                raise ValueError("Ruby desktop attribute contract drift")
        elif lines.count(line) != 1:
            raise ValueError("Ruby desktop policy contract drift")


class Audit:
    def __init__(self, args):
        self.a = args
        self.aliases = {str(args.ruby): "$RUBY", str(args.product): "$PRODUCT",
                        str(args.tools): "$TOOLS", str(args.kernel): "$KERNEL", str(args.out): "$OUT",
                        str(REPO): "$REPO"}

    def clean(self, text):
        for path, name in sorted(self.aliases.items(), key=lambda v: -len(v[0])):
            text = text.replace(path, name)
        return text

    def command(self, cmd, log, timeout=180):
        result = subprocess.run([str(v) for v in cmd], capture_output=True, text=True, timeout=timeout)
        output = self.clean(result.stdout + result.stderr)
        log.write_text(output)
        return {"exit_code": result.returncode, "passed": result.returncode == 0,
                "command": [self.clean(str(v)) for v in cmd], "log": str(log.relative_to(self.a.out))}

    def inventory(self, trees):
        files = {POLICY_PROFILE, PROBE_POLICY, SERVICE_PROFILE, ZRAM_INIT, DESKTOP_POLICY, PC_INIT,
                 self.a.ruby / "fs/system_a/system/etc/init/timberslide.rc"}
        files.update(CAMERA_SOURCE.glob("*"))
        files.update(self.a.product / "vendor" / name for name in CAMERA_FILES)
        files.update((self.a.product / "vendor/lib64").glob("*camera*.so"))
        for maps in trees:
            for root in maps.values():
                files.update(p for sub in ("etc/vintf", "etc/selinux", "apex")
                             for p in (root / sub).rglob("*") if p.is_file())
                files.update(p for p in (root / "build.prop", root / "etc/build.prop", root / "etc/ueventd.rc") if p.is_file())
        files.update((self.a.kernel / "dot_config", self.a.kernel / "linux_banner.txt",
                      self.a.ruby / "kernel/config", self.a.ruby / "kernel/vmlinux"))
        files.update(self.a.tools / n for n in ("checkvintf", "secilc", "checkfc", "deapexer", "debugfs_static", "fsck.erofs"))
        return {self.clean(str(p)): sha(p) for p in sorted(files)}

    def apexes(self, maps, out):
        """Inspect every supplied APEX; enumerate VINTF by manifest name, not filename."""
        out.mkdir()
        infos = ET.Element("apex-info-list")
        records, names = [], set()
        deapex = [self.a.tools / "deapexer", "--debugfs_path", self.a.tools / "debugfs_static",
                  "--fsckerofs_path", self.a.tools / "fsck.erofs"]
        for part, root in maps.items():
            for src in sorted((root / "apex").glob("*")):
                if not src.is_file() or src.suffix != ".apex":
                    raise ValueError(f"Unsupported APEX input (must audit explicitly): {src}")
                meta = json.loads(subprocess.check_output([*map(str, deapex), "info", str(src)], text=True))
                name = meta["name"]
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in names:
                    raise ValueError(f"Duplicate or unsafe APEX module name: {name}")
                names.add(name)
                # deapexer list does not support EROFS APEXes. Extract locally
                # with Android's own tool, then inspect the complete VINTF tree.
                dest = out / name
                result = self.command([*deapex, "extract", src, dest], out / f"{name}.extract.log")
                if not result["passed"]:
                    raise ValueError(f"APEX extraction failed: {result['log']}")
                fragments = sorted(str(p.relative_to(dest)) for p in (dest / "etc/vintf").rglob("*.xml"))
                record = {"source": f"{part}/apex/{src.name}", "sha256": sha(src), "module": name,
                          "version": meta["version"], "vintf_fragments": fragments}
                record["fragment_sha256"] = {n: sha(dest / n) for n in fragments}
                (dest / "etc/vintf").mkdir(parents=True, exist_ok=True)
                ET.SubElement(infos, "apex-info", moduleName=name, modulePath=f"/{part}/apex/{src.name}",
                              preinstalledModulePath=f"/{part}/apex/{src.name}", versionCode=str(meta["version"]),
                              versionName="", isFactory="true", isActive="true", partition=part.upper(),
                              lastUpdateMillis="0", provideSharedApexLibs="false")
                records.append(record)
        ET.ElementTree(infos).write(out / "apex-info-list.xml", encoding="utf-8", xml_declaration=True)
        return records

    def run_case(self, name, maps, apex_records, apex_roots, reduced=False):
        print(f"Checking {name} (VINTF/APEX/kernel and strict SELinux)...", flush=True)
        out = self.a.out / name
        out.mkdir()
        apex = out / "apex"
        apex.mkdir()
        infos = ET.Element("apex-info-list")
        selected = []
        for part in PARTS:
            source = "openbook" if maps[part] == self.a.product / part else "ruby"
            for record in apex_records[source]:
                if not record["source"].startswith(part + "/"):
                    continue
                module = record["module"]
                if (apex / module).exists():
                    raise ValueError(f"Duplicate active module: {module}")
                (apex / module).symlink_to(apex_roots[source] / module, target_is_directory=True)
                ET.SubElement(infos, "apex-info", moduleName=module, modulePath="/" + record["source"],
                              preinstalledModulePath="/" + record["source"], versionCode=str(record["version"]),
                              versionName="", isFactory="true", isActive="true", partition=part.upper(),
                              lastUpdateMillis="0", provideSharedApexLibs="false")
                selected.append(record["source"])
        ET.ElementTree(infos).write(apex / "apex-info-list.xml", encoding="utf-8", xml_declaration=True)
        cmd = [self.a.tools / "checkvintf", "--check-compat", "--property", "ro.product.first_api_level=37",
               "--property", "apex.all.ready=true"]
        # Stock Ruby uses its own kernel config; mixed and OpenBook use the G14 kernel.
        kroot = self.a.ruby / "kernel" if name == "ruby" else self.a.kernel
        kconfig = kroot / ("config" if name == "ruby" else "dot_config")
        release = kroot / ("vmlinux" if name == "ruby" else "linux_banner.txt")
        kversion = kernel_release(release)
        release_file = out / "kernel-release.txt"
        release_file.write_text(kversion + "\n")
        cmd += ["--kernel", f"{release_file}:{kconfig}"]
        for part, root in {**maps, "apex": apex}.items():
            cmd += ["--dirmap", f"/{part}:{root}"]
        vintf = self.command(cmd, out / "vintf.log")
        version, inputs = policy_inputs(maps)
        reductions = []
        if reduced:
            profile = json.loads(POLICY_PROFILE.read_text())
            if version != profile["mapping_version"]:
                raise ValueError("Policy reduction profile does not match vendor mapping version")
            source = maps["vendor"] / "etc/selinux/vendor_sepolicy.cil"
            changed = out / "vendor_sepolicy.cil"
            changed.write_text(reduce_policy(source.read_text(), profile))
            inputs = [changed if p == source else p for p in inputs]
            inputs.append(PROBE_POLICY)
            validate_desktop_policy((self.a.ruby / "fs/vendor_a/etc/selinux/vendor_sepolicy.cil").read_text(),
                                    DESKTOP_POLICY.read_text())
            inputs.append(DESKTOP_POLICY)
            reductions = profile["remove"]
        policy = self.command([self.a.tools / "secilc", "-m", "-M", "true", "-G", "-c", "33",
                               "-o", out / "policy.bin", "-f", "/dev/null", *inputs], out / "policy.log")
        contexts = maps["vendor"] / "etc/selinux/vendor_service_contexts"
        if reduced:
            merged = framework_service_contexts(contexts.read_text(),
                (self.a.ruby / "fs/vendor_a/etc/selinux/vendor_service_contexts").read_text(), SERVICE_PROFILE.read_text())
            contexts = out / "vendor_service_contexts"
            contexts.write_text(merged)
        services = self.command([self.a.tools / "checkfc", "-s", out / "policy.bin", contexts], out / "services.log") if policy["passed"] else None
        return {"vintf": vintf, "selinux": policy, "active_apexes": selected,
                "service_contexts": services,
                "policy_mapping": version, "removed_grants": reductions,
                "policy_inputs": {self.clean(str(p)): sha(p) for p in inputs},
                "kernel_config_sha256": sha(kconfig), "kernel_version": kversion,
                "static_checks_passed": vintf["passed"] and policy["passed"] and services["passed"]}

    def run(self):
        a = self.a
        camera = camera_contract(a.product / "vendor")
        empty = a.out / "empty"
        empty.mkdir()
        ruby = {"system": a.ruby / "fs/system_a/system", "system_ext": a.ruby / "fs/system_ext_a",
                "product": a.ruby / "fs/product_a", "vendor": a.ruby / "fs/vendor_a", "odm": empty}
        openbook = {n: a.product / n if (a.product / n).is_dir() else empty for n in PARTS}
        for maps in (ruby, openbook):
            for n in PARTS[:-1]:
                if not (maps[n] / "etc").is_dir():
                    raise ValueError(f"Missing {n} tree: {maps[n]}")
        before = self.inventory((ruby, openbook))
        apex_roots = {n: a.out / f"{n}-apex" for n in ("ruby", "openbook")}
        apex_records = {n: self.apexes(m, apex_roots[n]) for n, m in (("ruby", ruby), ("openbook", openbook))}
        hybrid = {**ruby, "vendor": openbook["vendor"], "odm": openbook["odm"]}
        report = {"schema": "openbook-googlebook-compat-audit/1", "installable": False,
                  "camera": camera,
                  "scope": "Static local-tree checks; no boot, signature trust, runtime ABI or licensing assertion",
                  "tools": {n: sha(a.tools / n) for n in ("checkvintf", "secilc", "deapexer")},
                  "properties": {n: {p: properties(root) for p, root in m.items()} for n, m in (("ruby", ruby), ("openbook", openbook))},
                  "apexes": apex_records, "cases": {}}
        for name, maps, reduced in (("openbook", openbook, False), ("ruby", ruby, False),
                                     ("hybrid", hybrid, False), ("hybrid-reduced", hybrid, True)):
            report["cases"][name] = self.run_case(name, maps, apex_records, apex_roots, reduced)
            (a.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        report["input_inventory"] = before
        report["inputs_unchanged"] = before == self.inventory((ruby, openbook))
        (a.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({n: {k: c[k]["passed"] for k in ("vintf", "selinux")} for n, c in report["cases"].items()}, indent=2))
        return 0 if report["inputs_unchanged"] and all(report["cases"][n]["static_checks_passed"]
                                                    for n in ("ruby", "openbook", "hybrid-reduced")) else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("ruby", "product", "tools", "kernel", "out"):
        p.add_argument("--" + n, required=True, type=Path)
    a = p.parse_args()
    for n in ("ruby", "product", "tools", "kernel"):
        value = getattr(a, n).resolve(strict=True)
        if not value.is_dir():
            p.error(f"{n} must be a directory")
        setattr(a, n, value)
    a.out = a.out.absolute()
    if a.out.exists() or a.out.is_symlink():
        p.error("Output must be a new directory")
    for src in (a.ruby, a.product, a.tools, a.kernel):
        if a.out.resolve().is_relative_to(src):
            p.error("Output must be outside every input tree")
    a.out.mkdir(parents=True)
    return Audit(a).run()


if __name__ == "__main__":
    raise SystemExit(main())
