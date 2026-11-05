# ARM translation performance: corpus and method

How OpenBook measures what running ARM code through Digitalis costs, so translator changes can be ranked and checked
on the same workloads every time (ANAL-380). The translator is described in [`digitalis.md`](digitalis.md). The
per-app tools this builds on are in [`app-performance.md`](app-performance.md) and
[`gpu-diagnostics.md`](gpu-diagnostics.md).

Results stay out of this repository. Keep run folders in the evidence store, and put the tables on the issue
(CONTRIBUTING.md).

## The corpus

`scripts/perf/arm-corpus.tsv` pins every app by its APK's sha256 and its signer's certificate. Each workload runs
twice, translated and native, with nothing else changed:

- **"fat" APKs** carry every ABI. The same APK is installed with `--abi arm64-v8a` (translated) and with
  `--abi x86_64` (native), so the version and the bytes are identical.
- **Per-ABI builds** of the same version are installed one after the other. Their version codes differ, so the
  second install uses `-d`.

| Workload | Source | Represents | Task |
|---|---|---|---|
| SuperTuxKart 1.5 | GitHub release, fat | native 3D game (C++, GLES) | start-up (its performance test: see below) |
| Godot TPS demo (commit `a82f1544`, Godot 4.7.2) | built by `scripts/perf/workloads/build-tps-demo.sh`, fat | demanding 3D game: Godot's mobile renderer, PBR, robots, particles | `arm-corpus.sh bench`: a fixed 60-second camera path through the level, the engine's own frame times |
| glmark2 (commit `22c527cb`) | built by `scripts/perf/workloads/build-glmark2.sh`, fat | a translated app's GL calls | `-b build:duration=10 --run-forever` under `gpu-diag.sh run`, as ANAL-336 ran it |
| Luanti 5.17.0 | F-Droid, fat | native 3D engine plus Lua | start-up |
| Mindustry 160.7 | F-Droid, fat | Java game on libGDX: only libGDX's `.so` is translated | start-up |
| Lichess 0.30.3 | F-Droid, per ABI | Flutter (Dart AOT) | start-up |
| Jitsi Meet 26.0.0 | F-Droid, per ABI | React Native with Hermes | start-up |
| CoreMark | `scripts/compat/build-probes.sh` | integer CPU | executables, each core type |
| simd-bench | `scripts/perf/simd-bench/` | vector code | executables, each core type |
| Chromium ContentShell | ANAL-378's page/task | JIT-heavy native code | ANAL-378's G14 run, not repeated |

**Deferred, and why:**

