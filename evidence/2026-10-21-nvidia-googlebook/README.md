# ANAL-187 follow-up: project-churro review and the Googlebook (Ruby) NVIDIA plan (2026-10-21/22)

Analysis: `docs/nvidia-googlebook.md`. Execution: epic ANAL-237.

| File | What it shows |
|---|---|
| `churro-pin.txt` | The project-churro commit reviewed, its GitHub metadata (no licence), the sha256 of every file read for the NVIDIA review, and the upstream commit behind each `nouveau-up-*` backport |
| `g14-ruby-readonly.txt` | A read-only adb snapshot of the G14 on the Googlebook image: builds, PCI devices (dGPU at 64:00.0/.1), DRM nodes, modules, the dGPU hook in the vendor init, firmware and TPM tools present, AC state. Taken as `shell` on a user build: no PCI power state, no dmesg. Nothing was changed on the laptop |
