---
name: openbook-g14-update
description: Ship a new OpenBook build to an installed OpenBook laptop (today the ASUS G14 at 192.168.50.11) as an A/B image update over adb, keeping the user's data, with a QEMU rehearsal first and an automatic fallback to the old slot. Use when a task says to put finished work, a PR, a fix or a feature "on the laptop", "on the G14", "update the laptop", "OTA", "image update", or "sync it to the laptop"; also for rolling an installed OpenBook back or checking an update's result. Not for live USB sticks (re-flash those) or Cuttlefish.
---

# Updating an installed OpenBook over adb

The procedure that took the G14 from `anal192e` to `openbook-ota-20261018-cand1` on 2026-10-18 (ANAL-223, PR #112): QEMU 55/55, then the laptop, with 0 data lost. The repo is https://github.com/Mhsbrian/OpenBook. Paths below are relative to a checkout of it. `<data>` is `~/anybook`.

How it works: `docs/installer.md` §2.5 (bootsync, the boot HAL) and §13.13 (results). The operator's view: `docs/adb-debug.md` §7. Each step below has a command and a pass condition. **If a pass condition fails, stop and report. Do not go on to the laptop.**

## 0. Gates: check them first, every time

1. **The owner's go, naming the device.** An update writes the laptop's disk: the other slot, copy-on-write data in `/data`, and the ESP's loader entry.
   - The standing go for the G14 at `192.168.50.11` (internal NVMe) is ANAL-214, comment `01a15100-2884-7da1-87ca-eb98be040aab` (2026-10-18). It covers that device only.
   - Before writing, read the latest owner comments on the issue you are on and on ANAL-214. A later "stop", "wait" or "not now" overrides the go.
   - Any other device needs its own go, naming it.
2. **What goes in.** The base is the tree the laptop runs now: the last update's manifest, `tree` in `<data>/ota/out/<label>.json`.
   - Add the PRs the owner named, or the ones the issue lists. A PR with an open Checker **Hold** stays out unless the owner says otherwise.
   - Write the exact commits down. The owner always asks what is in it.
3. **Nobody else on the laptop.** `ps -eo pid,cmd | grep -E '192\.168\.50\.11|g14-adb|composer-swap'` must show nothing. Read ANAL-222's recent comments.
   - Post one note on ANAL-222 before writing: the update is running, stay off adb until the result is posted.
   - A composer swap (`/mnt/openbook-hwc` bind mount) disappears at the reboot.
4. **Power.** AC, or at least 50 % battery. `ota` refuses otherwise.

## 1. Build the package (about 5 to 40 min)

```bash
# a separate tree for the integration, so this PR's branch stays clean
git clone -q <your checkout> <data>/ota/<name> && cd <data>/ota/<name>
git merge <PR branches>          # resolve docs/STATUS.md conflicts with --ours; any conflict in device/ or aosp/ is a real one
export BUILD_NUMBER=<yyyymmdd>.<x>   # its own fingerprint: g14-adb.sh ota refuses the running build's (stale package cache)
AOSP_JOBS=20 scripts/aosp-docker.sh -d anybook-aosp-build-<x> /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug \
  droid target-files-package otatools-package openbook_hals_test validatekeymaps </dev/null >/dev/null 2>&1
timeout 590 docker wait anybook-aosp-build-<x>   # repeat until it returns; `m exit 0` in <data>/logs/aosp/build-*.log
scripts/ota/make-ota.sh openbook-ota-<yyyymmdd>-<x> --tree "<commit>: <what it is>"   # ~1 min, under the lane lock
```

- **Pass:** `<data>/ota/out/<label>.{zip,json,bootsync}` exist, and the JSON's `vbmeta_digest`, `build_date_utc` and `fingerprint` are new.
- **Why the build number:** without one every build is `…/eng.builde:userdebug`. With the running build's fingerprint, PackageManager keeps its parse cache of the old system APKs and APEXes (it invalidates `eng.*` caches by mtimes, which image files don't have) and runs no upgrade step. On 2026-10-19 that kept AVF's system service from starting after an update (ANAL-225).
- For the rollback rehearsal, also run `make-ota.sh <label>-broken --target-files <data>/ota/builds/<label>/target_files.zip --otatools <data>/ota/builds/<label>/otatools.zip --break-boot`. That gives the same build with a kernel command line that cannot start. **Never send a `-broken` package to the laptop.** Its JSON says `test_only_broken_boot: true`.
- Run the build under the lane lock (aosp-docker.sh takes it). Redirect its output: a plain `| tail` keeps the tool call open until the build ends.
- Check that the merged PRs are in the image, for example by hashing a changed binary in `target_files.zip` against the previous build's.