- **SuperTuxKart's built-in performance test** (a fixed replay of Black Forest, 1.5 only): it can only be started
  from STK's menu. Injected taps would also update the idle gate's activity token, so an owner's input in the
  seconds around them couldn't be told apart. It isn't run unattended until injected and physical input can be told
  apart (the input dispatcher's device ids are a candidate). Until then, the TPS demo is the demanding game and
  glmark2 the GL call path.
- **Unity (IL2CPP):** there's no Unity build we may use. It is the most common shape of a Play Store game, so it
  is measured once Play is on the laptop.
- **Godot:** the corpus entry is the editor, not a game with a fixed scene.
- **Sustained tasks for Luanti, Mindustry, Lichess and Jitsi:** none of them can run a fixed task without input
  or a server. They are measured for start-up only (process-cold and warm starts, and CPU attribution from launch).
- **Video decoding (VLC with AV1):** VLC prefers Android's MediaCodec, whose decoders run natively. Measuring VLC's
  own NEON decoders needs its hardware decoding turned off first.

### The TPS demo benchmark

`scripts/perf/workloads/tps-demo/bench.gd` is an autoload added to Godot's third-person-shooter demo. The demo is
unchanged except for one line: the player doesn't capture the mouse while the benchmark runs. On the G14 that capture
resets the touchpad and mouse, which Android counts as user activity, so the idle gate stopped every run.

The APK is built with the "Undefined" app category, not "Game": Android caps games at 60 fps by default on this image
(`ro.surface_flinger.game_default_frame_rate_override`), which would hide any difference between the two ABIs. It skips the menu and loads the level, so the player and the robots spawn and run as in a game. Then it
flies its own camera through the level's spawn points at a fixed speed in wall-clock time, so every run follows the
same path at the same speed whatever its frame rate. vsync is off and the frame rate uncapped.

After a 10-second warm-up a 60-second window opens at a frame boundary. Every frame that completes inside it counts.
The frame that crosses its end is reported (`crossing_frame_ms`), not counted, and `window_s` is the time the
counted frames actually cover. On a slow device that is less than 60 s, and the crossing frame shows by how much.
One `OPENBOOK_BENCH result` line gives:
- frames, `window_s` and average FPS;
- frame-time p50, p95, p99 and maximum;
- `engine_process_ms_avg`, the average of Godot's `TIME_PROCESS` monitor: the engine's frame-processing time, not
  CPU time;
- the architecture the engine was built for.

`arm-corpus.sh bench` ties each result to its own launch:
- It clears the log first, and starts nothing if that fails.
- It launches the app with `am start -S` (which ends any earlier instance), then reads the one process that launch
  started. Only lines that logcat recorded for that process and that report the same `pid=` count. A file or an
  intent extra can't carry a token instead: on a fresh install the app's external files directory doesn't exist
  until the app creates it, and Godot drops command-line extras sent to an exported activity.
- The launch itself must succeed, and the engine's architecture must match the installed ABI: arm64 for a
  translated run, x86_64 for a native one.
- At the end of a run, and on input, a timeout, an adb failure or a signal, the app is force-stopped and its
  processes are confirmed gone. Until then the host journal marks it running, and the next command of the tool stops
  it before doing anything else.

The build exports one APK with both ABIs, so the two runs use the same bytes.

### simd-bench

`scripts/perf/simd-bench/simd_bench.c` is one source for both ABIs. Its baseline kernels use clang's 128-bit vector
types, which lower to NEON on arm64 and SSE on x86_64, so both builds do the same work at the same width:

- `triad_f32` (with a scalar copy, `triad_scalar`, as the control);
- `dot_f32` and `dot_i8`;
- `blur_u8`;
- `minmax_f32`;
- `swizzle_u8`, a byte shuffle (TBL on arm64, PSHUFB on x86_64).

Its optional kernels use each architecture's own instructions and run only where the CPU reports them:

- `crc32c`: CRC32CX on arm64, SSE 4.2's CRC32 on x86_64;
- `aes128`: AESE/AESMC on arm64, AES-NI on x86_64.

Every kernel's result is checked against a scalar reference (AES also against FIPS-197's test vector), and the
float kernels are built so that their results are bit-identical on both. `build.sh` builds it with the NDK r30
container and runs `check-isa.py`. That script fails the build unless the disassembly shows that every baseline
kernel uses vector instructions on both ABIs, that the scalar control has no packed float arithmetic, and that the
optional kernels use their AES and CRC instructions.

### mman-bench

`scripts/perf/mman-bench/mman_bench.c` times a JIT engine's address-space pattern (ANAL-379). Each iteration:
- reserves a never-executable range (`mmap` with `PROT_NONE` and `MAP_NORESERVE`; 4 GiB by default);
- commits and decommits 256 KiB pieces of it (`mprotect` read-write, touch one page, `mprotect` back to `PROT_NONE`;
  32 by default);
- releases it (`munmap`).

Natively this measures the kernel alone. Translated, it also measures the translator's bookkeeping of which guest
pages are executable. It prints one JSON line: the median of 5 batches per iteration and per call.
`build.sh` builds both ABIs in the same NDK container as simd-bench.

```bash
scripts/perf/mman-bench/build.sh
# on the build host, through the host runner (as for simd-bench):
LD_LIBRARY_PATH=<variant>:$OUT/lib64 taskset -c 15 <variant>/berberis_program_runner_arm64 \
  ~/anybook/perf/mman-bench/mman-bench-arm64-static [iterations] [reserve_mib] [commits]
```

## Matching the two runs

- **The ABI is checked, not assumed.** `install` reads `primaryCpuAbi` back and fails if it isn't the ABI asked
  for. Translated execution is then shown directly:
  - for apps, `app-perf.sh cpu`'s translated-code share;
  - for executables, an aarch64 binary running on an x86_64 CPU (simd-bench also prints the architecture it was
    built for).

  `libberberis_arm64.so` being mapped proves nothing: it is mapped in native processes too.
- **The same app state:**
  - The app is installed once per ABI with `install -r`, so its data, settings and first-run state carry over.
  - One untimed first start follows each install.
  - Every runtime permission the test package hasn't been granted is left denied and marked user-fixed at install,
    so no permission prompt sits on top of its process-cold starts.
  - ART's state is recorded with `app-perf.sh inventory`. The Java code is compiled for x86_64 under either ABI.
- **The same graphics settings:** the GPU is the per-app default (Radeon), and glmark2's renderer is recorded from
  its log.
- **Order:**
  - Apps run A, B, B, A: translated, native, native, translated, with a reinstall at each switch.
  - Executables alternate the ABI order every round, on each core type.
- **Start-up and sustained work are reported apart:**
  - start-up: process-cold and warm starts, and CPU from launch;
  - sustained: the TPS demo's benchmark, glmark2 and the executables.

  A start-up profile can't rank gameplay: a translated run may still be loading when the native run is already
  playing.

