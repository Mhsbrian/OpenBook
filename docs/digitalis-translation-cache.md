# Digitalis: a persistent translation cache

A design, partly built. Revision 3, 2026-11-05:
- **Revision 2** carried the corrections from the plan review of revision 1 (Proceed with follow-ups, ANAL-381).
- **Revision 3** records step P1a (Digitalis patch 10: relocatable lite output, section 8). It also takes in the
  review's two clarifications for P2 (3.6 and 7), and corrects which libraries Lichess's regions come from (1 and 7).

Digitalis translates every ARM region again in every process. Lichess's second cold start on the G14 compiled 99.8% of
the same file-backed code as its first. This design keeps translated regions in the app's private storage and loads
them the next time the app starts, without trusting anything it can't check.

Source references are to Digitalis at OpenBook patch 9 (`main` `5aab4a5b`), with
`aosp/patches/frameworks/libs/binary_translation/0001`–`0009` applied. Bare paths are relative to
`frameworks/libs/binary_translation`.

## 1. Why

**Lichess 0.30.3 arm64 on the G14.** Image `ob20261104.1`, translator profiling on, the second of two cold starts
(ANAL-384):

| | |
|---|---|
| Lite regions installed | 188,751. 5.48 MB of guest code becomes 75.4 MB of host code (13.8×). A region averages 29 guest bytes (7 instructions) and 400 host bytes |
| Heavy regions installed | 831: 143 KB guest, 1.11 MB host |
| Accumulated elapsed compile time | lite 0.636 s (3.4 µs a region), heavy 0.375 s. Lite is 63% of the total |
| Same `(library, file offset, size)` as the first launch | 183,980 of 184,404 file-backed regions (99.8%) |
| Where the regions are (183,699 unique starts) | All in the APK, 93%: `libflutter.so` (76 k), the app's Dart code `libapp.so` (39 k), Chromium's network stack `libcronet` (29 k) and `libonnxruntime.so` (27 k). Guest system libraries (`linker64`, `libc`, `libandroid_runtime`, `libGLESv2` and others) make up the other 7% (12 k) |
| Invalidations | 0 |

Sampled CPU inside `libberberis_arm64.so` for the same two launches, bucketed by symbol name:

| Bucket | Launch 1 | Launch 2 |
|---|---|---|
| Heavy optimizer passes and register allocation | 284 ms (37%) | 306 ms (40%) |
| Assembler and `MachineCode` | 123 ms (16%) | 119 ms (16%) |
| Lite translator and decoder | 105 ms (14%) | 116 ms (15%) |
| Translation-cache map insert | 76 ms (10%) | 63 ms (8%) |
| Recovery-map insert | 37 ms (5%) | 32 ms (4%) |
| Perf-map writing (profiling only) | 39 ms (5%) | 47 ms (6%) |
| Allocation, dispatch, other | 99 ms | 80 ms |
| **Total** | **763 ms of the app's 2,266** | **763 ms of 2,290** |

**What this shows:**
- Lite is most of the elapsed compile time. Heavy is the largest share of the CPU, so both tiers matter.
- These runs predate patch 9, which skips the heavy backend for the 86% of gear-ups that are declined. That patch's G14
  effect is measured separately (ANAL-387).
- Cold start to the first frame is 922 ms translated against 274 ms native. How much of the compile falls before the
  first frame isn't known yet: the profile has no timeline.

## 2. What the source says

- **Nothing survives the process.** `TranslationCache` is an in-memory `ForeverMap<GuestAddr, GuestCodeEntry>`
  (`runtime_primitives/include/berberis/runtime_primitives/translation_cache.h:220`).
- **A translation depends only on the region's own instruction bytes.** Both tiers fetch words in `[pc, stop_pc)` and
  nothing else:
  - lite: `lite_translator/arm64_to_x86_64/lite_translate_region.cc:84`;
  - heavy: the decode loop in `heavy_optimizer/arm64/heavy_optimize_region.cc`;
  - the only read past the region is a bail's trace line (`heavy_optimizer/arm64/frontend.cc:2629`).

  Literal loads stay loads at run time and aren't folded into constants (`frontend.cc:3017`).
