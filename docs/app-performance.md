# Per-app performance (translation, compilation, start-up, CPU)

`scripts/perf/app-perf.sh` measures one app of an OpenBook laptop over adb, the same way every time. It answers
four questions for that app:

- Does its native code run translated?
- Is its code compiled?
- How long do its process-cold and warm starts take?
- Where does its CPU time go?

Frames and the GPU path are measured by `scripts/gpu-diag.sh` ([`gpu-diagnostics.md`](gpu-diagnostics.md)). It
finds the app's own SurfaceFlinger layers, so it also covers games that draw without HWUI. This tool was written for
ANAL-378.

Results stay out of this repository. Keep run folders in the evidence store and put a summary on the issue
(CONTRIBUTING.md).

## Commands

```bash
scripts/perf/app-perf.sh state OUT                       # the device and its power settings
scripts/perf/app-perf.sh inventory OUT [PKG...]          # default: every third-party app
scripts/perf/app-perf.sh start OUT PKG [--runs 5] [--warm-runs 5]
scripts/perf/app-perf.sh start OUT PKG --fixed-performance          # one power setting changed for this run
scripts/perf/app-perf.sh start OUT PKG --platform-profile performance
scripts/perf/app-perf.sh cpu OUT PKG [--seconds 20]
scripts/perf/app-perf.sh cpu OUT PKG --translator           # plus Digitalis's own profile (an image with ANAL-383)
scripts/perf/app-perf.sh start|cpu OUT PKG --pcache on|verify|off   # Digitalis's translation cache for this run
scripts/perf/app-perf.sh dexopt OUT PKG --filter speed --yes        # recompiles one app; it can't be undone exactly
scripts/perf/app-perf.sh table RUN_DIR...                # a Markdown table of runs
scripts/perf/app-perf.sh restore                         # after a failed restore: put the power setting back
```

`-a ADDR[:PORT]` (or `OPENBOOK_G14_ADDR`) picks the G14, as with `g14-adb.sh`. Each command then holds the G14 lock
for as long as it runs. `-s SERIAL` runs against another device on the same adb server, such as a test VM. That takes
no lock, and the gate asks for no idle minutes. `start` and `cpu` take `--component PKG/ACTIVITY` and repeated
`--extra ARG` for the `am start` arguments a benchmark needs. Each run writes `run.json` and its raw outputs to OUT,
and OUT must not exist yet.

## Rules every run follows

- **Gate:** the same as gpu-diag's. A run needs:
  - no input for `--idle-min` minutes (10 on the G14);
  - the display awake;
  - no lock screen;
  - no audio playing;
  - the app not running.

  The gate keeps the activity token it saw. Any input after that stops the run (exit 3), and its numbers don't count.
  The tool never injects input. It sends the app to the background by starting the launcher, so the token stays
  valid.
- **Owner apps and data:**
  - nothing is installed, uninstalled or cleared;
  - the app is force-stopped at the end, which is how it was before the run.

  An app that was already running is refused rather than restarted.
- **Power settings:** `start` changes at most one, for the length of the run:
  - `--fixed-performance` turns on Android's fixed performance mode. The power HAL then sets the EPP to
    `performance`.
  - `--platform-profile` writes the ACPI platform profile as root. On ASUS laptops this is the same setting as the
    Fn+F5 key.

  The value from before the run is journalled on the host, then put back at the end, after a failure and on a signal.
  The tool reads it back to check. If the restore fails, the journal stays and the exit status is 4. Every other
  command then refuses to run until `restore` succeeds.
  The journal is tied to the laptop by a hash of its serial number, boot partition UUID and Android ID, never by its
  network address. `restore` writes nothing to a device that doesn't match, and keeps the journal. `restore` needs
  nothing a run left behind: it reads the EPP and the profile itself, and any value it can't read counts as a
  failure, not a match.
  Android has no getter for fixed performance mode, so "off" is assumed beforehand. Nothing in OpenBook turns it on.
  The restore checks that the EPP values match what they were before the run.
