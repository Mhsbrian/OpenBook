// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// openbook-audio-test: the same speaker-to-microphone loopback as `openbook-audio-setup test`, but through Android
// (AAudio -> AudioFlinger -> the audio HAL's primary module -> ALSA), so it shows what apps get. Prints one JSON
// object. userdebug only; run as root or shell.
//   openbook-audio-test [--seconds S] [--freq HZ] [--wav FILE] [--out-device ID] [--in-device ID]
// The device IDs are audio port IDs (dumpsys media.audio_policy: "Port ID: 2; "Speaker""); without them Android
// routes as it would for an app, e.g. to a connected Bluetooth headset instead of the speakers.

#include <aaudio/AAudio.h>
#include <unistd.h>

#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include "alsa_cards.h"

namespace {

constexpr int kRate = 48000;
constexpr int kChannels = 2;

AAudioStream* Open(aaudio_direction_t dir, int device, std::string* err) {
    AAudioStreamBuilder* b = nullptr;
    if (AAudio_createStreamBuilder(&b) != AAUDIO_OK) {
        *err = "createStreamBuilder";
        return nullptr;
    }
    AAudioStreamBuilder_setDirection(b, dir);
    if (device > 0) AAudioStreamBuilder_setDeviceId(b, device);
    AAudioStreamBuilder_setSampleRate(b, kRate);
    AAudioStreamBuilder_setChannelCount(b, kChannels);
    AAudioStreamBuilder_setFormat(b, AAUDIO_FORMAT_PCM_I16);
    AAudioStreamBuilder_setSharingMode(b, AAUDIO_SHARING_MODE_SHARED);
    AAudioStreamBuilder_setPerformanceMode(b, AAUDIO_PERFORMANCE_MODE_NONE);
    if (dir == AAUDIO_DIRECTION_INPUT) AAudioStreamBuilder_setInputPreset(b, AAUDIO_INPUT_PRESET_UNPROCESSED);
    else AAudioStreamBuilder_setUsage(b, AAUDIO_USAGE_MEDIA);
    AAudioStream* s = nullptr;
    aaudio_result_t r = AAudioStreamBuilder_openStream(b, &s);
    AAudioStreamBuilder_delete(b);
    if (r != AAUDIO_OK) {
        *err = AAudio_convertResultToText(r);
        return nullptr;
    }
    return s;
}

}  // namespace