- **Publication already handles races.** Every result goes through `AddAndLockForTranslation` and
  `SetTranslatedAndUnlock` (`runtime/arm64/translator_x86_64.cc:291`, `:361`). The latter throws away a result that was
  invalidated while it was being made (`runtime_primitives/translation_cache.cc:97`).
- **Generated code sits in the low 2 GiB**, in a memfd-backed pool (`HostCodeAddr` is 32-bit, `host_code.h:31`;
  `exec_region_anonymous.cc:59`). It embeds per-process values; section 3.4 lists them.
- **The platform already gives the bridge a private directory:**
  - the zygote passes the app's data directory (`frameworks/base/core/jni/com_android_internal_os_Zygote.cpp:2017`);
  - libnativebridge creates `<data>/code_cache` and passes it to the bridge's `initialize` as `private_dir`
    (`art/libnativebridge/native_bridge.cc:301–447`);
  - Digitalis reads only the package name from it today (`native_bridge/native_bridge.cc:500`).
- **The system manages `code_cache`:**
  - it's cleared when the app is updated (`InstallPackageHelper.java:1284`);
  - it's cleared on every OTA, since the build fingerprint changes (`PackageManagerService.java:2449`);
  - installd evicts it under storage pressure (`frameworks/native/cmds/installd/CacheTracker.cpp:71`);
  - backups leave it out (`BackupAgent.java:625`).
- **Guest `mmap` sees the file.** `MmapForGuest` (`kernel_api/sys_mman_emulation.cc:70`) has the fd and offset of every
  guest mapping, and already reads ELF headers for libraries stored inside APKs.

## 3. Design

### 3.1 What is cached

- **Cached:** lite and heavy regions translated from **file-backed** guest mappings.
- **Never cached:**
  - anonymous memory, memfds, deleted files and guest JIT code. Those are what ANAL-379's invalidation work is about,
    so the two don't interact;
  - wrappers and trampolines, which are built when a library loads, not translated.
- **Which tier.** A region is stored as the tier it ended on: heavy, lite with its hotness counter, or lite settled for
  good (a declined or bailed gear-up, with no counter). Next launch it starts where it finished.

### 3.2 Identity and key

- **Module:** the ELF image a guest mapping comes from. It's recorded when the guest maps it, as:
  - its GNU build-id when it has one, otherwise `(st_dev, st_ino, st_size, st_mtime)`. Lichess 0.30.3's arm64
    libraries: 7 of 12 have a build-id, including `libflutter.so` and `libapp.so`. `libsqlite3.so` and the Stockfish
    engines don't;
  - plus the ELF's offset inside its file, since an APK holds several.
- **Region:** `(module, ELF virtual address of the region's first instruction)`. ELF addresses don't move between
  launches; only the load bias does. This is the identity behind the 99.8% figure, which used file offsets.
- **Why there's no whole-library content hash.** The key only *finds* a candidate. Correctness comes from comparing the
  region's own bytes exactly (3.3), which is a content check of precisely what the translation depends on.
  - **Cost:** hashing every library on every launch costs 36–37 ms for Lichess's 80 MB of arm64 libraries (SHA-256,
    page cache, Ryzen 9 7950X build host), and 6–7 ms for `libflutter.so` alone. That's before any disk read.
  - **The per-region compare** reads only the 5.5 MB that actually runs, spread over the launch.
  - **A library replaced** under the same path and timestamps fails those compares region by region, and its regions
    are translated afresh.

### 3.3 Validity: when a cached region is used, and when it's ignored

**What may be written.**
- **One mapping, one module.** The whole range `[pc, pc + size)` must lie in one file-backed mapping of one module.
  Being file-backed alone doesn't make code immutable: the app can write a private file mapping, or replace it with
  `MAP_FIXED`.
- **The bytes stored** are the instruction bytes the translator actually decoded, captured while it decoded them. They
  aren't re-read from memory when the record is written.
- **Addresses stay in the module.** Every guest address the region embeds must lie inside the same module's load
  range. If any doesn't, the region is never written.
