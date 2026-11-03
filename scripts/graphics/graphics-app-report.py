#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The checks of graphics-app-qemu.sh (ANAL-323, ANAL-327), from the sections its boot printed.

usage: graphics-app-report.py BOOT_DIR OUT_JSON [NVK_APK_SHA256]      exit 1 if a check failed
"""
import json
import os
import re
import sys


def read(d, name):
    p = os.path.join(d, "sections", name + ".txt")
    return open(p, encoding="utf-8", errors="replace").read() if os.path.exists(p) else ""


def ids(xml):
    return set(re.findall(r'resource-id="([^"]*)"', xml))


def texts(xml):
    return re.findall(r' text="([^"]*)"', xml)


def main(boot, out, apk_sha=""):
    pkg, bootlog = read(boot, "gfx-pkg"), read(boot, "gfx-boot")
    main_, apps, settings = read(boot, "gfx-main"), read(boot, "gfx-apps"), read(boot, "gfx-settings")
    g14, apps_g14, avc = read(boot, "gfx-g14"), read(boot, "gfx-apps-g14"), read(boot, "gfx-avc")
    sw, sw_on, g14_off = read(boot, "gfx-switch"), read(boot, "gfx-switch-on"), read(boot, "gfx-g14-off")
    checks = []

    def check(name, ok, detail="", required=True):
        checks.append({"check": name, "ok": bool(ok), "detail": detail, "required": required})

    path = re.search(r"package:(\S+)", pkg)
    check("installed as a system_ext priv-app", path and path.group(1) == "/system_ext/priv-app/OpenBookGraphics/OpenBookGraphics.apk",
          path.group(1) if path else "no path")
    check("version 1.3 (4)", "versionName=1.3" in pkg and re.search(r"versionCode=4\b", pkg))
    check("privileged", re.search(r"privateFlags=\[[^\]]*PRIVILEGED", pkg))
    for perm in ("REBOOT", "WRITE_SECURE_SETTINGS", "POST_NOTIFICATIONS", "QUERY_ALL_PACKAGES", "RECEIVE_BOOT_COMPLETED"):
        check(f"{perm} granted", re.search(rf"android\.permission\.{perm}: granted=true", pkg))
    check("allow-list and default permissions installed",
          "privapp-permissions-org.openbook.graphics.xml" in pkg and "default-permissions-org.openbook.graphics.xml" in pkg)
    stopped = re.search(r"User 0: .*stopped=(true|false)", pkg)
    check("not stopped at first boot (sysconfig)", stopped and stopped.group(1) == "false", stopped.group(1) if stopped else "?")
    check("seapp_contexts entry", "name=org.openbook.graphics domain=openbook_graphics_app" in pkg)
    nvk = re.search(r"^(\d+)$", pkg, re.M)
    check("org.openbook.nvk installed", nvk and nvk.group(1) == "1", nvk.group(1) if nvk else "?")
    check("org.openbook.nvk in /vendor/app", "package:/vendor/app/OpenBookNvk/OpenBookNvk.apk" in pkg)
    check("org.openbook.nvk: a system package", re.search(r"(pkgFlags|flags)=\[[^\]]*\bSYSTEM\b", pkg))
    check("org.openbook.nvk: x86_64 libraries", "primaryCpuAbi=x86_64" in pkg)
    check("org.openbook.nvk: version 26.2.5-openbook.3 (3)",
          "versionName=26.2.5-openbook.3" in pkg and re.search(r"versionCode=3\b", pkg))
    check("OpenBookNvk.apk labelled vendor_app_file", re.search(r"u:object_r:vendor_app_file:s0\s.*\sOpenBookNvk\.apk$", pkg, re.M))
    on_dev = re.search(r"^([0-9a-f]{64})\s+/vendor/app/OpenBookNvk/OpenBookNvk\.apk", pkg, re.M)
    check("OpenBookNvk.apk is the image's", on_dev and (not apk_sha or on_dev.group(1) == apk_sha),
          on_dev.group(1)[:16] if on_dev else "no hash")
    check("nothing offers it without an NVIDIA GPU",
          re.search(r"nvk_offer=\s", pkg) and re.search(r"gfx_driver=\s*$", pkg, re.M))

    check("boot sync: with the app driver", "games: 0 on the NVIDIA GPU's list (boot)" in bootlog,
          next((l for l in bootlog.splitlines() if "games:" in l), "")[-120:])
    for k in ("updatable_driver_all_apps", "updatable_driver_production_allowlist", "updatable_driver_production_opt_in_apps",
              "updatable_driver_production_opt_out_apps"):
        check(f"{k} unset after boot (no game installed)", f"{k}=null" in bootlog)
    check("periodic job scheduled", not re.search(r"unknown job|not found|Could not find", bootlog, re.I), "")
    summary = re.search(r"^1 \S+ \S+ \S+ \S+ (on|off) (\S+) \S+$", bootlog, re.M)
    check("switcher state readable", summary, summary.group(0) if summary else "")

    domain = re.search(r"u:r:(\S+?):s0\S*\s.*org\.openbook\.graphics", main_)
    check("runs in openbook_graphics_app", domain and domain.group(1) == "openbook_graphics_app", domain.group(1) if domain else "no process")
    mi, mt = ids(main_), texts(main_)
    check("main screen: Apps on the NVIDIA GPU with its switch and button",
          "apps-no-driver" not in mi and "apps-open" in mi and "apps-switch-main" in mi)
    switching = [t for t in mt if "Switching is not turned on" in t or "no graphics switch" in t]
    check("main screen: switching off or not available said", switching, switching[0] if switching else " | ".join(mt[:12]))
    check("switch off: updatable_driver_all_apps 3", "off=3" in sw and "tapped" in sw, sw.strip()[-160:])
    check("switch off: the screen says every app uses the Radeon", "Off: every app uses the Radeon" in sw)
    check("switch on again: updatable_driver_all_apps 0", "on=0" in sw_on and "tapped" in sw_on, sw_on.strip()[-160:])
    check("the app logged both writes", sw_on.count("NVIDIA GPU for apps") >= 2 and "refused" not in sw_on)
    ai = ids(apps)
    check("apps screen: the switch and the games rule, no 'no driver'",
          "apps-no-driver" not in ai and "apps-switch-toggle" in ai and "games-switch" in ai)
    check("Settings resolves the app's Display entry", "org.openbook.graphics/.ui.SettingsEntry" in settings)
    # Informational: AOSP 17 (cp2a) builds Display as a catalyst screen (catalyst_display_settings_screen, read-only
    # since bp2a), and in the first runs (anal323b-app3) its Settings process loaded no injected entries at all.
    listed = "OpenBook Graphics" in texts(settings)
    check("Settings > Display lists OpenBook Graphics", listed,
          "" if listed else "AOSP 17's catalyst Display page shows no injected entries; the launcher entry is the way in",
          required=False)

    check("test game installed", "Success" in g14)
    check("driver package offered as on the G14", "gfx_driver=org.openbook.nvk" in g14)
    check("GraphicsEnvironment chose org.openbook.nvk",
          re.search(r"Updatable driver package search path: \S*OpenBookNvk", g14)
          and "not installed" not in g14)
    # GLES: with ANGLE as the system GLES driver (ro.hardware.egl=angle), Android gives every app the system ANGLE
    # first (GraphicsEnvironment.setupAngle), which carries the NVK patch; ANGLE then loads Vulkan, and libvulkan loads
    # the package's NVK from its namespace. QEMU's Vulkan name is pastel (its software fallback), so libvulkan asks the
    # package for vulkan.pastel.so, finds none and aborts the game: init never offers the package then (only with
    # ro.hardware.vulkan=radv, as on the G14). What QEMU shows is that the namespace exists and is searched.
    vk_name = re.search(r"Could not load vulkan\.(\S+)\.so from updatable gfx driver namespace", g14)
    check("libvulkan searched the package's namespace for the Vulkan HAL", vk_name,
          f"asked for vulkan.{vk_name.group(1)}.so" if vk_name else "")
    check("GLES through the system ANGLE, which then loads Vulkan",
          re.search(r"/system/lib64/libGLESv2_angle\.so \((egl::Initialize|EGL_Initialize)", g14)
          and "couldn't find an OpenGL ES implementation" not in g14)
    qemu_name = vk_name and vk_name.group(1) != "radv"
    check("no other library missing in the driver namespace",
          not re.search(r"(dlopen failed: library \"(?!vulkan\.)[^\"]+\" not found|cannot locate symbol)", g14),
          next((l for l in g14.splitlines() if re.search(r"cannot locate|dlopen failed: library \"(?!vulkan\.)", l)), "")[-160:])
    check("Vulkan: NVK loaded from the package (G14 only: QEMU's name is " + (vk_name.group(1) if vk_name else "?") + ")",
          "couldn't find an updated Vulkan implementation" not in g14, required=not qemu_name)
    check("dumpsys gpu: the game's driver is org.openbook.nvk",
          re.search(r"driverPackageName = org\.openbook\.nvk", g14), required=not qemu_name)
    check("with the switch off the game keeps the system driver",
          "Load updated gl driver" not in g14_off and "Updatable driver package search path" not in g14_off
          and re.search(r"game_pid=\d+", g14_off))
    gi = ids(apps_g14)
    check("apps screen lists the game with its choice", "choice-org.openbook.test.game-nvidia" in gi
          and "gpu-org.openbook.test.game" in gi)
    check("the games rule listed the game", "updatable_driver_production_allowlist=org.openbook.test.game" in apps_g14)

    kernel = re.search(r"kernel:(\d+)", avc)
    logcat = re.search(r"logcat:(\d+)", avc)
    app = re.search(r"app:(\d+)", avc)
    check("no SELinux denial for the app", app and app.group(1) == "0", app.group(1) if app else "?")
    game = re.search(r"game:(\d+)", avc)
    check("no SELinux denial for the game, the package or the GPU nodes", game and game.group(1) == "0",
          game.group(1) if game else "?")
    result = {"schema": "openbook-graphics-app-qemu/1", "boot": boot,
              "denials": {"kernel": int(kernel.group(1)) if kernel else None, "logcat": int(logcat.group(1)) if logcat else None},
              "passed": sum(c["ok"] for c in checks if c["required"]), "total": sum(c["required"] for c in checks),
              "informational": [c["check"] + (": ok" if c["ok"] else ": no") for c in checks if not c["required"]],
              "checks": checks}
    json.dump(result, open(out, "w"), indent=1)
    for c in checks:
        mark = ("ok  " if c["ok"] else "FAIL") if c["required"] else ("info" if c["ok"] else "no  ")
        print(mark + "  " + c["check"] + (f"  ({c['detail']})" if c["detail"] else ""))
    print(f"{result['passed']}/{result['total']} required; informational: {'; '.join(result['informational'])}; "
          f"denials: kernel {result['denials']['kernel']}, logcat {result['denials']['logcat']}")
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
