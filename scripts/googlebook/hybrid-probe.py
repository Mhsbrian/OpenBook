#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Build and boot a disposable Ruby-framework/OpenBook-vendor VM experiment.

Requires compat-audit.py's successful hybrid-reduced case. Runs only inside the
installer container: inputs read-only, /dev/kvm the only passed-through device.
Outputs are NEW local regular files, never installer sources or release images.
The Google system/product/system_ext image bytes are retained. This experiment
uses a local test-key AVB root and software security; it makes no Google trust,
certification, credential persistence or desktop claim. Do not upload output.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gpt = module("g14", HERE.parent / "kernel-g14-qemu.py")
bc = module("bootconfig", HERE.parent / "installer/bootconfig.py")
audit = module("audit", HERE / "compat-audit.py")
MiB = 1 << 20


def platform_cmdline(text):
    """Retain the vendor boot contract when loading its kernel directly.

    Android bootloaders consume vendor_boot's cmdline. QEMU -kernel and our
    UEFI Linux entries do not: omitting it hides all /vendor/firmware files.
    Refuse incompatible inputs instead of silently making a broken G14 image.
    """
    if any(c in text for c in ("\n", "\r", "\0")):
        raise ValueError("Invalid vendor command line")
    paths = [s for s in text.split() if s.startswith("firmware_class.path=")]
    if paths != ["firmware_class.path=/vendor/firmware"]:
        raise ValueError("Vendor command line must select /vendor/firmware exactly once")
    return text.strip()


def unpack_vendor(tool, image, out):
    args = shlex.split(subprocess.check_output(
        [str(tool), "--boot_img", str(image), "--out", str(out), "--format=mkbootimg"], text=True))
    if "--vendor_cmdline" not in args:
        raise ValueError("Missing vendor command line")
    return platform_cmdline(args[args.index("--vendor_cmdline") + 1])


def vendor_contexts(text, paths):
    """Keep original label rules applicable to the vendor tree being packed.

    Unrelated platform executable types can differ between AOSP and Ruby.
    Preserve the original regex and file-kind selector; libselinux still does
    the final precedence/label lookup. checkfc validates every retained type.
    """
    result = []
    for line in text.splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        if len(fields) not in (2, 3):
            raise ValueError("Unexpected file-context rule")
        pattern = re.compile(fields[0])
        if any(pattern.fullmatch(path) for path in paths):
            result.append(line)
    return "\n".join(result) + "\n"


def run(*args, **kw):
    print("+", " ".join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kw)


def wifi_overlay(a, w, vendor):
    """Build a local test-signed, resource-only hardware compatibility RRO."""
    source = HERE / "wifi-overlay"
    targets = list((a.audit / "ruby-apex/com.android.wifi/priv-app").glob("*/ServiceWifiResourcesGoogle.apk"))
    if len(targets) != 1:
        raise ValueError("Expected exactly one audited Ruby Wi-Fi resource APK")
    package = subprocess.check_output([str(a.tools / "aapt2"), "dump", "packagename", str(targets[0])], text=True).strip()
    validate_wifi_target((source / "AndroidManifest.xml").read_text(), package)
    aosp = a.product.parents[3]
    java = aosp / "prebuilts/jdk/jdk21/linux-x86/bin/java"
    cert = aosp / "build/make/target/product/security/testkey"
    compiled, unsigned = w / "wifi-res.zip", w / "wifi-unsigned.apk"
    run(a.tools / "aapt2", "compile", "--dir", source / "res", "-o", compiled)
    run(a.tools / "aapt2", "link", "--manifest", source / "AndroidManifest.xml",
        "-I", a.ruby / "fs/system_a/system/framework/framework-res.apk",
        "--min-sdk-version", "36", "--target-sdk-version", "36",
        "--auto-add-overlay", "--no-resource-deduping", "--no-resource-removal",
        "-o", unsigned, compiled)
    target = vendor / "overlay/OpenBookRubyWifi.apk"
    run(java, f"-Djava.library.path={a.tools.parent / 'lib64'}", "-jar", a.tools.parent / "framework/signapk.jar",
        str(cert) + ".x509.pem", str(cert) + ".pk8", unsigned, target)
    # Validate the actual retained Wi-Fi APK's overlayable declarations.
    run(a.tools / "idmap2", "create", "--target-apk-path", targets[0],
        "--overlay-apk-path", target, "--idmap-path", w / "wifi.idmap", "--policy", "vendor")
    shutil.copyfile(HERE / "wifi-platform.sh", vendor / "etc/ruby-wifi-platform.sh")
    (vendor / "etc/init/ruby-wifi-platform.rc").write_text('''service ruby-wifi-platform /system/bin/sh /vendor/etc/ruby-wifi-platform.sh
    class late_start
    user shell
    group shell system log
    seclabel u:r:shell:s0
    oneshot
''')
    return {"package": "org.openbook.ruby.wifi", "apk_sha256": audit.sha(target),
            "target_package": package,
            "target_sha256": audit.sha(targets[0]), "idmap_vendor_policy_validated": True,
            "activation": "mutable RRO, system user 0, highest priority; runtime readback required"}


