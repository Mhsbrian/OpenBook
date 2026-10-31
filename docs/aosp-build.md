# AOSP 17 build environment, source tree, image build and Cuttlefish boot (Track A, M1b)

Issue ANAL-167, status as of 2026-10-15/16, covers the build container, the source mirror and tree, ccache, and a Soong analysis pass. The image build and the Cuttlefish boot are ANAL-168, in [M1b: build and boot](#m1b-build-aosp_cf_x86_64_pc-and-boot-it-in-cuttlefish-anal-168) below.

## What upstream looks like (checked 2026-10-15)

- **CONFIRMED** (`git ls-remote` and gitiles on `platform/manifest`):
  - `android-latest-release` is `ad156f32` ("Update android-latest-release to android17-release", 2026-06-16).
  - Its `default.xml` has `<default revision="android17-release">`. It points at the moving `android17-release` branch, not at the `android-17.0.0_r1` tag (`5bc9a7ce`). We pin exact revisions with `repo manifest -r` after each sync (see Evidence).
  - The manifest lists 1,087 projects and has no `<include>`.
- **CONFIRMED** (`device/google/cuttlefish/AndroidProducts.mk` at `android17-release`): `aosp_cf_x86_64_pc` (`vsoc_x86_64_only/pc/aosp_cf.mk`) and `aosp_cf_x86_64_desktop` exist. `aosp_cf_x86_64_pc-trunk_staging-userdebug` is in `COMMON_LUNCH_CHOICES`.
- **CONFIRMED** (`build/release/release_configs/`): `trunk_staging`, `cp1a`, `cp2a`, `bp1a`–`bp4a`, `ap2a`–`ap4a`, and `mainline_2026_0[1-4]` exist. lunch shows `cp1a` = Android 16 and `cp2a` = Android 17 (see Verification).

## Mirror or shallow tree: the decision

We measured the size of every project's full history using the `clone.bundle` that googlesource serves for it (HTTP `Content-Length`, 2026-10-15; per-project list in `evidence/2026-10-15-aosp/clone-bundle-sizes.txt`):

| Set | Projects | Full history |
|---|---|---|
| Whole `android-latest-release` manifest | 1,087 | **748 GB** |
| Binary projects (names matching `prebuilt`, plus `external/chromium-webview` and `device/google/cuttlefish_vmm`) | 112 | 651 GB (87%) |
| Source projects | 975 | **97 GB** |

The five biggest projects are all prebuilts: `prebuilts/tools` 127 GB, `prebuilts/rust` 83 GB, `prebuilts/clang/host/linux-x86` 70 GB, `prebuilts/clang/host/darwin-x86` 52 GB and `external/chromium-webview` 45 GB. A full AOSP mirror covers every project in every manifest, not just this one, so it is well above 1 TB. A full mirror of only this manifest (748 GB) would use about 45% of the shared host's free space before any build output, and would take about 4 hours to download at the 51 MB/s we measured. The binary history buys us nothing: we never bisect or patch old prebuilt toolchains.

**Choice: a split.**
- `~/anybook/aosp/mirror`: a `repo --mirror` of the 975 **source** projects, with full history, all branches from the bundles, plus fresh `android17-release` and tags. It is the shared local mirror the agent identity asks for. A second tree (another branch or product) costs almost no download.
- `~/anybook/aosp/src`: the build tree. Source projects use `--reference` to the mirror (git alternates: full history, no second copy). The 112 binary projects are fetched shallow (`clone-depth="1"`) through a generated local manifest (`scripts/aosp-local-manifest.py`).

Rate limits:
- The mirror is seeded from the `clone.bundle` files on `storage.googleapis.com`, not from git fetches. It touches the googlesource git servers only for the delta since each bundle was made.
- The tree fetches only shallow tips for the prebuilts.
- During the sync we saw two HTTP 503s from googlesource: `platform/manifest` `ls-remote`, and `platform/test/vts` in mirror pass 1. Both went through on retry. That is why `aosp-sync.sh` uses `--retry-fetches=5` and retries the whole sync up to 5 times.

Upstream anomaly found on the way: in `platform/external/curl`, `refs/heads/android17-security-release` points at a signed **tag** object (`e2ed3616…`, tagging commit `8db9a00c…`). Git won't write a tag object to a branch ref, so a mirror that fetches all heads (`+refs/heads/*`) of this manifest gets the error `cannot update ref … non-commit object`. To avoid that, the mirror sync uses `-c` (the manifest branch plus tags only). The bundles still carry every branch's history.

## Layout

```
~/anybook/aosp/mirror   source-project mirror (repo --mirror, -c), ~102 GB
~/anybook/aosp/src      build tree: alternates -> mirror, prebuilts depth 1
~/anybook/ccache        ccache, max_size 100 GB, compiler_check=content
~/anybook/logs/aosp/    sync-*.log, verify-*.log, manifest-pinned.xml
```

Don't delete `mirror/` while `src/` exists: the tree's source objects live there.
- repo writes the alternates as container paths (`/aosp/mirror/...`). `aosp-sync.sh` rewrites them as relative paths (the `relink` step), so `git` works on the host and in the container as long as `mirror/` and `src/` stay siblings.
- If you need a standalone tree, run `git repack -a -d` per project, then delete `objects/info/alternates`.

## Container

`tools/Dockerfile.aosp`:
- Ubuntu 24.04, the AOSP host package list from source.android.com, ccache 4.9.1, git 2.43, Python 3.12.
- The `repo` launcher v2.69 is pinned by sha256.
- It runs as the host uid/gid (build args). The image's stock `ubuntu` user (uid 1000) is removed first.

`scripts/aosp-docker.sh` mounts:
- `~/anybook/aosp` at `/aosp`
- `~/anybook/ccache` at `/ccache`
- `~/anybook/logs/aosp` at `/logs`
- the repo, read-only, at `/repo`

**Build sandbox.** Soong runs the build inside nsjail (`build/soong/ui/build/sandbox_linux.go`), and nsjail needs two Docker options:
- `--security-opt seccomp=unconfined`, so it can clone user, mount and pid namespaces.
- `--security-opt systempaths=unconfined`. With only seccomp unconfined, nsjail fails with "procfs can only be mounted if the original /proc doesn't have any other file-systems mounted on top of it", because Docker masks `/proc/kcore` and other paths.

With either option missing, Soong prints `Build sandboxing disabled due to nsjail error` and builds unsandboxed. The container still runs as uid 1000 with no added capabilities. Evidence: `nsjail-probe.txt`.

**ccache.** Android 17 Soong puts `$CC_WRAPPER` in front of every C/C++ compile (`build/soong/cc/config/global.go`, `CcWrapper`) and passes `CC_WRAPPER` and `CCACHE_DIR` through to ninja (`ui/build/dumpvars.go`, `ui/build/ninja.go`). It does **not** read `CCACHE_EXEC`. The image sets `USE_CCACHE=1 CC_WRAPPER=/usr/bin/ccache CCACHE_DIR=/ccache`. The size limit and `compiler_check=content` are stored in `~/anybook/ccache/ccache.conf`. Hit rates can only be measured in the full build (next stage). Until then, ccache's effect on AOSP build time is a **HYPOTHESIS**.

## Commands

```bash
docker build -t anybook-aosp -f tools/Dockerfile.aosp --build-arg UID=$(id -u) --build-arg GID=$(id -g) tools/
scripts/aosp-docker.sh bash -c 'ccache -M 100G && ccache --set-config=compiler_check=content'
# Long job (~47 min here): run it detached and block on it. Re-running resumes.
scripts/aosp-docker.sh -d anybook-aosp-sync /repo/scripts/aosp-sync.sh all
docker wait anybook-aosp-sync        # or: docker logs -f anybook-aosp-sync; cancel: docker stop anybook-aosp-sync
scripts/aosp-docker.sh /repo/scripts/aosp-verify.sh      # envsetup + lunch + m nothing, timed (default target trunk_staging)
scripts/aosp-docker.sh /repo/scripts/aosp-verify.sh aosp_cf_x86_64_pc-cp2a-userdebug
```

Why detached and not `timeout … repo sync` in a loop: one shallow fetch of a large prebuilt is a single multi-GB pack, and git throws away a partial pack when killed. A short `timeout` can kill the same fetch forever. The container name is the cleanup handle, and every step writes a durable log under `~/anybook/logs/aosp/`.

## Measurements (2026-10-16 UTC, Ryzen 9 7950X 16C/32T, 61 GB RAM + 123 GB swap, btrfs zstd:3, link sustained 51 MB/s during the mirror sync)

The host was shared during these runs: other runs were using about 22 GB of RAM and 6 GB of swap. Treat the times as indicative.

| Step | Wall clock | Disk (`du`) | Notes |
|---|---|---|---|
| `docker build` anybook-aosp | 37 s | 1.16 GB image | |
| Mirror pass 1, all heads | 31 min 15 s | 102 GB (95 GB apparent) | about 51 MB/s average. Ended with the `external/curl` tag-as-branch error and one HTTP 503 on `test/vts` |
| Mirror pass 2, `-c` (the committed script) | 41 s | | `repo sync has finished successfully` |
| Tree sync | 15 min 17 s | 128 GB = 105 GB working files + 23 GB `.repo` (shallow prebuilt objects) | 1,084 projects; 976 alternates into the mirror |
| Tree re-sync, no-op | 56 s | | proves resume; pinned manifest unchanged |
| `m nothing`, trunk_staging, cold, no sandbox | 1:25 | `out/` 27 GB | 1,008 s user + 152 s sys (1,360% CPU); max RSS 38.1 GiB |
| `m nothing`, trunk_staging, cold, sandboxed | 1:20 | `out/` 27 GB | 1,005 s user + 101 s sys (1,374% CPU); max RSS 38.9 GiB; container peak 41.6 GiB including page cache |
| `m nothing`, cp2a, Soong already bootstrapped | 1:37 | `out/` 30 GB | 964 s user + 106 s sys (1,103%); max RSS 43.0 GiB; container peak 46.4 GiB |
| **Total so far** | **~50 min** | **~260 GB** (mirror 102 + tree 157 with `out/`) | ccache is empty until the first compile |

What this means for the next stage (the image build):
- Soong analysis alone peaks at 38–43 GiB RSS in `soong_build`. On this 61 GB host, don't run two AOSP analyses at once, and expect a full build to use swap while other runs are active.
- Starting the full build at `-j24` instead of `-j32` is a **HYPOTHESIS** to test.
- Disk: allow another ~250–350 GB for `out/` (Google's guidance is 250 GB checkout + 150 GB build; our checkout is smaller because prebuilt history is shallow), plus up to 100 GB of ccache. That fits in the 1.4 TB currently free.

## Verification

- **Revision:** manifest `ad156f32` (android-latest-release → `android17-release`). `repo info`: "Manifest branch: android17-release", 1,084 projects, groups `default,platform-linux`. Every project's exact SHA is in `manifest-pinned.xml.gz`.
- **History:** in the tree, `frameworks/base` has 1,133,938 commits (full history, through the mirror). `prebuilts/clang/host/linux-x86` is shallow (1 commit). `git log` works on both host and container. `repo status` is clean.
- **lunch `aosp_cf_x86_64_pc-trunk_staging-userdebug`: succeeds.** It reports `BUILD_ID=CP2A.260605.016`, `TARGET_ARCH_VARIANT=silvermont`, and **`PLATFORM_VERSION=Baklava`, `PLATFORM_VERSION_CODENAME=Baklava`**. On this branch, `trunk_staging` produces a pre-release-codename build.
- **lunch `aosp_cf_x86_64_pc-cp2a-userdebug`:** `PLATFORM_VERSION=17`, codename `REL`. `cp1a` gives `PLATFORM_VERSION=16`. **Recommendation for M1b:** build `aosp_cf_x86_64_pc-cp2a-userdebug`. That `cp2a` is the release config behind the `android-17.0.0_r1` builds is a **HYPOTHESIS**: the `CP2A` build ID prefix suggests it, but we haven't checked it against Google's build list. `release-configs.txt` has the comparison.
- **`m nothing`:** `#### build completed successfully ####` for both trunk_staging (sandboxed, cold, 1:19) and cp2a (1:36).
- **ISA:** `silvermont` is the generic x86_64 baseline, so Track A images avoid the AVX-VNNI problem that Google's `pantherlake` Googlebook builds hit on Zen 4 (`docs/PLAN.md` §3.4). Confirmed only from the product variables; nothing has been built or run yet.

Evidence is in `evidence/2026-10-15-aosp/`:
- Sync logs: `sync-mirror-pass1.log`, `sync-all.log`, `sync-relink.log`, `sync-tree-rerun.log`
- Manifest: `manifest-revision.txt`, `manifest-pinned.xml.gz`, `repo-info.txt.gz`
- lunch: `lunch-trunk_staging.txt`, `lunch-cp2a.txt`, `release-configs.txt`
- `m nothing`: `verify-{1,2,3}-*.log.gz`, `time-{1,2,3}-*.txt`
- Environment: `sizes.txt`, `container.txt`, `nsjail-probe.txt`, `clone-bundle-sizes.txt`

## Open items

- ~~ccache use is configured but unproven until the first compile.~~ Proven in ANAL-168 (below).
- The `cp2a` = `android-17.0.0_r1` mapping (above).
- Report the `external/curl` `android17-security-release` tag-as-branch anomaly upstream (AOSP issue tracker). It breaks any all-heads mirror of this manifest.

## M1b: build aosp_cf_x86_64_pc and boot it in Cuttlefish (ANAL-168)

Status as of 2026-10-16. The target is `aosp_cf_x86_64_pc-cp2a-userdebug`, built from the tree above (manifest `ad156f32`). **Result: our own build boots in Cuttlefish to `sys.boot_completed=1` in 17–29 s, with the display up at 1920×1080.**

### Commands

```bash
# Build. Resumable: re-running continues where siso stopped. About 2 h 10 min here, cold, on a shared host.
AOSP_JOBS=32 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh aosp_cf_x86_64_pc-cp2a-userdebug
docker wait anybook-aosp-build          # cancel: docker stop anybook-aosp-build
# Optional: out/dist (img zip, target-files, OTA, cvd-host_package.tar.gz). About 4 min after the build above.
scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh aosp_cf_x86_64_pc-cp2a-userdebug dist

# Boot, wait for boot_completed, capture evidence, tear down. About 45 s here.
scripts/cf-boot.sh                      # = all
CF_HOST_TOOLS=build scripts/cf-boot.sh  # same, but with our build's host tools instead of cvd's packaged ones
# Or step by step, keeping the device up for WebRTC (https://localhost:11443) or adb:
scripts/cf-boot.sh up && scripts/cf-boot.sh wait && scripts/cf-boot.sh capture
docker exec anybook-cf /root/cvd-host/bin/adb -s 127.0.0.1:6520 shell
scripts/cf-boot.sh down
```

Build logs are in `~/anybook/logs/aosp/`:
- `build-<ts>.log`: the console log.
- `time-build-<ts>.txt`: GNU `time -v` output.
- `mem-build-<ts>.csv`: the container cgroup's RAM and swap, plus host `MemAvailable`, sampled every 15 s.
- `ccache-<ts>-{before,after}.txt` and `sizes-build-<ts>.txt`.

Each boot writes to `~/anybook/logs/aosp/cf-<ts>/`, and `cf-latest` links to the newest.

### Build measurements (2026-10-16, 11:04–13:15 UTC)

| | `m` (goal `droid`), cold | `m dist`, after that |
|---|---|---|
| Jobs | `-j32` | `-j32` |
| Actions | 187,648 planned, 183,525 run (siso drops some after restat) | 3,867 |
| Wall clock | **2 h 10 min 32 s** | 4 min 12 s |
| CPU | 142,633 s user + 17,155 s sys, 2,040% (about 20 of 32 threads) | 4,439 s + 542 s, 1,979% |
| Peak RAM (container cgroup) | **41.0 GiB RAM + 18.5 GiB swap** (15 s samples); 56.1 GiB RAM+swap combined; `memory.peak` 43.1 GiB including page cache | 38.3 GiB + 6.7 GiB swap |
| Largest single process | 17.4 GiB RSS | 15.5 GiB RSS |
| ccache | Empty at the start: 82,268 cacheable C/C++ calls, **20,881 hits (25.4%)**, 9.9 GB stored; 5,802 calls uncacheable ("unsupported compiler option") | 149 / 1,162 hits (12.8%) |

Output size (`du` on btrfs zstd:3, so these are compressed sizes; `evidence/2026-10-16-aosp/sizes.txt`):
- `out/` is **137 GB after `m`** and 165 GB after `m dist`. After `dist` that breaks down as `out/soong` 135 GB, `out/host` 6.6 GB, `out/dist` 12 GB and `out/target/product/vsoc_x86_64_only` 8.7 GB.
- ccache adds 9.4 GB.
- The top-level images are 3.6 GB; `super.img` is 1.6 GB sparse.
- `cvd-host_package.tar.gz` is 898 MB and is built by plain `m`.
- In `out/dist`: `-img-builder.zip` 1.05 GB, `-target_files-builder.zip` 2.1 GB, `-symbols-builder.zip` 2.6 GB.

The fingerprint is `generic/aosp_cf_x86_64_pc/vsoc_x86_64_only:17/CP2A.260605.016/eng.builde:userdebug/test-keys`.

Notes:
- **The host was shared.** ANAL-171 kernel builds (`anybook-amd-b*`) and a Digitalis build ran at the same time. The load average stayed at 75–133 on 32 threads, one `docker stats` sample showed the other two containers using about 20 cores, and host `MemAvailable` dropped as low as 4.0 GiB (12:28 UTC). There were no OOM kills. That an idle host would build faster than 2:10 is a **HYPOTHESIS**; it wasn't measured.
- Soong analysis did not run again, because the `cp2a` analysis from ANAL-167's `m nothing` was still valid. These numbers therefore leave out the analysis peak (about 1.5 min at ~43 GiB). A cold tree needs that first.
- The cache started empty, yet 25% of compiles hit it. The likely reason is that the same sources are compiled more than once with identical command lines (host and APEX variants). The benefit for a rebuild from scratch is not measured; measuring it means deleting `out/`.
- `-j32` with swap worked. Swap peaked at 18.5 GiB while the other runs were active, so `-j24` wasn't needed.

### Booting in Cuttlefish

**Container.** `us-docker.pkg.dev/android-cuttlefish-artifacts/cuttlefish-orchestration/cuttlefish-orchestration:1.56.0`, pinned by digest `sha256:ecdb3376…`. That digest is what the `stable` tag pointed to on 2026-10-16; `1.57.0` is the newest tag. Despite the 1.56.0 tag, the image contains the Debian packages `cuttlefish-base`, `cuttlefish-user` and `cuttlefish-orchestration` at **1.57.0** (`cvd` VCS `9bb9c723`), because the image apt-installs whatever is current when it's built.

**Docker flags.**
- `--cap-add NET_ADMIN`
- `--device` for `/dev/kvm`, `/dev/net/tun`, `/dev/vhost-net` and `/dev/vhost-vsock`
- `--security-opt seccomp=unconfined`

There is no `--privileged` and no sudo. Ports are published on 127.0.0.1 only: adb 6520 → 16520, and the WebRTC operator 1443 → 11443.

**Three things the issue's recipe doesn't cover.** We hit all three:
1. **`--host_path` must be writable.** `cvd create` always symlinks its packaged `cvdalloc` into the host tools, so the read-only `out/` mount failed with `symlink(... cvdalloc ...) failed: Read-only file system`. The script unpacks our `cvd-host_package.tar.gz` inside the container instead (7–13 s), and `out/` is never modified.
2. **`--product_path` must be writable.** `assemble_cvd` de-sparses `super.img` in place, and failed with `open('.../super.img.lock') failed: Read-only file system`. The script stages the product's top-level files in `~/anybook/aosp/cf/product` as reflink copies, which copy no data on btrfs, and mounts that. Each boot then costs about 1.5 GB, because `super.img` is rewritten there as an 8 GiB raw sparse file.
3. **Docker's default seccomp profile blocks `socket(AF_VSOCK)`.** `run_cvd` failed with `Can't tombstone server socket`. A Python `AF_VSOCK` bind gets `EPERM` under the default profile and succeeds with `seccomp=unconfined` (checked 2026-10-16). Cuttlefish's host-side vsock servers need it, so this container runs unconfined, the same as the build container does for nsjail.

QEMU wasn't needed.

**Host tools: whose binaries run.** In `cvd` 1.57.0 (`fetch/substitute.cc` at `9bb9c723`), if the host package contains `etc/debian_substitution_marker`, `cvd` symlinks **every** host tool it packages over the host package's copy. AOSP's `cvd-host_package` ships that marker (`device/google/cuttlefish/Android.bp`). By default, then:
- 147 files are swapped, including `run_cvd`, `assemble_cvd`, `crosvm`, `webRTC`, `secure_env` and `adb` (`boot2/host-substitutions.txt`).
- The **guest images** are entirely ours; the **VMM and launcher** are Google's 1.57.0 Debian builds.

`CF_HOST_TOOLS=build` deletes the marker. Then only `cvdalloc` is swapped (`boot3/host-substitutions.txt`), the launcher reports `Launcher Build ID: eng.builde`, and the device boots just as well. Both modes are tested below. The default stays `packaged` because that is the combination Google ships and tests.

**Launch flags.** `--x_res=1920 --y_res=1080 --dpi=160 --gpu_mode=guest_swiftshader --cpus=4 --memory_mb=8192`. The `pc` product has no `--config` preset; `android-info.txt` selects `phone`, which means 720×1280. So the script sets a laptop-sized display. The container has no `/dev/dri`, so rendering is in software. Host-GPU modes (`CF_GPU=amd|nvidia`) came in ANAL-169: see `docs/aosp-desktop.md`.

### Boot results

| | Boot 1 (`up`, `wait`, `capture`) | Boot 2 (`cf-boot.sh`, final committed script) | Boot 3 (`CF_HOST_TOOLS=build cf-boot.sh`) |
|---|---|---|---|
| Time (UTC) | 13:17 | 13:30 | 13:27 |
| Host tools | packaged 1.57.0 | packaged 1.57.0 | **ours** (`eng.builde`) |
| `cvd create` → "Virtual device booted successfully" | 29 s | 18 s | 17 s |
| `sys.boot_completed=1` | yes, at +37 s (first poll) | yes, at +21 s | yes, at +17 s |
| `boot_progress_start` / `boot_progress_enable_screen` / boot animation done, from kernel start | 8.4 s / 18.4 s / 19.7 s | 4.2 s / 9.3 s / 9.7 s | 3.7 s / 9.1 s / 9.7 s |
| Whole cycle: stage, unpack, boot, capture, teardown | n/a | 46 s, exit 0 | 36 s, exit 0 |

Boot 1 was the first boot of these images, 2 minutes after the build finished. Boots 2 and 3 are about twice as fast; a warm page cache is the likely reason (**HYPOTHESIS**).

What the device reports (`boot1/props-summary.txt`, `getprop.txt`, `features.txt`; `features.txt` is identical across all three boots):
- **Build:** `ro.build.version.release=17`, SDK 37, `ro.build.id=CP2A.260605.016`, userdebug, `ro.boot.verifiedbootstate=orange` (test keys, unlocked).
- **Kernel:** `6.12.74-android16-6-g3ec022196c4e-ab15076761`. The Cuttlefish product boots Google's **prebuilt android16-6.12 GKI**, not the android17-6.18 kernel that Googlebook ships (ANAL-170). Swapping in our kernel belongs to ANAL-171/172.
- **Features:** `feature:android.hardware.type.pc` and `android.software.freeform_window_management` are present. `ro.build.characteristics=default` (neither `tablet` nor `pc`).
- **Display:** 1920×1080 at 160 dpi. Launcher3 (`QuickstepLauncher`) is the resumed activity, in fullscreen windowing mode. Screenshots: `boot1/screen.png` (lock screen) and `boot1/screen-home.png` (home screen after `wm dismiss-keyguard`).
- **Graphics stack in this mode:** `ro.hardware.egl=angle`, `ro.hardware.vulkan=pastel`, gralloc `minigbm`, HWC `ranchu`, `feature:android.hardware.vulkan.level=1`. Vulkan version 4206592 = 1.4.0.
- **ARM: advertised but not present.** `ro.product.cpu.abilist=x86_64,arm64-v8a`, because `vsoc_x86_64_only/BoardConfig.mk` sets `TARGET_NATIVE_BRIDGE_ARCH := arm64`. But `ro.dalvik.vm.native.bridge=0`, and there is no translator library in `/system`. We checked with the ANAL-180 probe APKs (`boot1/arm64-probe-check.txt`):
  - The x86_64 probe runs: 17 pass / 0 fail / 2 skip.
  - The arm64-only probe **installs** (`primaryCpuAbi=arm64-v8a`), then fails at `dlopen` with `libprobe.so is for EM_AARCH64 (183) instead of EM_X86_64 (62)`.

  So a plain AOSP build accepts arm64-only apps it can't run. Either a translator (ANAL-181) or dropping `arm64-v8a` from the abilist is needed.

Evidence is in `evidence/2026-10-16-aosp/`:
- `build/`: the console log (`build-*.log.gz`), GNU time output, memory samples (`mem-build-*.csv.gz`), and ccache stats before and after.
- `build-dist/`: the same for `m dist`, plus `dist-listing.txt`.
- `sizes.txt`
- `boot1/`:
  - Launch: `cf-boot.log`, `cvd-create.log`, `cvd-fleet.json`
  - Device state: `props-summary.txt`, `getprop.txt`, `features.txt`, `display.txt`, `boot-progress.txt`, `uname.txt`
  - Logs: `dmesg.txt.gz`, `logcat.txt.gz`, `kernel.log.gz` (guest console), `launcher.log.gz` (host)
  - The two screenshots and `arm64-probe-check.txt`
- `boot2/` (packaged host tools) and `boot3/` (our host tools): the scripted end-to-end runs, each with `host-substitutions.txt` and the host launcher log.

### Open items (M1b)

- **Native-bridge mismatch.** The abilist advertises `arm64-v8a`, but no bridge is present. Decide in ANAL-181 whether to ship a translator or drop the ABI.
- **Kernel.** The product boots the prebuilt android16-6.12 GKI. Booting our android17-6.18 build in Cuttlefish is for ANAL-171/172.
- **seccomp.** A narrower profile (Docker's default plus `AF_VSOCK`) would be tighter than `seccomp=unconfined`. Not done yet.
- **Unmeasured:** build time on an idle host, and the ccache benefit on a rebuild from scratch.