- **Verified, not assumed:** each launch samples every policy's EPP and the highest current frequency while
  `am start` runs. That shows what the CPU was actually asked for. The power HAL rewrites the EPP on its own: it sets
  `performance` during a launch and goes back to its base value afterwards.

## What each command reports

### state

- Build fingerprint, slot, and whether the system is installed or a live stick.
- Kernel.
- gpu-diag's conditions: power source, battery, brightness, refresh rate, platform profile and thermals.
- For each cpufreq policy: driver, governor, EPP and frequencies.
- For each CPU: amd-pstate's preferred-core ranking and top frequency. These group the HX 370's two core types by
  their top frequency, which is a fact, not a guess about the core type.
- Memory and swap.
- The ART, dexopt, native-bridge and graphics properties.

### inventory

For each app:

- **Version and installer.**
- **`primaryCpuAbi` and installed ABIs.** `primaryCpuAbi` is the ABI the package manager picked. The installed ABIs
  are the ones its installed APK splits carry.
  - "Native code" is `translated (arm64-v8a)`, `x86_64` or `none`.
  - An app's Java and Kotlin always run as x86_64: ART compiles an arm64 app's dex for x86_64
    (`ro.dalvik.vm.isa.arm64=x86_64`). Only the app's `.so` libraries go through the bridge.
  - If the installed set has no x86_64 libraries, the publisher may still offer them in another build or split.
- **Framework hint**, taken from the library names: Flutter, Unity, Unreal, React Native, .NET, Godot, Cocos2d-x, Qt,
  Chromium or Gecko. It's a hint, not proof. "unknown" means the app has native code that matches none of these.
- **ART's compiler filter and reason** for each dex file, from `pm art dump`. Examples are `speed-profile/install`,
  `verify/first-boot`, and `run-from-apk/unknown` (nothing compiled).

### start

- **Process-cold start:** `am start -W -S`. The app's processes are force-stopped first. The page cache and ART's
  compiled code stay, so this is not a cold start from boot.
- **Warm start:** first a process-cold start, then going home, then `am start -W --activity-clear-task`. The process
  stays and its activity is created again.
- Every sample is kept. Each mode reports `TotalTime` as a median with its minimum, maximum and spread. A launch with
  no time (an error, or a task brought to the front) counts as missing, never as zero.

### cpu

- simpleperf records the whole system (`cpu-clock`, 1000 Hz, as root) for `--seconds` after a process-cold launch.
- The report keeps only the app's processes, by pid. The tool sorts each sample into one category:

| Category | What it is |
|---|---|
| `translated` | ARM code that Digitalis translated and is running. simpleperf calls these samples "unknown". The tool finds their address in the process's maps: the memfd named `exec` that Berberis maps over `libberberis_exec_region.so`'s range |
| `translator-compile` | Digitalis translating: decoding, the lite and heavy tiers, register allocation, the assembler |
| `translator-interpret` | Digitalis's interpreter |
| `translator-helpers` | The intrinsics that translated code calls |
| `translator-runtime` | The rest of `libberberis*`: dispatch, the translation cache, guest calls, syscalls and signals |
| `bridge-proxies` | `libberberis_proxy_*`: host code that does the guest's GL, Vulkan, audio and other system library calls |
| `java` | ART, compiled and JIT code |
| `app-native` | The app's own x86_64 libraries |
| `graphics` | GL, Vulkan, EGL, ANGLE, Mesa, HWUI, SwiftShader |
| `system-native` | Other system libraries |
| `kernel` | The kernel |
| `unknown` | Samples that can't be placed. They are reported as unknown, never folded into another category |

The groups: `arm_code` is translated plus helpers plus interpret, and is the ARM code running.
`translation_overhead` is compile. `bridge_runtime` is runtime plus proxies.

**How the recording is handled**
- simpleperf runs in the background as root, and the tool knows its exact pid.
- While it records, the tool checks the gate every second and notes every process of the app it sees.
- Input, a signal or a failure stops the recorder first: `SIGINT`, so simpleperf finishes its file, then `TERM`, then
  `KILL`. The tool waits until that pid is gone. Only then are its files removed and adbd unrooted.
