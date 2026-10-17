// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// The wizard's hardware check (screen 2, "hwinfo"): what this boot of OpenBook found and drives, read from sysfs and
// procfs, plus the known gaps of models we have tested. States and reason codes are in PROTOCOL.md.
#include "common.h"

#include <dirent.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

// Known gaps of tested models, by DMI board name (docs/HARDWARE.md, docs/STATUS.md).
static const struct gap {
    const char *board, *component, *state, *detail;
} GAPS[] = {
    // ANAL-178: s2idle works, the SoC does not reach S0i3 yet.
    {"GA403WR", "sleep", "limited", "s0i3_not_reached"},
    // ANAL-179: Wi-Fi, Bluetooth and the speakers are built and tested in QEMU, not yet on the laptop.
    {"GA403WR", "wifi", "new", "untested_model"},
    {"GA403WR", "audio", "new", "untested_model"},
};

struct comp {
    const char *id;
    char state[16], value[128], detail[160];
    int present;
};

static void rd(const char *rel, char *out, size_t n) {
    char p[PATH_MAX];
    env_path(p, sizeof p, "%s", rel);
    if (read_text(p, out, n)) out[0] = 0;
}

static void rd_abs(const char *path, char *out, size_t n) {
    if (read_text(path, out, n)) out[0] = 0;
}

static void link_base(const char *path, char *out, size_t n) {
    char t[PATH_MAX];
    ssize_t r = readlink(path, t, sizeof t - 1);
    out[0] = 0;
    if (r <= 0) return;
    t[r] = 0;
    const char *b = strrchr(t, '/');
    snprintf(out, n, "%s", b ? b + 1 : t);
}

static void set(struct comp *c, const char *state, const char *detail) {
    snprintf(c->state, sizeof c->state, "%s", state);
    if (detail) snprintf(c->detail, sizeof c->detail, "%s", detail);
}

static const char *gpu_name(unsigned v, unsigned d) {
    static char buf[64];
    if (v == 0x1002) {
        switch (d) {
        case 0x150e: return "AMD Radeon 890M";
        case 0x1586: return "AMD Radeon 8060S";
        case 0x15bf: case 0x1900: case 0x1901: return "AMD Radeon 780M";
        case 0x1681: return "AMD Radeon 680M";
        case 0x164e: return "AMD Radeon 610M";
        }
        snprintf(buf, sizeof buf, "AMD GPU %04x:%04x", v, d);
        return buf;
    }
    if (v == 0x10de) {
        if (d == 0x2f58) return "NVIDIA GeForce RTX 5070 Ti Laptop GPU";
        snprintf(buf, sizeof buf, "NVIDIA GPU %04x:%04x", v, d);
        return buf;
    }
    if (v == 0x8086) return "Intel graphics";
    if (v == 0x1af4) return "Virtio GPU";
    if (v == 0x1234) return "QEMU standard VGA";
    snprintf(buf, sizeof buf, "GPU %04x:%04x", v, d);
    return buf;
}

static const char *wifi_name(unsigned v, unsigned d) {
    static char buf[64];
    if (v == 0x14c3 && d == 0x7925) return "MediaTek MT7925";
    if (v == 0x14c3 && d == 0x0616) return "MediaTek MT7922";
    if (v == 0x14c3 && d == 0x7961) return "MediaTek MT7921";
    if (v == 0x8086) return "Intel Wi-Fi";
    if (v == 0x10ec) return "Realtek Wi-Fi";
    if (v == 0x17cb) return "Qualcomm Wi-Fi";
    snprintf(buf, sizeof buf, "Wi-Fi %04x:%04x", v, d);
    return buf;
}

