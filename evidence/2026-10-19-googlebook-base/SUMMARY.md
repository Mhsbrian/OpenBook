# ANAL-228: Googlebook alternative image base

2026-10-19. OpenBook baseline `0664d66`; upstream GBRUNCH
`a8936fd33e50efda3f1b36e332ab30b67b709ab1`. Source review and next gates:
`docs/googlebook-image-base.md`.

## Results

| Check | Result | Scope |
|---|---|---|
| Upstream unit tests | 17 AMD + 5 menu checks passed | Open-source tests; no new kernel build or private-fixture UEFI run |
| Recovery preflight unit tests | 7/7 passed | Synthetic raw/ZIP identities, size/digest mismatch, symlink/FIFO/device rejection; even a profile claiming installable cannot enable it |
| Retained Ruby raw recovery | Match | 19,069,493,760 bytes, SHA-256 matches reviewed pin; read-only |
| Retained Ruby ZIP | Match | 7,816,442,985 bytes, SHA-256 and recorded official manifest MD5 match; read-only |
| Engine base checks | 19/19 passed | Real host engine CLI and socket daemon, sparse target, copied live source; unsupported/malformed requests and source markers refused; explicit AOSP plan replays with the same digest; tampered recovery plan refused before write |
| Existing installer regression | 69/69 passed | Real host engine, whole-disk and alongside installs on regular image files, source/disk/power/confirmation refusals, partition readback and simulated firmware-variable checks |
| Standalone app compiler | 26 Kotlin files, zero warnings/errors | Initial UI revision; final revision additionally built with Soong below |
| Final Android build | Passed | `OpenBookInstaller` and `openbook-install`, `anybook_g14_x86_64-cp2a-userdebug`, 48 seconds |
| Final QEMU chooser | 7/7 passed | Built APK on a private copy of `openbook-live-20261018-anal192e`, KVM/OVMF, virtio-vga 2880×1800, density 240, SELinux enforcing |

The QEMU run starts the built APK as a freeform window, selects Googlebook,
verifies Continue disabled, returns to AOSP and reaches Disk, goes back to the
base choice and then Try/Install. There are no UI timeouts or captured crashes;
the sparse NVMe target's size/allocation/write timestamps remain unchanged.
Screenshots show the actual Compose app, not HTML mockups. Both themes were
visually checked for clipped text, controls and status copy.

The VM retains the existing live image's daemon. The changed engine is separately
tested by the real host daemon/CLI fixtures and built by Soong. This is not an
end-to-end install test of a newly rebuilt whole Android image.

The first screenshot rehearsal exposed a test harness problem: its root-console
`svc power` call lacked the ART classpath exports. The harness now exports them
before that call. Its XML checker also now distinguishes echoed shell commands
from output and checks the button container's enabled state. The final fresh VM
run in `qemu-checks.json` passes after those corrections and the final card layout.

## Reproduction

```sh
python3 -m unittest discover -s tests -p 'test_amd*.py' -v   # in pinned GBRUNCH checkout
python3 -m unittest discover -s tests -p 'test_googlebook_boot_menu.py' -v
python3 scripts/installer/recovery-preflight-test.py -v    # in OpenBook
python3 scripts/installer/recovery-preflight.py --raw /path/to/retained/recovery.bin
python3 scripts/installer/recovery-preflight.py --zip /path/to/retained/recovery.zip
```

Build the host engine with `scripts/installer/engine-host-build.sh`, then run
`image-base-test.py --engine BIN --image OPENBOOK.img --run NEW_DIR` through
`scripts/installer/inst-docker.sh`. The existing regression suite uses the same
arguments with `engine-test.py`. For the app, build `OpenBookInstaller` with
the repository AOSP lane lock, then run `image-base-qemu.py --image OPENBOOK.img
--apk APK --run NEW_DIR` through the same installer container. The test output
directory must be inside its writable installer workspace; all disks are regular
files. QEMU has no network or physical disk attached.

## Limits

- The retained recoveries were already present from M0 interoperability research.
  This run did not download, unpack, execute or modify a Google recovery. Only
  metadata/hash reports are committed; no recovery-derived binaries are included.
- `matched: true` means byte identity. It does not establish a license, an AVB
  signature trust chain, device certification, compatibility or boot success.
- No Googlebook G14 image was assembled or booted. No USB, firmware or laptop
  disk was changed. Recovery-use terms and the security/vendor/graphics/layout
  gates in the review remain open before this can become an installable option.
- The updated existing QEMU wizard drivers now include the base page; their full
  GApps, microG and reboot matrices were not rerun for this change.
