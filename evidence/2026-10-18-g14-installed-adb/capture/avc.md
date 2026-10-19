# SELinux denials: adb-first

- Denial lines in the kernel log that the enforcing entries would hit (helper and helper-induced excluded): **12**
- Distinct (source, target, class) in kernel log + logcat: **9** (9 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {'android': 12, 'helper': 3}, logcat {'android': 26, 'helper': 6}

| source | target | class | permissions | example |
|---|---|---|---|---|
| keystore | hal_gatekeeper_service | service_manager | find |  |
| platform_app | bluetooth_lea_prop | file | read | u:object_r:bluetooth_lea_prop:s0 |
| system_app | hal_audio_default | binder | call |  |
| system_app | hal_authsecret_default | binder | call |  |
| system_app | hal_bluetooth_default | binder | call |  |
| system_app | system_suspend_control_internal_service | service_manager | find |  |
| system_app | system_suspend_control_service | service_manager | find |  |
| system_app | tracingproxy_service | service_manager | find |  |
| system_server | wifi_hal_prop | file | read | u:object_r:wifi_hal_prop:s0 |
