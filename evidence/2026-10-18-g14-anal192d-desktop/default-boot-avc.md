# SELinux denials: d192avc

- Denial lines in the kernel log that the enforcing entries would hit (helper and helper-induced excluded): **0**
- Distinct (source, target, class) in kernel log + logcat: **9** (9 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {}, logcat {'android': 229}

| source | target | class | permissions | example |
|---|---|---|---|---|
| isolated_app | app_data_file | file | setattr | model-info.pb |
| isolated_app | content_capture_service | service_manager | find |  |
| keystore | hal_gatekeeper_service | service_manager | find |  |
| mediaserver | audioserver_tmpfs | file | read write |  |
| openbook_installd | openbook_vendor_fw_file | dir | search | firmware |
| openbook_installd | sysfs_batteryinfo | file | read | type |
| platform_app | bluetooth_finder_prop | file | read | u:object_r:bluetooth_finder_prop:s0 |
| platform_app | bluetooth_lea_prop | file | read | u:object_r:bluetooth_lea_prop:s0 |
| system_server | wifi_hal_prop | file | read | u:object_r:wifi_hal_prop:s0 |
