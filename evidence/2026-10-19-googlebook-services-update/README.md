# Desktop services and preserving USB updates

2026-10-19, ANAL-228. Local services21 research candidate, retaining Ruby
16452207 system/system_ext/product and the existing OpenBook G14 kernel/modules.
No recovery images, user data, raw bugreports or TPM state are published here.

## Changes and checks

- Restored seven original desktop service labels and their reviewed policy
  contracts. Exact source-contract checks, strict neverallow compilation and
  service-context validation pass; no default-service permission is added.
- Stopped timberslide during early-init on this PC integration, which has no
  Chrome EC console. The first services20 trial exposed Android's rejection
  of a cross-Treble service override and was stopped at 127.6 seconds. No
  services20 image was written to the physical stick. Services21 uses the
  verified init stop operation and has no override error or timberslide start.
- Included the earlier matching GKI zram loader, Wi-Fi compatibility settings
  and audio buffer policy fixes.
- Implemented a private preserving clone builder and guarded USB applier.
  GPT, misc, metadata, userdata and unchanged boot images are protected.
  All 8,805,941,248 bytes outside EFI/super/vbmeta_a and unrelated ESP files
  match the original snapshots. Both inputs are unchanged. Only vendor changes
  among logical images; all eight reviewed encryption-related files match.
- Added active/system-user touchpad preferences, mapper and capability capture.
  Nine synthetic AOSP gesture controls pass, including tap-disabled scrolling
  with staggered contact/release. No physical trackpad fix is claimed.

`static-and-preservation.json`: 399 unchanged audited inputs, 51 passing host
checks, init verification, file-compatibility and preservation results.

## Existing-state VM rehearsal

`runtime.json`: the updater operated on a previously booted disposable net18
USB image. The new VM used a copy of that VM's software TPM state. Its original
USB image and TPM state remain unchanged, as does the synthetic internal disk.
The prior log session is excluded from this run's results.

The 1,100.6-second UEFI/USB observation mounts the preserved encrypted data,
reports boot completion, registers all seven restored services and activates
12,146,652 KiB of swap. mmd setup exits successfully. There is no recorded fatal
signal, zygote exit, watchdog kill or timberslide start. The new saved capture
finishes at 600.2 seconds with zero overruns, failed saves or unsaved bytes:
286 files / 21,068,764 bytes. Serial observation continues beyond that window.

After idle, a wake key activates a blank display; additional keyboard/pointer
input renders welcome and the accessibility prompt, and Escape dismisses it.
`vm-input-check.json` and `vm-responsive.png` document that interaction.
This is emulated input, not the G14's ELAN touchpad. A briefly started redundant
baseline control was stopped once the updated UI responded; it is not counted
as a completed comparison.

One clean VM observation does not resolve the earlier physical property-service
watchdog or establish general runtime stability. The previously provisioned
**owner's** encrypted data was never booted in this VM. Credential unlock and
existing apps/settings on the G14 require a physical retest.

## Remaining hardware and integration gates

`physical-write.json` records the completed SanDisk handoff: baseline matched
the private backup, only super/vbmeta_a/EFI were written, and all 12,766,412,800
bytes passed direct readback with SHA-256
`d52f877b4e1199f96ef1908501361234e85e9c2631e3dbdc86034890d3f46861`.
Protected data is unchanged, the backup is retained and power-off succeeded.
No internal disk or firmware was written. Physical post-update boot is pending.

- Boot the updated USB on the G14 and verify the existing user setup unlocks.
- Retest Wi-Fi, actual audible media output and longer runtime stability.
- Capture tapping off in both the active user's preference and mapper, then
  record labeled failing touchpad motion. The previous Ruby dump has tapping
  on, plus 253 backwards-time queue warnings and 270 spurious callbacks; these
  do not establish the reported click's cause. The AOSP replay library differs
  from the retained Ruby binary.
- Integrate or explicitly handle the absent vendor serviceability backend;
  framework registration alone does not fix Tips/RepairMode.
- Keep Googlebook internal-disk installation disabled until its separate
  installation/recovery and hardware qualification gates pass.

Reproduction, exact device confirmation and recovery limits are documented in
`docs/googlebook-live.md`. The single-slot update is not power-loss atomic;
the verified private pre-update backup is the recovery source.
