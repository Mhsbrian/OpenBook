# When init chose the GPU HALs, relative to SurfaceFlinger's start (QEMU/OVMF, save-logs case, kernel log)

## desktop2: property trigger (on property:vendor.anybook.gpu.hal=virtio)
[    3.725307] init: processing action (queue_property_triggers) from (<Builtin Action>:0)
[   12.323786] init: processing action (boot) from (/system/etc/init/hw/init.rc:1112)
[   12.601990] init: processing action (enable_property_trigger) from (<Builtin Action>:0)
[   12.618825] init: processing action (vendor.anybook.gpu.hal=virtio) from (/vendor/etc/init/hw/init.openbook.rc:40)
[ro.boottime.surfaceflinger]: [12287359982]

## desktop3: init event queued at early-init (on vendor-anybook-gpu-virtio)
[    3.736789] init: processing action (vendor-anybook-gpu-virtio) from (/vendor/etc/init/hw/init.openbook.rc:41)
[    3.784094] init: processing action (early-fs) from (/system/etc/init/hw/init.rc:551)
[   12.370378] init: processing action (boot) from (/system/etc/init/hw/init.rc:1112)
[ro.boottime.surfaceflinger]: [12340404302]

ro.boottime.* are nanoseconds since boot. On the G14 the desktop2 race was lost once (live-002: SurfaceFlinger abort, 'couldn't find an OpenGL ES implementation').
