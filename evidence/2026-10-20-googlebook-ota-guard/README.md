# Ruby native OTA guard — 2026-10-20

This is a disposable, offline VM experiment for ANAL-229. No physical device
was written. Images, Google binaries, TPM state, raw logs and extracted
encryption keys remain private. Reproduction and deployment boundaries are in
`docs/googlebook-ota-guard.md`.

## Measured result

| Check | Result | Evidence |
|---|---|---|
| Native build | Experimental daemon/probe/test and normal `update_engine` build successfully; normal binary has no guard policy | `native-build.json` |
| Backend behavior | 19 refusal, callback-identity/lifetime and real-cleanup assertions pass | `native-test.txt` |
| Dynamic-link preflight | Direct dependencies and strong versioned imports resolve; private protobuf/Abseil exports absent | `link-preflight.json`; preliminary ABI check only |
| Policy | Exact policy compiles with neverallow checks; 10 baseline + 10 harness full-context assertions pass | `policy-*.txt`, `test-summary.json` |
| Reassembly | 7,292 metadata rows, 3,464 files/symlinks audited; only five specified file contents and sizes change; data/GPT preserved | `image.json` |
| AVB handoff | Actual EFI readback and root vbmeta digest/size agree; legacy input27 is rejected for stale size | `avb-handoff.json` |
| Python regression suites | 77 tests pass across eight suites | `*-tests.txt`, `test-summary.json` |
| Fresh-data VM | 760.7 s complete; boot/enforcing reported; 24 IPC assertions pass; three probe executions exit 0 | `fresh-vm.json`, `fresh-probe-lines.txt` |
| Initialized-data VM | 760.7 s complete; boot/enforcing reported; 24 IPC assertions pass; probe exits 0; all four encryption-key files unchanged | `initialized-vm.json`, `initialized-probe-lines.txt` |

The final candidate SHA-256 is
`4be743d2cc11d6f58ce15e2dce6ac4ba264776965611317831ad86345d564937`.
Both VMs use TCG, UEFI USB, software TPM, emulated audio, no NIC and synthetic
data. Inputs and decoy disk are unchanged; the initialized test also preserves
the source TPM state. Guest disks change normally during Android boot.
Neither final log reports the stale-size/vbmeta-digest handoff error.

The fresh-data VM records a `system_server` SIGSEGV and three zygote exits.
The unchanged camera25 baseline retry also completes boot and records the same
signal class. This does not establish an identical cause or excuse the crash.
The final initialized-data observation has no recorded system-server fatal
signal or zygote exit. Neither bounded observation qualifies runtime stability.
Fresh USB diagnostic capture did not reach its completion marker within the
window; boot, IPC, enforcing and crash observations come from the serial log.

## Parser correction and retained failures

The initialized wrapper initially exited 1 because kernel console output was
appended to `PASS ordinary status callback` before its newline. The probe itself
exited 0. `initialized-original-rehearsal.json` preserves that original report.
`initialized-vm.json` re-evaluates the **same serial bytes** using
`ota-guard-qemu.py:probe_checks`, which accepts exact known PASS names followed
by a newline or kernel timestamp. Tests reject arbitrary prefixes/suffixes.
Serial/result/parser hashes and line-numbered probe excerpts make this
correction reviewable. It is not an additional VM run or a claim that the
original wrapper exited successfully.

`earlier-observations.json` retains bounded results and raw-log hashes:

- The first unchanged baseline exited after 39.9 s without completing the
  observation or boot; the cause remains unresolved. Its separate 480.7 s retry
  completed boot and recorded a system-server SIGSEGV.
- The first guard harness could not enter the shell domain directly through
  the replaced client binary. Boot was observed, but the probe failed. The
  fresh observation also ended early at 461.1 s.
- The second candidate's runs were stopped when stale AVB bootconfig size was
  discovered. They are not qualification passes. The final candidate fixes
  both size and digest and repeats the full observation.

The final candidate's compiled policy matches the policy tested for the second
candidate byte-for-byte. Actual final EFI/readback and vbmeta-byte verification
also ran independently after their corresponding builder assertions were added.

## Remaining gates

This proves installation-request refusal and real status/cleanup behavior for
the tested ordinary/stable Binder APIs in this VM environment. It does not
contain independent downloads, recovery/sideload, Mainline or privileged raw
writes. A pending merge can still finish through real cleanup; deployment needs
a quiescent installed state.

The probe, four shell test-policy rules and experimental image are not
deployable. Installer source gates reject the experiment marker, and the
physical writer rejects its experimental clone schema. No automatic system
rollback, interrupted physical write, data-schema downgrade, laptop credential
unlock, Play Store operation or current-G14 behavior was tested here.

Older input27/fresh28 artifacts need corrected boot parameters, new hashes and
installer pins, and another rehearsal before promotion. The new preparation
checks do not retroactively revoke previously prepared physical-write plans.
