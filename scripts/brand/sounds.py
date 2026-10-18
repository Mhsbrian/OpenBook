#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""OpenBook's sound set, synthesised from scratch: one ringtone, one notification, one alarm and the UI sounds
Android plays on a laptop (lock, unlock, trusted device, low battery, charging). Every sound uses the same voice, a
soft glass mallet (a struck bar's partials with a short felt transient, in a small room), and the same motif, the
notes of D major 9 rising (D A E F#), so the set sounds like one family.

Output: assets/sounds/{ringtones,notifications,alarms,ui}/OpenBook_*.ogg (Vorbis, 48 kHz, with TITLE and
ANDROID_LOOP tags) and assets/sounds/sounds.json (duration, loudness, peak, and the PCM digest that --check uses).
Levels follow AOSP's own files: ringtone, alarm and notification near -16 LUFS; UI sounds peak about -10 dBFS.
Needs ffmpeg with libvorbis.

usage: sounds.py [--out DIR] [--wav DIR] [--only NAME ...]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brandlib import ASSETS, rng, write_json  # noqa: E402

SR = 48000
A4 = 440.0
NOTES = {"C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4, "F#": -3, "G": -2, "G#": -1, "A": 0, "A#": 1,
         "B": 2}


def hz(note):
    """'F#5' -> frequency."""
    name, octave = note[:-1], int(note[-1])
    return A4 * 2.0 ** ((NOTES[name] + 12 * (octave - 4)) / 12.0)


def mallet(note, dur=1.6, vel=1.0, bright=1.0, bell=0.0, seed="m"):
    """One struck note. bright scales the upper partials; bell adds inharmonic glass partials."""
    f0 = hz(note)
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float64) / SR
    out = np.zeros(n)
    # marimba-like tuned bar (1, 4, 10) plus a soft octave, each partial a slightly detuned pair
    partials = [(1.0, 1.00, 1.10), (2.0, 0.10 * bright, 0.55), (3.98, 0.22 * bright, 0.32),
                (9.94, 0.05 * bright, 0.11)]
    if bell:
        partials += [(2.76, 0.18 * bell, 0.75), (5.40, 0.08 * bell, 0.40), (8.93, 0.035 * bell, 0.22)]
    # lower notes ring longer
    ring = np.clip((440.0 / f0) ** 0.35, 0.6, 1.6)
    for ratio, amp, tau in partials:
        f = f0 * ratio
        if f > SR * 0.45:
            continue
        env = np.exp(-t / (tau * ring))
        for det in (-0.12, 0.12):
            out += 0.5 * amp * env * np.sin(2 * np.pi * (f + det * ratio) * t)
    # felt transient: a few ms of low-passed noise
    g = rng(f"{seed}:{note}:{dur}")
    k = int(0.006 * SR)
    noise = g.standard_normal(k)
    noise = np.convolve(noise, np.ones(12) / 12.0, mode="same") * np.hanning(2 * k)[k:]
    out[:k] += 0.05 * bright * noise
    # 3 ms raised-cosine attack, so no click
    a = int(0.003 * SR)
    out[:a] *= 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a))
    # and a release over the last third, so a note never stops while it still rings (a click)
    r = n // 3
    out[-r:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, r))
    return vel * out


