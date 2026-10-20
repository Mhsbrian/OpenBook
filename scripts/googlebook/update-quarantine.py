#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact-build guard for a failed containment experiment; never deploy."""
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STOCK_RC = """# LINT.IfChange
service update_engine /system/bin/update_engine --logtostderr --logtofile --foreground
    class late_start
    user root
    group root system wakelock inet cache media_rw
    task_profiles OtaProfiles
    disabled

on property:ro.boot.slot_suffix=*
    enable update_engine
# LINT.ThenChange(update_engine_nostats.rc)
"""


def prepare(ruby, vendor):
    original = ruby / "fs/system_a/system/etc/init/update_engine.rc"
    if original.read_text() != STOCK_RC:
        raise ValueError("Unknown update_engine init contract; experiment refused")
    for path in vendor.glob("etc/init/*.rc"):
        if "service update_engine " in path.read_text():
            raise ValueError("Conflicting vendor update_engine definition")
    fragment = REPO / "config/image-bases/ruby-update-quarantine.rc"
    target = vendor / "etc/init/ruby-update-quarantine.rc"
    with target.open("xb") as stream:
        stream.write(fragment.read_bytes())
    return {"scope": "experimental auto-start suppression; privileged restart/downloads/recovery uncontained",
            "stock_rc_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
            "override_sha256": hashlib.sha256(fragment.read_bytes()).hexdigest(),
            "unattended_safe": False, "deployment_eligible": False}