## 2. Rehearse in QEMU first (about 15 to 25 min)

Start the VM from the state the laptop is in. The run `r2` in `<data>/installer/ota/` keeps:
- `base.img`: `anal192e` installed by `scripts/installer/e2e-qemu.sh`'s `install` case, after `prep`;
- `after-ab.img`: its first update, which is the G14's state since 2026-10-18 23:24Z: slot B, the new boot HAL;
- `after-ba.img`: one more update.

```bash
Q="python3 scripts/ota/ota-qemu.py"; P=<data>/ota/out/<label>.zip; X=<data>/ota/out/<label>-broken.zip
$Q case ba       --run r2 --ota $P                       # the update the laptop will get: from slot B, through its boot HAL
$Q case rollback --run r2 --from after-ab --ota $P --broken $X   # a slot that never starts: 3 tries, then the old slot
$Q case cut      --run r2 --from after-ab --ota $P               # power cut at 40 %: the old slot boots, the re-run resumes
$Q check --run r2                                         # results.json, SUMMARY.md in <data>/logs/installer/ota/r2/
```

- **Pass:** every check in those cases is PASS. That means:
  - the slot booted;
  - the PIN, the app, the setting and the file are kept;
  - no setup screen;
  - the merge completed;
  - ESP and `misc` agree;
  - no denial for `openbook_bootsync`, `hal_bootctl` or `openbook_esp_block_device`.
- Run one case per foreground tool call, with its output to a log file. A case takes 3 to 6 min.
- If the laptop's state changes (another update), re-make the matching saved state with `case ab|ba` before trusting a rehearsal.
- A fresh starting point, if the saved disks are gone: run `scripts/installer/e2e-qemu.sh <stick image the laptop was installed from> <run> prep install`, then `ota-qemu.py prep --run <run> --installed <data>/installer/qemu/<run>/whole.img`, then the cases.
- Changed `device/anybook/common/bootsync/` or the FAT code? Also run `scripts/ota/bootsync-test.sh <stick image> <run> <data>/ota/builds/<label>/images`. Unzip `IMAGES/{boot,init_boot,vendor_boot,vbmeta}.img` there first. It must report 56/56 or more.

## 3. The laptop

```bash
export OPENBOOK_G14_ADDR=192.168.50.11
B=<data>/installer/g14/ota-g14-$(date -u +%Y%m%dT%H%MZ); mkdir -p $B
scripts/g14-adb.sh state $B/state-before.json                       # read-only baseline (stays on the host)
scripts/g14-adb.sh capture --redact evidence/<date>-ota-<x>/g14/capture-before $B/capture-before
scripts/g14-adb.sh ota <data>/ota/out/<label>.zip --dry-run        # checks only
scripts/g14-adb.sh ota <data>/ota/out/<label>.zip --yes > $B/ota-apply.log 2>&1   # --yes only with the go from step 0
```