- **Module attribution stays current.** The mapping registry is updated on every guest `mmap`, `munmap`, `mprotect`
  and `mremap`, including a `MAP_FIXED` replacement. A range whose mapping changed belongs to the new mapping, or to
  none.

**What may be installed.** A cached region is installed only if all of these hold, checked in this order:

1. **Same translator and settings.** The file's header matches all of these:
   - the translator's build-id;
   - `berberis.mode`, `berberis.gearup_min_insns` and `berberis.flags`;
   - the host CPU features the backends test (AVX2, BMI1/2, F16C, FMA, AVX-512 and so on);
   - the guest ISA and the page size.

   A mismatch ignores the whole file, which is then rewritten.
2. **Intact and well-formed.** The checks run on the private copy of the record that will be installed:
   - its CRC32C matches. A bad record ends the scan of that file;
   - its lengths, offsets and relocation entries are in bounds and don't overflow;
   - `pc + size` doesn't wrap.

   All of this is checked before anything is allocated or patched.
3. **Still executable, in the same module.** All of `[pc, pc + size)` is executable in `GuestMapShadow`, the same
   check translation makes (`GetExecutableRegionSize`). The range is also currently attributed to the record's module.
   This is checked before any guest memory is read.
4. **Exact bytes.** The guest bytes in memory now at `[pc, pc + size)` equal the bytes stored with the record. That's a
   full compare of about 29 bytes on average. It catches code the app patched before running it, a different library
   behind the same key, and a wrong module match.

**After install,** a loaded region is an ordinary cache entry:
- `IC IVAU`, and `ClearExecutable` from `munmap` or `mprotect`, invalidate it through `InvalidateGuestRange` as they do
  any other entry.
- A load that races with an invalidation is discarded at publication, like a compile. `InvalidateGuestRange`
  invalidates **every** in-flight translation, not only those overlapping its range
  (`runtime_primitives/translation_cache.cc:264`, `:273`), and `SetTranslatedAndUnlock` then rejects them.
- The writer's own invalidations don't need recording. A region whose bytes changed fails check 4 next launch. One
  whose bytes didn't change is still a correct translation.

**The scope is unmodified, file-backed code,** which needs no change to how invalidation works. These are loader
requirements; they don't depend on any further ANAL-379 work. On the G14, Lichess made 0 invalidation requests and
ContentShell 0–1 per process (ANAL-379).

### 3.4 What generated code embeds, and how a cached region is re-linked

| Embedded value | Emitted at | Changes between launches because | Stored as |
|---|---|---|---|
| Guest PCs and PC-relative results: region exits, the `BL` link value, ADR/ADRP, literal addresses | lite: about 25 `GetInsnAddr()` sites; `EmitDirectDispatch` and `EmitSyscall` (`code_gen_lib/all_to_x86_64/code_gen_lib.cc`); heavy: `GetImm(target)`, then IR immediates | library ASLR | ELF address in the module |
| Translation-table slot of a direct-dispatch target | `code_gen_lib.cc:140` | heap allocation | the target's ELF address |
| Main table pointer (indirect dispatch) | `code_gen_lib.cc:167` | heap allocation | a fixed id |
| The region's hotness counter | `lite_translate_region.cc:45` (`&entry->invocation_counter`) | heap allocation | a flag: point it at the new entry's counter |
| Helper and callback calls: `RunGuestSyscall`, `FpEstimateSlowPath`, the gear-up callback, heavy `CallImm`. Static data: the FRECPE/FRSQRTE fast tables | `x86_64::Assembler::Call`, `Jcc` and `Jmp` with an inline 64-bit target (`assembler/include/berberis/assembler/x86_64.h:155`, `:179`, `:232`); `lite_translator.cc:77`, `:151`; `backend/x86_64/code_emit.cc:214` | `libberberis` ASLR | offset in `libberberis` (its build-id is in the header) |
| Helper data built on the heap: the unsigned reciprocal/rsqrt estimate tables, and the heavy tier's LD2–LD4/ST2–ST4 permutation masks | lite `lite_translator_fp_dataproc.inc:945` (used at `lite_translator_simd_two_reg_misc.inc:95`); heavy `heavy_optimizer/arm64/frontend.cc:89`, and `:178`, used at `:15708` | heap allocation (`new`) | a semantic resource id (which table, which entry) resolved in the new process. An unidentified one makes the region not persistable |
| Host entry trampolines (`kEntryExitGeneratedCode` and the rest) | `RelocAbsToDisp32` records (`machine_code.h:49`) | installed into the code pool at start-up (`host_entries.cc:54`) | an entry id |
| Recovery points for faulting guest accesses | `RelocRecoveryPoint` records | the code's address | unchanged: re-registered at load |

