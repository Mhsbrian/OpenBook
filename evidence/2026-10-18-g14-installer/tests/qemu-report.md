# OpenBook live boot report: lr-qemu (vm)

Build: `OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys`; SELinux permissive; capture: final; 146 modules (amdgpu loaded).

| Area | Verdict | Facts |
|---|---|---|
| boot_completed | yes | {"seconds": 17.7, "second_stage_s": 2.6} |
| display | yes | {"connectors": ["card0-Virtual-1 connected enabled 1920x1200"], "surfaceflinger": "running", "screenshot": true} |
| refresh_rate | yes | {"resolution": "1920x1200", "active_hz": 75.0, "fastest_mode_hz": 75.0, "primary_render_max_hz": 1000.0, "primary_physical_max_hz": 1000.0, "render_hz_now": 75.0, "seconds_by_render_hz": {"75.00": 97.3}} |
| gpu_hal | yes | {"hal": "virtio", "egl": "angle", "vulkan": "pastel", "gralloc": "minigbm", "hwcomposer": "drm"} |
| data_on_stick | yes | {"data_kib": 14904320, "used_kib": 356548, "byname_targets": ["sda"]} |
| installer_nvram | yes | {"boot_order": ["0002", "0000", "0001", "0003"], "boot_current": "0002", "entries": ["0003 EFI Internal Shell", "0002 UEFI QEMU QEMU USB HARDDRIVE 1-0000:00:01.0-1", "0001 EFI Firmware Setup", "0000 BootManagerMenuApp"]} |
| installer_log | yes | {"dry_runs": 0, "installs": 0, "refused": [], "ended": []} |
| wifi_regulatory | yes | {"driver": ".", "country": "00"} |
| wifi_enabled | NO | {"supplicant": ""} |
| wifi_scan | NO | {"networks": 0, "ghz2": 0, "ghz5": 0, "ghz6": 0} |
| wifi_pno | NO | {"driver_offers": false} |
| wifi_connected | NO | {"freq_mhz": null, "signal_dbm": null, "tx_mbit": null, "rx_mbit": null} |
| wifi_dhcp | NO | {"prefix": "", "gateway": false} |
| wifi_gateway_ping | unknown | {} |
| wifi_internet | NO | {} |
| wifi_iperf3 | unknown | {"up_mbit_s": null, "down_mbit_s": null, "seconds": null} |
| bt_enabled | NO | {"hal": "running"} |
| bt_paired | NO | {"bonded": 0} |
| audio_card | NO | {"card": -1, "pcm": ""} |
| audio_loopback_alsa | NO | {"card": null, "tone_bin_dbfs": null, "noise_bin_dbfs": null, "glitched_slices": null, "slices": null, "playback_error": null, "capture_error": null, "error": "no built-in sound card"} |
| bridge_config | yes | {"native_bridge": "libberberis_arm64.so", "binfmt": true, "guest_libs": 57, "abilist": "x86_64,arm64-v8a"} |
| bridge_exec | yes | {"uname_machine": "aarch64", "hwcap": "0x9fb", "error": null} |
| bridge_id_registers | yes | {"sigill": 0, "first_sigill": -1, "midr": "0x410fd034", "isar0": "0x211120", "pfr0": "0x11"} |
| bridge_fp_estimates | yes | {"cases": 6900, "bad": 0, "first_bad": ""} |
| bridge_int_simd | yes | {"crc32": true, "neon_fma": true} |
| audio_loopback_android | NO | {"tone_bin_dbfs": -36.1, "noise_bin_dbfs": -46.3, "glitched_slices": 30, "slices": 30, "xruns": 1, "media_volume": "10/15", "out_device": 2, "in_device": 5, "hal_input_pads": 0, "hal_output_drops": 0, "hal_skipped_transf |
| audio_android_clean | NO | {"glitched_slices": 30, "hal_input_pads": 0} |
| audio_routes | yes | {"speaker_port": 2, "mic_port": 5, "headphone_jacks": 0, "mic_jacks": 0, "wired_connected": false, "a2dp_connected": false, "pacing": ""} |
