#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bind an offline installer to a reviewed source and add its USB boot entry.

Regular files only. `pin` uses a reviewed configured-image manifest.
`add` uses a fresh independently verified backup and preserves every non-EFI
byte. Apply the prepared output only with the existing guarded USB updater.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
INSTALLER_FILES = {"kernel", "initrd.img", "build.json", "package-versions.txt"}
INSTALLER_MENUS = {f"loader/entries/ruby-{kind}{suffix}.conf"
                   for kind in ("install", "fresh") for suffix in ("", "-serial")}


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


m = module("migrate", "migrate.py")
u = module("preserve", "preserve-update.py")


def make_pin(base, out, build, dmi):
    image = u.regular(base / "ruby-live.img")
    manifest = json.loads(u.regular(base / "manifest.json").read_text())
    m.require(u.h.audit.sha(image) == manifest["image_sha256"], "Reviewed base image checksum changed")
    m.require(not out.exists(), "New pin output required")
    out.mkdir(mode=0o700)
    fd = os.open(image, os.O_RDONLY)
    try:
        gpt = m.read_gpt(fd)
        m.require(manifest["gpt"] == [
            {k: r[k] for k in ("name", "first_lba", "last_lba", "partuuid")} for r in gpt["rows"]],
            "Reviewed manifest GPT mismatch")
        esp = out / "esp.img"
        u.live.copy_range(image, esp, *m.extent(gpt["rows"][0]))
        tree = out / "efi"; tree.mkdir()
        m.run("mcopy", "-s", "-i", esp, "::*", tree)
        names = ["ruby/kernel", "EFI/BOOT/BOOTX64.EFI"]
        names += [f"ruby/initrd-{mode}.img" for mode in m.MODES]
        # The default menu selection can change without changing any boot payload.
        # Installer menus are replaced when rebinding the installer itself.
        # Pin the Android boot entries, which migration must actually preserve.
        names += [str(p.relative_to(tree)) for p in (tree / "loader/entries").glob("*.conf")
                  if str(p.relative_to(tree)) not in INSTALLER_MENUS]
        pin = dict(schema="openbook-ruby-migration-source/1", build=build,
                   dmi_product_prefix=dmi, image_bytes=gpt["used_bytes"], gpt=manifest["gpt"],
                   entries=manifest["entries"], kernel_sha256=manifest["kernel_sha256"],
                   payload_readback={n: manifest["payload_readback"][n] for n in m.STATIC},
                   efi_sha256={n: u.h.audit.sha(tree / n) for n in names})
        m.check_source(fd, pin)
        (out / "source.json").write_text(json.dumps(pin, indent=2) + "\n")
    finally:
        os.close(fd)
    print("Pinned source system and boot files; no userdata or credentials are packaged.")


def replacement_files(tree, manifest, expected_build_sha):
    directory = tree / "ruby-installer"
    if not expected_build_sha:
        m.require(not directory.exists() and not any((tree / n).exists() for n in INSTALLER_MENUS),
                  "Installer already exists; explicit verified replacement required")
        return set()
    m.require(directory.is_dir() and {p.name for p in directory.iterdir()} == INSTALLER_FILES,
              "Unexpected existing installer file set")
    m.require(u.h.audit.sha(directory / "build.json") == expected_build_sha,
              "Existing installer identity mismatch")
    build = json.loads((directory / "build.json").read_text())
    m.require(build == manifest.get("offline_migration_installer"), "Existing installer manifest mismatch")
    for name in INSTALLER_FILES - {"build.json"}:
        m.require(u.h.audit.sha(directory / name) == build["files"][name], "Existing installer changed")
    return {f"ruby-installer/{name}" for name in INSTALLER_FILES} | INSTALLER_MENUS


