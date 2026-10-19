# ANAL-191 on the G14: the installer in the owner's `anal192d` session (2026-10-18)

Source: the build host's read-only copy `~/anybook/installer/g14/stick-20261018T123221Z/` (`read-stick-logs.sh`, 12:32Z).
The default boot is `live-001/prior/` (persisted logcat); `live-001/` is "save logs", `live-002/` the ARM apps check.
Stick `openbook-live-20261018-anal192d` (`main` `81578c1` + #83), with #68 and #70. **No photos yet, and no hardware
report (`hwcheck-live-NNN.json`).** The files here are filtered extracts: the full logcat stays on the build host,
because it holds the owner's network details.

| File | What |
|---|---|
| `default-boot-installer.txt` | The default boot (11:00–11:05): the installer's activities, the daemon's SELinux records, efivarfs, `nvme0n1`'s partition scan, the battery at 11:04 |
| `save-logs-boot-installer.txt` | The "save logs" boot (11:59): the same filter, plus efivarfs in `/proc/mounts` |
| `internal-nvme.txt` | The internal NVMe in every G14 session's capture since 2026-10-16, and both `anal192d` kernel scans |

## What happened (times UTC)
| Time | Event | Source |
|---|---|---|
| 11:00:37 | `efivarfs.ko` loaded | modprobe |
| 11:01:03 | The installer's setup screen (on a live stick) stepped aside; no crash on the stick's first boot | `wm_*` |
| 11:01:06 | **The wizard opened by itself**; the daemon answered its first request | `wm_create_activity`, daemon records |
| 11:02:12 | The hardware check (the only request that lists `/vendor/firmware`), once | daemon records |
| 11:02:51 | The wizard closed | `wm_finish_activity` |
| 11:02:55 | **"Install OpenBook" opened again from All Apps** | `InstallLauncher`, category `LAUNCHER` |
| 11:03:05 | Requests that read the power supplies: hello or a plan (H: "View the plan" / Continue) | daemon records |
| 11:04:16 | Battery **41 %, discharging** (`healthd st=3`) | healthd |
| 11:04:29 | **An install request** (`apply`): a second process in the daemon's domain, pid 5244. Only `apply` forks (`daemon.c`) | daemon records |
| 11:04:43 | Another request from the wizard (H: after the refusal) | daemon records |
| 11:04:49 | The wizard closed | `wm_finish_activity` |

**The install was refused before anything was written.**
- **No report on the stick.** Every install that gets past the early checks writes `openbook/logs/install-*.json`, whether it succeeds or fails. `read-stick-logs.sh` copies `openbook/logs/` whole, and there is none.
- **The internal NVMe is unchanged:** p1 2 GiB + p2 952 GiB in both later boots, as in every session since 2026-10-16 (`internal-nvme.txt`). That disk has no free space, so the only layout is a whole-disk install, which wipes the table in its first write step.
- **Why it was refused (H, strong):** S8, power. The laptop was on battery at 41 % (S8 needs mains or at least 50 %).
  - The daemon could not read the power supplies itself (below), so it used the reading the app sends.
  - The other early refusals don't fit: the wizard enables Install only once the typed name matches (S3), and the plan was the one just shown.
  - The owner's photo of the screen would settle it.
- **On mains power, this install would have erased the internal NVMe.** The checklist said "Never press Continue on the Disk screen"; whether the install was meant is the owner's to say.

**The firmware side:**
- efivarfs was mounted on the "save logs" boot (`/proc/mounts`), with no denial.
- The default boot logged no mount failure, so the plan's `boot.nvram` would have been `planned` (H until the photos).
- The G14's own `Boot####` entries and `BootOrder` were not recorded: "save logs" did not collect them (added).

**SELinux on real hardware** (QEMU has neither, so neither showed before):
- `openbook_installd` → `sysfs_batteryinfo` (`/sys/class/power_supply/*/type`), 4 records per power reading.
  - AOSP lets only the health HAL read these (neverallow in `domain.te`), so a read rule cannot build.
  - The app's BatteryManager reading is what S8 uses. The denial is now `dontaudit`.
  - **S8 now fails closed** when neither reading exists; before, it logged "not checked" and went on.
- `openbook_installd` → `/vendor/firmware` (`openbook_vendor_fw_file`, search), from the hardware check's speaker-tuning test.
  - Policy can't allow it: a `system_ext` domain can't name a vendor type, and Treble keeps vendor files from core domains.
  - By design the check then says nothing about the tuning. A follow-up could have vendor init publish it as a property.

## Tests of the fixes (PR #104, image `openbook-live-20261018-anal191i`, built at `b25f91a`)
| Run | Result | Files |
|---|---|---|
| Engine host tests, with two new S8 cases (on battery at 41 % with the charger off; supplies unreadable and no reading given: both refused, target unchanged) | **69/69** | `tests/engine-host-SUMMARY.md` |
| QEMU live "save logs" (`live-qemu.sh … logs`): the new `INSTALLER` section; `live-report.py` on that capture | **11/11**; `installer_nvram` and `installer_log` filled | `tests/live-logs-SUMMARY.md`, `tests/qemu-installer-section.txt`, `tests/qemu-report.md` |
| QEMU wizard dry run and install, enforcing | **17/17** | `tests/wizard-SUMMARY.md` |
