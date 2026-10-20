# Move a configured Googlebook USB to the same G14

**Later option, 2026-10-20:** `googlebook-fresh-install.md` documents fresh28's
separate **Fresh install - ERASE SSD DATA** entry, which uses the remaining SSD
capacity and starts setup over. The preserving migration described here keeps
the source filesystem size. The owner's 16 GB Settings reading is compatible
with its 8 GiB data partition and Android's rounded reported total.

This is an offline migration of the existing camera25 system and its saved
state. It is separate from the AOSP wizard's fresh-install writer. The generic
Googlebook recovery card remains gated: it must not feed a Ruby image into the
AOSP layout/formatting path.

The owner reports working webcam and Bluetooth after camera25. That report
does not establish microphone, suspend, privacy-switch behavior, stability or
future-update compatibility.

## User flow

The added boot-menu entry is **Install this Googlebook USB to SSD - keep saved
data**. Live boot remains the default. The entry starts a small Linux environment
entirely in RAM, with Android stopped and its data unmounted. It does not connect
to a network or start an automounter.

The installer identifies the pinned source USB and lists eligible internal
NVMe disks with model, capacity and serial. It excludes the source, partitions,
mounted disks, disks with active holders/swap, read-only targets and unsupported
sector geometry. The G14 model check is a compatibility guard, not proof that
another machine's TPM or credentials would work.

Connect the laptop's charger. The installer checks known system batteries
before selection and immediately before writing; low or unreadable charge
without external power stops the operation. Select the target, review its
identity and type **ERASE followed by its exact serial number**.
This replaces **all partitions on that SSD**, including any
existing OpenBook or other OS. Back up that SSD's contents first. It is not a
secure erase. Cancellation or an incorrect phrase writes nothing.

The source USB is retained unchanged. After copying and verification, the
installer adds an **OpenBook Googlebook** firmware boot entry. If firmware
registration fails, it reports that separately; the verified target can be
selected through `EFI\BOOT\BOOTX64.EFI` in firmware. Power off, remove the USB
and boot the SSD. Verify the existing PIN/unlock, apps, accounts, files and
hardware before treating migration as accepted. Keep the USB as recovery.

The initial migration retains the exact **8 GiB encrypted userdata extent**.
The remaining SSD space is unallocated. Enlarging a partition is not equivalent
to growing the encrypted F2FS filesystem; no formatting or untested resize is
performed. This is a single-slot system, without automatic A/B rollback.

## What is preserved and changed

`migrate.py` validates both source GPT copies and their CRCs, the expected
partition layout/identity, all pinned static system partitions, and the kernel,
initrds and boot entries. The pin comes from a reviewed build, not a manifest
supplied by an arbitrary USB.

Userdata may continue changing during normal live use. After a system update,
regenerate the source pin and installer for the newly reviewed build; the old
installer deliberately refuses changed static system or boot payloads. The
default `add` command is addition-only and requires existing EFI files unchanged;
replacement of an existing installer requires an independently retained digest
of its old `ruby-installer/build.json`. The new
`--replace-installer-sha256` packaging operation validates the exact old files
and menus before replacing them in a private clone. See
`googlebook-update-prototype.md`; no physical write is implied.

Metadata, userdata, misc, boot, init_boot, vendor_boot, vbmeta and super are
copied byte-for-byte. Serial identity, kernel, initrd bodies, security services,
encryption policy, SELinux enforcement and verity stay as in the tested source.
Copying only userdata would omit the KeyMint-wrapped metadata-encryption key.

The target gets new disk and partition GUIDs and a valid backup GPT at the
physical end of the SSD. Each Android initrd is rebound to the target ESP's
PARTUUID, so an attached source USB with the same partition names cannot supply
the installed system's partitions. The EFI manifest is marked as an installed
Ruby migration, and installer menu entries are removed from the target. Other
EFI files, including existing logs, are retained.

Before the first write, the installer verifies the full source hash and
prepares/checks the new EFI files in RAM. Physical descriptors are opened
exclusively; source access is read-only. The target's old GPT is invalidated
before copying. Every copied partition is flushed and independently read back;
block-device reads follow `BLKFLSBUF` cache invalidation. Only after all payloads
verify and the source rehash matches are the backup and primary target GPTs
activated and checked. A failed/interrupted install retains the original USB;
it does not promise automatic restoration of the previous SSD contents.

## Build and package locally

Google payloads, configured images, userdata, private logs and TPM state must
remain local. The offline environment contains only the migration code and
open-source Linux/userspace tools; it packages no userdata or credentials.

The base container digest is pinned. Each build records the exact Debian
package versions, kernel release and artifact hashes. Package repositories can
change; retain the resulting container and package-version record for replay.
The Linux kernel in this environment is used only by the installer. Android
continues to use the unchanged OpenBook kernel/modules from camera25.

