#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only native-code inventory of retained Android partition trees.

Records hashes/relative names, never extracts or publishes APK/library bytes.
Static exposure only: ZIP ABI names do not establish actual runtime loading.
APEX contents, downloaded code and later-installed packages are outside scope.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import zipfile


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def elf_machine(header):
    if len(header) < 20 or header[:4] != b"\x7fELF" or header[5] not in (1, 2):
        return None
    return struct.unpack_from("<H" if header[5] == 1 else ">H", header, 18)[0]


def inventory(root):
    apks, foreign, errors = [], [], []
    apk_count = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = str(path.relative_to(root))
        try:
            if path.suffix.lower() == ".apk":
                apk_count += 1
                with zipfile.ZipFile(path) as archive:
                    libraries = []
                    for item in archive.infolist():
                        parts = item.filename.split("/")
                        if len(parts) == 3 and parts[0] == "lib" and parts[2].endswith(".so"):
                            with archive.open(item) as stream:
                                machine = elf_machine(stream.read(64))
                            libraries.append({"name": item.filename, "elf_machine": machine})
                if libraries:
                    apks.append({"path": relative, "sha256": sha(path),
                        "abis": sorted({x["name"].split("/")[1] for x in libraries}),
                        "libraries": libraries})
            else:
                with path.open("rb") as f:
                    machine = elf_machine(f.read(64))
                if machine in (40, 183):
                    foreign.append({"path": relative, "elf_machine": machine, "sha256": sha(path)})
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            errors.append({"path": relative, "error": str(error)})
    return {"schema": "openbook-native-footprint/1", "runtime_verdict": "not_tested",
        "scope": "Retained partition trees; no APEX extraction, later-installed apps, or downloaded code",
        "apk_count": apk_count, "native_apk_count": len(apks),
        "abi_combinations": dict(Counter(",".join(x["abis"]) for x in apks)),
        "arm_only_apks": [x for x in apks if set(x["abis"]) <= {"arm64-v8a", "armeabi-v7a", "armeabi"}],
        "native_apks": apks, "external_arm_elf_files": foreign, "errors": errors}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    a = parser.parse_args()
    if not a.root.is_dir(): parser.error("root must be a retained filesystem tree")
    report = inventory(a.root)
    with a.out.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2); f.write("\n")
    print(json.dumps({k: report[k] for k in ("apk_count", "native_apk_count", "abi_combinations", "errors")}))
    raise SystemExit(bool(report["errors"]))
