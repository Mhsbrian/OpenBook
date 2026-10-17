# Graphics run: live-001

Mesa CI expectations: `<data dir>/mesa/src/upstream/src/amd/ci` (RADV: navi31, radeonsi: vangogh, ANGLE: stoney).

| Part | Renderer | Cases | Pass | Fail | Crash | Timeout | Skip | Warn | Flake | Not run | Time | Mesa CI: our fails listed / new |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vk | SwiftShader Device (LLVM 16.0.0) | 40 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 s | 0 / 0 |
| vk14 | | | | | | | | | | | | needs the AMD GPU (hal=virtio) |
| gles-angle | ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (LLVM 16.0.0 | 120 | 80 | 0 | 0 | 0 | 40 | 0 | 0 | 0 | 1 s | 0 / 0 |
| gles-mesa | | | | | | | | | | | | needs the AMD GPU (hal=virtio) |
| egl |  | 40 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 30 s |  |
| angle |  | 40 | 35 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 5 s |  |
