# AOSP 17 build environment, source tree, image build and Cuttlefish boot (Track A, M1b)

This covers the AOSP build container, the source mirror and build tree, ccache, the Soong sandbox (ANAL-167), and
building `aosp_cf_x86_64_pc` and booting it in Cuttlefish (ANAL-168, [M1b](#m1b-build-aosp_cf_x86_64_pc-and-boot-it-in-cuttlefish-anal-168)).
The OpenBook products build on the same tree; their commands are in [`BUILD.md`](BUILD.md). Measurements are from
2026-10-15/16 unless stated. Guesses are labelled **HYPOTHESIS**.

## What upstream looks like (checked 2026-10-15)

- **CONFIRMED** (`git ls-remote` and gitiles on `platform/manifest`):
  - `android-latest-release` is `ad156f32` ("Update android-latest-release to android17-release", 2026-06-16).
  - Its `default.xml` has `<default revision="android17-release">`. It points at the moving `android17-release`
    branch, not at the `android-17.0.0_r1` tag (`5bc9a7ce`). So every project's exact revision is pinned with
    `repo manifest -r` after a sync, in `manifests/aosp/manifest-pinned.xml.gz`.
  - The manifest lists 1,087 projects and has no `<include>`.
- **CONFIRMED** (`device/google/cuttlefish/AndroidProducts.mk` at `android17-release`): `aosp_cf_x86_64_pc`
  (`vsoc_x86_64_only/pc/aosp_cf.mk`) and `aosp_cf_x86_64_desktop` exist. `aosp_cf_x86_64_pc-trunk_staging-userdebug`
  is in `COMMON_LUNCH_CHOICES`.
- **CONFIRMED** (`build/release/release_configs/`): `trunk_staging`, `cp1a`, `cp2a`, `bp1a`–`bp4a`, `ap2a`–`ap4a`,
  and `mainline_2026_0[1-4]` exist. lunch shows `cp1a` = Android 16 and `cp2a` = Android 17 (see
  [Verification](#verification)).

## Mirror or shallow tree: the decision

The size of every project's full history, from the `clone.bundle` googlesource serves for it (HTTP `Content-Length`,
2026-10-15):

| Set | Projects | Full history |
|---|---|---|
| Whole `android-latest-release` manifest | 1,087 | **748 GB** |
| Binary projects (names matching `prebuilt`, plus `external/chromium-webview` and `device/google/cuttlefish_vmm`) | 112 | 651 GB (87%) |
| Source projects | 975 | **97 GB** |

The five biggest projects are all prebuilts: `prebuilts/tools` 127 GB, `prebuilts/rust` 83 GB,
`prebuilts/clang/host/linux-x86` 70 GB, `prebuilts/clang/host/darwin-x86` 52 GB and `external/chromium-webview`
45 GB. A full AOSP mirror covers every project in every manifest, so it is well above 1 TB. A mirror of only this
manifest (748 GB) would take about 4 hours at 51 MB/s, before any build output. The binary history buys nothing:
OpenBook never bisects or patches old prebuilt toolchains.

**Choice: a split.** Reason: full source history for a fraction of the disk.
- `~/anybook/aosp/mirror`: a `repo --mirror` of the 975 **source** projects, with full history, all branches from the
  bundles, plus fresh `android17-release` and tags. A second tree (another branch or product) costs almost no
  download.
- `~/anybook/aosp/src`: the build tree. Source projects use `--reference` to the mirror (git alternates: full
  history, no second copy). The 112 binary projects are fetched shallow (`clone-depth="1"`) through a generated
  local manifest (`scripts/aosp-local-manifest.py`).

Rate limits:
- The mirror is seeded from the `clone.bundle` files on `storage.googleapis.com`, not from git fetches. It touches
  the googlesource git servers only for the delta since each bundle was made.
- The tree fetches only shallow tips for the prebuilts.
- googlesource answers HTTP 503 now and then (seen on `platform/manifest` `ls-remote` and `platform/test/vts`). So
  `aosp-sync.sh` uses `--retry-fetches=5` and retries the whole sync up to 5 times.

**Upstream anomaly.** In `platform/external/curl`, `refs/heads/android17-security-release` points at a signed **tag**
object (`e2ed3616…`, tagging commit `8db9a00c…`). Git won't write a tag object to a branch ref, so a mirror that
fetches all heads (`+refs/heads/*`) of this manifest fails with `cannot update ref … non-commit object`. The mirror
sync therefore uses `-c` (the manifest branch plus tags only). The bundles still carry every branch's history.

## Layout

```
~/anybook/aosp/mirror   source-project mirror (repo --mirror, -c), ~102 GB
~/anybook/aosp/src      build tree: alternates -> mirror, prebuilts depth 1
~/anybook/ccache        ccache, max_size 100 GB, compiler_check=content
~/anybook/logs/aosp/    sync-*.log, verify-*.log, build-*.log, manifest-pinned.xml and manifest-revision.txt of the last sync
```

Don't delete `mirror/` while `src/` exists: the tree's source objects live there.
- repo writes the alternates as container paths (`/aosp/mirror/...`). `aosp-sync.sh` rewrites them as relative paths
  (the `relink` step), so `git` works on the host and in the container as long as `mirror/` and `src/` stay siblings.
- If you need a standalone tree, run `git repack -a -d` per project, then delete `objects/info/alternates`.
- A sync follows the moving `android17-release` branch. The committed pin is `manifests/aosp/manifest-pinned.xml.gz`;
  `scripts/aosp-patches.sh` applies OpenBook's patches on top of each project's pinned revision. Moving the pin is
  described in `manifests/README.md`.

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

**Build sandbox.** Soong runs the build inside nsjail (`build/soong/ui/build/sandbox_linux.go`), and nsjail needs two
Docker options:
- `--security-opt seccomp=unconfined`, so it can clone user, mount and pid namespaces.
- `--security-opt systempaths=unconfined`. With only seccomp unconfined, nsjail fails with "procfs can only be
  mounted if the original /proc doesn't have any other file-systems mounted on top of it", because Docker masks
  `/proc/kcore` and other paths.

With either option missing, Soong prints `Build sandboxing disabled due to nsjail error` and builds unsandboxed. The
container still runs as the host uid with no added capabilities.

**ccache.** Android 17 Soong puts `$CC_WRAPPER` in front of every C/C++ compile (`build/soong/cc/config/global.go`,
`CcWrapper`) and passes `CC_WRAPPER` and `CCACHE_DIR` through to ninja (`ui/build/dumpvars.go`, `ui/build/ninja.go`).
It does **not** read `CCACHE_EXEC`. The image sets `USE_CCACHE=1 CC_WRAPPER=/usr/bin/ccache CCACHE_DIR=/ccache`. The
size limit and `compiler_check=content` are stored in `~/anybook/ccache/ccache.conf`. It works: the first cold build
hit 25% of compiles with an empty cache ([M1b](#build-cost)).

## Commands

```bash
docker build -t anybook-aosp -f tools/Dockerfile.aosp --build-arg UID=$(id -u) --build-arg GID=$(id -g) tools/
scripts/aosp-docker.sh bash -c 'ccache -M 100G && ccache --set-config=compiler_check=content'
# Long job (~47 min): run it detached and block on it. Re-running resumes.
scripts/aosp-docker.sh -d anybook-aosp-sync /repo/scripts/aosp-sync.sh all
docker wait anybook-aosp-sync        # or: docker logs -f anybook-aosp-sync; cancel: docker stop anybook-aosp-sync
scripts/aosp-docker.sh /repo/scripts/aosp-verify.sh      # envsetup + lunch + m nothing, timed (default target trunk_staging)
scripts/aosp-docker.sh /repo/scripts/aosp-verify.sh aosp_cf_x86_64_pc-cp2a-userdebug
```

Why detached and not `timeout … repo sync` in a loop: one shallow fetch of a large prebuilt is a single multi-GB
pack, and git throws away a partial pack when killed. A short `timeout` can kill the same fetch forever. The
container name is the cleanup handle, and every step writes a durable log under `~/anybook/logs/aosp/`.

## Sizing

Measured 2026-10-15/16 on a Ryzen 9 7950X (16C/32T), 61 GB RAM + 123 GB swap, btrfs zstd:3 (so `du` sizes are
compressed), at 51 MB/s. The host was shared with other builds, so treat times as indicative.

| Step | Wall clock | Disk (`du`) | Peak memory |
|---|---|---|---|
| `docker build` anybook-aosp | 37 s | 1.16 GB image | |
| Mirror, first sync | ~31 min | 102 GB (95 GB apparent) | |
| Tree sync | ~15 min | 128 GB: 105 GB working files + 23 GB `.repo` (shallow prebuilt objects) | |
| Re-sync, nothing new | ~1 min | | |
| `m nothing` (Soong analysis), cold | 1:20–1:37 | `out/` 27–30 GB | 38–43 GiB RSS in `soong_build`; container up to 46 GiB with page cache |
| Full build, `out/` and ccache | see [M1b](#build-cost) | `out/` 137 GB, 165 GB with `dist`; ccache ~10 GB | 41 GiB RAM + 18.5 GiB swap |

What this means:
- Don't run two AOSP analyses or builds at once on a 61 GB host. That is why builds share one lane lock
  ([`BUILD.md`](BUILD.md)).
- Disk for one tree: mirror 102 GB + tree 128 GB + `out/` up to 165 GB + ccache up to 100 GB, about 500 GB.

## Verification

- **Revision:** manifest `ad156f32` (android-latest-release → `android17-release`). `repo info`: "Manifest branch:
  android17-release", 1,084 projects, groups `default,platform-linux`. Every project's exact SHA is in
  `manifests/aosp/manifest-pinned.xml.gz`.
- **History:** in the tree, `frameworks/base` has 1,133,938 commits (full history, through the mirror).
  `prebuilts/clang/host/linux-x86` is shallow (1 commit). `git log` works on both host and container.
- **lunch `aosp_cf_x86_64_pc-trunk_staging-userdebug`: succeeds,** but reports `BUILD_ID=CP2A.260605.016`,
  `TARGET_ARCH_VARIANT=silvermont`, and **`PLATFORM_VERSION=Baklava`, `PLATFORM_VERSION_CODENAME=Baklava`**. On this
  branch, `trunk_staging` produces a pre-release-codename build.
- **lunch `aosp_cf_x86_64_pc-cp2a-userdebug`:** `PLATFORM_VERSION=17`, codename `REL`. `cp1a` gives
  `PLATFORM_VERSION=16`. **Decision: build with `cp2a`.** Reason: it is the release config that gives Android 17 `REL`.
  That `cp2a` is the release config behind the `android-17.0.0_r1` builds is a **HYPOTHESIS**: the `CP2A` build ID
  prefix suggests it, but it is not checked against Google's build list.
- **`m nothing`:** `#### build completed successfully ####` for both trunk_staging and cp2a.
- **ISA:** `silvermont` is the generic x86_64 baseline, so Track A images avoid the AVX-VNNI problem that Google's
  `pantherlake` Googlebook builds hit on Zen 4 (`docs/PLAN.md` §3.4).

## M1b: build aosp_cf_x86_64_pc and boot it in Cuttlefish (ANAL-168)

The target is `aosp_cf_x86_64_pc-cp2a-userdebug`, built from the tree above (manifest `ad156f32`). It is Google's
plain PC Cuttlefish product, the baseline the OpenBook products started from. **It boots in Cuttlefish to
`sys.boot_completed=1` in 17–37 s, with the display up at 1920×1080** (2026-10-16).

### Commands

```bash
# Build. Resumable: re-running continues where siso stopped. About 2 h 10 min cold on a shared host.
AOSP_JOBS=32 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh aosp_cf_x86_64_pc-cp2a-userdebug
docker wait anybook-aosp-build          # cancel: docker stop anybook-aosp-build
# Optional: out/dist (img zip, target-files, OTA, cvd-host_package.tar.gz). About 4 min after the build above.
scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh aosp_cf_x86_64_pc-cp2a-userdebug dist

# Boot, wait for boot_completed, capture, tear down. About 45 s.
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

### Build cost

One cold build at `-j32`, 2026-10-16, on a host shared with kernel and Digitalis builds (load average 75–133 on 32
threads, host `MemAvailable` down to 4 GiB, no OOM kills):

| | `m` (goal `droid`), cold | `m dist`, after that |
|---|---|---|
| Actions | 187,648 planned, 183,525 run | 3,867 |
| Wall clock | **2 h 10 min** | 4 min |
| CPU | about 20 of 32 threads busy on average | about the same |
| Peak memory (container cgroup) | **41.0 GiB RAM + 18.5 GiB swap**; largest process 17.4 GiB RSS | 38.3 GiB + 6.7 GiB swap |
| ccache | empty at the start; **25% of 82,268 cacheable calls hit**, 9.9 GB stored; 5,802 calls uncacheable ("unsupported compiler option") | 13% |

- `-j32` with swap works on a 61 GB host; `-j24` was not needed.
- Soong analysis did not rerun in this build. A cold tree adds about 1.5 min at ~43 GiB first.
- The likely reason for hits on an empty cache: the same sources are compiled more than once with identical command
  lines (host and APEX variants).
- Unmeasured: the build time on an idle host (**HYPOTHESIS:** faster than 2:10) and the ccache benefit on a rebuild
  from scratch.

Output size (compressed `du`):
- `out/` is **137 GB after `m`** and 165 GB after `m dist`: `out/soong` 135 GB, `out/host` 6.6 GB, `out/dist` 12 GB,
  `out/target/product/vsoc_x86_64_only` 8.7 GB.
- The top-level images are 3.6 GB; `super.img` is 1.6 GB sparse.
- `cvd-host_package.tar.gz` is 898 MB and is built by plain `m`.
- In `out/dist`: `-img-builder.zip` 1.05 GB, `-target_files-builder.zip` 2.1 GB, `-symbols-builder.zip` 2.6 GB.

The fingerprint is `generic/aosp_cf_x86_64_pc/vsoc_x86_64_only:17/CP2A.260605.016/eng.builde:userdebug/test-keys`.

### Booting in Cuttlefish

**Container.** `us-docker.pkg.dev/android-cuttlefish-artifacts/cuttlefish-orchestration/cuttlefish-orchestration:1.56.0`,
pinned by digest `sha256:ecdb3376…`. That digest is what the `stable` tag pointed to on 2026-10-16. Despite the
1.56.0 tag, the image contains the Debian packages `cuttlefish-base`, `cuttlefish-user` and `cuttlefish-orchestration`
at **1.57.0** (`cvd` VCS `9bb9c723`), because the image apt-installs whatever is current when it's built.

**Docker flags.**
- `--cap-add NET_ADMIN`
- `--device` for `/dev/kvm`, `/dev/net/tun`, `/dev/vhost-net` and `/dev/vhost-vsock`
- `--security-opt seccomp=unconfined`

There is no `--privileged` and no sudo. Ports are published on 127.0.0.1 only: adb 6520 → 16520, and the WebRTC
operator 1443 → 11443. QEMU isn't needed.

**Three gotchas the usual recipe doesn't cover:**
1. **`--host_path` must be writable.** `cvd create` always symlinks its packaged `cvdalloc` into the host tools, so a
   read-only `out/` mount fails with `symlink(... cvdalloc ...) failed: Read-only file system`. The script unpacks our
   `cvd-host_package.tar.gz` inside the container instead (7–13 s), and `out/` is never modified.
2. **`--product_path` must be writable.** `assemble_cvd` de-sparses `super.img` in place, and fails with
   `open('.../super.img.lock') failed: Read-only file system`. The script stages the product's top-level files in
   `~/anybook/aosp/cf/product` as reflink copies, which copy no data on btrfs, and mounts that. Each boot then costs
   about 1.5 GB, because `super.img` is rewritten there as an 8 GiB raw sparse file.
3. **Docker's default seccomp profile blocks `socket(AF_VSOCK)`.** `run_cvd` fails with `Can't tombstone server
   socket`. A Python `AF_VSOCK` bind gets `EPERM` under the default profile and succeeds with `seccomp=unconfined`.
   Cuttlefish's host-side vsock servers need it, so this container runs unconfined, as the build container does for
   nsjail.

**Host tools: whose binaries run.** In `cvd` 1.57.0 (`fetch/substitute.cc` at `9bb9c723`), if the host package
contains `etc/debian_substitution_marker`, `cvd` symlinks **every** host tool it packages over the host package's
copy. AOSP's `cvd-host_package` ships that marker (`device/google/cuttlefish/Android.bp`). By default, then:
- 147 files are swapped, including `run_cvd`, `assemble_cvd`, `crosvm`, `webRTC`, `secure_env` and `adb`.
- The **guest images** are entirely ours; the **VMM and launcher** are Google's 1.57.0 Debian builds.

`CF_HOST_TOOLS=build` deletes the marker. Then only `cvdalloc` is swapped, the launcher reports `Launcher Build ID:
eng.builde`, and the device boots just as well. **The default stays `packaged`.** Reason: that is the combination
Google ships and tests.

**Launch flags.** `--x_res=1920 --y_res=1080 --dpi=160 --gpu_mode=guest_swiftshader --cpus=4 --memory_mb=8192`. The
`pc` product has no `--config` preset; `android-info.txt` selects `phone`, which means 720×1280. So the script sets a
laptop-sized display. Without `/dev/dri` in the container, rendering is in software. Host-GPU modes
(`CF_GPU=amd|nvidia`) are in `docs/aosp-desktop.md`.

**Boot times** (three boots, packaged and our own host tools alike): `cvd create` to "Virtual device booted
successfully" 17–29 s; `sys.boot_completed=1` by +17 to +37 s; from kernel start, `boot_progress_enable_screen` at
9.1–18.4 s. The whole scripted cycle (stage, unpack, boot, capture, teardown) takes 36–46 s. The first boot after a
build is about twice as slow; a cold page cache is the likely reason (**HYPOTHESIS**).

### What the device reports

- **Build:** `ro.build.version.release=17`, SDK 37, `ro.build.id=CP2A.260605.016`, userdebug,
  `ro.boot.verifiedbootstate=orange` (test keys, unlocked).
- **Kernel:** `6.12.74-android16-6-g3ec022196c4e-ab15076761`. This product boots Google's **prebuilt android16-6.12
  GKI**, not the android17-6.18 kernel that Googlebook ships. The OpenBook kernel in Cuttlefish is in
  [`kernel.md`](kernel.md) (ANAL-172).
- **Features:** `feature:android.hardware.type.pc` and `android.software.freeform_window_management` are present.
  `ro.build.characteristics=default` (neither `tablet` nor `pc`).
- **Display:** 1920×1080 at 160 dpi. Launcher3 (`QuickstepLauncher`) is the resumed activity, in fullscreen windowing
  mode. The lock screen shows first; `wm dismiss-keyguard` gets to the home screen.
- **Graphics stack in this mode:** `ro.hardware.egl=angle`, `ro.hardware.vulkan=pastel`, gralloc `minigbm`, HWC
  `ranchu`, `feature:android.hardware.vulkan.level=1`. Vulkan version 4206592 = 1.4.0.
- **ARM: advertised but not present.** `ro.product.cpu.abilist=x86_64,arm64-v8a`, because
  `vsoc_x86_64_only/BoardConfig.mk` sets `TARGET_NATIVE_BRIDGE_ARCH := arm64`. But `ro.dalvik.vm.native.bridge=0`,
  and there is no translator library in `/system`. With the ANAL-180 probe APKs:
  - The x86_64 probe runs: 17 pass / 0 fail / 2 skip.
  - The arm64-only probe **installs** (`primaryCpuAbi=arm64-v8a`), then fails at `dlopen` with `libprobe.so is for
    EM_AARCH64 (183) instead of EM_X86_64 (62)`.

  So a plain AOSP build accepts arm64-only apps it can't run. The OpenBook products ship the Digitalis bridge
  (ANAL-200, `docs/digitalis.md`).

## Open items

- **The `cp2a` = `android-17.0.0_r1` mapping** (above) is unconfirmed.
- **Report the `external/curl` tag-as-branch anomaly upstream** (AOSP issue tracker). It breaks any all-heads mirror
  of this manifest.
- **seccomp.** A narrower profile (Docker's default plus `AF_VSOCK`) would be tighter than `seccomp=unconfined`. Not
  done yet.
- **Unmeasured:** build time on an idle host, and the ccache benefit on a rebuild from scratch.
