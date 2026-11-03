# Debugging the installed G14 over the network (adb)

An installed OpenBook on the G14 is debugged, tested and updated from the build host over the LAN with adb: logs,
checks and new builds go over Wi-Fi, with no stick and no reboot. The live stick's "save logs" boot is still the tool
for boots that never get as far as Wi-Fi (§6), and for testing the installer itself.

Tool: `scripts/g14-adb.sh` (ANAL-222). Image updates over adb: §7 (ANAL-223).

## 1. What the installed G14 does with adb (observed 2026-10-18)

| Fact | Detail |
|---|---|
| **No USB path** | The G14 has no USB device-mode controller: `/sys/class/udc` is empty, there is no `/dev/usb-ffs/adb`, and all four USB controllers are xHCI hosts. The USB4 router (`67:00.5`) has no driver. A cable between the G14 and the build host carries nothing, and the build host has no USB4 controller for USB4 networking either |
| **adb runs over IP** | With no USB gadget, `adbd` listens on **tcp:5555** whenever it runs (its default when USB is unavailable). With Wireless debugging on, it also listens on a random TLS port. mDNS advertises both as "OpenBook on ROG Zephyrus G14 (GA403WR)" (`_adb._tcp`, `_adb-tls-connect._tcp`) |
| **Authorization** | Images built since 2026-10-31 set `ro.adb.secure=1`: a new computer must be allowed on the laptop once. Older userdebug images log `authentication not required`, and `adb root` works over the network for anyone on it (§5) |
| **Survives a reboot** | Wi-Fi connects about 11 s after boot, before anyone unlocks, and port 5555 answers by about 12 s. The desktop is up at about 7.7 s (about 30 s from a stick) |
| **"USB debugging" keeps adbd running** | The build sets `persist.sys.usb.config=adb`, so adb is on by default. With Developer options > USB debugging on, init starts adbd at every boot, and with it port 5555. Turning USB debugging off while Wireless debugging is on still leaves 5555 open. Turning both off stops adbd |
| **Switches restart adbd** | Each USB or Wireless debugging change kills or restarts adbd, and so does `adb root`. A connected host then sees `device offline` until it disconnects and connects again. `g14-adb.sh` does that by itself (5 tries). The TLS port changes with each restart; 5555 does not |
| **Persistent logs can be lost** | The product turns on `persist.logd.logpersistd=logcatd` (16 files, `device/anybook/common/pc/pc.mk`). Setting Developer options > "Store logger data persistently on device" to Off overrides this **and deletes `/data/misc/logd`**. Turn logging back on with `g14-adb.sh persist-logs on` |
| **The logcat ring buffers are small** | 256 KiB each. By 2 minutes after boot the early `main` lines (AdbService, Wi-Fi connect) have rotated out, while the `events` buffer still holds the boot timings. For anything about boot, use the persisted logs |
| **Full kernel log** | `log_buf_len=1M`: `dmesg` starts at 0 s (in Cuttlefish it lost the first ~3 s). logd also copies it to logcat's `kernel` buffer |
| **No panic log** | `/sys/fs/pstore` is mounted but empty, and no pstore backend is set up (ramoops or efi-pstore). A kernel panic leaves nothing to read on the next boot |
| **Wi-Fi power save is on** | Ping from the build host: 2–320 ms. This is harmless for adb, but large pulls are slower |

## 2. One-time setup on the G14

1. Developer options (Settings > About > tap Build number 7 times, if it is not on yet): **USB debugging on.** On this
   laptop that switch is what starts adbd at every boot (§1), even though there is no USB port it applies to.
2. **Allow the build host once.** On images with `ro.adb.secure=1`, the first connection from a new computer shows
   "Allow USB debugging?" on the laptop. Tick "Always allow from this computer"; the key is stored in
   `/data/misc/adb/adb_keys`. `g14-adb.sh` says so when it sees `unauthorized`.
3. **Wireless debugging** is optional. Its TLS port needs a one-time pairing: `g14-adb.sh pair HOST:PORT` with the
   code from "Pair device with pairing code".
