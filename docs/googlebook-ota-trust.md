# Ruby OTA trust anchor: refuse stock OTAs, keep OpenBook updates

ANAL-229 (containment: ANAL-230), 2026-10-22. Disposable VM proof plus a
production-shaped image builder. No laptop, USB stick or setting was changed.

## Why this is needed now

The G14 runs Google's Ruby system. It has:
- `ro.build.ab_update=true` and Virtual A/B;
- a running `update_engine`;
- Google's system-update activity enabled.

Its only OTA trust anchor is `/system/etc/security/otacerts.zip`:
- one RSA-2048 certificate, subject `CN=test`;
- archive path `projects/chromeos-release-bot/locations/us/keyRings/RubyMPKeys/releasekey.x509.pem`;
- SHA-256 fingerprint `00:E8:97:B7:…:7F:49:73`.

Any payload signed by that key passes `update_engine`'s signature checks.

The G14 has one slot. Before this work we expected a stock OTA to fail
harmlessly at the missing `boot_b`. The VM shows a trusted, stock-shaped
(Virtual A/B) payload does more first. `allocateSpaceForPayload`:
- rewrites super metadata slot 1;
- creates a copy-on-write snapshot for `system_b`.

It maps `system_b` over `system_a`'s extents, as Virtual A/B does, and puts the
copy-on-write data in free super space. `applyPayload` repeats that preparation.
It stops only at `Device file /dev/block/by-name/boot_b does not exist`.

Afterwards:
- slot `_a` is still the only active slot;
- the boot partitions are unchanged;
- the snapshot state (`/metadata/ota/state`, `snapshots/system_b`) and the
  slot-1 metadata stay behind for `update_engine`'s next cleanup.

A reboot with that leftover state was not tested.

Today a payload signed with Ruby's key would get this far. Once ANAL-231 adds a
second slot, the missing `boot_b` no longer stops it.

## Design

Replace the archive's content with one OpenBook certificate, as a
deterministic stored zip with the single entry `openbook/releasekey.x509.pem`.
`update_engine` reads only entries ending in `x509.pem`.

Ruby's `update_engine` binary names this path. In AOSP `update_engine`, every
installation entry point checks the metadata signature first:

- `verifyPayloadApplicable` and `allocateSpaceForPayload` call
  `VerifyPayloadParseManifest` → `VerifyPayloadMetadata`. This happens before
  any partition preparation.
- `applyPayload` downloads through `DeltaPerformer`. It validates the metadata
  signature before the timestamp and manifest checks, partition preparation or
  any write. The check is mandatory because `ro.secure=1` (`IsOfficialBuild`).

The binary stays Google's stock `update_engine`; only one data file changes.

By design, this file plays no part in:
- app updates (APK signatures);
- Mainline/APEX updates (their own keys, checked by `apexd`/PackageManager);
- boot.

App and Mainline updates have not yet been exercised after the change.

Compared with the 2026-10-20 OTA guard (`googlebook-ota-guard.md`): the guard
replaced `update_engine` with a rebuilt binary that refuses every installation
request. That also blocks our own updates and needs a native rebuild against
Ruby's libraries. The trust anchor changes one file, keeps the stock binary and
leaves a path open for OpenBook-signed updates.

An untrusted apply request still does some housekeeping before its signature is
checked. Measured in the VM:
- it cancels a prepared but not yet applied update (`ResetUpdate`);
- it confirms the booted slot as good;
- it runs the previous-update cleanup;
- it asks the boot HAL to mark slot B unbootable, which our single-slot HAL
  refuses.

It writes no partition data. Verify and allocate requests check the signature
first.

## VM evidence

Two images were built from the same camera25 base, harness and payloads:
- **trust**: OpenBook test certificate in place, image `2db57f34…`;
- **stock**: Google's archive kept, image `3c3ca47a…`.

