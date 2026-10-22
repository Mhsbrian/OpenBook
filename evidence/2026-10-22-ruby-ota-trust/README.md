# Ruby OTA trust anchor, VM evidence (ANAL-229), 2026-10-22

These are disposable VM images built from the camera25 base. They carry
test-only payloads, test keys and shell Binder grants. No laptop, USB stick or
setting was touched. Design and commands: `docs/googlebook-ota-trust.md`.

| File | Content |
|---|---|
| `builds.json` | Both images: hashes, changed and added paths, trust-anchor record, payload and test-certificate hashes, test policy hash, per-file hashes. Private keys are not included. |
| `vm-trust.json` | Runner result for the OpenBook-certificate image `2db57f34…`. Per request it records the client exit code, `update_engine` ErrorCodes, signature/preparation/snapshot flags and log milestones. It also has the disk before/after comparison and runtime findings. |
| `vm-stock.json` | The same for the stock-certificate control `3c3ca47a…` |
| `vm-*-lpdump.json` | `lpdump` of super metadata slots 0 and 1 before and after each run |
| `superseded.json` | Three earlier runs and why each was replaced |
| `production-shape.json` | Production-path check on camera25 with the test certificate (image deleted) |
| `release-candidate.json` | Real candidate `9985be73…` = RB-20261021-01 + OpenBook certificate: identity, single changed file, retained module and trackpad fix, VM boot, runtime against the RB-20261021-01 baseline |
| `vm-release-cert.json` | Harness twin with the real certificate: payloads from both disposable keys refused at the signature on every request, archive `3e1529c9…` on the device, 19/19 checks |

## Outcome

- **Trust image:** the foreign-signed payload was refused with
  `kDownloadMetadataSignatureMismatch` on verify, allocate and apply. No
  signature was accepted and no partitions were prepared. Both OpenBook-signed
  payloads verified. The static payload's apply stopped at the missing
  `boot_b` (`kInstallDeviceOpenError`). The Virtual A/B payload created a
  `system_b` snapshot and wrote super slot 1 at allocate and again at apply,
  then stopped at `boot_b`.
- **Stock control:** all three payloads were refused at the signature on every
  request.
- **Both images:**
  - the single-slot boot partitions and super slot 0 are unchanged;
  - slot `_a` stays active with one slot and slot B at priority 0;
  - the harness ran once, after `update_engine` was idle;
  - boot completed with SELinux enforcing;
  - there were no denials involving `update_engine`, its client or the harness
    files.

All 16 trust checks and all 19 control checks pass.

Runtime: each run has one `system_server` SIGSEGV and three zygote exit events.
The same class appears on the unchanged baseline, so it is not attributed to
this change. Raw serial logs and the VM disks stay private in the work
directory. Their SHA-256 values are in the JSON files.
