# Per-app GPU diagnostics (Radeon vs NVIDIA)

`scripts/gpu-diag.sh` measures one app on one GPU of an OpenBook laptop over adb and writes the same files every
time. `scripts/gpu-diag-summary.py` turns those runs into a table. It was written for the G14's Radeon 890M vs RTX
5070 Ti baseline (ANAL-336) and works on any OpenBook device reachable with `scripts/g14-adb.sh`.

Results stay out of this repository. Keep run folders in the evidence store and attach a summary to the issue
(CONTRIBUTING.md).

## Commands

```bash
scripts/gpu-diag.sh idle 10                         # may a run start now? exit 0 yes, 3 no (and why)
scripts/gpu-diag.sh snapshot OUT [PKG...]           # the static part: routing, drivers, dGPU, vkjson
scripts/gpu-diag.sh run OUT PKG --gpu nvidia --warmup 20 --seconds 60 --label "STK: fixed replay, 1382x777"
scripts/gpu-diag.sh run OUT PKG --gpu nvidia --seconds 1800 --label "qualification: …"   # a 30-minute soak
scripts/gpu-diag.sh restore                         # after a failed restore: put back the per-app GPU choice
scripts/gpu-diag.sh reap                            # after a failed clean-up: stop what a run left on the device
scripts/gpu-diag-summary.py RUN_DIR...              # run.json per run, and the table on stdout
```

`OPENBOOK_G14_ADDR` or `-a ADDR[:PORT]` picks the device, as for `g14-adb.sh`. Every command holds the G14 lock
(`scripts/g14-lock.sh`, docs/adb-debug.md) for as long as it runs. `OPENBOOK_G14_OWNER` names the task. A session
of several commands runs whole under `g14-lock.sh run OWNER -- SCRIPT`, so nothing else reaches the G14 between them.

## What one run does

1. **Gate:** no input for `--idle-min` minutes (default 10), the display awake, the lock screen not showing and no
   audio playing. The app must not be running: a user's open session is never touched. AC runs need external
   power. `--battery` runs need the laptop unplugged and at least `--floor` percent charged (default 50). Anything
   else exits 3 without changing anything. The gate records an **activity token**, the display group's
   `lastUserActivityTime`. Every later step compares against it: before the GPU choice; on the device just before
   `am start`, together with "the app isn't running"; and every second of warm-up and measurement. Input at any
   point stops the run before anything more is changed or launched.
2. **Before:** conditions (power, battery, brightness, refresh rate, power profile, display size, temperatures),
   Android's updatable-driver and ANGLE settings and the graphics properties, the APK's SHA-256, the vendor helper's
   dGPU report (driver, power state, NVRM/Xid counts) and the crash records.
3. **GPU choice:** `--gpu radeon|nvidia` sets this app's per-app choice in Android's own lists, the ones OpenBook
   Graphics and Developer options › Graphics Driver Preferences use (`scripts/gpu-diag/choice.sh`).
   - **Journal first.** Before the first write, the app's membership of all three lists (prerelease opt-in, opt-in,
     opt-out) and its position in each go to a journal next to the lock file. Then only this app's entries change.
   - **Every read and write is checked.** The device must report the `settings` command's own exit status. A
     choice that doesn't read back as set stops the run.
   - **Restore** on success, failure and signals puts the original memberships back, at their old positions, and
     reads them back. The journal goes only when the read-back matches, or when it shows the owner changed the
     choice during the run (kept). A partial set or partial restore counts as the run's own, so it is undone.
   - **A failed restore keeps the journal** and makes the exit status 4. The next run won't start until
     `restore` succeeds.
   - **Limit:** an owner who re-picks exactly the run's choice during the run is indistinguishable from the run,
     so it is undone.
4. **Start:** process-cold (`am start -W -S`). Shader caches are not cleared, because that would mean deleting app
   data. Stalls from first-run shader compiles are reported only where they happened on their own.
