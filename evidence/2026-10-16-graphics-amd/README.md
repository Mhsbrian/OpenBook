## ANAL-174 evidence: AMD graphics in the AnyBook device tree

The write-up is in `docs/graphics-amd.md`. Everything here was captured on 2026-10-16 on the build host (Ryzen 9 7950X, Radeon 610M iGPU, RTX 4090).

| Path | What |
|---|---|
| `build/` | Build logs, GNU time, cgroup memory samples and sizes. `build-20261016T180241Z` is the first product build (exit 0, 3:00); `build-20261016T181305Z` is the final one (exit 0), with `anybook_gpu_probe_test`. `*-failed-libdrm_amdgpu-clash` is the first attempt, which failed because AOSP's libdrm_amdgpu claims the same install path. |
| `mesa/` | The Mesa build that went into the image: versions and options (`versions.txt`), NEEDED and symbol check, sha256s, sizes, HAL exports, SONAME renames, setup log. Also the staged `vendor/anybook/mesa` `Android.bp` and `PROVENANCE.txt`. |
| `minigbm-host/` | `scripts/minigbm-amdgpu-host-test.sh`: minigbm's amdgpu backend with `dri_gbm.c`, built for Linux against Arch's Mesa 26.2.4 and run on the 610M. Covers allocations, GPU ↔ mapping round trips across two driver instances, linear-only mode and lifetimes. PASS. |
| `hwtest/` | `scripts/amd-android-hwtest.sh`: the image's own bionic, RADV, radeonsi and `libminigbm_gralloc.so` on the 610M, in a container with no framework. PASS. |
| `vm/` | The final build in Cuttlefish (`CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle`): `cf-boot.log`, props, kernel log (`probe-kernel-log.txt` has the probe's lines), logcat, dmesg, SurfaceFlinger. |
| `vm/desktop/` | `scripts/desktop-capture.sh`: screenshots and windowing/SurfaceFlinger summaries, comparable with `evidence/2026-10-16-desktop/desktop/`. |
| `vm/bench/` | `scripts/cf-gfx-bench.sh`: the same benchmark as ANAL-169, with the same result (0 % janky, 5 ms). |
| `vm/hal/` | Probe properties and `--list`/`--dry-run` output; the device binary on every fixture; `ls -Z` of the AMD files; AVC denials; RADV smoke and hwtest inside the VM; the manually triggered `hal=amdgpu` actions. |
| `vm/avc-compare.txt` | AVC denials: ANAL-169, ANAL-174's first boot (with the `vendor.mesa.*` label, since dropped) and the final build. |
| `probe/` | Host unit test output (3/3), and the host build of the probe on this machine's real sysfs. |
| `image/` | The AMD files in the product output, with sizes, hashes and a strings check of the patched minigbm. |

No image files or Mesa binaries are committed.
