# Ruby update research, 2026-10-20

ANAL-229, starting from migration commit `d904dc2`. This is a partial
qualification and a local staging prototype. **No tested complete OS-update
containment or hardware promotion is delivered.** No physical medium was
written. Do not deploy the optional engine-stop fragment.

Decision/reproduction: `docs/googlebook-updates.md` and
`docs/googlebook-update-prototype.md`. Follow-on backlog: ANAL-230
(boot-compatible containment and current-device/network qualification), ANAL-231
(recoverable Ruby writer and data-schema rollback).

## Evidence boundaries

| File | What it establishes |
|---|---|
| `inventory.json` | Retained Ruby files, engine init, build properties, APK manifest components, hybrid partition names and hashes |
| `gms-allowlists.json` | Selected privileged grants in product and GMS APEX allowlists; static declarations, not current device state |
| `security.json` | Observed vbmeta/OTA certificate identities, rollback fields, freshly fetched official recovery-index entry; **not** an independent trust anchor or verified OTA signature |
| `bootcontrol.json` | CRC-valid one-slot boot-control record from the initialized disposable VM's misc partition |
| `original-preflight.json` | Retained raw input digest matches the earlier reviewed baseline; installation remains disabled |
| `baseline.json` | Earlier camera25 observation, reused as baseline: engine process and both Binder interfaces present |
| `rejected-vendor-*.json`, `ineffective-first-stage.json` | Overrides fail or disappear; stock engine still starts |
| `rejected-executable-mask.json` | Strict `secilc` rejects an executable bind-mask permission; neverallow retained |
| `stop-experiment-recipe.json` | Exact native experiment tuple and injected RC hashes; strict compilation and enforcing requested |
| `native-build.json` | Successful native preparation, compiler flags and tool/policy/log hashes; no engine-stop permission grant added |
| `stopped-fresh-data.json` | 275.7-second direct-kernel observation: seven stopped-state samples, both interfaces absent in seven checks; no completed boot, checkpoint failure and reboot |
| `stopped-preserved-data.json` | 480.7-second UEFI run with initialized encrypted data: 12 stopped-state samples, both interfaces absent in 12 checks, boot complete, one distinct system-server SIGSEGV and zygote restart |
| `reversed-preserved-data.json` | 480.7-second UEFI reversal: original process and both interfaces return, boot completes, same system-server SIGSEGV class recurs; input/source TPM/decoy unchanged |
| `preserving-preparation.json`, `reversal-preparation.json` | Private regular-file preparations, protected ranges and unrelated EFI content preserved, sources unchanged |
| `metadata-keys.json` | Four pre-existing synthetic metadata-encryption files unchanged after both suppression and reversal trials; no keys included |
| `*-tests.txt` | Synthetic positive/negative checks and existing regressions: 57 tests across six suites |

Each observation contains the original serial SHA-256, original line numbers
and bounded excerpts. Repeated logcat dumps can repeat the same crash; excerpt
counts are line counts, not independent crashes or uninterrupted monitoring.
Service-list lines interleave with kernel output, so matching counts are a lower
bound. `engine_binder` counts both found and not-found records: read the text.
The original raw logs, disk images, TPM state and extracted keys stay private.

The initialized VM reaches boot completion at guest 153.4 seconds. Guest time
differs from wall time under TCG. The runner's zero exit means observation
completion; it is not a stability or containment pass. The persistent logger's
ten-minute completion marker is absent in the eight-minute run, as expected.
There is no NIC, no Play update exercise and no physical G14 state in these
observations. Rejected experiments with the engine still running also show
checkpoint failures; the fresh-data failure is not attributed solely to
suppression.

The recorded recipe predates the CLI rename from `--quarantine-update-engine`
to `--test-update-engine-stop` and the addition of `deployment_eligible: false`.
The RC bytes are unchanged. No SELinux permission exception or failed override
from earlier experiments remains in the implementation.

## Reproduction details

Inventory and test commands are in the prototype document. Use the retained
Ruby extraction, camera25 audit's extracted GMS APEX, camera25 vendor and live
manifest. The inventory's manifest/file/tool hashes identify those inputs.

To independently inspect the security inventory, run the local AOSP
`external/avb/avbtool.py info_image --image` against stock
`parts/vbmeta_a.img` and the camera25 probe's `vbmeta.img`.
The SHA-256 public-key field hashes the AVB-format public-key bytes, not PEM:
the key starts at header-size 256 + authentication-block-size +
public-key-offset and has public-key-size bytes (AVB big-endian header).
Compare flags, algorithm, rollback index and rollback-index location.
These operations inspect bytes; authenticate their origin separately.

Read certificates directly from system and recovery `etc/security/otacerts.zip`.
Use `openssl x509 -noout -subject -issuer -fingerprint -sha256`; hash the DER
public key from `openssl x509 -pubkey -noout` piped to
`openssl pkey -pubin -outform DER` for the SPKI digest. Do not identify ownership
from the certificate's subject/path. `security.json` records the recovery-index
URL, fetch date and SHA-256; that server's future response may change.

The misc slot record is 32 bytes at misc offset + 2048. Validate the first 28
bytes' CRC32 against its final little-endian word, magic `0x42414342`, version
and the low three bits of byte 9 for slot count. This is a saved-file
observation, not a fresh boot HAL query.

`migration-qemu.py:metadata_key_hashes` extracts `/vold` from a private copy of
the metadata partition and compares file digests. The four files exist and
match; debugfs's inability to restore guest ownership as the unprivileged host
user does not change their bytes. No owner PIN, credential-encrypted user
content or hardware KeyMint behavior is validated by this synthetic check.

## Remaining acceptance

Actual Google signed-payload/device assertion validation, independent key
provenance and usage authorization, networked ordinary/idle/charging/reboot/
recovery containment, app-update preservation, stable runtime, failed-boot
dual-system fallback, physical write interruption and newer-schema restoration
remain open. Host staging interruption and byte preservation tests do not
substitute for those tests.
