# Debugging the installed G14 over the network (adb)

Since 2026-10-18 the G14 runs OpenBook from its own NVMe disk (whole-disk install, build `CP2A.260605.016 eng.builde`, userdebug). Since 23:24Z that day it runs slot B, updated over adb (§7). From now on, logs and checks come from the build host over the LAN with adb, not from the stick's "save logs" boot. The stick is still the tool for boots that never get as far as Wi-Fi (§6).

Tool: `scripts/g14-adb.sh`. Evidence for everything below: `evidence/2026-10-18-g14-installed-adb/` (ANAL-222).

## 1. What the installed G14 does with adb (observed 2026-10-18)

| Fact | Detail | Evidence |
|---|---|---|
| **No USB path** | The G14 has no USB device-mode controller: `/sys/class/udc` is empty, there is no `/dev/usb-ffs/adb`, and all four USB controllers are xHCI hosts. The USB4 router (`67:00.5`) has no driver. A cable between the G14 and the build host carries nothing, and the build host has no USB4 controller for USB4 networking either | `adb-facts.txt` |
| **adb runs over IP** | With no USB gadget, `adbd` listens on **tcp:5555** whenever it runs (its default when USB is unavailable). With Wireless debugging on, it also listens on a random TLS port. mDNS advertises both as "OpenBook on ROG Zephyrus G14 (GA403WR)" (`_adb._tcp`, `_adb-tls-connect._tcp`) | `adb-facts.txt`, `scripts/g14-adb.sh find` |
| **No authorization (security)** | userdebug, `ro.adb.secure` unset, and verified boot `orange` make adbd log `authentication not required`. `/data/misc/adb/adb_keys` holds 0 keys, and `adb root` works over the network. **Anyone on the same network gets a root shell** (§5) | `adb-facts.txt`, `adb-toggles-previous-boot.txt` |
| **Survives a reboot** | After the owner's reboot at 16:02:09Z, Wi-Fi connected at 11.0 s, before anyone unlocked, and port 5555 answered by about 12 s. The desktop was up at 7.7 s (from the stick: about 30 s) | `boot-timeline.txt` |
| **"USB debugging" keeps adbd running** | The build sets `persist.sys.usb.config=adb`. With Developer options > USB debugging on, init starts adbd at every boot, and with it port 5555. Turning USB debugging off while Wireless debugging is on still leaves 5555 open without authorization. Turning both off stops adbd | `adb-toggles-previous-boot.txt` |
| **Switches restart adbd** | Each USB or Wireless debugging change kills or restarts adbd, and so does `adb root`. A connected host then sees `device offline` until it disconnects and connects again. `g14-adb.sh` does that by itself (5 tries). The TLS port changes with each restart; 5555 does not | same |
| **Persistent logs can be lost** | The product turns on `persist.logd.logpersistd=logcatd` (16 files, `device/anybook/common/pc/pc.mk`). Setting Developer options > "Store logger data persistently on device" to Off overrides this **and deletes `/data/misc/logd`**. That happened at 15:56:51Z; turn logging back on with `g14-adb.sh persist-logs on` | same; `adb-facts.txt` |
| **The logcat ring buffers are small** | 256 KiB each. By 2 minutes after boot the early `main` lines (AdbService, Wi-Fi connect) had already rotated out, while the `events` buffer still held the boot timings. For anything about boot, use the persisted logs | `boot-timeline.txt` |
| **Full kernel log** | `log_buf_len=1M`: `dmesg` starts at 0 s (in Cuttlefish it lost the first ~3 s). logd also copies it to logcat's `kernel` buffer | `adb-facts.txt` |
| **No panic log** | `/sys/fs/pstore` is mounted but empty, and no pstore backend is set up (ramoops or efi-pstore). A kernel panic leaves nothing to read on the next boot | `adb-facts.txt` |
| **Wi-Fi power save is on** | Ping from the build host: 2–320 ms. This is harmless for adb, but large pulls are slower | `adb-facts.txt` |

## 2. One-time setup on the G14

