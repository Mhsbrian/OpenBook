# Quire Q4 (ANAL-218): the Linux environment and `quired serve`, evidence

2026-10-18. Host: AMD Ryzen 9 7950X (Zen 4), Arch Linux, `kvm_amd` nested=1. Cuttlefish `anybook_cf_x86_64_pc` cp2a userdebug on the AMD lane (`CF_GPU=amd`, `gfxstream_guest_angle`), pinned trees as in `docs/quire.md` §Sources, Virtualization `22f1c9ee92b1` plus `aosp/patches/packages/modules/Virtualization/0001`. Guest image: `image/image-info.txt` (Debian 13, kernel 6.12.113+deb13-cloud-amd64, `quired` 0.2.0, test agent opencode 1.19.3).

## Acceptance (ANAL-218)

| # | Item | Result | Where |
|---|---|---|---|
| 1 | Cuttlefish: the Linux environment boots, `quired agents` in the guest lists an agent installed there, and a prompt sent from Quire core gets an answer back, with the logs | **Met.** Final image, fresh `/data`: **29 pass, 0 fail**. The Terminal app installs the image and boots the guest under nested KVM. `quired agents`, typed in the Terminal app, lists opencode 1.19.3 (screenshot). Quire core lists the same agent through the bridge and sends "Reply with exactly: QUIRE OK"; opencode in the guest answers **"QUIRE OK"**, `end_turn`, in 3.0 s | `cf/` |
| 2 | G14 through the owner's stick: the same, plus a KVM check and the guest's boot time | **Not run.** The check is written and passes on Cuttlefish (`scripts/quire/q4-device-check.sh`, `cf-device/`: 0 failures, with `/dev/kvm`, `kvm_amd` and `systemd-analyze` in the Terminal app). The G14 product builds with AVF (see below). The guest image (733 MB) doesn't fit the stick's 256 MiB ESP, where add-ons go, so the stick builder (ANAL-192) has to carry it in the stick's userdata | `cf-device/` |
| 3 | With no KVM, Quire degrades to a paired computer and says so; it does not fail silently | **Met in Cuttlefish**, with pairing itself not built: Quire says the Linux environment can't be used, why, and that a paired computer could be used instead but none is paired (**8 pass, 0 fail**). On a PC, no KVM means AVF isn't offered at all, and Quire says "no hardware virtualization" (fixture-tested; not booted) | `cf-nokvm/` |
| 4 | Evidence and `docs/quire.md` §4 updated | This folder; `docs/quire.md` §4.1, §5.4, §6.1, §7, §8; `docs/quire-pairing.md` (design, for review) | |

## What was measured

