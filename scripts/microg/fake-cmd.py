#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""A stand-in for Android's /system/bin/cmd in openbook-addons' host tests (addons-test.py).

It emulates just what openbook-addons asks of PackageManager, app-ops and deviceidle, with its state in
$FAKE_PM/state.json and every call appended to $FAKE_PM/calls.jsonl. The test's "APKs" are random bytes, so
$FAKE_PM/apks.json maps each file's sha256 to the package and versionCode it stands for.
$FAKE_PM/fail.json (optional) makes a step fail: {"commit": "<package>"} or {"grant": "<permission>"}.
"""
import hashlib
import json
import os
import sys

D = os.environ["FAKE_PM"]


def load(name, default):
    try:
        with open(os.path.join(D, name)) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(st):
    with open(os.path.join(D, "state.json"), "w") as f:
        json.dump(st, f, indent=1)


def main():
    a = sys.argv[1:]
    st = load("state.json", {"installed": {}, "sessions": {}, "grants": [], "appops": [], "deviceidle": [], "next": 100})
    fail = load("fail.json", {})
    call = {"args": a}
    rc = 0
    if a[:3] == ["package", "list", "packages"]:
        pkg = a[-1]
        if pkg in st["installed"]:
            print(f"package:{pkg} versionCode:{st['installed'][pkg]}")
    elif a[:2] == ["package", "install-create"]:
        sid = str(st["next"])
        st["next"] += 1
        st["sessions"][sid] = {"flags": a[2:]}
        print(f"Success: created install session [{sid}]")
    elif a[:2] == ["package", "install-write"]:
        size, sid = int(a[3]), a[4]
        data = sys.stdin.buffer.read()
        call["stdin_bytes"] = len(data)
        call["stdin_sha256"] = hashlib.sha256(data).hexdigest()
        if sid not in st["sessions"] or len(data) != size:
            print(f"Error: wrote {len(data)} of {size} bytes")
            rc = 1
        else:
            st["sessions"][sid]["sha256"] = call["stdin_sha256"]
            print(f"Success: streamed {len(data)} bytes")
    elif a[:2] == ["package", "install-commit"]:
        s = st["sessions"].pop(a[2], None)
        apk = load("apks.json", {}).get((s or {}).get("sha256", ""))
        if not apk:
            print("Failure [INSTALL_FAILED_INVALID_APK]")
            rc = 1
        elif fail.get("commit") == apk["package"]:
            print("Failure [INSTALL_FAILED_INTERNAL_ERROR: test]")
            rc = 1
        else:
            st["installed"][apk["package"]] = apk["version_code"]
            call["installed"] = apk["package"]
            call["flags"] = s["flags"]
            print("Success")
    elif a[:2] == ["package", "install-abandon"]:
        st["sessions"].pop(a[2], None)
        print("Success")
    elif a[:2] == ["package", "grant"]:
        if fail.get("grant") == a[3] or a[2] not in st["installed"]:
            print(f"Exception occurred while executing 'grant': java.lang.SecurityException: {a[3]}")
            rc = 255
        else:
            st["grants"].append([a[2], a[3]])
    elif a[:2] == ["appops", "set"]:
        st["appops"].append(a[2:])
    elif a[:2] == ["deviceidle", "whitelist"]:
        st["deviceidle"].append(a[2])
        print(f"Added: {a[2][1:]}")
    else:
        print(f"fake-cmd: unexpected {a}")
        rc = 2
    call["rc"] = rc
    save(st)
    with open(os.path.join(D, "calls.jsonl"), "a") as f:
        f.write(json.dumps(call) + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
