# Phase 4: the laptop's own payload, key and install (ANAL-229, 2026-10-24)

Phase 3 (`../2026-10-24-adapt-phase3/`) lets the laptop build Google's release for itself. Phase 4 turns
that build into an update the laptop installs after the owner approves it. The pieces:

- **Payload.** `openbook-adapt payload` writes it:
  - the changed partitions in full, as 2 MiB REPLACE operations (all-zero chunks as ZERO);
  - every other partition as an identity SOURCE_COPY, which Virtual A/B satisfies without writing (the
    snapshot reads those blocks from the installed slot); update_engine then verifies it against the
    installed release's hash.

  Every dynamic partition is listed. The new build's timestamp and security patch let update_engine
  refuse a downgrade. Space for two RSA-4096 signatures is reserved.
- **Key.** OpenBook Update 2.0 creates this laptop's key in Android Keystore: RSA-4096, never exported
  (`LaptopKey`). It signs the payload's two hashes, and the engine checks both signatures against the key's
  certificate before inserting them (`sign`). update_engine accepts them only once that certificate is in
  the running system's `otacerts.zip`.
- **Install.** After the owner reviews and confirms in the app, `InstallWorker` serves the payload on the
  loopback interface (unguessable path, byte ranges) and calls `UpdateEngine.applyPayload`.

## Results

| Check | Result |
|---|---|
| Google's own tools on the host (`host/payload-checks.json`) | A payload from RB-20261023-02 to RB-20261023-03 with its layer embedded: delta_generator verifies its signature. `ota_extractor` (update_engine's payload consumer) applies it onto RB-20261023-02 and gives all 10 target partitions byte for byte |
| **Ruby's update_engine in QEMU, the pinned adapter** (`vm/`) | Slot A is the apply harness (RB-20261023-02 plus a test driver). An `openbook-adapt` payload installing RB-20261023-03 into slot B: **apply 11/11, boot B and merge 7/7, merged slot byte-identical to the release, fallback from a broken slot 7/7** (`summary.json`) |
| **On the G14, the pinned adapter** (`laptop/`) | The engine downloads Google's real release (7.8 GB, 522 s, MD5 verified). Reconstruct takes 40 s. RB-20261023-03 is rebuilt byte for byte; the cross build and the embedded-layer release match the host byte for byte (29–30 s each). Then the embedded release's payload against the laptop's actual installed release takes 6 s: only `system` and `vbmeta` written, eight identity copies. Signed with a throwaway test key; never applied |
| App (JVM) | 23 tests: the checklist follows the adaptation, held and failed reasons, the build kept but not offered without an enrolled key, the engine's files parsed |
| App on Google's Android Desktop emulator, the pinned APK `cd2c896e…` and adapter `090fe211…` (`emulator/`) | 13/13 instrumented tests, plus `openbook-adapt` as the app's child (1/1). The engine on the emulator's tools: 9/9. As a privileged system app: REBOOT granted, battery-exempt, started at boot. 54 screenshots. The tests include Keystore signing that verifies as a standard SHA256withRSA signature (what update_engine checks), the enrollment check against an otacerts.zip, and the loopback server (whole file, ranges, refusals). `openbook-adapt` ran under Android's app seccomp filter |
| Screens (`screenshots/`) | The new states on the emulator, light and dark: checking against the adaptations, built but waiting for the key, held for an adaptation (with the reason), a failed build, and ready to install |
| Engine | 40 tests on the host's shell and on Android's mksh R59, one-true-awk and toybox. They cover adapt, a held release that stays held for the same layer and is tried again under a new one, a fault (exit 11), space, stop, sign and pruning |

A first VM run with a development build of the adapter, before the review fixes, also passed every stage.
The run above uses the pinned bytes.

## How it reaches the laptop

Two OpenBook updates:

1. **R1** ships the adapter (pinned `090fe211…`), the AOSP AVB test key it signs vbmeta with (hash-pinned),
   OpenBook Update 2.0 (pinned `cd2c896e…`) and the release's layer (`embed-adapter-layer.sh`). After R1
   the laptop builds and checks Google's next release by itself, then waits for its key.
2. The laptop creates its key the first time the app runs. The shell reads the certificate:
   `am broadcast -a org.openbook.update.action.LAPTOP_KEY -n org.openbook.update/.work.LaptopKeyReceiver`.
3. **R2** adds that certificate to `otacerts.zip`. From then on, each build the laptop makes carries the
   certificate forward (the adapter copies the running `otacerts.zip`), and the laptop installs Google's
   next release itself, with the owner's approval.

## Not tested here

- The adapter in the app's own SELinux domain on the laptop. On the laptop it ran as adb's shell; under app
  seccomp it ran on the emulator. Its first run in `openbook_update_app` comes with the first Google release
  after R1. A denial would stop it before anything is installed.
- An install by the app on the laptop. That needs R2 and Google's next release (phase 5).