def validate_wifi_target(manifest, package):
    # idmap2 validates resource mappings but does not reject a targetPackage
    # mismatch. Runtime OMS does. Fail before building a useless overlay.
    overlay = ET.fromstring(manifest).find("overlay")
    attr = "{http://schemas.android.com/apk/res/android}targetPackage"
    if package != "com.google.android.wifi.resources" or overlay is None or overlay.get(attr) != package:
        raise ValueError("Ruby Wi-Fi overlay target package mismatch")


def new_output(path, sources):
    path = path.absolute()
    if any(c in str(path) for c in (",", "\n", "\r")):
        raise ValueError("Output path contains QEMU option delimiters")
    if path.exists() or path.is_symlink() or path.resolve().is_relative_to(Path("/dev")):
        raise ValueError("Output must be a new local directory outside /dev")
    if any(path.resolve().is_relative_to(p.resolve()) for p in sources):
        raise ValueError("Output must be outside all input trees")
    path.mkdir(parents=True)
    return path


def prepare(a):
    if not Path("/.dockerenv").exists():
        raise ValueError("Run through scripts/installer/inst-docker.sh")
    report = json.loads((a.audit / "report.json").read_text())
    if report.get("schema") != "openbook-googlebook-compat-audit/1" or not report.get("inputs_unchanged"):
        raise ValueError("Audit missing or input changes detected")
    if not all(report["cases"][n]["static_checks_passed"] for n in ("ruby", "openbook", "hybrid-reduced")):
        raise ValueError("Required baseline/hybrid static checks failed")
    aliases = {"$RUBY": a.ruby, "$PRODUCT": a.product, "$TOOLS": a.tools,
               "$KERNEL": a.kernel, "$REPO": HERE.parents[1], "$OUT": a.audit}
    if "$RUBY/fs/vendor_a/etc/ueventd.rc" not in report["input_inventory"]:
        raise ValueError("Rerun the audit to include Ruby's TPM ownership configuration")
    if "$REPO/device/anybook/common/pc/init.openbook.zram.rc" not in report["input_inventory"]:
        raise ValueError("Rerun the audit to include the GKI zram module loader")
    camera = audit.camera_contract(a.product / "vendor")
    if report.get("camera") != camera:
        raise ValueError("Rerun the audit to include the built PC camera provider")
    for required in ("$REPO/config/image-bases/ruby-desktop-services.cil",
                     "$REPO/config/image-bases/ruby-pc-init.rc",
                     "$RUBY/fs/system_a/system/etc/init/timberslide.rc"):
        if required not in report["input_inventory"]:
            raise ValueError(f"Rerun the audit to include {required}")
    if not report["cases"]["hybrid-reduced"].get("service_contexts", {}).get("passed"):
        raise ValueError("Rerun the audit to validate retained framework service labels")
    for name, expected in report["input_inventory"].items():
        prefix, _, rel = name.partition("/")
        if prefix not in aliases or audit.sha(aliases[prefix] / rel) != expected:
            raise ValueError(f"Audited input drift: {name}")
    w = new_output(a.out, (a.ruby, a.product, a.tools, a.kernel, a.audit))
    # Local copies only. --product-out and file_contexts preserve Android ownership,
    # capabilities and labels; host copy ownership is not used as image metadata.
    vendor = w / "vendor"
    shutil.copytree(a.product / "vendor", vendor, symlinks=True)
    # Also supports an existing PRODUCT_OUT predating this PC init fragment.
    shutil.copyfile(audit.ZRAM_INIT, vendor / "etc/init/init.openbook.zram.rc")
    wifi = wifi_overlay(a, w, vendor)
    # The retained Ruby framework runs gscd as hsm. Preserve its reviewed device
    # ownership contract on the existing OpenBook TPM/CRB modules; no policy bypass.
    tpm_rule = "/dev/tpm* 0660 hsm hsm"
    ruby_ueventd = (a.ruby / "fs/vendor_a/etc/ueventd.rc").read_text()
    if ruby_ueventd.splitlines().count(tpm_rule) != 1:
        raise ValueError("Ruby TPM ownership rule changed")
    ueventd = vendor / "etc/ueventd.rc"
    text = ueventd.read_text()
    if any(line.strip().startswith("/dev/tpm") for line in text.splitlines()):
        raise ValueError("OpenBook already defines TPM ownership; review the integration")
    ueventd.write_text(text + "\n# Retained Ruby gscd device ownership\n" + tpm_rule + "\n")
    engine = HERE.parents[1] / "device/anybook/common/installer/engine"
    run("gcc", "-static", "-O2", "-Wall", "-Wextra", "-Werror", "-ffunction-sections", "-fdata-sections",
        "-Wl,--gc-sections", "-I", engine, HERE / "usb-log.c", engine / "fat.c", engine / "util.c",
        "-o", vendor / "bin/ruby-usb-log")
    se = vendor / "etc/selinux"
    services = se / "vendor_service_contexts"
    services.write_text(audit.framework_service_contexts(services.read_text(),
        (a.ruby / "fs/vendor_a/etc/selinux/vendor_service_contexts").read_text(), audit.SERVICE_PROFILE.read_text()))
    reduced_cil = a.audit / "hybrid-reduced/vendor_sepolicy.cil"
    (se / "vendor_sepolicy.cil").write_text(reduced_cil.read_text() + "\n" + audit.PROBE_POLICY.read_text()
                                           + "\n" + audit.DESKTOP_POLICY.read_text())
    # Fail on upstream service command drift before disabling this PC-inapplicable daemon.
    original_ec = (a.ruby / "fs/system_a/system/etc/init/timberslide.rc").read_text()
    ec_command = ("service timberslide /system/bin/timberslide --name cros_ec --log-to-logcat "
                  "--log-to-file /data/misc/timberslide/cros_ec.log --period-ms 4000")
    if original_ec.splitlines().count(ec_command) != 1:
        raise ValueError("Ruby timberslide init contract changed")
    shutil.copyfile(audit.PC_INIT, vendor / "etc/init/ruby-pc.rc")
    # Recompile the audited inputs into this new image, with neverallow checks.
    # A stale or replaced binary in the previous audit directory is not trusted.
    policy_inputs = []
    for name, expected in report["cases"]["hybrid-reduced"]["policy_inputs"].items():
        prefix, _, rel = name.partition("/")
        src = aliases[prefix] / rel
        if audit.sha(src) != expected:
            raise ValueError(f"Audited policy input drift: {name}")
        if src not in (audit.PROBE_POLICY, audit.DESKTOP_POLICY):
            policy_inputs.append(se / "vendor_sepolicy.cil" if src == reduced_cil else src)
    run(a.tools / "secilc", "-m", "-M", "true", "-G", "-c", "33", "-o", se / "precompiled_sepolicy",
        "-f", "/dev/null", *policy_inputs)
    run(a.tools / "checkfc", "-s", se / "precompiled_sepolicy", services)
    contexts = se / "vendor_file_contexts"
    contexts.write_text(contexts.read_text() + "\n/vendor/bin/ruby-usb-log u:object_r:ruby_usb_log_exec:s0\n"
                        "/dev/ruby-log-stream u:object_r:ruby_usb_log_pipe:s0\n")
    # Opt-in disposable VM check, excluded from the ordinary USB candidate.
    # Use the production HAL domain and policy without adding test permissions.
    fmq_test = None
    if a.camera_fmq_test:
        source = HERE / "camera-fmq-test.c"
        binary = vendor / "bin/openbook-camera-fmq-test"
        run("gcc", "-static", "-O2", "-Wall", "-Wextra", "-Werror", source, "-o", binary)
        contexts.write_text(contexts.read_text() +
                           "/vendor/bin/openbook-camera-fmq-test u:object_r:hal_camera_default_exec:s0\n")
        (vendor / "etc/init/openbook-camera-fmq-test.rc").write_text('''service openbook.camera-fmq-test /vendor/bin/openbook-camera-fmq-test
    class hal
    user cameraserver
    group camera
    oneshot
''')
        fmq_test = {"source_sha256": audit.sha(source), "binary_sha256": audit.sha(binary),
                    "expected_domain": "hal_camera_default", "expected_exit_status": 0,
                    "scope": "disposable VM only; no video device or frames"}
        # Built explicitly as a native test, absent from ordinary vendor images.
        buffer_source = HERE.parents[1] / "device/anybook/common/pc/camera/camera-buffer-test.cpp"
        buffer_built = a.product / "data/nativetest64/vendor/openbook-camera-buffer-test/openbook-camera-buffer-test"
        if not buffer_built.is_file():
            raise ValueError("Build openbook-camera-buffer-test in the AOSP lane before --camera-fmq-test")
        buffer_binary = vendor / "bin/openbook-camera-buffer-test"
        shutil.copyfile(buffer_built, buffer_binary)
        buffer_binary.chmod(0o755)
        contexts.write_text(contexts.read_text() +
                           "/vendor/bin/openbook-camera-buffer-test u:object_r:hal_camera_default_exec:s0\n")
        (vendor / "etc/init/openbook-camera-buffer-test.rc").write_text('''service openbook.camera-buffer-test /vendor/bin/openbook-camera-buffer-test
    class late_start
    user cameraserver
    group audio camera input drmrpc usb
    oneshot
''')
        fmq_test["buffer_test"] = {
            "source_sha256": audit.sha(buffer_source), "binary_sha256": audit.sha(buffer_binary),
            "expected_exit_status": 0, "scope": "synthetic YUV allocation, import, CPU write/read"}
    run(a.tools / "checkfc", se / "precompiled_sepolicy", contexts)
    for part, root in (("plat", a.ruby / "fs/system_a/system"), ("system_ext", a.ruby / "fs/system_ext_a"),
                       ("product", a.ruby / "fs/product_a")):
        shutil.copyfile(root / f"etc/selinux/{part}_sepolicy_and_mapping.sha256",
                        se / f"precompiled_sepolicy.{part}_sepolicy_and_mapping.sha256")
    # Diagnostic service writes to the VM serial console, without a root shell.
    # It is intentionally limited to local logs and public service/property state.
    (vendor / "etc/init/ruby-probe.rc").write_text('''on init
    chown root shell /dev/ttyS0
    chmod 0660 /dev/ttyS0

service openbook.ruby.probe /system/bin/sh /vendor/etc/ruby-probe.sh
    class core
    user shell
    group shell system log readproc
    seclabel u:r:shell:s0
    console ttyS0
    oneshot
''')
    (vendor / "etc/init/ruby-usb-log.rc").write_text('''on early-init && property:ro.boot.openbook.ruby_logs=1
    start ruby-usb-log

on property:ro.boot.openbook.ruby_logs=1
    start ruby-usb-log-collect

service ruby-usb-log /vendor/bin/ruby-usb-log --collect
    user root
    group root
    capabilities SYSLOG
    disabled
    oneshot

service ruby-usb-log-collect /system/bin/sh /vendor/etc/ruby-usb-log-collect.sh
    user shell
    group shell system log readproc
    seclabel u:r:shell:s0
    disabled
    oneshot
''')
    shutil.copyfile(HERE / "usb-log-collect.sh", vendor / "etc/ruby-usb-log-collect.sh")
    (vendor / "etc/ruby-probe.sh").write_text('''#!/system/bin/sh
sleep 20
for checkpoint in 1 2 3 4 5 6 7 8 9 10 11 12; do
echo OPENBOOK_RUBY_PROBE_BEGIN
echo OPENBOOK_RUBY_CHECKPOINT=$checkpoint
id
getenforce
echo OPENBOOK_RUBY_BOOT_COMPLETED=$(getprop sys.boot_completed)
echo init.svc.vendor.camera.provider-ext=$(getprop init.svc.vendor.camera.provider-ext)
timeout 8 service check android.hardware.camera.provider.ICameraProvider/external/0
timeout 8 dumpsys media.camera
service list
echo OPENBOOK_RUBY_PROBE_DISKS
ls -l /dev/block/by-name
cat /proc/mounts
echo OPENBOOK_RUBY_PROBE_PROCESSES
ps -A
echo OPENBOOK_RUBY_PROBE_DISPLAY
dumpsys SurfaceFlinger --display-id
dumpsys window | grep -E 'mCurrentFocus|mFocusedApp|mDisplayEnabled|mScreenOn'
echo OPENBOOK_RUBY_PROBE_MODULES
cat /proc/modules
echo OPENBOOK_RUBY_PROBE_LOGCAT
logcat -b crash -d -v threadtime
logcat -b all -d -v brief -t 400
echo OPENBOOK_RUBY_PROBE_END
[ "$checkpoint" = 12 ] || sleep 30
done
''')
    # Vendor contexts alone omit platform defaults such as vendor_file and
    # vendor_apex_file. Preserve the original product's applicable label rules;
    # unrelated platform executable types can differ in the retained framework.
    context = w / "file_contexts"
    context_inputs = [a.product / "system/etc/selinux/plat_file_contexts",
                      a.product / "system_ext/etc/selinux/system_ext_file_contexts",
                      a.product / "product/etc/selinux/product_file_contexts", contexts]
    paths = ["/vendor"] + ["/vendor/" + str(p.relative_to(vendor)) for p in vendor.rglob("*")]
    context.write_text(vendor_contexts("\n".join(p.read_text() for p in context_inputs if p.exists()), paths))
    run(a.tools / "checkfc", se / "precompiled_sepolicy", context)
    label_tests = w / "file-context-tests.txt"
    label_tests.write_text("/vendor vendor_file\n/vendor/etc/ueventd.rc vendor_configs_file\n"
                           "/vendor/apex vendor_apex_file\n/vendor/bin/ruby-usb-log ruby_usb_log_exec\n"
                           "/vendor/bin/hw/android.hardware.camera.provider-V1-external-service hal_camera_default_exec\n"
                           "/vendor/firmware openbook_vendor_fw_file\n"
                           "/vendor/firmware/amdgpu/psp_14_0_0_toc.bin openbook_vendor_fw_file\n")
    if fmq_test:
        with label_tests.open("a") as f:
            f.write("/vendor/bin/openbook-camera-fmq-test hal_camera_default_exec\n")
            f.write("/vendor/bin/openbook-camera-buffer-test hal_camera_default_exec\n")
    with (w / "file-context-tests.log").open("wb") as log:
        check = subprocess.run([str(a.tools / "checkfc"), "-t", str(context), str(label_tests)],
                               stdout=log, stderr=subprocess.STDOUT)
    # checkfc.c returns 2 for unused rules in this focused test; mismatches and
    # lookup/parse failures return 1. All rules were policy-validated above.
    if check.returncode not in (0, 2):
        raise ValueError("Vendor label regression; see file-context-tests.log")
    vendor_img = w / "vendor.img"
    run(a.tools / "mkfs.erofs", "-zlz4hc,9", "-T", "1792368000", "--mount-point=vendor",
        f"--product-out={a.product}", f"--file-contexts={context}", vendor_img, vendor)
    run(a.tools / "fsck.erofs", "--extract", vendor_img)
    run(a.tools / "avbtool", "add_hashtree_footer", "--image", vendor_img, "--partition_name", "vendor",
        "--partition_size", gpt.round_up(vendor_img.stat().st_size + 16 * MiB, MiB),
        "--do_not_generate_fec", "--hash_algorithm", "sha256")
    images = {n: a.ruby / f"super/{n}_a.img" for n in ("system", "system_ext", "product")}
    images.update(vendor=vendor_img, vendor_dlkm=a.kernel / f"{a.variant}/vendor_dlkm.img",
                  system_dlkm=a.kernel / "system_dlkm.flatten.erofs.img")
    for src in images.values():
        if not src.is_file() or src.is_symlink():
            raise ValueError(f"Expected regular image: {src}")
    hashes = {n: audit.sha(src) for n, src in images.items()}
    vbmeta = w / "vbmeta.img"
    cmd = [a.tools / "avbtool", "make_vbmeta_image", "--algorithm", "SHA256_RSA4096", "--key", a.key,
           "--padding_size", "4096", "--output", vbmeta]
    for src in images.values():
        cmd += ["--include_descriptors_from_image", src]
    run(*cmd)
    digest = subprocess.check_output([str(a.tools / "avbtool"), "calculate_vbmeta_digest", "--image", str(vbmeta),
                                      "--hash_algorithm", "sha256"], text=True).strip()
    info = subprocess.check_output([str(a.tools / "avbtool"), "info_image", "--image", str(vbmeta)], text=True)
    vbsize = sum(map(int, re.findall(r"(?:Header|Authentication|Auxiliary) Block:\s+(\d+) bytes", info)))
    sizes = {n: gpt.round_up(p.stat().st_size, 4096) for n, p in images.items()}
    ssize = gpt.round_up(sum(sizes.values()) + 64 * MiB, 64 * MiB)
    super_img = w / "super.img"
    cmd = [a.tools / "lpmake", "--metadata-size", "65536", "--metadata-slots", "2", "--super-name", "super",
           "--device", f"super:{ssize}", "--group", f"ruby_probe_a:{ssize - 4 * MiB}", "--output", super_img]
    for n, src in images.items():
        cmd += ["--partition", f"{n}_a:readonly:{sizes[n]}:ruby_probe_a", "--image", f"{n}_a={src}"]
    run(*cmd)
    # Existing matched G14 kernel/modules; OpenBook first-stage fstab and generic init.
    for name in ("boot", "init_boot"):
        run(a.tools / "unpack_bootimg", "--boot_img", a.product / f"{name}.img", "--out", w / name,
            stdout=subprocess.DEVNULL)
    vendor_cmdline = unpack_vendor(a.tools / "unpack_bootimg", a.product / "vendor_boot.img", w / "vendor_boot")
    if audit.sha(w / "boot/kernel") != audit.sha(a.kernel / "bzImage"):
        raise ValueError("PRODUCT_OUT boot kernel does not match the selected G14 dist")
    layout = [("misc", 4 * MiB, gpt.LINUX_DATA, None),
              ("boot_a", 64 * MiB, gpt.LINUX_DATA, str(a.product / "boot.img")),
              ("init_boot_a", 8 * MiB, gpt.LINUX_DATA, str(a.product / "init_boot.img")),
              ("vendor_boot_a", 64 * MiB, gpt.LINUX_DATA, str(a.product / "vendor_boot.img")),
              ("vbmeta_a", MiB, gpt.VBMETA_TYPE, str(vbmeta)),
              ("metadata", 64 * MiB, gpt.LINUX_DATA, None),
              ("super", ssize, gpt.LINUX_DATA, str(super_img)),
              ("userdata", 8192 * MiB, gpt.LINUX_DATA, None)]
    disk = w / "probe.img"
    g = gpt.Gpt(layout, "ruby-openbook-local-probe")
    g.write(str(disk))
    run("sgdisk", "-v", disk)
    if hashes != {n: audit.sha(src) for n, src in images.items()}:
        raise ValueError("Source image changed during assembly")
    params = bc.parse_text((w / "vendor_boot/bootconfig").read_text())
    params.update({"androidboot.slot_suffix": "_a", "androidboot.force_normal_boot": "1",
                   "androidboot.boot_devices": "pci0000:00/0000:00:04.0", "androidboot.console": "ttyS0",
                   "androidboot.serialconsole": "1", "androidboot.verifiedbootstate": "orange",
                   "androidboot.vbmeta.device_state": "unlocked", "androidboot.veritymode": "enforcing",
                   "androidboot.vbmeta.avb_version": "1.2", "androidboot.vbmeta.hash_alg": "sha256",
                   "androidboot.vbmeta.digest": digest, "androidboot.vbmeta.size": str(vbsize),
                   "androidboot.serialno": "OPENBOOKRUBYVM01", "androidboot.selinux": "enforcing"})
    initrd = w / "initrd.img"
    with initrd.open("xb") as f:
        for p in sorted((w / "vendor_boot").glob("vendor_ramdisk*")):
            f.write(p.read_bytes())
        f.write((w / "init_boot/ramdisk").read_bytes())
        f.write(gpt.bootconfig_trailer(bc.render(params).decode(), f.tell()))
    recipe = {"schema": "openbook-ruby-vm-probe/1", "installable": False,
              "scope": "Local VM experiment; not a Googlebook installer source", "source_sha256": hashes,
              "kernel_sha256": audit.sha(a.kernel / "bzImage"), "module_variant": a.variant,
              "vendor_cmdline": vendor_cmdline,
              "wifi_overlay": wifi,
              "zram_init_sha256": audit.sha(audit.ZRAM_INIT),
              "camera": camera,
              "camera_fmq_test": fmq_test,
              "bootconfig": params, "gpt": g.table(),
              "avb": "local test-key root, unlocked/orange; retained Google logical image descriptors",
              "usb_logger_sha256": audit.sha(vendor / "bin/ruby-usb-log"),
              "file_contexts_sha256": audit.sha(context),
              "policy": "strictly compiled hybrid; six OpenBook grants removed; scoped serial and USB diagnostic domains; enforcing requested"}
    (w / "recipe.json").write_text(json.dumps(recipe, indent=2) + "\n")
    return w


