# OpenBook live boot report: live-001 (g14)

Build: `OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys`; SELinux permissive; capture: final; 139 modules (amdgpu loaded).

| Area | Verdict | Facts |
|---|---|---|
| boot_completed | yes | {"seconds": 28.2, "second_stage_s": 2.9} |
| display | yes | {"connectors": ["card0-DP-1 disconnected disabled", "card0-DP-2 disconnected disabled", "card0-DP-3 disconnected disabled", "card0-DP-4 disconnected disabled", "card0-DP-5 disconnected disabled", "card0-DP-6 disconnected |
| gpu_hal | yes | {"hal": "amdgpu", "egl": "angle", "vulkan": "radv", "gralloc": "minigbm", "hwcomposer": "drm"} |
| data_on_stick | yes | {"data_kib": 58801152, "used_kib": 810464, "byname_targets": ["sda"]} |
| wifi | yes | {"interface": true, "status": ["Wifi is enabled", "Wifi scanning is only available when wifi is enabled", "==== ClientModeManager instance: ConcreteClientModeManager{id=16048 iface=wlan0 role=ROLE_CLIENT_PRIMARY} ===="], |
| touchpad | yes | {"devices": ["ASCE1206:00 04F3:3315 Touchpad"]} |
| keyboard | yes | {"devices": ["Asus Keyboard"]} |
| dgpu_off | yes | {"functions": ["0000:64:00.0 0x10de 0x2f58 0x030000 D3cold suspended", "0000:64:00.1 0x10de 0x2f80 0x040300 D3cold suspended"]} |
| backlight | yes | {"devices": ["amdgpu_bl0 330520/399000"]} |
| battery | yes | {"supplies": ["ACAD: Mains  ", "BAT1: Battery Discharging 35", "ucsi-source-psy-USBC000:001: USB  ", "ucsi-source-psy-USBC000:002: USB"]} |
| cpu_power | yes | {"facts": ["freeze mem disk", "[s2idle]", "active", "amd-pstate-epp", "balance_performance"]} |
| touchpad_gestures | yes | {"classes": "TOUCH / TOUCH_MT / TOUCHPAD"} |
| key_layouts | yes | {"layouts": {"Asus Keyboard": "/vendor/usr/keylayout/Vendor_0b05_Product_19b6.kl", "Asus WMI hotkeys": "/vendor/usr/keylayout/Asus_WMI_hotkeys.kl"}} |
| lid_switch | yes | {"power_button": true} |
| lid_and_power_config | yes | {"config": {"mLidKeyboardAccessibility": "1", "getLidBehavior": "LID_BEHAVIOR_SLEEP", "mShortPressOnPowerBehavior": "6", "mLongPressOnPowerBehavior": "LONG_PRESS_POWER_GLOBAL_ACTIONS"}, "lid": "LID_OPEN"} |
| s0i3 | NO | {"suspends": 1, "fails": "3", "total_hw_sleep_us": 0, "last_hw_sleep_us": "0"} |
| kbd_backlight | yes | {"leds": ["asus::kbd_backlight 0/3"]} |
| epp | yes | {"policies": ["24 balance_performance"]} |
| touchpad_clock | NO | {"frames": 2130, "frames_with_msc": 2025, "msc_backward_steps": 1, "msc_backward_within_1s": 0, "median_msc_per_event_second": 1.017, "median_frame_interval_ms": 4.02} |
| wifi_regulatory | yes | {"driver": "mt7925e", "country": "00"} |
| wifi_enabled | yes | {"supplicant": "running"} |
| wifi_scan | yes | {"networks": 91, "ghz2": 12, "ghz5": 79, "ghz6": 0} |
| wifi_connected | NO | {"freq_mhz": 5320.0, "signal_dbm": -37, "tx_mbit": 1200.9, "rx_mbit": 1921.5} |
| wifi_dhcp | yes | {"prefix": "24", "gateway": true} |
| wifi_gateway_ping | yes | {"loss_pct": 0, "avg_ms": 16.041} |
| wifi_internet | yes | {} |
| wifi_iperf3 | unknown | {"up_mbit_s": null, "down_mbit_s": null, "seconds": null} |
| bt_enabled | yes | {"hal": "running"} |
| bt_paired | NO | {"bonded": 0} |
| audio_card | yes | {"card": 2, "pcm": "02-00: ALC285 Analog : ALC285 Analog : playback 1 : capture 1"} |
| audio_loopback_alsa | yes | {"card": 2, "tone_bin_dbfs": -32.0, "noise_bin_dbfs": -72.5, "glitched_slices": 0, "slices": 33, "playback_error": "", "capture_error": "", "error": null} |
| bridge_config | yes | {"native_bridge": "libberberis_arm64.so", "binfmt": true, "guest_libs": 57, "abilist": "x86_64,arm64-v8a"} |
| bridge_exec | yes | {"uname_machine": "aarch64", "hwcap": "0x9fb", "error": null} |
| bridge_id_registers | yes | {"sigill": 0, "first_sigill": -1, "midr": "0x410fd034", "isar0": "0x211120", "pfr0": "0x11"} |
| bridge_fp_estimates | yes | {"cases": 6900, "bad": 0, "first_bad": ""} |
| bridge_int_simd | yes | {"crc32": true, "neon_fma": true} |
| audio_loopback_android | yes | {"tone_bin_dbfs": -49.8, "noise_bin_dbfs": -90.9, "glitched_slices": 24, "slices": 30, "xruns": 1, "media_volume": "10/15", "input_error": 0, "output_error": 0, "error": null} |
