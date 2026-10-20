# Ruby OTA guard prototype

ANAL-229, 2026-10-20. The owner is using the installed G14 and reports normal
app updates working. The immediate work is system-update control and recovery.
No laptop setting, app, disk or firmware has been changed by this work.

This is a **disposable VM prototype**, not an approved laptop update. Recovery,
independent Google downloads, Mainline, a second system slot and newer-schema
data rollback remain separate gates. See `googlebook-updates.md` for the decision
record and `../evidence/2026-10-20-googlebook-ota-guard/` for measured results.

The final fresh and initialized-data VMs each completed a 760.7-second
observation, reported boot completion/enforcing mode and passed all 24 ordinary
and stable Binder assertions. The initialized test retained all four encryption
key files and the original software TPM state. Native tests pass 19 assertions,
policy tests pass 20, and eight Python suites pass 77 cases.

The fresh-data VM still records a system-server SIGSEGV, also seen in the
unchanged baseline retry; runtime stability is not qualified. The initialized
wrapper initially reported one missing PASS because of interleaved console
output. Its exit-1 report is retained alongside the corrected parser's
evaluation of the same log; the actual probe exited 0. See the evidence README
for this distinction and earlier failed/superseded observations.

## Backend behavior

The opt-in `openbook_ruby_update_engine` target retains AOSP's real updater,
initialization, boot flags, observers and successful-update cleanup. Its
`ServiceDelegateAndroidInterface` wrapper refuses every installation-related
request from both ordinary and stable Binder services before reaching the real
update attempter: URL/FD apply, allocation, activation/reset, resume/suspend,
cancel/reset-status, postinstall and applicability checks.

Binding/status callbacks remain available. Cleanup forwards the original
callback and error without manufacturing success. There is no runtime property,
UID exception, special header or API to enable installation. The normal
`update_engine` target and all product package lists remain unchanged.

Install this kind of policy only into a **quiescent** system after confirming
that no earlier OTA/snapshot merge is pending. Real cleanup can finish an
existing merge. This guard does not revoke privileged raw-device access or
change recovery/sideload, APK/APEX installers, Google update clients or their
network requests.

