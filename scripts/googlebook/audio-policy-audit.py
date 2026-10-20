#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read policy declarations without claiming hardware/profile availability."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def audit(directory):
    seen, modules = {}, []

    def visit(name):
        if Path(name).name != name:
            raise ValueError("Policy includes must be local filenames")
        if name in seen:
            return
        data = (directory / name).read_bytes()
        seen[name] = hashlib.sha256(data).hexdigest()
        root = ET.fromstring(data)
        for inc in root.iter("{http://www.w3.org/2001/XInclude}include"):
            visit(inc.attrib["href"])
        for module in root.iter("module"):
            ports = {p.attrib["tagName"]: p.attrib["type"] for p in module.findall("devicePorts/devicePort")}
            routes = module.findall("routes/route")
            routed = set()
            for route in routes:
                routed.add(route.attrib["sink"])
                routed.update(route.attrib["sources"].split(","))
            modules.append(dict(name=module.attrib["name"], declared_types=sorted(set(ports.values())),
                                routed_types=sorted({t for name, t in ports.items() if name in routed})))

    visit("audio_policy_configuration.xml")
    types = {t for m in modules for t in m["routed_types"]}
    return dict(schema="openbook-audio-policy-audit/1", files=seen, modules=modules,
                classic_sco_input="AUDIO_DEVICE_IN_BLUETOOTH_SCO_HEADSET" in types,
                classic_sco_output=bool(types & {"AUDIO_DEVICE_OUT_BLUETOOTH_SCO",
                    "AUDIO_DEVICE_OUT_BLUETOOTH_SCO_HEADSET", "AUDIO_DEVICE_OUT_BLUETOOTH_SCO_CARKIT"}),
                le_audio_input="AUDIO_DEVICE_IN_BLE_HEADSET" in types,
                a2dp_playback="AUDIO_DEVICE_OUT_BLUETOOTH_A2DP" in types,
                scope="Static declarations only; no radio, codec negotiation or call route measured")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vendor-etc", type=Path, required=True)
    p.add_argument("--system-properties", type=Path)
    a = p.parse_args()
    result = audit(a.vendor_etc)
    if a.system_properties:
        key = "bluetooth.hfp.software_datapath.enabled"
        result[key] = next((line.split("=", 1)[1] for line in a.system_properties.read_text().splitlines()
                            if line.startswith(key + "=")), None)
    print(json.dumps(result, indent=2))