def pad(notes, dur, vel=0.12, attack=0.6):
    """A soft sustained chord under a phrase."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.minimum(1.0, t / attack) * np.minimum(1.0, (dur - t) / (dur * 0.4))
    out = np.zeros(n)
    for note in notes:
        f = hz(note)
        for det, amp in ((-0.35, 0.5), (0.35, 0.5), (0.0, 0.25)):
            out += amp * np.sin(2 * np.pi * (f + det) * t) + 0.08 * amp * np.sin(2 * np.pi * 2 * (f + det) * t)
    return vel * env * out / len(notes)


def place(track, sound, at):
    i = int(at * SR)
    end = min(len(track), i + len(sound))
    track[i:end] += sound[:end - i]


def room(dry, seed, rt60=1.1, wet=0.2, width=1.0):
    """Stereo room: an exponentially decaying, darkening noise impulse response, convolved by FFT."""
    g = rng(f"room:{seed}")
    n = int(rt60 * 1.3 * SR)
    t = np.arange(n) / SR
    env = np.exp(-6.9 * t / rt60)
    pre = int(0.012 * SR)
    irs = []
    for ch in range(2):
        ir = g.standard_normal(n) * env
        # darken: one-pole low-pass, applied twice
        for _ in range(2):
            y = np.empty_like(ir)
            acc = 0.0
            for i0 in range(0, n, 4096):
                seg = ir[i0:i0 + 4096]
                out = np.empty_like(seg)
                for j, v in enumerate(seg):
                    acc = acc + 0.35 * (v - acc)
                    out[j] = acc
                y[i0:i0 + 4096] = out
            ir = y
        ir = np.concatenate([np.zeros(pre + 37 * ch), ir])
        ir /= np.sqrt(np.sum(ir * ir))
        irs.append(ir)
    m = len(dry) + len(irs[0]) + 64
    nfft = 1 << (m - 1).bit_length()
    D = np.fft.rfft(dry, nfft)
    left = np.fft.irfft(D * np.fft.rfft(irs[0], nfft), nfft)[:m]
    right = np.fft.irfft(D * np.fft.rfft(irs[1], nfft), nfft)[:m]
    dry_p = np.concatenate([dry, np.zeros(m - len(dry))])
    mid = (left + right) / 2.0
    side = (left - right) / 2.0 * width
    return np.stack([dry_p + wet * (mid + side), dry_p + wet * (mid - side)], axis=1)


def trim_tail(x, floor_db=-60.0, fade=0.08):
    """Cut the silent end and fade the last bit out."""
    level = np.max(np.abs(x), axis=1) if x.ndim == 2 else np.abs(x)
    thr = np.max(level) * 10 ** (floor_db / 20.0)
    idx = np.nonzero(level > thr)[0]
    end = int(idx[-1]) + 1 if len(idx) else len(level)
    x = x[:end]
    f = min(len(x), int(fade * SR))
    ramp = np.cos(np.linspace(0, np.pi / 2, f)) ** 2
    x[-f:] = x[-f:] * (ramp[:, None] if x.ndim == 2 else ramp)
    return x


# ------------------------------------------------------------------------------------------------- the sounds
def s_ringtone():
    """Open Pages: the motif rising twice over D and B minor, then resolving; loops."""
    beat = 60.0 / 108
    tr = np.zeros(int(9.6 * SR))
    phrase = [("D5", 0, 1.0), ("A5", 0.5, 0.8), ("E6", 1.0, 0.9), ("F#6", 1.5, 1.0), ("E6", 2.25, 0.7),
              ("C#6", 2.75, 0.75), ("A5", 3.0, 0.8)]
    answer = [("B4", 4.0, 0.9), ("F#5", 4.5, 0.75), ("C#6", 5.0, 0.85), ("D6", 5.5, 0.95), ("C#6", 6.25, 0.7),
              ("A5", 6.75, 0.75), ("D6", 7.0, 1.0)]
    for note, b, v in phrase + answer:
        place(tr, mallet(note, 1.8, v, bright=1.0, bell=0.35, seed="ring"), b * beat)
    place(tr, pad(["D4", "A4", "F#5"], 4.0 * beat + 0.3, 0.10), 0.0)
    place(tr, pad(["B3", "F#4", "D5"], 4.0 * beat + 0.6, 0.10), 4.0 * beat)
    return trim_tail(room(tr, "ring", 1.2, 0.22)), True


def s_notification():
    """Spark: a grace note into a bright held one."""
    tr = np.zeros(int(1.8 * SR))
    place(tr, mallet("A5", 1.2, 0.55, bright=1.1, bell=0.6, seed="note"), 0.0)
    place(tr, mallet("E6", 1.6, 1.0, bright=1.2, bell=0.9, seed="note"), 0.085)
    place(tr, mallet("F#6", 1.4, 0.35, bright=1.0, bell=1.0, seed="note"), 0.17)
    return trim_tail(room(tr, "note", 0.9, 0.18)), False


def s_alarm():
    """First Light: the motif as a steady pattern that grows over eight bars; loops."""
    beat = 60.0 / 120
    bars = 8
    tr = np.zeros(int((bars * 4 * beat + 1.5) * SR))
    pattern = [("D5", 0), ("A5", 0.5), ("E6", 1.0), ("A5", 1.5), ("F#6", 2.0), ("A5", 2.5), ("E6", 3.0),
               ("A5", 3.5)]
    for bar in range(bars):
        grow = 0.45 + 0.55 * bar / (bars - 1)
        for note, b in pattern:
            at = (bar * 4 + b) * beat
            accent = 1.0 if b in (0, 2.0) else 0.72
            place(tr, mallet(note, 1.2, grow * accent, bright=0.9 + 0.4 * grow, bell=0.5 * grow, seed="alarm"), at)
            if bar >= 4 and b in (0, 2.0):  # an octave below joins halfway
                low = note[:-1] + str(int(note[-1]) - 1)
                place(tr, mallet(low, 1.4, 0.30 * grow, bright=0.8, seed="alarm-low"), at)
    return trim_tail(room(tr, "alarm", 0.9, 0.16)), True


def s_lock():
    tr = np.zeros(int(0.5 * SR))
    place(tr, mallet("A5", 0.30, 0.8, bright=0.7, seed="lock"), 0.0)
    place(tr, mallet("E5", 0.34, 1.0, bright=0.6, seed="lock"), 0.06)
    return trim_tail(room(tr, "ui", 0.30, 0.08), floor_db=-50.0, fade=0.05), False


def s_unlock():
    tr = np.zeros(int(0.5 * SR))
    place(tr, mallet("E5", 0.30, 0.8, bright=0.7, seed="unlock"), 0.0)
    place(tr, mallet("A5", 0.34, 1.0, bright=0.8, seed="unlock"), 0.06)
    return trim_tail(room(tr, "ui", 0.30, 0.08), floor_db=-50.0, fade=0.05), False


def s_trusted():
    tr = np.zeros(int(0.5 * SR))
    place(tr, mallet("E6", 0.36, 1.0, bright=0.8, bell=0.5, seed="trusted"), 0.0)
    return trim_tail(room(tr, "ui", 0.30, 0.08), floor_db=-50.0, fade=0.05), False


def s_low_battery():
    tr = np.zeros(int(1.4 * SR))
    for i, note in enumerate(("F#5", "D5", "A4")):
        place(tr, mallet(note, 0.9, 1.0 - 0.15 * i, bright=0.55, seed="lowbat"), 0.16 * i)
    return trim_tail(room(tr, "ui", 0.6, 0.12)), False


def s_charging():
    tr = np.zeros(int(1.2 * SR))
    for i, note in enumerate(("D5", "A5", "D6")):
        place(tr, mallet(note, 0.8, 0.75 + 0.12 * i, bright=0.9, bell=0.4 + 0.2 * i, seed="charge"), 0.07 * i)
    return trim_tail(room(tr, "ui", 0.6, 0.14)), False


# name: (function, directory, title, level). level: ("lufs", target) or ("peak", dBFS); channels; loudness check.
SOUNDS = {
    "OpenBook_Pages": (s_ringtone, "ringtones", "Open Pages", ("lufs", -16.0), 2),
    "OpenBook_Spark": (s_notification, "notifications", "Spark", ("lufs", -16.0), 1),
    "OpenBook_FirstLight": (s_alarm, "alarms", "First Light", ("lufs", -16.0), 2),
    "OpenBook_Lock": (s_lock, "ui", "Lock", ("peak", -10.0), 1),
    "OpenBook_Unlock": (s_unlock, "ui", "Unlock", ("peak", -10.0), 1),
    "OpenBook_Trusted": (s_trusted, "ui", "Trusted", ("peak", -14.0), 1),
    "OpenBook_LowBattery": (s_low_battery, "ui", "Low battery", ("peak", -5.0), 1),
    "OpenBook_ChargingStarted": (s_charging, "ui", "Charging started", ("peak", -12.0), 1),
}


def to_pcm16(x):
    return np.clip(np.round(x * 32767.0), -32768, 32767).astype("<i2")


def write_wav(path, pcm):
    ch = 1 if pcm.ndim == 1 else pcm.shape[1]
    with wave.open(path, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def ebur128(path):
    """Integrated loudness (LUFS) and true peak (dBTP) from ffmpeg's ebur128 filter."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null",
                        "-"], capture_output=True, text=True, check=True).stderr
    summ = r[r.rfind("Summary:"):]
    lufs = float(summ.split("I:")[1].split("LUFS")[0])
    peak = float(summ.split("Peak:")[1].split("dBFS")[0])
    return lufs, peak


