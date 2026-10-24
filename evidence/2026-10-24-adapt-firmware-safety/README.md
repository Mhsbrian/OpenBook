# The laptop's adapter checks firmware safety; R1 with ANAL-251 (ANAL-229, ANAL-251, 2026-10-24)

ANAL-251 found that Google's `gscutil` ran at every boot on the G14. It sent security chip commands through
the PC's firmware TPM. ANAL-251 neutralised the two init scripts, and `check-firmware-safety.py` checks every
OpenBook image against `device/anybook/common/safety/firmware-safety.json`. The laptop builds Google's next
releases by itself (phase 3), so it must apply the same rules. This change does that, and puts ANAL-251's
work in the same release (R1) as phases 3 and 4.

## What changed

- **`openbook-adapt` (pinned `b80879f2…`, a clean reproducible build of `d4a34cf`).**
  - `adapt` runs the firmware-safety check (`safety.go`) on the release it has adapted, before building
    anything. It checks the adapted `system`, Google's new `system_ext` and `product`, and the init scripts
    inside every APEX.
  - Reading: EROFS in place (flat files); ext4 APEX payloads through a small reader (`ext4.go`); compressed
    files through the laptop's `fsck.erofs`.
  - The rules are the adapted system's own `/system/etc/openbook/firmware-safety.json`: OpenBook's file, carried
    from the running release and checked against the layer byte for byte.
  - These hold the release (exit 8, with the reason the app shows): any finding, missing rules, or content
    it cannot read.
  - `firmware-safety` runs the same check on images or trees, to compare it with the host script.
  - The payload writer refuses a manifest with a postinstall step (`run_postinstall` or `postinstall_path`).
- **What the check reads beyond the host script.** Android's init parses every regular file in an `etc/init`
  directory, whatever its name, and an APEX's `etc/*rc` (versioned scripts). The laptop reads both; the host
  script reads `*.rc` only. Today that is 5 versioned APEX scripts in Google 16658739, none with a trigger.
  A compressed APEX (`.capex`) holds. Python's `(?i)` also matches `i` with `ı` and `İ`, which Go's RE2 does
  not, so the text is matched with those folded to `i`. So the laptop can only hold more than the host,
  never less.
