# nvk-rm-clean: NVK on NVIDIA's open kernel driver

NVK is Mesa's Vulkan driver for NVIDIA GPUs. Upstream, it runs only on nouveau. This directory holds what makes it
run on NVIDIA's open kernel driver (open-gpu-kernel-modules 615.78.08): its RM backend, `libnv_bionic_native.so`.
OpenBook ships both as the NVIDIA driver for apps, the OpenBook NVK package (`docs/nvk-openbook.md`).

Everything here comes from the clean-room tree of ANAL-324 (path A), at commit
`ea217004c40fac92b6e3d17af01ad9e0024a003f`. The clean-side run of ANAL-330 wrote the parts that had no public source,
and ANAL-326 tested the result on an RTX 4090. ANAL-349's clean-side run added patch `0027` (an Android fix) and
ANAL-351's patch `0028` (the present copy on the copy engine); each ran on the G14. `clean-commit.txt` lists every file of that commit with its git blob, and
`scripts/nvk-provenance-check.sh` checks that the files here are those blobs, byte for byte.

| Path | What it is |
|---|---|
| `backend/` | The RM backend (Rust, MIT, `backend/LICENSE`). `scripts/mesa-android-build.sh`'s `rm` step builds it. |
| `../patches/nvk/` | NVK on Android (ANAL-240, written for nouveau). |
| `../patches/nvk-rm-clean/` | NVK on the RM backend. They go on top of Mesa 26.2.5 and `../patches/upstream`. |
| `SPEC.md` | The clean-room work items (S, H and V). |
| `PROVENANCE.md` | Where every file came from, and who wrote what from which public source. |
| `scripts/scan.py` | The provenance gate's scanner. |
| `scripts/test-backend.sh` | The backend's host unit tests (no GPU). |
| `clean-commit.txt` | The clean-room commit's files and their blobs. |

## Rules

- **Nothing that cites NVIDIA's closed userspace driver enters this repository.** `scripts/nvk-provenance-check.sh`
  runs `scripts/scan.py` on every path of NVIDIA app support, and the build and the stage refuse to run unless it
  reports 0 hits.
- **Code changes here come from a clean-side run**: an author who has read only public sources and this tree. The
  clean-room exclusion list of ANAL-324 still applies. A change is a new commit of the clean-room tree, tested, then
  brought here with `clean-commit.txt` regenerated.
- **Commits** use `B Honey <9922368+Mhsbrian@users.noreply.github.com>`.

## Build and test

```bash
scripts/nvk-provenance-check.sh                                   # 0 hits, every clean-room file unchanged
scripts/mesa-android-build.sh fetch deps clc rm setup build install verify -- nvk-rm-clean
mesa/nvk-rm-clean/scripts/test-backend.sh                         # backend unit tests, no GPU
scripts/nvk-stage.sh                                              # into the AOSP tree, for the G14 product
```

The build writes `~/anybook/mesa/out/nvk-rm-clean/vendor/lib64/{hw/vulkan.nouveau.so,libnv_bionic_native.so,
libdrm.so,libelf_mesa.so}`. Its directories and patch commits are those of the clean-room build, so it gives the same
bytes as the build ANAL-326 tested (`device/anybook/common/nvk/tested-bytes.txt`).
