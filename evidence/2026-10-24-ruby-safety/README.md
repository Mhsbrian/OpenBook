# Ruby firmware safety audit and fix (ANAL-251, 2026-10-24)

Release impact: **Ruby**, `system` only (two files change size; `vbmeta` follows). No boot, layout, data
format or installer-pin change. Design and verdicts: `docs/ruby-firmware-safety.md`.

## Inputs handed off (`handoff-ANAL-251.json`)

| Input | SHA-256 |
|---|---|
| `device/anybook/common/safety/gscutil.rc` (replaces Google's `af331819…`) | `61149fa16b80229cc7a3df2cd8f197f8160a9f6e252bbae8df49b8fc100c96b4` |
| `device/anybook/common/safety/gscutil-executor.rc` (replaces Google's `c7fdbc5c…`) | `5105310de9674fb53ede1e77d60f7d021e6de870a84ac97a389da2d57f8cab0e` |
| `device/anybook/common/safety/firmware-safety.json` (rules) | `2b806321a068168ed052244d078b5f4ed24d1b218eecbbd6f6f8ebe5af9c7da7` |
| `scripts/googlebook/build-safety-candidate.py` | `2a68a3e81c3dbfb280a9d32004de1ecd7715f5eaf3a944dd261000afd23d9b77` |
| `scripts/googlebook/check-firmware-safety.py` | `37ec72b89fd10c5b038d1db9ee3a40f62bc778ff956705b60315d7ab30eccae8` |
| Parent: RB-20261023-03 candidate C | `71da0228488781fa7db6bbb2b07b8559024023b606ae54cd868f780954b9cc24` |

## What was checked

| File | What |
|---|---|
| `g14-readonly-20261024.txt` | Read-only adb (shell user) on the G14 running RB-20261023-03, slot A, 2026-10-24 01:21 UTC. gscutil ran at boot (SELinux denied its `/memfd:GSC_IMAGE` write); gscd running as `android.system.desktop.security.gscd`; `efi_pstore` built in; no fwupd/flashrom/futility, no `/dev/mtd*`. Boot reasons since the fresh install: reboot ×3 |
| `audit-rb-20261023-03.{txt,json}` | `check-firmware-safety.py tree` on RB-20261023-03's system, system_ext, product and vendor (23 APEX init scripts included): **exactly two findings**, the two Google files, which still run. Every other trigger is reviewed; 11 firmware/TPM/EC tools by name, all reviewed |
| `google-postinstall.txt` | Google's update postinstall (`updater-wrapper-system` → `google_desktop_firmware_updater`) installs GSC firmware from `system` and AP (BIOS) and EC firmware from Google's `vendor` (`ap-ec-fw.zip` through `IFutilityExecutor`, which OpenBook's vendor does not have) |
| `payload-rb-20261023-03-laptop.json` | The payload the G14 took (`3c3b3b38…`): **no postinstall step**, 10 partitions |
| `payload-controls/` | `delta_generator` payloads from one 64 KiB image: with Google's postinstall config the check fails, without it passes |
| `kernel-pstore.txt` | Ruby's kernel config: `CONFIG_EFI_VARS_PSTORE=y` without default-disable, `CONFIG_PANIC_TIMEOUT=-1`, no Chrome EC (`CONFIG_CHROME_PLATFORMS` unset). The kernel command line comes from OpenBook's `vendor_boot` |
| `baseline-vm-security-lines.txt` | RB-20261023-03's own fresh-boot VM (ANAL-256, software TPM): gscutil started at post-fs, two denials, exit 133; check_tpm_clear exit 2; udsattestation exit 1 |
| `tests/` | Unit: checker 15/15 (real `delta_generator` payloads included), candidate builder 8/8 (`host_init_verifier` on each new init script), VM judge 6/6. `host_init_verifier` over all four partitions before and after: the same three errors, all in Google's `aoad.rc`; none new |
| `vm/` | `safety-vm.sh`: RB-20261023-03 + this change, `--vm-check` variant (not deployable, candidate `ea5af037…`), two-slot disk, TCG QEMU with a software TPM, 2,401 s |

## VM result (`vm/judge.json`): 19/19

- Boot: completed, slot A marked good, bootsync in sync, no AVB error (`vm/boot.json`, 9/9).
- **Changed:** gscutil did not start at boot (the baseline shows it did); no gscutil denials;
  `IGscutilExecutor` not found; the `/metadata/gscutil` step runs.
- **Unchanged:** gscd running and IGsc served; check_tpm_clear exit 2 and udsattestation exit 1, as in the
  baseline; keystore2, gatekeeperd and update_engine running; the Weaver served; KeyMint registered.
- No system_server fatal signal, no zygote exit. App crashes: Google's `repairmode` ×2 and Play services ×2,
  both also in the baseline (×3 and ×4). No new crashing app.
- The candidate's own firmware safety check: PASS, 2 neutralised, 7 reviewed init scripts
  (`vm/candidate-firmware-safety.json`). Changed paths: the two init scripts; added only the disposable
  report (`vm/candidate-result.json`).
- The judge was revised once while the VM ran: the shell may not look KeyMint up (`avc: denied { find }`
  for `hal_keymint_service`), so KeyMint is judged from servicemanager's registration line in both logs,
  and a check that no new app crashes was added. Both are in `scripts/googlebook/safety-vm-judge-test.py`.

## For the release

- Build the deployable candidate with `build-safety-candidate.py` (no `--vm-check`) on the release's parent;
  it runs the firmware safety check itself.
- Content check: `check-firmware-safety.py images` on the release images and `payload` on the laptop
  payload.
- After-update check: the `--vm-check` variant updated into the other slot, then
  `safety-vm-judge.py WORK BASELINE_SERIAL`.
- The laptop runs slot A, so the update goes into slot B.

## Not covered

- No run on the G14 hardware.
- `efi_pstore` is not changed (see the doc: it needs a `vendor_boot` builder).
- Verdicts for gscd, check_tpm_clear and udsattestation rest on their strings and the VM's behaviour, not on
  a TPM command trace.

Storage: this task's VM and extraction scratch was removed after the evidence was collected (32.4 GiB
reclaimed by `df`, 921 GiB free); logs and results are kept privately.
