# OpenBook live boot report: capture-after (g14)

Build: `OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/20261019.quire2:userdebug/test-keys`; SELinux enforcing; capture: final; 141 modules (amdgpu loaded).

| Area | Verdict | Facts |
|---|---|---|
| boot_completed | yes | {"seconds": 8.116, "second_stage_s": 0.909158} |
| display | yes | {"connectors": ["card0-DP-1 disconnected disabled", "card0-DP-2 disconnected disabled", "card0-DP-3 disconnected disabled", "card0-DP-4 disconnected disabled", "card0-DP-5 disconnected disabled", "card0-DP-6 disconnected |
| refresh_rate | yes | {"resolution": "2880x1800", "active_hz": 120.0, "fastest_mode_hz": 120.0, "primary_render_max_hz": 1000.0, "primary_physical_max_hz": 1000.0, "render_hz_now": 120.0, "seconds_by_render_hz": {"120.00": 149.7}} |
| gpu_hal | yes | {"hal": "amdgpu", "egl": "angle", "vulkan": "radv", "gralloc": "minigbm", "hwcomposer": "drm"} |
| data_on_stick | yes | {"data_kib": 986743808, "used_kib": 7173048, "byname_targets": ["nvme0n", "nvme0n1p"]} |
| installer_nvram | NO | {"boot_order": null, "boot_current": null, "entries": []} |
| installer_log | unknown | {"dry_runs": 0, "installs": 0, "refused": [], "ended": []} |
| wifi | yes | {"interface": true, "status": ["Wifi is enabled", "Wifi scanning is only available when wifi is enabled", "==== ClientModeManager instance: ConcreteClientModeManager{id=7773 iface=wlan0 role=ROLE_CLIENT_PRIMARY} ===="],  |
| touchpad | yes | {"devices": ["ASCE1206:00 04F3:3315 Touchpad"]} |
| keyboard | yes | {"devices": ["Asus Keyboard"]} |
| dgpu_off | yes | {"functions": ["0000:64:00.0 0x10de 0x2f58 0x030000 D3cold suspended", "0000:64:00.1 0x10de 0x2f80 0x040300 D3cold suspended"]} |
| backlight | yes | {"devices": ["amdgpu_bl0 239399/399000"]} |
| battery | yes | {"supplies": ["ACAD: Mains  ", "BAT1: Battery Charging 99", "ucsi-source-psy-USBC000:001: USB  ", "ucsi-source-psy-USBC000:002: USB"]} |
| cpu_power | yes | {"facts": ["freeze mem disk", "[s2idle]", "active", "amd-pstate-epp", "balance_performance"]} |
| touchpad_gestures | yes | {"classes": "TOUCH / TOUCH_MT / TOUCHPAD"} |
| key_layouts | yes | {"layouts": {"Asus Keyboard": "/vendor/usr/keylayout/Vendor_0b05_Product_19b6.kl", "Asus WMI hotkeys": "/vendor/usr/keylayout/Asus_WMI_hotkeys.kl"}} |
| lid_switch | yes | {"power_button": true} |
| lid_and_power_config | yes | {"config": {"mLidKeyboardAccessibility": "1", "getLidBehavior": "LID_BEHAVIOR_SLEEP", "mShortPressOnPowerBehavior": "6", "mLongPressOnPowerBehavior": "LONG_PRESS_POWER_GLOBAL_ACTIONS"}, "lid": "LID_OPEN"} |
| s0i3 | unknown | {"suspends": 0, "fails": "0", "total_hw_sleep_us": 0, "last_hw_sleep_us": "0", "last_failed_dev": null, "not_deepest": 0, "resume_causes": []} |
| health_hal | yes | {"service": "running", "charge_counter_uah": 3997000, "charge_now_uah": 3997000, "state_of_health_pct": 88.2, "android_health": 2, "cycle_count": "0", "charge_limit_pct": "100"} |
| lid_events | yes | {"sleeps_on_close": 1, "wakes_on_open": 1, "suspended_while_closed": null} |
| epp_modes | yes | {"set_counts": {"balance_performance": 254, "performance": 8, "power": 246}, "screen_went_off": true, "battery_saver_seen": false} |
| touchpad_clock_warnings | yes | {"count": 0} |
| kbd_backlight | yes | {"leds": ["asus::kbd_backlight 0/3"]} |
| epp | yes | {"policies": ["24 balance_performance"]} |
| touchpad_clock | unknown | {"note": "no touchpad events captured"} |