Each was booted once in QEMU (TCG, no NIC, software TPM). The harness waited
until `update_engine` finished its boot-time cleanup, then sent verify,
allocate and apply for each payload. Outcomes come from `update_engine`'s own
log.

| Payload | Request | Trust image | Stock control |
|---|---|---|---|
| foreign-static | verify, allocate, apply | **Refused** (`kDownloadMetadataSignatureMismatch`), before partition preparation | Refused, same |
| openbook-static | verify, allocate | Signature verified; allocate prepares nothing (static partitions only) | Refused at signature |
| openbook-static | apply | Signature verified, then stops at the missing `boot_b` (`kInstallDeviceOpenError`) | Refused at signature |
| openbook-vab | verify | Signature verified | Refused at signature |
| openbook-vab | allocate | Verified, then `system_b` snapshot and super slot-1 metadata written | Refused at signature |
| openbook-vab | apply | Same preparation, then stops at the missing `boot_b` | Refused at signature |

Disk after each run:
- **Both images:**
  - `boot_a`, `init_boot_a`, `vendor_boot_a`, `vbmeta_a` and super slot 0 are
    unchanged;
  - boot control shows `_a` active, one slot, slot B priority 0.
- **Trust run:** super slot 1 and `/metadata/ota` changed, from the trusted
  Virtual A/B payload only.
- **Stock run:** no change.

Neither run activated a second slot or wrote partition data. Each run has one
`system_server` SIGSEGV. That crash class is also present on the unchanged
baseline (`googlebook-ota-guard.md`), so it is not caused by this change.

Results and superseded runs: `../evidence/2026-10-22-ruby-ota-trust/`.
Two earlier runs were superseded:
- the first test payloads lacked `max_timestamp`, so trusted applies stopped at
  the anti-downgrade check;
- one foreign allocate request arrived during the boot-time cleanup and was
  refused as busy, not at the signature.

The harness now waits for the cleanup, and the judge reads `update_engine`'s
log instead of interleaved console lines.

## Tools

- `scripts/googlebook/make-ota-test-payloads.sh`: creates two disposable RSA-4096
  signers (OpenBook stand-in and Google stand-in) and three full payloads:
  - `foreign-static`: boot + vbmeta, foreign signer;
  - `openbook-static`: boot + vbmeta, OpenBook signer;
  - `openbook-vab`: compressed Virtual A/B `system` + boot + vbmeta, OpenBook
    signer.

  `max_timestamp` is 2100-01-01, as for a newer stock build.
- `scripts/googlebook/build-ota-trust-candidate.py`: replaces only the trust
  archive. It pins the stock archive's hash and entry, accepts one public RSA
  certificate pinned by SHA-256 and refuses key material. Options:
  - `--input-correction` reproduces RB01's system;
  - `--vm-test` adds the disposable harness (stock `update_engine_client`, test
    payloads, the four neverallow-checked shell Binder grants from the OTA guard
    work);
  - `--stock-trust` keeps Google's archive as the control.
- `scripts/googlebook/ota-trust-qemu.py`: boots a private copy with no NIC. It
  judges each verify/allocate/update step and compares:
  - the single-slot boot partitions;
  - misc boot control;
  - each super metadata slot;
  - `/metadata/ota`.

  It also checks enforcing mode and denials that involve `update_engine`.
  `--reevaluate` judges a finished run again without booting.
- The shared reassembler (`build-input-candidate.py:build_system`) can add new
  root-owned `system_file` paths, but only for annotations marked
  `experimental_*` with `deployment_eligible: false`. The EROFS comparison covers
  the added rows. Installer pinning, packaging and boot-entry tools now refuse
  any `experimental_*` manifest.

## Reproduce

