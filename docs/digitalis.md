# Digitalis: Track A's arm64 native bridge (ANAL-181, ANAL-200)

As of 2026-10-18. **CONFIRMED** means we observed it in our own build logs, device logs or test output. **HYPOTHESIS** means a likely explanation we have not proven.

Digitalis (https://github.com/DigitalisX64) is an Apache-2.0 fork of AOSP's Berberis binary translator that adds an arm64 guest. It is the arm64 native bridge of OpenBook's Android 17 build: built from source in our tree, shipped in both products (`anybook_cf_x86_64_pc` and `anybook_g14_x86_64`), with our Android 17 port and three fixes. ANAL-181 chose it (2026-10-16); ANAL-200 ported and fixed it (2026-10-17). The app-by-app matrix is in [`COMPAT-MATRIX.md`](COMPAT-MATRIX.md) and the harness in [`compat-harness.md`](compat-harness.md).

## Status

- **It ships in both products** (CONFIRMED). `device/anybook/common/native-bridge` puts into the image:
  - ABI list `x86_64,arm64-v8a`, `ro.dalvik.vm.native.bridge=libberberis_arm64.so`;
  - binfmt_misc runners for arm64 executables;
  - 57 arm64 guest libraries;
  - 89 files, 30 MB, in `/system` (88 for the bridge, plus our self-check `openbook_bridge_check`).
- **arm64 apps get the Android 17 NDK** (CONFIRMED). The guest libraries come from our Android 17 tree. Every export of the host `libandroid`, `libbinder_ndk`, `libGLESv2` and `libnativewindow` is in the guest library. The only differences left are `__cfi_check` and libEGL's internal C++ symbols, which are not API. (With Android 16 guest libraries, `libandroid` alone lacked 43 exports.)
- **arm64-only apps run** (CONFIRMED, Cuttlefish desktop product, two runs from wiped data with identical outcomes). 15 of the 17 arm64-only entries run, which is 14 of the 16 apps, against 13/16 for libndk_translation on Google's image.
  - AAAAXY crashes the same way natively.
  - Element X fails the same way on both bridges (`JNI_GetCreatedJavaVMs`).
- **Three bugs are fixed** (CONFIRMED, [below](#the-three-bugs)): `MRS` of the ID registers (Tor VPN), bit-exact `FRECPE`/`FRSQRTE`, and `Build.CPU_ABI` for bridged apps (Fennec).
- **Speed** (CONFIRMED numbers, CoreMark arm64 / native x86_64): 0.394 (executable) and 0.399 (in an app) in Cuttlefish; 0.361 and 0.351 on the G14. On Google's emulator image the same bridge gives 0.300 / 0.298 and libndk_translation 0.457 / 0.456, so Digitalis reaches about 65% of libndk_translation's speed in the same VM.
- **Licensing is clean** (CONFIRMED). Everything is built from source. The only prebuilt among the bridge's files is AOSP's own toolchain `libc++.so`, the same library the x86_64 system ships. No Digitalis binary is in the image.
- **On the G14** (CONFIRMED, bare metal, Ryzen AI 9 HX 370): the bridge self-check passes all five verdicts, and the ARM apps check passes all five of its own; the arm64 probe app gives the same results as in Cuttlefish and QEMU ([On the G14](#on-the-g14-bare-metal)). An arm64 app in an enforcing boot is still unobserved.

## Why Digitalis

ANAL-181 recommended it for Track A, with conditions (2026-10-16):
- **It is the only redistributable option.** libndk_translation and libhoudini are proprietary, and upstream AOSP Berberis still has no arm64 guest product on `android17-release` (it has only `enable_riscv64_to_x86_64.mk`: no arm64 decoder, interpreter or translator). Without Digitalis, Track A would have no arm64 support, or only QEMU user mode.
- **Google's libndk_translation is the same framework, closed.** In the Desktop 37 image it reports `ro.berberis.version=16.0.0`, and its crash stacks show `berberis::` frames.
- **Nearly the same app coverage, and more correct in several areas** than libndk_translation ([Comparison](#comparison-with-libndk_translation)).

| Condition | Where it stands |
|---|---|
| Port it to Android 17 (the guest NDK must match the platform) | Done (ANAL-200): built against our Android 17 tree, NDK gap closed |
| Close the regressions that block real apps (Fennec, Tor VPN) and make `FRECPE` bit-exact | Done (ANAL-200) |
| Accept the speed gap or close it | Open: about 65% of libndk_translation in the same VM |
| Plan for bus-factor risk | Open: one maintainer wrote 692 of the fork's 716 commits; the project was about 6 months old in 2026-10 |

## What Digitalis is

| Repo (github.com/DigitalisX64) | Pinned commit | What it is |
|---|---|---|
| `platform_frameworks_libs_binary_translation` | `b6b7fc30` (2026-10-13) | The translator. Replaces AOSP `frameworks/libs/binary_translation` |
| `manifest` | `3969040d` (2026-08-05) | AOSP `android16-qpr2-release` plus `digitalis.xml` |
| `device_generic_goldfish` | `bbc2f1e4` | Stock goldfish plus the `sdk_phone64_x86_64_digitalis` product (8 commits, 4 files) |
| `digitalis` | `11062cb0` (2026-09-23) | Docs, test and benchmark tooling, Docker packaging |
| `sample_hello_digitalis` | `ce9aa116` | 158 Gradle sample apps (test suite; not used by the image build) |

- The translator fork is `android16-qpr2-release` plus 716 commits. It changes 230 files (139 new, 91 modified, 0 deleted; +210,027/−87 lines). Commit authors: utzcoz 692, Artem Smirnov 23, kuloPo 1 (CONFIRMED, checked 2026-10-16).
- Three translation tiers: an interpreter, a "lite" JIT and a "heavy" optimizer.
- App-specific workarounds, which add maintenance risk: Qt plugin-path injection into the guest `environ`; a redirect of `/system/bin/linker64` opens to the guest linker; rewriting of `/proc/self/maps` for linker introspection; in-APK library extraction to `cache/berberis_extract`.
- Operational notes: it logs at debug level on every 100th translation (about 1,200 `trans#` lines per Fennec launch), and `libberberis_arm64.so` stays mapped in x86_64 app processes too, so "the bridge is mapped" says nothing about which ABI ran.

## How it is built

The bridge is part of the normal product build (`scripts/aosp-build.sh`). Nothing is installed by hand.

- **Source:** `aosp/patches/frameworks/libs/binary_translation/IMPORT` replaces AOSP's `frameworks/libs/binary_translation` (android17-release, `1290e88c`) with the Digitalis fork at `b6b7fc30`, fetched from GitHub once, on the host, by `aosp-docker.sh` (`aosp-patches.sh --fetch`). `scripts/aosp-patches.sh` makes the import a reproducible commit on the pin and applies our patches on top. Other branches' runs of `aosp-patches.sh` put the project back on its pin, as they do for any branch's patches.
- **Guest world:** `frameworks/libs/native_bridge_support` (the guest bionic, the NDK stub libraries and the proxy trampolines), bionic and the framework all come from our Android 17 tree. That is what closes the NDK gap: guest and host libraries must come from the same tree.
- **Our patches** (`aosp/patches/frameworks/libs/binary_translation/`):
  1. `libberberis_runtime_library_headers`: the android17-release name and path of the runtime library header, which Android 17's `native_bridge_support` includes.
  2. An unused variable that Android 17's clang (`clang-r584948b`) rejects under `-Werror`.
  3. `MRS` of the ID registers.
  4. Bit-exact `FRECPE`/`FRSQRTE`.
  5. A single-register `TBL`/`TBX` fast path in both tiers (ANAL-380, ANAL-382). Constant byte shuffles compile to a
     one-register `TBL`. Both tiers lowered every `TBL` generically, with a range mask and a merge per table
     register. For one register, `PADDUSB idx, 0x70` then `PSHUFB` is exact: indices 0–15 keep their low nibble
     with bit 7 clear, and 16–255 saturate to bit 7 set, which `PSHUFB` zeroes. `TBX` keeps the old byte where
     `PCMPGTB(0, c)` marks a miss. The 2–4-register forms are unchanged.
  6. Translator counters and a stable region identity (ANAL-383).
     - **Counters:** `berberis.stats=1` turns on process-wide counters (relaxed atomics).
       - They sit in one self-describing block (`OBSTAT2`), whose address is logged at start. Root reads it from
         `/proc/PID/mem`.
       - There's no thread, because the native bridge also runs in app zygotes, and ART won't fork a zygote that
         has one.
       - A `fork()` child becomes the owner of its counts through a `pthread_atfork` handler, with what it
         inherited kept as a baseline. A guest's raw clone runs no handler and keeps its parent as owner.
       - A program run through the binfmt runner logs an `openbook-stats v1` line when it ends (patch 7).
     - **What's counted:**
       - installs per tier (published only) and results discarded at publication;
       - elapsed compile time per tier;
       - gear-ups and how each ended;
       - interpreter batches;
       - invalidation requests (by source), entries invalidated, in-flight translations thrown away, and dispatcher
         flushes.
     - **Off by default:** each counting site then costs one load of a flag.
     - **Perf map:**
       - Each region of a mapped file is now named with its file offset too (`_0x<addr>+<size>@0x<offset>`).
         Anonymous memory gets no offset.
       - The map belongs to one process: a fork or clone child opens its own instead of writing into its
         parent's.
     - `app-perf.sh cpu --translator` collects both ([app-performance.md](app-performance.md)).
  7. The final `openbook-stats v1` line on `exit()` too (ANAL-383). Patch 6 logged it only at the guest's
     `exit_group`, so only `_exit()` logged one; `exit()` and a return from `main` logged none (ANAL-384's VM run).
     - **Why:** the guest bionic's `exit()` is a weak symbol for the native bridge. `native_bridge_support`'s guest
       libc replaces it with one that runs the guest's `__cxa_finalize` and then calls the host's `exit()`
       (`android_api/libc/exit.c`, `native_bridge_exit`). The host's `exit()` ends the process with its own
       `exit_group`, which never goes through the guest syscall path.
     - **Fix:** with counting on, an `atexit` handler logs the line from the host's `exit()`, and `_exit()` still
       logs at the guest's `exit_group`. The logger remembers the last pid that logged:
       - a second call in the same process logs nothing, so a process whose exit paths meet logs one line;
       - a fork, vfork or raw-clone child still logs its own.
       - **Not guaranteed:** if a shared-memory (`CLONE_VM`) child logs between two calls of its parent, the
         parent's second call logs again (the Checker's reproduction, ANAL-383). That takes a parent that logs
         and keeps running, which the exit paths don't do. Exact once-per-process for any interleaving would need
         per-process state.
       - The line's pid comes from the `getpid` syscall, not bionic's cached value.
     - **Executables only, not apps.** An app's `System.exit()` runs `JVM_Exit`, then the framework's exit hook,
       `AndroidRuntime::exit()`, which ends the process with the host's `_exit()` ("VM exiting with result code 0,
       cleanup skipped"). No `atexit` handler runs, so an app logs no final line, before or after this patch
       (ANAL-387, VM, an arm64 test app). `app-perf.sh cpu --translator` reads an app's counters from its memory
       instead, so app profiles don't depend on the line.
     - A process killed by a signal still logs none: its memory block is the only record.
  8. `ClearExecutable` clears the executable-page shadow a word at a time (ANAL-379).
     - **What it fixes:** every guest `mmap`, `mprotect` and `munmap` that isn't executable clears the range's bits in
       the shadow bitmap (one bit per guest page). That was done page by page, writing every byte. A JIT engine
       reserves, protects and releases gigabytes of never-executable address space, so a browser engine spent about
       10% of its CPU there on the G14 with almost nothing to invalidate.
     - **How:** whole shadow bytes are taken eight at a time (64 pages, 256 KiB of guest space, per step), and
       read before written, so untouched shadow pages stay unpopulated. The bits cleared and the invalidation
       requested are unchanged, and a range whose `start + size` overflows is rounded exactly as before.
     - **Host result:** with `scripts/perf/mman-bench` reserving 4 GiB per iteration, 3082 µs → 156 µs (native 138).
     - **New counters:** `clear_executable_calls`, `clear_executable_pages` and `clear_executable_ns`.
  9. Gear-ups skip the heavy backend when their result would be discarded (ANAL-381).
     - **What it fixes:** a hot lite region gears up. The heavy optimizer ran its frontend and then its backend
       (`x86_64::GenCode`, the optimization passes and code generation), and only then did the caller look at the
       outcome. Two outcomes throw the code away: a fully translated region below the minimum size, and a bail with
       no in-region loop. On the G14, 86% of Lichess's heavy attempts were declined as too small.
     - **How:** `HeavyOptimizeParams` gets `skip_codegen_below_instructions` and
       `skip_codegen_if_bailed_without_backedge`, off by default. Gear-up turns them on, so for those two outcomes
       the optimizer returns after the frontend. What's installed is unchanged.
     - **Host result:** heavy-tier compile time fell 18% on CoreMark and 21% on simd-bench, with every gear-up
       outcome and install count identical.
  10. Lite translations can record every absolute operand they embed (ANAL-381, step P1a of
      [`digitalis-translation-cache.md`](digitalis-translation-cache.md)).
      - **Why:** a persistent translation cache has to give a translation another process's addresses. Lite code
        embeds guest PCs, translation-table slots, the main table, the hotness counter, helper and callback
        addresses, entry trampolines and two heap-built tables.
      - **How:**
        - `MachineCode` can keep a `PersistentReloc` per operand. Recording is off unless the cache (patch 12) is
          on; it costs a median 2.4% of lite translation time.
        - The assembler's `Call`, `Jmp` and `Jcc` record their 64-bit targets.
        - `MovqPersistent` and `MovqGuestAddr` always emit the 10-byte `movabs`.
          - **Above 4 GiB** (where Android puts guest code, slots, tables and counters), that's exactly `Movq`'s
            encoding, checked per register.
          - **Below 4 GiB**, a tagged operand is now 10 bytes where `Movq` chose a shorter form, recording or not.
        - `runtime/arm64/relocatable_code` names, re-links and scans translations, for the tests.
      - **Checks:**
        - a pointer scan of installed code, against ranges that include every 16 MiB translation subtable the module
          spans;
        - a translation re-linked from a guest module above 4 GiB into one below it must equal that environment's own;
          - in-process, for the fixtures and the region corpus;
          - in a second process, where the image, heap, tables and entries all move, for the fixtures;
        - leaving out any record kind fails both checks.
      - **Host result:** all 183,699 region starts of a Lichess cold start (the G14 profile) are persistable, with no
        unrecorded pointer and no re-link mismatch. Their total is 73,942,150 host bytes before and after. That's an
        equal aggregate, not a byte comparison of each translation.
  11. Heavy translations record what they embed too, through the optimizer (ANAL-381, step P1b).
      - **Why:** in the heavy tier, guest addresses become MachineIR immediates, and `FoldInsns` combines them with
        other values before they reach the code.
      - **How:**
        - `MachineInsnX86_64` carries the immediate's provenance (a kind and a 32-bit aux) in what was padding, so
          instructions don't grow.
        - The frontend tags ADR/ADRP, literal addresses, the link value, and its heap tables and permutation masks.
        - Folding keeps a record when the result is still the address plus a constant: add, subtract, a mask of at
          most the low 12 bits, and the TBI pair (shift left 8, then back). Any other fold of an address still
          happens, but marks the region not persistable.
        - An address is never narrowed into a 32-bit immediate operand, which only fits below 4 GiB.
      - **Checks:** the patch 10 checks, with 15 heavy fixtures among them, including ADRP+ADD (kept) and EOR and a
        32-bit add on an address (refused).
      - **Host result:** heavy-translating all 183,699 Lichess region starts:
        - 182,912 are persistable (99.6%), with no unrecorded pointer, no relink failure and no re-link mismatch;
        - 785 are refused for an unrepresentable fold;
        - 9 comparisons are inconclusive, because a copy translated differently again (below);
        - the translation benchmark's total is 57,713,707 host bytes for both the base translator and patch 11. That's
          an equal aggregate over comparable runs, not a byte comparison of each region.
      - **Heavy translation time with recording off:** +2.8% in the default host build (5 of 5 rounds), a measured
        regression of that binary.
        - It's layout-sensitive: unchanged with `-falign-functions=64` (median 0.999), and reverting either half of the
          patch also removes it.
        - That doesn't show the patch adds no work, though: provenance is still initialized and checked with recording
          off.
      - **Found on the way:** heavy translation isn't always a function of its input. Re-translated after other work, 3–9
        of the 183,699 regions come out different (no miscompile observed), on the base translator too. Zero-filling
        arena allocations removes it, which points to an uninitialized read (suspected, not yet identified: ANAL-389).
  12. A persistent translation cache, off by default (ANAL-381, step P2 of
      [`digitalis-translation-cache.md`](digitalis-translation-cache.md)).
      - **What:** translations of file-backed guest code are kept in the app's `code_cache/berberis` and installed on a
        later launch instead of being translated again. `berberis.pcache` (`BERBERIS_PCACHE`) is `off` (the default),
        `on` or `verify`. Executables run through the program runner use `BERBERIS_PCACHE_DIR`.
      - **When a record is used:** the design's checks (3.3), in its order: the file header (the translator's build-id
        and settings), the record (CRC32C and bounds), the mapping (executable, and still the mapping the record was
        found through), then the guest bytes, exactly. The record is re-linked into the code pool and published like a
        translation, so an invalidation during the load discards it. A region starts in the tier it ended on.
      - **Mappings:** a registry follows every guest `mmap`, `munmap`, `mprotect` and `mremap`, under a lock held
        around the host call. It attributes an executable file mapping to its ELF image by checking the image's
        program headers against the mappings. The checks, the compare, the install and the publication hold the lock
        shared, so the code can't be unmapped, re-protected or replaced underneath them.
      - **A fix on the way:** an executable mapping replaced by another one (`MAP_FIXED`) now invalidates the old
        code's translations. It kept the shadow's executable bits, so nothing was invalidated before.
      - **Writing:**
        - one writer process per module, by `flock` on a lock file;
        - records are appended to a data file, with an index file;
        - a translating thread flushes at 1 MiB, or 2 s after the last flush, and so do exit and the guest's
          `exit_group`. No thread is started;
        - 128 MiB per app, checked against the cache directory's size at each flush, so other processes' files
          count. Processes flushing at the same moment can each still go over by one batch;
        - a fork child, from the host's `fork()` or the guest's raw clone, stops using the cache without taking a
          lock, and closes its copies of the lock fds.
      - **`verify`:** a record is installed only if it equals a fresh translation, code and recovery points, re-linked
        to one address. Otherwise the fresh code is installed, and a second fresh translation tells a mismatch (the
        two agree) from inconclusive. Both fresh translations read guest memory, so they run under the mapping lock
        too, held from the checks until the chosen code is published.
      - **Counters:** `pcache_*` (hits, misses, rejects by reason, load and write time, records and bytes written,
        `verify` results). Loaded regions are `lite_cached` and `heavy_cached` in the perf map. The final stats line
        outgrew its buffer and the host's 1,024-byte log limit, so it's longer, and on the host it goes to stderr
        directly.
      - **Host results** (2026-11-05):
        - **Lichess's 183,699 region starts**, mapped from their files at a new address each launch:
          - **lite, with a 1 GiB measurement cap** so every region is stored: 7.2 µs per region to translate,
            3.45 µs to load;
          - **lite at the default 128 MiB cap:** 148,217 regions are stored and 35,482 miss, and a launch
            averages 4.2 µs per region;
          - **every region geared up, 1 GiB cap:** 53 µs to translate, 3.6 µs to load. The loaded set is
            163,057 lite regions (settled, or still counting) and 20,642 heavy ones;
          - writing adds 14% to lite translation time, and 3% with the gear-ups.
        - **`verify`:**
          - every loaded lite region matched (183,699);
          - in the geared-up run, 183,696 matched, 2 were inconclusive and 1 was a mismatch, a heavy region in
            `linker64`. Replayed alone, in a replay that writes its own cache, it matched 3 times out of 3. That
            suggests heavy output that depends on what was translated before (ANAL-389), but doesn't prove the
            original record was sound. Fresh code was installed for all three.
        - **CoreMark through the runner, in separate processes:**
          - the second launch loaded 1,392 regions and translated 6;
          - translator time fell from 28.5 ms to 5.3 ms, and wall time from 99 ms to 75 ms (medians of 5);
          - the first launch cost 8% more lite translation time (one run) and 0.2 ms of writing.
        - **Storage:** a lite record averages 920 bytes with its index entry, for 402 bytes of code. Lichess's lite
          set is 169 MB, so the 128 MiB cap holds 81% of it.
      - **Not yet:** device measurement (P3), and the default and trust model (P4).
  13. A compact record format for the translation cache (ANAL-381, step P2b).
      - **Why:** a Lichess lite record averaged 920 bytes for 402 bytes of code. The 24-byte relocation entries were
        41% of the cache, which put the app's lite set at 169 MB, over the 128 MiB cap.
      - **Format 2:**
        - varints and unpadded bytes after a 16-byte prefix;
        - operands as offset deltas with a tag byte, guest addresses relative to the region's;
        - recovery points as deltas;
        - 24-byte index entries with 32-bit offsets. A record past 4 GiB isn't written, rather than narrowed.
      - **Decoding fails closed:**
        - canonical, length-limited varints and checked arithmetic;
        - every bound and combination checked, and no trailing bytes;
        - counts bounded before anything grows;
        - guest addresses must lie in the module, and an image offset in the translator image.

        Format-1 files fail the header check, and their writer replaces them.
      - **The cap** is now described as best effort: a flush can write several modules' batches, and 1 MiB is when a
        flush starts, not a limit on it.
      - **Found on the way:** libc++'s range `insert` measured about 2 µs a record in the host build, so records are
        copied with `memcpy`. That also halved loading against patch 12.
      - **Host results** (2026-11-05, Lichess's 183,699 region starts):
        - **lite, default 128 MiB cap:** all 183,699 regions stored in 100.3 MB instead of 169 MB. Loading takes
          1.67 µs a region (patch 12: 3.45 µs, at its 1 GiB measurement cap). Writing adds 15% to lite translation
          time, and `verify` matched every region;
        - **every region geared up:**
          - 1 GiB cap: 202 MB instead of 339 MB, and loading takes 1.8 µs. `verify` is unchanged: 183,696 matched,
            2 inconclusive, 1 mismatch;
          - default cap: 249,543 of 367,360 records are stored;
        - **every byte of a real record flipped**, with its CRC repaired: 75 were refused, 76 decoded and matched a
          fresh translation (bytes that re-linking overwrites anyway), and 122 were replaced by fresh code. The code
          installed was always the fresh translation's;
        - **CoreMark through the runner:** 1.0 MB written instead of 1.6 MB, and the same checks pass.
  14. The cache can be turned on for one app, and its write queue can be read (ANAL-381, for step P3).
      - **Why:** `berberis.pcache` is system-wide. Set for a G14 test, it would also turn the cache on for any of
        the owner's ARM apps that started meanwhile.
      - **`berberis.pcache=on:<package>`** (and `verify:<package>`) turns it on only in that package's processes, by
        exact name: `native_bridge_initialize` sets the package from the app's private directory before
        initialization.
        - A process without a package name, another package or a malformed value stays off.
        - Plain `off`, `on` and `verify` are unchanged.
      - **New counters:**
        - `pcache_records_queued`: published translations queued for writing;
        - `pcache_records_dropped`: records whose batch wasn't written (the cap, a file that would pass 4 GiB, a
          failed write).

        A record is counted as queued under the write queue's lock, so a flush can't count it as written first. Read
        from a running app, queued − written − dropped **estimates** what's waiting: the counters aren't read as one
        snapshot, and the app can still flush between the reading and a later kill. So it isn't the number a
        force-stop loses. Tests keep the raw values and their read times. Drops at the cap were counted as not
        persistable before.
- **ART patch** (`aosp/patches/art/`): `libnativebridge` sets `Build.CPU_ABI` and `CPU_ABI2` for bridged apps again (the Fennec fix).
- **Device:** `device/anybook/common/native-bridge/`:
  - `native-bridge.mk` inherits Digitalis's `enable_arm64_to_x86_64.mk` and adds `openbook_bridge_check`;
  - `BoardConfig.mk` sets `TARGET_NATIVE_BRIDGE_ARCH=arm64` (Cuttlefish's `vsoc_x86_64_only` board already sets it);
  - `pc.mk`, `anybook_cf_x86_64_pc.mk` and both BoardConfigs include them.
- **Why not merge android17-release into the fork:** a trial merge gives 64 conflicting files and 219 renames (a `cpu_emulation/` restructure; most conflicts in `cpu_emulation/backend/x86_64` and the arm64 `kernel_api`, `guest_os_primitives`, `runtime` and `native_bridge` code). Upstream android17-release has no arm64 translator; its new arm64 pieces are infrastructure that overlaps the fork's. Building the fork's translator against the Android 17 tree needs only patches 1 and 2. A full merge is worth doing when Digitalis itself moves to Android 17.
- **Cost** (2026-10-17): adding the bridge to an existing `out/` took 11 min 35 s at `-j28`, with the container's memory peaking at 57.7 GB (cgroup `memory.peak`). A first G14 build with the bridge took 29 min 31 s.
- **Host tests:** Digitalis's suite (`berberis_arm64_host_tests`) builds and runs in the build container from the same tree: 3,761 of 3,763 tests pass, 2 are skipped and none fail (2026-10-17).

## The three bugs

### 1. `MRS` of the ID registers (Tor VPN, Go)

**Symptom.** Tor VPN died of SIGILL at `mrs x0, id_aa64isar0_el1` under both bridges.

Go's `golang.org/x/sys/cpu` reads `ID_AA64ISAR0/ISAR1/PFR0` when it can't read `/proc/self/auxv`, and Android apps can't read it. A real arm64 kernel traps these EL0 reads and returns sanitised values (`emulate_mrs` in `arch/arm64/kernel/cpufeature.c`). Digitalis emulated only `MIDR_EL1`, while advertising `cpuid` in its emulated `/proc/cpuinfo`.

**Fix (patch 3).** `guest_id_registers_arm64.h` holds the guest CPU's identity in one place:
- `AT_HWCAP`, which gains `HWCAP_CPUID`;
- the values of `MIDR`/`MPIDR`/`REVIDR` and the `ID_AA64*` registers, built the way the kernel builds them: visible fields from the features the translator implements, hidden fields at the kernel's safe value;
- the rest of the feature ID space (CRm 2–7) reads as zero, and everything outside it still raises SIGILL, as on Linux.

The interpreter and the lite tier return these values. The heavy tier leaves such regions to the lite tier, as it did for `MIDR`.

`ID_AA64ISAR0_EL1` = `0x211120` (AES+PMULL, SHA1, SHA2, CRC32, LSE), matching `AT_HWCAP` = `fp asimd aes pmull sha1 sha2 crc32 atomics cpuid`.

**Result** (CONFIRMED): Tor VPN runs; the probe's `isa/mrs_cpuid_registers` passes; the probe's `regress` group checks 9 ID registers and their agreement with `AT_HWCAP` field by field, as the kernel derives HWCAPs.

### 2. `FRECPE` / `FRSQRTE` bit-exactness

**Symptom.** `FRECPE(1.0)` returned `0x3f800000`, where every Arm CPU returns `0x3f7f8000`.

All three tiers computed full-precision `1/x` and `1/sqrt(x)`. The special cases were wrong too:
- `FRSQRTE(+0)` gave NaN, where Arm gives +inf with DZC;
- NaN payloads were not propagated;
- `FPCR.FZ`, `DN` and `RMode` and the FPSR flags were ignored.

**Fix (patch 4).** `guest_fp_estimate_arm64.h` implements the Arm ARM's `FPRecipEstimate`, `FPRSqrtEstimate`, `RecipEstimate` and `RecipSqrtEstimate` for half, single and double precision.
- **Interpreter:** uses it directly.
- **Lite tier:** does the normal case inline per lane: a table lookup on the top fraction bits plus the result exponent, which needs neither FPCR nor FPSR. Any other lane (zero, denormal, infinity, NaN, negative `FRSQRTE` input, an `FRECPE` whose result would be denormal) calls the shared code out of line, with the caller-saved host registers saved around the call.
- **Heavy tier:** leaves vector `FRECPE`/`FRSQRTE` to the lite tier; it had no scalar forms.
- Digitalis's host tests that asserted the exact reciprocals now assert the Arm values. The tier-coverage table records the heavy tier's change.

**Result** (CONFIRMED):
- **The header against QEMU 11.1:** 0 mismatches in 189,200 cases. That covers scalar and vector, f16/f32/f64, `URECPE`/`URSQRTE`, and FPCR 0/FZ/DN/FZ|DN/RP/RM/RZ/FZ16, with edge cases and 2,000 random inputs per form.
- **On the device** (`scripts/compat/digitalis/fp-estimate.sh device`, an arm64 executable through binfmt_misc): 0 of 154,000 lines differ from QEMU under `two-gear`, `lite-translate-or-interpret` and `interpret-only`. Each input runs 50 times, so the JIT tiers translate the loop.
- **Probe:** `neon/frecpe_bit_exact` passes, and the `regress` group compares scalar and vector forms with QEMU golden values, including FPSR.

### 3. Fennec's SIGSEGV at `libxul.so+0x2b32da0`: not a translation bug

**What happens.** `Preferences::InitializeUserPrefs()` dereferences a NULL `Preferences` object. Gecko's `Preferences::GetInstanceForService()` had failed and dropped it, because `InitInitialObjects()` could not load the default preferences:
- GeckoView exports `MOZ_ANDROID_CPU_ABI` from `android.os.Build.CPU_ABI`;
- Gecko reads `<abi>/greprefs.js` from its omnijar, and then `greprefs.js`;
- the arm64 APK's `omni.ja` holds only `arm64-v8a/greprefs.js`, and `Build.CPU_ABI` was `x86_64`.

The `nsZipArchive` log shows the two failed lookups repeated about 970 times, then the crash.

**Why the ABI was wrong.** libnativebridge used to set `Build.CPU_ABI`/`CPU_ABI2` from the bridge's `getAppEnv()`, and Digitalis reports `arm64-v8a`. AOSP removed that in android17-release (art `b7947b0641`, May 2025: "deprecated since API 21").

**libndk_translation is affected too** (CONFIRMED). On Google's image the same two lookups fail. Its Gecko thread then spins at 100% CPU, and only the Java UI stays up, so a "RUNS" verdict for Fennec there means only "the process is alive". Under Digitalis the NULL dereference is fatal instead. Berberis's `HandleFatalSignal` catches the fault, so debuggerd writes no tombstone and the harness reports EXITED rather than CRASH.

**Fix** (`aosp/patches/art/0001-…`). Restore the two fields in `SetupEnvironment()`, as before android17-release.

**Result** (CONFIRMED): arm64 Fennec runs; Gecko logs "chrome startup finished" and runs its tab, content and GPU processes as arm64; it renders a page served over `adb reverse`, with JavaScript running. The probe's `regress/build_cpu_abi_is_native_abi` checks the field for the arm64 and x86_64 probes.

**Gotcha for future bisections.** Interpret-only mode at first seemed to fix the crash, which pointed at the JIT, and a lite-tier bisection by instruction class and library offset followed. Those runs were only slow enough to miss the crash inside a 20–25 s window, and app data left over between runs changed the timing. Clear app data per run, and confirm a "fix" survives a long wait.

## Results on our image (2026-10-17)

`anybook_cf_x86_64_pc-cp2a-userdebug` (`CP2A.260605.016`) in Cuttlefish (`scripts/compat/cf.sh`, `COMPAT_TARGET=cf`) with 6 vCPUs, 8 GiB and SwiftShader: the same resources, corpus, probes and harness as the emulator baselines. Two runs from wiped data gave identical outcomes.

### Apps

| App | Our build (Digitalis A17) | libndk_translation, Google image (ANAL-180) | Digitalis A16 overlay (ANAL-181) |
|---|---|---|---|
| OpenBook probe arm64 | RUNS, 18 pass / 2 fail (20 groups) | RUNS, 15/4 (19 groups) | RUNS, 16/3 |
| VLC, KOReader, Lichess, LocalSend, Godot, Ogre, Wesnoth, OsmAnd, GCompris, TIC-80, Tux Paint | RUNS | RUNS | RUNS |
| SimpleX | RUNS (window still black at 15 s) | RUNS (same) | RUNS (same) |
| **Fennec 158** | **RUNS** (Gecko works) | RUNS, but Gecko spins at 100% CPU | EXITED (SIGSEGV) |
| **Tor VPN** | **RUNS** | CRASH (SIGILL, `MRS`) | CRASH (SIGILL) |
| AAAAXY | CRASH (as natively) | CRASH | CRASH |
| Element X | CRASH (`JNI_GetCreatedJavaVMs`) | CRASH | CRASH |
| **arm64 apps alive at 15 s** | **14 / 16** | 13 / 16 | 12 / 16 |

- **Probe failures left** are the two known semantic differences: x86 NaN rules (`isa`: sNaN priority, default-NaN sign) and the SIGILL `si_code` (`signals`).
- **Launch times** (`am start -W`) are in the same range as libndk_translation's on the emulator: Fennec 0.62 s, Lichess 1.2 s, OsmAnd 1.0 s. They come from different VMs, so we don't compare them closely.

### CPU speed (CoreMark, 600k iterations, 3 interleaved rounds, quiet host)

| Bridge, image, VM | exe arm64 / x86_64 | apk arm64 / x86_64 |
|---|---|---|
| **Digitalis A17, our image, Cuttlefish** | **0.394** (16,870 / 42,839 it/s) | **0.399** (16,181 / 40,568) |
| Digitalis A17, Google's image, emulator | 0.300 (12,155 / 40,546) | 0.298 |
| libndk_translation, Google's image, emulator | 0.457 (18,516 / 40,532) | 0.456 |
| Digitalis A16, Google's image, emulator (ANAL-181) | 0.298 | 0.304 |
| **Digitalis A17, our image, on the G14** (bare metal, Ryzen AI 9 HX 370; "balanced", on mains; 2026-10-18) | **0.361** (10,012 / 27,724) | **0.351** (9,902 / 28,205) |

- Every round passed CoreMark validation, and the CoreMark binaries are the harness's own (`scripts/compat/build-probes.sh`). The spread between rounds is under 1%.
- The emulator rows with our A17 bridge use the bridge collected from the product (`scripts/compat/digitalis/bundle.sh`) and installed on Google's image ([Running Digitalis on Google's emulator image](#running-digitalis-on-googles-emulator-image)). The port neither helped nor hurt speed there.
- **HYPOTHESIS:** Cuttlefish passes the host's CPU features to the guest (`avx2 bmi1 bmi2 fma movbe adx avx512f`), the emulator's guest has none of these, and the translator selects code by host CPU features.
- **The G14 does not confirm "Cuttlefish or better":** its Zen 5 has the same features and gives 0.361 / 0.351. So CPU features alone don't explain Cuttlefish's 0.394. More HYPOTHESES: the ratio depends on the microarchitecture; or on which core ran the benchmark. The HX 370 has 4 Zen 5 and 8 Zen 5c cores, and native CoreMark there was 27.7k it/s against 37–43k in VMs on the build host's 7950X, which fits a Zen 5c core or the "balanced" power profile. The rounds were steady (within 1%), so each round probably ran on the same kind of core. Pinning each run to a known core would settle it.
- Digitalis's own published numbers (Geekbench 6 at 21–22% of native, its `docs/RELEASE_NOTES.md` of 2026-08-16) point the same way. CoreMark is integer-only and the VMs run SwiftShader, so these numbers say nothing about GPU-bound behaviour (`docs/compat-harness.md`).

## Comparison with libndk_translation

ANAL-181 ran both bridges on the same image (`google/sdk_gdesktop_x86_64/emu64xa:17/CLE1.260506.004`), same emulator (37.2.12), same 6 vCPUs, same corpus, 15 s wait, two runs each from wiped data (2026-10-16). Digitalis was then the upstream Android 16 build:

| Class | libndk_translation | Digitalis A16 (2026-10-16) |
|---|---|---|
| seq_cst store→load ordering (store-buffering test) | **FAIL**: about 2,000 of 200,000 | **PASS**: 0 of 200,000 |
| `MRS` ID registers | `MIDR_EL1` and `ID_AA64ISAR0_EL1` both SIGILL | `MIDR_EL1` emulated (`0x410fd034`); `ID_AA64ISAR0_EL1` SIGILL |
| x86 NaN rules | default NaN negative (`0xffc00000`); qNaN beats sNaN; `FMAX(qNaN,1)` returns the default NaN | default NaN still negative; qNaN still beats sNaN; **`FMAX` propagates the NaN** |
| `CNTVCT_EL0` rate | about 429× too fast (`CNTFRQ` 10.49 MHz) | **correct**: `CNTFRQ` 19.2 MHz, counter/wall = 0.999 |
| `uname -m` for arm64 code | `x86_64` | **`aarch64`** |
| SIGILL `si_code` | `SI_QUEUE` (−1) | `SI_QUEUE` (−1) |
| `FRECPE` estimate | bit-exact (`0x3f7f8000`) | returned exactly 1.0 (`0x3f800000`) |
| Advertised `HWCAP` | fp asimd aes pmull crc32 atomics | adds sha1 and sha2 |
| Element X (`JNI_GetCreatedJavaVMs`) | crash | crash; the probe finds it via `dlopen(libnativehelper)`, but not through `RTLD_DEFAULT` |
| SimpleX black window | black at 15 s | black at 15 s |

Our A17 build fixes the `MRS` and `FRECPE` rows and adds `cpuid` to `HWCAP` ([The three bugs](#the-three-bugs)); its probe fails only `isa` (x86 NaN rules) and `signals` (SIGILL `si_code`). The other 14 probe groups pass under both bridges: JNI, crypto, TLS, threads, syscalls, dlopen, C++ exceptions, JIT and memfd dual mapping, GLES 3.0 and Vulkan 1.3. Neither bridge has an arm32 guest, and the image is 64-bit only, so armeabi-v7a apps don't install.

Digitalis's own Android 16 reference image (`sdk_phone64_x86_64_digitalis`) gave the same arm64 outcomes, probe results and speed (0.295× / 0.297×) as the Android 16 overlay on Google's Android 17 image, so those results belonged to Digitalis itself, not to the mix. Gotcha on that image: emulator 37.2.12 segfaults with the virtio-gpu GL transport our harness forces for the Desktop image; it boots with the default transport (`COMPAT_GLTRANSPORT=`).

## License and provenance of what ships

`scripts/compat/digitalis/audit-shipped.py` lists every bridge file in a product's `PRODUCT_OUT`. For each file it records:
- the Soong module that installs it and its source directory (`module-info.json`);
- whether that source is under `prebuilts/`;
- its SHA-256;
- the licenses the image's own `NOTICE.xml.gz` gives for it, classified by their text.

Both products: 89 files each from the same modules, 1 prebuilt, 1 not covered by NOTICE (2026-10-17).

| What | Source | License (NOTICE) | Verdict |
|---|---|---|---|
| Translator, proxies, exec region, program runners | `frameworks/libs/binary_translation` (Digitalis fork plus our patches), built from source | Apache-2.0 | **OK** |
| binfmt_misc entries, `berberis.rc`, `ld.config.arm64.txt` | the fork's `prebuilt/` directory (text configs, not binaries) | Apache-2.0 | OK |
| Guest stub libraries, guest linker, `app_process64`, vdso | `frameworks/libs/native_bridge_support` (Android 17), built from source | Apache-2.0 | OK |
| Guest bionic, ICU, SQLite, zlib, BoringSSL, libpng, FreeType, liblzma, BLAS, RenderScript, libutils, liblog, … | AOSP projects, built from source for arm64 | Apache-2.0, BSD, MIT, ISC, zlib, Unicode, libpng, SQLite blessing, netlib BLAS | OK: the same projects ship natively in every AOSP image |
| `lib64/arm64/libc++.so` | `prebuilts/clang/host/linux-x86` (AOSP's LLVM toolchain) | not listed in `NOTICE.xml.gz` | OK. Apache-2.0 WITH LLVM-exception; the x86_64 `/system/lib64/libc++.so` is missing from NOTICE too, so this is an AOSP-wide gap, not ours |
| `openbook_bridge_check` | `device/anybook/common/native-bridge/check` | Apache-2.0 (OpenBook) | OK |
| `libnativebridge.so` (ART APEX) | `art` plus our patch | Apache-2.0 | OK |

- "GPL" appears in the NOTICE text of ICU and FreeType. It comes from build-tool files in those projects (autoconf/pkg-config macros, a collision-detection tool), and the x86_64 copies carry the same text. No GPL code is compiled into the bridge.
- Our patches carry Apache-2.0 headers ("The OpenBook Authors").

**The fork's own source** (ANAL-181 audit, CONFIRMED):
- The translator fork is Apache-2.0: 95 new files carry "Copyright (C) 2026 utzcoz" Apache headers, the rest AOSP headers. Its only binaries are upstream test fixtures, not built into the image.
- No copied third-party code turned up: a search of the fork's added lines for GPL/LGPL, QEMU, box64, FEX, dynarmic, SPDX tags, foreign copyright lines and "ported from" found only internal derivation comments.
- 20 new files have no license header (tests and the generated syscall table). Minor; ask upstream to add them.
- **Keep out:** `sample_hello_digitalis` carries third-party prebuilts for its test apps, including `libmsaoaidsec.so` (proprietary MSA OAID SDK, no license); the `digitalis` entry repo's `apkmirror_fetch` tooling downloads proprietary APKs and re-signs merged bundles. Neither is needed to build or run the bridge, and our corpus stays F-Droid only.
- No CLA or DCO. Development is agent-driven (the project's README and `CLAUDE.md` describe a Claude Code agent loop). That doesn't block Apache-2.0 use; the copyright status of AI-assisted code is an open legal question the owner knows about.
- Android and Berberis are Google trademarks, and Digitalis disclaims any affiliation. OpenBook must not imply Google endorsement either.

## On the G14 (bare metal)

### The self-check

`openbook_bridge_check` is an arm64 static binary, built from source in the tree as the bridge's guest architecture. It is installed as `/system/bin/arm64/openbook_bridge_check`; fsgen puts native-bridge modules on the system partition only. binfmt_misc runs it through the translator, and it prints one JSON result per check:
- `bridge-exec`: it ran as arm64;
- `bridge-id-registers`: 9 registers, no SIGILL, agreement with `AT_HWCAP`;
- `bridge-fp-estimates`: 6,900 golden cases from QEMU, with FPSR;
- `bridge-int-simd`: CRC32 and NEON FMA against references computed in the program.

`su 0 openbook-hwtest bridge` adds the configuration (`bridge-config`: the property, both binfmt_misc entries, the guest libraries) and passes the results on as `HWTEST` lines. The live image's "save logs" entry runs it with the other checks, and `scripts/installer/live-report.py` turns the lines into the verdicts `bridge_config`, `bridge_exec`, `bridge_id_registers`, `bridge_fp_estimates` and `bridge_int_simd`.

The check needs no network or user input and changes nothing. It passes in all three translation modes on Cuttlefish, as root and as the shell user, and under QEMU's `-cpu max` and `-cpu cortex-a53` (a real ARM CPU model), which validates the check itself.

**Enforcing policy.** `berberis.rc` mounts binfmt_misc and registers the runners in early-init. The Cuttlefish product inherits Cuttlefish's two rules for that; the PC products carry the same two rules in `device/anybook/common/pc/sepolicy/vendor/init.te` (ANAL-159). Without them, enforcing boots log `mount binfmt_misc ... Permission denied` and arm64 executables can't run, while app libraries still load through libnativebridge. **Gotcha:** the "save logs" entry is permissive, so its verdicts can't catch an enforcing-only gap like this one.

**Results on the G14** (CONFIRMED, 2026-10-17 and 2026-10-18; ROG Zephyrus G14 GA403WR, BIOS GA403WR.309, Ryzen AI 9 HX 370, family 0x1a, model 0x24):
- All five `bridge_*` verdicts pass: 57 guest libraries; `uname` `aarch64`, `AT_HWCAP` 0x9fb; `MIDR` 0x410fd034, `ISAR0` 0x211120; 0 wrong of 6,900 `FRECPE`/`FRSQRTE` cases; CRC32 and NEON FMA correct. Every block was translated by the JIT tiers (`jit=N interp=0`).
- Zygote starts with `-XX:NativeBridge=libberberis_arm64.so` in every boot, and no enforcing boot logged a denial naming binfmt_misc, berberis or a native-bridge path.
- The ARM apps check (below) passes all five of its verdicts. The arm64 probe gives the same results as in Cuttlefish and QEMU: `regress` passes (the ID registers, `FRECPE(1.0)`=`0x3f7f8000`, `Build.CPU_ABI`), `neon` passes, `isa` fails only on the x86 NaN rules and `signals` only on the SIGILL `si_code`. The x86_64 control passes 18 of 18, with 2 skips. CoreMark: 0.361 (executables) and 0.351 (in the app).
- **No arm64 app has been seen in an enforcing boot.** The apps used in normal sessions were all x86_64, and no app process outside the add-on logged a berberis translation line.

### The ARM apps check add-on (probe and CoreMark on the laptop)

The live stick has no adb and no arm64 app, so the probe and CoreMark go on the stick as an add-on. It uses the same live-init hook as the graphics check (`androidboot.openbook.addon=NAME`), and its entry is "OpenBook ARM apps check". It boots like "save logs". Once Android is up, the stick's own `openbook-live-init` unpacks the payload into the stick's `/data` and runs `scripts/compat/digitalis/stick/run.sh` as root. The run takes about 6 minutes in QEMU and 9 on the G14:
- `openbook_bridge_check`;
- the compat probe as arm64 and as x86_64 (the control);
- CoreMark, 600k iterations, 3 interleaved rounds, as executables and inside the probe app, as `run-bench.sh` runs it.

Afterwards it uninstalls the two probe apps, puts the keep-screen-on setting back, saves the results next to the boot's logs and powers off. The laptop's disks are never touched.

```bash
scripts/compat/build-probes.sh                                           # probe APKs and CoreMark (NDK r30)
scripts/compat/digitalis/stick/make-bridge-check.sh openbook-bridgecheck-<date>      # -> <data dir>/installer/out/NAME-addon (5 MB)
scripts/installer/inst-docker.sh "$PWD"/scripts/compat/digitalis/stick/add-to-image.sh IMG <data dir>/installer/out/NAME-addon   # mtools
scripts/compat/digitalis/stick/bridge-qemu.sh NAME RUN [LIVE_IMAGE]      # QEMU/KVM test on a copy of a live image
python3 -I scripts/compat/digitalis/stick/bridge-report.py <live-NNN>    # report-bridge.{json,md}
```

- **Image files only.** `add-to-image.sh` refuses block devices. A stick is written from the finished image with `scripts/installer/write-stick.sh`.
- **Verdicts:**
  - `addon_ran`: the payload checks out, `run.sh` returns 0, cleanup leaves no probe app;
  - `bridge_check`;
  - `probe_x86_64`: no failure;
  - `probe_arm64`: installed as `arm64-v8a`, `Build.CPU_ABI` is `arm64-v8a`, and no failed group beyond `isa` and `signals`, the two known differences;
  - `coremark_valid`: every run passes CRC validation.

  The report also gives the CoreMark ratios for executables and in the app. It keys on the installed ABI and `Build.CPU_ABI`, not on whether `libberberis_arm64.so` is mapped, because the bridge is mapped in x86_64 processes too.
- **In QEMU/KVM** (`-cpu host`, 8 vCPUs on the build host, 2026-10-17): all five verdicts pass, CoreMark 0.362 / 0.372. That is a VM on a busy host, not the laptop.
- **On the laptop:** boot "OpenBook ARM apps check" once, on mains power with the lid open, and leave it for about 10 minutes until it powers off. Results: `openbook/logs/live-NNN/addon-bridge*` on the stick.

## Running Digitalis on Google's emulator image

For like-for-like comparisons with libndk_translation, the bridge can be overlaid on Google's AOSP Desktop (Preview) 37.0 emulator image. `scripts/compat/digitalis/install.sh` uses a separate AVD, `anybook-digitalis`, built from the same system image, so the baseline AVD is never modified.

```bash
scripts/compat/digitalis/bundle.sh [PRODUCT_OUT] [OUT]                                # our A17 bridge -> ~/anybook/digitalis/bundle-a17
scripts/compat/digitalis/install.sh ~/anybook/digitalis/bundle-a17 -o <out dir>       # overlay onto the emulator AVD (port 5580)
COMPAT_AVD=anybook-digitalis COMPAT_EMU_ARGS=-writable-system scripts/compat/run-matrix.sh -o <dir> --keep-emulator
COMPAT_AVD=anybook-digitalis COMPAT_EMU_ARGS=-writable-system scripts/compat/run-bench.sh -o <dir> --keep-emulator
python3 -I scripts/compat/side-by-side.py libndk_translation <baseline-run> Digitalis <digitalis-run>
```

`install.sh`:
1. Wipe-boots with `-writable-system`.
2. Runs `adb remount`. The first remount disables verity and needs a reboot. The upper layer then lives on `/mnt/scratch`, an overlayfs on `/system` and `/vendor`.
3. Replaces `/system/{lib64,bin}/arm64` (libndk_translation's guest world) with Digitalis's, and pushes the translator, proxies, runners and configs.
4. Sets `ro.dalvik.vm.native.bridge=libberberis_arm64.so` and `ro.berberis.flags=disable-ir-check` in `/system/build.prop` (the image ships `accurate-sigsegv` for libndk_translation; `disable-ir-check` is what Digitalis's own product sets).
5. Reboots and verifies: zygote starts with `-XX:NativeBridge=libberberis_arm64.so`, binfmt_misc `arm64_dyn` points to `berberis_program_runner_binfmt_misc_arm64`, arm64 apps log `Initialized Berberis (aarch64)`, and the x86_64 control probe still passes.

Gotchas:
- `adb push` lands files as 0666, and init then refuses the binfmt entries with "Skipping insecure file". `install.sh` re-applies the bundle's modes.
- A data wipe also drops the overlay, so every fresh run reinstalls.
- The translator needs only `liblog`, `libandroid`, `libdl_android`, `libc++`, `libc`, `libm` and `libdl`, which is why an Android 16 build loads on the Android 17 image. Its guest libraries then lag the platform, a mix Digitalis's docs call unsupported.

**The upstream Android 16 build** (what ANAL-181 evaluated; not needed for OpenBook's own build):

```bash
scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/sync.sh             # ~/anybook/digitalis/aosp16
DIGITALIS_JOBS=16 scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/build.sh modules
DIGITALIS_JOBS=24 scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/build.sh full   # m + m emu_img_zip
```

- **Container:** the `anybook-aosp` image (Ubuntu 24.04). `docker.sh` mounts `~/anybook/digitalis` read-write and the shared AOSP mirror **read-only**, both at their host paths, so git alternates resolve on both sides.
- **Sync** (`sync.sh`, about 53 min, 115 GB): `repo init` on the Digitalis manifest at `3969040d` with `--reference` to the local AOSP mirror. `manifests/digitalis/digitalis-pinned.xml` pins the four Digitalis projects and switches them to https, because upstream uses `git@github.com:` URLs and floating branches. It also drops `sample_hello_digitalis`, which uses git-LFS and breaks `repo` checkout in the container.
- **Build** (`build.sh modules`): `lunch sdk_phone64_x86_64_digitalis-trunk_staging-userdebug`, then `m` on the 70 packages that `enable_arm64_to_x86_64.mk` installs (expanded by make from `berberis_config.mk` and `native_bridge_support.mk`, not hard-coded). About 44 min at `-j16` on a loaded host, peak RSS 26 GB. The bundle is the 74 files in `BERBERIS_DISTRIBUTION_ARTIFACTS_ARM64`.
- **Full image** (`build.sh full`): about 1 h 22 min at `-j24`, peak RSS 12 GB, `out/` 96 GB. Its 74 bridge files are byte-identical to the module build's.

## Open issues

- **Not fixed, by design:** x86 NaN semantics (default-NaN sign, sNaN priority), the SIGILL `si_code`, Element X's `JNI_GetCreatedJavaVMs`, and AAAAXY (a crash in the app itself).
- **The `Build.CPU_ABI` patch changes Android 17 behaviour back to Android 16's.** It affects every bridged app, as intended. An upstream AOSP report (art `b7947b0641`) would be outward-facing and is for the owner to decide.
- **Upstream reports to Digitalis** (`MRS`, `FRECPE`) wait for the owner's OK. The patches stay in this repo; none was sent anywhere.
- **Speed:** about 65% of libndk_translation in the same VM. The heavy tier leaves regions with vector `FRECPE`/`FRSQRTE` to the lite tier, which costs nothing on CoreMark but may cost a little in NEON-heavy code with estimates (HYPOTHESIS, not measured).
- **The emulated `/proc/cpuinfo`** lists `fphp asimdhp asimdrdm lrcpc dcpop asimddp`, but `AT_HWCAP` and the ID registers do not. The conservative `AT_HWCAP` is what code that probes features uses; the mismatch predates our changes.

## Next

1. An arm64 app in an **enforcing** G14 boot. The default boot has no arm64 app, and the add-on runs permissive. A small arm64 app preinstalled on the live image, or a device agent (ANAL-194), would close this.
2. A like-for-like libndk_translation baseline on the G14. It is proprietary and lives only in Google's images, so it can't go on ours. Google's AOSP Desktop emulator image under KVM on the G14's own Linux would give one (device loop, ANAL-194/195).
3. Why the G14 ratio is 0.36 and Cuttlefish's 0.39: pin CoreMark to a Zen 5 core and to a Zen 5c core in the add-on (`taskset`), and record the core each run used. Low priority.
4. Merge android17-release into the fork once Digitalis tracks Android 17, or do it ourselves (64 conflicts).
5. Upstream reports to DigitalisX64 and AOSP, after the owner's OK.
6. A SIMD/JIT micro-benchmark: CoreMark alone may understate the heavy optimizer's NEON work. simd-bench and the
   ARM-translation corpus cover the SIMD part ([`arm-performance.md`](arm-performance.md)); JIT-heavy code is ANAL-379.
