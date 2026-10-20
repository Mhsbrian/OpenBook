# G14 camera app and graphics failures

2026-10-20 UTC, ANAL-228. Live wireless ADB reached the configured camera24
G14. Camera24 corrects the first HAL FMQ allocation failure, but the desktop
camera remains black. Raw logs, generated images, user data and TPM state remain
private. No camera frames or audio were saved.

`hardware-diagnosis.json` records two independent failures. Camera2 cannot
receive cameraserver's result-queue FD because the app is denied access to
`cameraserver_tmpfs`. API1 avoids that boundary and reaches UVC STREAMON at
640×480/30, then the provider aborts when graphics-allocator discovery is denied
and its mapper is unavailable. Neither diagnostic receives a frame. Configured
30 fps is not measured delivered performance.

The temporary normal app used only its own CAMERA permission. It was removed
and the owner's camera app reopened. Owner app data, privacy settings and Play
Store state were not reset. The committed probe subsequently adds a defensive
closed-reader callback guard; the observed APK hash above identifies the exact
live diagnostic, and the final APK is rebuilt separately.

## Correction

Camera25 supplies the cameraserver tmpfs-file fallback to ordinary app clients,
excluding isolated processes, with MLS trust restricted to the shared object.
It also uses the standard graphics-allocator client attribute for the external
provider. The app receives queues through the existing permission-checked
camera service. It gains no video-device access, HAL-queue access, generic
tmpfs writes, queue execution or trusted-subject exemption.

`camera-policy-test.c` checks the compiled policy through libsepol's security
server, including MLS constraints. Camera24 reproduces the missing app queue
and allocator permissions; camera25 passes all 49 fixed-policy expectations.
A second negative control removes only the cameraserver object-trust membership
from a temporary CIL copy. All three categorized app contexts then fail queue
write solely due to the MLS constraint, demonstrating why TE-only checks would
miss the failure. Required and forbidden accesses are both checked.

The opt-in disposable VM payload adds a native graphics test under the actual
`hal_camera_default` domain. It allocates/imports a synthetic 640×480 YUV buffer,
writes every Y/Cb/Cr sample and verifies them through the original mapping.
It uses the candidate's production policy with no test-only grants. The normal
USB candidate excludes both native tests, and USB packaging rejects the test
recipe. Neither the VM test nor the policy test establishes physical frames.

`static.json` records the passing native build, both init checks, 52 host checks,
415 unchanged audit inputs and unchanged fstab/credential components.
`policy.json` and its text results record the positive and negative controls.
`focused-runtime.json` records both camera probes exiting 0 under enforcing.
That direct-kernel run later encounters RenderThread execmem denials, two zygote
exit events and a `Checkpoint commit failed` reboot at 279.6 seconds. It does
**not** complete Android boot, and is not counted as a successful boot rehearsal.
`runtime.json` records the separate normal UEFI preserving rehearsal: boot
completion, encrypted VM data mounted and the camera provider registered
through 760.7 seconds, with no recorded fatal signal, provider exit, zygote exit
or watchdog kill. The 600.3-second USB capture completes with 285 new files /
21,091,204 bytes; four prior sessions are excluded. The collector reports zero
kernel overruns, failed saves and unsaved bytes. Kernel audit rate limiting
separately reports 210 dropped events, so this is not a claim of complete audit
coverage. Input, source TPM state and the synthetic internal disk remain
unchanged. The VM has no webcam and does not qualify physical frames.

`preservation.json` records the prepared disposable VM update. Only
EFI/super/vbmeta_a change; all 8,805,941,248 protected bytes and unrelated ESP
files match the prior used VM image. This verifies preparation, not the owner's
credential unlock. The fresh candidate's hash is
`df793f2eed3a5c901659014c2ae368d8e5eeb3d504b514d46fc8c0c1959a7af4`.
Its blank userdata is never an update source for the configured physical stick.

`physical-write.json` records camera25 deployment to the configured SanDisk.
A fresh backup of its latest camera24 state matches an independent second
direct read. The updater also matches the current stick to that backup before
writing only super/vbmeta_a/EFI. Full 12,766,412,800-byte direct readback matches
`c613fd06e2eb213855d17902bd6685c740f7990b15dc2613d9d76c6e56fc6b7e`.
All 8,805,941,248 protected bytes, including userdata and encryption metadata,
and unrelated EFI files are unchanged. The backup is retained privately and
power-off succeeds. Camera25 G14 boot, credential unlock and actual webcam
frames are still untested.

Build instructions, primary-source references and hardware acceptance:
`docs/g14-camera.md`. Each future update after laptop use requires a fresh
verified backup. An earlier owner snapshot must not replace newer saved data.