| | Value | Source |
|---|---|---|
| Unit tests (`go test -race ./...`) | 30 pass, 0 fail (8 new, for `quired serve`) | `go-tests.txt` |
| PC KVM check fixtures | 0 failures (KVM on, KVM off) | `pc-setup-test.txt` |
| Guest image build (AOSP's builder, warm caches) | about 3 min | `image/build-steps.txt` |
| QEMU on this host: start to `quired` answering on vsock | 6.0 s; guest `systemd-analyze` 4.5 s (second boot) | `qemu/timings.txt`, `qemu/guest.txt` |
| QEMU: prompt over vsock from the host (as CID 2) | "QUIRE OK", `end_turn`, 3.3 s | `qemu/prompt.summary.txt` |
| QEMU: a peer that isn't the host (vsock loopback, CID 1) | refused (`serve: refused vsock:1:… (not the host)`) | `qemu/guest.txt` |
| Cuttlefish: local image install plus VM start | 21–35 s across runs (the install untars 3 GB) | `cf/results.tsv` |
| Cuttlefish: guest boot, first boot with cloud-init (`systemd-analyze`) | 12.6 s (1.84 s kernel + 10.78 s userspace); 11.5–13.0 s across runs | `cf/terminal-quired-agents.png` |
| Cuttlefish: crosvm start to Quire's first connection to `quired` | 12.0–15.7 s across runs; Quire retries every few seconds, so this is an upper bound | `cf/vm-start-and-connect.txt` |
| Cuttlefish: prompt from Quire core, answered | 3.0–9.5 s on the free model (one exception below) | `cf/prompt-quire.txt` |
| G14 product (`anybook_g14_x86_64` cp2a userdebug, repo `6a22211` plus docs) | builds (31 min 37 s): `com.android.virt.apex` 64 MB (1.4 MB with AVF compiled out), `features_com.android.virt.xml`, `init.openbook.rc` with the KVM check and its triggers, SELinux compiled. Not booted | `~/anybook/logs/aosp`, build of 2026-10-18T20:06Z |

## Runs on the final image (`fc9c34b`, repo head `6a22211` adds only check-script changes)

- `cf/`: full run, fresh `/data`, 29 pass, 0 fail.
- `cf-nokvm/`: guest kernel booted with `initcall_blacklist=svm_init`, so no `/dev/kvm`: 8 pass, 0 fail.
- `cf-device/`: the on-device script, fresh `/data`. First pass 1 failure (`kvm_amd` read from a wrapped kernel log; the script now reads sysfs), second pass 0 failures.
- `cf-other-runs/gfx-stall/`: 26 pass, 3 fail. The Terminal app's UI froze (ANR): its RenderThread was stuck in Cuttlefish's gfxstream Vulkan driver (`vkQueueWaitIdle`). With the UI frozen, its service never ran the VM stop, and the terminal never showed. A Cuttlefish graphics stall on the AMD lane, not OpenBook code; the next run on the same image passed.
- `cf-other-runs/prompt-timeout/`: 28 pass, 1 fail. The prompt opened a session but got no answer within 300 s; opencode logged no error. Retried on the same device, it was answered in 9.5 s (`results-retry.tsv`). Hypothesis: the free model's service was slow. Earlier, with no network in the guest, a prompt was answered 378 s later, once Wi-Fi came up: a turn waits rather than fails.

Earlier images during the work (not committed) found three faults, each fixed and then re-run (§Found).

## Found (C)

1. **AVF was compiled out of both products.** AOSP's PC Cuttlefish product doesn't inherit AVF's `product_packages.mk`, so `com.android.virt` was built without crosvm, virtmgr or the Terminal app (1.4 MB). Fixed by `device/anybook/common/linux-env/linux-env.mk`.
2. **Nested KVM works in Cuttlefish on this AMD host.** crosvm logs `creating hypervisor: Kvm { device: Some("/dev/kvm") }`; `kvm_amd` nested=1, npt=Y in the Cuttlefish guest.
3. **`virtmgr`'s vsock can't be half-closed by its owner.** AVF's `virtualizationservice_use` grants only `getattr getopt read write` on it, so the bridge's `shutdown` was denied and Quire's hang-up never reached `quired`. The bridge now opens its own vsock, as the Terminal app's ttyd bridge does. The hang-up check passes, with no denial for the bridge or Quire.
4. **Without KVM, AVF and the Terminal app both say the VM is running.** crosvm exits at once (`no enabled hypervisor`). But `VmController` sets Running as soon as crosvm is spawned, and `vm list` and `VirtualMachine.getStatus()` keep the VM while its vhost-user helpers (virtiofs, sound) live. The Terminal app shows a black terminal. The bridge now reads the truth from the vsock: a connect to an unused port fails with `ENODEV` when there is no VM. Quire also reports a connector that fails to connect with the fallback, not only in its log.
5. **The Terminal app installs a local image by itself** on a debuggable build: there is no Install button to tap.
6. **The guest's network comes from Android through AVF's tethering**, so it needs Android to have an upstream network. Cuttlefish's only one is its synthetic Wi-Fi, which the check turns on, as the microG checks did.
7. **AOSP AVF's own denials** appear with the VM running, none of them from OpenBook code:
   - `priv_app_all_virtualizationmanager`: `fd use` on surfaceflinger, `gpu_device` read/write, and `fuse` read of the image on `/sdcard` (a descriptor inherited from the installer);
   - `system_server` `setsched` on `crosvm_vu_snd`.

   They are listed apart in `cf/selinux-denials.txt`.
8. **The guest's desktop session (weston) fails**: Debian's cloud kernel has no virtio-gpu DRM. The terminal and agents don't need it.

## Not done

- The G14 run (acceptance 2): it needs the guest image on the owner's stick (ANAL-192) and the merged product.
- Pairing a second computer: a design for the Checker's review (`docs/quire-pairing.md`); nothing built.
- The guest's `cidata.iso` (guest agent, cloud-init files) is AOSP's checked-in prebuilt (build 15101902); building it from source needs a musl host build.
- A guest kernel with virtio-gpu, for Linux GUI apps.

## Reproduce

```bash
(cd quire/quired && go test -race ./...)
scripts/quire/linux-env-image.sh OUT --test-agent opencode
scripts/quire/linux-env-qemu.sh OUT/images.tar.gz RUN --prompt opencode "Reply with exactly: QUIRE OK"
# Build under the lane lock and snapshot
flock ~/anybook/aosp/.lane.lock bash -c 'ANYBOOK_LANE_LOCK_HELD=1 AOSP_JOBS=20 scripts/aosp-docker.sh /repo/scripts/aosp-build.sh \
    anybook_cf_x86_64_pc-cp2a-userdebug droid &&
  S=~/anybook/aosp/cf/q4-out O=~/anybook/aosp/src/out P=anybook_vsoc_x86_64 &&
  mkdir -p $S/target/product/$P $S/host/linux-x86 &&
  find $O/target/product/$P -maxdepth 1 -type f -exec cp --reflink=auto -t $S/target/product/$P {} + &&
  cp --reflink=auto $O/host/linux-x86/cvd-host_package.tar.gz $S/host/linux-x86/'
export CF_OUT=~/anybook/aosp/cf/q4-out CF_STAGE=~/anybook/aosp/cf/q4 CF_NAME=anybook-cf-q4 CF_DEVICE=anybook_vsoc_x86_64 \
  CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_ADB_PORT=16218 CF_WEBRTC_PORT=11218 ANDROID_ADB_SERVER_PORT=5218 \
  CF_ARGS="--vhost_user_vsock=true --data_policy=always_create --blank_data_image_mb=16384"
scripts/cf-boot.sh up && scripts/cf-boot.sh wait && ~/anybook/android-sdk/platform-tools/adb connect 127.0.0.1:16218
scripts/quire/q4-cf-check.py 127.0.0.1:16218 RUN --image OUT/images.tar.gz
scripts/cf-boot.sh down
# No KVM: the same, with CF_ARGS+=" --extra_kernel_cmdline=initcall_blacklist=svm_init", then
scripts/quire/q4-cf-check.py 127.0.0.1:16218 RUN --image OUT/images.tar.gz --only nokvm,health
# On the device itself (what the G14 runs): push the script and the image, then as root
Q4_WIFI=VirtWifi sh /data/local/tmp/q4-device-check.sh /data/local/tmp/images.tar.gz /data/local/tmp/q4
```

Prompts went to opencode's free model with no account (no OpenBook or owner credentials in the image). The evidence was scanned for common credential patterns, and the Terminal app's session keys are redacted from the logcat extracts (a bounded check, not proof).
