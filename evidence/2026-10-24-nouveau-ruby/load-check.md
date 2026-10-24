# Offline load check: new vendor modules against the installed kernel

- Kernel: vmlinux sha256 `406d1ca2b07e0f2b0a708d83507afff2811fe0e4ef608e735fae4516f82d8d17`, build ID `293bd76920857ee68ecbf84b46cb9b41c855cc1e`, 4751 exports, 656 protected export names
- Installed modules: 240 (100 signed), vermagic `6.18.21-android17-5-g206eb00bd0c4 SMP preempt mod_unload modversions `
- Imports checked: 684; CRC mismatches 0; missing versions 0; unresolved 0; ambiguous 0; protected imports 0; GPL violations 0; duplicate exports 0; protected exports 0
- Result: **PASS**

| module | sha256 | vermagic ok | imports (by exporter) | exports | depends | problems |
|---|---|---|---|---|---|---|
| drm_gpuvm | `38ab8f5c98930e4c…` | yes | 37 (vmlinux 31, drm_exec 6) | 41 | drm_exec | none |
| nouveau | `5818ae6c2b2721b9…` | yes | 609 (vmlinux 504, drm_display_helper 56, drm_gpuvm 21, gpu_sched 11, drm_exec 4, drm_ttm_helper 4, video 3, hwmon 2, i2c_algo_bit 2, wmi 2) | 0 | drm_display_helper, drm_exec, drm_gpuvm, drm_ttm_helper, gpu-sched, hwmon, i2c-algo-bit, video, wmi | none |
| openbook_lid_guard | `f62ebe3ae5e9c943…` | yes | 38 (vmlinux 38) | 0 | - | none |
