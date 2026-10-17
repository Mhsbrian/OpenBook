# ANAL-198 follow-up evidence: system DMA-BUF heap, efivarfs, GPU reset (2026-10-17)

Kernel `6.18.21-android17-5-gfbfdd65b0fd1`: the PR #26 tree plus `system_heap.ko`, `efivarfs.ko` and 26 more `anybook_amd` KMI symbols. The GKI `.config` is unchanged. Everything ran on the Ryzen 9 7950X host in QEMU/KVM; nothing ran on the laptop. Details: `docs/kernel.md`, "Follow-up (2026-10-17)".

## Kernel packaging (`scripts/kernel-g14-package.sh --evidence ...`): PASS

| File | What it shows |
|---|---|
| `images.md`, `images.json` | New images with sha256: `vendor_dlkm.img` `02477437…` (140 modules), `system_dlkm.img` `34185c35…`, `bzImage` `55b86074…`, `vendor_boot.img` `5ff49fd3…` |
| `modlists.md` | 0 problems. The vendor module set now comes from `_ANYBOOK_AMD_MODULES` in `BUILD.bazel` |
| `sigcheck.md` | 100/100 `system_dlkm` modules are signed by the new build key (serial `2041784F…`), which is built into `vmlinux`; 140 vendor modules are unsigned |
| `qemu/` | 5/5 first-stage runs with the Cuttlefish userspace, as in PR #26. New checks: `/dev/dma_heap/system` is present and efivarfs is registered (`qemu/*.dma_heap.txt`) |
| `kmi/kmi-pr26-vs-r2.txt` | Against PR #26's GKI: +21 exports, 0 CRCs changed, 0 removed; every KMI symbol is intact |
| `kmi/kmi-stock-vs-r2.txt` | Against Google's 16302624: 0 CRCs changed, 0 removed; all 4,038 stock KMI symbols are intact |
| `kmi/efivarfs-trial-modpost.txt` | The trial build without the list update: modpost could not resolve 10 symbols |
| `kmi/efivarfs-new-kmi-symbols.txt` | The 26 symbols efivarfs needs that were not on the KMI |
| `firmware/` | Unchanged: 137 files |

## G14 product in QEMU/OVMF (`scripts/g14-qemu.sh`, `product-qemu/expect-g14-media.json`)

All runs use the `anybook_g14_x86_64` userdebug product from `main` plus this PR, booted from a USB disk image. `image-provenance.txt` in each run names the staged kernel.

| Run | Kernel | Userspace fixes | `/dev/dma_heap/system` | Heap errors | `stagefright` on `Atria.ogg` |
|---|---|---|---|---|---|
| `before` | PR #26 | none | missing | 56 | crash: "No matching decoder! (audio/vorbis)" (Codec2 sees only `__ApexCodecs__`) |
| `after` | new | none | present | 0 | the same crash: the heap alone is not enough |
| `before-full` | PR #26 | Codec2 AIDL + memfd policy | missing | 64 | `source->start()` = -12 (ENOMEM) |
| **`after-full`** | **new** | **Codec2 AIDL + memfd policy** | **present** | **0** | **exit 0, 1,190,700 PCM bytes (13.5 s)** |

- **`efivars.txt`** (`after-full`; `after` has the enforcing part only):
  - `mount -t efivarfs` works and lists 37 variables, including `Boot0000`–`Boot0003`. `BootOrder` reads correctly.
  - Writing under enforcing is denied: efivarfs is `unlabeled`, so `associate` is denied.
  - Writing with SELinux permissive works: create, read back, `chattr -i`, delete.
- **`regress/`:** the product's standard `expect-g14.json` boot on the final image completes all steps. It shows 5 denials:
  - 4 are known from ANAL-192's runs (Gatekeeper, SystemUI's `bluetooth_lea_prop`, the shell).
  - 1 is new and appears only now that decoding works: `audioserver` cannot map SystemUI's SoundPool memfd (`appdomain_tmpfs`). That is left to the audio lane (`docs/kernel.md`).
- **Per run:** `logcat.txt.gz` and `dmesg.txt.gz`; full serial logs for the `-full` runs.