```sh
REPO="$(pwd)" # Run from the OpenBook checkout.
docker build -f tools/Dockerfile.ruby-installer -t openbook-ruby-installer .

scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/migration-package.py" pin \
  --base "$REVIEWED_CONFIGURED_IMAGE" --out "$NEW_PIN_DIR" \
  --build camera25 --dmi-prefix 'ROG Zephyrus G14 GA403WR'

mkdir -m 700 "$NEW_INSTALLER_DIR"
docker run --rm --network none -u "$(id -u):$(id -g)" \
  -v "$NEW_PIN_DIR:/input:ro" -v "$NEW_INSTALLER_DIR:/out" openbook-ruby-installer

# A NEW independently verified backup is required after each use of the USB.
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/migration-package.py" add \
  --snapshot "$LATEST_USB_BACKUP" --snapshot-sha256 "$VERIFIED_BACKUP_SHA256" \
  --base-manifest "$DEPLOYED_BASE/manifest.json" \
  --installer "$NEW_INSTALLER_DIR" --out "$NEW_PREPARED_USB"
```

`pin` and `add` accept regular files only. `add` changes only EFI in a private
clone, checks every existing EFI file and all non-EFI partitions unchanged,
and emits a preserving-update plan. The existing `apply-preserved-update.py`
can apply it after exact USB authorization and rehearsal. That writer still
writes its coherent three-part set; super and vbmeta payloads in this plan are
identical to the source. Full direct readback and power-off remain mandatory.
Never write a fresh image over the configured USB to add the installer.

## Validation

The synthetic unit suite is:

```sh
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/migration-test.py" -v
```

It checks partition/data preservation, target GUID separation, relocated GPT
validation with `sgdisk`, boot-identity rebinding, unchanged serial/initrd bodies,
stale source refusal, changed system/boot refusal, damaged GPT, small target,
wrong target/source alias, interrupted writes, failed readback, low battery and
the final power recheck before any destructive write. All eleven tests pass.

For an end-to-end run, package a **disposable VM's used disk** with a separate
source pin; never use owner data. `migration-qemu.py` boots the actual installer
entry in QEMU/OVMF, types through disk selection and the exact serial confirmation,
and verifies all non-EFI partitions before Android boots. `--cancel` instead
types an incorrect confirmation and requires source, target and decoy unchanged.
The install run then boots the synthetic NVMe with the original USB still
attached and a copy of that VM's software TPM state. Use the reviewed
ISA-compatible QEMU binary for the Ruby Android phase. It also compares the
existing metadata-encryption files before and after Android boot.
`--console-smoke` captures the normal framebuffer console, cancels through
keyboard input and verifies all three disks unchanged; review its screenshots.

```sh
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/migration-qemu.py" \
  --source "$PACKAGED_DISPOSABLE_USB" --tpm-state-from "$PREVIOUS_VM/tpm-state" \
  --android-qemu "$RUBY_QEMU" --out "$NEW_REHEARSAL_DIR" --seconds 760
```

A VM boot does not prove physical credential unlock. The laptop installation
and existing owner PIN/app-state checks remain separate acceptance steps.

The recorded final migration/data-retention run completes its 480-second
Android window (495.0 seconds including verification), with unchanged
metadata-encryption files, source disk, source TPM and decoy. It observes the
new EFI identity and target NVMe partitions while the source USB is attached.
It also records the existing VM system-server SIGSEGV/zygote-restart class.
An earlier attempt exits before boot completion for an undetermined reason.
These are retained in `evidence/2026-10-20-googlebook-migration/`; successful
copy/data checks do not establish runtime stability or physical acceptance.

## Google updates

This migration preserves the current OS behavior. It **does not disable or
qualify Google's automatic OS updater**. App updates and OS updates are separate
paths; do not disable Play Store or unrelated Google services as a workaround.

ANAL-229 tracks the requested follow-up. The leading candidate is a local
pipeline that obtains an authorized original update/recovery, applies the
versioned AMD compatibility changes, validates the entire framework/vendor/
kernel tuple and encrypted-data migration, rehearses failure/recovery, then
promotes a known build. An unknown build should stop for review.

An app could provide status, download scheduling and approval. Image rebuilding,
signature/AVB handling and disk writes need a carefully privileged backend or a
build host; an ordinary APK cannot safely patch the running kernel. Incremental
OTAs also depend on an exact source build, so applying them directly to a hybrid
or modifying only its kernel is not a general solution. The research must
measure the actual Ruby updater before choosing a reversible containment method,
and account for the security cost of delaying updates.

Primary references checked 2026-10-20:
[AOSP metadata encryption](https://source.android.com/docs/security/features/encryption/metadata)
explains the separate metadata key store;
[AOSP file-based encryption](https://source.android.com/docs/security/features/encryption/file-based)
describes credential/device-encrypted storage and key protection;
[AOSP A/B updates](https://source.android.com/docs/core/ota/ab)
describes slot/payload requirements. None establishes compatibility of a stock
Google OTA with this single-slot hybrid.
