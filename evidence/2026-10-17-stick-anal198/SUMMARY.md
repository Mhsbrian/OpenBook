# The owner's stick `openbook-live-20261017-anal198` (2026-10-17)

Built on the owner's request ("merge all and build new usb stick") after PR #64 merged. It replaces `openbook-live-20261017-anal192c`. Recipe: `docs/installer.md` §13.9, in one lane-lock hold. Everything below ran in QEMU/KVM + OVMF on image files, SELinux enforcing. Nothing has run on the G14 yet.

## What is on it
- **Built from `main` `2d90741`** (clean checkout, PRs #1–#64), product `anybook_g14_x86_64-cp2a-userdebug` (`image/openbook-live-20261017-anal198.build.json`). Compared with `anal192c` (`main` `3908b14`), it adds:
  - PR #61: Vulkan 1.4. Mesa was rebuilt non-strict, and the image declares `android.hardware.vulkan.version` 4210688 (1.4.0).
  - PR #64: kernel `6.18.21-android17-5-gfbfdd65b0fd1`, with the system DMA-BUF heap and efivarfs; Codec2 on the AIDL HAL, and its memfd policy; `stagefright`.
  - #60, #62, #63: docs and test tooling.
- **Add-ons** (`image/addons.log`):
  - the power check `openbook-powercheck-anal178-c`, unchanged;
  - the ARM apps check: `anal192c`'s add-on, whose builder is unchanged since #56;
  - **the graphics check `openbook-gfxcheck-anal198`**, new for ANAL-177's second run. It was built from this product's dEQP and ANGLE test modules. There is no second RADV in it, because the image already ships 1.4, so `vk14` skips itself.
- **sha256** `3b405d0875332306695ae87eae741d905e02a20c4202edd48d1173f3fd749c8b` (`image/openbook-live-20261017-anal198.sha256`), and `before-addons.sha256` for the copy without add-ons.

## Results
| Run | Result | Evidence |
|---|---|---|
| Live stick matrix (`live-qemu.sh`, two calls) | **40/40** | `live-qemu/` |
| Wizard (`wizard-qemu.sh`: dry run, install, installed, console) | **25/25** | `wizard-qemu/` |
| End-to-end matrix (`e2e-qemu.sh`) | **78/78** | `e2e-qemu/` |
| ARM apps check (`bridge-qemu.sh`, on the copy before the add-ons) | runs to the end; probe x86_64 18/0, arm64 18/2, the same known groups as `anal192c` | `addons-qemu/bridge.txt` |
| Power check (`power-check-qemu.sh vm`, `real`) | 14/14 and 10/10 expect steps | `addons-qemu/power-*.txt` |
| Graphics check (`gfx-qemu.sh`, 40 cases per list, SwiftShader) | every part exits 0; `vk14` skipped (image ships 1.4), `gles-mesa` skipped (no AMD GPU) | `addons-qemu/gfx.txt` |
| Media check on the same product (`g14-qemu.sh` + `expect-g14-media.json`) | `/dev/dma_heap/system` present, 0 heap errors, `stagefright` decodes `Atria.ogg` in full (1,190,700 bytes), efivarfs mounts | `media-check/` |
| `write-stick.sh --dry-run` to the owner's SanDisk Ultra (62 GB) | every check passes, image sha256 OK, nothing written | `image/write-stick-dry-run.log` (serial redacted) |

- **Why 78 rather than 79 checks.** The extra check, "the new ESP passes `fsck.fat`", only applies when cut 4 leaves a new table. This time the power cut landed while the disk was still blank. Both are allowed safe states (S9), and the timing differs from run to run.
