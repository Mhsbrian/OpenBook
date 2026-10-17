# SELinux denials: live-001

- Denial lines in the kernel log that the enforcing entries would hit (helper and helper-induced excluded): **51**
- Distinct (source, target, class) in kernel log + logcat: **9** (9 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {'helper': 337, 'android': 51, 'induced': 4}, logcat {'helper': 649, 'android': 82, 'induced': 8}

| source | target | class | permissions | example |
|---|---|---|---|---|
| audioserver | tmpfs | file | map read write |  |
| crash_dump | resourcecache_data_file | file | getattr map open read | /data/resource-cache/product@overlay@AnyBookDesktopFrameworkOverlay.apk@idmap |
| hal_audio_default | tmpfs | file | map read write | memfd:MessageQueue |
| init | debugfs_bootreceiver_tracing | dir | add_name | enable |
| keystore | hal_gatekeeper_default | binder | call |  |
| keystore | hal_gatekeeper_service | service_manager | find |  |
| platform_app | bluetooth_lea_prop | file | getattr map open read | /dev/__properties__/u:object_r:bluetooth_lea_prop:s0 |
| secure_element | system_data_file | dir | add_name create remove_name | SecureElement.2737.tmp |
| secure_element | system_data_file | file | create open write | /data/user_de/0/com.android.se/cache/oat_primary/x86_64/SecureElement.2737.tmp |
