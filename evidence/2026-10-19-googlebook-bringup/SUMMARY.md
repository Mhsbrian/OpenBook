# ANAL-228: first mixed Ruby/OpenBook VM milestone

2026-10-19. Baseline OpenBook commit `b4dd485` (installer groundwork), retained
Ruby recovery build `16452207_CL3B.260622.271.R1`, existing OpenBook G14 product,
and matched G14 kernel `6.18.21-android17-5-gfbfdd65b0fd1`.
Reproduction and remaining gates: `docs/googlebook-bringup.md`.

## Results

| Check | Observed result |
|---|---|
| Input guards | 9/9 pass: exact grant counts, neverallow preservation, input/output separation, symlink and QEMU delimiter refusal, kernel banner parsing |
| Native audit | 389 metadata/APEX/tool/kernel inputs hashed before and after; unchanged |
| Stock OpenBook and Ruby | Both pass native VINTF including APEX/kernel checks, and strict SELinux compilation |
| Unmodified mixed tuple | VINTF passes; strict policy compilation fails on six debug/SwiftShader grants (expected negative control) |
| Adapted mixed tuple | VINTF and strict policy compilation pass; six grants removed, two serial-diagnostic rules added |
| Image assembly | New private EROFS/vendor, local test-key vbmeta, super and GPT; `fsck.erofs` and `sgdisk -v` pass |
| Super payload readback | 6/6 logical partition hashes match the assembly inputs; Ruby system/product/system_ext remain unchanged |
| Final VM | QEMU/KVM, Ryzen 7950X, four vCPUs, 8 GiB RAM, 90-second observation, no network/physical disks, process reaped |
| Boot progress | First-stage and second-stage init; matched vendor module loader exits 0; no captured module ABI errors; diagnostic `getenforce` reports Enforcing |
| Security services | Service-list output contains KeyMint, Gatekeeper and keystore2; encrypted userdata is initialized; no PIN or persistence result |
| Framework | Zygote starts then crashes 16 times with SIGILL; boot animation also SIGILL; `sys.boot_completed` remains unset |
| Crash diagnosis | Both faulting instructions are VEX VPDPWSSD (AVX-VNNI), matched by tombstone PC and ELF Build ID |
| Isolated host instruction | CPUID AVX-VNNI false; the exact libz instruction encoding traps with SIGILL, caught without a core dump |

The final audit is local run `anal228-ruby-audit-v5`; the final VM is
`anal228-ruby-probe-v3`. Initial probe logging used the userdebug kmsg node,
which Ruby's user policy denied. The final probe uses a scoped serial diagnostic
service under enforcing policy. Serial kernel records can interleave with
userspace lines; `observations.json` removes those records only when decoding
the service list. `serial.log.gz` preserves the original capture.

`audit.json` holds input hashes, APEX identities, native command arguments and
results. Empty successful `*-policy.log` files mean secilc returned zero without
diagnostics. `hybrid-policy.log` preserves the expected strict rejection.
`recipe.json` identifies the actual image inputs and boot configuration.
`crash-instructions.json` and `crash-disassembly.txt` tie the failures to exact
ELF builds and instructions; no library binaries are included.

## Scope and next step

This is progress past the previous stock Ruby keystore/Trusty/GSC stall, not a
completed Android boot. The earlier “no SIGILL” observation covered only the
early stock boot phase; it does not apply to this newly reached framework phase.
The G14's retained HX 370 inventory reports AVX-VNNI, unlike the 7950X host.
That is not a physical Googlebook boot result.

Shared-secret service and vendor boot patch-level property denials, stock GSC
services and uprobe errors remain. Do not infer secure credentials, successful
graphics, app compatibility or installation readiness from a VINTF pass.
Next: establish a CPU execution baseline with AVX-VNNI, resolve security-service
integration, then desktop and an explicitly approved external G14 trial.

All generated images, extracted APEX payloads and compiled policy stay local.
No Google payload is redistributed. No USB, laptop disk, firmware, account or
installed OS was changed. The installer Googlebook option remains unavailable.
