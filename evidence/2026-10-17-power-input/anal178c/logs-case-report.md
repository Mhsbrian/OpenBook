# OpenBook live boot report: live-001 (g14)

Build: `OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys`; SELinux permissive; capture: final; 144 modules (amdgpu loaded).

| Area | Verdict | Facts |
|---|---|---|
| boot_completed | yes | {"seconds": 17.7, "second_stage_s": 2.7} |
| display | NO | {"connectors": ["card0-Virtual-1 connected disabled 1920x1200"], "surfaceflinger": "running", "screenshot": true} |
| gpu_hal | NO | {"hal": "virtio", "egl": "angle", "vulkan": "pastel", "gralloc": "minigbm", "hwcomposer": "drm"} |
| data_on_stick | yes | {"data_kib": 14924800, "used_kib": 359024, "byname_targets": ["sda"]} |
| wifi | NO | {"interface": false, "status": ["Wifi is disabled", "Wifi scanning is only available when wifi is enabled"], "supplicant": null} |
| touchpad | NO | {"devices": []} |
| keyboard | yes | {"devices": ["AT Translated Set 2 keyboard", "QEMU QEMU USB Keyboard"]} |
| dgpu_off | yes | {"functions": "no NVIDIA function on the bus"} |
| backlight | NO | {"devices": []} |
| battery | NO | {"supplies": []} |
| cpu_power | NO | {"facts": ["freeze mem disk", "s2idle [deep]"]} |
| touchpad_gestures | unknown | {"classes": null} |
| key_layouts | unknown | {"layouts": {}} |
| lid_switch | NO | {"power_button": true} |
| lid_and_power_config | yes | {"config": {"mLidKeyboardAccessibility": "1", "getLidBehavior": "LID_BEHAVIOR_SLEEP", "mShortPressOnPowerBehavior": "6", "mLongPressOnPowerBehavior": "LONG_PRESS_POWER_GLOBAL_ACTIONS"}, "lid": "LID_ABSENT"} |
| s0i3 | unknown | {"suspends": 0, "fails": "0", "total_hw_sleep_us": 0, "last_hw_sleep_us": ""} |
| kbd_backlight | NO | {"leds": []} |
| epp | yes | {"policies": ["1 cat: /sys/devices/system/cpu/cpufreq/policy*/energy_performance_preference: No such file or directory"]} |
| touchpad_clock | unknown | {"note": "no touchpad events captured"} |
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
| bridge_config | yes | {"native_bridge": "libberberis_arm64.so", "binfmt": true, "guest_libs": 57, "abilist": "x86_64,arm64-v8a"} |
| bridge_exec | yes | {"uname_machine": "aarch64", "hwcap": "0x9fb", "error": null} |
| bridge_id_registers | yes | {"sigill": 0, "first_sigill": -1, "midr": "0x410fd034", "isar0": "0x211120", "pfr0": "0x11"} |
| bridge_fp_estimates | yes | {"cases": 6900, "bad": 0, "first_bad": ""} |
| bridge_int_simd | yes | {"crc32": true, "neon_fma": true} |
| audio_loopback_android | NO | {"tone_bin_dbfs": -36.7, "noise_bin_dbfs": -46.2, "glitched_slices": 30, "slices": 30, "xruns": 1, "media_volume": "10/15", "input_error": 0, "output_error": 0, "error": null} |
