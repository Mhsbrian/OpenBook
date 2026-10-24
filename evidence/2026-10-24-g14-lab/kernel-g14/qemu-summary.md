# ANAL-198 QEMU first-stage check

| run | variant | disks | boot device by | result |
|---|---|---|---|---|
| usb | bm | usb-storage | boot_devices | PASS |
| uas | bm | usb-uas | boot_devices | PASS |
| nvme | bm | nvme | boot_devices | PASS |
| both-uuid | bm | nvme, usb-storage | boot_part_uuid | PASS |
| vm | vm | nvme | boot_devices | PASS |
