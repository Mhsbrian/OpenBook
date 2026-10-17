#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Where a WAV file carries a steady tone: what the QEMU audio test's guest played into QEMU's HDA codec
(scripts/audio-net-qemu.sh). Scans 50 ms windows of the first channel for the tone frequency (Goertzel) and
prints the stretches where it is at least half of the energy and above -60 dBFS, as JSON.

usage: wav-tone.py FILE.wav [--freq 1000]
"""
import argparse
import json
import math
import struct
import wave


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--freq", type=float, default=1000)
    a = ap.parse_args()
    w = wave.open(a.wav)
    rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    if width != 2:
        raise SystemExit(f"{a.wav}: {8 * width}-bit samples; only 16-bit is handled")
    raw = w.readframes(n)
    x = struct.unpack(f"<{len(raw) // 2}h", raw)[::ch]
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
