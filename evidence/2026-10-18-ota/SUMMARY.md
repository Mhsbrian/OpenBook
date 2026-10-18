# Image updates over adb: A/B OTA with openbook-bootsync (ANAL-223, 2026-10-18)

**Result:** the installed G14 was updated over Wi-Fi adb from slot A (`anal192e`) to slot B (`openbook-ota-20261018-cand1`) at 23:24Z, with `/data` kept. It booted slot B, the slot was marked good, and the virtual A/B merge completed 12 s after boot. This followed a QEMU rehearsal (55/55 checks) and bootsync's host tests (56/56). The owner's go: ANAL-214, comment `01a15100-2884-7da1-87ca-eb98be040aab` (21:52Z), recorded on ANAL-223 at 21:53Z.

Docs: `docs/installer.md` §2.5 and §13.13, `docs/adb-debug.md` §7.

## What was sent

| | |
|---|---|
| Package | `openbook-ota-20261018-cand1.zip`: full A/B OTA, 937,904,235 bytes, sha256 `d75f4773e9d91996446c929e7024e55134536c439199410eddf02df50cbd24fa` (`packages/openbook-ota-20261018-cand1.json`) |
| Tree | `481c5c8` = this branch at `0157eee` (`main` `2594cd3` + #107 + bootsync and the boot HAL) merged with #109 (120 fps composer fix), #106 (touchpad palm lift-off) and #104 (installer S8). Built 2026-10-18 22:32Z, `anybook_g14_x86_64-cp2a-userdebug`, AOSP test keys |
| Not in it | Quire's platform PRs (#108, #110, #111, stacked on #94): not reviewed yet, and #108 adds a privileged app with computer control. `ro.adb.secure` unchanged (still the owner's decision) |
| vbmeta digest | `e0ec4b9ccb2df1e7b01c41e097b3d2b4ee56d14a3d1ecbf92db28b49acaa4fac` (was `6d3735b9…`, `anal192e`) |

## The G14 (`g14/`)

