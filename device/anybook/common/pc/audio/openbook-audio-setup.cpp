// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// openbook-audio-setup: the built-in sound card of an OpenBook PC, for AOSP's example audio HAL (docs/g14-audio-net.md).
//
//   boot   (init, before the audio HAL starts) Find the built-in codec's PCM (alsa_cards.h: "<codec> Analog" on
//          HDA) and publish it as vendor.audio.primary.card/.device for the HAL's primary module
//          (aosp/patches/hardware/interfaces; card -1 when there is none). Then give the codec's mixer a working
//          state: the outputs' and capture switches on, their volumes at 0 dB. Android has no alsactl or UCM;
//          this is the part of what desktop Linux's PipeWire profile does that a single analog PCM needs. Volume
//          control stays in AudioFlinger (software volume).
//   list   Cards, PCMs and every mixer control with its values (for logs).
//   test   Direct ALSA loopback, bypassing Android: record the built-in mic while the speakers play a tone,
//          then measure it (alsa_cards.h). Prints one JSON object. [--seconds S] [--freq HZ] [--card N
//          --device D] [--wav FILE]
//
// Testing: OPENBOOK_PROC_ROOT=<dir> reads <dir>/proc/asound/pcm instead of /proc/asound/pcm.

#include <dirent.h>
#include <fcntl.h>
#include <sound/asound.h>
#include <sound/tlv.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include <cutils/properties.h>
#include <tinyalsa/asoundlib.h>

#include "alsa_cards.h"

using openbook::audio::Pcm;

namespace {

constexpr int kRate = 48000;
constexpr int kChannels = 2;

std::string ReadFile(const std::string& path) {
    std::string out;
    FILE* f = fopen(path.c_str(), "re");
    if (!f) return out;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0) out.append(buf, n);
    fclose(f);
    return out;
}

std::string ProcRoot() {
    const char* r = getenv("OPENBOOK_PROC_ROOT");
    return r ? r : "";
}

std::vector<Pcm> ListPcms() {
    return openbook::audio::ParsePcmList(ReadFile(ProcRoot() + "/proc/asound/pcm"));
}

// HDA controllers bound to snd_hda_intel register their cards from a work queue, after modprobe returns.
bool HdaControllersBound() {
    DIR* d = opendir((ProcRoot() + "/sys/bus/pci/drivers/snd_hda_intel").c_str());
    if (!d) return false;
    bool any = false;
    while (struct dirent* e = readdir(d)) any |= !strncmp(e->d_name, "0000:", 5);
    closedir(d);
    return any;
}

std::string Json(const std::string& s) {  // for error messages in the JSON output
    std::string o;
    for (char c : s) o += (c == '"' || c == '\\') ? '\'' : (static_cast<unsigned char>(c) < 0x20 ? ' ' : c);
    return o;
}

// The value of control `name` (index 0) that is closest to `db` decibels, from its TLV (DB_SCALE or
// DB_MINMAX); -1 when the control has no such TLV.
int ValueForDb(int card, const char* name, double db, int min, int max) {
    char path[64];
    snprintf(path, sizeof path, "/dev/snd/controlC%d", card);
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    int result = -1;
    snd_ctl_elem_list list{};
    if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_LIST, &list) == 0 && list.count > 0) {
        std::vector<snd_ctl_elem_id> ids(list.count);
        list.space = list.count;
        list.pids = ids.data();
        unsigned numid = 0;
        if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_LIST, &list) == 0) {
            for (unsigned i = 0; i < list.used; i++) {
                if (ids[i].index == 0 && !strcmp(reinterpret_cast<const char*>(ids[i].name), name)) {
                    numid = ids[i].numid;
                    break;
                }
            }
        }
        if (numid) {
            std::vector<unsigned> buf(2 + 64);
            auto* tlv = reinterpret_cast<snd_ctl_tlv*>(buf.data());
            tlv->numid = numid;
            tlv->length = 64 * sizeof(unsigned);
            if (ioctl(fd, SNDRV_CTL_IOCTL_TLV_READ, tlv) == 0) {
                unsigned type = tlv->tlv[0];
                if (type == SNDRV_CTL_TLVT_DB_SCALE && max > min) {  // [min dB*100, step dB*100 | mute flag]
                    int db_min = static_cast<int>(tlv->tlv[2]);
                    int step = static_cast<int>(tlv->tlv[3] & 0xffff);
                    if (step > 0) result = min + static_cast<int>(std::lround((db * 100 - db_min) / step));
                } else if ((type == SNDRV_CTL_TLVT_DB_MINMAX || type == SNDRV_CTL_TLVT_DB_MINMAX_MUTE) && max > min) {
                    int db_min = static_cast<int>(tlv->tlv[2]), db_max = static_cast<int>(tlv->tlv[3]);
                    if (db_max > db_min)
                        result = min + static_cast<int>(std::lround((db * 100.0 - db_min) * (max - min) /
                                                                    (db_max - db_min)));
                }
                if (result >= 0) result = std::max(min, std::min(max, result));
            }
        }
    }
    close(fd);
    return result;
}