**How it's recorded:**
- **Control transfers with an inline 64-bit target** are tagged centrally. The three assembler routines add a
  relocation record that's a no-op at install. At save time, a target inside `libberberis` becomes an offset and a
  trampoline becomes an entry id. Anything else makes the region not persistable.
- **Existing `RelocAbsToDisp32` records** already hold their absolute target, so they're symbolised the same way, with
  no change where they're emitted.
- **Data immediates** go through typed emitters: guest address, table slot, main table, counter, `libberberis` data,
  heap resource. Each always emits one fixed width, so re-linking is a patch of known size and code length can't
  depend on the value. Narrower forms are covered too: a 32-bit immediate or displacement that holds an address gets
  a record like a 64-bit one.

**On load:** copy the code into the code pool, patch those operands, then run the existing `PerformRelocations` for
the 32-bit displacements and recovery points.

**Tier order:**
1. **Lite first.** It's 99.6% of installed regions and 63% of elapsed compile time. Its output is emitted directly,
   so tagging the emission sites is enough.
2. **Heavy second.** It's the largest share of translator CPU, so it can't be skipped, but addresses pass through its
   IR. Immediates carry symbolic provenance: a base (guest module, table, heap resource) plus a constant addend.
   - Optimization must preserve it. A fold is safe only when its result is still one base plus a constant addend.
   - Two address-valued operands aren't automatically safe.
   - Any fold that can't be represented marks the region not persistable.

### 3.5 When to load: lazily, on a region's first execution

- **How:** when a region first runs, `berberis_HandleNotTranslated` reaches `TranslateRegion`. Once
  `AddAndLockForTranslation` succeeds, the module's index is checked. A hit that passes 3.3 is copied, re-linked and
  published with `SetTranslatedAndUnlock`. A miss is translated as today.
- **Why lazily:**
  - work stays proportional to the code that runs;
  - every install keeps the existing lock and publication protocol;
  - the bytes check happens at the moment the code is first used.
- **Why not eagerly at library load:** that would copy and relocate all 75 MB for Lichess before its first instruction
  runs, on the main thread, for regions that may not run this time. It would also need a separate path to keep entries
  consistent with invalidation.

### 3.6 Storage and concurrency

- **Where:** `<private_dir>/berberis/`, which is the app's `code_cache`. It's per app and per user, because ART passes
  that user's data directory.
  - **Never cached:** isolated processes and others with no `private_dir`, or one that can't be opened. They translate
    as today.
  - **Executables run through the program runner** use `BERBERIS_PCACHE_DIR`, which tests and benchmarks set.
- **Files:** one per module, named by the module key. Each holds:
  - a header (the settings fingerprint from 3.3, and the module identity);
  - an append-only log of records: guest bytes, code before relocation, relocation list, tier and counter flag, CRC32C;
  - a small index log (ELF address → record offset), so a reader builds its index without touching the code pages.
- **Writes, two kinds:**
  - **Publication is atomic.** A file is created by writing the header to a temporary name and renaming it into
    place, so a reader sees no file or a whole header.
  - **Appends aren't atomic.** After publication, records are appended (`O_APPEND`) and nothing is rewritten in
    place. A torn tail is what the CRC check below handles.
- **Corruption fails closed.** A reader stops at the first record whose length or CRC doesn't check out, and translates
  everything past it.
- **A mismatch never makes a reader write.** Readers ignore a file whose header doesn't match. Only the module's
  writer replaces a file, and it does so under the single-writer lock below.
