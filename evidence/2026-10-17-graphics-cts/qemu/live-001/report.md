# OpenBook live boot report: live-001 (vm)

Build: `OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys`; SELinux permissive; capture: final; 144 modules (amdgpu loaded).

| Area | Verdict | Facts |
|---|---|---|
| boot_completed | yes | {"seconds": 17.6, "second_stage_s": 2.6} |
| display | yes | {"connectors": ["card0-Virtual-1 connected enabled 1920x1200"], "surfaceflinger": "running", "screenshot": true} |
| gpu_hal | yes | {"hal": "virtio", "egl": "angle", "vulkan": "pastel", "gralloc": "minigbm", "hwcomposer": "drm"} |
| data_on_stick | yes | {"data_kib": 14924800, "used_kib": 655768, "byname_targets": ["sda"]} |
| gfx_run | yes | {"rc": 0, "seconds": 40.9, "out_bytes": 899584} |
| gfx_vk | yes | {"renderer": "SwiftShader Device (LLVM 16.0.0)", "cases": 40, "counts": {"Pass": 40, "Fail": 0, "Crash": 0}, "seconds": 0, "amdgpu_events": 0, "not_in_mesa_ci": 0} |
| gfx_vk14 | unknown | {"note": "needs the AMD GPU (hal=virtio)"} |
| gfx_gles_angle | yes | {"renderer": "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (LLVM 16.0.0) (0x0000C0DE)), SwiftShader driver-5.0.0)", "cases": 120, "counts": {"Pass": 111, "Fail": 0, "Crash": 0, "Skip": 9}, "seconds": 1, "amdgpu_events |
| gfx_gles_mesa | unknown | {"note": "needs the AMD GPU (hal=virtio)"} |
| gfx_egl | yes | {"renderer": null, "cases": 40, "counts": {"Pass": 40, "Fail": 0, "Crash": 0}, "seconds": 30, "amdgpu_events": 0, "not_in_mesa_ci": null} |
| gfx_angle_end2end | yes | {"renderer": null, "cases": 40, "counts": {"Pass": 32, "Fail": 0, "Crash": 0, "Skip": 8}, "seconds": 5, "amdgpu_events": 0, "not_in_mesa_ci": null} |