int main(int argc, char** argv) {
    double seconds = 2, freq = 1000;
    std::string wav;
    int out_device = 0, in_device = 0;
    for (int i = 1; i + 1 < argc; i += 2) {
        if (!strcmp(argv[i], "--out-device")) out_device = atoi(argv[i + 1]);
        if (!strcmp(argv[i], "--in-device")) in_device = atoi(argv[i + 1]);
        if (!strcmp(argv[i], "--seconds")) seconds = atof(argv[i + 1]);
        else if (!strcmp(argv[i], "--freq")) freq = atof(argv[i + 1]);
        else if (!strcmp(argv[i], "--wav")) wav = argv[i + 1];
    }
    std::string ierr, oerr;
    AAudioStream* in = Open(AAUDIO_DIRECTION_INPUT, in_device, &ierr);
    AAudioStream* out = Open(AAUDIO_DIRECTION_OUTPUT, out_device, &oerr);
    if (!in || !out) {
        printf("{\"test\": \"aaudio-loopback\", \"ok\": false, \"error\": \"%s%s%s%s\"}\n", in ? "" : "input: ",
               in ? "" : ierr.c_str(), out ? "" : " output: ", out ? "" : oerr.c_str());
        if (in) AAudioStream_close(in);
        if (out) AAudioStream_close(out);
        return 1;
    }
    const int in_rate = AAudioStream_getSampleRate(in), in_ch = AAudioStream_getChannelCount(in);
    const int out_rate = AAudioStream_getSampleRate(out), out_ch = AAudioStream_getChannelCount(out);
    const double lead = 0.5, tail = 0.5;
    std::vector<int16_t> captured(static_cast<size_t>((lead + seconds + tail + 0.5) * in_rate) * in_ch);
    std::atomic<long> got{0};
    std::atomic<int> in_err{0};
    if (AAudioStream_requestStart(in) != AAUDIO_OK) in_err = 1;
    std::thread rec([&] {
        const int chunk = in_rate / 50;
        while (!in_err && static_cast<size_t>(got * in_ch + chunk * in_ch) <= captured.size()) {
            aaudio_result_t n =
                    AAudioStream_read(in, captured.data() + got * in_ch, chunk, 500 * 1000 * 1000LL);
            if (n < 0) { in_err = n; break; }
            got += n;
        }
    });
    usleep(static_cast<useconds_t>(lead * 1e6));
    // The tone at -15 dBFS with 10 ms ramps, then silence; the capture keeps running through both.
    std::vector<int16_t> tone(static_cast<size_t>((seconds + tail) * out_rate) * out_ch, 0);
    double amp = std::pow(10.0, -15.0 / 20) * 32767;
    size_t tn = static_cast<size_t>(seconds * out_rate), ramp = out_rate / 100;
    for (size_t i = 0; i < tn; i++) {
        double g = std::min({1.0, static_cast<double>(i) / ramp, static_cast<double>(tn - i) / ramp});
        int16_t v = static_cast<int16_t>(amp * g * std::sin(2 * M_PI * freq * i / out_rate));
        for (int c = 0; c < out_ch; c++) tone[i * out_ch + c] = v;
    }
    int out_err = AAudioStream_requestStart(out) == AAUDIO_OK ? 0 : 1;
    long written = 0;
    const long frames = static_cast<long>(tone.size() / out_ch);
    while (!out_err && written < frames) {
        long n = std::min<long>(out_rate / 50, frames - written);
        aaudio_result_t w = AAudioStream_write(out, tone.data() + written * out_ch, n, 500 * 1000 * 1000LL);
        if (w < 0) { out_err = w; break; }
        written += w;
    }
    usleep(300000);
    rec.join();
    AAudioStream_requestStop(out);
    AAudioStream_requestStop(in);
    int xruns = AAudioStream_getXRunCount(out);
    // Where Android actually routed the two streams (audio port IDs).
    const int routed_out = AAudioStream_getDeviceId(out), routed_in = AAudioStream_getDeviceId(in);
    AAudioStream_close(out);
    AAudioStream_close(in);
    captured.resize(static_cast<size_t>(got) * in_ch);
    if (!wav.empty()) {
        FILE* f = fopen(wav.c_str(), "we");
        if (f) {
            uint32_t data = captured.size() * 2, riff = 36 + data, fmt = 16, rate = in_rate,
                     bps = in_rate * in_ch * 2;
            uint16_t pcm = 1, ch = in_ch, align = in_ch * 2, bits = 16;
            fwrite("RIFF", 1, 4, f), fwrite(&riff, 4, 1, f), fwrite("WAVEfmt ", 1, 8, f), fwrite(&fmt, 4, 1, f);
            fwrite(&pcm, 2, 1, f), fwrite(&ch, 2, 1, f), fwrite(&rate, 4, 1, f), fwrite(&bps, 4, 1, f);
            fwrite(&align, 2, 1, f), fwrite(&bits, 2, 1, f), fwrite("data", 1, 4, f), fwrite(&data, 4, 1, f);
            fwrite(captured.data(), 2, captured.size(), f);
            fclose(f);
        }
    }
    // Output latency is unknown here: measure the tone in the middle of where it can be.
    auto l = openbook::audio::MeasureTone(captured, in_ch, in_rate, freq, 0.1, lead - 0.05, lead + 0.4,
                                          lead + seconds - 0.1);
    bool heard = openbook::audio::ToneDetected(l);
    printf("{\"test\": \"aaudio-loopback\", \"ok\": %s, \"in_rate\": %d, \"in_channels\": %d, \"out_rate\": %d, "
           "\"out_channels\": %d, \"captured_frames\": %ld, \"written_frames\": %ld, \"xruns\": %d, \"freq\": %.0f, "
           "\"tone_dbfs_out\": -15, \"noise_rms_dbfs\": %.1f, \"noise_bin_dbfs\": %.1f, \"tone_rms_dbfs\": %.1f, "
           "\"tone_bin_dbfs\": %.1f, \"tone_share\": %.3f, \"slice_share_mean\": %.3f, \"slice_share_min\": %.3f, "
           "\"glitched_slices\": %d, \"slices\": %d, \"heard\": %s, \"input_error\": %d, \"output_error\": %d, "
           "\"out_device\": %d, \"in_device\": %d}\n",
           !in_err && !out_err ? "true" : "false", in_rate, in_ch, out_rate, out_ch, static_cast<long>(got), written,
           xruns, freq, l.noise_rms_dbfs, l.noise_bin_dbfs, l.tone_rms_dbfs, l.tone_bin_dbfs, l.tone_share,
           l.slice_share_mean, l.slice_share_min, l.glitched_slices, l.slices,
           heard ? "true" : "false", static_cast<int>(in_err), out_err, routed_out, routed_in);
    return !in_err && !out_err ? 0 : 1;
}
