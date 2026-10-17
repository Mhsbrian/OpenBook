# SELinux denials: live-001

- Denial lines in the kernel log that the enforcing entries would hit (helper and helper-induced excluded): **14**
- Distinct (source, target, class) in kernel log + logcat: **7** (7 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {'helper': 83, 'android': 14}, logcat {'helper': 408, 'android': 59}

| source | target | class | permissions | example |
|---|---|---|---|---|
| audioserver | tmpfs | file | map read write |  |
| crash_dump | resourcecache_data_file | file | getattr map open read | /data/resource-cache/data@resource-cache@com.android.systemui-dynamic-4Cqp.frro@idmap |
| hal_audio_default | tmpfs | file | map read write | memfd:MessageQueue |
| init | debugfs_bootreceiver_tracing | dir | add_name | enable |
| keystore | hal_gatekeeper_default | binder | call |  |
| keystore | hal_gatekeeper_service | service_manager | find |  |
| platform_app | bluetooth_lea_prop | file | getattr map open read | /dev/__properties__/u:object_r:bluetooth_lea_prop:s0 |
