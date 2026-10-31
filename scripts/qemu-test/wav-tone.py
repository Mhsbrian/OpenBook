#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Where a WAV file carries a steady tone: what the QEMU audio test's guest played into QEMU's HDA codec
(scripts/audio-net-qemu.sh). Scans 50 ms windows of the first channel for the tone frequency (Goertzel) and
prints the stretches where it is at least 30% of the energy and above -60 dBFS, as JSON, with how many windows
fall under 90% (glitches). QEMU leaves the RIFF and
data sizes at 0 when the guest powers off, so the samples are taken to run from the data chunk to the end of the file.

--activity instead lists every stretch of sound above -50 dBFS (any signal, e.g. a UI sound effect), gaps under
0.2 s bridged, with its peak and RMS level.

usage: wav-tone.py FILE.wav [--freq 1000 | --activity]
"""
import argparse
import json
import math
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--freq", type=float, default=1000)
    ap.add_argument("--activity", action="store_true")
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
    if a.activity:
        return activity(a.wav, x, rate, ch, n, win)
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
        share = tone * tone / (rms * rms) if rms > 0 else 0
        on = rms > 1e-3 and share >= 0.3
        t = i / rate
        if on and cur is None:
            cur = {"start_s": round(t, 2), "levels": [], "shares": []}
        if on:
            cur["levels"].append(tone)
            cur["shares"].append(share)
        if not on and cur is not None:
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)
    out = []
    for r in runs:
        lv, sh = r.pop("levels"), r.pop("shares")
        r["seconds"] = round(len(lv) * win / rate, 2)
        r["tone_rms_dbfs"] = round(20 * math.log10(sum(lv) / len(lv)), 1)
        # A clean tone keeps every 50 ms window near 1; broken phase (dropped buffers) pulls windows down.
        r["window_share_mean"] = round(sum(sh) / len(sh), 3)
        r["glitched_windows"] = sum(1 for x in sh if x < 0.9)
        if r["seconds"] >= 0.5:
            out.append(r)
    print(json.dumps({"file": a.wav, "rate": rate, "channels": ch, "seconds": round(n / rate, 2), "freq": a.freq,
                      "tone_runs": out}, indent=1))


def activity(path, x, rate, ch, n, win):
    runs, cur, quiet = [], None, 0
    for i in range(0, len(x) - win + 1, win):
        w = x[i:i + win]
        rms = math.sqrt(sum((v / 32768.0) ** 2 for v in w) / win)
        peak = max(abs(v) for v in w) / 32768.0
        if rms > 10 ** (-50 / 20):
            if cur is None:
                cur = {"start_s": round(i / rate, 2), "end": i, "rms": [], "peak": 0.0}
            cur["end"], quiet = i + win, 0
            cur["rms"].append(rms)
            cur["peak"] = max(cur["peak"], peak)
        elif cur is not None:
            quiet += 1
            if quiet * win >= rate // 5:
                runs.append(cur)
                cur = None
    if cur is not None:
        runs.append(cur)
    out = [{"start_s": r["start_s"], "seconds": round((r["end"] - r["start_s"] * rate) / rate, 2),
            "peak_dbfs": round(20 * math.log10(r["peak"]), 1),
            "rms_dbfs": round(20 * math.log10(math.sqrt(sum(v * v for v in r["rms"]) / len(r["rms"]))), 1)}
           for r in runs]
    print(json.dumps({"file": path, "rate": rate, "channels": ch, "seconds": round(n / rate, 2), "sounds": out},
                     indent=1))


if __name__ == "__main__":
    main()
