#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarize Audio Check reports without publishing identifiers or raw rows.

Only aggregate route/profile observations and capacity are emitted. Absence of a
sampled event is not proof it never happened between samples. This cannot measure
underruns, RF quality, packet loss or the identity of another app's recording.
"""
import argparse
import json
from pathlib import Path

MAX_BYTES = 4 * 1024 * 1024


def summarize(rows):
    if not rows or rows[0].get("schema") != "openbook-audio-diagnostic/1":
        raise ValueError("Unsupported or missing Audio Check schema")
    elapsed = [r["elapsed_ms"] for r in rows]
    if any(type(t) is not int or t < 0 for t in elapsed) or elapsed != sorted(elapsed):
        raise ValueError("Invalid elapsed-time sequence")
    snapshots = [r for r in rows if "devices" in r and "access_error" not in r]
    permitted = [r for r in snapshots if r.get("bluetooth_permission") is True]
    # Allow only known labels, never forward arbitrary input strings.
    allowed = {"speaker", "built_in_mic", "bluetooth_a2dp", "bluetooth_sco",
               "ble_headset", "wired_headset", "type_25"}
    label = lambda d: d.get("type") if d.get("type") in allowed else "other"
    devices = sorted({label(d) for r in snapshots for d in r["devices"]})
    comm = sorted({label(d) for r in snapshots
                   for d in r.get("available_communication_devices", [])})
    recordings = [c for r in snapshots for c in r.get("recording_metadata_visible_to_app", [])
                  if isinstance(c.get("device"), dict)]
    profile_rows = {
        name: [p for r in permitted for p in r.get("profiles", []) if p.get("profile") == name]
        for name in ("HFP", "A2DP", "LE_AUDIO")}
    profiles = {name: {
        "observations": len(ps),
        "connection_states_observed": sorted({p["connection_state"] for p in ps}),
        "audio_connected_counts_observed": sorted({p["audio_connected_count"] for p in ps
                                                  if "audio_connected_count" in p}),
    } for name, ps in profile_rows.items()}
    storage = next((r for r in rows if r.get("event") == "storage"), {})
    size = lambda v: v if type(v) is int and v >= 0 else None
    no_headset_route = bool(snapshots) and all(
        not any(label(d) in ("bluetooth_sco", "ble_headset")
                for d in r.get("available_communication_devices", [])) for r in snapshots)
    return {
        "schema": "openbook-audio-report-summary/1",
        "duration_ms": elapsed[-1],
        "rows": len(rows), "snapshots": len(snapshots),
        "clean_stop": rows[-1].get("event") == "stop",
        "access_errors": sum("access_error" in r for r in rows),
        "bluetooth_permitted_snapshots": len(permitted),
        "device_types_observed": devices,
        "available_communication_types_observed": comm,
        "no_bluetooth_communication_route_observed": no_headset_route if snapshots else None,
        "audio_modes_observed": sorted({r["mode"] for r in snapshots}),
        "recording_device_types_observed": sorted({label(c["device"]) for c in recordings}),
        "recording_observations": len(recordings),
        "recording_unsilenced_observations": sum(c.get("silenced") is False for c in recordings),
        "profiles": profiles,
        "a2dp_playing_events": sum(
            r.get("event") == "bluetooth_event"
            and r.get("action") == "android.bluetooth.a2dp.profile.action.PLAYING_STATE_CHANGED"
            and r.get("state") == 10 for r in rows),
        "marked_problems": sum(r.get("event") == "user_marked_problem" for r in rows),
        "storage": {
            "data_total_bytes": size(storage.get("data_filesystem", {}).get("total_bytes")),
            "data_available_bytes": size(storage.get("data_filesystem", {}).get("available_bytes")),
            "android_total_bytes": size(storage.get("android_storage_total_bytes")),
        },
        "limits": ["No audio content or underrun/RF measurements",
                   "Recording app identity unavailable; event gaps may hide transitions",
                   "Communication route is not a measurement of media playback routing"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    if args.report.stat().st_size > MAX_BYTES:
        parser.error("Report exceeds 4 MiB")
    print(json.dumps(summarize([json.loads(line) for line in args.report.read_text().splitlines()]),
                     indent=2))