// Set every value of a control; report what it was and what it is.
void Set(struct mixer* m, int card, const char* name, const char* how) {
    struct mixer_ctl* ctl = mixer_get_ctl_by_name(m, name);
    if (!ctl) return;
    unsigned n = mixer_ctl_get_num_values(ctl);
    int before = mixer_ctl_get_value(ctl, 0), value;
    if (!strcmp(how, "on")) {
        value = 1;
    } else {  // "0dB": the TLV's 0 dB, or the maximum when the control has none
        int min = mixer_ctl_get_range_min(ctl), max = mixer_ctl_get_range_max(ctl);
        value = ValueForDb(card, name, 0.0, min, max);
        if (value < 0) value = max;
    }
    int rc = 0;
    for (unsigned i = 0; i < n; i++) rc |= mixer_ctl_set_value(ctl, i, value);
    printf("openbook-audio-setup: card %d '%s': %d -> %d%s\n", card, name, before, value, rc ? " (FAILED)" : "");
}

int Boot() {
    std::vector<Pcm> pcms = ListPcms();
    std::optional<Pcm> p = openbook::audio::PickPrimary(pcms);
    for (int i = 0; !p && i < 20 && HdaControllersBound(); i++) {  // up to 5 s for the codec probe
        usleep(250000);
        pcms = ListPcms();
        p = openbook::audio::PickPrimary(pcms);
    }
    for (const auto& x : pcms)
        printf("openbook-audio-setup: pcm %02d-%02d '%s'%s%s\n", x.card, x.device, x.name.c_str(),
               x.playback ? " playback" : "", x.capture ? " capture" : "");
    if (!p) {
        // A VM without sound, or a codec this does not recognise: the HAL's primary module runs on its stub
        // driver instead of failing on a card 0 that is missing or HDMI.
        property_set("vendor.audio.primary.card", "-1");
        printf("openbook-audio-setup: no built-in sound card; the audio HAL's primary module uses its stub driver\n");
        return 0;
    }
    property_set("vendor.audio.primary.card", std::to_string(p->card).c_str());
    property_set("vendor.audio.primary.device", std::to_string(p->device).c_str());
    printf("openbook-audio-setup: primary card %d device %d ('%s'%s)\n", p->card, p->device, p->name.c_str(),
           p->capture ? ", capture too" : ", NO capture");
    struct mixer* m = mixer_open(p->card);
    if (!m) {
        printf("openbook-audio-setup: cannot open the mixer of card %d\n", p->card);
        return 1;
    }
    // HDA names (the generic parser and the Realtek/Cirrus codec drivers). Missing controls are skipped.
    for (const char* n : {"Master Playback Switch", "Speaker Playback Switch", "Bass Speaker Playback Switch",
                          "Headphone Playback Switch", "Capture Switch"})
        Set(m, p->card, n, "on");
    for (const char* n : {"Master Playback Volume", "Speaker Playback Volume", "Headphone Playback Volume",
                          "PCM Playback Volume", "Capture Volume"})
        Set(m, p->card, n, "0dB");
    mixer_close(m);
    return 0;
}

