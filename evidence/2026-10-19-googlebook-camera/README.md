# G14 USB webcam integration

2026-10-19, ANAL-228. The camera23 candidate adds the missing Android camera
provider to the PC vendor used by both AOSP OpenBook and the local Ruby hybrid.
Images, raw bugreports, user data, TPM state and camera frames are not published.

## Diagnosis and implementation

Prior G14 inventory identifies the Shinetech `3277:0060` USB UVC webcam; earlier
kernel captures bind its UVC interfaces. The GKI has built-in UVC support.
However, the PC product supplied no Android camera provider, manifest instance,
camera feature declaration or video-node access rule. The private net18 G14
bugreport reports zero cameras. Services21 did not change that camera payload.

The fix packages AOSP's AIDL V1 external provider, its native dependencies,
`external/0` manifest instance, external-camera features and stream config.
Video nodes are restricted to root:camera 0660, and the exact Binder service
uses the existing `hal_camera_service` label. No permissive policy, new allow
rule or privacy bypass is added. The collectors record camera status, not frames.

The first candidate, camera22, failed at runtime: the missing service label
made registration resolve to `default_android_service` and the provider aborted.
That observation was stopped at 107.8 seconds; no physical media was written.
Camera23 adds the exact label used by AOSP Cuttlefish. A regression guard rejects
missing/default service labels before packaging.

## Static checks and preservation

`static.json` records 50 passing host checks (24 compatibility, nine live/reporting,
seven ADB collection and ten preservation), successful native init verification,
412 unchanged audited inputs, and passing VINTF/strict SELinux/service-context
checks for both stock baselines and the adapted hybrid. The unadapted hybrid's
policy failure remains expected. Camera file hashes describe PRODUCT_OUT inputs;
the hybrid subsequently appends its reviewed desktop service labels.

`preservation.json` records preparation of a disposable VM image, preserving all
8,805,941,248 bytes outside EFI/super/vbmeta_a and unrelated ESP files. The owner’s
configured data was never booted in QEMU. The fstab and seven credential/encryption
payload files match services21; retained framework and boot inputs remain unchanged.

## Existing-state VM rehearsal

`runtime.json` records a completed 760.6-second UEFI USB observation with the
previous disposable VM's copied TPM state. Preserved encrypted data mounts and
Android reports boot completion. The provider starts once, remains registered,
appears in the process list and is listed by cameraserver, with no provider exit,
registration-label denial, fatal signal, zygote exit or watchdog kill recorded.
No camera is attached to this VM, so the reported device count is correctly zero.

Ruby denies the shell access to the provider's init property; the corresponding
`camera_provider_running_reported` field is false because the property is blank.
Independent registration, process and cameraserver evidence establish startup.
No diagnostic permission was added to expose that property.

The new saved capture completes at 600.3 seconds with zero kernel overruns,
failed saves or unsaved bytes: 285 files / 21,147,522 bytes. Two prior sessions
are excluded. The source image, source TPM state and synthetic internal decoy
are unchanged. This bounded VM observation does not resolve the separate physical
watchdog or qualify the G14 webcam.

## Hardware gate

The configured SanDisk is absent from this workstation, and the G14 has no usable
wireless ADB endpoint. Camera23 has **not** been applied to the physical USB.
A new backup must precede the preserving update because the owner has used the
stick since its last backup. Never replace its configured data with the fresh
candidate's blank data partitions.

The selected provider accepts MJPEG color, advertises EXTERNAL lens facing, and
does not establish front-camera-only app compatibility. Actual G14 enumeration,
live frames, modes, orientation, mirroring, LED, camera permission/privacy behavior,
browser preview and resume remain unverified. A VM without a webcam can qualify
service registration and boot, not physical capture. Trackpad and physical
watchdog issues remain separate. Reproduction and acceptance: `docs/g14-camera.md`.
