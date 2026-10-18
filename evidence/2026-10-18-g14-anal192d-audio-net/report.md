# OpenBook live boot report: live-001 (g14)

Build: `OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys`; SELinux permissive; capture: final; 141 modules (amdgpu loaded).

| Area | Verdict | Facts |
|---|---|---|
| boot_completed | yes | {"seconds": 28.1, "second_stage_s": 2.9} |
| display | yes | {"connectors": ["card0-DP-1 disconnected disabled", "card0-DP-2 disconnected disabled", "card0-DP-3 disconnected disabled", "card0-DP-4 disconnected disabled", "card0-DP-5 disconnected disabled", "card0-DP-6 disconnected |
| refresh_rate | NO | {"resolution": "2880x1800", "active_hz": 120.0, "fastest_mode_hz": 120.0, "primary_render_max_hz": 60.0, "primary_physical_max_hz": "none", "render_hz_now": 60.0, "seconds_by_render_hz": {"120.00": 4.1, "60.00": 84.2}} |
| gpu_hal | yes | {"hal": "amdgpu", "egl": "angle", "vulkan": "radv", "gralloc": "minigbm", "hwcomposer": "drm"} |
| data_on_stick | yes | {"data_kib": 58780672, "used_kib": 1799812, "byname_targets": ["sda"]} |
| wifi | yes | {"interface": true, "status": ["Wifi is enabled", "Wifi scanning is only available when wifi is enabled", "==== ClientModeManager instance: ConcreteClientModeManager{id=16512 iface=wlan0 role=ROLE_CLIENT_PRIMARY} ===="], |
| touchpad | yes | {"devices": ["ASCE1206:00 04F3:3315 Touchpad"]} |
| keyboard | yes | {"devices": ["Asus Keyboard"]} |
| dgpu_off | yes | {"functions": ["0000:64:00.0 0x10de 0x2f58 0x030000 D3cold suspended", "0000:64:00.1 0x10de 0x2f80 0x040300 D3cold suspended"]} |
| backlight | yes | {"devices": ["amdgpu_bl0 202693/399000"]} |
| battery | yes | {"supplies": ["ACAD: Mains  ", "BAT1: Battery Discharging 15", "ucsi-source-psy-USBC000:001: USB  ", "ucsi-source-psy-USBC000:002: USB"]} |
| cpu_power | yes | {"facts": ["freeze mem disk", "[s2idle]", "active", "amd-pstate-epp", "balance_performance"]} |
| touchpad_gestures | yes | {"classes": "TOUCH / TOUCH_MT / TOUCHPAD"} |
| key_layouts | yes | {"layouts": {"Asus Keyboard": "/vendor/usr/keylayout/Vendor_0b05_Product_19b6.kl", "Asus WMI hotkeys": "/vendor/usr/keylayout/Asus_WMI_hotkeys.kl"}} |
| lid_switch | yes | {"power_button": true} |
| lid_and_power_config | yes | {"config": {"mLidKeyboardAccessibility": "1", "getLidBehavior": "LID_BEHAVIOR_SLEEP", "mShortPressOnPowerBehavior": "6", "mLongPressOnPowerBehavior": "LONG_PRESS_POWER_GLOBAL_ACTIONS"}, "lid": "LID_OPEN"} |
| s0i3 | unknown | {"suspends": 0, "fails": "0", "total_hw_sleep_us": 0, "last_hw_sleep_us": "0", "last_failed_dev": null, "not_deepest": 0, "resume_causes": []} |
| health_hal | yes | {"service": "running", "charge_counter_uah": 629000, "charge_now_uah": 607000, "state_of_health_pct": 88.7, "android_health": 2, "cycle_count": "0", "charge_limit_pct": "100"} |
| lid_events | unknown | {"sleeps_on_close": 0, "wakes_on_open": 0, "suspended_while_closed": null} |
| epp_modes | yes | {"set_counts": {"balance_performance": 63, "performance": 63}, "screen_went_off": false, "battery_saver_seen": false} |
| touchpad_clock_warnings | yes | {"count": 0} |
| kbd_backlight | yes | {"leds": ["asus::kbd_backlight 0/3"]} |
| epp | yes | {"policies": ["24 balance_performance"]} |
| touchpad_clock | unknown | {"note": "no touchpad events captured"} |
| wifi_regulatory | yes | {"driver": "mt7925e", "country": "US"} |
| wifi_enabled | yes | {"supplicant": "running"} |
| wifi_scan | yes | {"networks": 54, "ghz2": 19, "ghz5": 35, "ghz6": 0} |
| wifi_pno | yes | {"driver_offers": true} |
| wifi_connected | yes | {"freq_mhz": 2437.0, "signal_dbm": -22, "tx_mbit": 286.7, "rx_mbit": 286.7} |
| wifi_dhcp | yes | {"prefix": "24", "gateway": true} |
| wifi_gateway_ping | NO | {"loss_pct": 100, "avg_ms": null} |
| wifi_internet | yes | {} |
| wifi_iperf3 | unknown | {"up_mbit_s": null, "down_mbit_s": null, "seconds": null} |
| bt_enabled | yes | {"hal": "running"} |
| bt_paired | yes | {"bonded": 1} |
| audio_card | yes | {"card": 2, "pcm": "02-00: ALC285 Analog : ALC285 Analog : playback 1 : capture 1"} |
| audio_loopback_alsa | yes | {"card": 2, "tone_bin_dbfs": -35.9, "noise_bin_dbfs": -76.1, "glitched_slices": 3, "slices": 33, "playback_error": "", "capture_error": "", "error": null} |
| bridge_config | yes | {"native_bridge": "libberberis_arm64.so", "binfmt": true, "guest_libs": 57, "abilist": "x86_64,arm64-v8a"} |
| bridge_exec | yes | {"uname_machine": "aarch64", "hwcap": "0x9fb", "error": null} |
| bridge_id_registers | yes | {"sigill": 0, "first_sigill": -1, "midr": "0x410fd034", "isar0": "0x211120", "pfr0": "0x11"} |
| bridge_fp_estimates | yes | {"cases": 6900, "bad": 0, "first_bad": ""} |
| bridge_int_simd | yes | {"crc32": true, "neon_fma": true} |
| audio_loopback_android | yes | {"tone_bin_dbfs": -49.4, "noise_bin_dbfs": -114.3, "glitched_slices": 0, "slices": 30, "xruns": 1, "media_volume": "10/15", "out_device": 2, "in_device": 5, "hal_input_pads": 0, "hal_output_drops": 0, "hal_skipped_transf |
| audio_android_clean | yes | {"glitched_slices": 0, "hal_input_pads": 0} |
| audio_routes | yes | {"speaker_port": 2, "mic_port": 5, "headphone_jacks": 1, "mic_jacks": 2, "wired_connected": false, "a2dp_connected": false, "pacing": "false"} |