```sh
W=$HOME/anybook/installer/work/anal229-trust-a1   # new private directory
A=$HOME/anybook/aosp/src
scripts/googlebook/make-ota-test-payloads.sh "$A/out/host/linux-x86/bin/delta_generator" "$W/inputs2"
COMMON="--base $HOME/anybook/installer/work/anal228-ruby-live-camera25 \
  --tools $A/out/host/linux-x86/bin --inventory $EROFS_INVENTORY \
  --key $A/external/avb/test/data/testkey_rsa4096.pem --vm-test $W/inputs2/payloads \
  --vm-test-signer $W/inputs2/keys/openbook-test.x509.pem"
scripts/installer/inst-docker.sh python3 "$PWD/scripts/googlebook/build-ota-trust-candidate.py" $COMMON \
  --cert "$W/inputs2/keys/openbook-test.x509.pem" \
  --cert-sha256 "$(sha256sum "$W/inputs2/keys/openbook-test.x509.pem" | cut -d' ' -f1)" --out "$W/trust-test"
scripts/installer/inst-docker.sh python3 "$PWD/scripts/googlebook/build-ota-trust-candidate.py" $COMMON \
  --stock-trust --out "$W/stock-test"
for m in trust stock; do
  scripts/installer/inst-docker.sh python3 "$PWD/scripts/googlebook/ota-trust-qemu.py" \
    --candidate "$W/$m-test" --qemu "$REVIEWED_TCG_QEMU" --tools "$A/out/host/linux-x86/bin" \
    --seconds 780 --out "$W/vm-$m"
done
```

`EROFS_INVENTORY` is the read-only helper from `googlebook-input-update.md`.

The release candidate on RB-20261021-01 (the release hub repeats this on its
next base):

```sh
R=$HOME/anybook/installer/work/anal229-trust-r1
scripts/installer/inst-docker.sh python3 "$PWD/scripts/googlebook/stage-base.py" \
  --source "$RB_20261021_01_CANDIDATE" \
  --source-sha256 4b110e750ec2e7874ccdaf563ca8b9c7d45cd8eccc18848478edb1f9b5382cf3 \
  --tools "$OTATOOLS/bin" --out "$R/base-rb0121"
cp config/security/openbook-ota-2026.x509.pem "$R/"
scripts/installer/inst-docker.sh python3 "$PWD/scripts/googlebook/build-ota-trust-candidate.py" \
  --base "$R/base-rb0121" --base-sha256 4b110e750ec2e7874ccdaf563ca8b9c7d45cd8eccc18848478edb1f9b5382cf3 \
  --tools "$A/out/host/linux-x86/bin" --inventory "$EROFS_INVENTORY" \
  --key "$A/external/avb/test/data/testkey_rsa4096.pem" --cert "$R/openbook-ota-2026.x509.pem" \
  --cert-sha256 c755c4a3313c6d597538e19c2ad4af77334acb1681dff044c0c92aea3f6410bb --out "$R/candidate"
scripts/googlebook/sign-ota-payload.sh --self-test "$A/out/host/linux-x86/bin/delta_generator" \
  ~/.local/share/openbook-keys/ota/openbook-ota-2026.key config/security/openbook-ota-2026.x509.pem
```
The camera25 base is the reviewed fresh live image used by the other builders.

## OpenBook OTA key (approved 2026-10-22)

B Honey approved the custody plan on ANAL-229 on 2026-10-22. The key was
generated that day.

| Item | Value |
|---|---|
| Algorithm | RSA-4096, PKCS#8 PEM, SHA-256 signatures |
| Certificate | `config/security/openbook-ota-2026.x509.pem`, `O=OpenBook, CN=OpenBook Ruby OTA release key 2026`, valid 2026-10-22 to 2056-10-21 |
| Certificate file SHA-256 | `c755c4a3313c6d597538e19c2ad4af77334acb1681dff044c0c92aea3f6410bb` |
| DER fingerprint (SHA-256) | `25:BB:B0:69:1D:B3:24:6A:51:09:95:13:9D:EF:80:4C:C1:9B:D7:CE:49:E7:B8:3B:D1:AA:BB:EE:5F:CC:DD:D2` |
| Private key | Build host, `~/.local/share/openbook-keys/ota/` (directory 0700, key 0600) |
| Offline backup | Same key, scrypt + AES-256 encrypted, in `backup/`. The owner copies it to offline media and moves the passphrase into a password manager. |

