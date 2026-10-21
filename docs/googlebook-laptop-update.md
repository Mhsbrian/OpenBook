# Updating the installed Ruby laptop from the USB, keeping its data

ANAL-229, 2026-10-21. This adds two offline entries to the Ruby USB's existing
installer environment:

- **Update the laptop's Googlebook system - keep data**
- **Restore previous laptop system (after an update)**

Both run `scripts/googlebook/laptop-update.py` in the same RAM-only Debian
environment as the migration installer (no network, Android, swap or automounter).
The USB's pinned system (`source.json`) is the new system. `laptop-update.json`,
embedded in the same initrd, names the single reviewed previous system it may
replace. Both files are fixed when the installer is built; the menu cannot pick
another build.

## What it writes

On the laptop's internal NVMe it writes only `super`, `vbmeta_a` and `EFI`, in
that order, with each range read back after a flush. The GPT, `misc`, the three
boot partitions, `metadata` (encryption keys) and `userdata` are never written.
A guard hashes the GPT copies, `misc`, boot partitions, `metadata`, the first and
last 64 MiB of `userdata`, and one MiB on each side of every written range,
before and after the update.

The new `EFI` is the laptop's own ESP with two changes: each initrd's bootconfig
gets the new `androidboot.vbmeta.digest`/`size`, and `ruby/RESEARCH.json` records
the new payloads. The disk-bound boot UUID, serial/KeyMint parameters, kernel,
initrd bodies, loader entries and logs are kept and compared byte for byte.

Before the first laptop write, the laptop's current `EFI`, `vbmeta_a` and `super`
are copied to a **rollback area on the USB beyond its partitioned extent**: it
starts at the next GiB after the USB's backup GPT plus 1 GiB (13 GiB on the
12.77 GB RB01 image) and needs 3.7 GiB. No USB partition is written. The tool
refuses a USB without that space. Two alternating, checksummed record slots track
`saving → saved → writing → updated` (and `restoring → restored`), so a torn
record write still leaves the previous record valid.

## Refusals

The update stops before any write when any of these is true:

- the USB system differs from its pin, or the record names another USB system;
- the laptop is not an installed OpenBook Googlebook (`openbook-ruby-installed/1`,
  same-machine record matching its GPT), or its layout differs from the USB's
  except for the size of `userdata`;
- the laptop's record or its actual `super`/`vbmeta_a`/boot bytes differ from
  the reviewed previous system; boot parameters other than the vbmeta digest and
  size drift; initrd bodies or the kernel differ;
- the previous and new systems differ in kernel, boot partitions, vendor, vendor
  command line, partition layout, or any logical image other than the reviewed
  list (`system` for camera25 → RB01);
- an earlier operation on this laptop was interrupted (`writing`/`restoring`):
  Restore must close it first;
- the charger/battery check fails, the disk identity changes after review, or the
  typed confirmation is not exactly `UPDATE <serial>` (`RESTORE <serial>`).

An already-updated laptop reports "Nothing to do". Both disks stay exclusively
open from review to write.

Restore requires a completed rollback copy for the same disk (GPT GUID, ESP UUID
and full GPT row hash), unchanged boot partitions and intact saved copies. It
writes back only the ranges that differ, then verifies them.

## Limits

- Not power-loss atomic. An interruption during `writing` leaves the laptop
  unbootable until **Restore** runs from the same USB. The unit and VM tests
  simulate this; no physical interruption was tested.
- One rollback level per USB. A later update replaces the saved copy, including
  one made for a different laptop disk; keep one USB per laptop until accepted.
- The VM fixture has no screen-lock PIN. The new vbmeta digest is outside
  KeyMint's key binding (verified-boot key and state), and the VM's encrypted
  `/data` unlocked after the change, but PIN unlock is a G14 acceptance check.
- Rollback is only offered because this pair changes no data format: same
  kernel, vendor, boot partitions and userdata format; only the `system` image
  (the input-library correction) and AVB metadata differ. Future pairs need their
  own data-compatibility review (`data_compatible_rollback`).
- This tool does not block or qualify Google OS updates, expand storage, or
  provide automatic fallback at boot (ANAL-230/231).
- Physical unlock, apps and the trackpad on the G14 are owner acceptance steps.

## Build and rehearse

```sh
REPO="$(pwd)"
docker build -f tools/Dockerfile.ruby-installer -t openbook-ruby-installer .
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/laptop-update.py" spec \
  --previous-manifest "$CAMERA25_BASE/manifest.json" --previous-build camera25 \
  --new-manifest "$RB01_IMAGE/manifest.json" --pin "$PIN_DIR/source.json" \
  --allow-logical system --out "$NEW_DIR/laptop-update.json"
# Put source.json and laptop-update.json in one input directory, then:
docker run --rm --network none -u "$(id -u):$(id -g)" \
  -v "$INPUT_DIR:/input:ro" -v "$NEW_INSTALLER_DIR:/out" openbook-ruby-installer
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/migration-package.py" add \
  --snapshot "$FRESH_USB_BACKUP" --snapshot-sha256 "$BACKUP_SHA256" \
  --base-manifest "$DEPLOYED/manifest.json" --installer "$NEW_INSTALLER_DIR" \
  --out "$NEW_PREPARED_USB" --replace-installer-sha256 "$OLD_INSTALLER_BUILD_JSON_SHA256"
```

`migration-package.py` adds the four update/restore entries only when the
installer's `build.json` lists a `laptop-update.json` that matches its pin, and
refuses to replace an update-capable installer with one that is not. Apply the
prepared USB with `apply-preserved-update.py`, as for earlier installer changes.

Synthetic rehearsal (container only; synthetic data and TPM):

```sh
Q="scripts/installer/inst-docker.sh python3 $REPO/scripts/googlebook/laptop-update-qemu.py"
$Q prepare --camera25-usb "$SYNTHETIC_CAMERA25_USB" --tpm-state-from "$ITS_TPM_STATE" \
  --usb-package "$NEW_PREPARED_SYNTHETIC_USB" --installer "$NEW_INSTALLER_DIR" \
  --android-qemu "$RUBY_QEMU" --out "$RUN"
$Q ui --run "$RUN" --mode update --answer wrong   # and --answer cancel
$Q ui --run "$RUN" --mode update
$Q android --run "$RUN" --label after-update
$Q ui --run "$RUN" --mode restore
$Q android --run "$RUN" --label after-restore
$Q ui --run "$RUN" --mode restore --answer noop
```

The Android phase checks boot completion, the guest's own dm-verity tables
against every hashtree root digest in the disk's current `vbmeta_a`, NVMe
`metadata`/`super`/`userdata` selection and the four metadata-encryption key
files. It does not rely on firmware printing the ESP UUID. Unit tests:
`laptop-update-test.py` (16) and `migration-package-test.py` (7).

## Owner steps on the G14

1. Plug in the charger. Boot the USB and choose **Update the laptop's Googlebook
   system - keep data**. Pick the laptop disk and type the phrase it shows.
2. Wait for **UPDATE VERIFIED** (a few minutes; the USB copy of the old system is
   the slow part on USB 2), press Enter, remove the USB and start the laptop.
3. Check PIN unlock, apps, files, tap-drag and two-finger scrolling.
4. If it does not start or misbehaves, boot the USB and choose **Restore previous
   laptop system (after an update)**. Keep the USB until the update is accepted.

Results and sanitized evidence: `evidence/2026-10-21-ruby-laptop-update/`.
