#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Container-only RAM filesystem builder; /input/source.json → new /out files."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    out = Path("/out")
    if list(out.iterdir()):
        raise ValueError("Output must be empty")
    pin = Path("/input/source.json")
    if json.loads(pin.read_text())["schema"] != "openbook-ruby-migration-source/1":
        raise ValueError("Invalid source pin")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for directory in ("bin", "sbin", "usr/bin", "usr/sbin", "dev", "proc", "sys", "tmp", "run", "opt/openbook"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        copied = set()

        def binary(path):
            path = Path(path)
            dest = root / path.as_posix().lstrip("/")
            if str(path) in copied:
                return
            copied.add(str(path))
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
            dest.chmod(0o755)
            info = subprocess.run(["ldd", str(path)], text=True, capture_output=True)
            for line in info.stdout.splitlines():
                words = line.split()
                candidates = [v for v in words if v.startswith("/")]
                for dependency in candidates:
                    binary(dependency)

        binary("/bin/busybox")
        for applet in subprocess.check_output(["/bin/busybox", "--list"], text=True).splitlines():
            dest = root / "bin" / applet
            if not dest.exists():
                dest.symlink_to("busybox")
        for name in ("python3", "modprobe", "mcopy", "mdel", "fsck.fat", "efibootmgr"):
            binary(shutil.which(name))
        # mtools uses iconv for FAT names even in an otherwise ASCII tree.
        # ldd does not report these dynamically loaded conversion modules.
        for directory in ("usr/lib/x86_64-linux-gnu/gconv", "usr/lib/locale"):
            shutil.copytree(Path("/") / directory, root / directory)
        version = subprocess.check_output(["python3", "-c", "import sys; print(f'python{sys.version_info.major}.{sys.version_info.minor}')"], text=True).strip()
        shutil.copytree(Path("/usr/lib") / version, root / "usr/lib" / version,
                        ignore=shutil.ignore_patterns("__pycache__", "test", "tests", "ensurepip", "idlelib", "tkinter"))
        for extension in (root / "usr/lib" / version / "lib-dynload").glob("*.so"):
            # ldd resolves the extension's host absolute path, not the copied file.
            binary(Path("/usr/lib") / version / "lib-dynload" / extension.name)
        modules = list(Path("/lib/modules").iterdir())
        if len(modules) != 1:
            raise ValueError("Expected exactly one installed kernel")
        release = modules[0].name
        kernel = Path("/boot") / f"vmlinuz-{release}"
        shutil.copyfile(kernel, out / "kernel")
        dest_modules = root / "lib/modules" / release
        dest_modules.mkdir(parents=True)
        # Only the console/input/storage module dependency closures. Do not load
        # graphics or radio drivers; EFI console remains active during copying.
        wanted = ("nvme", "xhci_pci", "usb_storage", "uas", "usbhid", "hid_generic",
                  "atkbd", "i8042", "i2c_hid_acpi", "hid_multitouch", "hid_asus",
                  "virtio_pci", "virtio_blk", "sd_mod", "efivarfs", "ac", "battery")
        for module in wanted:
            result = subprocess.run(["modprobe", "--set-version", release, "--show-depends", module],
                                    text=True, capture_output=True)
            if result.returncode:
                raise ValueError(f"Required installer module unavailable: {module}: {result.stderr}")
            for line in result.stdout.splitlines():
                if line.startswith("insmod "):
                    src = Path(line.split()[1])
                    dest = root / src.as_posix().lstrip("/")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dest)
        for name in ("modules.builtin", "modules.builtin.modinfo", "modules.order"):
            shutil.copyfile(modules[0] / name, dest_modules / name)
        subprocess.run(["depmod", "-b", str(root), release], check=True)
        shutil.copyfile("/opt/openbook/init", root / "init")
        (root / "init").chmod(0o755)
        shutil.copyfile("/opt/openbook/migrate.py", root / "opt/openbook/migrate.py")
        shutil.copyfile(pin, root / "opt/openbook/source.json")
        # Optional laptop update/restore mode, bound to this same pinned system.
        update = Path("/input/laptop-update.json")
        if update.exists():
            record = json.loads(update.read_text())
            source = json.loads(pin.read_text())
            if (record.get("schema") != "openbook-ruby-laptop-update/1"
                    or record["new"]["build"] != source["build"]
                    or record["new"]["payload_readback"] != source["payload_readback"]):
                raise ValueError("Laptop update record does not match the source pin")
            shutil.copyfile("/opt/openbook/laptop-update.py", root / "opt/openbook/laptop-update.py")
            shutil.copyfile(update, root / "opt/openbook/laptop-update.json")
        # Optional two-slot fresh install plan, bound to this same pinned system.
        ab_plan = Path("/input/ab-install.json")
        if ab_plan.exists():
            plan = json.loads(ab_plan.read_text())
            bundle = Path("/input") / plan["bundle_file"]
            if (plan.get("schema") != "openbook-ruby-ab-install/1" or plan["bundle_file"] != "ab-bundle.bin"
                    or plan["source_pin_sha256"] != hashlib.sha256(pin.read_bytes()).hexdigest()
                    or hashlib.sha256(bundle.read_bytes()).hexdigest() != plan["bundle_sha256"]):
                raise ValueError("Two-slot plan does not match the source pin or its bundle")
            if update.exists():
                raise ValueError("A two-slot installer does not carry the single-slot laptop update")
            for path in (ab_plan, bundle):
                shutil.copyfile(path, root / "opt/openbook" / path.name)
                shutil.copyfile(path, out / path.name)
        # Stable ordering and no host ownership in the cpio. The package lock and
        # output digests identify the precise environment; timestamps are normalized.
        for path in root.rglob("*"):
            os.utime(path, (0, 0), follow_symlinks=False)
        paths = b"\0".join(str(p.relative_to(root)).encode() for p in sorted(root.rglob("*"))) + b"\0"
        archive = subprocess.run(["cpio", "--null", "-o", "--format=newc", "--owner=0:0"],
                                 cwd=root, input=paths, capture_output=True, check=True).stdout
        compressed = subprocess.run(["gzip", "-n", "-9"], input=archive, capture_output=True, check=True).stdout
        (out / "initrd.img").write_bytes(compressed)
        shutil.copyfile(pin, out / "source.json")
        if update.exists():
            shutil.copyfile(update, out / "laptop-update.json")
        versions = subprocess.check_output(["dpkg-query", "-W", "-f=${Package}\t${Version}\n"])
        (out / "package-versions.txt").write_bytes(versions)
        record = dict(schema="openbook-ruby-offline-installer/1", kernel_release=release,
                      source_pin_sha256=hashlib.sha256(pin.read_bytes()).hexdigest(),
                      files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())})
        (out / "build.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
