#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Probe a pinned audio APEX before/after a temporary policy bind in Cuttlefish.

Never connects to LAN adb. The caller owns the disposable container lifecycle.
The probe creates synthetic HFP sessions; this does not test a controller/headset.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--container", required=True)
p.add_argument("--probe", type=Path, required=True)
p.add_argument("--policy", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
if not a.container.startswith("openbook-audio-test-"):
    p.error("Disposable audio-test container required")
a.out.mkdir(mode=0o700, exist_ok=False)
prefix = ["docker", "exec", "-e", "PATH=/root/cvd-host/bin:/usr/bin:/bin",
          a.container, "adb", "-s", "127.0.0.1:6520"]


def adb(*args, check=True):
    return subprocess.run(prefix + list(args), capture_output=True, text=True,
                          check=check, timeout=70)


def push(src, dst):
    subprocess.run(["docker", "cp", str(src), a.container + ":/tmp/audio-probe-input"],
                   check=True)
    adb("push", "/tmp/audio-probe-input", dst)


def probe(name):
    r = adb("shell", "timeout", "60", "/data/local/tmp/hfp-hal-test", "--disposable-vm",
            check=False)
    (a.out / (name + ".txt")).write_text(r.stdout + r.stderr)
    return r


adb("root")
time.sleep(2)
assert adb("shell", "getprop", "ro.product.board").stdout.strip() == "cutf"
assert adb("shell", "getenforce").stdout.strip() == "Enforcing"
apex = adb("shell", "sha256sum", "/vendor/apex/com.android.hardware.audio.apex").stdout.split()[0]
assert apex == "dca81a647aa21f6d91f2d7250b00a775b6ab6403cd040a2ded3ce49bcca2fa03"
push(a.probe, "/data/local/tmp/hfp-hal-test")
adb("shell", "chmod", "755", "/data/local/tmp/hfp-hal-test")
baseline = probe("before")
assert baseline.returncode == 1 and "SCO control interface exposed" in baseline.stderr + baseline.stdout
target = "/vendor/etc/bluetooth_with_le_audio_policy_configuration_7_0.xml"
before = adb("shell", "cat", target).stdout
(a.out / "before-policy.xml").write_text(before)
push(a.policy, "/data/local/tmp/sco-policy.xml")
adb("shell", "chcon", "u:object_r:vendor_configs_file:s0", "/data/local/tmp/sco-policy.xml")
adb("shell", "mount", "--bind", "/data/local/tmp/sco-policy.xml", target)
try:
    adb("shell", "setprop", "ctl.restart", "vendor.audio-hal-aidl")
    time.sleep(8)
    after = probe("after")
    log = adb("logcat", "-d", "-s", "AHAL_ModuleBluetooth", "BTAudioProviderHfpSW",
              "AHAL_BluetoothAudioPort", "DEBUG:E").stdout
    (a.out / "hal-log.txt").write_text(log)
    assert after.returncode == 0, after.stdout + after.stderr
    assert "PASS 12 SCO route/stream cases" in after.stdout
    assert adb("shell", "getenforce").stdout.strip() == "Enforcing"
    result = dict(audio_apex_sha256=apex, baseline_missing_sco=True,
                  policy_sha256=hashlib.sha256(a.policy.read_bytes()).hexdigest(),
                  probe_sha256=hashlib.sha256(a.probe.read_bytes()).hexdigest(),
                  stream_cases=12, hfp_rates=[8000, 16000, 32000],
                  enforcing=True, synthetic_stack=True, physical_radio_tested=False,
                  audio_frames_tested=False)
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
finally:
    adb("shell", "umount", target)
    adb("shell", "setprop", "ctl.restart", "vendor.audio-hal-aidl")
print("SCO provider/session/route/stream tests passed on the exact retained APEX.")