The key directory is outside every repository and outside `~/anybook`, which
the build containers mount. No build container can read it. Only the
certificate enters images and Git. `.gitignore` refuses `*.key` and `*.pk8`.

`scripts/googlebook/sign-ota-payload.sh` signs on the host with
`delta_generator`'s hash-file mode, then verifies the result against the
certificate. Only its two `openssl pkeyutl` calls touch the key, so a hardware
token can replace them later. It refuses to run:
- in a container;
- with a key under `~/anybook` or in a git work tree;
- with a key that is not mode 0600;
- with a key that does not match the certificate.

`--self-test` signs an inert payload (partition `openbook_selftest`,
`max_timestamp` 1), verifies it against the certificate, checks that another
key fails, and deletes it. It passes with the real key. Test payloads are never
signed with the real key.

If the key is lost, the USB Update path, which does not use `update_engine`, can
install a new certificate.

The AVB key is still the public AOSP test key. Moving verified boot to an
owner-held key is a separate decision of the same shape.

## Release candidate on RB-20261021-01

`stage-base.py` turns a reviewed image into a reassembler base:
- the image and its manifest;
- the super logical images, unpacked with otatools' `lpunpack` and each checked
  against the manifest.

`build-ota-trust-candidate.py --base-sha256` then layers the certificate onto
that exact image. The shared reassembler now accepts any pinned, reviewed base
(camera25 stays the default) and checks every logical image against the base
manifest.

Development candidate `9985be733553f1adfaf500864d4f02e03d47b585a63fcc109d866f3e2aa47184`:
- base: RB-20261021-01, image `4b110e75…`, vbmeta `611d49f2…`, the vbmeta the
  G14 reports;
- the only changed file is `/system/etc/security/otacerts.zip`, archive
  `3e1529c9…`;
- only the `system` logical image differs;
- boot partitions and kernel are identical;
- the lid-guard module and trackpad fix are retained;
- new vbmeta `3ceeb6ac…`.

In the VM (TCG, no NIC):
- **Boot:** completes with SELinux enforcing, `openbook_lid_guard` loaded and
  no AVB errors. Runtime matches the unchanged RB-20261021-01 run (one
  `system_server` SIGSEGV in 720 s against two in 540 s).
- **Harness (a twin with the same certificate):** payloads from both
  disposable keys are refused at the metadata signature on verify, allocate
  and apply, before any partition preparation. The device reports archive
  `3e1529c9…`, and super slot 1 is unchanged. All 19 checks pass.

Evidence: `release-candidate.json` and `vm-release-cert.json`.

USB packaging: `preserve-update.py --allow-logical system` now accepts a
reviewed system change on the same terms as `vendor_dlkm`:
- explicit, never implicit;
- every other logical image, boot image and kernel identical;
- the stage marked incomplete until `migration-package.py` rebinds the
  installer and `compose-usb-plan.py` composes the plan.

`laptop-update.py spec --allow-logical system` already accepted it.

## Next

1. Release hub: the next Ruby release after RB-20261021-02 should layer the
   certificate onto that release's image. Run `stage-base.py` on it, then
   `build-ota-trust-candidate.py --base-sha256 <its hash> --cert
   config/security/openbook-ota-2026.x509.pem`, then the usual USB chain with
   `--allow-logical system`. It needs its own plan approval and stick-write
   approval.
2. On the laptop after the update, check with read-only ADB that
   `/system/etc/security/otacerts.zip` has SHA-256
   `3e1529c919baf5bbe71c729e2f6884d034a589328af0fb41a1ae730ac3342a59`.
3. Later: our own OTA delivery (ANAL-231 second slot, OpenBook payloads signed
   with `sign-ota-payload.sh`) and the admin update UI.
