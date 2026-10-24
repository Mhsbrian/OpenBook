# Ruby firmware safety (ANAL-251)

Googlebook images are built for Google's hardware. Some of what they run at boot, and in Google's update
postinstall, talks to firmware that on a PC belongs to the laptop maker: the TPM, the BIOS flash and the
embedded controller. This page says what OpenBook neutralises, what it keeps and why, and how every new
image is checked. Rules: `device/anybook/common/safety/firmware-safety.json`. Evidence:
`evidence/2026-10-24-ruby-safety/`.

## What runs on the G14 today (RB-20261023-03, Google 16658739)

| Item | What it does | On the G14 | OpenBook |
|---|---|---|---|
| `gscutil.rc` → `gscutil perform-os-startup` | Every boot: stages Google security chip (GSC) firmware (`gsc.zip`) and sends GSC vendor commands through `/dev/tpm0` | `/dev/tpm0` is the CPU's firmware TPM. It ran at 00:48 UTC on 2026-10-24; SELinux denied the firmware image buffer and it stopped. The VM shows exit 133 | **Neutralised**: the boot step is removed, the `/metadata/gscutil` directory is still made |
| `gscutil-executor.rc` (IGscutilExecutor) | Started on demand; how Google's postinstall installs GSC firmware | Not started (no Google payload is accepted) | **Neutralised**: the service is not defined |
| Google's postinstall: `updater-wrapper-system` → `google_desktop_firmware_updater` | GSC firmware from `system`; AP (BIOS flash) and EC firmware (`ap-ec-fw.zip`) from Google's `vendor` | Only reachable through a payload's postinstall step. The OpenBook OTA certificate refuses Google payloads, and OpenBook payloads have no postinstall | **Checked**: every payload must have no postinstall step (`check-firmware-safety.py payload`) |
| `gscd` | IGsc daemon (user hsm): TPM commands for Trusty's secure storage, `udsattestation`, `check_tpm_clear` | Running | Kept: Trusty uses it. Standard TPM 2.0 commands |
| `check_tpm_clear` | Every boot: a transient TPM key to name the TPM owner; writes `/metadata/hwsec_metadata` | Runs; exits 2 in the VM | Kept (reviewed) |
| `udsattestation` | One shot at boot | Skips provisioning on a TPM that is not Google's chip; exits 1 in the VM | Kept (reviewed) |
| `timberslide`, `ec_crash_collector`, `ectool` | Chrome EC tools | Inert: Google's kernel has no Chrome EC support (`CONFIG_CHROME_PLATFORMS` is not set) | Kept (inert) |
| fwupd, flashrom, futility, vpd, crossystem | Firmware flashers | **Absent**: they live in Google's `vendor`, which OpenBook replaces | Forbidden in any partition |
| `efi_pstore` | On a kernel oops or panic, writes the log into UEFI variables | Built into Google's kernel and enabled (`CONFIG_EFI_VARS_PSTORE=y`, no default-disable); a panic reboots at once (`CONFIG_PANIC_TIMEOUT=-1`) | **Open**, see below |
| `spi_amd`, `tpm_crb` | AMD SPI controller and firmware TPM drivers | OpenBook's own `vendor_dlkm` modules. No `/dev/mtd*` or spidev | Unchanged |

The 2026-10-22 audit said gscutil and check_tpm_clear "never started". That was wrong: they are boot-time
`exec` actions, which never set `init.svc.*`, and gscd's service name is
`android.system.desktop.security.gscd`.

## How every image is checked

```sh
# extracted partitions (APEX init scripts too, with --tools)
python3 scripts/googlebook/check-firmware-safety.py tree system=DIR system_ext=DIR product=DIR vendor=DIR \
    --tools OTATOOLS/bin --work SCRATCH --output result.json
# partition images
python3 scripts/googlebook/check-firmware-safety.py images --tools OTATOOLS/bin --work SCRATCH system=system.img ...
# an update payload (payload.bin or an OTA zip)
python3 scripts/googlebook/check-firmware-safety.py payload payload.bin
```

