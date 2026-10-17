#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Where a WAV file carries a steady tone: what the QEMU audio test's guest played into QEMU's HDA codec
(scripts/audio-net-qemu.sh). Scans 50 ms windows of the first channel for the tone frequency (Goertzel) and
prints the stretches where it is at least half of the energy and above -60 dBFS, as JSON. QEMU leaves the RIFF and
data sizes at 0 when the guest powers off, so the samples are taken to run from the data chunk to the end of the file.

usage: wav-tone.py FILE.wav [--freq 1000]
"""
import argparse
import json
import math
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--freq", type=float, default=1000)
    a = ap.parse_args()
    b = open(a.wav, "rb").read()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise SystemExit(f"{a.wav}: not a WAV file")
    at, fmt, data = 12, None, None
    while at + 8 <= len(b):
        cid, size = b[at:at + 4], struct.unpack("<I", b[at + 4:at + 8])[0]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", b[at + 8:at + 24])
        if cid == b"data":
            data = b[at + 8:] if size == 0 else b[at + 8:at + 8 + size]
            break
        at += 8 + size + (size & 1)
    if not fmt or data is None:
        raise SystemExit(f"{a.wav}: no fmt or data chunk")
    _, ch, rate, _, _, bits = fmt
    if bits != 16:
        raise SystemExit(f"{a.wav}: {bits}-bit samples; only 16-bit is handled")
    data = data[:len(data) // (2 * ch) * 2 * ch]
    n = len(data) // (2 * ch)
    x = struct.unpack(f"<{len(data) // 2}h", data)[::ch]
    win = rate // 20
    coeff = 2 * math.cos(2 * math.pi * a.freq / rate)
    runs, cur = [], None
    for i in range(0, len(x) - win + 1, win):
        s1 = s2 = tot = 0.0
        for v in x[i:i + win]:
            f = v / 32768.0
            tot += f * f
            s1, s2 = f + coeff * s1 - s2, s1
        power = s1 * s1 + s2 * s2 - coeff * s1 * s2
        rms, tone = math.sqrt(tot / win), math.sqrt(2 * max(power, 0)) / win
        on = rms > 1e-3 and tone * tone >= 0.5 * rms * rms
        t = i / rate
        if on and cur is None:
            cur = {"start_s": round(t, 2), "levels": []}
        if on:
            cur["levels"].append(tone)
        if not on and cur is not None:
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)
    out = []
    for r in runs:
        lv = r.pop("levels")
        r["seconds"] = round(len(lv) * win / rate, 2)
        r["tone_rms_dbfs"] = round(20 * math.log10(sum(lv) / len(lv)), 1)
        if r["seconds"] >= 0.5:
            out.append(r)
    print(json.dumps({"file": a.wav, "rate": rate, "channels": ch, "seconds": round(n / rate, 2), "freq": a.freq,
                      "tone_runs": out}, indent=1))


if __name__ == "__main__":
    main()
