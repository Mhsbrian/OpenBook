# SELinux denials: capture-after

- Denial lines in the kernel log that the enforcing entries would hit (helper and helper-induced excluded): **11**
- Distinct (source, target, class) in kernel log + logcat: **11** (11 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {'kernel': 5, 'android': 6}, logcat {'kernel': 5, 'android': 14}

| source | target | class | permissions | example |
|---|---|---|---|---|
| kernel | ota_metadata_file | file | getattr open read | /metadata/ota/state |
| kernel | super_block_device | lnk_file | relabelto | super |
| kernel | sysfs_ublk | file | getattr | /sys/devices/virtual/misc/ublk-control/ublkc6/uevent |
| keystore | hal_gatekeeper_service | service_manager | find |  |
| platform_app | bluetooth_lea_prop | file | read | u:object_r:bluetooth_lea_prop:s0 |
| system_server | wifi_hal_prop | file | read | u:object_r:wifi_hal_prop:s0 |
| untrusted_app_34 | proc | file | read | devices |
| untrusted_app_34 | proc_tty_drivers | file | read | drivers |
| untrusted_app_34 | qemu_hw_prop | file | read | u:object_r:qemu_hw_prop:s0 |
| untrusted_app_34 | qemu_sf_lcd_density_prop | file | read | u:object_r:qemu_sf_lcd_density_prop:s0 |
| untrusted_app_34 | serialno_prop | file | read | u:object_r:serialno_prop:s0 |
