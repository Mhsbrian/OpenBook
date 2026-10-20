# G14 UVC camera integration

Owner acceptance, 2026-10-20: after camera25 was written and verified, the owner
reports that the camera is fixed and Bluetooth works. This confirms practical
preview use according to the owner; measured frame delivery, orientation,
privacy and suspend remain separate tests. See
`evidence/2026-10-20-googlebook-migration/owner-confirmation.json`.

The GA403WR inventory identifies `3277:0060`, a Shinetech USB2.0 FHD UVC webcam.
The earlier G14 boot captures show `uvcvideo` binding both its UVC 1.10 and
1.50 interfaces. The OpenBook GKI already has `CONFIG_USB_VIDEO_CLASS=y` and
`CONFIG_MEDIA_USB_SUPPORT=y`. This device does not require the AMD ISP or the
Intel IPU7 camera stack from the original Ruby vendor image.

The previous PC product did not package an Android camera provider, a camera
VINTF instance or camera feature declaration. The Ruby hybrid uses that PC
vendor tree in place of Google's vendor tree, so it also had no provider. The
private net18 G14 bugreport independently reports **zero camera devices**. That
capture predates services21, whose camera payload was unchanged. These facts
identify a missing integration layer; they do not measure current capture quality.

## Camera24 physical follow-up (2026-10-20 UTC)

The owner reports that the updated disk boots correctly, but preview remains
black. Wireless ADB confirms boot completion, encrypted `/data` mounted and one
public camera. The camera24 HAL queue correction works: its initial session now
opens. Two further failures were reproduced independently:

1. Camera2 calls `ICameraDeviceUser.getCaptureResultMetadataQueue`. Binder cannot
   transfer the cameraserver-created queue FD to the categorized app context:
   `untrusted_app:s0:c147,c256,c522,c768` is denied read/write on
   `cameraserver_tmpfs:s0`. The device remains UNCONFIGURED, with no streams or
   capture requests. The resulting `DeadObjectException` does not itself prove
   that cameraserver died; the matching FD-transfer denial explains this path.
2. A temporary normal app using Camera API1 bypasses that app-facing FMQ and
   reaches UVC STREAMON at 640×480/30. The external provider then receives a
   service-manager denial finding `hal_graphics_allocator_service`, falls through
   mapper initialization, and aborts with `gralloc-mapper is missing`. Its native
   stack is in `GraphicBufferMapper` / camera `HandleImporter`. Zero frames reach
   the app. The provider restarts automatically.

The same diagnostic using Camera2 reproduces the metadata-queue failure. Each
foreground run lasts 20 seconds and logs counts/timing/luma range only. It saves
no frames or audio and has no network/storage permission. It was uninstalled
and the owner's camera app reopened after testing. No data reset, security-mode
change, privacy override or Play Store change was made.

Camera25 adds two narrowly scoped corrections in `sepolicy/vendor/hal_camera.te`:

- Permit ordinary app clients to read/write/map/getattr the **cameraserver**
  queue, excluding `isolated_app_all`. Add MLS trust to that shared **object**
  type because the app categories differ from the service's s0. This is the
  tmpfs-file equivalent of AOSP's cameraserver memfd grant, following the existing
  audio/Codec2 kernel compatibility pattern. Apps still cannot access the HAL's
  queue or video nodes; no generic tmpfs write, queue execution, app trusted-subject
  attribute or permissive domain is added.
- Apply `hal_client_domain(hal_camera_default, hal_graphics_allocator)`. AOSP's
  standard client attribute supplies allocator discovery, Binder IPC and mapper
  loading. A one-off `find` grant would leave the remaining operations untested.

`camera-policy-test.c` uses libsepol's security server to evaluate compiled
policies with full MLS contexts. It checks three app contexts, FD use, queue
permissions, isolated-process exclusion, HAL queue isolation, video-node
isolation and allocator discovery/IPC. Camera24 is the negative control; a
candidate must pass the fixed expectations. This complements native neverallow
compilation; it is not a physical streaming test.

Build the host checker against the pinned AOSP libsepol (already built by the
native policy tools), then run both controls:

```bash
clang -O2 -Wall -Wextra -Werror \
  -I "$AOSP_SRC/external/selinux/libsepol/include" \
  scripts/googlebook/camera-policy-test.c \
  "$AOSP_SRC/out/soong/.intermediates/external/selinux/libsepol/libsepol/linux_glibc_x86_64_static/libsepol.a" \
  -o "$PRIVATE_OUT/camera-policy-test"
"$PRIVATE_OUT/camera-policy-test" "$OLD_AUDIT/hybrid-reduced/policy.bin" broken
"$PRIVATE_OUT/camera-policy-test" "$NEW_AUDIT/hybrid-reduced/policy.bin" fixed
```

