# Fixed Ruby adaptation job

ANAL-229, 2026-10-21. This implements the first host execution milestone from
`googlebook-update-workstreams.md`. It is a **private development replay** of the
known camera25 input correction, not a new release, Google OTA reconstruction,
installation service or upstream-signature verifier. It does not include the
experimental OTA guard. No G14 connection is needed.

## What runs

`run-update-workflow.sh` starts the locally retained container by immutable image
ID with networking disabled, a read-only root, all capabilities dropped and no
disk/USB/KVM devices or Docker socket passed through. Source trees and repository
are read-only; the existing private installer workspace is writable. This is a
trusted local operator tool, not an API accepting untrusted paths or profiles.
The image must already exist; the launcher neither downloads nor rebuilds it.

`update-workflow.py` holds the shared `.ruby-release.lock` and performs this fixed
sequence. There is no profile-supplied shell command or arbitrary recipe hook.

1. Verify the original raw recovery, retained derived image/logical partitions,
   helper/probe, public AVB test key and recipe/tool hashes against the versioned
   profile. Check the complete 415-entry native audit inventory digest.
2. Run `compat-audit.py`: native VINTF/APEX/kernel checks, strict SELinux compile
   and service-label checks for Ruby, OpenBook and the reduced hybrid. The raw
   hybrid must still fail its policy negative control. Require both command
   success and complete, matching structured results before proceeding.
3. Recheck inputs, then run the existing exact-build reassembler. Its transform
   changes only eight bytes in the known `libinputflinger.so`, preserving all
   inode/xattr metadata and unrelated files. It rebuilds EROFS, verifies the local
   AVB chain, updates boot digest/size and checks protected GPT/data ranges.
4. Independently rehash the resulting image and validate the builder result and
   manifest. Run the native original/patched converter and drag controls against
   the extracted runtime. Recheck input/profile identities before completion.
5. Retain the candidate, metadata, reports, logs and hashes. Remove only this
   completed job's explicitly enumerated extraction/assembly scratch; save the
   exact private cleanup manifest and actual free-space measurements.

The source image is camera25
`df793f2eed3a5c901659014c2ae368d8e5eeb3d504b514d46fc8c0c1959a7af4`.
The raw recovery is separately pinned to
`4f4490415d4db0721fa99ad10abd64b1b05c284b6c0e413907da948561de8c9e`.
**These two pins do not prove the extraction/adaptation chain between them.**
The selected audit trees are pinned static-check inputs, not an assertion that
every file in the raw recovery was reproduced. The job always records upstream
authentication and raw-to-derived provenance verification as false. The AVB key
is the public AOSP development test key, not a production trust root.

The container and executable/tool inputs are pinned, but this is not a hermetic
AOSP source rebuild. Existing dynamically loaded host-tool dependencies and
retained native library trees remain part of the local build environment.
Unknown/new builds require engineering review and another adapter/profile;
editing hashes until a job passes is not qualification. Installer source pins,
encrypted-data boot, stability, containment, recovery/data rollback and hardware
acceptance remain separate gates.

## Reproduction

Use the existing authorized private inputs. `DATA` below is the host's retained
OpenBook data root. Run from this repository; choose an output directory that
does not yet exist and whose parent is already present. The key argument must
match the pinned public AOSP test key. No owner backup or installed data is an
input to this replay.

```bash
DATA="$HOME/anybook"
A="$DATA/aosp/src"
bash scripts/googlebook/run-update-workflow.sh \
  --original "$DATA/dl/gbos-ruby/android-desktop_signed_recovery_image.bin" \
  --base "$DATA/installer/work/anal228-ruby-live-camera25" \
  --ruby "$DATA/work/gbos-ruby" \
  --product "$A/out/target/product/anybook_g14" \
  --kernel "$DATA/kernel/dist/anybook-g14-gbos-16302624" \
  --tools "$A/out/host/linux-x86/bin" \
  --inventory "$DATA/installer/work/anal228-input27/erofs-inventory" \
  --probe "$DATA/installer/work/anal228-input27/input-replay-native" \
  --key "$A/external/avb/test/data/testkey_rsa4096.pem" \
  --out "$DATA/installer/work/ruby-workflow-new"

python3 scripts/googlebook/update-workflow-test.py -v
python3 scripts/googlebook/update-test.py -v
```

The native probe requires the instruction set of the retained Ruby libraries;
the measured host is the existing Ryzen 7950X build machine. Unsupported hosts
fail the native phase rather than qualify an image. Keep output private: it
contains retained proprietary binaries. Only sanitized reports/logs belong in
the repository, never the image or extracted trees.

## Durable state and failures

`job.json` uses schema `openbook-ruby-update-job/1`. State changes are atomic,
fsynced and retain history with timestamps/free bytes:

`validating → auditing → assembling → verifying → cleaning → assembled_unqualified`

Exit 0 means **assembled and statically checked, still unqualified**. Physical
installation and release approval always remain false. This is not the signed
`ready_for_local_staging` contract and cannot manufacture its approval evidence.
The next service layer can expose these states after authentication; this local
CLI itself does not implement authentication, transport, an APK or remote jobs.

Caught failures/cancellation produce `failed`, the phase and a reason. Each
native process group is terminated/reaped on timeout, cancellation or reserve
violation. Logs are durable while the command runs. Abrupt host failure/SIGKILL
can leave a nonterminal state; **only `assembled_unqualified` is successful**.
Existing or partial directories are never overwritten/resumed. Inspect and
retain failure evidence, clean its explicitly identified scratch once no process
needs it, and start a fresh job. No recovery or automatic retry is implied.

The initial peak additional allocation budget is **64 GiB**, plus **40 GiB free
reserve**. Before assembly the job requires 48 GiB additional; before final
verification it requires 1 GiB. A running native phase checks free space every
0.5 seconds and stops below the reserve. This is cooperative storage protection,
not a filesystem quota: another task can consume space between checks. Cleanup
reports actual before/after free space, not apparent sparse/reflink file sizes;
concurrent host activity can affect that delta. Failed jobs retain their partial
files for investigation and never publish success.

The source issue owns development evidence. A future promoted candidate requires
a numbered Ruby release record, current issue census, frozen plan approval,
fresh tests/installer pins and separate exact-device write approval through
ANAL-232. This replay changes neither the approved USB nor installed G14 pointers.
