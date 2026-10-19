# Ruby/OpenBook live-image research — 2026-10-19

ANAL-228, follow-up to the first mixed-framework KVM probe. Work uses the
existing G14 AOSP product, matched kernel/module dist, retained Ruby 16452207
recovery extraction and isolated installer container. The installed G14 and
physical disks were not written. No recovery-derived binary or TPM state is
included here.

## Measured changes

- QEMU v11.1.2 at `4fc49f46dc95d4a27de2509e7fceb2931e91faeb`, patched with
  GBRUNCH `a8936fd33e50efda3f1b36e332ab30b67b709ab1`, executes the previously
  faulting VEX VPDPWSSD instruction. Native 7950X still traps. Tracked QEMU
  source was checked against HEAD plus exactly that patch. Source links and
  binary/container hashes are in `emulator-provenance.json`.
- GFNI/256-bit VPCLMUL arithmetic digest `fac410b5009f4d4f` matches native
  execution; VEX VNNI digest `cd09a9370c7cef79` matches equivalent native
  AVX512-VNNI/VL operations. Each upstream oracle performs 10,000 iterations.
  This validates these tests, not the complete emulated ISA.
- `live-image.py` packages the bare-metal module variant with a removable UEFI
  loader, strict ESP-PARTUUID disk selection, enforcing SELinux/verity, blank
  metadata and 8 GiB encrypted userdata. Six logical payloads and all six
  populated GPT partitions are read back. The image is 12,766,412,800 bytes.
- An initial `ruby-live.conf` entry violated the existing boot-control helper's
  slot naming contract. Android reached checkpoint commit, failed to mark slot
  A good and rebooted. The host negative control reproduces
  `no_current_entry`; `openbook-a.conf` passes the unchanged helper. The fixed
  VM records successful mark-good and `sys.boot_completed=1`. No checkpoint or
  verified-boot check was bypassed.
- Existing OpenBook TPM/CRB modules work with a disposable software TPM. The
  hybrid vendor restores Ruby's original `/dev/tpm* 0660 hsm hsm` ownership
  rule and the original `gscd_service` service mapping. Its type and permissions
  already exist in the retained framework. No GSC permission is added.
- Native `checkfc -s` rejected seven additional mappings whose types only exist
  in Ruby's replaced vendor policy. Those mappings are excluded. The final
  stock baselines and adapted hybrid pass VINTF/APEX/kernel, strict `secilc`
  and service-context validation; 395 inventoried inputs are unchanged. The
  original mixed policy remains a failing negative control.
- The guard suites pass 12/12 and 6/6, including input preservation, policy
  drift, conflicting labels, truncated payloads and readback corruption.

## Observation records

| Run | Result | Scope |
|---|---|---|
| `anal228-usb-kvm1` | 150-second window; SIGILL reproduced | Native Zen 4 control; earlier candidate |
| `anal228-usb-tcg-tpm1` | Guest reboots after checkpoint commit fails | Old loader entry; TPM ownership not yet fixed |
| `anal228-usb-tcg-tpm-fixed` | Full 480.3-second observation, boot complete, no observed SIGILL/panic; input, guest backing image and internal decoy unchanged | Loader and ownership fixed; GSC service mapping not yet restored; final display inactive |
| `anal228-usb-tcg-services` | 495.4 seconds including wake check; enforcing boot complete, welcome screen and input response; all three disk hashes unchanged; no SIGILL/panic | **Fails stability:** `system_server` SIGSEGV/SEGV_ACCERR followed by zygote restart; final screen is boot animation |

Each `result.json` records the actual observation duration. A zero harness exit
only means the observation completed. Early guest reboot is not a passing boot.
Full serial evidence is gzip-compressed; commands and QEMU stderr are retained.
VM paths are replaced with `$DATA`/`$REPO` for publication.

`screen-keyboard.png` records the welcome screen after Escape dismissed the
screen-reader prompt; that feature was not enabled. `manual-input.json` records
the injected pointer/key events. No network, account or terms were accepted.
`screen-after-wake.png` shows the later boot animation after the runtime restart.
The original result is unmodified; `runtime-analysis.json` separately validates
the new crash/zygote/execmem markers against the retained serial log. Subsequent
harness runs include these markers directly, so boot completion cannot hide a
later runtime fault.

Final packaged candidate SHA-256:
`5b21c93932dc39deb46b4462ebafcf17a943de93dbfd2d005d5233e142e66e1e`.
The local image uses schema `openbook-ruby-live-research/1`, with installation
and hardware qualification explicitly false. It is not an installer source.

## Remaining gates

Seven desktop services still lack their original vendor-specific policy
integration. Shared-secret/security-property denials and hardware-specific
services require review. `mmd_setup` aborts with “failed to write zram disk size:
No such file or directory”. RenderThread `execmem` denials precede the
`system_server` SIGSEGV (pid 692, Thread<00>, SEGV_ACCERR at
`0x74595d4c1000`); zygote restarts at kernel uptime 393.237 s. The VM selects
SwiftShader under ANGLE. Its JIT path is a plausible cause, since the strict
Ruby policy explicitly forbids OpenBook's debug `system_server execmem` grant.
There is no complete symbolized system-server trace yet, so that causal link
remains a hypothesis. Do not re-enable the forbidden grant or weaken policy.

No PIN persistence, Google account, Play Integrity,
DRM, ARM app, networking, suspend, AMD rendering or physical G14 result is
claimed. A software TPM is not Google's security chip or an attestation result.

The build host has no attached USB block device (`host-block-devices.txt`).
The owner's previously recorded 62 GB SanDisk Ultra was not updated. Replacing
it requires connection, exact-device confirmation, the guarded writer and full
readback. No image download/distribution permission is inferred from this local
research. The Googlebook installer option stays unavailable.

Reproduction: `docs/googlebook-live.md`. Earlier KVM fault localization:
`evidence/2026-10-19-googlebook-bringup/`.