4. **Leave "Store logger data persistently on device" alone.** Setting it to Off deletes the saved logs. If it was
   changed, run `scripts/g14-adb.sh persist-logs on`.
5. Use a network you trust (§5).

## 3. Commands (build host)

```bash
scripts/g14-adb.sh find                       # OpenBook devices on the LAN that advertise adb (no others)
scripts/g14-adb.sh connect                    # build, uptime, SELinux, adbd uid, the debugging switches
export OPENBOOK_G14_ADDR=192.0.2.11           # optional; otherwise found by mDNS
scripts/g14-adb.sh capture                    # the "save logs" set from the running system, ~35 s (below)
scripts/g14-adb.sh capture --hwtest           # plus openbook-hwtest: Wi-Fi, Bluetooth, audio, arm64 bridge
OPENBOOK_HWTEST_IPERF3_SERVER=<host> scripts/g14-adb.sh capture --hwtest   # plus iperf3 to a host running iperf3 -s
scripts/g14-adb.sh capture --bugreport        # plus adb bugreport (a few minutes; stays on the host, never commit it)
scripts/g14-adb.sh capture --redact OUT DEST  # plus a masked copy of the text files in OUT (no screen capture)
scripts/g14-adb.sh logcat                     # follow logcat; -b kernel for the kernel log; resumes after a drop
scripts/g14-adb.sh shell                      # interactive shell (adb root first if you need it: adb -s ... root)
scripts/g14-adb.sh wait 600                   # after a reboot: wait until adb answers and the boot completed
scripts/g14-adb.sh persist-logs status|on|off
scripts/g14-adb.sh pair HOST:PORT             # Wireless debugging pairing; asks for the code (only with ro.adb.secure=1)
scripts/g14-adb.sh state OUT.json             # read-only: build, slot, packages, Settings, counts (keep it on the host)
scripts/g14-adb.sh ota PKG.zip [--dry-run]    # an A/B image update of the other slot (§7); ota-status, ota-cancel
```

Everything runs through a private adb server (`ANDROID_ADB_SERVER_PORT`, default 5222), so other runs' servers and
devices are untouched. `find` and the default address only ever match "OpenBook on ..." advertisements.

**One session at a time.** Every command except `find` holds the G14 lock (`scripts/g14-lock.sh`, a host-side
`flock`) while it runs, and stops at once with exit 75 if another task holds it (`OPENBOOK_G14_LOCK_WAIT=SECONDS`
waits instead). A task that drives the G14 for longer than one command holds it for the whole session, so nobody
else's commands land in the middle:

```bash
scripts/g14-lock.sh run ANAL-326 -- ./my-session.sh   # g14-adb.sh and gpu-diag.sh inside it don't lock again
scripts/g14-lock.sh status                            # "free", or who holds it (or a pending gpu-diag clean-up)
```

- **Raw `adb` calls are not covered on their own.** Inside such a session script they are, because the lock lasts
  until every process of the session is gone.
- **The session gets its own process group.** The first INT/TERM/HUP to `g14-lock.sh` reaches all of it as TERM.
  Later signals aren't forwarded, so they can't cut a clean-up short.
- **Clean-up time:** the lock is released once the session's clean-up is done. If that takes longer than
  `OPENBOOK_G14_LOCK_GRACE` seconds (300) after the first signal, the whole group gets KILL, leader included.
- **Daemons that leave the group,** such as the adb server, never hold the lock.

**What `capture` saves** (default `<data dir>/installer/g14/adb-<UTC>/`): the same files as the stick's "save logs"
entry, made by the same commands.
- `collect-final.txt` comes from the `COLLECT` script, which is read out of `scripts/installer/live-init.c` at run
  time by `scripts/installer/live-init-script.py`, so the two cannot drift.
- `logcat-final.txt`, `dmesg.txt` and `screen-final.png`.
- `prior-boots.txt` and `prior-boots.tar.gz`, unpacked into `prior/`: earlier boots' persisted logcat (with the kernel
  log), tombstones, ANR traces and dropbox.
