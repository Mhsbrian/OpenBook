# Googlebook G14 Wi-Fi and audio follow-up

2026-10-19, ANAL-228. The owner reports that both normal and save-logs entries
of fw10 reach setup. Networks are visible, but a supplied password leaves the
network saved rather than connected. No startup audio was heard. A startup
sound is not an audio acceptance test. The retained `bootanimation.zip` has
247 entries and no audio track; sounds triggered elsewhere are not ruled out.

The returned ESP contains 64 files / 8,967,953 bytes, copied and individually
SHA-256 verified into a private backup. A read-only FAT check passes. The used
12,766,412,800-byte image extent is also backed up privately. Raw logs and
userdata are not published; they can contain network and device identifiers.

The kernel capture ends at 65.936853 seconds and the Android stream ends at
21:26:38.519 UTC, with four diagnostic checkpoints and no `complete.txt`.
The reason for the capture ending is unknown. It contains initial Wi-Fi
service setup, but no authentication attempt or DHCP result. Do not attribute
the reported connection failure to a specific password or access point.

## Confirmed findings

- Radeon SMU, Display Core and DMUB initialize. The previous firmware-path
  failure is resolved in this interval, consistent with the owner's display report.
- MT7925 firmware loads, and both CS35L56 amplifiers load their firmware/tuning.
- Android selects the mainline supplicant. The vendor Wi-Fi HAL is absent.
  The retained Ruby product overlay enables station MAC randomization and
  dropping a connection when MAC configuration fails. Those assumptions do
  not match OpenBook's hardware integration. This is a compatibility defect;
  the truncated capture does not prove it caused this particular join failure.
- Codec2 (`mediaswcodec`) is denied read/write access to SoundPool's shared
  queues and write access to its own queues. Android then fails to load
  `/product/media/audio/ui/KeypressStandard.ogg`. The retained Ruby policy
  grants `memfd_file` access but does not enable `memfd_class`; this kernel
  labels those objects as tmpfs files instead. OpenBook's corresponding
  system_ext fixes were lost when that partition was replaced with Ruby.
- The audio setup helper exits successfully, but its stdout cannot reach the
  incorrectly labelled `/dev/kmsg_debug`. Its selected card/mixer state is
  therefore not established by this capture.

## Changes and validation

- Resource-only, local test-signed vendor RRO for the two unsupported MAC
  settings. A bounded shell service enables it for the Wi-Fi system user (0),
  sets highest priority and verifies the effective values. The default vendor
  RRO targets AOSP's package, whereas Ruby uses
  `com.google.android.wifi.resources`; the new builder verifies the actual APK
  package name as well as its resource mappings. A vendor RRO also cannot
  override Ruby's product RRO by manifest priority alone. Mainline
  supplicant selection, networks and credentials are unchanged.
- Restore the existing OpenBook Codec2/SoundPool/MediaPlayer tmpfs contract
  inside the private hybrid policy. A dedicated decoder queue type excludes
  isolated clients; no generic tmpfs write grant or permissive domain is added.
- ALSA inventory is captured independently of the audio setup helper's lost
  stdout. A vendor-init restorecon attempt was denied in VM testing and removed;
  no generic tmpfs access or relabelling permission was added to make it pass.
- Capture Wi-Fi state, effective overlay values, connectivity, ALSA inventory,
  AudioFlinger and audio policy throughout the ten-minute window. Full display
  dumps are less frequent to leave room for the connection attempt.
- Forward Binder service dumps through an ordinary shell pipe. Passing the
  logger's private named FIFO directly denied system_server's output. Only
  the shell forwards bytes into that FIFO; no service gets new FIFO access.
  Add only directory traversal to the existing shell read permissions for
  `proc_asound`. Restricted vendor properties are omitted. HAL-private dump
  calls remain restricted by Ruby's user policy.

Native audit: both stock baselines and adapted hybrid pass VINTF and strict
SELinux; 395 audited inputs unchanged. The unadapted hybrid still fails its
known six forbidden debug grants, as expected. The new RRO maps exactly two
resources and passes `idmap2 create --policy vendor` against the retained Wi-Fi
APK. Compiled policy has no permissive domains. All 23 host guards pass.

The intermediate net16 run completed 600.3 seconds of capture: 291 files /
28,889,224 bytes, zero overruns, failed saves or unsaved bytes. Both Wi-Fi
resource values read back false, and the activation service succeeded. Twenty
Vorbis components were created, sound-effect loading completed before and after
the framework restart, and there were no decoder AVCs, bad-input queue errors
or UI-sample load errors. The existing system-server SIGSEGV and zram abort
remain. See `validation-net16.json`. This is not an audible speaker test.

The final net18 image (`74c5270b2c37b658…`) completes a 660.6-second UEFI/TCG
observation with emulated HDA and a disposable software TPM. Its logger saves
271 files / 24,529,288 bytes, completing at 600.2 seconds with zero overruns,
failed saves or unsaved bytes. Both overlay values are false; the Wi-Fi
service's own cached randomization value is false in 18 snapshots. Ten Vorbis
components are created, and Sound Effects Loading completes. No decoder AVC,
bad-input queue error, UI-sample loading error, named-pipe denial or ALSA
inventory denial occurs. Card and PCM inventory are readable. The source image
and synthetic internal disk remain unchanged. See `validation-final.json`,
`complete-final.txt` and the selected `runtime-final-excerpts.txt`.

The final run reaches welcome and reports boot completion. It has one zygote
exit and the known zram setup abort, but no captured system-server fatal signal
or execmem denial in this observation. The prior intermittent SIGSEGV remains
unresolved; one clean interval does not establish desktop stability. No virtual
Wi-Fi radio or physical speaker was exercised. Hardware authentication, DHCP
and audible playback still require the next G14 test.

The same authorized 62 GB SanDisk now holds net18. The guarded writer wrote
12,766,412,800 bytes in 662 seconds, read the entire image back in 96 seconds
with matching SHA-256, and powered the stick off. Both copies of the previous
64-file capture match by hash; the prior used image extent is also preserved
privately. See `physical-write.json`. Boot **Googlebook - save detailed logs to
USB (10 minutes)**, attempt Wi-Fi, play a sound if setup permits, keep the
laptop awake for 12 minutes, then shut down normally and return the stick.

Primary references checked 2026-10-19:
[Android RRO policy, precedence and runtime activation](https://source.android.com/docs/core/runtime/rros),
[Android SELinux implementation](https://source.android.com/docs/security/features/selinux/implement).
Local primary inputs: retained `WifiDesktopOverlayGoogle.apk` resource table,
`plat_sepolicy.cil`, and AOSP `OverlayManagerServiceImpl.setHighestPriority`.
Existing OpenBook media rules: `device/anybook/common/pc/sepolicy/system_ext/`.
