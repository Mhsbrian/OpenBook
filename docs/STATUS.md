# Status

## 2026-10-15: M0 (research, dev host, baselines)

**Done**
- Researched Googlebook OS and prior art. Findings are in `docs/RESEARCH.md`, and the two-track plan with ranked blockers is in `docs/PLAN.md`.
- Downloaded Google's official recovery image for ruby (Lenovo Googlebook 15, Intel), build `16452207_CL3B.260622.271.R1`. The zip md5 `0567fe2ed0dd1c1753b383a6b3dbfe81` matches Google's manifest. The image is stored locally and never committed.
- Unpacked it without root: GPT, `super`, EROFS partitions, boot/init_boot/vendor_boot, ramdisks, and the kernel config.
- ISA scan: of 2,675 x86-64 ELF files, 79 contain instructions Zen 4 doesn't implement. 65 of those use AVX-VNNI, including `init`, `linker64`, `surfaceflinger` and `libhwui`.
- **Execution test:** booted Google's stock kernel and ramdisks in QEMU/KVM with `-cpu host` on a Ryzen 9 7950X (Zen 4):
  - First-stage mount works: dm-linear `super`, dm-verity using Google's hashtree, AVB in orange state.
  - Second-stage init starts about 30 services.
  - **0 SIGILL or invalid-opcode traps.**
  - Boot stalls at `keystore2` because KeyMint lives in the Trusty pKVM security VM and there is no GSC TPM. Zygote and the UI never start.
- Booted Google's AOSP Desktop (Preview) Android 17 emulator image headless under KVM:
  - `boot_completed` after 16 s.
  - The desktop taskbar is up and Settings and Files open in freeform windows.
  - `feature:android.hardware.type.pc` is present, and the native bridge is libndk_translation with `arm64-v8a` listed.

**Evidence** (in `evidence/2026-10-15-m0/`)
- `m0-emulator/screen-desktop.png`, `m0-emulator/screen-windows.png`, `props.txt`, `boot-result.txt`, `logcat.txt.gz`, `dmesg.txt.gz`
- `gbos-boot-zen4-kvm.log`: full serial log of the Googlebook kernel and init on Zen 4
- `isa-scan-ruby.json`: per-binary counts of instructions Zen 4 doesn't implement
- `gbos-kernel-config.txt`: the stock Googlebook GKI config

**Blocked / needs a decision**
- Target hardware: which AMD laptop (exact SKU)? The dev host is a Ryzen 9 7950X desktop with a Radeon 610M iGPU and an RTX 4090.
- Which repo receives this work. No AnyBook repo exists yet.
- Track B licensing: whether to proceed past research with Google's proprietary image (`docs/PLAN.md` §6).

**Next**
- M1a: software KeyMint/Gatekeeper/Weaver vendor overlay (GBRUNCH method), then boot Googlebook OS in QEMU/KVM to `boot_completed`.
- M1b: mirror and sync `android17-release`, then build `aosp_cf_x86_64_pc` and boot it in the Cuttlefish container.
