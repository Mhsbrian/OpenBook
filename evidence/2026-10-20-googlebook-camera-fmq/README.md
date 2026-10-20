# G14 camera session failure and scoped FMQ correction

2026-10-20 UTC, ANAL-228. Wireless ADB reached the owner's camera23 G14 while
the desktop camera app had been failing to open. Raw device logs, images,
configured data and TPM state remain private. No camera frames were collected.

## Physical diagnosis

`hardware-diagnosis.json` records successful boot, encrypted data mounted,
one enumerated public external camera and restricted video nodes. The log chain
shows an enforcing SELinux denial writing `memfd:MessageQueue`, followed by
`ftruncate(MessageQueue, 266240)` failure, `invalid request fmq` and camera session
initialization failure. In the pinned AOSP source, this occurs before the
output thread starts. It explains the failed open, without proving subsequent
capture stages work or implicating the preserved data.

The latest input capture has tapping enabled in both the current user's setting
and the effective mapper. It does not reproduce the earlier tap-disabled
Settings symptom. No setting was changed. A later ADB read failed after the
SanDisk appeared on the development host; the diagnosis uses the completed
earlier capture, not the failed follow-up.

## Change and static validation

Camera24 creates `hal_camera_default_tmpfs`, uses AOSP's `tmpfs_domain` macro,
and permits cameraserver read/write/map/getattr on this dedicated queue type.
It follows the existing OpenBook audio adaptation for ordinary tmpfs-backed
memfds on android17-6.18. It does not change the framework, kernel, privacy
controls, user settings or credential payloads.

`static.json` records the native vendor build, init verification, 51 host checks,
413 unchanged audit inputs and passing native VINTF/SELinux/service-context
checks for both baselines and the adapted hybrid. The unadapted hybrid's policy
failure is expected. Eight security/credential payload files are unchanged.

`policy.json` tests the **compiled binary policy** with `sepolicy-analyze`:
each required HAL/client permission is present, and neverallow assertions
confirm no generic tmpfs write, app-domain queue read/write/map or HAL queue
execute grant. No permissive domain is present. Positive permission queries
deliberately assert the opposite and require the tool's explicit violation;
negative assertions must pass. This is a policy check, not a streaming test.

## Focused runtime regression

`fmq-runtime.json` records the opt-in `--camera-fmq-test` disposable VM run.
The probe checks its actual `hal_camera_default` context, creates and resizes
a 266,240-byte memfd, verifies its dedicated SELinux label, and validates all
bytes through writable and read-only shared mappings. Init reports exit 0;
existing diagnostics independently report enforcing. The test and normal USB
candidate have identical compiled policies, with no test-only permissions.

An initial probe exited 11 because the HAL cannot read selinuxfs's `enforce`
file. That check was moved to existing shell diagnostics, without expanding
policy. The corrected probe exits 0. Its 180.4-second direct-kernel observation
does not report full Android boot completion, and is used only for the focused
operation check. The separate preserving UEFI rehearsal tests normal boot.

The test binary and init service are excluded from the USB candidate.
`live-image.py` explicitly rejects a test-payload recipe before creating output;
the refusal was exercised. These checks still do not exercise a real video
device, cross-process Camera2 streaming, frame delivery, orientation or privacy.

## Data preservation

`preservation.json` describes a disposable camera23-to-camera24 VM update.
The old VM image and software TPM state are copied; the owner's data is never
booted in QEMU. Only EFI/super/vbmeta_a change. All 8,805,941,248 protected bytes,
including the old VM userdata and metadata, and unrelated ESP files match.
The fresh candidate has SHA-256
`b3cadf83dc66d0b8b2c98f6cba4c93e312b172491fa20c7612384220bcddcdd5`.
The configured stick must use a freshly backed-up preserving clone, never this
fresh candidate's blank userdata.

`runtime.json` records the normal candidate's 760.6-second preserving UEFI
rehearsal: encrypted VM data mounts, boot completes, and the provider remains
registered without an exit, fatal signal, zygote exit or watchdog kill in the
observed logs. The ten-minute capture completes at 600.3 seconds with zero
overruns, failed saves or unsaved bytes (285 new files / 21,256,915 bytes).
Three earlier sessions are excluded. Input, source TPM state and synthetic
internal disk remain unchanged. Ruby's shell cannot read the provider's init
property; registration and process evidence establish startup. Zero enumerated
devices is expected in this camera-less VM and does not qualify G14 frames.

Build and hardware acceptance instructions: `docs/g14-camera.md`. Primary
source checked locally: hardware/interfaces
`d41643629491b67274c1c5092518adfab51a2ff9`,
`camera/device/default/ExternalCameraDeviceSession.cpp`; system/sepolicy
`e066568e98d86db31a9346d30977f3632fa7073c`, `public/te_macros`.
