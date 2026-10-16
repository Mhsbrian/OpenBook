# ANAL-187 evidence: NVIDIA dGPU research (2026-10-16)

Nothing here ran on the G14. Paths starting with `~` are on the 7950X dev host. Analysis is in `docs/nvidia.md`.

| File | What it shows |
|---|---|
| `kernel-6.18-nouveau.txt` | The AnyBook 6.18 tree: the GB206 device entry, GSP-RM 570.144 firmware names, GB20x display classes, GSP suspend path, nouveau git history (including the `8302d0afeaec` backport), our config (nouveau, Nova, VGA_SWITCHEROO and VFIO off; HDA power_save 0), the nouveau Kconfig selects against our vendor modules, and no NVPCF driver |
| `kernel-6.18-pci-runtime-pm.txt` | Why an unbound dGPU stays in D0: `pm_runtime_forbid` by default, unbound devices left in D0, root-port D3 rules, and snd_hda_intel giving NVIDIA HDA runtime PM only through vga_switcheroo |
| `asus-wmi-6.18.txt` | The `dgpu_disable` and `gpu_mux_mode` store functions and their guards, and the ABI doc |
| `mesa-26.2-nvk.txt` | NVK's conformance gate (Blackwell B), its Android WSI and fence workaround, Zink being forced on Blackwell, the Rust requirement, NVK docs and release notes, no AHB in NVK, the linear render-target rule, and Mesa EGL picking one GPU on Android |
| `android17-graphics-loading.txt` | AOSP 17: one Vulkan HAL per process, the per-app updatable-driver settings and Settings UI, EGL load order, minigbm's first-render-node choice, drm_hwcomposer's card scan, ANGLE treating NVK as proprietary NVIDIA, and ANGLE's AHB gate for `EGL_ANDROID_image_native_buffer` |
| `linux-firmware-nvidia.txt` | WHENCE entries and licence line for GB20x, `LICENCE.nvidia` §2.1.2 with its sha256, file sizes |
| `omarchy-hybrid-gpu.txt` | Omarchy's supergfxd config (`hotplug_type: None`), the Integrated-mode switch, and the G14 resume hook |
| `fixture-tests.txt` | `scripts/dgpu-power-check-test.sh`: 9/9 under bash and 9/9 under AOSP mksh R59 with toybox |
| `fixture-try-auto.json` | A `--sample 10 --try auto` run on the "OpenBook today" fixture, showing the JSON shape with two states and battery samples |
| `devhost-rtx4090-run.json`, `.stderr` | A live run on the dev host (RTX 4090 with the nvidia driver): `WARN d0-driver`, as expected |