5. **Warm-up** (`--warmup`, not scored), then **TimeStats cleared** and the **scored interval** (`--seconds`). The
   on-device sampler (`scripts/gpu-diag/device.sh sample`) is three kinds of process, so slow work never delays
   the frame dumps:
   - **the dumper** records SurfaceFlinger's per-layer present timestamps (`dumpsys SurfaceFlinger --latency`)
     for each of the app's layers every `--period` seconds (0.25 s; about 0.3 s with the dumps themselves), and
     nothing else;
   - **the monitor**, once a second, checks the activity token, the app's process, a stall and the watchers, takes
     the load samples (CPU, clocks, battery; GPU values where readable) and refreshes the layer list;
   - **three log watchers** stream the kernel log, the app's own log and ActivityManager's events
     (`logcat -v epoch -T <epoch>`, each line read once). Each covers the phase from its **boundary**: the phase's
     start, or for the measurement the warm-up's end, so nothing between the phases goes unwatched. logd's
     backlog comes first, so a line logged after the boundary but before the reader attached still counts. Lines
     are compared with their fractions of a second: a line at 2000.100 is before a boundary at 2000.900.

   They hand over through small files, each with one writer, written atomically. The dumper stops the run if any
   of them reports a failure, a log stream ends, or the monitor's heartbeat is older than 5 s: lost or stale
   monitoring is never "no errors".
   - **The end** is recorded first (`@end` carries it). The phase passes only once a whole monitor round has begun
     after it, and the log streams have had a second to deliver what was logged up to it. A failure found by then,
     including one from the last sleep before the end, or one a watcher reports before it is stopped, still
     stops the run.
   - **Clean-up is bounded** (about 3 s) and verified. TERM, then up to 2 s. Then whatever is left is frozen
     (STOP), so nothing can start a new process, and gets KILL. Every process seen once stays tracked, including
     a child whose parent already went. A worker that still won't go makes the phase exit 6 (`@cleanup-failed`).
   - The host's own clean-up then runs `device.sh reap`, which applies the same steps to anything a run left,
     including a dumper whose adb session was cut. Only when it confirms nothing is left are the device files
     deleted. Otherwise a `pending-cleanup` record next to the lock keeps the G14 held: `g14-lock.sh` refuses
     every other session, gpu-diag's own `idle`, `snapshot` and `restore` refuse too (exit 75, nothing touched), and
     the next gpu-diag run reaps first and stops if it can't. `gpu-diag.sh reap` clears it by hand.

   The output is
   written on the device and pulled afterwards, so Wi-Fi traffic stays out of the interval. (Attempt 2 of ANAL-336's
   qualification: with the log reads inside the sampling loop, the G14's large kernel log stretched the dump
   spacing and left 119 gaps.)
   - On Android 17 a `--latency` dump comes from FrameTimeline (`Layer::getFrameStats` →
     `FrameTimeline::generateFrameStats`). It holds the layer's frames among the **last 64 display frames**
     (`kDefaultMaxDisplayFrames`) whose present fence has signalled; pending frames are left out.
   - SurfaceFlinger composes at most one display frame per vsync, so a dump reaches back at least 64 vsyncs: 533 ms
     at 120 Hz.
   - Each dump is timed on the device (`@Le`: its start, its end and dumpsys's exit status). Two dumps' snapshots
     are at most "second dump's end − first dump's start" apart, so that span must stay under 60 vsyncs (64 minus
     4 for frames still pending at either snapshot, and rounding), using the dumps' own vsync periods. The summary
     marks a gap wherever it doesn't, and where a dump is untimed, failed or doesn't parse.
6. **After**, outside the scored interval: TimeStats, `gfxinfo`, the full SurfaceFlinger dump, `dumpsys gpu`, the
   app's window, logcat and the kernel log since the start. The app is force-stopped, then after `--settle`
   seconds the dGPU report, conditions and crash records are taken again.
7. **Stops at once** (exit 3, the run is invalid) when someone touches the laptop, because the activity token
   changes, and on INT, TERM or HUP. During warm-up and measurement it also stops on:
   - a new kernel GPU error line: an NVIDIA Xid or NVRM error, a GPU off the bus, a GSP error, an amdgpu ring
     timeout or reset (streamed; lines from before the phase's boundary are ignored);
   - a new error in the app's own processes (by uid): a device-lost, context loss, Java crash or fatal signal; or
     an ANR or crash ActivityManager records for the app (streamed);
   - a log stream ending, or the monitor's heartbeat going stale (5 s);
   - the app's process going away (every second);
   - **a hang**: no newly presented frame on any of the app's layers for `--stall` seconds (15). Workloads must
     render continuously.
   - Either way the app is stopped (only if this run launched it) and the choice is restored.
   - The clean-up ignores further signals. `g14-lock.sh` forwards only the first, and holds the lock until the
     session's whole process group is gone, or until `OPENBOOK_G14_LOCK_GRACE` seconds after that signal, when the
     group gets KILL.

   The summary also invalidates a run on:
   - more Xids in the after-report than the before-report;
   - app errors or crash/ANR lines for the app in its logcat;
   - **rendering errors** the app logs: a missing or failed shader, a solid-colour fallback, a GL error, a Vulkan
     error. These are what a rendering failure looks like in the logs; a wrong picture the app doesn't log isn't
     detected automatically.

## What the summary reports, and its limits

| Field | Source | Limit |
|---|---|---|
| GPU seen | GL renderer strings and Vulkan device names from the app's own processes (`Start proc PID:PKG`, child processes such as a browser's GPU process too) | Driver selection and loading lines (`GraphicsEnvironment`, the driver package path, libEGL/vulkan) are kept separately and never count. An app that logs no renderer can't be scored |
| why that GPU | Android's settings, in `GraphicsEnvironment`'s order (as `AppDriver.kt`) | Doesn't decide eligibility (privileged or built-in apps) |
| fps, frame-time p50–p99/max, missed vsyncs, hitches | per-layer present timestamps of the busiest app layer (a game's SurfaceView) | Invalid when two dumps are ≥ 64 vsyncs apart, a dump line doesn't parse, or the frames cover < 90 % of the interval |
| TimeStats | SurfaceFlinger's own count for the scored layer, cleared before the interval and dumped after it (times recorded) | Must agree: no fewer frames than sampled, and no more than the sampled rate explains over its span (+10 %). A missing record or interval makes the run invalid |
| gfxinfo | HWUI's view pipeline | Not a game's surface: kept for View-based apps only |
| app FPS | the workload's own frame-rate lines (`app-logcat.txt`, epoch-stamped, by the app's uid): OpenBook's patched Willems samples ("fps N frames F ms M", tag `vulkanExample`) | Only report windows wholly inside the scored interval count (`@begin`/`@end` carry `epoch=`), aggregated as total frames over total time. The app loop's throughput, which can exceed the display's refresh, not GPU execution time. None when the app logs none. glmark2's per-scene reports are kept as logged (`glmark2_reports`) but not aggregated: their `duration=` is the requested length, not the measured one, and a scene is logged after teardown, so a report can't be placed inside the interval |
| start-up | `am start -W` TotalTime (first activity frame), and the first app-layer frame afterwards (±1 sample) | |
| CPU | `/proc/stat`, and per process (app, SurfaceFlinger, composer) from `/proc/PID/stat` | |
| Radeon load, sclk, temperature, power | amdgpu sysfs and hwmon | "na" when the shell user can't read it, never 0. On the G14's OpenBook build (`ob20261102.2`) the shell user can read none of them: no GPU load or temperature history |
| NVIDIA | the vendor helper's report (`dgpu-report`: driver, power state, NVRM/Xid counts) before and after the run; sysfs `power/runtime_status` during it where readable | On the G14's build the shell user can't read `runtime_status`: no live awake/D3 state, only the before/after reports. `dgpu-report` has no load or temperature. Endpoint reports can't show the load or thermal history, nor prove a workload GPU-bound. Our hwmon reads skip any sensor whose device is NVIDIA (vendor 0x10de) or named nvidia/nouveau; `dumpsys thermalservice` shows the thermal HAL's own sensors (NVIDIA's open driver registers no hwmon) |
| energy | battery runs only: `power_now` integrated, and the charge counter × voltage | Never a battery-percentage delta |
| errors | kernel GPU lines (NVRM Xid/errors, off the bus, GSP, amdgpu ring timeout/reset), the app's own error and rendering-error lines, ActivityManager's ANR/crash lines for the app, new dropbox entries | Any of them, except dropbox entries, makes the run invalid |
| render size | the layer's `sourceCrop` and `displayFrame` (SurfaceFlinger) and the window frame | |

