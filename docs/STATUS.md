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
- Target hardware: **ASUS ROG Zephyrus G14 (2025)**, expected to be the GA403WP (Ryzen AI 9 HX 370 + RTX 5070). The exact SKU still needs `scripts/hw-inventory.sh` output from the laptop (ANAL-175). See `docs/HARDWARE.md`.
- ~~Merge PR #1.~~ Merged 2026-10-16.
- ~~Which repo receives this work.~~ Resolved: https://github.com/Mhsbrian/AnyBook (public, created 2026-10-15).
- License for the scripts and docs. Apache-2.0 is suggested, to match AOSP. Not chosen yet.
- Track B licensing: whether to proceed past research with Google's proprietary image (`docs/PLAN.md` §6).

**Next** (tracked in Multica as children of ANAL-159; ▶ marks issues running now)

| Epic | Stage 1 | Later stages |
|---|---|---|
| ANAL-160 Track A: AOSP 17 desktop boots in a VM | ▶ ANAL-167 build container and source mirror | ANAL-168 build `aosp_cf_x86_64_pc` and boot to adb → ANAL-169 VM graphics and desktop windowing |
| ANAL-161 AMD GKI kernel (android17-6.18) | ▶ ANAL-170 reproduce the stock GKI build and diff the config | ANAL-171 AMD config and modules → ANAL-172 QEMU boot test |
| ANAL-162 AMD graphics userspace | ▶ ANAL-173 Mesa radeonsi/RADV Android build | ANAL-174 device-tree integration → ANAL-177 dEQP/CTS on the target |
| ANAL-164 ARM compat and native bridge | ▶ ANAL-180 harness and libndk_translation baseline | ANAL-181 Digitalis evaluation |
| ANAL-163 Bare-metal bring-up on the G14 2025 (waiting for inventory output from the laptop) | ANAL-175 inventory | ANAL-176 USB boot → ANAL-178 input and power, ANAL-179 audio and Wi-Fi |
| ANAL-165 Track B: Googlebook OS on AMD (parked: licensing decision) | ANAL-182 VM boot to `boot_completed`, ANAL-183 Zen 4 ISA spike | ANAL-184 kernel swap → ANAL-185 graphics overlay |
| ANAL-166 Performance and parity (parked) | — | — |
