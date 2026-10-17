# Installer end to end, and the owner's integrated stick (ANAL-192, 2026-10-17)

Everything here ran in QEMU/KVM + OVMF on image files, SELinux enforcing. **Nothing has run on the G14 yet.** Details and the owner's checklist: `docs/installer.md` §13. The user guide and release checklist: `docs/INSTALL.md`.

## The stick: `openbook-live-20261017-anal192c`
- Built from a clean checkout of `main` at `3908b14` (PRs #1–#59). The build and the snapshot ran in one lane-lock hold.
- Add-ons: the power check `openbook-powercheck-anal178-c` and the ARM apps check `openbook-bridgecheck-anal192c` (built from `main`). The graphics check is not on it; its second run waits for PR #61.
- sha256 **`dd1ebe202cb49e56317b4ec477c17464ef754d3bd7e482904ddc047612301442`**, and `ab0c5726…` before the add-ons (`image/`).

| Run | Result | Here |
|---|---|---|
| End-to-end matrix (`scripts/installer/e2e-qemu.sh`) | **79/79** | `e2e-qemu/SUMMARY.md`, `results.json`, `inspect/` (every disk state), `cases/<case>/` (sections, firmware lines) |
| Live stick matrix (`live-qemu.sh`) | **40/40** | `live-qemu/` |
| Wizard (`wizard-qemu.sh`) | **25/25** | `wizard-qemu/` |
| ARM apps check in QEMU | 5/5 verdicts; CoreMark arm64/x86_64 0.39 (exe), 0.40 (app) | `addons-qemu/bridge-*` |
| Power check in QEMU | vm 14/14, real 10/10 steps | `addons-qemu/power-*` |
| SELinux denials in the enforcing boots | 0 groups with an OpenBook type (234 records in 10 AOSP/test-shell groups) | `avc/anal192c.md` |
| Reproducible image | `anal192b` rebuilt from its snapshot, byte for byte | `image/reproducible-anal192b.txt` |

## End-to-end matrix highlights
- **Alongside a Windows-like disk:**
  - MSR, NTFS and recovery are byte-identical afterwards. The ESP gains only `EFI/OpenBook/systemd-bootx64.efi` and passes `fsck.fat`.
  - With fresh NVRAM, the firmware still starts the stand-in Windows boot manager.
  - With a boot option added (as in the firmware setup), OpenBook starts and runs through setup to the desktop.
- **The 32 GiB disk is refused** in the CLI and in the wizard (`screens/1-…`).
- **Power cuts at six points, each followed by a restart:**

  | Cut | Disk afterwards |
  |---|---|
  | `check_source` | old table |
  | `boot_images` | blank |
  | `system` | blank |
  | `boot_entry` | new table, not activated |
  | `verify` | new table, not activated |
  | `report` | complete |

  The firmware starts nothing from the incomplete states, and every restart completed.
- **The installed disk** boots alone, and with the stick still plugged in. The stick is unchanged.
- **Reinstall over a used OpenBook:** new disk and partition GUIDs, a new serial number, the old data gone, setup again.

## Findings
1. An installed OpenBook shows "USB drive detected · Tap to set up" for a plugged-in installer stick. Tapping it formats the stick (`cases/inst-stick/sections/notifications.txt`).
2. The wizard labels a disk with OpenBook on it "Linux" (`screens/5-…`).
3. Two harness bugs were found and fixed on the way (`docs/installer.md` §13.5):
   - `dev-runs/e2e-anal192a-results.json` is the first full run, 77/78. The `install` power-off failure and the cut `reinstall` were the harness, not the engine.
   - `dev-runs/e2e-anal192b-results.json` is the rerun on `anal192b`: 79/79.

## Screens (`screens/`, downscaled)
| File | What it shows |
|---|---|
| `1-live-wizard-disks-windows-and-small.png` | The wizard's disk step with the Windows-like disk, the 32 GiB disk ("too small") and the stick ("In use") |
| `2-alongside-openbook-from-firmware-option-qemu-display.png` | OpenBook setup, started from the firmware option next to Windows |
| `3-alongside-desktop-after-setup.png` | The alongside install's desktop |
| `4-installed-no-stick-qemu-display.png` | The whole-disk install, alone, at setup |
| `5-live-wizard-disks-installed-openbook.png` | The disk step over the installed OpenBook, with alongside refused |
| `6-reinstalled-setup-again.png` | After the reinstall: setup again |

The `qemu-display` frames come from QEMU's screendump, with red and blue swapped back (`docs/installer.md` §12.7). The others are Android's own `screencap`.

## Reproduce
`docs/installer.md` §13.9. The test-only EFI apps' hashes are in `e2e-qemu/efi-apps.txt`.