// Names by driver, for devices whose PCI IDs this domain may not read (Android: unlabeled sysfs).
static const char *name_by_driver(const char *drv) {
    static const struct {
        const char *drv, *name;
    } T[] = {{"amdgpu", "AMD Radeon graphics"}, {"i915", "Intel graphics"}, {"xe", "Intel graphics"},
             {"nouveau", "NVIDIA GPU"}, {"virtio-pci", "Virtio GPU"}, {"virtio_gpu", "Virtio GPU"},
             {"bochs-drm", "QEMU standard VGA"}, {"mt7925e", "MediaTek MT7925"}, {"mt7921e", "MediaTek MT7921"},
             {"iwlwifi", "Intel Wi-Fi"}, {"ath11k_pci", "Qualcomm Wi-Fi"}, {"ath12k_pci", "Qualcomm Wi-Fi"},
             {"rtw89_8852be", "Realtek Wi-Fi"}, {"mac80211_hwsim", "Simulated Wi-Fi (mac80211_hwsim)"}};
    for (size_t i = 0; i < ARRAY_LEN(T); i++)
        if (!strcmp(drv, T[i].drv)) return T[i].name;
    return NULL;
}

// "B: ABS=..." bitmaps: hex longs, most significant first.
static int bit_set(const char *bitmap, int bit) {
    char tmp[512];
    snprintf(tmp, sizeof tmp, "%s", bitmap);
    char *words[16];
    int n = 0;
    char *save = NULL;
    for (char *t = strtok_r(tmp, " ", &save); t && n < 16; t = strtok_r(NULL, " ", &save)) words[n++] = t;
    int w = bit / 64, b = bit % 64;
    if (w >= n) return 0;
    unsigned long long v = strtoull(words[n - 1 - w], NULL, 16);
    return (v >> b) & 1;
}