- `summary.json` (`"source": "adb"`), plus `hwtest-final.txt` with `--hwtest`.
- It then writes `report.md`/`report.json` (`live-report.py --expect g14`) and `avc.md`/`avc.json`
  (`avc-summary.py`, which counts the adb session's own `shell`/`su` denials as the helper's).

`data_on_stick` reads "yes" because it checks that `/data` is f2fs and sized; on the installed system that `/data` is
on the NVMe disk.

**Side effects on the G14:**
- `capture` restarts adbd as root and back (`adb root`/`adb unroot`).
- It mounts debugfs for the amdgpu firmware versions, as the stick does.
- It writes, and then removes, its scripts in `/data/local/tmp/openbook-adb/`.
- `--hwtest` may turn Wi-Fi and Bluetooth on. Its speaker tone stays off unless `OPENBOOK_HWTEST_TONE=1`.
- `persist-logs on|off` changes the logpersist properties and closes the Settings app so it reloads them.
- Nothing here reboots, remounts, flashes or changes a partition.

## 4. The network method next to the stick method

| With a live stick | On the installed G14 over adb |
|---|---|
| Boot the "save logs" entry, wait, move the stick to the host, then `read-stick-logs.sh` | `g14-adb.sh capture`: 35 s, with no reboot and no stick |
| `openbook/hwtest.conf` on the stick plus a "save logs" boot | `capture --hwtest`, with `OPENBOOK_HWTEST_*` set in the host environment |
| The earlier boots' logs in `prior/`, from the stick's `/data` | The same `prior/`, from the G14's `/data`. This needs persistent logging on (§2) |
| A boot that shows nothing: its logs, read on the next "save logs" boot | Its logs, read by `capture` on the next good boot (`prior/misc/logd`), as long as it reached `/data` and logd |
| Add-on checks (graphics, ARM apps, power) through `androidboot.openbook.addon=` | Not scripted yet. The add-ons' `run.sh` can be pushed and run over adb (§6) |
| A photo of the screen | `adb exec-out screencap -p`, at the panel's own resolution (2880×1800) |

## 5. Security: unauthenticated root adb

**Fixed in images built from 2026-10-31 (ANAL-320).** `device/anybook/common/pc/pc.mk` sets `ro.adb.secure=1`, and
`scripts/release/make-release.sh` refuses to publish a debuggable image without it (gate `adb_auth`). The first public
image, `0.1.0-preview.1`, shipped without it and was withdrawn the same day; `0.1.0-preview.2` has the fix.

**Why it matters.** A userdebug build leaves `ro.adb.secure` unset, so adbd skips authorization. With no USB device
mode, a PC's adbd listens on tcp:5555, and adb is on by default. On images built before the fix, anyone who can reach
the laptop on port 5555 gets a shell, and with `adb root` a root shell, with no prompt on the laptop. This holds on
every network the laptop joins while USB debugging is on, including public Wi-Fi. Wireless debugging's own "trusted
network" check does not protect port 5555.

**On an older image, without a rebuild:** turn USB debugging and Wireless debugging off before joining a network you
don't trust. adbd then stops (§1).

**With the fix:**
- A new host on port 5555 gets the "Allow USB debugging?" dialog on the laptop once ("Always allow from this computer"
  stores its key in `/data/misc/adb/adb_keys`).
- Wireless debugging needs a one-time pairing (§2).
- `adb root` keeps working for authorized hosts on userdebug.
- The G14's QEMU tests use the serial console, not adb, so they are unaffected. Cuttlefish uses its own product.

## 6. Limits and next steps

- **A boot that never reaches Wi-Fi** (black screen, early hang, kernel panic) cannot be reached over adb.
  - If it got as far as logd, its logcat and kernel log are in `/data/misc/logd` and the next good boot's `capture`
    reads them.
  - A panic leaves nothing until a pstore backend is configured (follow-up).
  - The stick boots its own system and cannot read the installed system's encrypted `/data`.
- **Debugging Wi-Fi over Wi-Fi** drops the link whenever Wi-Fi goes down. A wired path would be a USB-Ethernet adapter
  on the G14:
  - The GKI already ships `r8152`, `ax88179_178a`, `cdc_ether`, `cdc_ncm` and `usbnet` in `system_dlkm`, and Android's
    EthernetTracker is enabled for `(usb|eth)\d+`.
  - But none of these modules is loaded at boot.
  - Hypothesis, untested: loading them in the G14 product gives adb over a cable.
