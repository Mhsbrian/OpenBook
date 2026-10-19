#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Test a disposable copy of an installed disk. Never connects to the physical laptop.

Requires websocket-client for Chromium DevTools checks. --baseline demonstrates
that the old image accepts a guest native-only bind; it skips Chromium testing.
The OTA harness must come from the integration tree used to build the image.
"""
import argparse
import base64
import functools
import http.server
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
import urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--harness", required=True, type=Path)
    ap.add_argument("--disk", required=True, type=Path)
    ap.add_argument("--vars", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--probe", required=True, type=Path)
    ap.add_argument("--host-probe", type=Path)
    ap.add_argument("--legacy-probes", type=Path)
    ap.add_argument("--chromium", type=Path)
    ap.add_argument("--baseline", action="store_true")
    args = ap.parse_args()
    spec = importlib.util.spec_from_file_location("ota_qemu", args.harness)
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    args.out.mkdir(parents=True, exist_ok=True)
    # The installer container can write only under anybook/installer and logs/installer.
    disk = args.disk.parent / (args.out.name + "-compat.img")
    variables = disk.with_suffix(".vars")
    if disk.exists() or variables.exists():
        raise RuntimeError("Refusing to overwrite an existing test disk")
    q.reflink(str(args.disk), str(disk))
    shutil.copy(args.vars, variables)
    checks = []

    def check(name, ok, detail):
        checks.append(dict(name=name, ok=bool(ok), detail=detail))
        print(("PASS " if ok else "FAIL ") + name + ": " + str(detail), flush=True)
        (args.out / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")

    vm = q.VM(str(args.out), str(disk), str(variables), q.free_port(),
              "anal224-" + args.out.name)
    server = None
    adb = None
    forward = None
    try:
        vm.start()
        q.boot(vm)
        adb = q.Adb(vm.port, str(args.out))
        adb.connect()
        check("user unlocked", *q.unlock(adb))
        adb.root()
        props, _ = adb.sh("getprop ro.build.version.incremental; getprop ro.boot.vbmeta.digest; "
                          "getprop ro.product.cpu.abilist; getprop ro.dalvik.vm.native.bridge; getenforce")
        (args.out / "image.txt").write_text(props)
        check("ARM bridge and enforcing", "arm64-v8a" in props and
              "libberberis_arm64.so" in props and "Enforcing" in props, props.strip())
        if not args.baseline:
            bridge, rc = adb.sh("/system/bin/arm64/openbook_bridge_check")
            (args.out / "bridge.txt").write_text(bridge)
            rows = [json.loads(line) for line in bridge.splitlines() if line.startswith('{"test":')]
            check("ARM64 executable and ISA regressions", rc == 0 and len(rows) == 4
                  and all(row.get("ok") for row in rows), rows)
            pushed = adb("push", str(args.probe), "/data/local/tmp/native-service-probe.apk")
            if pushed.returncode:
                raise RuntimeError(pushed.stderr)
            policy, rc = adb.sh("CLASSPATH=/system/framework/services.jar:/data/local/tmp/native-service-probe.apk "
                               "app_process / com.android.server.am.PolicyProbe")
            (args.out / "policy.txt").write_text(policy)
            check("real framework policy and direct API guards", rc == 0 and "POLICY_PASS checks=27" in policy,
                  policy.strip())
        result = adb("install", "--no-incremental", "-r", str(args.probe))
        check("install ARM-only probe", result.returncode == 0, result.stdout + result.stderr)
        native_before, _ = adb.sh("getprop init.svc.zygote_next")
        adb.sh("logcat -c")
        for attempt in range(1 if args.baseline else 3):
            adb.sh("am force-stop dev.openbook.nativefallback")
            adb.sh("am start -W -n dev.openbook.nativefallback/.ProbeActivity")
            end = time.monotonic() + 20
            while time.monotonic() < end:
                probe_log, _ = adb.sh("logcat -d -s NativeFallbackProbe:I '*:S'")
                if "PASS translated" in probe_log or "FAIL " in probe_log:
                    break
                time.sleep(0.5)
            (args.out / f"probe-{attempt}.txt").write_text(probe_log)
            expected = "FAIL guest native-only bind accepted" if args.baseline else "PASS translated"
            check(f"probe attempt {attempt + 1}", expected in probe_log, probe_log.strip())
            adb.sh("logcat -c")
        if args.baseline:
            return 0 if all(c["ok"] for c in checks) else 1
        native_after, _ = adb.sh("getprop init.svc.zygote_next")
        check("guest requests do not prewarm native zygote", native_before == native_after,
              dict(before=native_before.strip(), after=native_after.strip()))
        services, _ = adb.sh("dumpsys activity services dev.openbook.nativefallback")
        (args.out / "probe-services.txt").write_text(services)
        check("rejected service records do not accumulate", ".NativeOnly" not in services,
              services.strip())
        for mode, expected in [("positive", "PASS compatible alias translated JNI returned 42"),
                               ("permission", "PASS permission mismatch rejected")]:
            adb.sh("am force-stop dev.openbook.nativefallback; logcat -c")
            adb.sh("am start -W -n dev.openbook.nativefallback/.ProbeActivity --es alias_control " + mode)
            end = time.monotonic() + 20
            while time.monotonic() < end:
                alias_log, _ = adb.sh("logcat -d -s NativeFallbackProbe:I '*:S'")
                if "PASS " in alias_log or "FAIL " in alias_log:
                    break
                time.sleep(0.5)
            (args.out / f"alias-{mode}.txt").write_text(alias_log)
            check("service alias " + mode, expected in alias_log, alias_log.strip())
        if args.host_probe:
            result = adb("install", "--no-incremental", "-r", str(args.host_probe))
            check("install native host control", result.returncode == 0, result.stdout + result.stderr)
            abi, _ = adb.sh("dumpsys package dev.openbook.nativefallback | grep primaryCpuAbi")
            check("host control uses x86_64", "primaryCpuAbi=x86_64" in abi, abi.strip())
            adb.sh("am start -W -n dev.openbook.nativefallback/.ProbeActivity --ez host_control true")
            host_log, _ = adb.sh("logcat -d -s NativeFallbackProbe:I '*:S'")
            (args.out / "host-probe.txt").write_text(host_log)
            check("host native service lookup preserved", "PASS host native-only bind accepted" in host_log,
                  host_log.strip())
        if args.legacy_probes:
            for arch in ("arm64", "x86_64"):
                package = "dev.anybook.probe." + arch
                result = adb("install", "--no-incremental", "-r",
                             str(args.legacy_probes / f"anybook-probe-{arch}.apk"))
                check("install existing probe " + arch, result.returncode == 0, result.stdout)
                adb.sh(f"am force-stop {package}; logcat -c; am start -W "
                       f"-n {package}/dev.anybook.probe.MainActivity")
                end = time.monotonic() + 90
                while time.monotonic() < end:
                    legacy, _ = adb.sh("logcat -d -s AnyBookProbe:I '*:S'")
                    if "PROBE_DONE " in legacy:
                        break
                    time.sleep(1)
                (args.out / f"legacy-{arch}.txt").write_text(legacy)
                failed = set(re.findall(r"PROBE_RESULT (\S+) FAIL", legacy))
                summary = re.search(r"PROBE_DONE pass=(\d+) fail=(\d+) skip=(\d+)", legacy)
                expected = {"isa", "signals"} if arch == "arm64" else set()
                check("no additional legacy probe failures " + arch,
                      summary and int(summary[1]) >= 18 and failed <= expected,
                      dict(summary=summary[0] if summary else None, failed=sorted(failed)))
        if not args.chromium:
            raise RuntimeError("--chromium is required unless --baseline")
        import websocket
        result = adb("install", "--no-incremental", "-r", str(args.chromium), timeout=300)
        check("install Chromium ARM64", result.returncode == 0, result.stdout + result.stderr)
        abi, _ = adb.sh("dumpsys package org.chromium.chrome | grep primaryCpuAbi")
        check("Chromium uses ARM64", "primaryCpuAbi=arm64-v8a" in abi, abi.strip())
        www = args.out / "www"
        www.mkdir(exist_ok=True)
        for i in range(3):
            (www / f"{i}.html").write_text(
                f'<title>OpenBook ARM renderer {i}</title><h1>ARM64 renderer {i}</h1>'
                '<canvas id="c" width="80" height="80"></canvas><script>'
                'let c=document.getElementById("c").getContext("2d");'
                'c.fillStyle="#00aa44";c.fillRect(0,0,80,80);'
                f'window.probeResult={{answer:6*7,round:{i},pixel:[...c.getImageData(10,10,1,1).data]}};'
                '</script>')
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                    functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(www)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://10.0.2.2:{server.server_port}"
        # Only the disposable VM: permit debug command-line flags and skip account/setup UI.
        adb.sh("am set-debug-app --persistent org.chromium.chrome; "
               "echo '_ --no-first-run --disable-fre --no-default-browser-check "
               "--javaless-renderers=enabled "
               "--remote-debugging-port=9222 --remote-allow-origins=*' "
               "> /data/local/tmp/chrome-command-line; chmod 644 /data/local/tmp/chrome-command-line")
        adb.sh("am force-stop org.chromium.chrome; logcat -c")
        adb.sh(f"am start -W -a android.intent.action.VIEW -d '{url}/0.html' -p org.chromium.chrome")
        f = adb("forward", "tcp:0", "localabstract:chrome_devtools_remote")
        if f.returncode:
            raise RuntimeError(f.stderr)
        forward = f.stdout.strip()
        tabs = []
        end = time.monotonic() + 90
        while time.monotonic() < end:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{forward}/json", timeout=2) as r:
                    tabs = [x for x in json.load(r) if x.get("type") == "page"]
                if tabs:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(1)
        check("Chromium exposes a page", bool(tabs), [x.get("title") for x in tabs])
        if not tabs:
            raise RuntimeError("No Chromium page after 90 seconds")
        ws_url = tabs[0]["webSocketDebuggerUrl"].replace("localhost", "127.0.0.1")
        ws = websocket.create_connection(ws_url, timeout=20, suppress_origin=True)
        ident = 0

        def cdp(method, params):
            nonlocal ident
            ident += 1
            ws.send(json.dumps(dict(id=ident, method=method, params=params)))
            while True:
                response = json.loads(ws.recv())
                if response.get("id") == ident:
                    if "error" in response:
                        raise RuntimeError(response)
                    return response["result"]

        for i in range(3):
            adb.sh("am start -W -a android.intent.action.MAIN "
                   "-c android.intent.category.LAUNCHER -p org.chromium.chrome")
            cdp("Page.navigate", {"url": f"{url}/{i}.html"})
            result = None
            end = time.monotonic() + 30
            while time.monotonic() < end:
                result = cdp("Runtime.evaluate", {"expression": "window.probeResult", "returnByValue": True})
                value = result.get("result", {}).get("value", {})
                if value.get("round") == i:
                    break
                time.sleep(0.5)
            check(f"ARM renderer navigation {i}",
                  value == {"answer": 42, "round": i, "pixel": [0, 170, 68, 255]}, result)
            if i == 2:
                shot = cdp("Page.captureScreenshot", {"format": "png"})
                (args.out / "renderer.png").write_bytes(base64.b64decode(shot["data"]))
            start = time.monotonic()
            launch, rc = adb.sh("am force-stop com.android.settings; "
                                "am start -W -a android.settings.SETTINGS", timeout=15)
            elapsed = time.monotonic() - start
            check(f"unrelated app starts during round {i}", rc == 0 and
                  "Status: ok" in launch and elapsed < 5, dict(seconds=round(elapsed, 3), am=launch))
        ws.close()
        logs, _ = adb.sh("logcat -d -b all")
        (args.out / "logcat.txt").write_text(logs)
        check("Chromium managed service alias exercised", "Native bridge service fallback: org.chromium.chrome/" in logs,
              logs.count("Native bridge service fallback: org.chromium.chrome/"))
        check("no ELF mismatch or zygote retry storm", "EM_AARCH64" not in logs and
              "Got error connecting to zygote, retrying" not in logs, "ELF/zygote retry log search")
        processes, _ = adb.sh("ps -A -o LABEL,PID,NAME,ARGS | grep chromium")
        (args.out / "processes.txt").write_text(processes)
        check("managed isolated renderer exists", "sandboxed_process" in processes and
              "NativeOnlySandboxedProcessService" not in processes, processes.strip())
    except Exception as e:
        check("test completed", False, str(e))
        if adb:
            logs, _ = adb.sh("logcat -d -b all")
            (args.out / "logcat-error.txt").write_text(logs)
    finally:
        if adb and forward:
            adb("forward", "--remove", "tcp:" + forward)
        if server:
            server.shutdown()
        vm.stop()
    return 0 if checks and all(c["ok"] for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
