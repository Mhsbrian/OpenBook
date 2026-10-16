# AOSP 17 build environment and source tree (Track A, M1b prep)

Issue ANAL-167. Status as of 2026-10-15/16. This stage covers the build container, the source mirror and tree, ccache, and a Soong analysis pass. It does not build the image; that is the next stage.

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

- ccache use is configured but unproven until the first compile, which is the next stage.
- The `cp2a` = `android-17.0.0_r1` mapping (above).
- Report the `external/curl` `android17-security-release` tag-as-branch anomaly upstream (AOSP issue tracker). It breaks any all-heads mirror of this manifest.
