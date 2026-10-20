#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run exact-build Bionic library probes without a device or Android services.

The two library hashes bind the native probe's converter-layout assumptions.
Host must support the instruction set reached by the probe. No image execution
qualification follows from this small userspace test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

p=argparse.ArgumentParser(description=__doc__)
for name in ("probe","ruby-system","apexes","patched-library","output"):
    p.add_argument("--"+name,type=Path,required=True)
a=p.parse_args()
paths=[a.apexes/"com.android.runtime/lib64/bionic",a.ruby_system/"lib64",
       *sorted(a.apexes.glob("*/lib64"))]
rows=[]
for mode,lib,wanted in (
    ("reset",a.ruby_system/"lib64/libinputflinger.so",
     "e27014ec1e2e4d611cdd6df2c1175d86d679d1353ee970f190e831953fbcb3e4"),
    ("preserve",a.patched_library,
     "4752d1351dbed7f0b5cb5a1d31d409edbb91396c6627fd7b34e1e99a0e655148")):
    if hashlib.sha256(lib.read_bytes()).hexdigest()!=wanted:
        raise ValueError("Native layout probe requires its exact reviewed library")
    result=subprocess.run([str((a.apexes/"com.android.runtime/bin/linker64").resolve()),
        str(a.probe.resolve()),str(lib.resolve()),mode],
        env={**os.environ,"LD_LIBRARY_PATH":":".join(map(str,paths))},
        capture_output=True,text=True,timeout=30)
    rows.append(dict(mode=mode,library_sha256=wanted,exit_code=result.returncode,
                     stdout=result.stdout,stderr=result.stderr))
with a.output.open("x") as f: json.dump(rows,f,indent=2); f.write("\n")
if not all(r["exit_code"]==0 and r["stdout"].count("pass=1")==4 for r in rows):
    raise SystemExit("Native input controls failed; see output")
print("Both exact-build converter probes and six retained-library drag controls passed.")
