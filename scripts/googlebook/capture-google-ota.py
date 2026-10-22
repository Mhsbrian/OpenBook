#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Capture the system update Google offered the G14, from the laptop's own logs (read-only).

After the owner presses Settings > System > System update > Check for update, GMS
SystemUpdate fetches the offer's payload metadata and hands it to update_engine,
which logs the request. This reads the logcat buffers over adb (no root, nothing
changed on the laptop), keeps the lines that describe the offer, and saves:

  OUT/logcat.txt    the raw buffers (private)
  OUT/offer.json    url, payload offset/size, the payload headers
                    (FILE_HASH, FILE_SIZE, METADATA_HASH, METADATA_SIZE, ...),
                    and every offer-related line (private)

OUT is created mode 0700 and the files 0600: an offer URL is the owner's, never
evidence. The printed summary redacts it to its host and file name.

usage: capture-google-ota.py --out ~/anybook/private/google-ota/<utc> [--laptop 192.168.50.11]
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ADB = os.environ.get("ADB", str(Path.home() / "anybook/android-sdk/platform-tools/adb"))
URL_RE = re.compile(r"https?://[^\s\"'<>(),]+")
APPLY_RE = re.compile(r"ApplyPayload\((?P<url>[^,\s]+),\s*(?P<offset>\d+),\s*(?P<size>\d+)\)\s*(?P<headers>.*)")
HEADER_RE = re.compile(r"\b(FILE_HASH|FILE_SIZE|METADATA_HASH|METADATA_SIZE|USER_AGENT|NETWORK_ID|SWITCH_SLOT_ON_REBOOT|"
                       r"RUN_POST_INSTALL|DISABLE_VABC)=([^\s,]+)")
OFFER_HINT = re.compile(r"update_engine|SystemUpdate|ota_package|payload_metadata|onPayloadApplicationComplete|"
                        r"ErrorCode::k|\.zip\b|ota\.googlezip|gvt1\.com|dl\.google\.com", re.I)
OTA_URL = re.compile(r"ota\.googlezip\.net|/ota[-_/]|ota-api|otapackage|/packages/ota", re.I)
BUILD_RE = re.compile(r"\b(?:[A-Z]{2}[0-9][A-Z]\.\d{6}\.\d{3}(?:\.[A-Z0-9]+)?|\d{8,9})\b")


def device(laptop):
    def listed():
        out = subprocess.run([ADB, "devices"], capture_output=True, text=True).stdout
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) == 2 and parts[1] == "device" and (
                    parts[0].startswith("adb-RUBYLIVERESEARCH-") or parts[0].startswith(laptop + ":")):
                return parts[0]
        return None
    serial = listed()
    if not serial:
        services = subprocess.run([ADB, "mdns", "services"], capture_output=True, text=True).stdout
        m = re.search(r"adb-RUBYLIVERESEARCH-\S+\s+_adb-tls-connect\._tcp\S*\s+\S+:(\d+)", services)
        if m:
            subprocess.run([ADB, "connect", f"{laptop}:{m.group(1)}"], capture_output=True)
            serial = listed()
    if not serial:
        sys.exit("the G14 is not reachable over adb")
    return serial


def parse(text):
    """The offer, from logcat text: the last ApplyPayload request (url/offset/size/headers), all offer lines."""
    lines = [l for l in text.splitlines() if OFFER_HINT.search(l)]
    offer = dict(url=None, offset=None, size=None, headers={}, urls=[], builds=[], result=None, lines=lines)
    for l in lines:
        m = APPLY_RE.search(l)
        if m and not m.group("url").startswith("file://"):
            offer.update(url=m.group("url"), offset=int(m.group("offset")), size=int(m.group("size")))
        for k, v in HEADER_RE.findall(l):
            offer["headers"][k] = v
        for u in URL_RE.findall(l):
            if u not in offer["urls"]:
                offer["urls"].append(u)
        r = re.search(r"onPayloadApplicationComplete\(ErrorCode::(k\w+)", l)
        if r:
            offer["result"] = r.group(1)
    offer["source"] = "update_engine ApplyPayload" if offer["url"] else None
    if not offer["url"]:
        # Without update_engine's request (the certificate can stop GMS earlier), accept only URLs that look
        # like OTA packages; other Google downloads (speech packs, fonts, models) are listed, never taken.
        ota = [u for u in offer["urls"] if OTA_URL.search(u)]
        if ota:
            offer.update(url=ota[-1], source="GMS log (OTA-like URL)")
    offer["other_downloads"] = [redact(u) for u in offer["urls"] if u != offer["url"]]
    offer["builds"] = sorted({b for l in lines for b in BUILD_RE.findall(l)})
    return offer


def redact(url):
    if not url:
        return None
    m = re.match(r"(https?://[^/]+)/.*?([^/?]*)(\?.*)?$", url)
    return f"{m.group(1)}/…/{m.group(2)}" if m else "<url>"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--laptop", default="192.168.50.11")
    a = p.parse_args()
    os.umask(0o077)
    a.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    serial = device(a.laptop)
    text = subprocess.run([ADB, "-s", serial, "shell", "logcat", "-d", "-b", "main", "-b", "system", "-b", "events"],
                          capture_output=True, text=True, timeout=120).stdout
    (a.out / "logcat.txt").write_text(text)
    offer = parse(text)
    offer.update(captured_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), laptop=a.laptop)
    (a.out / "offer.json").write_text(json.dumps(offer, indent=2) + "\n")
    print(json.dumps(dict(offer_found=bool(offer["url"]), source=offer["source"], url=redact(offer["url"]),
                          other_downloads=offer["other_downloads"][:5], payload_offset=offer["offset"],
                          payload_size=offer["size"], headers=sorted(offer["headers"]), result=offer["result"],
                          builds_mentioned=offer["builds"][:6], offer_lines=len(offer["lines"]),
                          saved=str(a.out)), indent=2))
    return 0 if offer["url"] else 3


if __name__ == "__main__":
    sys.exit(main())
