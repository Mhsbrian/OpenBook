# ANAL-238 dGPU diagnostics on the two-slot Ruby base, 2026-10-24

The vendor change from `evidence/2026-10-22-ruby-dgpu-power/`, rebased onto RB-20261023-03 (what the G14 runs)
and tested once on exactly the handed-off bytes. Regular image files only: no laptop, no stick.

## Files

| File | What |
|---|---|
| `handoff-ANAL-238.json` | `anybook-handoff/1`: each check, its evidence and the input hashes it tested |
| `policy-check.json` | `build-dgpu-diag-candidate.py --check-policy-only` on RB-20261023-03's candidate C (`71da0228…`) |
| `candidate-vmcheck-result.json` | The VM-check candidate `76ed6959…` (not deployable): vendor and system rebuild details |
| `vm/` | QEMU fresh boot of that candidate: `judge.json` (14/14), `boot.json`, `qemu-command.json`, `serial.log.gz` |
| `vm-attempt1/judge-result.json` | The first boot: stopped early, and the boot report had already rotated out of logcat (see below) |
| `tests/unit.txt` | Unit and fixture tests |

## Results

**Policy (CONFIRMED).** RB-20261023-03 compiles its split policy at boot: the platform hash `318c33bb…` does not
match the vendor's precompiled `344a39b0…`. So the new vendor rule takes effect.
- Both the base and the candidate policy compile with secilc, neverallows included, against RB-20261023-03's own
  platform, system_ext and product policies.
- Only the candidate grants `openbook_pc_setup` the `sysfs_suspend_stats` dir, file and symlink reads.
- The other probes are unchanged: the power-stats HAL's read, `sysfs` writes, the `debug_prop`/`boot_status_prop`
  triggers for vendor_init, shell setting `debug_prop`, and the `tmpfs` kmsg_debug write (still denied).

**Candidate (CONFIRMED).**
- Vendor changes in exactly three files:
  - `/bin/openbook-pc-setup` `f48c7063…`
  - `/etc/init/hw/init.openbook.rc` `50e65153…`
  - `/etc/selinux/vendor_sepolicy.cil` `54f0dfb9…` (base `321e4491…` plus three statements)
- Every other inode, xattr and file is proven identical, and the vendor keeps its own file time (1792368000).
- The VM-check variant adds two disposable files to `system`. AVB verifies.

**QEMU fresh boot: 14/14 against RB-20261023-03's own fresh boot (CONFIRMED).**
- The boot passes, with no system_server fatal signal and no zygote exit.
- At boot completion, `dgpu-report` runs as root and its lines reach logcat:
  `suspend_stats success=0 fail=0`, `state=absent` (QEMU has no NVIDIA GPU).
- `setprop debug.openbook.dgpu_report vm-1` runs it again.
- `debug.openbook.dgpu_pm on` and `auto` run `dgpu-ctl`, which finds no NVIDIA function and reports.
- All four service runs exit 0.
- `openbook_pc_setup` has no denial the baseline lacks: only the known `kmsg_debug` writes from the early-init
  services.
- No new init-script errors. The only app crash is Google's RepairMode, which the baseline shows too.

**Attempt 1.** On candidate `7eb7ac8b`, with the same vendor bytes and an earlier check script:
- The on-demand report, both `dgpu-ctl` runs, the exit codes and the denial set were the same as in attempt 2.
- The boot report's lines had rotated out of logcat by the time the check read them, about 150 s after boot.
  Attempt 2's check reads them 10 s after boot.
- On the laptop, `dgpu-power-adb.py report` always asks for a fresh report.

## Not tested here

- **NVIDIA hardware:** QEMU has none. The dGPU's real D-state and the D0 vs D3cold battery figure need the
  release on the G14.
- **The deployable candidate, payload and laptop-update rehearsal:** they are the release's to build and run, under
  "Test once".

## Commands

```sh
scripts/googlebook/dgpu-vm.sh ~/anybook/installer/work/anal238-dgpu-vm     # stage, policy check, candidate, disk, QEMU, judge
python3 -I scripts/googlebook/build-dgpu-diag-candidate-test.py -v
```