- "Gone" means the device answered that the pid no longer exists or is no longer this recorder. A probe that fails
  (wireless adb drops) is retried; if the device still can't answer, the state is unknown, never gone. While the
  recorder runs or its state is unknown, the files and root stay, and the run records why. A later run refuses to
  start a recorder while an earlier one is still writing into the directory, and no clean-up removes the directory
  while one is, or while that can't be checked.

**What the attribution covers**
- The report keeps every process of the app seen during the recording, including any that exited before the end.
- Each process's maps are read when it's first seen and again at the end. A mapping that was created and removed
  between those two reads can't be placed, so its samples count as unknown.
- The method was checked on known workloads: arm64 CoreMark in the compat probe app came out almost all translated,
  and its x86_64 build came out almost all app-native. The results are on ANAL-378.

**Digitalis's own profile (`--translator`, ANAL-383)**

The categories say how much time is translated code or translator. `--translator` says which tier ran that code
and what the translator did. It needs an image with Digitalis patch 6. Its first device run was ANAL-384's VM
rehearsal (2026-11-04): the property access, the `xxd` read of process memory and the map collection work there, for
Chromium's app-zygote renderers too. The G14 run comes with that image.

- **Properties.** As root, before the process-cold launch, the run sets `berberis.stats=1` and
  `berberis.profiling=PKG`. Digitalis reads both when the app's process starts.
  - After the run, both go back to their old values, even when the run stops early.
  - The perf maps that were read (`/data/data/PKG/perf-PID.map`) are removed.
  - Both properties are volatile: if the run is killed before it can put them back, they stay set only until the
    next reboot.
  - `run.json` records what happened.
- **Counters** (`translator.stats`, per pid).
  - **How they're read:** at the end of the recording, while the app still runs, straight from each process's memory
    (`xxd` on `/proc/PID/mem`, as root). The block's own header (`OBSTAT2`) and names are checked.
  - **Where the block is** (`address_from`): the address Digitalis logs when the process starts, if that line is
    still in the log; otherwise the block is found in `libberberis_arm64.so`'s writable data, where it lives. On a
    device the line is usually gone by the end of a recording: Digitalis also logs a debug line every 100
    translations, and Chromium's start-up lines were out of the 256 KiB main log within 20 s (ANAL-384's VM run,
    2026-11-04). A process forked from a zygote never logs one.
  - **No thread is involved:** Android won't fork a zygote that has one, and app zygotes initialize the native
    bridge too.
  - **What they count:**
    - regions **installed** per tier, meaning published in the translation cache;
    - results **discarded** because the region was invalidated while it was being translated;
    - the accumulated **elapsed** time (not CPU time) spent compiling per tier, failed and discarded attempts
      included;
    - gear-ups and how each heavy attempt ended (`gearup_heavy` is heavy code emitted; `installed_heavy` is what
      was published);
    - interpreter batches;
    - invalidations, three ways: requests, entries dropped, and dispatcher flushes. A flush makes every other thread
      return to the dispatcher, but discards nothing.
  - **Whose counts they are** (`counts_from`). A forked process inherits its parent's counts, so each pid says:
    - `process start`: the process started the translator itself;
    - `fork from its parent`: a `fork()` child, such as an app zygote's. `since_fork` is its own share (the counters
      minus what it inherited).
    - `inherited from pid N with no baseline`: a guest's raw clone. Its totals include the parent's counts up to the
      fork.
