# ANAL-191: without consent, OpenBook goes last in `BootOrder` (owner decision): evidence

Date: 2026-10-17. QEMU/KVM + OVMF and host tests on image files. **Nothing ran on the G14.** Design: `docs/installer.md` S11
and §12.11. This builds on #68 (`evidence/2026-10-17-installer-nvram/`).

**The decision** (owner on ANAL-159, 2026-10-17 ~21:35Z): with "Start OpenBook by default" off, add OpenBook's new
`Boot####` at the end of `BootOrder`. The system that starts now stays the default, and OpenBook appears in the firmware's
boot menu. With the box ticked, OpenBook goes first as before. Never overwrite or delete another entry; keep the read-backs.

## Inputs
- **Product:** `anybook_g14_x86_64-cp2a-userdebug` built from this branch at `1023ded` under the AOSP lane lock (incremental, `m exit 0`; `build/aosp-build.txt`). The test runs used one harness fix made after that build (below).
- **Image:** test image `openbook-live-20261017-anal191h` (`build/`). It is not for the owner: the next stick carries this.
- **Windows stand-in:** the Windows-like disk's `EFI/Microsoft/Boot/bootmgfw.efi` (and `EFI/BOOT/BOOTX64.EFI`) is now a 2.5 KB EFI application, `scripts/installer/efi-standin.c`, built with AOSP's prebuilt clang and lld. It prints `BootCurrent` and `BootOrder`, waits 3 s and returns to the firmware. OVMF then shows its boot menu.

## Results
| Run | Result | Files |
|---|---|---|
| Engine host tests (`engine-test.sh`) | **65/65** | `engine-host-tests/` |
| QEMU, `wizard-qemu.sh` run `nvram-b`: `dryrun`, `install`, `nvram-boot`, `alongside`, `alongside-default`, `alongside-boot` | **41/41** | `qemu/SUMMARY.md`, `qemu/results.json`, `qemu/<case>/` |

**Host tests** (a directory in efivarfs format stands in for the firmware):
- **Ticked** (whole disk): `Boot0002` → the new ESP, **first**: 0002, 0000, 0001; the other entries byte-identical.
- **Unticked** (alongside):
  - The firmware starts with `BootOrder` 0000 ("Windows Boot Manager"), 0001 (a stale reference to a deleted entry).
  - Result: `Boot0002` → the Windows ESP, **appended**: 0000, 0001, 0002.
  - `Boot0000` is byte-identical. Number 0001 is not reused, and no other variable appears.

**Whole disk** (`qemu/install/`, `qemu/nvram-boot/`): as in #68.
- The install made `Boot0005`, first in `BootOrder`.
- A copy of the disk with `EFI/BOOT/BOOTX64.EFI` deleted booted through it alone: `BootCurrent=0005`, `installed=whole`.

**Alongside, "Start OpenBook by default" off:**
- **The install** (`qemu/alongside/`).
  - Before: `Boot0007` "Windows Boot Manager", first.
  - After: one new `Boot0005` "OpenBook" → `HD(1, GPT, the Windows ESP)/\EFI\OpenBook\systemd-bootx64.efi`. **`BootOrder` 0007, 0002, 0003, 0000, 0001, 0004, 0005**, the old order plus OpenBook (`nvram-before.txt`, `nvram-after.txt`).
  - `Boot0007` has the same sha256 before and after.
  - Confirm says "OpenBook is added to this laptop's boot menu; Windows stays the default" (`screens/a5-confirm.png`). Done says "OpenBook is in this laptop's boot menu (Boot0005); Windows stays the default" (`screens/a7-done.png`).
- **The next start** (`qemu/alongside-default/`): the disk alone with the install's NVRAM, no stick, no QEMU `bootindex` hints.
  - **Windows starts by default:** the stand-in reports `BootCurrent=0007` (`firmware.txt`).
  - It returns, and **OVMF's boot menu lists "OpenBook" last** (`screens/fw-menu.png`, `firmware.txt`).
  - Up, then Enter (`screens/fw-menu-openbook.png`): **`BootCurrent=0005`**. Android boots from the Windows disk's new partitions: `installed=alongside`, 18 by-name links on `nvme0n1`, enforcing (`nvram-boot.txt`). `BootOrder` is unchanged by the boot.
- **`BootNext`** (`qemu/alongside-boot/`): the test then set `BootNext=0005` (`alongside-default/nvram-next.txt`). The next boot used it once (`BootCurrent=0005`, `BootNext` gone), and Windows is still first.
- **Before this change** (`screens/fw-menu-before.png`): #68's alongside disk and NVRAM (run `nvram-a`, OpenBook's `Boot0005` outside `BootOrder`), with the stand-in copied onto its ESP. The same menu has no OpenBook. This is the gap the decision closes.

**SELinux:** no denial for init, `openbook_installd` or the app in the enforcing `install` and `alongside` runs, and none for OpenBook's domains on the installed system (`*/avc.txt`). The other records are AOSP's or the test's, as in #68.

**Harness fix found on the way:** uiautomator wraps an attribute in single quotes when its text contains a double quote. Confirm's note quotes "Start OpenBook by default", so the helpers `bnd`/`bndx` now match both forms. The first `alongside` attempt timed out on that wait; a debug run showed the note on screen and in the dump (`text='OpenBook is added…'`).

## Not shown
- **The G14's AMI firmware:** whether its boot menu, like EDK2's, lists only `BootOrder`, and how it treats an appended entry (H). ANAL-192's spare-drive install will be the first real NVRAM write (`docs/installer.md` §13.7).
- **The live stick regression (`live-qemu.sh`) was not re-run:** this change touches only the engine, the app and the tests, not the stick's boot, init or policy. #68's 40/40 used the same `rc` and policy.