1. Developer options (Settings > About > tap Build number 7 times, if it is not on yet): **USB debugging on.** On this laptop that switch is what starts adbd at every boot (§1), even though there is no USB port it applies to.
2. **Wireless debugging** is optional today. It is needed only to pair once adbd asks for authorization (§5).
3. **Leave "Store logger data persistently on device" alone.** Setting it to Off deletes the saved logs. If it was changed, run `scripts/g14-adb.sh persist-logs on`.
4. Use a network you trust (§5).

## 3. Commands (build host)

```bash
scripts/g14-adb.sh find                       # OpenBook devices on the LAN that advertise adb (no others)
scripts/g14-adb.sh connect                    # build, uptime, SELinux, adbd uid, the debugging switches
export OPENBOOK_G14_ADDR=192.168.50.11        # optional; otherwise found by mDNS
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

Everything runs through a private adb server (`ANDROID_ADB_SERVER_PORT`, default 5222), so other runs' servers and devices are untouched. `find` and the default address only ever match "OpenBook on ..." advertisements.

**What `capture` saves** (default `<data dir>/installer/g14/adb-<UTC>/`): the same files as the stick's "save logs" entry, made by the same commands.
- `collect-final.txt` comes from the `COLLECT` script, which is read out of `scripts/installer/live-init.c` at run time by `scripts/installer/live-init-script.py`, so the two cannot drift.
- `logcat-final.txt`, `dmesg.txt` and `screen-final.png`.
- `prior-boots.txt` and `prior-boots.tar.gz`, unpacked into `prior/`: earlier boots' persisted logcat (with the kernel log), tombstones, ANR traces and dropbox.
- `summary.json` (`"source": "adb"`), plus `hwtest-final.txt` with `--hwtest`.
- It then writes `report.md`/`report.json` (`live-report.py --expect g14`) and `avc.md`/`avc.json` (`avc-summary.py`, which counts the adb session's own `shell`/`su` denials as the helper's).

`data_on_stick` reads "yes" because it checks that `/data` is f2fs and sized; on the installed system that `/data` is on the NVMe disk.

**Side effects on the G14:**
- `capture` restarts adbd as root and back (`adb root`/`adb unroot`).
- It mounts debugfs for the amdgpu firmware versions, as the stick does.
- It writes, and then removes, its scripts in `/data/local/tmp/openbook-adb/`.
- `--hwtest` may turn Wi-Fi and Bluetooth on. Its speaker tone stays off unless `OPENBOOK_HWTEST_TONE=1`.
- `persist-logs on|off` changes the logpersist properties and closes the Settings app so it reloads them.
- Nothing here reboots, remounts, flashes or changes a partition.

## 4. From the stick method to the network method

| Before (live stick) | Now (installed G14 over adb) |
|---|---|
| Boot the "save logs" entry, wait, move the stick to the host, then `read-stick-logs.sh` | `g14-adb.sh capture`: 35 s, with no reboot and no stick |
| `openbook/hwtest.conf` on the stick plus a "save logs" boot | `capture --hwtest`, with `OPENBOOK_HWTEST_*` set in the host environment |
| The earlier boots' logs in `prior/`, from the stick's `/data` | The same `prior/`, from the G14's `/data`. This needs persistent logging on (§2) |
| A boot that shows nothing: its logs, read on the next "save logs" boot | Its logs, read by `capture` on the next good boot (`prior/misc/logd`), as long as it reached `/data` and logd |
| Add-on checks (graphics, ARM apps, power) through `androidboot.openbook.addon=` | Not scripted yet. The add-ons' `run.sh` can be pushed and run over adb (next step) |
| An owner photo of the screen | `adb exec-out screencap -p`, at the panel's own resolution (2880×1800) |

## 5. Security: unauthenticated root adb

**Today**, anyone who can reach the G14 on port 5555 gets a shell, and with `adb root` a root shell, with no prompt on the laptop. This holds for every network the laptop joins while USB debugging is on, including public Wi-Fi. Wireless debugging's own "trusted network" check does not protect port 5555.

**Now, without a rebuild:** turn USB debugging and Wireless debugging off before joining a network you don't trust. adbd then stops (§1).

**Recommended for the image (owner decision):** set `ro.adb.secure=1` in the G14 product (`device/anybook/g14/anybook_g14_x86_64.mk`, `PRODUCT_SYSTEM_PROPERTIES` or `PRODUCT_PRODUCT_PROPERTIES`). adbd then asks for authorization:
- A new host on port 5555 gets the "Allow debugging?" dialog on the G14 once ("Always allow from this computer" stores its key in `/data/misc/adb/adb_keys`).
- Wireless debugging needs a one-time pairing: `g14-adb.sh pair HOST:PORT` with the code from "Pair device with pairing code".
- `adb root` keeps working for authorized hosts on userdebug.

The G14's QEMU tests use the serial console, not adb, so they are unaffected. Cuttlefish uses its own product. This takes effect on the next image the owner installs.

## 6. Limits and next steps

- **New builds reach the laptop over adb since ANAL-223 (§7).** The G14 runs slot B with `openbook-ota-20261018-cand1` since 2026-10-18 23:24Z.
- **A boot that never reaches Wi-Fi** (black screen, early hang, kernel panic) cannot be reached over adb.
  - If it got as far as logd, its logcat and kernel log are in `/data/misc/logd` and the next good boot's `capture` reads them.
  - A panic leaves nothing until a pstore backend is configured (follow-up).
  - The stick boots its own system and cannot read the installed system's encrypted `/data`.
- **Debugging Wi-Fi over Wi-Fi** drops the link whenever Wi-Fi goes down. A wired path would be a USB-Ethernet adapter on the G14:
  - The GKI already ships `r8152`, `ax88179_178a`, `cdc_ether`, `cdc_ncm` and `usbnet` in `system_dlkm`, and Android's EthernetTracker is enabled for `(usb|eth)\d+`.
  - But none of these modules is loaded at boot.
  - Hypothesis, untested: loading them in the G14 product gives adb over a cable.
- **Add-on checks over adb:** push and run the graphics, ARM apps and power checks' `run.sh`, and feed their output to the existing reports.
- **Larger logcat buffers** (Developer options > Logger buffer sizes, or `persist.logd.size`) would keep boot lines in the live buffers. The persisted logs already keep them.

## 7. Updating the installed system (A/B image updates over adb, ANAL-223)

A new build reaches the laptop as a full A/B update. update_engine writes the slot that is not running, and `/data` (apps, settings, files, the PIN) is kept. The running slot stays the fallback until the new one has booted. How it works: `docs/installer.md` §2.5. Results: §13.13 and `evidence/2026-10-18-ota/`.

**Each update writes the laptop's disk** (the other slot, the copy-on-write data in `/data`, the ESP's loader entry), so it needs the owner's go for that device.

**For agents:** the skill `openbook-g14-update` (`.claude/skills/openbook-g14-update/SKILL.md`, also a Multica workspace skill) is this procedure step by step: the gates, the build, the QEMU rehearsal from the laptop's current state, the laptop step with its idle rule, the after-checks, the evidence and the report.

```bash
# on the build host, after the product build (with the target-files-package and otatools-package goals)
scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug \
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