void hwinfo_json(struct jw *w, struct disk *disks, int ndisks) {
    char vendor[96], product[128], board[64], family[96], buf[256];
    rd("/sys/class/dmi/id/sys_vendor", vendor, sizeof vendor);
    rd("/sys/class/dmi/id/product_name", product, sizeof product);
    rd("/sys/class/dmi/id/product_family", family, sizeof family);
    rd("/sys/class/dmi/id/board_name", board, sizeof board);
    char path[PATH_MAX];
    env_path(path, sizeof path, "/sys/firmware/efi");
    int uefi = !access(path, F_OK);
    uint64_t ram = 0;
    env_path(path, sizeof path, "/proc/meminfo");
    char *mi = read_file(path, NULL);
    if (mi) {
        char *m = strstr(mi, "MemTotal:");
        if (m) ram = strtoull(m + 9, NULL, 10) * 1024;
        free(mi);
    }
    struct comp c[10] = {{"cpu"}, {"gpu"}, {"display"}, {"wifi"}, {"touchpad"},
                         {"storage"}, {"audio"}, {"sleep"}, {"dgpu"}, {"battery"}};
    for (int i = 0; i < 10; i++) set(&c[i], "missing", "not_found");

    // ---- CPU
    char cpu[128] = "";
    int threads = 0, cores = 0;
    env_path(path, sizeof path, "/proc/cpuinfo");
    char *ci = read_file(path, NULL);
    if (ci) {
        for (char *l = ci; l && *l;) {
            char *nl = strchr(l, '\n');
            if (nl) *nl = 0;
            if (!strncmp(l, "processor", 9)) threads++;
            if (!cpu[0] && !strncmp(l, "model name", 10) && strchr(l, ':')) snprintf(cpu, sizeof cpu, "%s", strchr(l, ':') + 2);
            if (!cores && !strncmp(l, "cpu cores", 9) && strchr(l, ':')) cores = atoi(strchr(l, ':') + 1);
            l = nl ? nl + 1 : NULL;
        }
        free(ci);
    }
    trim(cpu);
    char drv[64];
    rd("/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver", drv, sizeof drv);
    if (cpu[0]) {
        c[0].present = 1;
        snprintf(c[0].value, sizeof c[0].value, "%s", cpu);
        snprintf(buf, sizeof buf, "%d cores, %d threads%s%s", cores ? cores : threads, threads, drv[0] ? " · " : "", drv);
        set(&c[0], "ready", buf);
    }

    // ---- PCI: GPUs and Wi-Fi
    char base[PATH_MAX];
    env_path(base, sizeof base, "/sys/bus/pci/devices");
    // On Android the daemon may not read unlabeled PCI attributes (SELinux): only the DRM scan below there.
    DIR *dir = E.root[0] || !E.live ? opendir(base) : NULL;
    struct dirent *e;
    struct gpu {
        unsigned v, d;
        char drv[64], ps[16], path[PATH_MAX];
    } gpus[4];
    int ngpu = 0;
    while (dir && (e = readdir(dir))) {
        if (e->d_name[0] == '.') continue;
        char dp[PATH_MAX], cls[32], ven[16], dev[16];
        snprintf(dp, sizeof dp, "%s/%s/class", base, e->d_name);
        rd_abs(dp, cls, sizeof cls);
        snprintf(dp, sizeof dp, "%s/%s/vendor", base, e->d_name);
        rd_abs(dp, ven, sizeof ven);
        snprintf(dp, sizeof dp, "%s/%s/device", base, e->d_name);
        rd_abs(dp, dev, sizeof dev);
        snprintf(dp, sizeof dp, "%s/%s/driver", base, e->d_name);
        link_base(dp, drv, sizeof drv);
        unsigned cl = strtoul(cls, NULL, 16), v = strtoul(ven, NULL, 16), d = strtoul(dev, NULL, 16);
        if ((cl >> 16) == 0x03 && ngpu < 4) {
            struct gpu *g = &gpus[ngpu++];
            memset(g, 0, sizeof *g);
            snprintf(dp, sizeof dp, "%s/%s", base, e->d_name);
            if (!realpath(dp, g->path)) snprintf(g->path, sizeof g->path, "%s", dp);
            g->v = v;
            g->d = d;
            snprintf(g->drv, sizeof g->drv, "%s", drv);
            snprintf(dp, sizeof dp, "%s/%s/power_state", base, e->d_name);
            rd_abs(dp, g->ps, sizeof g->ps);
        } else if ((cl >> 8) == 0x0280) {  // network controller: Wi-Fi
            c[3].present = 1;
            snprintf(c[3].value, sizeof c[3].value, "%s", wifi_name(v, d));
            set(&c[3], drv[0] ? "ready" : "missing", drv[0] ? drv : "no_driver");
        }
    }
    if (dir) closedir(dir);
    // GPUs with a DRM driver, from /sys/class/drm/cardN/device (links and directories are readable everywhere;
    // the iGPU's ID files are labeled sysfs_gpu). Merged with the PCI scan above, which only works where every
    // PCI attribute is readable (host tests, permissive boots).
    env_path(base, sizeof base, "/sys/class/drm");
    dir = opendir(base);
    while (dir && (e = readdir(dir)) && ngpu < 4) {
        if (strncmp(e->d_name, "card", 4) || strchr(e->d_name, '-')) continue;
        char dp[PATH_MAX], real[PATH_MAX], ven[16], dev[16];
        snprintf(dp, sizeof dp, "%s/%s/device", base, e->d_name);
        if (!realpath(dp, real)) continue;
        int dup = 0;
        for (int i = 0; i < ngpu; i++)
            if (!strcmp(gpus[i].path, real)) dup = 1;
        if (dup) continue;
        struct gpu *g = &gpus[ngpu++];
        memset(g, 0, sizeof *g);
        snprintf(g->path, sizeof g->path, "%s", real);
        snprintf(dp, sizeof dp, "%s/vendor", real);
        rd_abs(dp, ven, sizeof ven);
        snprintf(dp, sizeof dp, "%s/device", real);
        rd_abs(dp, dev, sizeof dev);
        g->v = strtoul(ven, NULL, 16);
        g->d = strtoul(dev, NULL, 16);
        snprintf(dp, sizeof dp, "%s/driver", real);
        link_base(dp, g->drv, sizeof g->drv);
    }
    if (dir) closedir(dir);
    // The display GPU is the first one that is not NVIDIA (the iGPU); an NVIDIA GPU next to it is the dGPU, kept
    // off on OpenBook for now (docs/nvidia.md).
    struct gpu *ig = NULL, *dg = NULL;
    for (int i = 0; i < ngpu; i++)
        if (gpus[i].v != 0x10de && !ig) ig = &gpus[i];
    for (int i = 0; i < ngpu; i++)
        if (gpus[i].v == 0x10de && &gpus[i] != ig && !dg) dg = &gpus[i];
    if (!ig && ngpu) ig = &gpus[0], dg = NULL;
    if (ig) {
        c[1].present = 1;
        snprintf(c[1].value, sizeof c[1].value, "%s",
                 ig->v ? gpu_name(ig->v, ig->d) : name_by_driver(ig->drv) ? name_by_driver(ig->drv) : "Graphics");
        if (!strcmp(ig->drv, "amdgpu") || !strcmp(ig->drv, "i915") || !strcmp(ig->drv, "xe")) set(&c[1], "ready", ig->drv);
        else if (ig->drv[0]) set(&c[1], "limited", "software_rendering");
        else set(&c[1], "missing", "no_driver");
    }
    if (dg) {
        c[8].present = 1;
        snprintf(c[8].value, sizeof c[8].value, "%s", gpu_name(dg->v, dg->d));
        if (dg->drv[0]) set(&c[8], "ready", dg->drv);
        else set(&c[8], "off", !strcmp(dg->ps, "D3cold") ? "powered_down" : "no_driver");
    }
    char p[32];
    prop_get("ro.hardware.vulkan", p, sizeof p);
    if (!strcmp(p, "pastel") && !strcmp(c[1].state, "ready")) set(&c[1], "limited", "software_rendering");
    // Wi-Fi without a PCI device (USB or SDIO adapters): any wlan interface.
    env_path(base, sizeof base, "/sys/class/net");
    dir = opendir(base);
    while (dir && (e = readdir(dir))) {
        char dp[PATH_MAX];
        snprintf(dp, sizeof dp, "%s/%s/wireless", base, e->d_name);
        if (e->d_name[0] == '.' || access(dp, F_OK)) continue;
        snprintf(dp, sizeof dp, "%s/%s/device/driver", base, e->d_name);
        link_base(dp, drv, sizeof drv);
        if (!c[3].present) {
            c[3].present = 1;
            if (name_by_driver(drv)) snprintf(c[3].value, sizeof c[3].value, "%s", name_by_driver(drv));
            else snprintf(c[3].value, sizeof c[3].value, "Wi-Fi (%s)", e->d_name);
        }
        snprintf(buf, sizeof buf, "%s · %s", drv[0] ? drv : "wlan", e->d_name);
        set(&c[3], "ready", buf);
    }
    if (dir) closedir(dir);
    env_path(path, sizeof path, "/sys/class/bluetooth/hci0");
    if (c[3].present && !access(path, F_OK)) {
        size_t l = strlen(c[3].detail);
        snprintf(c[3].detail + l, sizeof c[3].detail - l, " · Bluetooth hci0");
    }

    // ---- display: DRM connectors
    env_path(base, sizeof base, "/sys/class/drm");
    dir = opendir(base);
    while (dir && (e = readdir(dir))) {
        if (strncmp(e->d_name, "card", 4) || !strchr(e->d_name, '-')) continue;
        char dp[PATH_MAX], st[32], modes[64];
        snprintf(dp, sizeof dp, "%s/%s/status", base, e->d_name);
        rd_abs(dp, st, sizeof st);
        if (strcmp(st, "connected")) continue;
        snprintf(dp, sizeof dp, "%s/%s/modes", base, e->d_name);
        rd_abs(dp, modes, sizeof modes);
        char *nl = strchr(modes, '\n');
        if (nl) *nl = 0;
        int mw = 0, mh = 0;
        sscanf(modes, "%dx%d", &mw, &mh);
        const char *conn = strchr(e->d_name, '-') + 1;
        // Prefer the built-in panel.
        if (c[2].present && strncmp(conn, "eDP", 3)) continue;
        c[2].present = 1;
        if (mw) snprintf(c[2].value, sizeof c[2].value, "%d × %d", mw, mh);
        else snprintf(c[2].value, sizeof c[2].value, "connected");
        set(&c[2], "ready", conn);
    }
    if (dir) closedir(dir);

    // ---- touchpad (and touchscreen) from the input devices
    env_path(path, sizeof path, "/proc/bus/input/devices");
    // On Android the daemon may not read /proc/bus/input (unlabeled procfs): the app reports the touchpad there.
    char *in = E.root[0] || !E.live ? read_file(path, NULL) : NULL;
    int touchscreen = 0;
    if (in) {
        char name[128] = "", prop[64] = "", abs_[256] = "";
        for (char *l = in; l;) {
            char *nl = strchr(l, '\n');
            if (nl) *nl = 0;
            if (!strncmp(l, "N: Name=", 8)) {
                snprintf(name, sizeof name, "%s", l + 8);
                size_t k = strlen(name);
                if (k && name[k - 1] == '"') name[k - 1] = 0;
                if (name[0] == '"') memmove(name, name + 1, strlen(name));
            } else if (!strncmp(l, "B: PROP=", 8)) {
                snprintf(prop, sizeof prop, "%s", l + 8);
            } else if (!strncmp(l, "B: ABS=", 7)) {
                snprintf(abs_, sizeof abs_, "%s", l + 7);
            } else if (!*l) {  // end of a device block
                unsigned long pr = strtoul(prop, NULL, 16);
                int mt = abs_[0] && bit_set(abs_, 0x35);
                if (mt && (pr & 1) && !c[4].present) {  // INPUT_PROP_POINTER + multitouch: a touchpad
                    c[4].present = 1;
                    snprintf(c[4].value, sizeof c[4].value, "%s", name);
                    set(&c[4], "ready", "hid-multitouch");
                } else if (mt && (pr & 2)) {
                    touchscreen = 1;
                }
                name[0] = prop[0] = abs_[0] = 0;
            }
            l = nl ? nl + 1 : NULL;
        }
        free(in);
    }
    if (touchscreen && c[4].present) {
        size_t l = strlen(c[4].detail);
        snprintf(c[4].detail + l, sizeof c[4].detail - l, " · touchscreen too");
    }

    // ---- storage: the largest internal disk that is not the stick
    struct disk *best = NULL;
    for (int i = 0; i < ndisks; i++)
        if (!disks[i].boot_disk && !disks[i].external && (!best || disks[i].size > best->size)) best = &disks[i];
    if (best) {
        c[5].present = 1;
        snprintf(c[5].value, sizeof c[5].value, "%s", best->model);
        char hb[32];
        human_bytes(best->size, hb, sizeof hb);
        snprintf(buf, sizeof buf, "%s · %s", !strcmp(best->bus, "nvme") ? "NVMe" : best->bus, hb);
        set(&c[5], "ready", buf);
    }

    // ---- audio: ALSA cards; Cirrus CS35L56 speaker amplifiers need tuning files for this laptop
    env_path(path, sizeof path, "/proc/asound/cards");
    char *cards = read_file(path, NULL);
    if (cards && strstr(cards, "]:")) {
        c[6].present = 1;
        char *br = strstr(cards, "]:");
        char *eol = strchr(br, '\n');
        if (eol) *eol = 0;
        snprintf(c[6].value, sizeof c[6].value, "%s", br + 3);
        trim(c[6].value);
        set(&c[6], "ready", "snd-hda-intel");
        env_path(path, sizeof path, "/sys/bus/acpi/devices/CSC3556:00");
        if (!access(path, F_OK)) {
            char ssid[32];
            rd("/sys/class/sound/hwC0D0/subsystem_id", ssid, sizeof ssid);
            char want[96];
            snprintf(want, sizeof want, "cs35l56-b0-dsp1-misc-%s", ssid[0] ? ssid + 2 : "");
            env_path(base, sizeof base, "/vendor/firmware/cirrus");
            DIR *fw = opendir(base);
            int tuned = 0;
            while (fw && (e = readdir(fw)))
                if (ssid[0] && !strncasecmp(e->d_name, want, strlen(want))) tuned = 1;
            size_t l = strlen(c[6].value);
            snprintf(c[6].value + l, sizeof c[6].value - l, " + CS35L56");
            // Only when the firmware directory could be listed and has no tuning for this laptop's codec ID.
            if (fw && ssid[0] && !tuned) set(&c[6], "limited", "speaker_tuning_missing");
            if (fw) closedir(fw);
        }
    }
    free(cards);

    // ---- sleep
    char ms[64];
    rd("/sys/power/mem_sleep", ms, sizeof ms);
    if (!ms[0]) {
        // Android: mem_sleep is unlabeled sysfs; /sys/power/state is readable. "freeze" = suspend-to-idle.
        char st[64];
        rd("/sys/power/state", st, sizeof st);
        if (strstr(st, "mem")) snprintf(ms, sizeof ms, "%s", strstr(st, "freeze") ? "[s2idle]" : "[deep]");
        else if (strstr(st, "freeze")) snprintf(ms, sizeof ms, "[s2idle]");
    }
    if (ms[0]) {
        c[7].present = 1;
        char *b = strchr(ms, '[');
        char cur[16] = "";
        if (b) sscanf(b + 1, "%15[^]]", cur);
        snprintf(c[7].value, sizeof c[7].value, "%s", cur[0] ? cur : ms);
        set(&c[7], "new", "untested_model");
    }

    // ---- battery
    struct power pw;
    power_read(&pw);
    if (pw.have_battery) {
        c[9].present = 1;
        snprintf(c[9].value, sizeof c[9].value, "%d %%", pw.battery_pct);
        set(&c[9], "ready", pw.ac ? "charging" : "on_battery");
    }

    // ---- the G14's dGPU, if this domain could not read the PCI attributes to find it (docs/HARDWARE.md)
    if (!c[8].present && !strcmp(board, "GA403WR")) {
        c[8].present = 1;
        snprintf(c[8].value, sizeof c[8].value, "%s", gpu_name(0x10de, 0x2f58));
        set(&c[8], "off", "powered_down");
    }

    // ---- known gaps of tested models
    for (size_t g = 0; g < ARRAY_LEN(GAPS); g++)
        if (!strcmp(board, GAPS[g].board))
            for (int i = 0; i < 10; i++)
                if (!strcmp(c[i].id, GAPS[g].component) && c[i].present && !strcmp(c[i].state, "ready"))
                    set(&c[i], GAPS[g].state, GAPS[g].detail);
    for (int i = 0; i < 10; i++)
        if (!strcmp(c[i].id, "sleep") && c[i].present && !strcmp(c[i].state, "new")) {
            for (size_t g = 0; g < ARRAY_LEN(GAPS); g++)
                if (!strcmp(board, GAPS[g].board) && !strcmp(GAPS[g].component, "sleep")) set(&c[i], GAPS[g].state, GAPS[g].detail);
        }

    const char *verdict = "ready";
    for (int i = 0; i < 10; i++) {
        if ((!strcmp(c[i].id, "dgpu") || !strcmp(c[i].id, "battery")) && !c[i].present) continue;
        if (!strcmp(c[i].state, "missing") || !strcmp(c[i].detail, "software_rendering")) verdict = "limited";
    }
    if (!c[2].present || !c[5].present) verdict = "unsupported";

    jw_obj(w, "hw");
    jw_str(w, "schema", "openbook-hwinfo/1");
    jw_obj(w, "machine");
    jw_str(w, "vendor", vendor);
    char prod[256];
    snprintf(prod, sizeof prod, "%s%s%s", family[0] && !strstr(product, family) ? family : "",
             family[0] && !strstr(product, family) ? " " : "", product);
    jw_str(w, "product", prod);
    jw_str(w, "board", board);
    jw_str(w, "firmware", uefi ? "UEFI" : "BIOS");
    // This boot came through OpenBook's unsigned systemd-boot, so Secure Boot is off.
    jw_str(w, "secure_boot", E.live ? "off" : "unknown");
    jw_u64(w, "ram_bytes", ram);
    jw_str(w, "cpu", cpu);
    jw_endo(w);
    jw_str(w, "verdict", verdict);
    jw_arr(w, "components");
    for (int i = 0; i < 10; i++) {
        if ((!strcmp(c[i].id, "dgpu") || !strcmp(c[i].id, "battery")) && !c[i].present) continue;
        jw_obj(w, NULL);
        jw_str(w, "id", c[i].id);
        jw_str(w, "state", c[i].state);
        jw_str(w, "value", c[i].value);
        jw_str(w, "detail", c[i].detail);
        jw_endo(w);
    }
    jw_enda(w);
    jw_endo(w);
    (void)ngpu;
}
