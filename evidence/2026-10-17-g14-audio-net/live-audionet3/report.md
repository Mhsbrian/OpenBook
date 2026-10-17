# OpenBook live boot report: live-001 (vm)

Build: `OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys`; SELinux permissive; capture: final; 144 modules (amdgpu loaded).

| Area | Verdict | Facts |
|---|---|---|
| boot_completed | yes | {"seconds": 17.6, "second_stage_s": 2.6} |
| display | yes | {"connectors": ["card0-Virtual-1 connected disabled 1920x1200"], "surfaceflinger": "running", "screenshot": true} |
| gpu_hal | yes | {"hal": "virtio", "egl": "angle", "vulkan": "pastel", "gralloc": "minigbm", "hwcomposer": "drm"} |
| data_on_stick | yes | {"data_kib": 14943232, "used_kib": 358948, "byname_targets": ["sda"]} |
| wifi_regulatory | yes | {"driver": ".", "country": "00"} |
| wifi_enabled | NO | {"supplicant": ""} |
| wifi_scan | NO | {"networks": 0, "ghz2": 0, "ghz5": 0, "ghz6": 0} |
| wifi_connected | NO | {"freq_mhz": null, "signal_dbm": null, "tx_mbit": null, "rx_mbit": null} |
| wifi_dhcp | NO | {"prefix": "", "gateway": false} |
| wifi_gateway_ping | unknown | {} |
| wifi_internet | NO | {} |
| wifi_iperf3 | unknown | {"up_mbit_s": null, "down_mbit_s": null, "seconds": null} |
| bt_enabled | NO | {"hal": "running"} |
| bt_paired | NO | {"bonded": 0} |
| audio_card | NO | {"card": -1, "pcm": ""} |
| audio_loopback_alsa | NO | {"card": null, "tone_bin_dbfs": null, "noise_bin_dbfs": null, "glitched_slices": null, "slices": null, "playback_error": null, "capture_error": null, "error": "no built-in sound card"} |
| audio_loopback_android | NO | {"tone_bin_dbfs": -36.3, "noise_bin_dbfs": -47.3, "glitched_slices": 30, "slices": 30, "xruns": 1, "media_volume": "10/15", "input_error": 0, "output_error": 0, "error": null} |
