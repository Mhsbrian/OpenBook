# SELinux denials: capture-before

- Denial lines in the kernel log that the enforcing entries would hit (helper and helper-induced excluded): **73**
- Distinct (source, target, class) in kernel log + logcat: **14** (14 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {'android': 73, 'helper': 16}, logcat {'android': 79, 'helper': 24}

| source | target | class | permissions | example |
|---|---|---|---|---|
| keystore | hal_gatekeeper_service | service_manager | find |  |
| native_app_zygote | logdr_socket | sock_file | write | logdr |
| native_app_zygote | misctrl_prop | file | read | u:object_r:misctrl_prop:s0 |
| native_app_zygote | tombstoned_crash_socket | sock_file | write | tombstoned_crash |
| native_app_zygote | zygote_next_exec | file | open | /system/bin/zygote_next |
| platform_app | bluetooth_lea_prop | file | read | u:object_r:bluetooth_lea_prop:s0 |
| system_server | wifi_hal_prop | file | read | u:object_r:wifi_hal_prop:s0 |
| untrusted_app | proc_loadavg | file | read | loadavg |
| untrusted_app | proc_version | file | read | version |
| untrusted_app_34 | proc | file | read | devices |
| untrusted_app_34 | proc_tty_drivers | file | read | drivers |
| untrusted_app_34 | qemu_hw_prop | file | read | u:object_r:qemu_hw_prop:s0 |
| untrusted_app_34 | qemu_sf_lcd_density_prop | file | read | u:object_r:qemu_sf_lcd_density_prop:s0 |
| untrusted_app_34 | serialno_prop | file | read | u:object_r:serialno_prop:s0 |