- **Writing:**
  - records collect in a per-process buffer;
  - the thread that translated flushes it when it reaches 1 MiB, or 2 s after the last flush;
  - **no thread is started.** App zygotes must stay single-threaded to fork (ART's `WaitUntilSingleThreaded`, found in
    ANAL-383);
  - a tail lost to `SIGKILL` is translated again next time.
- **Several processes of one app:** one writer per module, by `flock(LOCK_EX | LOCK_NB)`. The others only read.
  - **The lock is on a stable lock file per module, not on the cache file.** A replacement is a new inode, and a lock
    on the old one doesn't lock it.
  - The writer holds the lock through creating, replacing or appending to the file.
- **Size and eviction:**
  - a cap of 128 MiB per app, after which writing stops;
  - installd evicts `code_cache` when storage runs low;
  - app updates and OTAs clear it.
  - Compaction is later work. Lichess's cache would be about 95 MB (estimate: 75 MB of code plus metadata). Smaller lite
    code would shrink it, and that's tracked with ANAL-382.

### 3.7 Knobs and counters

- **`berberis.pcache` (and `BERBERIS_PCACHE`):** `off`, `on` or `verify`. The default stays `off` until step P4.
  - `verify` loads a region, then also translates it with the cached tier and the cached parameters: profiling
    counter or not, in-region loop mode, region end. A first-gear lite compile can't validate heavy or settled-lite
    output.
  - **Comparing.** `RelocAbsToDisp32` displacements depend on the address the code is installed at
    (`assembler/machine_code.cc:76`), so both copies are relocated for one hypothetical address before comparing.
    Recovery metadata is compared separately.
  - The comparison happens before the candidate ever runs. On a mismatch the fresh translation is installed, logged
    and counted.
- **New translator counters:**
  - `pcache_hits_lite`, `pcache_hits_heavy` and `pcache_misses`;
  - rejects by reason: bytes, executable, settings, CRC;
  - `pcache_load_ns`;
  - `pcache_records_written`, `pcache_bytes_written` and `pcache_write_ns`;
  - regions not persistable, by reason: anonymous, cross-module, untagged pointer, cap.
- **Perf map:** loaded regions get a `_cached` tier name, so `app-perf.sh cpu --translator` separates loaded code from
  compiled code.

## 4. Security

- **Who can write the cache.** Only the app's own UID, plus root and system. `code_cache` is app-private storage, and
  backups and restores don't carry it.
- **What a tampered cache can do.** A cache entry is host x86_64 code that runs in the app's process with the app's
  permissions.
  - **Any write into the app's `code_cache` becomes native code execution at the next launch.** That includes a write
    with no code execution behind it, such as a path-traversal bug in the app's own file handling. It also gives an
    attacker who once ran code in the app persistence across restarts.
  - Android hardens this kind of path: no `execve` from app storage since API 29, and read-only dynamically loaded code
    since API 34. The API 34 rule isn't an authenticity guarantee for a custom loader like this one.
  - For translated apps, guest-side W^X already isn't enforced: a guest `PROT_EXEC` file mapping is host `PROT_READ`.
    But that needs the app to load the file itself; the cache would load automatically.
- **What this design does:**
  - every record, index and relocation is bounds-checked before anything is allocated or patched;
  - the record is copied privately, and that copy is what gets validated and installed. Nothing is read twice from the
    file;
  - guest bytes are checked exactly;
  - the cache is cleared on update and OTA;
  - it's off by default and used only in explicit opt-in tests.
- **What it can't do.** Mode `0400`, CRC32C and matching guest bytes don't authenticate host instructions against a
  writer with the app's UID. **The residual risk is the whole first bullet above.**
- **The way to remove it** is ART's own model: the app writes only a profile (region addresses per module), and a system
  job in its own confined SELinux domain translates from the installed APK into a cache the app can't modify. That's
  much more work: a daemon, a domain, installd paths, and confinement like dex2oat's, because it compiles code an
  attacker chose. Section 7 covers it.