| Step | Time (UTC) | Result | File |
|---|---|---|---|
| Read-only checks | 21:37, 23:19 | `anal192e` on slot A, whole-disk install, VAB on, ESP unmounted, `otacerts.zip` with the test key; nobody else on the laptop; ANAL-212's composer swap already gone (the laptop had rebooted at about 22:26) | `precheck.txt` |
| Baseline | 23:21–23:22 | `g14-adb.sh state` and `capture` | `state-diff.md`, `capture-before/` |
| Coordination | 23:22 | A note on ANAL-222, before writing: the update is running, keep off the laptop over adb | — |
| `g14-adb.sh ota … --yes` | 23:23–23:24 | Package checks passed; update_engine wrote slot B in **82 s** over Wi-Fi; then the package's own `openbook-bootsync` ran once as root (the installed image has none): files to `openbook/b/`, entry `openbook-b+3.conf`, loader.conf `default openbook-a.conf` + `preferred openbook-b.conf`; verified: systemd-boot starts B next | `ota-apply.log` |
| Reboot | 23:24:22 | The laptop was idle (last input 19 min earlier, launcher on screen); boot completed at 23:24:58 | `precheck.txt` |
| After | 23:24:43–23:24:54 | The new boot HAL started; `markBootSuccessful`: `openbook-b+2-1.conf` → `openbook-b.conf` (systemd-boot had used one try), `default openbook-b.conf`, A's entry removed; `Merge finished with state MergeCompleted`; then `setSlotAsUnbootable(A)` | `ota-status-after.log` |
| Data | 23:25 | Same user, 153 packages with the same versions (Provision → OpenBook setup, from #100), the same Settings except three boot/charge counters, 2 Wi-Fi networks, 1 account, PIN set; unlocked with its PIN a minute after the reboot. Shared storage 188 → 186 files: MediaProvider's own `.transforms/recovery` database, rotated at boot; the owner's files are there | `state-diff.md` |
| Binaries | 23:27 | The running composer is #109's (sha256 `df6f5287…` = the package), no bind mount; `openbook-bootsync` and the boot HAL match the package; AOSP's boot APEX is gone | `binaries-on-device.txt` |
| Crashes, denials | 23:26 | No tombstone or ANR, no fatal crash in logcat, before or after. No denial involves OpenBook's update path. New after the update: first-stage init's snapuserd records (`kernel` → `ota_metadata_file`, `super_block_device`, `sysfs_ublk`; once, on the snapshot boot, as in QEMU) and `hal_usb_default` → `sysfs_batteryinfo` (AOSP's example USB HAL, not from this change) | `capture-after/avc.md` |
| Frame pacing | 23:27 | Not measured: nothing moved on the screen during the passive check (the laptop was in use, so the scrolling check was not run) | `flip-check-after.txt` |

## QEMU rehearsal (`qemu/`, run `r2`): 55/55

On the G14's own starting point: `scripts/installer/e2e-qemu.sh`'s `install` case installed `openbook-live-20261018-anal192e.img` onto a 128 GiB virtual NVMe (unattended engine, `new-complete`; `qemu/e2e-install/`). `prep` added the serial console to that entry, did setup the way the installer's setup ends, set a PIN, installed an app, and wrote a setting and a 4 MiB file. adb ran over QEMU's USB Ethernet (GKI `cdc_ether`), and every update used `g14-adb.sh ota`.

| Case | What it shows | Checks |
|---|---|---|
| `prep` | the installed `anal192e` boots slot A, enforcing, AOSP's boot HAL | 7/7 |
| `ab` | first update A → B, with bootsync from the package; B boots; PIN, app, setting, file, serial kept; no setup screen; the merge completes; ESP and misc agree | 13/13 |
| `ba` | second update B → A from `ab`'s disk: this time the boot HAL on B moved the entry itself (no root bootstrap) | 13/13 |
| `rollback` | a package whose kernel cannot start (`--break-boot`: `rdinit` missing, `panic=5`) installs and verifies; B panics **three times**, then systemd-boot starts A by itself, with `/data` intact and update_engine idle; the good package then installs from A and B boots | 12/12 |
| `cut` | power cut (QEMU `quit`) at 40 % of the write: A boots, `/data` intact; the re-run resumes ("Resuming after 282/718 operations") and completes | 10/10 |

A development run on a build without #109/#106/#104 (`r1`, `ota-dev1`) passed the same cases.

## Host tests (`host/`): 56/56

`scripts/ota/bootsync-test.sh` on a whole-disk install made by the install engine, with the candidate's boot images in slot B:
- slot A's ESP files are byte for byte what bootsync exports;
- refusals with the ESP unchanged: blank slot, one changed byte of `vendor_boot_b`, another signing key, unsigned vbmeta;
- activate, again, mark-good, rollback, re-update, the second update, cancel, disable;
- a stop after each write step (files, entry, loader.conf) leaves a FAT that `fsck.fat` passes and that starts A (B only after loader.conf).

The entry systemd-boot would start is computed independently of bootsync (systemd v262.1 `boot_entry_compare`, `config_select_default_entry`), and the two agree in every case.

## Not shown

- **Frame pacing on the updated G14.** The patched composer is running (by hash), but a measurement needs something moving: `scripts/graphics/g14-flip-check.sh --scroll` while the laptop is idle, or testufo.com in Chrome.
- **A slot B failing on the G14 itself.** Rollback was shown in QEMU/OVMF only. What the G14 did show: its firmware writes systemd-boot's counter (the first boot of B renamed `openbook-b+3.conf` to `openbook-b+2-1.conf`), and the fallback at `+0` is systemd-boot's own logic, the same binary as in QEMU.
- **Alongside installs** (XBOOTLDR, no loader.conf of OpenBook's own): bootsync refuses them for now.