**During the update:** the laptop stays usable. Progress shows as `DOWNLOADING n%` (the write), then `VERIFYING` and `FINALIZING`. On the G14 the first package (895 MB) took 82 s over Wi-Fi.

**After the reboot:**
- `ota-status` should show:
  - the new slot;
  - `openbook-<slot>.conf (good)`;
  - `update_engine: UPDATE_STATUS_IDLE` and `Update state: none` (the merge is done, usually within a minute).
- From the merge on, the old slot is no longer a fallback.

**If the new slot does not start:**
- It gets 3 tries. Each failed start that ends in a restart counts one: a kernel panic restarts by itself; for a hang, hold the power button for 10 s.
- After the third, systemd-boot starts the old slot by itself, with `/data` as it was.
- To choose by hand, hold a key while powering on and pick "OpenBook (17 · slot A/B)".
- Before rebooting, `ota-cancel` undoes a staged update.

**The first update onto an older image** (one without `openbook-bootsync`, such as `anal192e`) runs the package's own bootsync once as root over adb. This is userdebug only. From then on the image's boot HAL does that step.

**Security:**
- The image and the payload are signed with AOSP's public test keys, so the signature proves nothing to an attacker.
- With adb open to the network (§5), anyone on the same Wi-Fi could push an update.
- Release keys come before any public update, and `ro.adb.secure=1` is still recommended.