int List() {
    printf("%s", ReadFile(ProcRoot() + "/proc/asound/cards").c_str());
    printf("%s", ReadFile(ProcRoot() + "/proc/asound/pcm").c_str());
    char v[PROPERTY_VALUE_MAX];
    property_get("vendor.audio.primary.card", v, "unset");
    printf("vendor.audio.primary.card=%s\n", v);
    property_get("vendor.audio.primary.device", v, "unset");
    printf("vendor.audio.primary.device=%s\n", v);
    for (int card = 0; card < 8; card++) {
        struct mixer* m = mixer_open(card);
        if (!m) continue;
        printf("card %d mixer '%s':\n", card, mixer_get_name(m));
        for (unsigned i = 0; i < mixer_get_num_ctls(m); i++) {
            struct mixer_ctl* c = mixer_get_ctl(m, i);
            enum mixer_ctl_type t = mixer_ctl_get_type(c);
            printf("  %s [%s]", mixer_ctl_get_name(c), mixer_ctl_get_type_string(c));
            if (t == MIXER_CTL_TYPE_BOOL || t == MIXER_CTL_TYPE_INT) {
                for (unsigned j = 0; j < mixer_ctl_get_num_values(c) && j < 8; j++)
                    printf(" %d", mixer_ctl_get_value(c, j));
                if (t == MIXER_CTL_TYPE_INT)
                    printf(" (%d..%d)", mixer_ctl_get_range_min(c), mixer_ctl_get_range_max(c));
            } else if (t == MIXER_CTL_TYPE_ENUM) {
                int e = mixer_ctl_get_value(c, 0);
                printf(" %s", e >= 0 && static_cast<unsigned>(e) < mixer_ctl_get_num_enums(c)
                                      ? mixer_ctl_get_enum_string(c, e)
                                      : "?");
            }
            printf("\n");
        }
        mixer_close(m);
    }
    return 0;
}

struct pcm* OpenPcm(int card, int device, bool input, std::string* err) {
    struct pcm_config c{};
    c.channels = kChannels;
    c.rate = kRate;
    c.period_size = 960;  // 20 ms
    c.period_count = 4;
    c.format = PCM_FORMAT_S16_LE;
    for (int i = 0; i < 40; i++) {  // the audio HAL may still hold the PCM for a few seconds after its last use
        struct pcm* p = pcm_open(card, device, input ? PCM_IN : PCM_OUT, &c);
        if (p && pcm_is_ready(p)) return p;
        *err = p ? pcm_get_error(p) : "pcm_open failed";
        if (p) pcm_close(p);
        usleep(250000);
    }
    return nullptr;
}

void WriteWav(const std::string& path, const std::vector<int16_t>& s) {
    FILE* f = fopen(path.c_str(), "we");
    if (!f) return;
    uint32_t data = s.size() * 2, riff = 36 + data, fmt = 16, rate = kRate, bps = kRate * kChannels * 2;
    uint16_t pcm = 1, ch = kChannels, align = kChannels * 2, bits = 16;
    fwrite("RIFF", 1, 4, f), fwrite(&riff, 4, 1, f), fwrite("WAVEfmt ", 1, 8, f), fwrite(&fmt, 4, 1, f);
    fwrite(&pcm, 2, 1, f), fwrite(&ch, 2, 1, f), fwrite(&rate, 4, 1, f), fwrite(&bps, 4, 1, f);
    fwrite(&align, 2, 1, f), fwrite(&bits, 2, 1, f), fwrite("data", 1, 4, f), fwrite(&data, 4, 1, f);
    fwrite(s.data(), 2, s.size(), f);
    fclose(f);
}

