# G14 UVC camera integration

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
AOSP_JOBS=8 BUILD_NUMBER=20261019.camera1 scripts/aosp-docker.sh \
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
This verifies stored bytes, not the user's next credential unlock or camera frames.

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
- [AOSP USB camera integration](https://source.android.com/docs/core/camera/external-usb-cameras),
  checked 2026-10-19: UVC kernel support plus an external Android provider,
  manifest/configuration and camera access controls are required. The documented
  reference path serves lightweight webcam use; camera CTS remains a hardware gate.
- Local pinned AOSP source: `hardware/interfaces/camera/provider/default/`
  and `camera/device/default/ExternalCamera{Device,Utils}.cpp`, plus
  `system/sepolicy/{vendor/hal_camera_default,private/hal_camera}.te`.