## Ranking bottlenecks

1. **The deficit:** how much slower the translated run is than native on a reproducible measure:
   - start-up time;
   - task time;
   - frame-time tail (gpu-diag's p99).
2. **Breadth:** how many corpus workloads show that deficit.
3. **Attribution:** CPU profiles (`app-perf.sh cpu`, Digitalis's own profiling maps) say where the time goes. They
   explain a deficit; they don't rank one. A CPU share isn't recoverable wall time.
4. **A fix counts** when the same end-to-end measure improves, not only a CPU share. Each fix also needs no
   correctness regression: Digitalis's host tests, the compat harness's ARM corpus, and JIT and self-modifying-code
   coverage.

## Commands

```bash
scripts/perf/arm-corpus.sh list                          # the corpus
scripts/perf/arm-corpus.sh fetch                         # download and check the pinned APKs
scripts/perf/workloads/build-glmark2.sh                  # glmark2-fat.apk
scripts/perf/workloads/build-tps-demo.sh                 # tps-demo-fat.apk (Godot 4.7.2, self-contained)
scripts/perf/simd-bench/build.sh                         # simd-bench for both ABIs, with the ISA check
scripts/compat/build-probes.sh                           # CoreMark executables (if not built yet)

scripts/perf/arm-corpus.sh install OUT stk --abi arm64-v8a
scripts/perf/app-perf.sh start OUT org.supertuxkart.stk  # starts; app-perf.sh cpu for attribution
scripts/perf/arm-corpus.sh install OUT stk --abi x86_64  # the same APK, native, data kept
scripts/gpu-diag.sh run OUT org.linaro.glmark2 --gpu radeon --component org.linaro.glmark2/.Glmark2Activity \
  --extra -e --extra args --extra '-b build:duration=10 --run-forever' --warmup 20 --seconds 60
scripts/perf/arm-corpus.sh install OUT tps --abi arm64-v8a
scripts/perf/arm-corpus.sh bench OUT tps --runs 3        # the TPS demo's benchmark, process-cold each run
scripts/perf/arm-corpus.sh exe OUT --rounds 3            # CoreMark and simd-bench, each core type
scripts/perf/arm-corpus.sh pcache-clear OUT tps         # remove a test install's translation cache (ANAL-381)
scripts/perf/arm-corpus.sh remove OUT                    # uninstall every corpus app this tool installed
```

A G14 session runs whole under `scripts/g14-lock.sh run OWNER -- SCRIPT`, so nothing else reaches the laptop between
these commands. Inside it, each tool takes the lock it already holds.

## Rules every run follows

- **The idle gate:** the same as app-perf's and gpu-diag's (10 minutes without input on the G14, display awake, no
  lock screen, no audio). Input at any later check stops the run. The tool never injects input.
- **Benchmarks stop promptly:** `exe` starts each benchmark in the background and checks the gate every `--poll`
  seconds (2) while it runs. Input, an adb failure, a timeout or a signal stops it:
  - every process whose command line runs one of the tool's executables gets TERM, then KILL, each pid's
    command line checked again right before its signal;
  - the run then waits until none is confirmed left.

  If that can't be confirmed (a lost link, a survivor), the device directory is kept and the run fails. The next
  command's clean-up stops what it finds before removing anything.
- **Owner apps:** only corpus test packages are installed.
  - A package counts as the tool's own only when it is in the host journal for this device and its installed APK's
    sha256 is one the tool installs for it. A journal left stale, by an owner reinstalling the app, doesn't let the
    tool replace or remove the owner's copy: `remove` leaves such a package alone and drops the claim.
  - Every write needs a confirmed answer from the package manager. If adb or pm doesn't answer, nothing is
    installed, replaced or removed.
  - A journal entry is dropped only once its package is confirmed absent.
- **On the device:**
  - Executables go to `/data/local/tmp/openbook-arm-corpus` and are removed at the end.
  - A test package's ungranted runtime permissions are marked user-fixed, and the flags are read back and recorded.
  - No owner setting is changed.

## Testing a translator change

- **In a VM:** host tests, the corpus and correctness coverage, before and after, in the same VM. That decides
  whether a change goes ahead. The improvement is reported as a VM result.
- **Executables on the G14:** a test translator could run from `/data/local/tmp` through
  `berberis_program_runner_arm64`, without touching `/system`. This is not yet shown to work. The runner links
  `libberberis_arm64` dynamically, so it first has to be proven in the VM that the runner loads the candidate
  library: its hash, build ID and the process maps.
- **Apps on the G14:** these need the change in the image, so they wait for an image update B Honey approves.
