# ANAL-191 follow-up: firmware boot entries through efivarfs — evidence

Date: 2026-10-17. QEMU/KVM + OVMF and host tests on image files. **Nothing ran on the G14.** Design and details:
`docs/installer.md` §12.11. This builds on ANAL-198's #64 (`efivarfs.ko` in `vendor_dlkm`).

## Inputs
- **Product:** `anybook_g14_x86_64-cp2a-userdebug` built from this branch (`build/aosp-build.txt`, incremental). It includes the kernel dist with `efivarfs.ko` (`6.18.21-android17-5-gfbfdd65b0fd1`), staged by ANAL-198.
- **Image:** test image `openbook-live-20261017-anal191g` (`build/`). It is not for the owner: the next stick carries this.
- **Policy as built:** `policy/system_ext_sepolicy-efivarfs.cil.txt`. Mount: `policy/openbook-installd.rc`.

## Results
| Run | Result | Files |
|---|---|---|
| Engine host tests (`engine-test.sh`), with a directory in efivarfs format as the firmware | **63/63** (10 new NVRAM checks) | `engine-host-tests/` |
| QEMU, `wizard-qemu.sh` run `nvram-a`: `dryrun`, `install`, `nvram-boot`, `alongside`, `alongside-boot` | **33/33** | `qemu/SUMMARY.md`, `qemu/results.json`, `qemu/<case>/` |
| Live stick regression (`live-qemu.sh`; init now mounts efivarfs on live boots) | **40/40** | `qemu/live-matrix-SUMMARY.md` |

**Whole disk** (`qemu/install/`, `qemu/nvram-boot/`):
- **The install.** The wizard, fresh OVMF NVRAM, enforcing. The daemon created `Boot0005 "OpenBook"` → `HD(1, GPT, 4d3c50e8-…)/\EFI\OpenBook\systemd-bootx64.efi` and put it first: `BootOrder` 0005, 0002, 0003, 0000, 0001, 0004 (`install/nvram-after.txt`, `installd-log.txt`).
  - efivarfs is mounted by init and labeled `openbook_efivarfs` (`install/labels.txt`).
- **The boot through that entry alone.** A copy of the installed disk with `EFI/BOOT/BOOTX64.EFI` deleted (`nvram-boot/esp-EFI-listing.txt`), that NVRAM, no stick, and no `bootindex` hints, so OVMF follows the NVRAM's `BootOrder` alone.
  - **`BootCurrent=0005`**, and Android booted from the NVMe disk: 14 by-name links on `nvme0n1`, `installed=whole`, enforcing (`nvram-boot/nvram-boot.txt`).

**Alongside** (`qemu/alongside/`, `qemu/alongside-boot/`):
- **Before.** A Windows-like disk (ESP with a fake `bootmgfw.efi`, MSR, NTFS, recovery, about 106 GB free). The firmware got `Boot0007 "Windows Boot Manager"` → `HD(1, GPT, its ESP)`, first in `BootOrder` (`alongside/nvram-before.txt`).
- **The install.** The wizard installs alongside with "Start OpenBook by default" off. The Confirm screen warns that the boot order stays (`screens/a5-confirm.png`), and Done says the other system still starts first (`screens/a7-done.png`).
  - Afterwards there is one new `Boot0005 "OpenBook"` → `HD(1, GPT, the Windows ESP)/\EFI\OpenBook\systemd-bootx64.efi`.
  - **`Boot0007` and `BootOrder` have the same sha256 before and after** (`alongside/nvram-after.txt`).
- **The boot.** The test then set `BootNext=0005`, standing in for the firmware's boot menu (`alongside/nvram-next.txt`). The disk alone, with that NVRAM and no `bootindex` hints:
  - **`BootCurrent=0005`**, `BootNext` used up, `Boot0007` still first;
  - Android booted from the Windows disk's new partitions with `installed=alongside` (`alongside-boot/nvram-boot.txt`).

**SELinux:** no denial for init, `openbook_installd` or the app in the enforcing `install` and `alongside` runs (`*/avc.txt`). The other records there are AOSP's or the test's: audioserver and an app's memfd (ANAL-179's open item), keystore and gatekeeper, MediaProvider and `/data/local/tmp`, SystemUI and `bluetooth_lea_prop`.

## Not shown
- **The G14's AMI firmware.** Whether its boot menu lists entries outside `BootOrder` is not known (H). ANAL-192's spare-drive install will be the first real NVRAM write.
- **Without consent, the alongside entry is not in `BootOrder`.** EDK2's boot menu lists only `BootOrder`, which is why the test used `BootNext`. Whether to append OpenBook at the end of `BootOrder` instead is the owner's decision (`docs/installer.md` §12.11).
- **Installed systems don't mount efivarfs**, so there are no entry updates after the install; that is `openbook-bootsync`'s job, not built yet.