def boot(a, w):
    recipe = json.loads((w / "recipe.json").read_text())
    vendor_cmdline = platform_cmdline(recipe.get("vendor_cmdline", ""))
    cmd = ["qemu-system-x86_64", "-machine", "q35", "-accel", "kvm", "-cpu", "host", "-smp", "4", "-m", "8192",
           "-kernel", str(w / "boot/kernel"), "-initrd", str(w / "initrd.img"),
           "-append", vendor_cmdline + " bootconfig console=ttyS0,115200 8250.nr_uarts=1 earlycon=uart8250,io,0x3f8,115200 printk.devkmsg=on panic=-1",
           "-drive", f"file={w}/probe.img,format=raw,if=none,id=d0,snapshot=on",
           "-device", "nvme,drive=d0,serial=RUBYPROBE,addr=0x4", "-device", "virtio-vga",
           "-display", "none", "-nic", "none", "-serial", f"file:{w}/serial.log", "-monitor", "none", "-no-reboot"]
    print("Starting isolated Ruby/OpenBook KVM probe...", flush=True)
    start = time.monotonic()
    with (w / "qemu.log").open("wb") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        timed_out = False
        try:
            proc.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    text = (w / "serial.log").read_text(errors="replace")
    result = {"elapsed_s": round(time.monotonic() - start, 1), "qemu_exit": proc.returncode,
              "observation_window_elapsed": timed_out, "first_stage_switch_root": "Switching root to" in text,
              "second_stage_init": "init second stage started" in text,
              "diagnostics_completed": "OPENBOOK_RUBY_PROBE_END" in text,
              "kernel_panic": "Kernel panic" in text,
              "boot_completed_reported": "OPENBOOK_RUBY_BOOT_COMPLETED=1" in text,
              "scope": "Milestone observations only. Service registration and boot_completed require log review."}
    (w / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("ruby", "product", "tools", "kernel", "audit", "key", "out"):
        p.add_argument("--" + n, type=Path, required=True)
    p.add_argument("--timeout", type=int, default=180, choices=range(30, 601), metavar="30..600")
    p.add_argument("--variant", choices=("vm", "bm"), default="vm")
    p.add_argument("--camera-fmq-test", action="store_true",
                   help="Add camera-domain memfd/YUV-buffer tests to a disposable VM; never deploy this image")
    p.add_argument("--prepare-only", action="store_true", help="Assemble only; use run-probe.py for a separate observation")
    a = p.parse_args()
    for n in ("ruby", "product", "tools", "kernel", "audit", "key"):
        setattr(a, n, getattr(a, n).resolve(strict=True))
    w = prepare(a)
    if not a.prepare_only:
        boot(a, w)


if __name__ == "__main__":
    main()
