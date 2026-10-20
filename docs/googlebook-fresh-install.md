# Googlebook fresh SSD installation (fresh28)

Prepared 2026-10-20 for the owner-requested fresh start on the G14's 1 TB NVMe.
This is a new option alongside configured-USB migration. It is **not** an update
of the currently installed laptop. No physical disk was accessed or written.

## Capacity: 8 GiB and the reported 16 GB

The migration source's userdata partition is exactly 8,589,934,592 bytes.
Copying that partition preserves its filesystem size. This does not mean the
owner's Settings reading of **16 GB** is wrong. Android's storage service can
report a rounded system-plus-data total instead of the data filesystem capacity.
In the diagnostic's Cuttlefish test, `StatFs` reports 8,587,837,440 data bytes
and `StorageStatsManager` reports **16,000,000,000 bytes** on that same device.

This reproduces the distinction without inspecting the absent laptop. The APK
records both values for the actual machine. The earlier statement equating the
owner's UI directly with an 8 GiB filesystem was too strong. Apps and user files
share `/data`; these are not two independent 8 GB and 16 GB pools.

## Choosing the new option

The new USB entry is **Fresh install Googlebook to SSD - ERASE SSD DATA**.
Live boot remains the default. The existing **keep saved data** entry remains
available and still copies the USB filesystem without expansion.

Fresh install runs offline with Android stopped. It shows each eligible internal
NVMe's model, serial, actual capacity and proposed Android data capacity. Select
the intended disk and type **FRESH ERASE followed by its exact serial number**.
The ordinary migration confirmation does not authorize fresh mode. This erases
the selected SSD's entire existing installation, accounts, files and apps.
It does not preserve the SSD's newer data or import the USB's saved setup.
Back up anything wanted before selecting this mode.

The source USB stays unchanged. A valid target GPT and firmware boot entry are
activated only after copied payloads and reset ranges read back successfully.
Remove the USB after power-off and complete Android setup again. First boot
creates fresh encrypted data storage and may take longer than subsequent boots.
Verify storage, restart, and test the required hardware before relying on it.
This is not a secure erase or an automatic recovery of the old SSD installation.

## Implementation

The reviewed input27 system (including the tap-drag correction) is retained.
Only the USB EFI partition gains installer files/menu entries; Android payloads
remain identical to input27. The fresh path in `migrate.py`:

- copies static system partitions, checks their hashes, and rebinds the unchanged
  initrd bodies to newly generated target partition GUIDs;
- extends the final userdata partition to the last whole MiB before the backup
  GPT, using actual disk capacity rather than the USB's size;
- zeros misc and metadata completely and clears both userdata edges; it never
  copies USB encryption keys or configured userdata;
- lets the shipped `formattable` fstab and vold create the filesystem and new
  metadata-encryption keys on first boot, through the encrypted mapping.

For a 1,000,000,000,000-byte fixture, fixed partitions occupy about 4.18 GB.
The userdata partition is 995,824,238,592 bytes. Filesystem metadata, reserved
space, system use and decimal/binary display units reduce the usable figure.
No arbitrary large unallocated tail or future A/B reservation is introduced.
This layout remains single-slot; automatic OTA safety is separate work.

Physical protections from migration remain: source pin and full hash, exact
serial confirmation, same-model check, whole internal NVMe only, unmounted/no
holders/no swap, 512-byte sectors, exclusive descriptors, power recheck, independent
readback and GPT publication last. Firmware registration failure is reported
separately from verified copying.

## Build and tests

Use `googlebook-migration.md`'s pin/build/add recipe, with reviewed input27 as the
base and new empty output directories. `migration-package.py add` now adds both
installer modes. It still refuses replacement of existing installer files.
Updating the already configured physical USB requires a fresh backup and a
reviewed preserving preparation; writing this fresh image wholesale would reset
the USB's setup.

```sh
scripts/installer/inst-docker.sh python3 "$PWD/scripts/googlebook/migration-test.py"
scripts/installer/inst-docker.sh python3 "$PWD/scripts/googlebook/migration-qemu.py" \
  --source "$FRESH28_IMAGE" --fresh --target-bytes 1000000000000 \
  --android-qemu "$RUBY_QEMU" --out "$NEW_VM_RUN" --seconds 480
# Wrong confirmation and normal framebuffer/keyboard cancellation:
# repeat in separate new directories with --fresh --cancel or --fresh --console-smoke
scripts/installer/inst-docker.sh python3 "$PWD/scripts/googlebook/fresh-reboot-qemu.py" \
  --first-run "$NEW_VM_RUN" --out "$NEW_REBOOT_RUN" --seconds 300
```

The 15 unit tests include reset of pre-existing target contents, untouched source
and static payloads, 1 TB GPT placement/full data extent, distinct confirmation,
and the existing migration/integrity/power/interruption checks.
The actual installer UI is exercised against synthetic USB/NVMe/decoy files.
The VM f2fs checker observes 949,692 MiB, matching the enlarged data partition.
Physical boot and available-space acceptance remain separate.

The normal second boot, without the USB, reaches graphical Android setup and
retains all four metadata-encryption files. Its raw serial-only result says
`boot_completed=false`: boot-control selected the existing `openbook-a.conf`
normal entry, which intentionally disables serial logging. The screenshot and
EFI contents refute the initial hypothesis of a missing boot entry. No production
boot-entry change is shipped. A proposed change based on that hypothesis failed
its source-pin guard before target writes and was discarded.

The corrected reboot harness copies the fixture and maps that **existing**
default entry to its existing serial diagnostic variant solely for observation.
It retains the selected entry name, TPM state and all Android partition bytes,
removes the USB, checks encrypted key retention and rechecks the original sparse
image's data ranges afterward. The 300-second instrumented restart passes boot,
key-retention, identity and source-integrity checks, with no system-server fatal
signal observed in that window. This instrumentation is not part of fresh28.

Evidence and final boot outcomes are in `evidence/2026-10-20-googlebook-fresh28`.
Private artifacts contain locally licensed Google payloads and are not distributed.
The open-source installer and APK sources are in this repository.

## Primary sources checked 2026-10-20

- [StorageStatsService](https://android.googlesource.com/platform/frameworks/base/+/b5c6c45f5243c6f08ee3e21bf8a3a0aed4941fd6/services/usage/java/com/android/server/usage/StorageStatsService.java),
  [StorageManager](https://android.googlesource.com/platform/frameworks/base/+/b5c6c45f5243c6f08ee3e21bf8a3a0aed4941fd6/core/java/android/os/storage/StorageManager.java)
  and [FileUtils](https://android.googlesource.com/platform/frameworks/base/+/b5c6c45f5243c6f08ee3e21bf8a3a0aed4941fd6/core/java/android/os/FileUtils.java):
  reported capacity and rounding, verified against local checked-out source.
- [Metadata encryption](https://source.android.com/docs/security/features/encryption/metadata):
  filesystem formatting through vold's encrypted mapping.
- Local `system/fs/fs_mgr/fs_mgr.cpp` and `system/core/libcutils/partition_utils.cpp`:
  the formattable path recognizes a zeroed first 4 KiB; local Ruby fstab requests
  F2FS with metadata encryption and fscrypt. No generic ciphertext resize is used.
