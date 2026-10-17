# ANAL-177 evidence: dEQP and CTS graphics subsets for the G14 (2026-10-17)

Details and the owner checklist: `docs/graphics-amd.md`, "dEQP and CTS on the G14". **Nothing here ran on the G14's
Radeon 890M yet.** The pre-check ran on the build host's Radeon 610M (gfx1036, RDNA2); QEMU and Cuttlefish tested the
plumbing.

| Folder | What | Result |
|---|---|---|
| `build/` | The G14 product's test modules (`deqp-binary`, the dEQP app, ANGLE's end2end helper app) built in the AOSP lane; RADV without android-strict; deqp-runner | 7 min 56 s, cgroup peak 50.4 GB; product images untouched; the non-strict build differs from the image's in `vulkan.radv.so` only |
| `caselists/` | The exact case lists (gzip) and `caselists.json` (settings, counts, sha256 of every source and output) | EGL 1,287, GLES2 3,598, GLES3 5,359, GLES3.1 4,714, VK 66,226, ANGLE end2end 2,364 |
| `precheck-610m/` | `scripts/graphics/pre-check.sh` on the 610M: `gfx-report.md`, versions, each pass's suite, `failures.csv`, `results.csv.gz`, the failing cases' logs | VK 1.1: 43,248 pass / 57 fail / 1 crash; VK 1.4: 45,161 / 5 / 0; GLES radeonsi: 13,621 / 0 / 0 |
| `addon/` | The add-on `openbook-gfxcheck-20261017`: its JSON, payload `VERSION.json`, both manifests, skip lists, the live-init host test, and the entry the applier writes on a copy of `combined` | Payload 88.2 MB (bzip2, 289 MB unpacked, 2,061 files); 89.3 MB on the ESP; host test 9/9; a fresh `combined` stick keeps 65.3 MB free (the applier needs 50.3 MB) |
| `qemu/` | The add-on on a copy of `openbook-live-20261017-combined`, end to end in QEMU/OVMF, 40 cases per list (SwiftShader, no AMD GPU) | One boot, 193 s, all 6 expected steps. 2,060 files unpacked and checked; `vk` 40/40, `gles-angle` 111 pass / 9 not supported, `egl` 40/40, ANGLE end2end 32 pass / 8 skipped; `vk14` and `gles-mesa` skipped (no AMD GPU); settings restored, apps removed; 0.9 MB of results; `gfx_*` verdicts in `live-001/report.md` |
| `cuttlefish/` | `run.sh`'s two app parts with the full lists on our Cuttlefish build: ANGLE over gfxstream on the 610M, SELinux permissive | dEQP-EGL: 1,287 cases, 822 pass, 0 fail, 463 not supported, 2 warnings, 198 s. ANGLE end2end: 2,364 subset, 1,802 pass, 7 fail (all `TextureBorderClamp*`), 336 skipped by ANGLE, 219 not in this build, 147 s |

Mesa CI expectation files used for comparison (Mesa 26.2.5 `src/amd/ci/`): `radv-raphael-*` and
`radeonsi-mendocino-*` for the 610M; `radv-navi31-*`, `radeonsi-vangogh-*` and `angle-radv-stoney-*` for the G14. There is
no gfx1150 file in 26.2.5, nor in Mesa main at `335d5698` (2026-10-17).
