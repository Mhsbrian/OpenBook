# OpenBook

OpenBook brings the Googlebook experience (Googlebook OS, Android 17 desktop) to x86_64 hardware Google doesn't ship. AMD Ryzen comes first, then other Intel parts, and NVIDIA later.

- `docs/PLAN.md`: the two-track plan, ranked blockers and milestones. Start here.
- `docs/RESEARCH.md`: verified facts, prior art and native-bridge licensing, with sources.
- `docs/STATUS.md`: Done / Evidence / Blocked / Next.
- `docs/BUILD.md`: reproducible steps. No host sudo needed; Docker and KVM required.
- `docs/HARDWARE.md`: the target laptop (ASUS ROG Zephyrus G14 GA403WR), its driver map and how to run the inventory script. `docs/COMPAT-MATRIX.md`: ARM-only app results.
- Topic docs:
  - **Android build:** `docs/aosp-build.md` (AOSP 17 build and Cuttlefish boot) and `docs/aosp-desktop.md` (desktop windowing and VM graphics).
  - **Kernel and graphics:** `docs/kernel.md` (GKI and AMD vendor modules), `docs/mesa.md` (Mesa for Android), `docs/graphics-amd.md` (AMD graphics in the device tree) and `docs/nvidia.md` (the NVIDIA dGPU).
  - **ARM apps:** `docs/compat-harness.md` (ARM compatibility harness) and `docs/digitalis.md` (Digitalis native bridge).
  - **Installer:** `docs/installer.md` (USB installer design) and `docs/installer-wireframes.html`.
- `device/anybook/`: the OpenBook AOSP device tree: the reusable desktop configuration, AMD graphics and the `anybook_cf_x86_64_pc` Cuttlefish product.
- `kernel/`: the kernel patches, the vendor-module build (`kernel/devices/anybook`) and the linux-firmware subset rules. `aosp/patches/`: patches to AOSP projects. `manifests/`: pinned repo manifests.
- `scripts/`: build, boot, test and inventory tools (AOSP, kernel, Mesa, compatibility, installer prototype, `hw-inventory.sh`). `tools/` holds the toolbox Dockerfiles.
- `evidence/`: logs and screenshots for each milestone.

No Google proprietary images, blobs or GMS go in this repo. Scripts work on images that each user downloads themselves.

## Name

The project was called AnyBook until 2026-10-16. It is now OpenBook, at https://github.com/Mhsbrian/OpenBook; the old `Mhsbrian/AnyBook` URL redirects.

Code and build identifiers still use the old name, and the docs quote them as they are:
- **AOSP:** `device/anybook/`, the `anybook_cf_x86_64_pc` product, the `AnyBookDesktop*Overlay` modules, and `PRODUCT_BRAND`/`PRODUCT_MODEL`.
- **Kernel:** `//devices/anybook`, the `anybook_amd` KMI symbol list, and the `ANYBOOK:` patch subjects.
- **Build host:** the `anybook-*` Docker images, `ANYBOOK_HOME` and `~/anybook/`.
- **Tools:** the `anybook-hw-*` inventory archives, the `AnyBookProbe` logcat tag, and the installer prototype's GRUB entry and `os-release` name.

Renaming those changes build outputs (kernel and AOSP commit IDs, the product name), so it is a separate step. `evidence/` keeps the old name because it records what ran at the time.
