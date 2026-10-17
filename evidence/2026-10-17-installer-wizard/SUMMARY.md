# ANAL-191: installer wizard, install engine and first-boot setup — evidence

Date: 2026-10-17. Everything here ran in QEMU/KVM + OVMF or on the host against image files. **Nothing ran on the G14**
(owner checklist: `docs/installer.md` §12.8). Design and details: `docs/installer.md` §12.

## Inputs
- Product `anybook_g14_x86_64-cp2a-userdebug` built from this branch (AOSP test keys), the last incremental build in
  `build/aosp-build.txt` (1 min 42 s, memory peak 48 GB).
- Live image `openbook-live-20261017-anal191e` (`build/*.build.json`, `build/*.sha256`, `build/image-layout.json`),
  test build with the boot menu shown for 10 s.
- QEMU: q35/KVM, OVMF, the image copied to a 16 GiB USB stick (xHCI), a blank 64 GiB virtual NVMe disk, virtio-vga at
  **2880×1800 with density 240** (the G14's panel and scaling), USB keyboard and tablet, TPM 2.0, 8 GiB, 8 vCPUs.
  The stick boots a test copy of its VM entry (serial console) at density 240; **SELinux enforcing**.

## Results
| Run | Result | Files |
|---|---|---|
| Engine host tests | **53/53** | `engine-host-tests/SUMMARY.md`, `results.json`; the whole-disk install's plan, events, report and `lpdump` in `engine-host-tests/{plan,whole,alongside}/` |
| QEMU: `dryrun` | 10/10 | `qemu/dryrun/`: `cli-disks.txt` and `cli-plan.txt` (the CLI dry run), `installd-log.txt` (the app's dry run through the daemon), `labels.txt`, `avc.txt` |
| QEMU: `install` | 5/5 | `qemu/install/`: `installd-log.txt`, `app-log.txt`, `avc.txt`, `nvme-gpt.txt` |
| QEMU: `installed` | 1/1 | the installed disk alone, no stick, fresh NVRAM: `screens/installed-boot-{10,30}s-qemu.png` |
| QEMU: `console` | 9/9 | a copy of the installed disk with a serial-console entry: `qemu/console/installed.txt`, `installer-state.txt`, `after-setup.txt`, `avc.txt` |
| QEMU total | **25/25** | `qemu/SUMMARY.md`, `qemu/results.json` |
| Live-stick regression (`live-qemu.sh`) | **39/39** | `qemu/live-matrix-SUMMARY.md`, `live-matrix-results.json` |

**Key facts**
- **Dry run (S5):** the app's "View the plan" and `openbook-install plan` both went through, and the 64 GiB NVMe file
  had **0 allocated blocks** afterwards.
- **Install:** 20.2 s in QEMU (check the stick 6.5 s, `super` 7.4 s, read-back 5.6 s); 33 items verified by sha256;
  report and log on the stick and on the new ESP (`install-report/`).
- **Boot from the installed disk:** without the stick, OVMF boots it through `EFI/BOOT/BOOTX64.EFI` (no efivarfs, no
  NVRAM entry: `build/decision6-kernel-config.txt`). `boot_completed` at 10 s; all 14 by-name links on `nvme0n1`;
  `ro.boot.openbook.installed=whole`; no live flags; enforcing.
- **First screen of the installed system: OpenBook setup** (`screens/8-setup-*.png`), then the launcher
  (`9-desktop.png`); afterwards `device_provisioned=1`, `user_setup_complete=1`, setup turned off.
- **SELinux:** no denial for `openbook_installd` or the app in the dry-run and install boots. The installed system
  logs denials only from other components (SystemUI `bluetooth_lea_prop`, keystore → gatekeeper, and MediaProvider
  searching `/data/local/tmp`, where this test writes its screenshots and UI dumps).

## Screens (`screens/`, Android's own `screencap`, scaled to 1440×900; `1-welcome-2880x1800.png` is full size)
1. `1-welcome.png`: language, keyboard, accessibility
2. `2-hardware.png`: the VM's real hardware: no Wi-Fi, speakers or touchpad, software rendering, so the verdict is
   "with a few limits"
3. `3-choose.png`, `3-choose-install.png`
4. `4-disk.png`, `4-disk-selected.png` (the stick locked), `4-plan.png` (the dry run)
5. `5-confirm.png`, `5-confirm-typed.png`: the model name typed, the red button enabled
6. `6-install-progress.png`, `6-install-details.png`
7. `7-done.png`
8. `8-setup-language.png`, `8-setup-wifi.png`, `8-setup-lock.png`, `9-desktop.png`: the installed system

**QEMU's display swaps red and blue** (`qemu-display-channel-swap-example.png`: the wizard's blue `#4355B9` shows as
`#B95543`). Android's `screencap` of the same moment is correct, so the screenshots above are `screencap`s. The two
`installed-boot-*` frames could only be taken through QEMU (no shell on that entry); their channels were swapped back
for this folder. The swap is in the VM display path (the virtio-gpu software fallback), not in the app.

## Not shown here
- the G14 (USB 3 speeds, the 890M, the real NVMe, a laptop battery);
- an alongside install booted in QEMU (host tests only);
- a firmware boot entry (efivarfs);
- `openbook-bootsync` and the text hardware report.
