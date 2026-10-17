#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Evaluate a live-qemu.sh run (ANAL-190): read each case's serial log and result.json, and the test sticks' GPT
and ESP afterwards; write RUN/results.json (machine-readable, one entry per check) and RUN/SUMMARY.md. Sections
the expect scripts printed between ===NAME-BEGIN=== and ===NAME-END=== go to RUN/<case>/sections/ (DMESG and
LOGCAT are decoded from gzip+base64). Files the "save logs" entry wrote to the ESP are copied to RUN/logs/esp/.
Runs in the openbook-installer container (sgdisk, mtools).

usage: live-qemu-check.py --run DIR --disks DIR --image IMG --esp-offset BYTES
"""
import argparse
import base64
import binascii
import gzip
import json
import os
import re
import subprocess


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def sections(text, out):
    found = {}
    for m in re.finditer(r"\n===([A-Z0-9-]+)-BEGIN===\r?\n(.*?)\n===\1-END===", text, re.S):
        name, body = m.group(1), m.group(2).replace("\r", "")
        found[name] = body
        os.makedirs(out, exist_ok=True)
        if name in ("DMESG", "LOGCAT"):
            try:
                raw = gzip.decompress(base64.b64decode("".join(l.strip() for l in body.splitlines()
                                                               if re.fullmatch(r"[A-Za-z0-9+/=]+", l.strip()))))
                open(f"{out}/{name.lower()}.txt.gz", "wb").write(gzip.compress(raw, mtime=0))
                found[name] = raw.decode("utf-8", "replace")
            except (binascii.Error, OSError, EOFError) as e:
                found[name] = f"(undecodable: {e})"
        else:
            open(f"{out}/{name.lower()}.txt", "w").write(body + "\n")
    return found


def gpt_facts(img):
    v = sh("sgdisk", "-v", img)
    p = sh("sgdisk", "-p", img)
    size = os.path.getsize(img) // 512
    last_usable = int(re.search(r"last usable sector is (\d+)", p).group(1))
    parts = {m.group(5): (int(m.group(2)), int(m.group(3))) for m in
             re.finditer(r"^\s+(\d+)\s+(\d+)\s+(\d+)\s+\S+ \S+\s+(\S+)\s+(\S+)$", p, re.M)}
    ud = parts.get("userdata", (0, 0))
    return {"ok": "No problems found" in v, "disk_sectors": size, "last_usable": last_usable,
            "userdata_sectors": ud[1] - ud[0] + 1, "userdata_to_end": size - 1 - ud[1]}


def esp_ls(img, off, path):
    o = subprocess.run(["mdir", "-b", "-i", f"{img}@@{off}", f"::{path}"], capture_output=True, text=True)
    return [os.path.basename(x.rstrip("/")) for x in o.stdout.split()] if o.returncode == 0 else []


def esp_get(img, off, path, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    return subprocess.run(["mcopy", "-n", "-o", "-i", f"{img}@@{off}", f"::{path}", dest]).returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--disks", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--esp-offset", type=int, required=True)
    a = ap.parse_args()
    R, Q, off = a.run, a.disks, a.esp_offset
    meta = json.load(open(a.image + ".json"))
    ud_image = next(p["sectors"] for p in meta["partitions"] if p["name"] == "userdata")
    results = {"image": os.path.basename(a.image), "label": meta["label"], "cases": {}}
    marker = {}

    def case(name):
        d = f"{R}/{name}"
        if not os.path.exists(f"{d}/result.json"):
            return None
        res = json.load(open(f"{d}/result.json"))
        text = open(f"{d}/serial.log", "rb").read().decode("utf-8", "replace") if os.path.exists(f"{d}/serial.log") else ""
        c = {"result": res, "checks": []}
        results["cases"][name] = c
        return c, res, text, sections(text, f"{d}/sections")

    def check(c, what, ok, detail=""):
        c["checks"].append({"check": what, "ok": bool(ok), "detail": str(detail)[:400]})

    def common(c, res, text, sec):
        check(c, "every expect step matched", res["steps_done"] == res["steps"],
              f"{res['steps_done']}/{res['steps']} ({res['reason']})")
        st = sec.get("STORAGE", "")
        links = re.findall(r" (\S+) -> (/dev/block/\S+)", st)
        check(c, "by-name links point at the USB stick only", links and all("/sd" in t for _, t in links),
              f"{len(links)} links: " + ", ".join(sorted({os.path.basename(t).rstrip('0123456789') for _, t in links})))
        m = re.search(r"^\S+\s+(\d+)\s+\d+\s+\d+\s+\d+% /data$", st, re.M)
        return int(m.group(1)) if m else None

    # first boot: grow, format, marker, boot, decoy untouched
    got = case("first")
    if got:
        c, res, text, sec = got
        data_kib = common(c, res, text, sec)
        m = re.search(r"grow: GPT backup moved LBA (\d+) -> (\d+); userdata (\d+) -> (\d+) sectors", text)
        check(c, "openbook-live-init grew userdata and moved the backup GPT", m, m.group(0) if m else "no grow line")
        g = gpt_facts(f"{Q}/s16.img")
        check(c, "stick GPT valid afterwards, backup at the end (sgdisk -v)", g["ok"] and g["userdata_to_end"] < 2048 + 34,
              json.dumps(g))
        check(c, "/data formatted at the grown size", data_kib and data_kib > 0.9 * g["userdata_sectors"] / 2,
              f"df /data {data_kib} KiB, userdata {g['userdata_sectors'] // 2} KiB")
        live = sec.get("LIVE", "")
        check(c, "Android formatted the blank metadata and userdata", re.search(r"wiped|[Ff]ormat", live),
              "; ".join(l for l in live.splitlines() if re.search(r"wiped|ormat", l))[:300])
        mk = re.search(r"\nMARKER=(openbook-live-marker-\d+)", text)
        marker["first"] = mk.group(1) if mk else None
        check(c, "marker file written to /data", mk, marker["first"])
        b = re.search(r"\nBOOTDONE=(\S*) uptime=([0-9.]+)", text)
        check(c, "sys.boot_completed=1 within 600 s (desktop)", b and b.group(1) == "1",
              f"BOOTDONE={b.group(1) if b else '?'} at uptime {b.group(2) if b else '?'} s")
        check(c, "screenshot after the boot wait", os.path.exists(f"{R}/first/shot-after-boot.png"))
        before = open(f"{Q}/decoy.sha256.before").read().strip() if os.path.exists(f"{Q}/decoy.sha256.before") else "?"
        # Hash the decoy now: it has been attached to every boot of this stick (first, second, reset).
        after = sh("sha256sum", f"{Q}/decoy.img").split()[0] if os.path.exists(f"{Q}/decoy.img") else "!"
        check(c, "decoy NVMe disk unchanged after all its boots (sha256)", before == after, f"{before[:16]} / {after[:16]}")
        rep = esp_ls(f"{Q}/s16.img", off, "/openbook/logs")
        check(c, "live-init report on the ESP", "live-init-001.json" in rep, rep)
        if "live-init-001.json" in rep and esp_get(f"{Q}/s16.img", off, "/openbook/logs/live-init-001.json",
                                                   f"{R}/first/esp/live-init-001.json"):
            c["live_init"] = json.load(open(f"{R}/first/esp/live-init-001.json"))["result"]

    got = case("second")
    if got:
        c, res, text, sec = got
        common(c, res, text, sec)
        check(c, "openbook-live-init: nothing to grow", "grow: nothing to do" in text)
        mk = re.search(r"\nMARKER=(openbook-live-marker-\d+)", text)
        check(c, "marker from the first boot still there", mk and mk.group(1) == marker.get("first"),
              f"{mk.group(1) if mk else None} vs {marker.get('first')}")

    got = case("reset")
    if got:
        c, res, text, sec = got
        common(c, res, text, sec)
        check(c, "metadata and userdata zeroed",
              set(re.findall(r"reset: zeroed the first 1024 KiB of (metadata|userdata)", text)) == {"metadata", "userdata"})
        check(c, "Android formatted them again", re.search(r"wiped|[Ff]ormat", sec.get("LIVE", "")))
        check(c, "marker gone", "\nMARKER=absent" in text)
        rep = esp_ls(f"{Q}/s16.img", off, "/openbook/logs")
        ok = False
        for f in sorted(x for x in rep if x.startswith("live-init-")):
            if esp_get(f"{Q}/s16.img", off, f"/openbook/logs/{f}", f"{R}/reset/esp/{f}"):
                ok = ok or json.load(open(f"{R}/reset/esp/{f}"))["result"]["action"].startswith("reset")
        check(c, "reset recorded on the ESP", ok, rep)

    got = case("exact")
    if got:
        c, res, text, sec = got
        data_kib = common(c, res, text, sec)
        check(c, "openbook-live-init: nothing to grow", "grow: nothing to do" in text)
        check(c, "/data at the image's userdata size", data_kib and 0.9 * ud_image / 2 < data_kib <= ud_image / 2,
              f"df /data {data_kib} KiB, userdata {ud_image // 2} KiB")
        check(c, "stick GPT valid (sgdisk -v)", gpt_facts(f"{Q}/exact.img")["ok"])

    got = case("logs")
    if got:
        c, res, text, sec = got
        check(c, "every expect step matched", res["steps_done"] == res["steps"], f"{res['steps_done']}/{res['steps']} ({res['reason']})")
        check(c, "Android shut down by itself after saving", res["reason"].startswith("QEMU exited"), res["reason"])
        img = f"{Q}/logs16.img"
        dirs = [x for x in esp_ls(img, off, "/openbook/logs") if re.fullmatch(r"live-\d{3}", x)]
        check(c, "openbook/logs/live-NNN/ on the ESP", dirs, dirs)
        if dirs:
            d = dirs[-1]
            files = esp_ls(img, off, f"/openbook/logs/{d}")
            for f in files:
                esp_get(img, off, f"/openbook/logs/{d}/{f}", f"{R}/logs/esp/{d}/{f}")
            got_files = sorted(files)
            check(c, "dmesg, logcat, system facts, screenshot and summary saved",
                  all(any(f.startswith(p) for f in got_files) for p in ("dmesg.txt", "logcat-final", "collect-final",
                                                                        "screen-final", "summary.json")), got_files)
            p = f"{R}/logs/esp/{d}"
            try:
                s = json.load(open(f"{p}/summary.json"))
            except (OSError, ValueError) as e:
                s = None
                check(c, "summary.json is valid JSON", False, e)
            if s:
                c["summary"] = s
                check(c, "summary.json: second stage seen, captures done", s["second_stage_s"] > 0 and s["captures"],
                      f"second stage {s['second_stage_s']} s, boot_completed {s['boot_completed']}, "
                      f"{len(s['captures'])} capture(s)")
            check(c, "dmesg.txt non-empty", os.path.exists(f"{p}/dmesg.txt") and os.path.getsize(f"{p}/dmesg.txt") > 10000,
                  os.path.getsize(f"{p}/dmesg.txt") if os.path.exists(f"{p}/dmesg.txt") else 0)
            lc = f"{p}/logcat-final.txt"
            check(c, "logcat saved", os.path.exists(lc) and os.path.getsize(lc) > 10000,
                  os.path.getsize(lc) if os.path.exists(lc) else 0)
            sc = f"{p}/screen-final.png"
            check(c, "screenshot is a PNG", os.path.exists(sc) and open(sc, "rb").read(8) == b"\x89PNG\r\n\x1a\n",
                  os.path.getsize(sc) if os.path.exists(sc) else 0)
            ls_ = f"{p}/logcat-stream.txt"
            check(c, "logcat streamed to the stick from early second stage",
                  os.path.exists(ls_) and os.path.getsize(ls_) > 10000, os.path.getsize(ls_) if os.path.exists(ls_) else 0)
            check(c, "wake lock held while recording (no suspend)", "logs: wake lock held" in text)
            co = f"{p}/collect-final.txt"
            check(c, "system facts saved", os.path.exists(co) and "===PROPS===" in open(co, errors="replace").read())
        check(c, "stick GPT valid (sgdisk -v)", gpt_facts(img)["ok"])

    got = case("default")
    if got:
        c, res, text, sec = got
        shots = sorted(f for f in os.listdir(f"{R}/default") if f.startswith("shot-") and f.endswith(".png"))
        check(c, "screenshots of the unchanged default entry", len(shots) >= 5, shots)
        g = gpt_facts(f"{Q}/default16.img")
        check(c, "openbook-live-init grew userdata on the default entry too",
              g["ok"] and g["userdata_to_end"] < 2048 + 34 and g["userdata_sectors"] > ud_image, json.dumps(g))
        check(c, "live-init report on the ESP", "live-init-001.json" in esp_ls(f"{Q}/default16.img", off, "/openbook/logs"))

    total = sum(len(c["checks"]) for c in results["cases"].values())
    passed = sum(x["ok"] for c in results["cases"].values() for x in c["checks"])
    results["passed"], results["total"] = passed, total
    json.dump(results, open(f"{R}/results.json", "w"), indent=1)
    with open(f"{R}/SUMMARY.md", "w") as f:
        f.write(f"# Live image QEMU run: {meta['label']}\n\n{passed}/{total} checks passed.\n\n"
                "| Case | Check | Result | Detail |\n|---|---|---|---|\n")
        for name, c in results["cases"].items():
            for x in c["checks"]:
                d = x["detail"].replace("|", "/").replace("\n", " ")[:160]
                f.write(f"| {name} | {x['check']} | {'PASS' if x['ok'] else 'FAIL'} | {d} |\n")
    print(open(f"{R}/SUMMARY.md").read())


if __name__ == "__main__":
    main()