- **Decision:** before any production enablement, step P4 records one of two outcomes: an explicit acceptance of that
  broader risk with the in-process writer, or the privileged writer. P3's measured gain informs it, and it must be
  settled before 0.2's `user` build.
  - The privileged writer only helps if its output and directory can't be modified by the app, and it translates only
    from trusted installed inputs.
  - The app's profile carries addresses, never code. Accepting native records written by the app would defeat it.
- **Licensing** isn't affected. A cache is generated on the device, from the user's installed apps, and never
  distributed.

## 5. Expected saving and how it's measured

**Estimate (a hypothesis until P2 and P3 measure it):**
- **The ceiling** is the translator CPU spent on repeat regions. That's most of Lichess's 763 ms: the heavy passes,
  lite and the assembler, 510–540 ms of it before patch 9. Patch 9 lowers that ceiling by however much heavy work it
  removed.
- **Loading costs:**
  - a lookup, a 29-byte compare, a 400-byte copy and about six patches per region. I expect well under 1 µs, against
    3.4 µs to compile a region lite and much more to compile it heavy;
  - the two map inserts (about 100 ms) remain.
- **My estimate:** 0.3–0.5 CPU-seconds saved per Lichess cold start, out of 2.27. How much of that shortens time to
  the first frame isn't known.

**Measurement:**
- **Host (P2):**
  - **Replay harness.** It translates Lichess's real region set (189,582 starts with library and file offset, from
    the G14 perf map), saves it, then loads it in a fresh process at a different base. It reports ns per region for
    compile and for load, and bytes written.
  - CoreMark and simd-bench through the program runner, launched twice: the first launch's write cost and the
    second's load cost.
- **G14 (P3), in a batched test image:**
  - the ARM corpus (Lichess, Luanti, SuperTuxKart, Jitsi Meet, Mindustry) at the same APK versions, `pcache=off`
    against `on`;
  - each app's first launch (it writes) and second launch (it loads), reported separately;
  - for each: `app-perf.sh start` (cold start, time to first frame), `app-perf.sh cpu --translator` (absolute CPU,
    compile share and the new counters);
  - profiling off for the headline numbers, and on only for attribution.
- **No regression:** Digitalis's host suite and the compat corpus pass with the cache on, and also with `verify`.

## 6. Verification

- **Relocation completeness, checked two independent ways.** Lichess's real region set establishes *coverage*, not
  completeness by itself. Its libraries come from the test APK and the guest system image, are used locally only, and
  are never redistributed.
  - **Pointer scan:** in audit mode, every window of installed code whose value falls inside one of these must be
    covered by a relocation record:
    - `libberberis`, the code pool, the translation tables or the guest module;
    - the heap resources from 3.4.

    The scan covers 4-byte values as well as 8-byte ones, for small ranges below 4 GiB. Recovery metadata is
    audited too. What P1a found:
    - **A window that touches a recorded operand is skipped.** Instruction fields don't overlap, and the opcode
      bytes before a recorded guest address can read as an address.
    - **The entry trampolines are left out of the 4-byte scan.** The code pool starts at a round address
      (`0x41000000`), whose bytes are what any small 32-bit immediate followed by a REX.B prefix looks like.
      Instead, the differential moves the entries between environments.
    - **A large module below 4 GiB isn't scanned in 4-byte windows.** 80 MB at `0x70000000` matches ordinary
      displacements by chance (`mov [rbp+0x70], r9`). The differential covers those copies.
  - **Differential across environments:**
    - the same guest bytes are translated in two environments that differ in **every** input: guest base (a
      page-multiple apart, both above 4 GiB), `libberberis` base, code pool, translation tables, counters and heap
      resources. The second is a separate process;
    - the first's records are relocated into the second environment;
    - the result must be byte-identical to the second's fresh translation, at the same hypothetical install address.
  - **Fixtures:** small opcode fixtures for every relocation class, including classes Lichess doesn't hit (the
    unsigned estimates, LD3/ST4 masks). Each comes with a deliberately omitted relocation that must make both checks
    fail.
