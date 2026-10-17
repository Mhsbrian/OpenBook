# `openbook-live-20261017-combined`: one G14 stick from `main` (ANAL-159, 2026-10-17)

This is one live stick for every open G14 test: ANAL-176 (desktop, enforcing boot), ANAL-178 (lid, touchpad, power check), ANAL-179 (Wi-Fi, Bluetooth, audio) and ANAL-200 (arm64 bridge). It replaces `anal178b` (which lacks the bridge) and `anal200` (built from an uncommitted tree, with only its "save logs" case tested).

## Build

- **Source:** `main` at `8b40298` (PRs #41–#46), plus `01750c5`, a G14 policy fix (below). The repo tree was clean (`.build.json`: `"dirty": false`).
- **Product:** `anybook_g14_x86_64-cp2a-userdebug`. An incremental build took 2:55 in the AOSP lane, peaking at 47.6 GB of memory (`build-g14-01750c5.txt`).
- **Image:** `scripts/installer-image.sh --menu-timeout 10 --no-xz`. ANAL-178's power check add-on (`openbook-powercheck-anal178-a-addon`, the same one as `anal178b`) was added with `scripts/power/add-to-live-stick.sh --image`.
- **sha256** of the image with the add-on: `8b0c690d…` (`openbook-live-20261017-combined.sha256`).

## Found and fixed: the bridge's binfmt_misc was blocked in enforcing boots

The first candidate, `openbook-live-20261017-main`, was built from `8b40298`. It passed the live matrix 39/39. But every enforcing boot logged this (`binfmt-enforcing-before-after.txt`):

```
init: Command 'mount binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc' ... (/system/etc/init/berberis.rc:3) ... failed: mount() failed: Permission denied
avc:  denied  { mounton } for comm="init" path="/proc/sys/fs/binfmt_misc" ... tcontext=u:object_r:proc:s0 tclass=dir permissive=0
```

- **Cause:** the Cuttlefish product inherits Cuttlefish's vendor rules for its translator (`allow init proc:dir mounton; allow init binfmt_miscfs:file w_file_perms;`). The G14 product's PC policy had neither rule.
- **Effect:** in the default (enforcing) boot, arm64 executables could not run through the translator. App libraries would still load, because they go through libnativebridge.
- **Why ANAL-200 missed it:** its matrix ran on Cuttlefish, and its G14 image test ran only the permissive "save logs" entry.
- **Fix (`01750c5`):** the same two rules in `device/anybook/common/pc/sepolicy/vendor/init.te`. The policy builds and passes the neverallow checks.

## Results (QEMU/KVM, q35 + OVMF, the image attached as a USB stick)

| Test | Result | Evidence |
|---|---|---|
| Live image matrix (ANAL-190's six cases) | **39/39** | `live-matrix-SUMMARY.md`, `live-matrix-results.json` |
| Enforcing boots (first, second, reset, exact) | **No binfmt_misc denial or failure** (each had one before the fix). The only denial left in their serial logs is the known keystore → gatekeeper one | `binfmt-enforcing-before-after.txt` |
| arm64 executable through binfmt_misc, enforcing, as the shell user | **All four checks pass:** `bridge-exec` (aarch64), `bridge-id-registers` (0 SIGILL), `bridge-fp-estimates` (6,900 cases, 0 bad), `bridge-int-simd` | `bridge-enforcing.txt`, `expect-bridge-enforcing.json` |
| "Save logs" report | boot_completed at 17.7 s; display and GPU HALs (virtio, ANGLE); data on the stick; all five `bridge_*` verdicts true; `vendor.health-openbook` running; lid → sleep, short power press = lock or sleep | `logs-report.md`, `logs-report.json` |
| Power check entry, unchanged ("OpenBook power check: S0i3") | **10/10 steps**, 4 cycles, report saved, powered off (S3 in QEMU, as for `anal178b`) | `powercheck-real-result.json`, `powercheck-real-hwcheck-001.json` |

**Expected in a VM, not failures:**
- The Wi-Fi and audio verdicts are NO. This matrix VM has no Wi-Fi or sound card; ANAL-179's QEMU rig tests those (`evidence/2026-10-17-g14-audio-net/`).
- The shell user can't list `/proc/sys/fs/binfmt_misc`. AOSP's policy keeps `binfmt_miscfs` from core domains other than init.

**Not tested here:** anything on the G14 itself. The owner's run of this stick is the hardware test (`docs/STATUS.md`, "Next G14 stick").
