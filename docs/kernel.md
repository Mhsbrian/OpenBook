# Kernel: reproducing the Googlebook OS GKI build

Status as of 2026-10-15 (ANAL-170). Every claim below has a log or a report in `evidence/2026-10-15-kernel/`. Guesses are labelled **HYPOTHESIS**.

## Results

- **Googlebook OS ships the public GKI kernel, unmodified.** The ruby `boot_a` kernel (from M0) is byte-identical to the `bzImage` of ci.android.com build **16302624**, target `kernel_x86_64`, branch `aosp_kernel-common-android17-6.18-2026-06`. Both have sha256 `7816c5d5…7f41`. The shipped `.config` is also byte-identical to that build's `kernel_x86_64_dot_config`: sha256 `046971f3…be40` (`repro-gbos-16302624-ab16302624-vs-ci.txt`).
- **The branch.** `kernel/manifest` `common-android17-6.18` exists; it is the development tip. The shipped kernel comes from the monthly GKI release branch **`common-android17-6.18-2026-06`**. CI published that build's repo manifest, which is now `manifests/kernel/gbos-16302624.xml`. It pins `common` at `3938c8d97142d5cf31543aa96f864a2cf832dda0` and `build/kernel` at `5877a401…`.
- **Is `3938c8d97142` reachable?** Yes from `android17-6.18-2026-06`. No from the `android17-6.18` tip and no from `android17-6.18-2026-09` (`common-provenance-*.txt`).
  - It sits 330 commits past the merge-base with `android17-6.18` (`0a24e2b8d9a0`, 2026-06-01). Most of those are backports: pKVM GSMI mediation, fuse-bpf fixes, LTS picks.
  - The `-2026-06` branch is now 80 commits past the shipped SHA.
- **Our local Kleaf build matches.** We built from the pinned manifest with `tools/bazel run --config=stamp //common:kernel_x86_64_dist`:
  - The `.config` is byte-identical to the shipped one.
  - `vmlinux.symvers` (KMI CRCs), `abi_symbollist`, `modules.builtin` and `system_dlkm.modules.load` are identical to CI's.
  - The default build has release string `6.18.21-android17-5-g3938c8d97142`. CI appends `-ab16302624` because it sets `BUILD_NUMBER`.
  - We ran one comparison build with `BUILD_NUMBER=16302624`, for measurement only. It was never published or flashed. In that build `System.map` is identical, and the decompressed `vmlinux` differs from Google's in **1,098 of 62,561,848 bytes**:
    - 1,078 bytes in `system_certificate_list`, the module-signing certificate each build generates;
    - 20 bytes of GNU build ID.
  - Everything else, including code, data and layout, is bit-for-bit the same.
- **Config diff: Google turned nothing on or off beyond `gki_defconfig`.** Our build from `gki_defconfig` alone gives the shipped config: 0 symbols differ, and all 749 `gki_defconfig` lines stick. `//common:kernel_x86_64` uses no defconfig fragments (`common/BUILD.bazel:323`), and CI passed no `--gki_build_config_fragment`.
  - **`CONFIG_PKVM_INTEL=y` is set in the GKI defconfig.** It is `gki_defconfig:100`, added by `002e9fb54954` "ANDROID: GKI: x86: Enable pKVM support on Intel" (2026-02-14). It only compiles pKVM in. The hypervisor starts only with `kvm-intel.pkvm=1`, which Googlebook's vendor cmdline sets. pKVM exists only for Intel VMX (`arch/x86/kvm/pkvm/`); `arch/x86/kvm/svm/` has no pKVM code.
  - **`CONFIG_X86_FRED=y` is in neither the defconfig nor a fragment.** It is selected by `KVM_INTEL` (`arch/x86/kvm/Kconfig:99`, `select X86_FRED if X86_64`). That line comes from upstream Linux commit `28d11e4548b7` "x86/fred: KVM: VMX: Always use FRED for IRQs when CONFIG_X86_FRED=y". `gki_defconfig:99` sets `KVM_INTEL=y`. FRED needs CPU support. The Ryzen 9 7950X doesn't advertise it (no `fred` flag in `/proc/cpuinfo`), so on that CPU the code is compiled in but the hardware path stays unused, even with `fred=on` on the cmdline.
- **It boots.** Our bzImage boots under QEMU/KVM `-cpu host` on the Ryzen 9 7950X with Googlebook's ramdisks (`boot-summary.txt`):
  - Version line `Linux version 6.18.21-android17-5-g3938c8d97142`.
  - The same 31 services start as with the stock kernel, and boot stalls at the same `keystore2` point (blocker 1 in `docs/PLAN.md`).
  - There were no `invalid opcode` traps and no panic.
