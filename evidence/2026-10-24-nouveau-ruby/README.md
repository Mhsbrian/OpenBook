# ANAL-239 evidence: nouveau for the G14 dGPU, Ruby kernel lane (2026-10-24)

Write-up: `docs/nouveau-ruby.md`. Every check ran on the Ryzen 9 7950X build host, in containers or QEMU/KVM.
**No laptop, stick or release artifact was written.** The RB-20261023-03 images were only read (hashed and
extracted to scratch).

| File | What |
|---|---|
| `series.md` | The 44 nouveau patches: upstream and 6.18.y IDs, v7.3 membership, the Churro mapping, and what was left out and why |
| `kmi-new-symbols.txt` | The 33 symbols patch 0004 adds to the kernel's combined KMI list |
| `kmi-kleaf-added.txt` | All 62 names Kleaf's add-only update wrote into `anybook_amd`; 29 of them were already on other x86_64 lists |
| `kernel-g14/` | `kernel-g14-package.sh` reports for dist `anybook-g14-gbos-16302624-anal239`: images and hashes, module lists (0 problems), signatures, `results.json`, and the 5 standard QEMU runs with serial logs (all PASS) |
| `load-check.{md,json}` | `kernel-nouveau-check.py`: drm_gpuvm, nouveau and the rebuilt lid guard against the new kernel's binaries. 684 imports, 0 problems |
| `rebuild-compare.{md,json}` | The new kernel against RB-20261023-03's boot kernel, vendor_dlkm and system_dlkm: 0 exports removed or changed, 30 added, 3 unprotected; 241 modules unchanged apart from release metadata. PASS |
| `qemu-guest/` | `nouveau-guest-check.sh` in the vm and nvme runs of the new dist: 17/17 each |
| `qemu-baseline/` | The same check on the installed kernel's dist, for the SELinux denial baseline: the same 2 `init` denials, nothing new |
| `firmware-subset.{md,tsv}`, `firmware/` | GSP-RM 570.144 for GB205: 3 files, 64.0 MB, LICENCE.nvidia; staged manifest with sha256 and git blobs |
| `gpu-probe-host.txt` | `anybook_gpu_probe`'s `Decide()`, built on the host against AOSP's libbase, on all 9 fixtures (new: `g14-ga403wr-nouveau.txt` → `amdgpu`) |
| `tests/` | Hook fixture tests (bash and sh, 49/49 each), the checker's planted-fault tests (0 failures), and the checker's self-test on RB-20261023-03 (141/141 modules, 9,127 imports) |
| `repro/` | A second build from a fresh tree with only the repo's scripts, compared with the first |
| `handoff-ANAL-239.json` | `anybook-handoff/1`: pinned artifacts and the checks run on exactly those bytes |