A separate negative control removes only `cameraserver_tmpfs_202604` from the
vendor CIL's `mlstrustedobject` membership in a temporary copy, recompiles with
the audit's exact `secilc` invocation and runs the fixed expectations. It must
fail only the three categorized-app writes with reason `0x2` (constraint).
Never change the shipping policy or use `secilc -N` for this test.

The optional VM payload now also runs `openbook-camera-buffer-test` in the
production HAL domain. It allocates a synthetic 640×480 YUV buffer, clones/imports
its handle, writes all Y/Cb/Cr samples and verifies them through the original
mapping. Init must report exit 0 with no abort. It does not open a webcam.
Build the native test explicitly before preparing a test image:

```bash
AOSP_JOBS=8 BUILD_NUMBER=20261020.camera4 scripts/aosp-docker.sh \
  /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug \
  openbook-camera-buffer-test vendorimage
```

The native test installs under PRODUCT_OUT's `data/nativetest64/vendor`, never
the production vendor tree. `--camera-fmq-test` copies it into the disposable VM
only, records its source/binary hashes and labels it with the real HAL domain.
Normal USB packaging rejects that test recipe.

Camera25 passes the native build, 52 host checks and the 415-input native audit.
All 49 compiled-policy expectations pass; removing only the object-trust
membership reproduces three MLS write denials. Both focused camera probes
exit 0 under enforcing. Their direct-kernel VM later hits RenderThread execmem
denials, zygote exits and a checkpoint-failure reboot at 279.6 seconds, without
boot completion. These are focused operation results, not a successful full
boot. The separate normal UEFI preserving candidate completes a 760.7-second
rehearsal: boot completes, encrypted test data mounts and the provider registers,
without a recorded fatal signal, provider/zygote exit or watchdog kill. Its
600.3-second capture completes with 285 new files and no unsaved collector bytes;
kernel audit rate limiting separately drops 210 events. The source image,
source TPM state and synthetic internal disk remain unchanged. Actual camera
frames remain a G14 gate.

Camera25 is now on the configured physical SanDisk. A fresh backup of its latest
camera24 state matches an independent direct read. The guarded updater verifies
the stick against that backup before writing only super/vbmeta_a/EFI, then checks
the entire 12,766,412,800-byte used extent by direct readback. Its result matches
`c613fd06e2eb213855d17902bd6685c740f7990b15dc2613d9d76c6e56fc6b7e`.
All 8,805,941,248 protected bytes and unrelated EFI files are unchanged. The
backup is retained privately and power-off succeeded. G14 boot and credential
unlock have not yet been retested with camera25.

For a physical follow-up, build the temporary APK with
`bash scripts/googlebook/camera-probe/build.sh`. Install it for the current
foreground user and grant **only its own** CAMERA permission. Close any other
camera client, launch `org.openbook.test.camera/.CameraProbeActivity --es api 1`
or `--es api 2`, allow the 20-second run to finish and collect the
`OpenBookCameraProbe` log tag. If the app pauses, it closes the camera early;
check the elapsed span before interpreting the result. Uninstall it afterwards
and reopen the owner's camera app. Any nonzero frame count is still insufficient
to qualify orientation, color, privacy, suspend or browser use.

Evidence: `evidence/2026-10-20-googlebook-camera-clients/`, including
`physical-write.json`. After any further laptop use, the next USB update must
begin with a new backup of that latest state. Never deploy the blank data
partitions from the fresh candidate or an earlier owner snapshot.

