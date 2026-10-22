#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare ARM64 translators on an authorized device without changing its system (ANAL-234).

Runs build.sh's probes in a new /data/local/tmp directory through three translators:
  houdini   the system's /system/bin/houdini64, as configured
  ndk       a copy of the system's libndk_translation program runner, with the system's
            /system/lib64/berberis/arm64 guest libraries (the set its init rule binds over
            /system/lib64/arm64 when it is the configured bridge)
  digitalis the source-built Digitalis bundle pushed beside the probes, started by dg_launch
            with its own guest linker and vdso (never Ruby's /system/bin/berberis)
plus the native x86_64 CoreMark control. libicing.so is extracted on the device from the
device's own Settings Services APK; it is never pushed or published. Nothing outside the
run directory is written, no app is installed and no setting changes; the run directory
is removed at the end. Raw output goes to a new private OUT directory.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SI_APK = "/product/priv-app/SettingsIntelligenceGooglePrebuilt/SettingsIntelligenceGooglePrebuilt.apk"
NDK_RUNNER = "/system/bin/ndk_translation_program_runner_binfmt_misc_arm64"
NDK_GUEST = "/system/lib64/berberis/arm64"
PROBES = ["icing_probe", "coremark-arm64", "coremark-x86_64", "bridge_check-arm64", "dg_launch", "icing-input.bin"]
MIN_DATA_FREE_KB = 400 * 1024


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--adb", required=True)
    p.add_argument("--serial", required=True, help="Exact authorized serial from adb devices -l")
    p.add_argument("--build", required=True, type=Path, help="build.sh output")
    p.add_argument("--digitalis", required=True, type=Path, help="Digitalis bundle (contains system/)")
    p.add_argument("--out", required=True, type=Path, help="New private output directory")
    p.add_argument("--rounds", type=int, default=20, help="Timed search rounds per translator")
    p.add_argument("--coremark-iterations", type=int, default=600000)
    p.add_argument("--coremark-rounds", type=int, default=3)
    a = p.parse_args()
    if a.out.exists():
        p.error("A new output directory is required")
    for name in PROBES:
        if not (a.build / name).is_file():
            p.error(f"missing {a.build / name}; run build.sh")
    bundle = a.digitalis / "system"
    if not (bundle / "bin/berberis_program_runner_arm64").is_file():
        p.error("not a Digitalis bundle")
    a.out.mkdir(mode=0o700, parents=True)
    log = open(a.out / "commands.log", "w")

    def adb(*args, timeout=900, check=True):
        cmd = [a.adb, "-s", a.serial, *args]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        log.write(json.dumps({"cmd": cmd[3:], "rc": r.returncode}) + "\n")
        log.flush()
        if check and r.returncode:
            raise RuntimeError(f"{' '.join(cmd[3:])}: rc={r.returncode} {r.stderr.strip()[:400]}")
        return r

    def sh(script, timeout=900, check=True):
        return adb("shell", script, timeout=timeout, check=check)

    if adb("get-state").stdout.strip() != "device":
        sys.exit("device not ready")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = f"/data/local/tmp/anal234-hw-{stamp}"
    identity = sh("getprop ro.build.fingerprint; getprop ro.bootimage.build.fingerprint; "
                  "getprop ro.dalvik.vm.native.bridge; grep -m1 'model name' /proc/cpuinfo; "
                  "uname -r; getenforce; uptime; sha256sum " + SI_APK).stdout
    (a.out / "identity.txt").write_text(identity)
    free_kb = int(sh("df -k /data | tail -1").stdout.split()[3])
    if free_kb < MIN_DATA_FREE_KB:
        sys.exit(f"/data has {free_kb} KiB free; need {MIN_DATA_FREE_KB}")
    started = sh("date '+%m-%d %H:%M:%S.000'").stdout.strip()
    result = {"schema": "openbook-anal234-hw-translators/1", "device_dir": d, "data_free_kb_before": free_kb,
              "started_device_time": started, "modes": {}}
    try:
        sh(f"mkdir {d} && cd {d} && mkdir -p hou/run ndk/run ndk/bin dg/run dg/bin && "
           f"unzip -p {SI_APK} lib/arm64-v8a/libicing.so > libicing.so && sha256sum libicing.so")
        for name in PROBES:
            adb("push", str(a.build / name), f"{d}/{name}")
        adb("push", str(bundle / "bin/arm64/linker64"), f"{d}/dg/bin/linker64")
        adb("push", str(bundle / "lib64/arm64"), f"{d}/dg/guest")
        host_libs = sorted(str(f) for f in (bundle / "lib64").glob("*.so"))
        sh(f"mkdir {d}/dg/lib64")
        adb("push", *host_libs, f"{d}/dg/lib64/")
        # $ORIGIN may resolve to the guest executable or to the host runner; provide both.
        sh(f"cd {d} && chmod 755 icing_probe coremark-* bridge_check-arm64 dg_launch && "
           f"cp {NDK_RUNNER} ndk/bin/ && "
           f"for m in hou ndk dg; do cp icing_probe coremark-arm64 bridge_check-arm64 $m/run/; done && "
           f"ln -s {NDK_GUEST} ndk/run/guest && ln -s {NDK_GUEST} ndk/bin/guest && "
           f"ln -s {d}/dg/guest dg/run/guest && ln -s {d}/dg/guest dg/bin/guest && "
           f"sha256sum libicing.so icing_probe coremark-arm64 bridge_check-arm64 icing-input.bin")
        runners = {
            "houdini": ("hou", lambda exe: f"/system/bin/houdini64 {exe} {exe}"),
            "ndk": ("ndk", lambda exe: f"{d}/ndk/bin/{Path(NDK_RUNNER).name} {exe} {exe}"),
            "digitalis": ("dg", lambda exe: f"env LD_LIBRARY_PATH={d}/dg/lib64 {d}/dg_launch {d}/dg/lib64/libberberis_arm64.so "
                                            f"{d}/dg/bin/linker64 {d}/dg/guest/libnative_bridge_vdso.so {exe}"),
        }
        for mode, (sub, run) in runners.items():
            m = result["modes"].setdefault(mode, {})
            exe = f"{d}/{sub}/run"
            args = f"{d}/libicing.so {d}/icing-input.bin {exe}/result.bin {exe}/icing {a.rounds}"
            r = sh(f"cd {exe} && timeout 600 {run(exe + '/icing_probe')} {args}; echo EXIT=$?", timeout=700, check=False)
            (a.out / f"{mode}-icing.txt").write_text(r.stdout + r.stderr)
            m["icing_exit"] = exit_code(r.stdout)
            m["icing_done"] = parse_kv(r.stdout, "ICING_PROBE_DONE")
            m["icing_loaded"] = re.findall(r"ICING_PROBE_LOADED (\S+)", r.stdout)
            if adb("pull", f"{exe}/result.bin", str(a.out / f"{mode}-result.bin"), check=False).returncode == 0:
                dec = subprocess.run([sys.executable, str(HERE / "icing-probe.py"), "decode",
                                      str(a.out / f"{mode}-result.bin")], capture_output=True, text=True)
                m["icing"] = json.loads(dec.stdout) if dec.returncode == 0 else {"decode_error": dec.stderr[-400:]}
            r = sh(f"cd {exe} && timeout 120 {run(exe + '/bridge_check-arm64')}; echo EXIT=$?", timeout=200, check=False)
            (a.out / f"{mode}-bridge-check.txt").write_text(r.stdout + r.stderr)
            m["bridge_check_exit"] = exit_code(r.stdout)
            m["bridge_check"] = [json.loads(x) for x in re.findall(r'^(\{"test".*\})\s*$', r.stdout, re.M)]
        cm = result["coremark"] = {}
        for rnd in range(a.coremark_rounds):
            for mode in ["native", "digitalis", "ndk"]:
                if mode == "native":
                    cmd = f"{d}/coremark-x86_64"
                else:
                    sub, run = runners[mode]
                    cmd = run(f"{d}/{sub}/run/coremark-arm64")
                r = sh(f"cd {d} && timeout 900 {cmd} 0x0 0x0 0x66 {a.coremark_iterations}; echo EXIT=$?",
                       timeout=1000, check=False)
                (a.out / f"coremark-{mode}-{rnd}.txt").write_text(r.stdout + r.stderr)
                ips = re.search(r"Iterations/Sec\s*:\s*([0-9.]+)", r.stdout)
                cm.setdefault(mode, []).append({"exit": exit_code(r.stdout), "valid": "Correct operation validated" in r.stdout,
                                                "iterations_per_sec": float(ips.group(1)) if ips else None})
        logs = sh(f"logcat -d -v threadtime -T '{started}' 2>/dev/null | grep -iE 'houdini|berberis|ndk_translation|"
                  f"icing_probe|DEBUG|F libc' | head -400", check=False)
        (a.out / "logcat-translators.txt").write_text(logs.stdout)
        result["houdini_log_lines"] = [l for l in logs.stdout.splitlines() if "houdini" in l.lower()][-6:]
    finally:
        sh(f"rm -rf {d}", check=False)
        result["device_dir_removed"] = sh(f"[ -e {d} ] && echo present || echo absent", check=False).stdout.strip() == "absent"
        result["data_free_kb_after"] = int(sh("df -k /data | tail -1").stdout.split()[3])
        (a.out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summarise(result), indent=2))


def exit_code(text):
    m = re.findall(r"EXIT=(\d+)", text)
    return int(m[-1]) if m else None


def parse_kv(text, tag):
    m = re.search(tag + r" (.*)", text)
    return dict(kv.split("=", 1) for kv in m.group(1).split()) if m else None


def summarise(r):
    out = {}
    for mode, m in r["modes"].items():
        icing = m.get("icing") or {}
        out[mode] = {"icing_exit": m.get("icing_exit"), "icing_pass": icing.get("pass"),
                     "timings": m.get("icing_done"),
                     "bridge_check": {x.get("test"): x.get("ok") for x in m.get("bridge_check", [])},
                     "bridge_check_exit": m.get("bridge_check_exit")}
    cm = r.get("coremark", {})
    best = {k: max((x["iterations_per_sec"] or 0) for x in v) for k, v in cm.items()}
    out["coremark_best_ips"] = best
    if best.get("native"):
        out["coremark_ratio_to_native"] = {k: round(v / best["native"], 3) for k, v in best.items() if k != "native"}
    out["device_dir_removed"] = r.get("device_dir_removed")
    return out


if __name__ == "__main__":
    main()