- **Pass for `ota`:** the log ends with `verified  slot <x>: images match vbmeta_<x> …; systemd-boot starts slot <x> next`. It took 82 s over Wi-Fi for 895 MB.
- On a failure before that line, nothing switches at the next boot. Report it and keep the laptop as it is. Before rebooting, `ota-cancel` undoes a staged update.
- **The reboot happens only when the laptop is idle.** Check: `dumpsys power` `mLastUserActivityTime(excludingAttention)` is more than 10 min behind `/proc/uptime`, no media is playing (`dumpsys media_session`), and the screen shows the launcher or nothing.
  - **If someone is using it:** leave the update staged (it is the next boot's default) and ask the owner to restart when it suits them.
  - **Idle:** `adb -s 192.168.50.11:5555 reboot`, then `scripts/g14-adb.sh wait 840`.
- **After the reboot,** collect:
  - `scripts/g14-adb.sh ota-status`;
  - `scripts/g14-adb.sh state $B/state-after.json`;
  - `capture --redact … capture-after`;
  - as root, `sha256sum` of the binaries the update was for, against `unzip -p <data>/ota/builds/<label>/target_files.zip <PATH>`.
- **Pass:**
  - `slot: _<x>`, the package's vbmeta digest, and `openbook-<x>.conf (good)`;
  - `update_engine: UPDATE_STATUS_IDLE` and `Update state: none` (the merge, usually within a minute);
  - the same users, packages and versions, Settings, Wi-Fi network count and accounts (`Accounts: N`);
  - the user's files: `media_files_user` the same, and `media_list_sha256` the same or its differences explained. Apps change their own files under `Android/data` while running;
  - no tombstone or ANR, and no new denial from OpenBook's domains.
  - Expected noise: boot counters (`boot_count`, `time_to_full_millis`, `global_color_palette_version`), MediaProvider's `.transforms/` files, and first-stage `kernel` → `snapuserd`/`ota_metadata_file`/`super_block_device` denials on the snapshot boot.
- **Never run screen-driving checks** (`g14-flip-check.sh --scroll`, taps, swipes) while someone is using the laptop. Passive checks only.

## 4. Evidence and the report

- `evidence/<date>-ota-<x>/`: `SUMMARY.md`, `packages/<label>.json`, the QEMU `results.json`/`SUMMARY.md` and each case's `checks.json`, logs and `serial.log.gz`. Follow the layout of `evidence/2026-10-18-ota/`.
- For the laptop, keep: `precheck.txt`, `ota-apply.log`, `ota-status-after.log`, `binaries-on-device.txt`, a `state-diff.md` with counts only, and `capture-*/` without `logcat-final.txt`, `dmesg.txt` or `collect-final.txt`.
- **Never commit:** the `state` JSON, serial numbers, app or account names, Wi-Fi names, or screenshots of the owner's screen. Grep the evidence for the device's serial before committing.
- **The report to the owner, short:**
  - what is on the laptop now, and which PRs are in it;
  - what came through (apps, settings, PIN), and what was not checked;
  - how to roll back.
- Update `docs/STATUS.md` (the "Image updates over adb" row, and what the G14 runs).
- Answer the owner's own question first if they asked one.

## Rolling back

- **Before the reboot:** `scripts/g14-adb.sh ota-cancel`.
- **A slot that never reaches Android:** systemd-boot gives it 3 tries, then starts the previous slot by itself. A panic restarts on its own (`panic=` on the command line); a hang needs the power button held for 10 s.
  - The firmware writes the counter: the G14's first boot of a new slot renames `+3` to `+2-1`.
  - To pick a slot by hand: hold a key at power-on and choose "OpenBook (17 · slot A/B)".
- **Once the new slot has booted,** `markBootSuccessful` makes it good and update_engine merges. The old slot is gone. Going back means building the old tree and sending it as a new update.

## Pitfalls already paid for

- **The first update onto an image without bootsync** needs the package's bootsync once, as root. The new image's `postinstall` cannot write the ESP under the old image's SELinux policy. `ota` does this by itself. The G14 has bootsync since 2026-10-18, so this no longer happens there.
- **`update_engine_client --follow` never exits while idle.** Wrap it in `timeout` and `; true` under `set -o pipefail`.
- **`adb root` restarts adbd.** Reconnect after it (`connect` in `g14-adb.sh` does). `capture` and `state` go back to `unroot` at the end.
- **QEMU runs in the `openbook-installer` container.** Its writable mounts are `<data>/installer` and `<data>/logs/installer` only. adb reaches the VM through `OPENBOOK_INSTALLER_NET=host`, at `127.0.0.1:<port>`, using a separate adb server (port 5223).
- **`cp --reflink` and `--sparse=always` are mutually exclusive.** The disks are 128 GiB sparse files; use reflinks.
- **The serial console interleaves kernel messages** until `dmesg -n 1`. Match markers without a trailing newline.
- **Not supported yet:** installs alongside another OS (XBOOTLDR, bootsync refuses them), and a bring-your-own GApps `product` (a full package brings the stock one back).
- **Test keys:** the payload is signed with AOSP's test key, which `/system/etc/security/otacerts.zip` holds. Release keys must come before any public update. Until `ro.adb.secure=1` (the owner's decision), anyone on the laptop's Wi-Fi can do all of the above.