Sources checked 2026-10-20: pinned AOSP
`frameworks/av/services/camera/libcameraservice/api2/CameraDeviceClient.cpp`
(`CreateMetadataQueue`, `getCaptureResultMetadataQueue`),
`frameworks/native/libs/ui/Gralloc5.cpp` (`waitForAllocator`),
`system/sepolicy/private/{app.te,mls,hal_graphics_allocator.te}` and
`system/sepolicy/vendor/hal_camera_default.te`. The current public
[allocator policy](https://android.googlesource.com/platform/system/sepolicy/+/refs/heads/main/private/hal_graphics_allocator.te)
independently confirms the standard client discovery/Binder/mapper pattern;
the local pinned policy, rather than moving upstream main, is the build input.

## Camera23 physical follow-up (2026-10-20 UTC)

Wireless ADB now connects to the booted G14. Camera23 enumerates one public
camera (`external/100`), and `/dev/video0..3` are root:camera 0660 with
`video_device` labels. The desktop camera app repeatedly fails to open its
session. The captured failure is specific:

```text
avc: denied { write } name="memfd:MessageQueue"
  scontext=u:r:hal_camera_default:s0 tcontext=u:object_r:tmpfs:s0 tclass=file permissive=0
ftruncate(MessageQueue, 266240) failed for memfd creation: Permission denied
initialize: invalid request fmq
open: camera device session init failed
```

The pinned AOSP external-provider source allocates request and result metadata
FMQs before starting its output thread. This denial explains a failed open
despite successful enumeration; it does not establish whether later capture
stages also need work. No frame is captured or published. No evidence implicates
the preserved user data, and no data reset or privacy override is appropriate.

Camera24 adds `hal_camera_default_tmpfs` and `tmpfs_domain(hal_camera_default)`
in `sepolicy/vendor/hal_camera.te`, plus read/write/map/getattr for cameraserver
on that dedicated type. This follows the existing PC audio-HAL adaptation for
the android17-6.18 kernel, where memfds are ordinary tmpfs files. There is no
generic tmpfs write grant, app-domain queue access, executable queue mapping or
permissive domain. The native audit hashes the source and compiled vendor policy.

The opt-in `hybrid-probe.py --camera-fmq-test --prepare-only` builds a disposable
VM payload in the actual camera HAL domain, without test-specific allow rules.
It allocates a 266,240-byte memfd, checks its label, maps it and verifies all
bytes through two shared mappings. Init must report exit status 0, and the
existing diagnostics must separately report enforcing. The HAL cannot read
selinuxfs directly; an initial test returned 11 at that check, so enforcement is
verified externally. `live-image.py` refuses this test payload. Build the ordinary
USB candidate **without** this flag. A successful FMQ test does not prove
cross-process Camera2 streaming or physical webcam frames.

Camera24 passes that focused test and the 760.6-second preserving UEFI rehearsal.
Existing encrypted VM data mounts, boot completes and the provider registers,
with no provider exit, fatal signal, zygote exit or watchdog kill recorded.
The ten-minute capture finishes with zero lost bytes. All 51 host checks pass;
both baseline and adapted-hybrid native audits pass across 413 unchanged inputs.

## Implementation

`device/anybook/common/pc/camera/camera.mk` includes the open-source AOSP AIDL
`android.hardware.camera.provider-V1-external-service`. The device manifest adds
`ICameraProvider/external/0`; the build normalizes version 1 by omitting its
default value. Both the AOSP PC and the Ruby hybrid use this vendor integration.

The service runs as cameraserver with group camera in AOSP's
`hal_camera_default` SELinux domain. The exact `external/0` Binder instance is
labeled `hal_camera_service`, as in AOSP Cuttlefish. Omitting this label caused
the first VM candidate (camera22) to abort at registration against
`default_android_service`; it was stopped and never deployed. Camera23 supplies
the label without adding a new allow rule. Ueventd assigns `/dev/video*` mode 0660,
owner root, group camera. Ordinary apps continue through Camera2/cameraserver
permissions and privacy controls. No permissive domain, general app device
access, root service or camera privacy override is added.

`external_camera_config.xml` leaves the ignored-node list empty: `video0` can
be the built-in webcam, and node numbering can change at boot. AOSP checks
V4L2 capture capability and supported formats before exposing a node. The
selected implementation accepts MJPEG color and optional Z16 depth; this config
disables depth. Metadata nodes and unsupported formats are not useful cameras.
The G14's actual color formats still require confirmation on the new image.

The configuration permits up to 1920×1080 at 30 fps, intersected with enumerated
device modes. This is an upper bound, not a measured frame-rate claim. Orientation
is 0 degrees for the laptop's landscape camera; physical orientation, mirroring
and color need verification. The generic provider advertises LENS_FACING_EXTERNAL,
even for a USB camera built into a bezel. It does not claim a front-facing phone
camera, autofocus, flash, face authentication or IR support. Applications that
insist on a front/back camera need separate testing and, if necessary, a reviewed
device-specific provider adaptation.

## Build and audit

Build with the shared AOSP lane lock and Ubuntu container:

```bash
AOSP_JOBS=8 BUILD_NUMBER=20261020.camera2 scripts/aosp-docker.sh \
  /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug vendorimage
python3 scripts/googlebook/compat-test.py -v
python3 scripts/googlebook/live-test.py -v
python3 scripts/googlebook/capture-adb-test.py -v
python3 scripts/googlebook/preserve-update-test.py -v
```

Run the native compatibility audit and hybrid packaging commands in
`docs/googlebook-live.md`. The audit requires the built service, implementation
libraries, manifest, config, features and restricted device permissions; old
camera-less PRODUCT_OUT trees are rejected. It hashes the camera inputs and
native camera libraries, validates both baseline trees and the adapted hybrid,
and recompiles SELinux with neverallow checks. Packaging checks the executable's
label. The VM must independently show the service running and registered.

The camera status fields in `run-probe.py` deliberately distinguish provider
startup from enumerated devices. Zero devices is expected in a VM without a
virtual or passed-through webcam and **does not qualify physical capture**.
Neither the ADB collector nor USB logger opens a camera stream or stores images.

Camera23 passes 50 host checks, native init verification and the compatibility
audit with 412 unchanged inputs. Its 760.6-second preserving VM rehearsal boots,
mounts existing encrypted test data and registers the provider without a provider
exit, fatal signal, zygote exit or watchdog kill. The ten-minute saved capture
completes with zero lost bytes. Ruby hides the provider's init property from the
shell; registration, process and cameraserver evidence establish startup instead.
The VM has no camera and reports zero devices. Sources, copied-from TPM state
and synthetic internal disk remain unchanged; physical validation is still open.

## Physical acceptance and preservation

Camera23 has been applied to the configured SanDisk from a fresh verified
backup of its current services21 state. Only super/vbmeta_a/EFI were written;
full 12,766,412,800-byte direct readback matches `bf79eef29bc760e5…`. All
8,805,941,248 protected bytes, including userdata and encryption metadata, and
unrelated ESP files remain unchanged. Power-off succeeded; the backup is retained.
The subsequent G14 boot reaches boot completion and mounts encrypted `/data`.
Camera enumeration succeeds but streaming fails as described above. Credential
unlock and the completeness of all owner apps/settings were not independently
tested.

Camera24 has now been applied from a **new** backup taken after that G14 session.
The backup matched an independent second direct device read. Only
super/vbmeta_a/EFI were written, and full 12,766,412,800-byte direct readback
matches `207aaaa1f2f1f376…`. All 8,805,941,248 protected bytes and unrelated ESP
files match the new backup. Power-off succeeded. The backup is retained privately;
the next G14 boot must verify unlock, existing setup and actual camera frames.

Keep the configured USB's current data: take a new verified backup before every
subsequent preserving update if the stick has been used. Retain metadata,
userdata and identity; never use a fresh candidate's blank data partitions on
this configured stick. Generated Google-based images and owner backups stay private.

For the first updated boot, select **Googlebook - save detailed logs to USB
(10 minutes)**. Confirm that the existing user unlocks and the configured apps
and settings are present before testing video. Leave this boot running for at
least ten minutes so the bounded capture can finish; shut Android down before
moving the stick back to the development host. For live inspection, use the
current IP address and port displayed on the main Wireless debugging screen.

On the G14, verify the service, video-node labels/access, `dumpsys media.camera`,
and camera privacy state. Then use an authorized camera app and a browser video
call preview to check enumeration, live frames, aspect ratio, orientation,
mirroring, color, supported frame rates, camera LED and close/reopen behavior.
Confirm that denying permission or disabling camera access blocks capture.
Check contention and resume separately. Do not save or publish camera frames
unless the owner requests them. Keep the trackpad and watchdog work separate;
this change does not claim to fix those issues.

## Evidence and sources

- Prior hardware evidence: `evidence/2026-10-16-ga403wr-inventory/SUMMARY.md`,
  `lsusb.txt`, and `evidence/2026-10-16-g14-hwcheck/hwcheck-005-dmesg.txt`.
- Current validation: `evidence/2026-10-19-googlebook-camera/`.
- Physical FMQ diagnosis and follow-up: `evidence/2026-10-20-googlebook-camera-fmq/`.
- [AOSP USB camera integration](https://source.android.com/docs/core/camera/external-usb-cameras),
  checked 2026-10-19: UVC kernel support plus an external Android provider,
  manifest/configuration and camera access controls are required. The documented
  reference path serves lightweight webcam use; camera CTS remains a hardware gate.
- Local pinned AOSP source: `hardware/interfaces/camera/provider/default/`
  and `camera/device/default/ExternalCamera{Device,Utils}.cpp`, plus
  `system/sepolicy/{vendor/hal_camera_default,private/hal_camera}.te`.
- Source checked locally on 2026-10-20: hardware/interfaces revision
  `d41643629491b67274c1c5092518adfab51a2ff9`,
  `camera/device/default/ExternalCameraDeviceSession.cpp:189`; system/sepolicy
  revision `e066568e98d86db31a9346d30977f3632fa7073c`, `public/te_macros:75`.
