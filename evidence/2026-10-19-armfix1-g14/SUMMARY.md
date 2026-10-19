# G14 ARM renderer fix rollout — 2026-10-19 (ANAL-224)

**Proceed: the authorized OTA is installed and verified on the physical G14.**
The ASUS ROG Zephyrus G14 GA403WR now runs `20261019.armfix1` in slot B,
SELinux enforcing. It booted, marked slot B good, and completed the snapshot
merge (`UPDATE_STATUS_IDLE`, `Update state: none`).

## Exact image and rollout

- Previous image: `20261019.photos1`, slot A, tree `d3e04fd`.
- Installed integration tree: `f72c1753ced270a3a7ad41a07e70ecd1d516030f`;
  the previous laptop image plus [PR #118](https://github.com/Mhsbrian/OpenBook/pull/118)'s
  native-service ABI guards and validated Chromium managed-service aliases.
  This is not a rebuild of the later consolidated `main` branch.
- Package: `openbook-ota-20261019-armfix1.zip`, 994,547,625 bytes;
  SHA-256 `fb95dcc49c2af455d2f847bba4814e823f5cf35a6e41953dcb60542ec52ab944`.
- Independently verified package/bootsync hashes against the attached manifest,
  the non-broken package flag, and the existing candidate reports: compatibility
  **32/32**, matching `photos1` slot-A OTA rehearsal **36/36**. Those are
  Porter-produced QEMU results, not additional physical-device tests in this run.
- `scripts/g14-adb.sh state`, `capture`, and `ota --dry-run` captured the baseline
  and passed preconditions. `ota --yes` wrote slot B in 85 seconds; image digest,
  ESP files and next-boot entry verified before reboot.
- Reboot requested at **17:53:22 UTC**, after 601.9 seconds without user input,
  launcher focused, no media sessions, and AC power present. Android marked
  `openbook-b.conf` good at 17:53:52. Host boot wait completed successfully.
- `ota-status`, another `state`/`capture`, and SHA-256 checks confirmed the result.
  Both installed framework JARs exactly match the candidate's target-files ZIP
  (`binaries.json`). Kernel, graphics, bridge and bootsync changes were outside
  this candidate; its existing build comparison records their unchanged hashes.

## Physical-device checks

**16/16 state checks pass.** One user and all 167 package versions are unchanged.
Secure and system settings match exactly; global settings differ only in
`boot_count` and `global_color_palette_version`. Saved-network/account counts
and screen-lock-enabled state are unchanged. The user was unlocked after boot.
All **318 user shared-storage files** retain the identical names/sizes/mtime
listing hash, excluding MediaProvider's rotating `.transforms` files. This is a
metadata comparison, not a content hash of every app's private data.

The owner was actively using Chromium after boot, so verification stayed passive.
The existing **ARM64 Chromium 158.0.8111.0** had **18 managed isolated renderer
processes** in the snapshot; logs recorded **58 managed fallback resolutions**.
The post-boot capture has **zero ELF mismatches, zygote connection retries,
exhausted zygote waits, native/Java crash signatures or ANRs**. Native-zygote and
SurfaceFlinger PIDs remained unchanged through the final 17:56:10 observation.
All 22 historical tombstone/artifact files are byte-identical before and after.

There are no OpenBook-domain denials in the post-boot capture. Six other AVC
tuples appear relative to the pre-update capture; see `selinux-observations.json`.
The captures cover different activity/boot phases; no associated failure was
established here. No policy was changed to suppress them.

## Limits and rollback

The controlled three-page JavaScript/canvas test and Settings launch timings
remain **QEMU evidence** from PR #118. They were not repeated while the owner was
using the laptop. This short physical observation does not establish general ARM
application compatibility or resolve the two known bridge instruction/signal
probe failures, ARMv7, or arbitrary native-only ARM services.

The successful slot has merged; slot A is no longer a rollback option. A code
rollback now requires packaging the earlier tree with a new build number and
applying another OTA. Do not select the stale slot-A images manually.

Raw device state, account/app inventories, screen captures and full logs remain
private on the build host. This directory contains only curated evidence; device
identifiers and host paths in operational logs are replaced with placeholders.
