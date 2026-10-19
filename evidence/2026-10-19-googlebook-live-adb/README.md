# Live Ruby G14 access preflight

2026-10-19, ANAL-228. The owner offered the running laptop for investigation
before internal-disk installer work. The supplied address advertises the Ruby
live serial through mDNS; its TLS connection port accepts TCP. The advertised
legacy port 5555 refuses TCP. Platform Tools 37.0.1 uses LIBADBMDNS with mDNS
enabled. ADB connect fails and no device transport is available.

The new user-build collector exits 2 at `get-state`, records `connected: false`
and `complete: false`, and executes no shell commands. Its private preflight
manifest and stderr remain local. No laptop log review, remote correction,
Wi-Fi association or audio playback result is claimed. The next input is the
temporary pairing port/code from the laptop's pairing dialog.

Six host checks pass: explicit endpoint validation, preserving old captures,
retaining failed output privately, timing out/reaping a hung client, stopping
before shell commands on an unconnected device, and distinguishing partial
capture from success. No image or physical disk was changed in this run.

The capture includes identity, boot/mount state, logcat/kernel logs, Wi-Fi and
connectivity, resource overlays, ALSA/audio services, graphics, power/thermal
state, memory, processes, ANR and system-server crash/watchdog history. Each
command is bounded; its status and output are preserved. Service-level denials
can occur even with exit code zero and require output review. Raw logs
remain private and are not automatically safe to publish.

Pairing workflow follows the primary
[Android ADB documentation](https://developer.android.com/tools/adb#connect-to-a-device-over-wi-fi)
(checked 2026-10-19). Installation remains gated on hardware validation and a
reviewed installer/update/rollback path.
