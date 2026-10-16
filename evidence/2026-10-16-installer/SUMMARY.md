# Evidence: installer boot-chain prototype (ANAL-189), 2026-10-16

The design and recommendation are in `docs/installer.md`. The results below come from run `matrix-20261016-openbook`, made with the OpenBook-named scripts. The earlier run under the old AnyBook names is in git history (PR #22).

**What ran.** One GPT "USB stick" image per EFI loader, all built from the same inputs, each booted in QEMU 11.1.2 / KVM with edk2-ovmf 202608:
- The image is attached as `usb-storage` on xHCI.
- Some runs add a decoy NVMe disk that carries the same Android partition names with random PARTUUIDs, standing in for an installed internal disk.
- Image files only. No host disk, USB stick or firmware was touched.

**Inputs.**
- The `anybook_cf_x86_64_pc-cp2a-userdebug` images (ANAL-169), reflink-snapshotted read-only. Fingerprints are in `matrix/input-provenance.txt`.
- The OpenBook GKI `6.18.21-android17-5-g44a90255c95f` (ANAL-171), `bzImage` sha256 `6d964789…`.
- The AOSP test key.
- GBL dev EFI from ci.android.com build 16633196. Hashes are in `tools.txt`; the binary is not redistributed here.

**Scripts:** `scripts/installer/` (`mkproto.py`, `qemu-run.py`, `probe-init.c`, `proto-matrix.sh`, `proto-summary.py`).

## Results (`matrix/SUMMARY.md`, `matrix/results.json`)

| Variant | Outcome |
|---|---|
| `grub` + decoy NVMe | GRUB 2.16 passes the vendor ramdisk, generic ramdisk and bootconfig. `boot_part_uuid` is probed at run time. Android finds the boot device on USB (`pci0000:00/0000:00:02.0/usb2/…`), mounts `super` with dm-verity, and formats `/metadata` (ext4) and `/data` (f2fs, 3.4 GiB). The console dump shows `ro.boot.*` from the loader. |
| `grub-2nd-boot` | The same stick boots again; no reformat, so the live data persists. |
| `grub-bad-digest` | `libfs_avb: vbmeta digest mismatch` / `Failed to verify vbmeta digest`; boot continues in orange. |
| `grub-slot-b` | The loader passes `androidboot.slot_suffix=_b` and `BOOT_IMAGE=(hd0,gpt1)/openbook/b/kernel` (probe only). |
| `sdboot` + decoy NVMe | systemd-boot 262 type #1 entry, bootconfig last, menu hidden: same Android result as GRUB, console 17 s after power-on. The screen keeps the firmware logo from power-on to Android's init (`matrix/sdboot/shot-{1,3,5,8,12}.png`). Boot counting renamed `openbook-a+3.conf` to `openbook-a+2-1.conf` (`matrix/sdboot/esp-entries-after.txt`). |
| `sdboot-menu` | The same loader with the menu shown (what a key held at power-on brings up): "OpenBook (17 · slot A)", "OpenBook (17 · slot B)", "Reboot Into Firmware Interface" (`matrix/sdboot-menu/shot-3.png`). |
| `uki` | `'bootconfig' found on command line, but no bootconfig found`. systemd-stub appends its own cpio archives after `.initrd`, so a UKI cannot carry Android bootconfig. |
| `gbl` | GBL does libavb in orange and writes its own bootconfig, but passes no `boot_part_uuid` or `boot_devices`: `Failed to create devices required for first stage mount`. |
| `gbl-uuid` | With `boot_part_uuid` baked into `vendor_boot`, GBL boots to the Android console from USB. Always slot `a` (no BootControl protocol). |
| `gbl-uuid-decoy` | `Failed to read bootloader message from misc partition: NotUnique`, then a panic and reset (`matrix/gbl-uuid-decoy/shot-20.png`). |

**Screenshots.**
- `matrix/grub/shot-2.png`: GRUB menu.
- `matrix/sdboot-menu/shot-3.png`: the systemd-boot menu.
- The installer design renders are in `docs/installer-design/png/`.

## Test stick for the G14 (`hwcheck-stick/`)
`openbook-hwcheck-20261016.img` (sha256 in `openbook-hwcheck-20261016.sha256`, layout in `.img.json`), built by `scripts/installer/make-hwcheck-stick.sh`, and tested in QEMU on that exact file:
- **"OpenBook hardware check":** 236 modules loaded, 0 failed, 29 skipped (safety list, blocklist, tests). The report and kernel log were written to the stick's ESP and the VM powered off after 23 s. The decoy NVMe was untouched. Files: `qemu-hwcheck-001.txt`, `qemu-hwcheck-001-dmesg.txt.gz`, `qemu-check-serial.log.gz`.
- **"OpenBook preview":** selected through the menu over the serial console; Android console reached, orange state, `/data` created on first boot (`qemu-vm-serial.log.gz`).
- `menu.png` is the boot menu.

## Not shown here
- This is plain QEMU booting the Cuttlefish `pc` product. There's no GPU, so we stop at the userdebug serial console, and `sys.boot_completed` was not checked.
- Cuttlefish's 6.12 `system_dlkm`/`vendor_dlkm` modules don't load on our kernel. That's expected and unrelated to the loader.
- Nothing ran on the G14.
- GBL's console output failed through a QEMU socket serial backend, and GBL then panicked inside its own error printer. With a FIFO or file backend it works, so the runner uses FIFOs.

## Files
- `matrix/<variant>/serial.log.gz`: the full serial console (ANSI codes stripped).
- `matrix/<variant>/result.json`: runner outcome and step timings.
- `matrix/<variant>/image.json`: GPT layout, PARTUUIDs, vbmeta digest and size, sha256 of every partition written.
- `matrix/matrix.log`: run order.
- `tools.txt`: tool versions and GBL hashes.
