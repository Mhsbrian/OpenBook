# G14 black-screen capture and firmware-path correction

2026-10-19, ANAL-228. The owner returned the diagnostic SanDisk after booting
the normal **save detailed logs to USB** entry on the GA403WR / Ryzen AI 9
HX 370 / Radeon 890M. This is physical hardware evidence, separate from TCG.

The ESP was mounted read-only. All 160 saved files (13,595,559 bytes) were copied
privately and checked against their source SHA-256 values. A subsequent
read-only FAT check passed. Raw logs, device identifiers and userdata are not
published. `capture.json` and `first-failure.txt` contain the relevant findings.

## First failure

At 6.047 seconds, amdgpu cannot find its PSP, display, graphics, SDMA, VCN and
MES firmware (`-2`), then reports **Fatal error during GPU init**. XDNA, MT7925
Wi-Fi/Bluetooth and regulatory firmware also fail lookup. The requested files
are present in the assembled vendor tree, except the optional older MES
fallback: its preferred `gc_11_5_0_mes_2.bin` is present.

The saved `/proc/cmdline` lacks `firmware_class.path=/vendor/firmware`. The
OpenBook `vendor_boot.img` supplies it, but all five research UEFI entries and
the direct QEMU launchers discarded the vendor command line. Unlike an Android
bootloader, loading the extracted kernel/initrd does not automatically consume
that header. Linux's default firmware paths do not include `/vendor/firmware`
([kernel documentation](https://docs.kernel.org/driver-api/firmware/fw_search_path.html),
checked 2026-10-19). OpenBook's contract is in
`device/anybook/common/pc/BoardConfig.mk`.

Minigbm subsequently fails driver initialization. ANGLE fails Vulkan/EGL
initialization; SurfaceFlinger aborts with **no suitable EGLConfig found**.
There are 33 distinct SurfaceFlinger SIGABRT PIDs in the saved Android stream.
No successful Android boot-completion property is captured. SELinux and verity
remain enforcing. No SIGILL or kernel panic appears in this captured interval.
This establishes a firmware-lookup blocker before the renderer; it does not
prove that fixing it will resolve every later integration problem.

## Capture limits and changes

Kernel records are contiguous from sequence 0 through 26305, ending at
525.829401 seconds. `complete.txt` is absent. There is no captured shutdown,
kernel panic or main collector exit explaining the end; the reason is unknown.
The shell diagnostics complete all 18 snapshots and exit normally after
272.198 seconds, stopping logcat too early even though kernel capture continues.

The packager now reads and preserves the actual vendor command line for every
UEFI entry and direct QEMU launch. A guard rejects a missing or conflicting
firmware path. The shell collector keeps logcat running after its snapshots,
with a bounded lifetime, and records the firmware command line and DRM nodes.
Reading the firmware sysfs parameter is denied to shell in the VM; that
optional diagnostic does not broaden permissions.
Neither fix relaxes SELinux, changes the kernel or enables installation.

The corrected local candidate is
`048bacf5934bcd22c2450784e83ec5e8eb563184ff7bb7e690ac595a68ba48f4`.
Only the vendor logical image changes (the diagnostic shell script); all
framework logical images and the kernel are unchanged. The five generated
loader entries each contain the firmware path exactly once. Fifteen
compatibility guards and six live-image guards pass; strict image-policy and
file-context validation pass during assembly, including firmware label lookups.

The corrected normal save-logs entry was observed for 720.6 seconds under TCG.
It captures 299 files / 29,793,360 bytes and finishes after 600.4 seconds, with
zero kernel overruns, failed saves or unsaved bytes. The saved guest command
line includes the firmware path, and 69,461 logcat lines follow the end of the
18 snapshots. The source image and synthetic internal disk hashes are unchanged;
there are no logger-domain or FIFO denials. `validation.json` and
`complete-tcg.txt` record these checks. The welcome screen renders and boot
completion is reported, but the known system-server SIGSEGV and `mmd_setup`
abort recur. This is a packaging/logging pass, not stable desktop qualification.

At the end of log review, the returned stick still held diagnostic candidate
`19b9a949…`; the `physical_stick_updated: false` field in `validation.json`
describes that review run.

The owner subsequently requested proceeding. The same 62 GB SanDisk Ultra was
updated with the corrected, unchanged VM-tested image `048bacf5934bcd22…`:
12,766,412,800 bytes written in 637 s and fully read back in 95 s with matching
SHA-256, then powered off successfully. `physical-write.json` records this
later action. Before writing, its entire used image extent was preserved
privately (12,766,412,800 bytes, mode 0600); both copies of its 160 report files
were hash-verified. The installed laptop and firmware were not updated.

The next G14 test should use **Googlebook - save detailed logs to USB (10
minutes)**, run for 12 minutes, then return the stick for inspection. The
correction requires that physical test before claiming Radeon or desktop success.
