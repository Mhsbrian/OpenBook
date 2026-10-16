# Compatibility matrix

## Images on hosts and VMs

| Date | Image | Host / VM | Result | Evidence |
|---|---|---|---|---|
| 2026-10-15 | AOSP Desktop (Preview) 37.0 x86_64, `CLE1.260506.004` | Emulator 37.2.12, KVM, Ryzen 9 7950X, SwiftShader | **Boots** (16 s); freeform windows and taskbar work; arm64-v8a listed through libndk_translation | `evidence/2026-10-15-m0/m0-emulator/` |
| 2026-10-15 | Googlebook OS ruby `CL3B.260622.271.R1`, stock kernel and ramdisks | QEMU 11.1.2, KVM `-cpu host`, Ryzen 9 7950X (Zen 4) | **Partial:** first-stage mount OK, about 30 services start, 0 SIGILL; stalls at keystore2 (Trusty/pKVM, GSC) | `evidence/2026-10-15-m0/gbos-boot-zen4-kvm.log` |

## ARM-only APKs

Not started. This begins at M6, testing libhoudini, libndk_translation and Digitalis side by side.

| App | ABI | houdini | ndk_translation | Digitalis | Notes |
|---|---|---|---|---|---|

## Graphics drivers

| Date | Driver build | Host / VM | Result | Evidence |
|---|---|---|---|---|
| 2026-10-15 | Mesa 26.2.5 and AG 26.0.8 radeonsi + RADV, NDK r30, API 37 | AOSP Desktop emulator 37 (`CLE1.260506.004`), KVM, no GPU | **Loads:** Vulkan HAL `open(vk0)` and `vkCreateInstance(1.3)` OK, 0 devices; EGL loads, `eglInitialize` fails (no DRM device). Not tested on AMD hardware | `evidence/2026-10-15-mesa/smoke/` |