def add(snapshot, snapshot_sha, base_manifest, installer, out, replace_installer_sha256=None):
    snapshot = u.regular(snapshot)
    old = json.loads(u.regular(base_manifest).read_text())
    m.require(u.h.audit.sha(snapshot) == snapshot_sha, "Snapshot checksum mismatch")
    m.require(not out.exists(), "New output required")
    pin = json.loads(u.regular(installer / "source.json").read_text())
    build = json.loads(u.regular(installer / "build.json").read_text())
    m.require(u.h.audit.sha(installer / "source.json") == build["source_pin_sha256"], "Installer/source mismatch")
    for name, sha in build["files"].items():
        m.require(Path(name).name == name and u.h.audit.sha(u.regular(installer / name)) == sha,
                  "Installer artifact changed")
    fd = os.open(snapshot, os.O_RDONLY)
    try:
        m.check_source(fd, pin)
    finally:
        os.close(fd)
    table = u.read_gpt(snapshot)
    u.verify_manifest(old, table, snapshot.stat().st_size)
    out.mkdir(mode=0o700)
    esp = out / "esp.img"
    u.live.copy_range(snapshot, esp, *u.extent(table[0]))
    m.run("fsck.fat", "-n", esp)
    before = out / "efi-before"; before.mkdir()
    m.run("mcopy", "-s", "-i", esp, "::*", before)
    replaceable = replacement_files(before, old, replace_installer_sha256)
    for name, sha in pin["efi_sha256"].items():
        m.require(u.h.audit.sha(before / name) == sha, f"Source boot file changed: {name}")
    if replaceable:
        m.run("mdeltree", "-i", esp, "::/ruby-installer")
    additions = out / "ruby-installer"; additions.mkdir()
    for name in ("kernel", "initrd.img", "build.json", "package-versions.txt"):
        shutil.copyfile(installer / name, additions / name)
    m.run("mcopy", "-s", "-i", esp, additions, "::/")
    for suffix in ("", "-serial"):
        conf = out / f"ruby-install{suffix}.conf"
        conf.write_text(
            "title Install this Googlebook USB to SSD - keep saved data" + (" (VM serial)" if suffix else "") + "\n"
            "linux /ruby-installer/kernel\ninitrd /ruby-installer/initrd.img\n"
            + ("options console=ttyS0,115200 loglevel=3\n" if suffix else "options console=tty0 loglevel=3\n"))
        m.run("mcopy", "-o", "-i", esp, conf, f"::/loader/entries/{conf.name}")
        conf = out / f"ruby-fresh{suffix}.conf"
        conf.write_text(
            "title Fresh install Googlebook to SSD - ERASE SSD DATA" + (" (VM serial)" if suffix else "") + "\n"
            "linux /ruby-installer/kernel\ninitrd /ruby-installer/initrd.img\n"
            "options openbook.install=fresh " +
            ("console=ttyS0,115200 loglevel=3\n" if suffix else "console=tty0 loglevel=3\n"))
        m.run("mcopy", "-o", "-i", esp, conf, f"::/loader/entries/{conf.name}")
    embedded = {k: v for k, v in old.items() if k not in ("image_sha256", "payload_readback", "requires_installer_rebind")}
    embedded["offline_migration_installer"] = build
    record = out / "RESEARCH.json"
    record.write_text(json.dumps(embedded, indent=2) + "\n")
    m.run("mcopy", "-o", "-i", esp, record, "::/ruby/RESEARCH.json")
    m.run("fsck.fat", "-n", esp)
    after = out / "efi-after"; after.mkdir()
    m.run("mcopy", "-s", "-i", esp, "::*", after)
    # Only the explicitly identified installer and its menus can be replaced.
    for name, sha in u.tree_hashes(before).items():
        if name not in replaceable and name != "ruby/RESEARCH.json":
            m.require(u.h.audit.sha(after / name) == sha, f"Existing EFI file changed: {name}")
    m.require((after / "ruby/RESEARCH.json").read_bytes() == record.read_bytes(), "Embedded manifest readback failed")
    for name in ("kernel", "initrd.img", "build.json", "package-versions.txt"):
        m.require(u.h.audit.sha(after / "ruby-installer" / name) == u.h.audit.sha(installer / name),
                  "Installer EFI readback failed")
    output = out / "ruby-live.img"
    m.run("cp", "--reflink=auto", "--sparse=always", snapshot, output)
    output.chmod(0o600)
    fd = os.open(output, os.O_RDWR)
    try:
        offset, length = u.extent(table[0])
        with esp.open("rb") as f:
            while data := f.read(4 * m.MIB):
                m.write_at(fd, offset, data)
                offset += len(data)
        os.fsync(fd)
    finally:
        os.close(fd)
    # Compatible with the proven apply guard. super/vbmeta writes are identical,
    # but remain included because that updater requires a coherent three-part set.
    writes = [dict(name=r["name"], offset=u.extent(r)[0], length=u.extent(r)[1],
                   sha256=u.digest_range(output, *u.extent(r))) for r in table if r["name"] in u.WRITABLE]
    protected = []
    for offset, length in u.protected_ranges(table, snapshot.stat().st_size):
        sha = u.digest_range(snapshot, offset, length)
        m.require(u.digest_range(output, offset, length) == sha, "Protected bytes changed")
        protected.append(dict(offset=offset, length=length, sha256=sha))
    for row in table[1:]:
        m.require(u.digest_range(snapshot, *u.extent(row)) == u.digest_range(output, *u.extent(row)),
                  "Non-EFI partition changed")
    m.require(u.read_gpt(output) == table and u.h.audit.sha(snapshot) == snapshot_sha,
              "Source or GPT changed")
    updated = copy.deepcopy(old)
    updated["image_sha256"] = u.h.audit.sha(output)
    updated["preserved_from_sha256"] = snapshot_sha
    updated["payload_readback"].update({r["name"]: r["sha256"] for r in writes})
    updated["offline_migration_installer"] = build
    updated.pop("requires_installer_rebind", None)
    # Verify the FINAL source, including the updated menus, against the exact
    # pin embedded in the rebuilt installer. Never ship an unusable source pin.
    fd = os.open(output, os.O_RDONLY)
    try:
        m.check_source(fd, pin)
    finally:
        os.close(fd)
    (out / "manifest.json").write_text(json.dumps(updated, indent=2) + "\n")
    plan = dict(schema="openbook-ruby-preserving-update/1", complete=True,
                backup_sha256=snapshot_sha, candidate_sha256=build["files"]["initrd.img"],
                image_sha256=updated["image_sha256"], writes=writes, protected=protected,
                sources_unchanged=True, unrelated_esp_files_unchanged=True,
                physical_device_written=False, data_unlock_verified=False,
                operation="Add offline migration boot entry; all Android partitions unchanged")
    (out / "update.json").write_text(json.dumps(plan, indent=2) + "\n")
    print("Offline migration entry added to private clone; all Android partitions unchanged.")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    pin = sub.add_parser("pin")
    pin.add_argument("--base", type=Path, required=True)
    pin.add_argument("--out", type=Path, required=True)
    pin.add_argument("--build", required=True)
    pin.add_argument("--dmi-prefix", required=True)
    attach = sub.add_parser("add")
    for name in ("snapshot", "base-manifest", "installer", "out"):
        attach.add_argument("--" + name, type=Path, required=True)
    attach.add_argument("--snapshot-sha256", required=True)
    attach.add_argument("--replace-installer-sha256", help="SHA-256 of the reviewed existing EFI installer build.json")
    args = parser.parse_args()
    if args.operation == "pin":
        make_pin(args.base, args.out, args.build, args.dmi_prefix)
    else:
        add(args.snapshot, args.snapshot_sha256, args.base_manifest, args.installer, args.out,
            args.replace_installer_sha256)


if __name__ == "__main__":
    main()
