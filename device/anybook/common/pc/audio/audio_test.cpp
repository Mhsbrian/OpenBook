// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Host tests for openbook-audio-setup's logic. The G14 lists follow the GA403WR: live-001's kernel log (NVIDIA
// HDMI audio card 0, Radeon HDMI/DP card 1, ALC285 card 2) and the inventory's aplay -l (dGPU off: no card 0).

#include <cmath>
#include <vector>

#include <gtest/gtest.h>

#include "alsa_cards.h"

namespace openbook::audio {
namespace {

constexpr char kG14[] =
        "00-03: HDMI 0 : HDMI 0 : playback 1\n"
        "00-07: HDMI 1 : HDMI 1 : playback 1\n"
        "00-08: HDMI 2 : HDMI 2 : playback 1\n"
        "00-09: HDMI 3 : HDMI 3 : playback 1\n"
        "01-03: HDMI 0 : HDMI 0 : playback 1\n"
        "01-07: HDMI 1 : HDMI 1 : playback 1\n"
        "02-00: ALC285 Analog : ALC285 Analog : playback 1 : capture 1\n";

constexpr char kG14DgpuOff[] =
        "00-03: HDMI 0 : HDMI 0 : playback 1\n"
        "01-00: ALC285 Analog : ALC285 Analog : playback 1 : capture 1\n";

TEST(AlsaCards, ParsesProcAsoundPcm) {
    auto p = ParsePcmList(kG14);
    ASSERT_EQ(7u, p.size());
    EXPECT_EQ(0, p[0].card);
    EXPECT_EQ(3, p[0].device);
    EXPECT_EQ("HDMI 0", p[0].id);
    EXPECT_TRUE(p[0].playback);
    EXPECT_FALSE(p[0].capture);
    EXPECT_EQ(2, p[6].card);
    EXPECT_EQ(0, p[6].device);
    EXPECT_EQ("ALC285 Analog", p[6].name);
    EXPECT_TRUE(p[6].capture);
}

TEST(AlsaCards, PicksTheAnalogCodecWhateverItsCardNumber) {
    auto a = PickPrimary(ParsePcmList(kG14));
    ASSERT_TRUE(a.has_value());
    EXPECT_EQ(2, a->card);
    EXPECT_EQ(0, a->device);
    auto b = PickPrimary(ParsePcmList(kG14DgpuOff));
    ASSERT_TRUE(b.has_value());
    EXPECT_EQ(1, b->card);
}

TEST(AlsaCards, NeverPicksDisplayAudio) {
    EXPECT_FALSE(PickPrimary(ParsePcmList("00-03: HDMI 0 : HDMI 0 : playback 1\n"
                                          "01-03: DisplayPort 0 : DP 0 : playback 1\n"))
                         .has_value());
    EXPECT_FALSE(PickPrimary(ParsePcmList("")).has_value());
}

TEST(AlsaCards, FallsBackToAnyNonDisplayPlaybackPcm) {
    // An ASoC machine (SOF/ACP) names its PCMs after the DAI link.
    auto p = PickPrimary(ParsePcmList("00-03: HDMI 0 : HDMI 0 : playback 1\n"
                                      "01-01: Speaker (*) :  : playback 1\n"
                                      "01-04: DMIC (*) :  : capture 1\n"));
    ASSERT_TRUE(p.has_value());
    EXPECT_EQ(1, p->card);
    EXPECT_EQ(1, p->device);
}

std::vector<int16_t> Signal(double seconds, double from, double to, double freq, double amp_dbfs, double noise) {
    const int rate = 48000;
    std::vector<int16_t> s(static_cast<size_t>(seconds * rate) * 2);
    uint32_t r = 12345;
    for (size_t i = 0; i < s.size() / 2; i++) {
        double t = static_cast<double>(i) / rate, x = 0;
        if (t >= from && t < to) x = std::pow(10, amp_dbfs / 20) * std::sin(2 * M_PI * freq * t);
        r = r * 1664525 + 1013904223;
        x += noise * ((r >> 8) / 16777216.0 - 0.5);
        s[2 * i] = s[2 * i + 1] = static_cast<int16_t>(std::lround(std::max(-1.0, std::min(1.0, x)) * 32767));
    }
    return s;
}

TEST(Tone, MeasuresASineAtItsLevel) {
    // A full-scale-referenced sine at -20 dBFS peak has an RMS of -23 dBFS.
    auto l = MeasureTone(Signal(3, 0.5, 2.5, 1000, -20, 0.001), 2, 48000, 1000, 0.1, 0.45, 0.75, 2.4);
    EXPECT_NEAR(-23.0, l.tone_bin_dbfs, 0.3);
    EXPECT_NEAR(-23.0, l.tone_rms_dbfs, 0.3);
    EXPECT_GT(l.tone_share, 0.95);
    EXPECT_LT(l.noise_bin_dbfs, -60);
    EXPECT_TRUE(ToneDetected(l));
}

TEST(Tone, SilenceAndNoiseAreNotATone) {
    EXPECT_FALSE(ToneDetected(MeasureTone(Signal(3, 0, 0, 1000, -20, 0), 2, 48000, 1000, 0.1, 0.45, 0.75, 2.4)));
    EXPECT_FALSE(ToneDetected(MeasureTone(Signal(3, 0, 0, 1000, -20, 0.3), 2, 48000, 1000, 0.1, 0.45, 0.75, 2.4)));
    // Another frequency is not this tone.
    EXPECT_FALSE(
            ToneDetected(MeasureTone(Signal(3, 0.5, 2.5, 3000, -20, 0.001), 2, 48000, 1000, 0.1, 0.45, 0.75, 2.4)));
}

TEST(Tone, AQuietButCleanToneIsHeard) {
    // What a laptop mic may return from its own speakers: -50 dBFS over a -70 dBFS noise floor.
    EXPECT_TRUE(
            ToneDetected(MeasureTone(Signal(3, 0.5, 2.5, 1000, -47, 0.0005), 2, 48000, 1000, 0.1, 0.45, 0.75, 2.4)));
}

}  // namespace
}  // namespace openbook::audio