- **Host suite:** all tests with `pcache=verify`, run twice (once writing, once loading). New tests:
  - changed guest bytes are rejected;
  - a different module base;
  - a corrupt or torn tail;
  - changed settings;
  - two writers;
  - an invalidation during a load;
  - a counter re-linked to the new entry;
  - an unwritable `private_dir`.
- **Device:** the compat corpus and the JIT and self-modifying-code coverage, with `pcache=verify`.

## 7. Rejected alternatives

| Alternative | Why not now |
|---|---|
| **Whole-library translation at install** (Rosetta-style ahead-of-time) | Finding code statically in stripped ARM binaries is unreliable: indirect branches, data in text, jump tables. Lichess's libraries hold 80 MB, and 5.5 MB of guest code runs at start-up, so most of the translation and storage would be wasted. It also needs the privileged translator below. |
| **A system-wide cache shared by all apps** | A writer whose output other apps run crosses app sandboxes, so it needs a privileged, confined writer and cache-poisoning defences. Most start-up code (Flutter, the app's Dart code) is per-app anyway. *Later extension, not rejected:* a read-only cache for guest **system** libraries (`linker64`, `libc`, `libandroid_runtime` and the rest), built into the signed image and covered by verified boot. It would cover only 7% of Lichess's regions (12 k), since the rest are in the APK. |
| **Moving compiles off the app's thread** | Background compilation doesn't remove compilation work, and its net effect on CPU and start-up is unmeasured. Lite has to stay synchronous, because the thread needs the code and the interpreter is far slower. Heavy compiles could move to a background thread, but app zygotes can't have one. Patch 9 cut 18–21% of heavy elapsed compile time on the host; its Lichess effect is still being measured (ANAL-387). This stays a separate, possible later change for heavy only. |
| **Privileged, profile-guided writer** (ART's model) | Not rejected: it's the secure form of this design (section 4). Steps P1 to P3 are shared with it. P4 decides whether it's needed. |
| **A content hash of each library as the key** | It costs 36–37 ms per Lichess launch on the build host, on the start-up path. The exact per-region compare is cheaper and checks exactly what a translation depends on (3.2). |

## 8. Steps

Each step is one pull request or one test image, and each decides something:

| Step | What | Decides | Device |
|---|---|---|---|
| P1a | Relocatable lite and `code_gen_lib` output: records, typed emitters including heap resources, the pointer scan, the all-inputs differential and the fixtures. No change in behaviour | **Done, Digitalis patch 10, on the host.** Every lite region of Lichess's set is relocatable: all 183,699 persistable, no unrecorded pointer, no re-link mismatch between a module above and below 4 GiB (in-process; the second-process differential runs on the fixtures). Above 4 GiB the typed emitters keep `Movq`'s exact encoding; below it they're longer. The corpus totals 73,942,150 host bytes before and after, an equal aggregate rather than a per-translation comparison. The scan's ranges cover every translation subtable a module spans (from the review). Recording is opt-in: it costs a median 2.4% of lite translation time. Re-linking a region took 0.1 µs against 6–7 µs to translate it, but that isn't a load's whole cost | none |
| P1b | The same for heavy: symbolic provenance on IR immediates and the fold rules | The same, for heavy | none |
| P2 | The cache: format, writer, loader (3.3's eligibility and check order), counters, `berberis.pcache` off by default, `verify`, the replay harness, the invalidation-during-load test | Load against compile cost per region; write cost; host start-up change | none |
| P3 | The next batched G14 test image | G14 start-up and absolute CPU before and after; correctness under `verify` | test image, one approval |
| P4 | The default and the trust model (section 4), recorded before any production enablement | Accept the broader risk with the in-process writer, or build the privileged one; on or off | none |

## 9. Open questions

- **How much compile falls before the first frame.** P2's runner measurement and P3's timeline answer it.
- **The two map inserts** (13% of translator CPU) stay even with the cache, because loaded regions still insert. Cheaper
  structures there are a separate lead: upstream's TODO b/232598137 (`code_pool.h:174`) asks for per-region recovery
  maps.
- **Whether 128 MiB is the right cap** for large games. P3's corpus decides.