The table groups valid runs by label and GPU seen. Each cell gives the median, then the min–max range, then
every run's value. Invalid runs are listed with the reason.

## The kernel log on a user build

On a `user` build the shell can't read the kernel log: logd carries no kernel buffer, so the sampler's kernel
watcher has nothing to read. The vendor helper (`openbook-pc-setup`, root) can hand over the kernel log's GPU
lines for one run instead, with proof that none is missing (ANAL-402):

```bash
adb shell setprop debug.openbook.klog begin@ID          # before the run; ID: 8 to 32 letters and digits, random
adb logcat -d -s openbook-pc-setup                      # klog: begin id=ID status=ok boot=… seq=SEQ …
# … the run …
adb shell setprop debug.openbook.klog end@ID@SEQ        # after it, with the SEQ that begin answered
adb logcat -d -s openbook-pc-setup                      # klog: line … (one per GPU line), then klog: end … status=…
```

- **How it proves it.** `/dev/kmsg` gives every record a sequence number. `begin` writes a marker record and
  answers with its number. `end` writes a second marker, reads the ring up to it, and checks that record `SEQ` is
  still that run's marker and that every number from it to the end marker was read. Timestamps play no part, so
  records in the same microsecond stay apart.
- **What it hands over.** Every record between the two markers whose text has one of `NVRM`, `nvidia`, `Xid`,
  `GSP`, `fallen off the bus`, `amdgpu`, `nouveau` or `[drm` (`filter=gpu1`): NVIDIA's lines and amdgpu's,
  whichever GPU drew. Each line carries its place (`n=I/SENT`), its sequence number and the record's time.