The patch is pinned to AOSP update_engine
`4591637f51644f5429f9e2fe589ab22b92f61842`. Its local
`aosp/daemon_state_android.cc`, both Binder adapters and
`aosp/update_attempter_android.cc` establish the call paths. The public
[update_engine design](https://android.googlesource.com/platform/system/update_engine/+/refs/heads/main/README.md)
and [A/B lifecycle](https://source.android.com/docs/core/ota/ab), checked
2026-10-20, provide background; neither proves this Ruby integration works.

Ruby and the build tree use different protobuf/Abseil library identities.
The experimental executables link their generated-message runtime statically
and hide archive exports with `--exclude-libs,ALL`. Ruby's shared libraries are
not renamed or replaced. Dynamic-symbol checks are only a preliminary gate:
they cannot prove C++ layouts, linker namespaces or runtime behavior.

## Test harness boundary

The VM candidate replaces five existing system files:

- `bin/update_engine`: the guarded native daemon.
- `bin/update_engine_client`: an explicit, bounded test client.
- `etc/init/update_engine.rc`: retains the original service and adds a test
  through `/system/bin/sh` after boot completion.
- `etc/selinux/plat_sepolicy.cil` and its mapping hash: four test-only
  Binder/FD rules allow shell and update_engine to communicate.

These test permissions are **not production containment policy**. The normal
Ruby policy denies shell Binder calls and denies a direct shell-domain entry
through a `system_file` binary. The first attempt correctly failed at that
entrypoint. The revised harness uses the existing shell entrypoint, retains
enforcing mode, and compiles the exact image policy inputs with neverallow
checks. Full-context controls compare baseline/harness permissions, including
unchanged denial for ordinary apps, shell entrypoints and raw userdata writes.
Actual Google/system callers already have Binder access in the baseline.

The reassembler hashes the complete camera25 source, compares all 7,292
filesystem metadata rows and all 3,464 files/symlinks, and permits only the five
recorded content changes and their file sizes. Ownership, labels, capabilities,
timestamps, all other files, Android data, GPT and unrelated EFI content must
match. It verifies the rebuilt AVB image against the supplied local test key.
This does not establish a production signing chain.

Both AVB digest **and unpadded size** are regenerated in every boot entry.
`verify_vbmeta_bootconfig()` checks them against actual partition bytes before
preserving preparation or installer source pinning. The earlier input27
assembler changed the digest but left a stale size; older input27/fresh28
artifacts need corrected boot parameters, new hashes, installer pins and a new
rehearsal before promotion. Android's unlocked boot tolerated that mismatch;
continued boot was not proof of a correct AVB handoff.

Experimental preserved clones use `openbook-ruby-experimental-clone/1`, which
the physical writer rejects. Installer pinning/packaging also rejects the
`experimental_ota_guard` marker. The ordinary preserving CLI retains its
vendor-only compatibility policy; its internal experimental validator is not
exposed as a command-line override.

## Reproduce

Use the shared AOSP lane. No Google artifacts, keys or data belong in Git.
Set `REPO` to this checkout, `AOSP` to the pinned AOSP source, and `WORK` to a
new private installer work directory. Use the existing read-only EROFS helper
documented in `googlebook-input-update.md`.

```bash
AOSP_JOBS=20 scripts/aosp-docker.sh /repo/scripts/aosp-build.sh \
  anybook_g14_x86_64-cp2a-userdebug \
  openbook_ruby_update_engine openbook_ota_guard_test openbook_ota_guard_probe

"$AOSP/out/host/linux-x86/nativetest64/openbook_ota_guard_test/openbook_ota_guard_test"

scripts/installer/inst-docker.sh python3 \
  "$REPO/scripts/googlebook/build-ota-guard-candidate.py" \
  --base "$CAMERA25_FRESH" --tools "$AOSP/out/host/linux-x86/bin" \
  --inventory "$EROFS_INVENTORY" \
  --key "$AOSP/external/avb/test/data/testkey_rsa4096.pem" \
  --engine "$PRIVATE_ENGINE_COPY" --engine-sha256 "$REVIEWED_ENGINE_SHA256" \
  --probe "$PRIVATE_PROBE_COPY" --probe-sha256 "$REVIEWED_PROBE_SHA256" \
  --out "$WORK/image"

scripts/installer/inst-docker.sh python3 \
  "$REPO/scripts/googlebook/ota-guard-qemu.py" \
  --candidate "$WORK/image" --base-manifest "$SYNTHETIC_BASE_MANIFEST" \
  --synthetic-vm "$INITIALIZED_SYNTHETIC_VM" \
  --synthetic-vm-sha256 "$REVIEWED_SYNTHETIC_VM_SHA256" \
  --tpm-state-from "$SYNTHETIC_TPM" --qemu "$REVIEWED_TCG_QEMU" \
  --seconds 760 --out "$WORK/rehearsal"
```

The initialized VM's manifest must match its actual GPT identity; the fresh
camera25 manifest is not interchangeable with an earlier preserved VM.
Use only synthetic data and that VM's software TPM. The runner copies inputs,
has no NIC or physical disk, validates physical-writer refusal, and waits for
all VM/TPM processes before returning. It checks all 24 IPC assertions, actual
cleanup completion, process exit codes, boot, enforcing mode, observation
completion, four encryption-key files and source/TPM/decoy preservation.
Keep raw logs and extracted synthetic keys private.

For a fresh-data control, use `run-probe.py --uefi-usb --usb-logs --tpm --audio
--accel tcg --timeout 760` with a fresh output and the candidate directory.
Repeat against unchanged camera25 when investigating a fresh-boot failure.
The runner's exit zero means the observation was collected, not a boot pass.
Report system-server crashes separately even when all guard assertions pass.

The native policy checker builds against pinned AOSP libsepol:

```bash
gcc -O2 -Wall -Wextra -Werror \
  -I"$AOSP/external/selinux/libsepol/include" \
  scripts/googlebook/ota-guard-policy-test.c \
  "$AOSP/out/soong/.intermediates/external/selinux/libsepol/libsepol/linux_glibc_x86_64_static/libsepol.a" \
  -o "$WORK/policy-test"
"$WORK/policy-test" "$CAMERA25_POLICY" baseline
"$WORK/policy-test" "$WORK/image/probe-policy.bin" harness
```

## Next hardware gate

Obtain a current paired wireless ADB endpoint for read-only capture while the
owner continues using the G14. Establish the current GPT/free space,
boot-control/snapshot state, updater activity and an up-to-date recovery backup.
The previous USB backup must not overwrite newer laptop data.

Reserve space for a second complete system set before expanding userdata into
all remaining SSD space. A fresh installer consuming that space is not an
update plan for the owner's currently used system.

A laptop trial needs an image without the VM probe or shell test permissions,
known-good recovery, interrupted-write/failed-boot tests and an explicit device
confirmation for any physical writes. The admin UI should expose installed,
reviewing, ready, reboot-pending and recovery-needed states only after those
backend operations exist. It must never present this experiment as a safe
automatic update or promise that an old system can read newer-schema data.