int Test(int argc, char** argv) {
    double seconds = 2, freq = 1000;
    int card = -1, device = 0;
    std::string wav;
    for (int i = 2; i + 1 < argc; i += 2) {
        if (!strcmp(argv[i], "--seconds")) seconds = atof(argv[i + 1]);
        else if (!strcmp(argv[i], "--freq")) freq = atof(argv[i + 1]);
        else if (!strcmp(argv[i], "--card")) card = atoi(argv[i + 1]);
        else if (!strcmp(argv[i], "--device")) device = atoi(argv[i + 1]);
        else if (!strcmp(argv[i], "--wav")) wav = argv[i + 1];
    }
    if (card < 0) {
        auto p = openbook::audio::PickPrimary(ListPcms());
        if (!p) {
            printf("{\"test\": \"alsa-loopback\", \"ok\": false, \"error\": \"no built-in sound card\"}\n");
            return 1;
        }
        card = p->card;
        device = p->device;
    }
    std::string perr, cerr;
    struct pcm* in = OpenPcm(card, device, true, &cerr);
    struct pcm* out = OpenPcm(card, device, false, &perr);
    if (!in || !out) {
        std::string e = (in ? "" : "capture: " + cerr) + (out ? "" : " playback: " + perr);
        printf("{\"test\": \"alsa-loopback\", \"ok\": false, \"card\": %d, \"device\": %d, \"error\": \"%s\"}\n",
               card, device, Json(e).c_str());
        if (in) pcm_close(in);
        if (out) pcm_close(out);
        return 1;
    }
    // Capture: 0.5 s before the tone, the tone, 0.5 s after. Playback: silence, the tone at -15 dBFS with 10 ms
    // ramps, silence.
    const double lead = 0.5, tail = 0.5;
    size_t cap_frames = static_cast<size_t>((lead + seconds + tail) * kRate);
    std::vector<int16_t> captured(cap_frames * kChannels);
    std::atomic<int> cap_err{0};
    std::thread rec([&] {
        const size_t chunk = 960 * kChannels;
        for (size_t at = 0; at < captured.size(); at += chunk) {
            size_t n = std::min(chunk, captured.size() - at);
            if (pcm_read(in, captured.data() + at, n * 2)) { cap_err = 1; break; }
        }
    });
    std::vector<int16_t> tone(static_cast<size_t>((lead + seconds + tail) * kRate) * kChannels, 0);
    double amp = std::pow(10.0, -15.0 / 20) * 32767;
    size_t t0 = static_cast<size_t>(lead * kRate), tn = static_cast<size_t>(seconds * kRate), ramp = kRate / 100;
    for (size_t i = 0; i < tn; i++) {
        double g = std::min({1.0, static_cast<double>(i) / ramp, static_cast<double>(tn - i) / ramp});
        int16_t v = static_cast<int16_t>(amp * g * std::sin(2 * M_PI * freq * i / kRate));
        for (int c = 0; c < kChannels; c++) tone[(t0 + i) * kChannels + c] = v;
    }
    int play_err = 0;
    const size_t chunk = 960 * kChannels;
    for (size_t at = 0; at < tone.size() && !play_err; at += chunk)
        play_err = pcm_write(out, tone.data() + at, std::min(chunk, tone.size() - at) * 2);
    rec.join();
    std::string play_msg = play_err ? pcm_get_error(out) : "", cap_msg = cap_err ? pcm_get_error(in) : "";
    pcm_close(out);
    pcm_close(in);
    if (!wav.empty()) WriteWav(wav, captured);
    // The capture starts a little before the playback reaches the speaker: measure the tone well inside its span.
    auto l = openbook::audio::MeasureTone(captured, kChannels, kRate, freq, 0.1, lead - 0.05, lead + 0.25,
                                          lead + seconds - 0.1);
    bool heard = openbook::audio::ToneDetected(l);
    printf("{\"test\": \"alsa-loopback\", \"ok\": %s, \"card\": %d, \"device\": %d, \"rate\": %d, \"channels\": %d, "
           "\"freq\": %.0f, \"seconds\": %.2f, \"tone_dbfs_out\": -15, \"noise_rms_dbfs\": %.1f, "
           "\"noise_bin_dbfs\": %.1f, \"tone_rms_dbfs\": %.1f, \"tone_bin_dbfs\": %.1f, \"tone_share\": %.3f, \"slice_share_mean\": %.3f, \"slice_share_min\": %.3f, "
           "\"glitched_slices\": %d, \"slices\": %d, "
           "\"heard\": %s, \"playback_error\": \"%s\", \"capture_error\": \"%s\"}\n",
           !play_err && !cap_err ? "true" : "false", card, device, kRate, kChannels, freq, seconds,
           l.noise_rms_dbfs, l.noise_bin_dbfs, l.tone_rms_dbfs, l.tone_bin_dbfs, l.tone_share, l.slice_share_mean,
           l.slice_share_min, l.glitched_slices, l.slices,
           heard ? "true" : "false", Json(play_msg).c_str(), Json(cap_msg).c_str());
    return !play_err && !cap_err ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
    setvbuf(stdout, nullptr, _IOLBF, 0);
    std::string cmd = argc > 1 ? argv[1] : "";
    if (cmd == "boot") return Boot();
    if (cmd == "list") return List();
    if (cmd == "test") return Test(argc, argv);
    fprintf(stderr, "usage: openbook-audio-setup boot | list | test [--seconds S] [--freq HZ] [--card N --device D] "
                    "[--wav FILE]\n");
    return 2;
}
