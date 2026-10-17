# SELinux denials: live-001

- Android denial lines in the kernel log (helper and helper-induced excluded): **41**
- Distinct (source, target, class) in kernel log + logcat: **8** (8 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {'helper': 335, 'android': 41, 'induced': 4}, logcat {'helper': 621, 'android': 67, 'induced': 8}

| source | target | class | permissions | example |
|---|---|---|---|---|
| audioserver | tmpfs | file | map read write |  |
| crash_dump | resourcecache_data_file | file | getattr map open read | /data/resource-cache/product@overlay@AnyBookDesktopFrameworkOverlay.apk@idmap |
| hal_audio_default | tmpfs | file | map read write | memfd:MessageQueue |
| init | debugfs_bootreceiver_tracing | dir | add_name | enable |
| keystore | hal_gatekeeper_default | binder | call |  |
| keystore | hal_gatekeeper_service | service_manager | find |  |
| platform_app | bluetooth_lea_prop | file | getattr map open read | /dev/__properties__/u:object_r:bluetooth_lea_prop:s0 |
| secure_element | system_data_file | dir | add_name | oat_primary |