- **The last line says what the answer is worth.** `status=complete` is the only one that covers a run, and only
  then do zero lines mean no GPU error. `truncated`, `fragmented`, `gap`, `evicted`, `other-boot`, `no-marker`
  and `unreadable` don't; the helper's usage text says what each means. An answer whose last line is missing, or
  with fewer `line`s than `sent=` says, is incomplete too.
- **A line printed in pieces is not certified.** The kernel flags a piece it could not join to its line as a
  continuation fragment (`c`). An error can then be split over two records, neither of which reads as one. The
  helper doesn't join them: with any fragment between the markers the answer is `fragmented`, and the fragments
  are handed over next to the matching lines for a person to read.
- **Every line says whether it arrived whole.** `sum=` is the SHA-256 of the line without that field, and a
  `line`'s `len=` is the length of its text. A reader that finds another sum or length has a line that was
  shortened or changed between the helper and itself, and must not take the answer as complete.
- **It needs no lab switch and changes nothing** but two marker lines in the kernel log. A bugreport already gives
  adb the whole kernel log.

`gpu-diag.sh` doesn't ask for it yet: OpenBook's previews are `userdebug` builds, where the sampler streams the
kernel log itself.

## Method (ANAL-336)

- The workload, scene, seed, render size, quality and frame cap go into `--label`. A run's identity is the image,
  kernel, driver/ANGLE and APK hashes plus `meta.txt`'s tool revision. Don't repeat a run whose identity hasn't
  changed.
- Use 3 scored runs per workload and GPU, alternating the GPU order, with the same warm-up, duration and cooldown.
  Repeat only an invalid run, and record why.
- **The 30-minute app qualification** (ANAL-336's gate) is one `run --seconds 1800` per workload and GPU, under
  the laptop rules. It passes only if:
  - the run is valid;
  - the dGPU report afterwards shows `d3cold` again.

  Its stops cover a new Xid, device-lost, GPU reset or GSP error, crash or ANR, a hang (`--stall`), and logged
  rendering errors. Look at the scene before trusting a timing: a frame the app renders wrong without logging it
  is the one failure the tool can't see.
- Keep AC throughput and battery energy as separate runs. Profile with `simpleperf` only on a bottleneck that has
  been seen, never inside a scored interval.
