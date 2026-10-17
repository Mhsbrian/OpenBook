// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

#include "alsa_cards.h"

#include <algorithm>
#include <cmath>
#include <sstream>

namespace openbook::audio {
namespace {

std::string Trim(const std::string& s) {
    size_t b = s.find_first_not_of(" \t"), e = s.find_last_not_of(" \t\r\n");
    return b == std::string::npos ? "" : s.substr(b, e - b + 1);
}

bool Contains(const std::string& s, const char* what) {
    return s.find(what) != std::string::npos;
}

bool IsDisplayAudio(const Pcm& p) {
    return Contains(p.id, "HDMI") || Contains(p.name, "HDMI") || Contains(p.id, "DisplayPort") ||
           Contains(p.name, "DisplayPort") || Contains(p.name, " DP") || p.name.rfind("DP", 0) == 0;
}

double Db(double rms) {
    return rms > 0 ? 20 * std::log10(rms) : -200;
}

// RMS of the whole window and of `freq` alone (Goertzel), both on samples scaled to [-1, 1).
void Levels(const std::vector<int16_t>& s, int channels, int rate, double freq, double from, double to, double* all,
            double* bin) {
    size_t frames = s.size() / channels;
    size_t a = std::min(frames, static_cast<size_t>(std::max(0.0, from) * rate));
    size_t b = std::min(frames, static_cast<size_t>(std::max(0.0, to) * rate));
    *all = *bin = 0;
    if (b <= a) return;
    double coeff = 2 * std::cos(2 * M_PI * freq / rate), s1 = 0, s2 = 0, sum = 0;
    for (size_t i = a; i < b; i++) {
        double x = s[i * channels] / 32768.0;
        sum += x * x;
        double s0 = x + coeff * s1 - s2;
        s2 = s1;
        s1 = s0;
    }
    size_t n = b - a;
    double power = s1 * s1 + s2 * s2 - coeff * s1 * s2;  // |X(f)|^2
    *all = std::sqrt(sum / n);
    // A sine of amplitude A gives |X| = A n / 2; its RMS is A / sqrt(2).
    *bin = std::sqrt(2 * power) / n;
}

}  // namespace

std::vector<Pcm> ParsePcmList(const std::string& text) {
    std::vector<Pcm> out;
    std::istringstream in(text);
    std::string line;
    while (std::getline(in, line)) {
        Pcm p;
        if (sscanf(line.c_str(), "%d-%d:", &p.card, &p.device) != 2) continue;
        std::vector<std::string> f;
        size_t pos = line.find(':') + 1;
        while (pos <= line.size()) {
            size_t next = line.find(" : ", pos);
            f.push_back(Trim(line.substr(pos, next == std::string::npos ? std::string::npos : next - pos)));
            if (next == std::string::npos) break;
            pos = next + 3;
        }
        if (f.size() >= 2) {
            p.id = f[0];
            p.name = f[1];
        }
        for (size_t i = 2; i < f.size(); i++) {
            if (f[i].rfind("playback", 0) == 0) p.playback = true;
            if (f[i].rfind("capture", 0) == 0) p.capture = true;
        }
        out.push_back(p);
    }
    return out;
}

std::optional<Pcm> PickPrimary(const std::vector<Pcm>& pcms) {
    for (const auto& p : pcms) {
        if (p.playback && (Contains(p.id, "Analog") || Contains(p.name, "Analog"))) return p;
    }
    for (const auto& p : pcms) {
        if (p.playback && !IsDisplayAudio(p)) return p;
    }
    return std::nullopt;
}

ToneLevels MeasureTone(const std::vector<int16_t>& samples, int channels, int rate, double freq, double noise_from,
                       double noise_to, double tone_from, double tone_to) {
    ToneLevels l;
    if (channels <= 0 || rate <= 0) return l;
    double all, bin;
    Levels(samples, channels, rate, freq, noise_from, noise_to, &all, &bin);
    l.noise_rms_dbfs = Db(all);
    l.noise_bin_dbfs = Db(bin);
    Levels(samples, channels, rate, freq, tone_from, tone_to, &all, &bin);
    l.tone_rms_dbfs = Db(all);
    l.tone_bin_dbfs = Db(bin);
    l.tone_share = all > 0 ? std::min(1.0, (bin * bin) / (all * all)) : 0;
    return l;
}

bool ToneDetected(const ToneLevels& l) {
    return l.tone_bin_dbfs > -90 && l.tone_bin_dbfs - l.noise_bin_dbfs >= 20 && l.tone_share >= 0.2;
}

}  // namespace openbook::audio