- **Google's GKI modules don't load on our kernel.** `rust_binder` and `zsmalloc` from the shipped image fail with `Unresolved symbol … (err -13)`:
  - Each build trusts only its own signing key. Under `MODULE_SIG_PROTECT`, a GKI module signed by another build counts as unsigned, and unsigned modules can't use protected symbols. Init falls back to the built-in C binder.
  - Google's vendor modules (`pinctrl-intel`, `i2c-i801`, `intel_rapl_msr` and others) do load. They are unprotected, and their KMI CRCs match.
  - So **boot, `system_dlkm` and our own vendor modules must ship from the same build.** This confirms `docs/PLAN.md`.
- **The tip moved on.** `android17-6.18` at `70a231d0d37b` (2026-10-15) is Linux 6.18.32 and builds as `6.18.32-android17-5-g70a231d0d37b`.
  - Its config differs from the shipped one in 15 symbols: 8 new `gki_defconfig` lines (`ANDROID_WRAPFD`, `CGROUP_FAVOR_DYNMODS`, `EFIVAR_FS`, `HID_HAPTIC`, `NET_APF`, `NINTENDO_FF`, `PAGE_PINNER`, `SW_SYNC`) plus symbols derived from them.
  - None of the 4,038 symbols on the shipped KMI list changed CRC or disappeared. The 10 changed and 3 removed exports are Rust `kernel`-crate symbols outside the list (`kmi-shipped-vs-android17-6.18-tip.txt`).

## Build steps

Host requirements: Docker, with no sudo. `tools/Dockerfile.kernel` is Ubuntu 24.04 with repo, git and python3. Kleaf brings its own clang 22.0.1, Rust, Bazel and build tools from the synced prebuilts.

```bash
scripts/kernel-sync.sh                      # default target gbos-16302624: the exact shipped sources
scripts/kernel-sync.sh android17-6.18       # or the branch tip (any kernel/manifest common-<X> works)
scripts/kernel-build.sh                     # -> ~/anybook/kernel/dist/<target>/
BUILD_NUMBER=16302624 scripts/kernel-build.sh   # comparison only: same release string as Google's CI build

scripts/kernel-fetch-ci.sh 16302624         # Google's public CI artifacts -> ~/anybook/kernel/ci/16302624/
scripts/kernel-compare.py ~/anybook/kernel/dist/gbos-16302624-ab16302624 ~/anybook/kernel/ci/16302624 \
    ~/anybook/work/gbos-ruby/boot_a/kernel  # artifact identity, System.map, vmlinux byte attribution
scripts/kernel-config-diff.py ~/anybook/kernel/dist/gbos-16302624/dot_config \
    evidence/2026-10-15-m0/gbos-kernel-config.txt \
    ~/anybook/kernel/src/common/arch/x86/configs/gki_defconfig ~/anybook/kernel/src/common
scripts/kernel-kmi-diff.py OLD/vmlinux.symvers NEW/vmlinux.symvers OLD/abi_symbollist
scripts/kernel-boot-test.sh ~/anybook/kernel/dist/gbos-16302624/bzImage   # needs M0's unpacked ruby image
```

- **How the scripts run.** `kernel-sync.sh` and `kernel-build.sh` re-run themselves inside the `anybook-kernel` container through `scripts/kernel-docker.sh`. That builds the image on first use. It mounts `~/anybook/kernel` and `~/anybook/logs/kernel` at the same paths, and uses `~/anybook/kernel/home` as `HOME`.
- **Long steps.** Set `KERNEL_DETACH=<name>` to run a step as a detached container, so it survives a shell timeout. Collect it with `docker wait <name>; docker rm <name>`.
- **Resuming.** Both scripts can be rerun after an interruption. `repo sync` resumes, and Bazel keeps its action cache in `src/out`.
- **Layout.** One source tree: `~/anybook/kernel/src`. Switching targets is a `repo init` plus sync, which takes seconds once the objects are present. `src/.anybook-target` names the current target.
- **Pins.** `~/anybook/kernel/pins/<target>.xml` holds the `repo manifest -r` of what was synced. Each dist dir records it again, together with `common-provenance.txt`, `linux_banner.txt`, `dot_config` (the IKCONFIG extracted from the built bzImage), `build-time.txt` and `sha256.txt`.
- **Dist contents.** Each `dist/<label>/` holds `bzImage`, `vmlinux`, `boot.img`, `system_dlkm.*.img`, 100 GKI modules, `abi_symbollist`, `vmlinux.symvers`, `kernel-headers.tar.gz` and DDK archives. That is 613 MB per build.
- **googlesource rate limiting.** It answered HTTP 503 during the second sync. The sync retries with backoff; `SYNC_JOBS=2` got through.

### Timings and resources (Ryzen 9 7950X, 32 threads, 61 GB RAM)

| Step | Wall time | Notes |
|---|---|---|
| `kernel-sync.sh gbos-16302624`, cold | 597 s | 44 GB tree, `-j8` |
| `kernel-sync.sh android17-6.18` after that | 83 s | incremental, `-j2` |
| `kernel-build.sh` gbos-16302624, cold Bazel cache | 337 s | 1,412 actions; critical path 324 s, almost all of it the single `Building kernel (trim)` action |
| `kernel-build.sh` gbos-16302624 with `BUILD_NUMBER=16302624` | 431 s | 18 actions; the stamp change reruns the kernel action |
| `kernel-build.sh` android17-6.18 | 307 s | 35 actions |

