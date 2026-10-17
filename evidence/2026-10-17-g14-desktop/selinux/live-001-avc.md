# SELinux denials: live-001

- Android denial lines in the kernel log (helper and helper-induced excluded): **66**
- Distinct (source, target, class) in kernel log + logcat: **257** (22 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {'helper': 328, 'android': 66}, logcat {'helper': 7125, 'android': 2789, 'induced': 31}

| source | target | class | permissions | example |
|---|---|---|---|---|
| bootanim | graphics_device | chr_file | getattr | /dev/dri/card0 |
| bootanim | sysfs | dir | open read | /sys/devices/pci0000:00/0000:00:08.1/0000:65:00.0/drm |
| bootanim | sysfs | file | getattr open read | /sys/devices/pci0000:00/0000:00:08.1/0000:65:00.0/uevent |
| bootanim | vendor_default_prop | file | getattr map open | /dev/__properties__/u:object_r:vendor_default_prop:s0 |
| hal_graphics_allocator_default | default_prop | file | getattr map open read | /dev/__properties__/u:object_r:default_prop:s0 |
| hal_graphics_allocator_default | graphics_device | chr_file | getattr | /dev/dri/card0 |
| hal_graphics_allocator_default | sysfs | dir | open read | /sys/devices/pci0000:00/0000:00:08.1/0000:65:00.0/drm |
| hal_graphics_allocator_default | sysfs | file | getattr open read | /sys/devices/pci0000:00/0000:00:08.1/0000:65:00.0/vendor |
| hal_graphics_composer_default | sysfs | dir | open read | /sys/devices/pci0000:00/0000:00:08.1/0000:65:00.0/drm |
| hal_graphics_composer_default | sysfs | file | getattr open read | /sys/devices/pci0000:00/0000:00:08.1/0000:65:00.0/drm/card0/card0-eDP-1/amdgpu_bl0/bl_power |
| hal_light_default | sysfs | file | getattr open read | /sys/devices/pci0000:00/0000:00:08.1/0000:65:00.0/drm/card0/card0-eDP-1/amdgpu_bl0/max_brightness |
| hal_thermal_default | sysfs | file | getattr open read | /sys/devices/pci0000:00/0000:00:02.3/0000:63:00.0/ieee80211/phy0/hwmon5/name |
| init | debugfs_bootreceiver_tracing | dir | add_name | enable |
| init | sysfs | file | open write | /sys/devices/pci0000:00/0000:00:08.3/0000:67:00.0/usb4/4-1/4-1:1.0/host0/target0:0:0/0:0:0:0/block/sda/queue/discard_max_bytes |
| keystore | hal_gatekeeper_default | binder | call |  |
| keystore | hal_gatekeeper_service | service_manager | find |  |
| surfaceflinger | sysfs | dir | open read | /sys/devices/pci0000:00/0000:00:08.1/0000:65:00.0/drm |
| surfaceflinger | sysfs | file | getattr open read | /sys/devices/pci0000:00/0000:00:08.1/0000:65:00.0/uevent |
| surfaceflinger | vendor_default_prop | file | getattr map open | /dev/__properties__/u:object_r:vendor_default_prop:s0 |
| system_server | sysfs | file | getattr open read | /sys/devices/pci0000:00/0000:00:08.3/0000:67:00.0/usb3/3-4/3-4:1.0/0003:0B05:19B6.0001/country |
| system_server | sysfs_leds | file | getattr open read | /sys/devices/pci0000:00/0000:00:08.3/0000:67:00.0/usb3/3-4/3-4:1.0/0003:0B05:19B6.0001/leds/asus::kbd_backlight/max_brightness |
| system_server | vendor_default_prop | file | getattr map open | /dev/__properties__/u:object_r:vendor_default_prop:s0 |