def render(name):
    fn, sub, title, level, channels = SOUNDS[name]
    x, loop = fn()
    if channels == 1:
        x = x.mean(axis=1)
    x = x / np.max(np.abs(x))
    with tempfile.TemporaryDirectory() as td:
        if level[0] == "lufs":
            # normalise for loudness, then keep true peak under -1 dBTP
            p = os.path.join(td, "probe.wav")
            write_wav(p, to_pcm16(x * 0.5))
            lufs, _ = ebur128(p)
            gain = 0.5 * 10 ** ((level[1] - lufs) / 20.0)
            x = x * min(gain, 10 ** (-1.2 / 20.0))
        else:
            x = x * 10 ** (level[1] / 20.0)
    return to_pcm16(x), title, loop, sub


def encode(pcm, title, loop, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        w = os.path.join(td, "in.wav")
        write_wav(w, pcm)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-fflags", "+bitexact", "-i", w,
                        "-map_metadata", "-1", "-c:a", "libvorbis", "-q:a", "6", "-flags:a", "+bitexact",
                        "-metadata", f"TITLE={title}", "-metadata", "ARTIST=The OpenBook Authors",
                        "-metadata", "COPYRIGHT=CC-BY-4.0",
                        "-metadata", f"ANDROID_LOOP={'true' if loop else 'false'}", path], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ASSETS, "sounds"))
    ap.add_argument("--wav", help="also write the 16-bit WAVs here")
    ap.add_argument("--only", action="append")
    a = ap.parse_args()
    manifest_path = os.path.join(a.out, "sounds.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
    for name in SOUNDS:
        if a.only and name not in a.only:
            continue
        pcm, title, loop, sub = render(name)
        path = os.path.join(a.out, sub, name + ".ogg")
        encode(pcm, title, loop, path)
        if a.wav:
            os.makedirs(a.wav, exist_ok=True)
            write_wav(os.path.join(a.wav, name + ".wav"), pcm)
        lufs, peak = ebur128(path)
        ch = 1 if pcm.ndim == 1 else pcm.shape[1]
        manifest[name] = {"file": f"{sub}/{name}.ogg", "title": title, "loop": loop, "channels": ch,
                          "seconds": round(len(pcm) / SR, 3), "lufs": lufs, "true_peak_dbfs": peak,
                          "pcm_sha256": hashlib.sha256(pcm.tobytes()).hexdigest()}
        print(f"{path}: {manifest[name]['seconds']} s, {lufs} LUFS, peak {peak} dBFS, {os.path.getsize(path)} B")
    write_json(manifest_path, manifest)


if __name__ == "__main__":
    main()
