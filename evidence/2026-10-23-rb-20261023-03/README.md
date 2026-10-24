# RB-20261023-03: OpenBook Update, built and VM-rehearsed (ANAL-256, 2026-10-23)

## On the G14, 2026-10-24 (`g14/`)

B Honey confirmed "Install 3c3b3b38 on the G14" on ANAL-232.

- **Before (read-only):** slot `_b`, boot digest `8517e2fe…`, Google 16658739, 68 % battery. No other adb or update session. The dry run passed.
- **Apply:** `g14-ota.sh --via-adb --approved "RB-20261023-03 to the G14"`, under the Ruby track lock. Download and verification took 00:36:35 → 00:37:25 UTC, with `ErrorCode::kSuccess`.
- **Restart:**
  - The first idle watcher subtracted Android's `uptimeMillis` from `/proc/uptime`, which includes suspend time, so its "idle" verdict was wrong. It was discarded before anything was restarted.
  - The corrected watcher read Android's own "N ms ago": input was still 1–3 minutes old.
  - The owner then wrote that the laptop was on and idling, so the restart was done on the owner's word (00:48:23 UTC).
- **After:** boot completed and adb was back at 00:49:14 UTC.
  - Slot `_a`, boot digest `14e3e6c6…`, exactly the release's `vbmeta`. Same Google build.
  - `update_engine_client --merge` reports success (CleanupSuccessfulUpdate kSuccess).
- **Counts:** users 2 → 2, packages 302 → 303 (the app), third-party 35 → 35, accounts 0,2 → 0,2. Settings 39/179/206 unchanged.
- **App:**
  - Privileged system app (`/system/priv-app/OpenBookUpdate-v1`), REBOOT granted, process in `openbook_update_app` for user 10.
  - First live check against Google's listing: `exit 0 (OK)`. No denials for the app.
  - As rehearsed: notifications are not yet allowed (the app asks), and the app is also installed, stopped, for user 0.
- **Crashes:** only Google's `repairmode` (×2, known). No tombstone or ANR.
- **OpenBook OTA certificate:** unchanged (`3e1529c9…`).
- **Rollback:** slot B keeps RB-20261023-02 until the next update. A slot that fails to boot falls back by itself. Going back after this boot means sending RB-20261023-02 as an OpenBook update.

Plan v1, `d6b1633d731ddc3eeca76ee78ed160fb6e40fe69619038ba983aff0a4864d126`, approved by B Honey on
ANAL-232 (`01a16aa8…`). The release is RB-20261023-02 plus OpenBook Update (ANAL-229, PR #121 `a05f832`,
APK `f3308832…`). It is delivered to the G14 as an OpenBook-signed incremental update into **slot A**,
because the laptop runs slot B. Written to the G14 on 2026-10-24 (below); the stick is unchanged.

## Artifacts (`build.json`)

| Item | SHA-256 |
|---|---|
| Candidate C (`candidate-manifest.json`) | `71da0228488781fa7db6bbb2b07b8559024023b606ae54cd868f780954b9cc24` |
| `system` | `2e7b342585b70b4829831ec32b6ec39681a58c8cc5735c414b6139724dbdb532` (same bytes as ANAL-229's production check) |
| `vbmeta` | `d19d423c0d8bc9036ef51cf4501e1b95128c475272eee17e37696772af74f8cc` |
| **Laptop payload P** (incremental, 4,472,248 bytes) | **`3c3b3b38b3a889149df198cf020d8086ece4b0049f16f439545bde70eef1b354`** |

The other eight partitions are byte-identical to RB-20261023-02 (`rel-prod.SHA256SUMS`).

## Gates

| Plan test | Result |
|---|---|
| T1 content | Only `system` and `vbmeta` change. The added paths are the five app files, and the changed files are the four platform-policy files. No experimental marker; the neverallow check passed. `avbtool verify_image` verifies all ten images. |
| Control | The same steps rebuilt RB-20261023-02's ten release images from its candidate byte for byte (10/10). So the release directory is the laptop's exact images plus the change. |
| T2 fresh boot | `update-app-vm.sh` on the vm-check variant: **16/16** (`vm/fresh-boot-app/`). |
| T3 payload | The metadata signature verifies against the OpenBook certificate. `check-ota-fit.py` against the G14 layout: FITS, snapshot 0.06 of 20.65 GiB free. Read-only `g14-ota.sh --dry-run` on the G14: running slot `_b`, OpenBook certificate yes, second slot yes, would stream into `_a` (`g14-dry-run.log`). |
| T4 B → A | The VM is put in the laptop's state, then updated into slot A. **First:** apply into B 11/11, boot B 7/7, slot B byte-identical (`vm/first-into-b/`). **Then:** release into A, apply 11/11, with bootsync `default openbook-b.conf, preferred openbook-a.conf`. Boot A 7/7: marked good, merged, no AVB error, no system_server fatal signal, zygote exits 0. **Slot A is byte-identical to the release (10/10)** (`vm/release-into-a/`). SELinux policy is compiled at boot (~3.4 s), as expected after a platform-policy change. |
| T5 fallback | `vbmeta_a` corrupted: three slot-A boots fail, then slot B boots by itself with the update rolled back, **7/7**. |
| App after the update | vm-check variant into A: 14/16 (`vm/app-check-into-a/app-after-update.json`). Passed: privileged, own domain `openbook_update_app`, REBOOT granted, battery-exempt, boot work scheduled, update_engine watched, engine check ran, 0 denials, no crash. Not passed, both as expected or understood: **notifications are not pre-granted** (expected for an app that arrives by update: it asks once), and **the app is also installed for user 0, the headless system user** (`stopped=true` there; its only process runs in the owner's user 10). On a fresh install, the user-type allow-list keeps it owner-only. An update that keeps Google's build fingerprint is not treated as a device upgrade, so a new system package is installed for every existing user. |
| T6 unit | Engine 32/32, candidate builder 11 (1 skipped), OTA builder 8, fit 8, slot judge 4, image 3, super 3, payload server 7, rebase 17, layout 12 (`tests/`). The app's JVM tests (19) were not re-run: they run only inside the signing build, and the APK is the pinned, unchanged build of `367090f`. |

## Test-only tooling added (no image change)

- `ab-ota-qemu.py --slot a` and `ab-ota-suite-slot-a.sh` (`d65594b`): rehearse an update into slot A from a disk running slot B.
- `build-apply-harness-variant.py` (`aac149a`): the VM apply harness ran once per data partition, so a second update on the same disk exited at once. That was **attempt 1** (`vm/attempt1/`): the first stage passed, then the driver exited on its marker, and the slot-A runs were stopped. The variant keys the marker to the payload's SHA-256, so it is still a disposable, experimental-marked harness (`vm/harness-variant-manifest.json`).

## Not covered

- The real laptop: its update, reboot, and the owner's first look at the app.
- A real Google update through the app (phase 3 is not built).
- Apps or data beyond the VM's fresh user.
- The VM payloads start from the harness, so the laptop payload P itself is checked by signature, fit and the device's own source-hash verification during the update. It is not applied in a VM.

Storage: 973 GiB free at the start. Peak scratch was removed with `cleanup-manifest.txt` (private), going from 884.79 to 954.30 GiB measured after sync. 21 GiB is kept: C, its release images, the payloads, logs and results.