- **Add-on checks over adb:** push and run the graphics, ARM apps and power checks' `run.sh`, and feed their output to
  the existing reports.
- **Larger logcat buffers** (Developer options > Logger buffer sizes, or `persist.logd.size`) would keep boot lines in
  the live buffers. The persisted logs already keep them.

## 7. Updating the installed system (A/B image updates over adb, ANAL-223)

A new build reaches the laptop as a full A/B update. update_engine writes the slot that is not running, and `/data`
(apps, settings, files, the PIN) is kept. The running slot stays the fallback until the new one has booted. How it
works: `docs/installer.md` §2.5. The tools and their tests: `docs/installer.md` §13.13.

**Each update writes the laptop's disk** (the other slot, the copy-on-write data in `/data`, the ESP's loader entry),
so it needs the owner's go for that device.

**For agents:** the Multica workspace skill `openbook-g14-update` is this procedure step by step: the gates, the
build, the QEMU rehearsal from the laptop's current state, the laptop step with its idle rule, the after-checks and
the report.

```bash
# on the build host, after the product build (with the target-files-package and otatools-package goals). Each update
# build needs its own BUILD_NUMBER (it is in the fingerprint; `ota` refuses the running build's, ANAL-225)
BUILD_NUMBER=<date>.<x> scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug \
    droid target-files-package otatools-package && docker wait anybook-aosp-build
scripts/ota/make-ota.sh openbook-ota-<date>-<x>                 # ~1 min: <data dir>/ota/out/<label>.{zip,json,bootsync}
scripts/g14-adb.sh state <file>.json                            # optional: what the update must keep, to compare after
scripts/g14-adb.sh ota <data dir>/ota/out/<label>.zip --dry-run # the checks only
scripts/g14-adb.sh ota <data dir>/ota/out/<label>.zip           # asks for the laptop's address, then ~1.5 min
scripts/g14-adb.sh shell reboot                                 # when the laptop is idle; or the owner restarts it
scripts/g14-adb.sh wait && scripts/g14-adb.sh ota-status        # slot, build, ESP entries, the merge
```

**What `ota` checks before writing anything:**
- the package's sha256 and its bootsync binary against `<label>.json`;
- that it is a full A/B package for `anybook_g14` and not older than the running build;
- virtual A/B, a whole-disk install, and update_engine idle (no merge pending);
- free space in `/data`, and AC power or at least 50 % battery.

**During the update:** the laptop stays usable. Progress shows as `DOWNLOADING n%` (the write), then `VERIFYING` and
`FINALIZING`. On the G14 an 895 MB package took 82 s over Wi-Fi.

**After the reboot:**
- `ota-status` should show:
  - the new slot;
  - `openbook-<slot>.conf (good)`;
  - `update_engine: UPDATE_STATUS_IDLE` and `Update state: none` (the merge is done, usually within a minute).
- From the merge on, the old slot is no longer a fallback.

**If the new slot does not start:**
- It gets 3 tries. Each failed start that ends in a restart counts one: a kernel panic restarts by itself; for a hang,
  hold the power button for 10 s.
- After the third, systemd-boot starts the old slot by itself, with `/data` as it was.
- To choose by hand, hold a key while powering on and pick "OpenBook (17 · slot A/B)".
- Before rebooting, `ota-cancel` undoes a staged update.

**The first update onto an image without `openbook-bootsync`** (built before ANAL-223) runs the package's own
bootsync once as root over adb. This is userdebug only. From then on the image's boot HAL does that step.

**Limits:**
- Only whole-disk installs take updates; bootsync refuses alongside installs (`docs/installer.md` §2.5).
- A Google apps package the user installed is not carried across: a full package brings the stock `product`.

**Security:**
- The image and the payload are signed with AOSP's public test keys, so the signature proves nothing to an attacker.
- On an image without `ro.adb.secure=1` (§5), anyone on the same network could push an update.
- Release keys come before any public update.
