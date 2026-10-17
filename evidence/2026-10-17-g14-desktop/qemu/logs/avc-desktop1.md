# SELinux denials: live-001

- Android denial lines in the kernel log (helper and helper-induced excluded): **69**
- Distinct (source, target, class) in kernel log + logcat: **16** (16 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {'helper': 335, 'android': 69, 'induced': 4}, logcat {'helper': 623, 'android': 114, 'induced': 8}

| source | target | class | permissions | example |
|---|---|---|---|---|
| audioserver | tmpfs | file | map read write |  |
| bootanim | vendor_default_prop | file | getattr map open | /dev/__properties__/u:object_r:vendor_default_prop:s0 |
| crash_dump | resourcecache_data_file | file | getattr map open read | /data/resource-cache/product@overlay@AnyBookDesktopFrameworkOverlay.apk@idmap |
| hal_audio_default | tmpfs | file | map read write | memfd:MessageQueue |
| init | debugfs_bootreceiver_tracing | dir | add_name | enable |
| keystore | hal_gatekeeper_default | binder | call |  |
| keystore | hal_gatekeeper_service | service_manager | find |  |
| platform_app | bluetooth_lea_prop | file | getattr map open read | /dev/__properties__/u:object_r:bluetooth_lea_prop:s0 |
| platform_app | vendor_default_prop | file | getattr map open | /dev/__properties__/u:object_r:vendor_default_prop:s0 |
| priv_app | vendor_default_prop | file | getattr map open | /dev/__properties__/u:object_r:vendor_default_prop:s0 |
| secure_element | system_data_file | dir | add_name create remove_name | SecureElement.2762.tmp |
| secure_element | system_data_file | file | create open write | /data/user_de/0/com.android.se/cache/oat_primary/x86_64/SecureElement.2762.tmp |
| surfaceflinger | vendor_default_prop | file | getattr map open | /dev/__properties__/u:object_r:vendor_default_prop:s0 |
| system_app | vendor_default_prop | file | getattr map open | /dev/__properties__/u:object_r:vendor_default_prop:s0 |
| system_server | vendor_default_prop | file | getattr map open | /dev/__properties__/u:object_r:vendor_default_prop:s0 |
| untrusted_app_30 | vendor_default_prop | file | getattr map open | /dev/__properties__/u:object_r:vendor_default_prop:s0 |
