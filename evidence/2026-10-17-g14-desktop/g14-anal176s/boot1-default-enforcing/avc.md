# SELinux denials: s176avc

- Denial lines in the kernel log that the enforcing entries would hit (helper and helper-induced excluded): **0**
- Distinct (source, target, class) in kernel log + logcat: **7** (7 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {}, logcat {'android': 77}

| source | target | class | permissions | example |
|---|---|---|---|---|
| bluetooth | hal_audio_default_tmpfs | file | read write |  |
| isolated_app | content_capture_service | service_manager | find |  |
| keystore | hal_gatekeeper_service | service_manager | find |  |
| platform_app | bluetooth_finder_prop | file | read | u:object_r:bluetooth_finder_prop:s0 |
| platform_app | bluetooth_lea_prop | file | read | u:object_r:bluetooth_lea_prop:s0 |
| system_server | wifi_hal_prop | file | read | u:object_r:wifi_hal_prop:s0 |
| untrusted_app_29 | audioserver_tmpfs | file | write |  |
