# Input27: held drag correction and installed-data preparation

Owner report: successful bare-metal install, held tap-drag releases after about
one second, storage still limited. Laptop is away and in use; no physical device
was accessed or written. This directory contains only synthetic measurements,
build fingerprints and sanitized counts.

- `native-controls.json`: the actual Ruby converter yields MSC `1.2345, 0`
  before the patch versus `1.2345, 1.2345` after it. Explicit zero still resets.
  The actual Ruby gestures library reproduces early release at 2.1972 s with
  repeat/reset policy; clean/preserve controls release at the real lift, 7.6461 s.
  The native ABI layout probe is SHA-gated and uses empty accumulators. It does
  not access any input devices or Android services.
- `image.json`: exact-build eight-byte correction; 3,645 inode records, every
  xattr, and all 3,464 files/symlinks compared. Only the input library differs.
  AVB root/descriptors and EFI digest are regenerated; vendor/kernel/security
  components retain the earlier qualified camera25 contents.
- `preservation.json`: a clone of the existing *synthetic installed* disk gets
  only EFI/super/vbmeta updates. GPT, data, metadata, misc, boot and unused space
  retain their bytes. No earlier USB userdata is imported.
- `initial-rehearsal.json`: the 480-second observation completes and Android
  boots, but the initial harness incorrectly requires OVMF to print the UUID.
- `rehearsal.json`: the **same captured run** re-evaluated with direct before/
  after initrd bootconfig verification and actual NVMe metadata/super/userdata
  selection. Preservation and boot checks pass; all four metadata key files
  remain identical. No second run is claimed.

The VM still reproduces the known system-server SIGSEGV/SEGV_ACCERR, an execmem
denial and one zygote exit. These measurements do not establish runtime stability
or a physical fix. The fixture is not an owner PIN/app migration test.

The candidate is prepared privately as
`installer/work/anal228-input27/image-v3` under the local data root. Whole-image
SHA-256: `816e694848c146b84c661f46717cf113f5df9ae47c07556cbba4b2021f5f4bf9`.
Never flash it over configured data. The installed preparation tool requires a
fresh offline current-laptop snapshot and accepts only this reviewed artifact.
Physical application/recovery and hardware acceptance remain open.

Storage is still 8 GiB. Source review confirms that the installer copied that
extent, mounted F2FS growth is unsupported, and the bundled offline safe-resize
mode refuses expansion. Normal resizing plus dm-default-key/fscrypt requires
an encrypted-file preservation test before it can be enabled. No storage growth
was attempted. Detailed reasoning, primary sources and reproduction are in
`docs/googlebook-input-update.md`.
