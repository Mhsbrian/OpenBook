# OpenBook live boot report: live-002 (g14)

Build: `OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys`; SELinux permissive; capture: final; 139 modules (amdgpu loaded).

| Area | Verdict | Facts |
|---|---|---|
| boot_completed | yes | {"seconds": 28.2, "second_stage_s": 2.9} |
| display | yes | {"connectors": ["card0-DP-1 disconnected disabled", "card0-DP-2 disconnected disabled", "card0-DP-3 disconnected disabled", "card0-DP-4 disconnected disabled", "card0-DP-5 disconnected disabled", "card0-DP-6 disconnected |
| gpu_hal | yes | {"hal": "amdgpu", "egl": "angle", "vulkan": "radv", "gralloc": "minigbm", "hwcomposer": "drm"} |
| data_on_stick | yes | {"data_kib": 58801152, "used_kib": 1122300, "byname_targets": ["sda"]} |
| wifi | yes | {"interface": true, "status": ["Wifi is enabled", "Wifi scanning is only available when wifi is enabled", "==== ClientModeManager instance: ConcreteClientModeManager{id=224730 iface=wlan0 role=ROLE_CLIENT_PRIMARY} ===="] |
| touchpad | yes | {"devices": ["ASCE1206:00 04F3:3315 Touchpad"]} |
| keyboard | yes | {"devices": ["Asus Keyboard"]} |
| dgpu_off | yes | {"functions": ["0000:64:00.0 0x10de 0x2f58 0x030000 D3cold suspended", "0000:64:00.1 0x10de 0x2f80 0x040300 D3cold suspended"]} |
| backlight | yes | {"devices": ["amdgpu_bl0 273348/399000"]} |
| battery | yes | {"supplies": ["ACAD: Mains  ", "BAT1: Battery Charging 24", "ucsi-source-psy-USBC000:001: USB  ", "ucsi-source-psy-USBC000:002: USB"]} |
| cpu_power | yes | {"facts": ["freeze mem disk", "[s2idle]", "active", "amd-pstate-epp", "balance_performance"]} |
| touchpad_gestures | yes | {"classes": "TOUCH / TOUCH_MT / TOUCHPAD"} |
| key_layouts | yes | {"layouts": {"Asus Keyboard": "/vendor/usr/keylayout/Vendor_0b05_Product_19b6.kl", "Asus WMI hotkeys": "/vendor/usr/keylayout/Asus_WMI_hotkeys.kl"}} |
| lid_switch | yes | {"power_button": true} |
| lid_and_power_config | yes | {"config": {"mLidKeyboardAccessibility": "1", "getLidBehavior": "LID_BEHAVIOR_SLEEP", "mShortPressOnPowerBehavior": "6", "mLongPressOnPowerBehavior": "LONG_PRESS_POWER_GLOBAL_ACTIONS"}, "lid": "LID_OPEN"} |
| s0i3 | unknown | {"suspends": 0, "fails": "0", "total_hw_sleep_us": 0, "last_hw_sleep_us": "0", "last_failed_dev": null, "not_deepest": 0, "resume_causes": []} |
| health_hal | yes | {"service": "running", "charge_counter_uah": 956000, "charge_now_uah": 964000, "state_of_health_pct": 88.7, "android_health": 2, "cycle_count": "0", "charge_limit_pct": "100"} |
| lid_events | unknown | {"sleeps_on_close": 0, "wakes_on_open": 0, "suspended_while_closed": null} |
| epp_modes | yes | {"set_counts": {"balance_performance": 1, "performance": 1}, "screen_went_off": false, "battery_saver_seen": false} |
| touchpad_clock_warnings | yes | {"count": 0} |
| kbd_backlight | yes | {"leds": ["asus::kbd_backlight 0/3"]} |
| epp | yes | {"policies": ["24 balance_performance"]} |
| touchpad_clock | unknown | {"note": "no touchpad events captured"} |
| gfx_run | yes | {"rc": 0, "seconds": 834.4, "out_bytes": 6358016} |
| gfx_vk | NO | {"renderer": "AMD Radeon 890M Graphics (RADV STRIX1)", "cases": 66226, "counts": {"Pass": 43222, "Fail": 8, "Crash": 2, "Skip": 22975, "Flake": 19}, "seconds": 270, "amdgpu_events": 5, "not_in_mesa_ci": 10} |
| gfx_vk14 | yes | {"renderer": "AMD Radeon 890M Graphics (RADV STRIX1)", "cases": 66226, "counts": {"Pass": 45220, "Fail": 5, "Crash": 0, "Skip": 21001}, "seconds": 222, "amdgpu_events": 0, "not_in_mesa_ci": 5} |
| gfx_gles_angle | yes | {"renderer": "ANGLE (AMD, Vulkan 1.1.354 (AMD Radeon 890M Graphics (RADV STRIX1) (0x0000150E)), radv-26.2.5)", "cases": 13671, "counts": {"Pass": 13099, "Fail": 0, "Crash": 0, "Skip": 509, "Warn": 63}, "seconds": 35, "am |
| gfx_gles_mesa | yes | {"renderer": "AMD Radeon 890M Graphics (radeonsi, strix1, ACO, DRM 3.64, 6.18.21-android17-5-g44a90255c95f)", "cases": 13671, "counts": {"Pass": 13621, "Fail": 0, "Crash": 0, "Skip": 48, "Warn": 2}, "seconds": 33, "amdgp |
| gfx_egl | yes | {"renderer": null, "cases": 1287, "counts": {"Pass": 847, "Fail": 0, "Crash": 0, "Skip": 438, "Warn": 2}, "seconds": 204, "amdgpu_events": 0, "not_in_mesa_ci": null} |
| gfx_angle_end2end | yes | {"renderer": null, "cases": 2364, "counts": {"Pass": 1814, "Fail": 2, "Crash": 0, "Skip": 329, "Missing": 219}, "seconds": 66, "amdgpu_events": 0, "not_in_mesa_ci": null} |
