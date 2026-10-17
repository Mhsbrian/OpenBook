# SELinux denials: live-002

- Denial lines in the kernel log that the enforcing entries would hit (helper and helper-induced excluded): **22**
- Distinct (source, target, class) in kernel log + logcat: **11** (11 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {'helper': 37, 'kernel': 1, 'android': 21}, logcat {'helper': 370, 'kernel': 1, 'android': 50}

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
| secure_element | system_data_file | file | open | /data/user_de/0/com.android.se/cache/oat_primary/x86_64/SecureElement.art |