It fails (exit 1) on: a neutralised file that is Google's original or anything else; an init script that
mentions the TPM, security chip, EC, flash tools, UEFI variables or the hsm user and is not reviewed at its
exact SHA-256; a firmware-tool name in a `bin` directory that is not reviewed; a forbidden tool anywhere; a
payload with a postinstall step. A new Google build that adds or changes any of these stops the release
until someone reviews it and updates the rule file.

`build-safety-candidate.py` applies the two replacements through the same reassembler as every OpenBook
candidate and runs the check on the result; a candidate that fails has its manifest set aside.

## Releases and the on-laptop updater (phase 3)

- **Release:** the change is `system` only (two files change size). It ships as an ordinary OpenBook-signed
  update into the other slot. The release runs `check-firmware-safety.py` on its candidate images and its
  payload as part of its content check.
- **Rebasing onto a new Google build** (`rebase-google-build.py`, and `openbook-adapt` on the laptop): the two
  files are changed paths of the OpenBook layer, so they are carried to every later Google build. If Google
  changes either file, the rebase stops (fail closed).
- **On the laptop (ANAL-229, built 2026-10-24):** `openbook-adapt` ports the check (`safety.go`). It checks
  every release it adapts, before building it: the adapted `system`, Google's new `system_ext` and `product`,
  and every APEX's init scripts. The rules are the running release's own copy, shipped by
  `build-update-app-candidate.py --adapter` at `/system/etc/openbook/firmware-safety.json`. Any finding, missing
  rules, or content it cannot read holds the release (exit 8, with the reason in the app). Its payloads never
  carry a postinstall step: the writer refuses one.
  - On Google 16658739 and 16452207, RB-20261023-03 and a test release with this change, it gives this
    script's findings and inventory exactly.
  - On the G14 it held RB-20261023-03's own adaptation on Google's `gscutil` scripts.
  - Evidence: `evidence/2026-10-24-adapt-firmware-safety/`.
- **Init's scope is wider than `*.rc`.** Android's init parses every regular file in an `etc/init` directory,
  whatever its name, and an APEX's `etc/*rc` (versioned scripts such as `netbpfload.35rc`). The laptop check
  reads those too; this script does not yet.
  - Google 16658739 has 5 versioned APEX scripts and no other such files. None matches the patterns.
  - Widening this script is a follow-up. It changes its pinned bytes, so ANAL-251's checks would run again.

## `efi_pstore`: open

The fix the review proposed, `efi_pstore.pstore_disable=1`, belongs on the kernel command line. On Ruby that
line comes from OpenBook's `vendor_boot` (bootsync copies it into each slot's ESP entry), and no Ruby
builder changes `vendor_boot` yet: the candidate format protects the boot partitions. Two ways forward,
each its own change:

1. **Command line** (recommended): a reviewed `vendor_boot` builder adds the flag, the release updates
   `vendor_boot` and `vbmeta` through the normal slot update, and bootsync writes the new slot's entry. The
   cost: no kernel crash log survives a reboot (the G14 has no RAM-backed pstore).
2. **Clear after reading:** a vendor init step copies `/sys/fs/pstore/dmesg-efi-*` to `/data/vendor` and deletes
   them, which frees the UEFI variables. Crash logs are kept; it needs vendor policy for `pstorefs`.

No panic has been recorded since the two-slot fresh install (boot reasons: reboot ×3 on 2026-10-24). The shell
user cannot read pstore or the UEFI variables, so whether older records are stored is unknown.

## Not covered

- No hardware run of the neutralised image yet: VM only.
- Strings, not source code, back the "standard TPM 2.0 commands" verdicts for gscd, check_tpm_clear and
  udsattestation. A TPM command trace was not taken.
- Apps and Java services that might call these tools directly are not inventoried; SELinux limits which
  domains can run them.
