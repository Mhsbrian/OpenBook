# SELinux denials: live-001

- Denial lines in the kernel log that the enforcing entries would hit (helper and helper-induced excluded): **29**
- Distinct (source, target, class) in kernel log + logcat: **13** (13 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {'helper': 42, 'kernel': 2, 'android': 27}, logcat {'helper': 362, 'kernel': 2, 'android': 68}

| source | target | class | permissions | example |
|---|---|---|---|---|
| audioserver | tmpfs | file | map read write |  |
| crash_dump | resourcecache_data_file | file | getattr map open read | /data/resource-cache/data@resource-cache@com.android.systemui-dynamic-Pg0c.frro@idmap |
| hal_audio_default | tmpfs | file | map read write | memfd:MessageQueue |
| hal_light_default | sysfs_gpu | dir | search | drm |
| init | debugfs_bootreceiver_tracing | dir | add_name | enable |
| kernel | openbook_vendor_fw_file | system | firmware_load | /vendor/firmware/amdgpu/psp_14_0_0_toc.bin |
| keystore | hal_gatekeeper_default | binder | call |  |
| keystore | hal_gatekeeper_service | service_manager | find |  |
| openbook_pc_setup | sysfs_gpu | file | open read | /sys/devices/pci0000:00/0000:00:08.1/0000:65:00.0/vendor |
| platform_app | bluetooth_lea_prop | file | getattr map open read | /dev/__properties__/u:object_r:bluetooth_lea_prop:s0 |
| secure_element | system_data_file | dir | add_name create | oat_primary |
| secure_element | system_data_file | file | create | SecureElement.3739.tmp |
| system_app | vendor_default_prop | file | getattr map open | /dev/__properties__/u:object_r:vendor_default_prop:s0 |
