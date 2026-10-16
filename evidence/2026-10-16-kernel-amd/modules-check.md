# Vendor module check: anybook-amd-gbos-16302624

Kernel release `6.18.21-android17-5-g04a5a95cd7be`; 134 vendor modules, 100 GKI modules in the dist; 4696 vmlinux exports; 4204 KMI-listed symbols.

vermagic expected: `6.18.21-android17-5-g04a5a95cd7be SMP preempt mod_unload modversions`

Result: 134 ok, 0 failing.


| module | license | intree | imports vmlinux / GKI mod / vendor mod | MODULE_FIRMWARE | status |
|---|---|---|---|---|---|
| amdxdna.ko | GPL | Y | 253 / 0 / 10 | 4 | ok |
| ac.ko | GPL | Y | 36 / 0 / 0 | 0 | ok |
| battery.ko | GPL | Y | 59 / 0 / 0 | 0 | ok |
| fan.ko | GPL | Y | 32 / 0 / 1 | 0 | ok |
| platform_profile.ko | GPL | Y | 44 / 0 / 0 | 0 | ok |
| thermal.ko | GPL | Y | 63 / 0 / 0 | 0 | ok |
| video.ko | GPL | Y | 81 / 0 / 1 | 0 | ok |
| btintel.ko | GPL | Y | 47 / 13 / 0 | 4 | ok |
| btmtk.ko | GPL | Y | 52 / 12 / 0 | 6 | ok |
| btrtl.ko | GPL | Y | 31 / 7 / 0 | 48 | ok |
| btusb.ko | GPL | Y | 105 / 23 / 14 | 0 | ok |
| tpm.ko | GPL | Y | 123 / 0 / 0 | 0 | ok |
| tpm_crb.ko | GPL | Y | 34 / 0 / 6 | 0 | ok |
| cs_dsp.ko | GPL v2 | Y | 58 / 0 / 0 | 0 | ok |
| amdgpu.ko | GPL and additional rights | Y | 833 / 0 / 115 | 583 | ok |
| amdxcp.ko | GPL and additional rights | Y | 17 / 0 / 0 | 0 | ok |
| drm_display_helper.ko | GPL and additional rights | Y | 110 / 0 / 0 | 0 | ok |
| drm_buddy.ko | Dual MIT/GPL | Y | 32 / 0 / 0 | 0 | ok |
| drm_exec.ko | Dual MIT/GPL | Y | 19 / 0 / 0 | 0 | ok |
| drm_panel_backlight_quirks.ko | GPL | Y | 9 / 0 / 0 | 0 | ok |
| drm_suballoc_helper.ko | Dual MIT/GPL | Y | 37 / 0 / 0 | 0 | ok |
| drm_ttm_helper.ko | GPL | Y | 15 / 0 / 0 | 0 | ok |
| gpu-sched.ko | GPL and additional rights | Y | 104 / 0 / 0 | 0 | ok |
| virtio-gpu.ko | GPL and additional rights | Y | 264 / 0 / 2 | 0 | ok |
| amd_sfh.ko | Dual BSD/GPL | Y | 77 / 0 / 0 | 0 | ok |
| hid-asus.ko | GPL | Y | 56 / 0 / 3 | 0 | ok |
| i2c-hid-acpi.ko | GPL | Y | 17 / 0 / 4 | 0 | ok |
| i2c-hid.ko | GPL | Y | 58 / 0 / 0 | 0 | ok |
| hwmon.ko | GPL | Y | 83 / 0 / 0 | 0 | ok |
| k10temp.ko | GPL | Y | 24 / 0 / 1 | 0 | ok |
| i2c-algo-bit.ko | GPL | Y | 17 / 0 / 0 | 0 | ok |
| i2c-designware-core.ko | GPL | Y | 57 / 0 / 0 | 0 | ok |
| i2c-designware-platform.ko | GPL | Y | 32 / 0 / 6 | 0 | ok |
| i2c-piix4.ko | GPL | Y | 46 / 0 / 1 | 0 | ok |
| i2c-smbus.ko | GPL | Y | 35 / 0 / 0 | 0 | ok |
| sparse-keymap.ko | GPL v2 | Y | 13 / 0 / 0 | 0 | ok |
| mt76-connac-lib.ko | Dual BSD/GPL | Y | 43 / 0 / 28 | 0 | ok |
| mt76.ko | Dual BSD/GPL | Y | 166 / 0 / 36 | 0 | ok |
| mt7921-common.ko | Dual BSD/GPL | Y | 86 / 0 / 140 | 0 | ok |
| mt7921e.ko | Dual BSD/GPL | Y | 58 / 1 / 58 | 6 | ok |
| mt7925-common.ko | Dual BSD/GPL | Y | 89 / 0 / 131 | 0 | ok |
| mt7925e.ko | Dual BSD/GPL | Y | 57 / 1 / 55 | 2 | ok |
| mt792x-lib.ko | Dual BSD/GPL | Y | 75 / 0 / 35 | 0 | ok |
| rtw89_8851b.ko | Dual BSD/GPL | Y | 18 / 0 / 32 | 1 | ok |
| rtw89_8851be.ko | Dual BSD/GPL | Y | 8 / 0 / 16 | 0 | ok |
| rtw89_8852a.ko | Dual BSD/GPL | Y | 17 / 0 / 31 | 1 | ok |
| rtw89_8852ae.ko | Dual BSD/GPL | Y | 8 / 0 / 16 | 0 | ok |
| rtw89_8852b.ko | Dual BSD/GPL | Y | 16 / 0 / 30 | 1 | ok |
| rtw89_8852b_common.ko | Dual BSD/GPL | Y | 17 / 0 / 12 | 0 | ok |
| rtw89_8852be.ko | Dual BSD/GPL | Y | 8 / 0 / 16 | 0 | ok |
| rtw89_8852c.ko | Dual BSD/GPL | Y | 18 / 0 / 39 | 1 | ok |
| rtw89_8852ce.ko | Dual BSD/GPL | Y | 8 / 0 / 16 | 0 | ok |
| rtw89_8922a.ko | Dual BSD/GPL | Y | 19 / 0 / 45 | 1 | ok |
| rtw89_8922ae.ko | Dual BSD/GPL | Y | 8 / 0 / 16 | 0 | ok |
| rtw89_core.ko | Dual BSD/GPL | Y | 118 / 1 / 66 | 0 | ok |
| rtw89_pci.ko | Dual BSD/GPL | Y | 80 / 0 / 16 | 0 | ok |
| amd-pmc.ko | GPL v2 | Y | 88 / 0 / 0 | 0 | ok |
| asus-nb-wmi.ko | GPL | Y | 10 / 0 / 3 | 0 | ok |
| asus-wmi.ko | GPL | Y | 93 / 7 / 14 | 0 | ok |
| serial-multi-instantiate.ko | GPL | Y | 31 / 0 / 0 | 0 | ok |
| wmi-bmof.ko | GPL | Y | 12 / 0 / 3 | 0 | ok |
| wmi.ko | GPL | Y | 64 / 0 / 0 | 0 | ok |
| spi-amd-pci.ko | GPL | Y | 14 / 0 / 1 | 0 | ok |
| spi-amd.ko | Dual BSD/GPL | Y | 21 / 0 / 0 | 0 | ok |
| ucsi_acpi.ko | GPL v2 | Y | 33 / 0 / 0 | 0 | ok |
| virtio_dma_buf.ko | GPL | Y | 9 / 0 / 0 | 0 | ok |
| virtio_input.ko | GPL | Y | 37 / 0 / 0 | 0 | ok |
| mac80211.ko | GPL | Y | 223 / 2 / 117 | 0 | ok |
| cfg80211.ko | GPL | Y | 204 / 7 / 0 | 2 | ok |
| snd-ctl-led.ko | GPL | Y | 50 / 0 / 0 | 0 | ok |
| snd-hda-codec-atihdmi.ko | GPL | Y | 8 / 0 / 20 | 0 | ok |
| snd-hda-codec-hdmi.ko | GPL | Y | 53 / 0 / 41 | 0 | ok |
| snd-hda-codec-intelhdmi.ko | GPL | Y | 11 / 0 / 34 | 0 | ok |
| snd-hda-codec-nvhdmi-mcp.ko | GPL | Y | 13 / 0 / 12 | 0 | ok |
| snd-hda-codec-nvhdmi.ko | GPL | Y | 7 / 0 / 18 | 0 | ok |
| snd-hda-codec-simplehdmi.ko | GPL | Y | 21 / 0 / 13 | 0 | ok |
| snd-hda-codec-tegrahdmi.ko | GPL | Y | 7 / 0 / 17 | 0 | ok |
| snd-hda-codec-alc260.ko | GPL | Y | 7 / 0 / 23 | 0 | ok |
| snd-hda-codec-alc262.ko | GPL | Y | 7 / 0 / 21 | 0 | ok |
| snd-hda-codec-alc268.ko | GPL | Y | 9 / 0 / 29 | 0 | ok |
| snd-hda-codec-alc269.ko | GPL | Y | 33 / 0 / 87 | 0 | ok |
| snd-hda-codec-alc662.ko | GPL | Y | 9 / 0 / 45 | 0 | ok |
| snd-hda-codec-alc680.ko | GPL | Y | 7 / 0 / 13 | 0 | ok |
| snd-hda-codec-alc861.ko | GPL | Y | 7 / 0 / 20 | 0 | ok |
| snd-hda-codec-alc861vd.ko | GPL | Y | 7 / 0 / 19 | 0 | ok |
| snd-hda-codec-alc880.ko | GPL | Y | 7 / 0 / 20 | 0 | ok |
| snd-hda-codec-alc882.ko | GPL | Y | 7 / 0 / 34 | 0 | ok |
| snd-hda-codec-realtek-lib.ko | GPL | Y | 21 / 0 / 26 | 0 | ok |
| snd-hda-cirrus-scodec.ko | GPL | Y | 11 / 0 / 0 | 0 | ok |
| snd-hda-scodec-component.ko | GPL | Y | 27 / 0 / 0 | 0 | ok |
| snd-hda-scodec-cs35l56-i2c.ko | GPL | Y | 13 / 0 / 5 | 0 | ok |
| snd-hda-scodec-cs35l56.ko | GPL | Y | 65 / 0 / 26 | 4 | ok |
| snd-hda-codec-generic.ko | GPL | Y | 44 / 0 / 70 | 0 | ok |
| snd-hda-codec.ko | GPL | Y | 153 / 0 / 61 | 0 | ok |
| snd-hda-intel.ko | GPL | Y | 107 / 0 / 20 | 0 | ok |
| snd-hda-core.ko | GPL | Y | 132 / 0 / 0 | 0 | ok |
| snd-acp-i2s.ko | Dual BSD/GPL | Y | 12 / 0 / 0 | 0 | ok |
| snd-acp-legacy-common.ko | Dual BSD/GPL | Y | 25 / 0 / 0 | 0 | ok |
| snd-acp-legacy-mach.ko | GPL v2 | Y | 34 / 0 / 2 | 0 | ok |
| snd-acp-mach.ko | GPL v2 | Y | 39 / 0 / 1 | 0 | ok |
| snd-acp-pci.ko | Dual BSD/GPL | Y | 28 / 0 / 15 | 0 | ok |
| snd-acp-pcm.ko | Dual BSD/GPL | Y | 23 / 0 / 0 | 0 | ok |
| snd-acp-pdm.ko | Dual BSD/GPL | Y | 11 / 0 / 0 | 0 | ok |
| snd-acp-sof-mach.ko | GPL v2 | Y | 14 / 0 / 2 | 0 | ok |
| snd-acp70.ko | Dual BSD/GPL | Y | 20 / 0 / 8 | 0 | ok |
| snd-amd-acpi-mach.ko | GPL | Y | 7 / 0 / 0 | 0 | ok |
| snd-amd-sdw-acpi.ko | Dual BSD/GPL | Y | 13 / 0 / 0 | 0 | ok |
| snd-soc-acpi-amd-match.ko | GPL | Y | 6 / 0 / 0 | 0 | ok |
| snd-pci-ps.ko | GPL v2 | Y | 41 / 0 / 3 | 0 | ok |
| snd-ps-pdm-dma.ko | GPL v2 | Y | 33 / 0 / 0 | 0 | ok |
| snd-ps-sdw-dma.ko | GPL | Y | 31 / 0 / 0 | 0 | ok |
| snd-soc-ps-mach.ko | GPL v2 | Y | 12 / 0 / 0 | 0 | ok |
| snd-acp-config.ko | Dual BSD/GPL | Y | 13 / 0 / 0 | 0 | ok |
| snd-soc-cs-amp-lib.ko | GPL | Y | 25 / 0 / 3 | 0 | ok |
| snd-soc-cs35l56-shared.ko | GPL | Y | 43 / 0 / 4 | 0 | ok |
| snd-soc-dmic.ko | GPL | Y | 26 / 0 / 0 | 0 | ok |
| snd-soc-max98357a.ko | GPL v2 | Y | 16 / 0 / 0 | 0 | ok |
| snd-soc-max98388.ko | GPL | Y | 40 / 0 / 0 | 0 | ok |
| snd-soc-nau8821.ko | GPL | Y | 61 / 0 / 0 | 0 | ok |
| snd-soc-nau8825.ko | GPL | Y | 73 / 0 / 0 | 0 | ok |
| snd-soc-rl6231.ko | GPL v2 | Y | 12 / 0 / 0 | 0 | ok |
| snd-soc-rt1019.ko | GPL v2 | Y | 28 / 0 / 2 | 0 | ok |
| snd-soc-rt5682-i2c.ko | GPL v2 | Y | 37 / 0 / 14 | 0 | ok |
| snd-soc-rt5682.ko | GPL v2 | Y | 62 / 0 / 2 | 0 | ok |
| snd-soc-rt5682s.ko | GPL v2 | Y | 74 / 0 / 0 | 0 | ok |
| snd-sof-amd-acp.ko | Dual BSD/GPL | Y | 44 / 0 / 14 | 0 | ok |
| snd-sof-amd-acp63.ko | Dual BSD/GPL | Y | 10 / 0 / 7 | 0 | ok |
| snd-sof-amd-acp70.ko | Dual BSD/GPL | Y | 10 / 0 / 7 | 0 | ok |
| snd-sof-amd-rembrandt.ko | Dual BSD/GPL | Y | 10 / 0 / 5 | 0 | ok |
| snd-sof-pci.ko | Dual BSD/GPL | Y | 19 / 0 / 11 | 0 | ok |
| snd-sof-probes.ko | GPL v2 | Y | 51 / 0 / 8 | 0 | ok |
| snd-sof-utils.ko | Dual BSD/GPL | Y | 8 / 0 / 0 | 0 | ok |
| snd-sof.ko | Dual BSD/GPL | Y | 152 / 0 / 1 | 0 | ok |
| snd-sof-xtensa-dsp.ko | Dual BSD/GPL | Y | 11 / 0 / 0 | 0 | ok |