- **For comparison:** Google's CI spent 785 s on `kernel_x86_64_abi_dist` plus tests, 1,966 actions (`logs/build.log` of build 16302624). That is a bigger target than ours.
- **Disk:** the source tree is 53 GB with both targets fetched (`.repo` 22 GB, `prebuilts` 19 GB). The Bazel cache in `src/out` is 8.7 GB, plus 0.6 GB per dist.
- **RAM:** peak use was not measured. GNU time only sees the Bazel client. The host had about 44 GB available throughout, with no swapping noticed.
- **Sandbox:** Bazel used `processwrapper-sandbox`, because linux-sandbox's namespaces are not available in Docker's default profile. CI used `linux-sandbox`. The outputs still match.
- **Benign warnings:** `diff: Unknown option 'I'` warnings in `modules_prepare` come from the hermetic toybox `diff`. They appear in Google's CI log too, 24 times.

## KMI symbol list (for the AMD stage)

- **Location.** The lists live in `common/gki/x86_64/symbols/`. At 3938c8d97142 these are:
  - `base` (5 lines)
  - `desktop` (3,725), the list Googlebook's Intel vendor modules use; the tip has 3,803
  - `kunit` (41)
  - `virtual_device` (1,341)

  The build merges them into `dist/abi_symbollist`. The ABI definition is `common/gki/x86_64/abi.stg`, with approved breaks in `abi.stg.allowed_breaks`.
- **Wiring.** `common/BUILD.bazel` sets the following on `kernel_x86_64`:
  - `kmi_symbol_list = "gki/x86_64/symbols/base"`
  - `additional_kmi_symbol_lists = [":x86_64_additional_kmi_symbol_lists"]`, a filegroup listing `desktop`, `kunit` and `virtual_device`
  - `trim_nonlisted_kmi = True`, which is `CONFIG_TRIM_UNUSED_KSYMS`
  - `kmi_symbol_list_strict_mode = True`
  - `kmi_enforced = True`

  Only listed symbols are exported. That is why an out-of-tree amdgpu cannot load on the stock kernel.
- **How to extend it:**
  1. Create `common/gki/x86_64/symbols/anybook_amd` and add it to the `x86_64_additional_kmi_symbol_lists` filegroup.
  2. Generate its contents from the real modules rather than by hand. The model is `virtual_device_x86_64` plus `virtual_device_x86_64_abi` in `common-modules/virtual-device/BUILD.bazel`:
     - Define a device `kernel_build` with `base_kernel = "//common:kernel_x86_64"` and `kmi_symbol_list = "//common:gki/x86_64/symbols/anybook_amd"`.
     - Add a `kernel_abi` whose `kernel_modules` are the AMD modules: amdgpu, pinctrl-amd, amd_pmc, the ACP/SOF drivers and others.
     - Run `tools/bazel run //<pkg>:<name>_abi_update_symbol_list` (Kleaf docs: `build/kernel/kleaf/docs/abi_device.md`).
  3. Rebuild the GKI with `scripts/kernel-build.sh`, so the new symbols are exported. Then refresh the ABI with `tools/bazel run //common:kernel_x86_64_abi_update` and check it with `//common:kernel_x86_64_abi_dist`, which is what CI runs. Adding symbols only adds exports, so existing vendor modules keep loading. Changing an exported struct is a KMI break and needs an entry in `abi.stg.allowed_breaks`.
  4. For quick experiments only: `tools/bazel run --notrim //common:kernel_x86_64_dist` turns off trimming and exports everything.
- **Release string.** With `CONFIG_MODVERSIONS`, `same_magic()` (`kernel/module/version.c:97`) skips the release-string part of vermagic. Modules therefore load across builds with different `-g<sha>`/`-ab<N>` suffixes, as long as the CRCs match. The boot test shows this for Google's vendor modules.

## Open issues

- **Signing key.** Our GKI cannot load Google-signed GKI modules, so the next stage must install our `system_dlkm` too. For M1a/M3, that means rebuilding `super`'s `system_dlkm_a` or overlaying it, and that is not done yet. **HYPOTHESIS:** once `system_dlkm` matches the kernel, boot behaves exactly like the stock kernel.
- **Release-branch choice.** Track B KMI compatibility favours staying on `android17-6.18-2026-06` at the shipped SHA, or on a later monthly release branch. For new AMD features, the tip (6.18.32) or `android-mainline-desktop` is better. The AMD fragment should be checked against both.
- **Unconfirmed upstream version.** `28d11e4548b7` is upstream (no `ANDROID:` prefix) and in mainline before the `android-mainline-6.18` tag. We did not confirm which Linux release first shipped it.
