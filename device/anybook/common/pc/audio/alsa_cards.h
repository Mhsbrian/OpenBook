// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Plain logic of openbook-audio-setup, tested on the host (audio_test.cpp): which ALSA PCM is a PC's built-in
// speaker and microphone, and how loud a test tone came back.

#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace openbook::audio {

// One line of /proc/asound/pcm: "02-00: ALC285 Analog : ALC285 Analog : playback 1 : capture 1".
struct Pcm {
    int card = -1;
    int device = -1;
    std::string id;
    std::string name;
    bool playback = false;
    bool capture = false;
};

std::vector<Pcm> ParsePcmList(const std::string& proc_asound_pcm);

// The built-in output: the first PCM an HDA codec driver calls "<codec> Analog" (Realtek, Conexant, Cirrus and
// QEMU's codec all do), else the first playback PCM that is not HDMI or DisplayPort. nullopt when there is none.
std::optional<Pcm> PickPrimary(const std::vector<Pcm>& pcms);

// What a recorded test tone looks like: levels in dBFS of 16-bit samples, interleaved, `channels` channels.
struct ToneLevels {
    double noise_rms_dbfs = -200;  // the window before the tone started
    double noise_bin_dbfs = -200;  // the tone frequency alone in that window
    double tone_rms_dbfs = -200;   // the window while the tone played (everything in it)
    double tone_bin_dbfs = -200;   // the tone frequency alone (Goertzel), in the same window
    double tone_share = 0;         // tone frequency's share of that window's energy, 0..1
};

// samples: interleaved 16-bit frames at `rate`. Noise window [noise_from, noise_to), tone window [tone_from,
// tone_to), in seconds from the start of the recording; the first channel only.
ToneLevels MeasureTone(const std::vector<int16_t>& samples, int channels, int rate, double freq, double noise_from,
                       double noise_to, double tone_from, double tone_to);

// The tone counts as heard when its frequency comes back at least 20 dB over that frequency before the tone,
// and carries at least a fifth of the energy while it plays.
bool ToneDetected(const ToneLevels& l);

}  // namespace openbook::audio
