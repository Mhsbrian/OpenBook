# Paired G14 investigation

2026-10-19, ANAL-228. Wireless ADB pairing succeeded. These observations come
from the physical ASUS GA403WR running the net18 Ruby/OpenBook live USB, not
the earlier OpenBook installation or the emulated test. The retained framework
identifies itself as Ruby build 16452207, a user build with SELinux enforcing.
`ro.boot.openbook.live=1`, slot A, and boot completion are observed. This boot
used the normal entry; the USB kernel logger was not enabled.
The current user's setup-complete and device-provisioned flags are both 1;
the foreground activity is Settings. This establishes progress beyond setup,
without qualifying the launcher or application compatibility.

Two bounded ADB captures and a complete bugreport are retained privately.
The bugreport contains 237 ZIP entries, 63,952,761 uncompressed bytes, including
native tombstones and ANR traces. Raw logs, network identifiers and app/account
context are not published. The pairing secret is not retained in project files.
The second capture completes all 40 records with four expected command failures:
bootconfig, partitions, swaps and dmesg are denied by the user build. Empty kernel
logcat output is not evidence of a clean kernel. The collector now separates
independent reads so a denial cannot suppress disk-space, module or memory data.
Some new mmd/vendor property queries are also denied, including when the enclosing
shell command returns zero. Empty values are not false values. Use the saved
kernel/init records and meminfo for the memory fix; no read grant was added.

## Hardware evidence

- Wi-Fi is associated using WPA2-PSK and 802.11ax at 2437 MHz. The supplicant
  reports COMPLETED; connectivity reports a local address, default route and
  VALIDATED internet capability in both captures. Both MAC compatibility RRO
  values are false. Link rates are not throughput measurements, and this does
  not qualify reconnect, roaming, suspend or other access points.
- SurfaceFlinger uses ANGLE/Vulkan on AMD Radeon 890M, RADV 26.2.5, with the
  2880×1800 panel at 120 Hz. This is a physical accelerated graphics result.
  Cursor-composition warnings and missed-frame counters still need assessment.
- ALSA exposes HDMI and ALC285 Analog playback/capture. Android's primary
  output routes to the speaker at 48 kHz; AudioFlinger reports 454,656 frames
  written and zero suspended frames. Sound-effects loading completes after
  the framework restart, without the previous Codec2 queue/UI sample errors.
  Master mute is false; the speaker media volume is only 1 of 15. This proves a
  functioning software path, not audible output or amplifier calibration.
- Thermal HAL is ready, with status 0 and CPU, GPU and Wi-Fi sensor readings.
  Battery data reports charging at 52%. Battery temperature is reported as 0;
  it is not a validated temperature measurement. Suspend and battery life were
  not tested during this investigation.

## Confirmed failures and next gates

1. **Missing zram device.** Both native tombstones are `mmd_setup` SIGABRT with
   `zram setup failed: failed to write zram disk size: No such file or directory
   (os error 2)`. The module list has no zram/zsmalloc, `/sys/block/zram0` and
   `/dev/block/zram0` are absent, and `/proc/meminfo` reports SwapTotal 0.
   The matching system_dlkm already contains zram and its zsmalloc dependency;
   loading only vendor drivers never requests them. Added a shared PC early-init
   fragment that runs modprobe against `/system/lib/modules` before framework
   memory management. The hybrid packager includes and hashes the same audited
   fragment even when using an older PRODUCT_OUT. Swap sizing/setup stays with
   the framework. No policy permission, kernel binary or retained framework
   image is changed. Hardware verification requires booting the new candidate.
2. **Framework watchdog.** At uptime 1,010,521 ms, system_server's `android.fg`
   handler is reported blocked for 74 seconds. Earlier ANR traces at 18:55:53
   and 18:56:14 show that same thread (1365) in libc `connect`, then
   `PropertyServiceConnection`, `__system_property_set`, `SystemService.stop`,
   and `IdmapDaemon.stopIdmapServiceLocked`. The later watchdog waiting-channel
   dump still shows `unix_wait_for_peer` for thread 1365. The property-service
   connection is the observed blocking site; why it failed to complete is not
   established. IO pressure is high around the event, but
   USB latency is only a hypothesis. Do not claim that zram or NVMe fixes it.
   The watchdog restarts the framework; later DeadSystemExceptions are a
   cascade, not nine independent causes. No additional watchdog entry appears
   in the follow-up capture.
3. **Seven desktop registrations lack their original vendor-private types.**
   Data migration, DRM network, desktop network, setting health, snapshot,
   video chat and serviceability are denied registration under the default
   service type. Original type/attribute contracts have been located for a
   scoped integration review; no blanket default-service grant was added.
   Both RepairMode and Tips fail to bind the absent vendor serviceability
   service; their exceptions identify that same missing dependency.
4. **Unsupported platform services.** Timberslide repeatedly tries to open a
   Chrome EC device absent on the ASUS. Other Ruby-specific HAL lookups remain
   unresolved. Input timestamps sometimes regress, with gesture queue flushes;
   this is not yet traced to a kernel clocksource. The normal live boot does
   not provide the kernel trace needed to decide that question.

The next hardware pass must check audible media at a useful volume, zram/mmd,
network reconnect and a longer interactive session while collecting logs. The
USB logger saves ten minutes, shorter than this 16.8-minute watchdog; retain
ADB logcat and a new bugreport as well for later events. Installation remains
disabled until stability, required desktop services and a reviewed
install/update/rollback path are established. No internal disk was modified.

## Validation

Seven collector checks, 16 compatibility guards and seven live-image guards
pass. Native init verification accepts the new fragment. Both stock baselines
and the adapted hybrid pass VINTF, strict SELinux and service-context checks;
all 396 inventoried inputs are unchanged during the audit. The expected
unadapted-hybrid policy failure remains.
Candidate comparisons confirm byte-identical retained system/system_ext/product,
kernel, both module images, compiled SELinux policy and logger binary versus
net18. New vendor content is the init fragment and added memory-state snapshots.

The zram19 candidate (`c29aade10f317995…`) completes a 660.6-second UEFI/USB
TCG run with emulated audio and a disposable software TPM. Its saved capture
finishes at 600.4 seconds: 290 files / 29,417,686 bytes, zero overruns, failed
saves or unsaved bytes. The source image and synthetic internal disk hashes
are unchanged. At 10.469 seconds the module creates zram0. At 289.302 seconds
the kernel activates 12,146,652 KiB of swap; mmd_setup exits 0 and mmd starts.
The same setup succeeds after the framework restart, and 17 snapshots show mmd
running. No mmd_setup abort occurs. SwapTotal changes from 0 before setup to
12,146,652 KiB afterward. This is VM proof of the correction, not a physical
G14 swap-size recommendation; the framework controls sizing for available RAM.

The known system-server SIGSEGV recurs, with execmem denials and one zygote
exit. This remains distinct from the physical G14 property-service watchdog;
neither stability failure is fixed by loading zram. Enforcing boot completion
and welcome are observed, but the candidate is still a diagnostic image.
See `validation-zram19.json`, `complete-zram19.txt` and
`runtime-zram19-excerpts.txt`. It has not been written to the physical USB.

Primary source checked 2026-10-19:
[AOSP module loading and GKI paths](https://source.android.com/docs/core/architecture/kernel/loadable-kernel-modules).
Local primary source: AOSP `system/memory/mmd/README.md` requires zram devices
before boot completion; `system/core/libmodprobe` resolves module dependencies.
The private retained Ruby `mmd.rc` starts setup after boot completion.