- **The image.** `build-update-app-candidate.py --adapter` ships the rules. It runs both checks on the
  finished candidate: `check-firmware-safety.py` (ANAL-251's `safety_check`) and the adapter's own
  `openbook-adapt firmware-safety`. It rejects a candidate that fails either, because the laptop would hold
  every release.
- **The laptop test.** `adapt-device-test.sh` can push Google's partitions reconstructed on the host
  (`RECON`), use a release's OpenBook files from a tar (for a release the laptop does not run), pass rules,
  and require a hold.

## Review

An independent review of the first version (`325006b5…`) confirmed one way the laptop could pass what the
host fails. It was the `ı`/`İ` case folding above: `/sys/firmware/efıvars` or a tool named `fırmware_updater`
passed in Go and failed in Python. It also confirmed that the rules parser accepted a null, a duplicate key
and a key in another case. It raised lesser points:
- repeated whole-image extraction with an `fsck.erofs` lacking `--path`, and no free-space check;
- some format errors exiting 1 instead of holding;
- EROFS inline whole-block tails;
- unbounded directory and extent-tree reads;
- APEX entry names containing NUL;
- the builder running only the narrower check.

All are fixed and tested in `d4a34cf`, pinned as `b80879f2…`. Every result below was run again on those
bytes. The first version had passed the same runs (G14 3/3, QEMU, emulator, parity); those results are
superseded.

## Results (all on the pinned adapter `b80879f2…`)

| Check | Result |
|---|---|
| Unit tests (`tests/go-test.txt`) | 20 pass. The new ones cover: Python-identical `rc_hits` and finding text, including `ı`/`İ`; strict rule refusals; the EROFS and ext4 readers on synthetic images (flat plain, flat inline with whole blocks, a hashed 300-entry ext4 directory); refused malformed content (whole-block inline tail, a self-referencing extent tree, no room); the check end to end on a tree with APEXes, including a NUL-named entry; holds; and payloads with and without postinstall. The compressed-file test passes with `fsck.erofs`: two directories, one whole-image extraction (second run in the file) |
| Builder (`tests/build-update-app-candidate-test.txt`) | 13 (1 skipped: no extracted Ruby policy here). The rules ship exactly as committed, and the adapter's check rejects a candidate |
| Go vs `check-firmware-safety.py` (`host/parity.json`) | Google 16658739, Google 16452207, RB-20261023-03 and the test release: **findings (in order) and inventory identical** in all four. Google's builds and RB-20261023-03 each fail on exactly the two `gscutil` scripts; the test release passes. The reviewed scripts are the same in both Google builds |
| The R1 chain as a test input (`host/test-release.json`) | On the R1 parent `75fa0196…` (RB-20261023-02's staged candidate): `build-safety-candidate.py` → `stage-base.py` → `build-update-app-candidate.py --adapter` (APK `cd2c896e…`) → `embed-adapter-layer.sh`. Both candidates pass the firmware-safety checks (the app candidate both checks); so does the adaptation inside the embed step. Release `system` `6f2abd2d…`, `vbmeta` `4cfa2acc…` |
| Host proofs (`host/proofs.txt`) | Fixed point: adapting Google 16658739 with the layer the test release carries reproduces its `system` and `vbmeta` byte for byte (28 s), the check passing with both scripts neutralised. RB-20261023-03's layer is held twice: with no rules, and with the repository's rules (Google's `gscutil`). Neither hold leaves output. The payload over RB-20261023-03 has no postinstall step, and `check-firmware-safety.py payload` passes. delta_generator verifies its signature, and `ota_extractor` gives all 10 partitions of the test release |
| **On the G14** (`laptop/`) | As adb's shell user, in a temporary directory that was removed after the run. Google's partitions were reconstructed on the host and pushed; the download and on-laptop reconstruct were proven in phase 3. **3/3:** (1) the test release adapted in **32 s, `system` and `vbmeta` byte-identical to the host, the check passing** (both scripts neutralised, 5 reviewed scripts, 16 APEX `*.rc` files, 5 scripts beyond the host set), and its payload in 6 s: only `system` and `vbmeta` written, no postinstall step. (2) RB-20261023-03's own layer, with the running system as OpenBook's files: **held**, as it carries no rules. (3) The same layer with the repository's rules: **held** on Google's `gscutil.rc` and `gscutil-executor.rc`. |
| QEMU (`vm/`) | Ruby's own update_engine, slot A the apply harness (RB-20261023-02 plus a test driver). An `openbook-adapt` payload (`7a69286d…`, signed with the OpenBook OTA key) installs the test release into slot B: **apply 11/11, boot B and merge 7/7, merged slot byte-identical to the release, fallback from a broken slot 7/7** (`summary.json`). So the R1 content boots in Ruby's VM, ANAL-251's change included |
| Emulator (`emulator/`) | Google's Android Desktop emulator, the pinned APK `cd2c896e…` with `openbook-adapt` `b80879f2…` in `/system/bin`: 13/13 instrumented tests, the engine 9/9, and `openbook-adapt` as the app's child under the app seccomp filter (1/1). As a privileged system app: REBOOT granted, battery-exempt, started at boot. The screens are phase 4's (same APK) |

## R1

R1 ships, on the RB-20261023-02 base:
- ANAL-251's neutralised `gscutil.rc` and `gscutil-executor.rc`;
- OpenBook Update 2.0 (`cd2c896e…`);
- `openbook-adapt` (`b80879f2…`) and AOSP's AVB test key;
- the firmware-safety rules (`2b806321…`);
- the release's layer.

After R1, the laptop builds and checks Google's next release by itself, under these rules, then waits for
its key. R2 enrolls the key. The handoff for the release is `handoff-ANAL-229.json`, with ANAL-251's
`../2026-10-24-ruby-safety/handoff-ANAL-251.json`.

## Not covered

- `efi_pstore` stays open: the owner chooses the command line or keeping the logs (ANAL-251).
- The neutralised image has not booted on the G14 itself yet (ANAL-251: VM only); that is the release's
  install.
- The adapter's first run in the app's own SELinux domain on the laptop comes with Google's first release
  after R1.