- **Tiers and regions** (`translator.tiers`). Each translated sample's host address is looked up in a perf map. Every
  process writes its own map; a forked child never writes into its parent's.
  - A child also runs code its parent translated before the fork (an app zygote's preload). That code is in the
    parent's map, so the run reads the parent's map too, and the child's own newer entries win.
  - `translator.perf_map_coverage` says per pid what was available: its own map, its parent's, both, or none. An
    isolated process can't write to the app's data directory, so its own regions have no tier profile.
  - Samples land in `lite` or `heavy` (the region's tier), or `unattributed` (no region covers the address: stubs and
    trampolines, or a missing map).
  - **Region names.** Code in a mapped file is named `<library path>@0x<file offset>`. That name stays the same from
    one launch to the next, and between processes (`comparable_across_launches: true`). So two runs can be compared
    region by region, for example to see what is recompiled on every start.
  - Anonymous memory (a guest JIT), memfds and unknown addresses have no stable identity. They're named by pid, guest
    address and size, and marked `false`.
- **What counters don't measure:** how long generated code runs, or its register traffic. Samples do that, and so
  does reading the generated code.
- **Cost.** Profiling costs a little on every region compiled: a maps lookup and a write to the map. So a
  `--translator` run is its own run; don't compare its CPU totals with plain `cpu` runs. ANAL-383 has the host
  measurement for the counters alone (no perf map).

**The translation cache (`--pcache`, Digitalis patch 14, ANAL-381)**
- **What it sets:** `berberis.pcache=MODE:PKG` (or `off` for a control run), as root, before the run's first
  process-cold launch. Only that package's processes, by exact name, use the cache.
- **Putting it back:** the app is force-stopped first and confirmed stopped (a process query that ran to completion
  finds none of its processes), then the property gets back its earlier value. A process left running keeps the
  mode it read at start, so an unconfirmed stop fails the run (`run.json` `pcache_stop`), and so does a failed
  restore (`pcache_restore`); the property is put back either way. It's volatile: a run killed outright leaves it
  set, for that package only, until the next reboot.
- **What `run.json` records:** `pcache` holds the mode, the restore, and the cache left in
  `/data/data/PKG/code_cache/berberis` (files and bytes). With `--translator`, the counters include the cache's
  (`pcache_*`), with the time they were read. `pcache_records_queued` − `_written` − `_dropped` estimates what was
  waiting to be written: the counters aren't read as one snapshot, and the app keeps running (and may flush) until
  it's stopped later, so it isn't the number the stop lost.
- **Each launch reads the cache the previous one left.** A first-write measurement needs the cache cleared just
  before it: `arm-corpus.sh pcache-clear OUT ID`, for this tool's own test installs only. It removes nothing unless
  a process query that succeeded, made again after adbd restarts as root, finds none of the app's processes, and the
  listing of the cache ran without a failure and accounts for every entry. Within one `start`, the
  first cold launch writes and the later ones reuse, and a `cpu` after a `start` is a reuse. Use `--warm-runs 0` for
  cold-start trials.

### dexopt

`dexopt` compiles one package with `pm compile -m FILTER -f -v`:

- It records `pm art dump` before and after, and the compiler's verbose output.
- The result is what ART reports afterwards, not the command's success. For example, `speed-profile` with no usable
  profile gives `verify`.
- Compilation changes derived state that can't be put back exactly. Don't clear profiles to recreate a baseline.
  That's why it needs `--yes`.
- One result answers for that app only. It doesn't speak for every fresh install.

### table

`table` writes one row per app build, label and power setting.
- **Build** means the package, its version code and its installed ABI, all taken from each run's own record. An
  app updated between runs gets a second row. That includes the same version as another ABI, such as an ARM build
  replaced by its x86_64 build.
- **The inventory** adds its framework hint and ART state only to rows of the build it saw. It never relabels
  measurements of another build.
- **Skipped runs:** runs that aren't `ok`, or are incomplete, are skipped and named on stderr.

## Method for one slow app

1. Run `state`, then `inventory`. Both are read-only. They record the power settings and the dexopt state.
2. **Baseline:** run `start`, then `cpu`, then `gpu-diag.sh run` for frames. Each has its own label and a fixed
   duration. These measure the scenario that was reported as slow.
3. **One change at a time:** `start --fixed-performance`, then `start --platform-profile performance`, and then,
   if the app isn't compiled, `dexopt` and `start` again. Each is compared with the baseline on the same method.
4. Run `table` over the run folders, and attach the folders to the issue.
