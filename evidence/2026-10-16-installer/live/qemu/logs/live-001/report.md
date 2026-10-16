# OpenBook live boot report: live-001 (vm)

Build: `OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys`; SELinux permissive; capture: final; 144 modules (amdgpu loaded).

| Area | Verdict | Facts |
|---|---|---|
| boot_completed | NO | {"seconds": -1.0, "second_stage_s": 2.6} |
| display | yes | {"connectors": ["card0-Virtual-1 connected enabled 1920x1200"], "surfaceflinger": "running", "screenshot": true} |
| gpu_hal | yes | {"hal": "virtio", "egl": "angle", "vulkan": "pastel", "gralloc": "minigbm", "hwcomposer": "drm"} |
| data_on_stick | yes | {"data_kib": 15008768, "used_kib": 696596, "byname_targets": ["sda"]} |
