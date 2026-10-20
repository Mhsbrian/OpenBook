# Installed Googlebook input candidate (ANAL-228, 2026-10-20)

The owner reports successful bare-metal installation, then a reproducible
tap-drag release after roughly one second while the second contact stays down.
The laptop is away from the host and in use. No laptop connection, preference
change, reboot, physical disk write or collection of owner data was performed.

## Finding and correction

A synthetic first tap, second contact, six seconds of smooth motion and lift
reproduces the early release when timestamp-less repeat frames are modeled
using Ruby's converter policy. In the **retained Ruby gestures library**, the
button goes down at 1.4100 s and up at 2.1972 s, although contact remains until
7.6461 s. Both the clean control and preserved-timestamp control release at
7.6461 s. Tap and tap-drag are enabled, drag lock disabled, using the G14's
measured pressure-less ELAN capabilities.

This demonstrates a software failure consistent with the report. It is not a
labeled recording of this particular hardware failure. Palm classification,
actual contact dropout, app dispatch and Settings preference propagation remain
separate possibilities for other symptoms.

Ruby's `HardwareStateConverter::processRawEvent` clears `mMscTimestamp` after
each SYN_REPORT. A frame without MSC therefore resets the gesture clock.
OpenBook's existing `frameworks/native/0002` preserves this member instead.
`input-timestamp-patch.py` applies the equivalent operation to the **exact**
locally licensed Ruby binary: eight NOP bytes replace the redundant store.
The original whole-library SHA, ELF executable mapping and instruction preimage
must match. Unknown builds and reapplying the patch fail. There is no framework
replacement, new SELinux allowance, timer-threshold change or preference override.

The native test calls the real exported converter in both binaries: consecutive
SYN frames yield MSC `1.2345, 0` before and `1.2345, 1.2345` after; an explicit
MSC zero still yields zero. Its empty-accumulator ABI probe is restricted to these
two fingerprints. It then tests the real exported gesture library with all three
timing policies. It runs under Ruby's Bionic linker on the host, outside Android
services; the missing `/linkerconfig` warning is expected. This is stronger than
the separate AOSP replay, but does not exercise the laptop kernel or app dispatch.

| Artifact | SHA-256 |
|---|---|
| Original library | `e27014ec1e2e4d611cdd6df2c1175d86d679d1353ee970f190e831953fbcb3e4` |
| Patched library | `4752d1351dbed7f0b5cb5a1d31d409edbb91396c6627fd7b34e1e99a0e655148` |
| Fresh camera25 source | `df793f2eed3a5c901659014c2ae368d8e5eeb3d504b514d46fc8c0c1959a7af4` |
| Prepared input27 image | `816e694848c146b84c661f46717cf113f5df9ae47c07556cbba4b2021f5f4bf9` |

## Image assembly and preservation

`build-input-candidate.py` reconstructs system EROFS using the original inode
ownership, permissions, timestamps, capabilities and SELinux labels. A read-only
liberofs inventory compares all 3,645 inodes and 7,292 inode/xattr rows. All 3,464
files/symlinks match except the eight-byte correction. Unknown xattrs or hardlinks
are refused. Vendor, credential services, kernel/modules, policy and other logical
partitions retain camera25 bytes. New AVB descriptors are verified with the same
local test-key trust model, and only the bootconfig digest changes.

Two failed build approaches were rejected before packaging: this EROFS version
does not implement full-data image-layer rebuild, and 4 KiB compression clusters
exceeded the original logical partition. Rebuilding from extracted files with
the complete metadata inventory and 64 KiB clusters passes the original size.
No output of either failed build is a candidate.

The image is private and contains no configured owner data. **Never write the
whole fresh image over the installed laptop.** `installed-update.py` instead
takes a fresh, complete, offline installed-disk snapshot and produces a private
updated clone. It requires the installed schema, exact camera25 system,
disk-bound UUIDs, unchanged initrd bodies/security identity, and the exact
reviewed input27 artifact. Only super, vbmeta and EFI change; protected-byte
hashes cover GPT, misc, boot partitions, metadata, userdata and unused space.
It rejects the old USB schema and any expanded or unfamiliar layout.

This is a **preparation tool, not a physical updater**. It implements neither
an online single-slot write nor automatic fallback. The AOSP A/B skill does not
apply to this single-slot Ruby layout. ANAL-229/231 remain the separate
containment/recoverable-update work. Experimental updater suppression from PR121
is not included here.

For the owner's return: obtain the current installed identity and a fresh,
consistent offline backup; prepare from that backup; review the exact NVMe and
recovery path before physical application. Never restore the earlier USB data
over the laptop's newer data. Hardware acceptance must include PIN unlock,
current apps/files, ten-second stationary/moving tap-drag, normal lift release,
two-finger Settings scrolling and sleep/resume. Keep a labeled touchpad-only
trace if any failure remains; never collect keyboard events.

## Reproduction

Paths below are local private build inputs, not distributable artifacts.
Run from the repository. Use a new output directory for each build. Source
revisions and commands are retained in the evidence directory.

```bash
W="$HOME/anybook/installer/work/anal228-input27"
A="$HOME/anybook/aosp/src"
R="$(pwd)"

# Read-only EROFS metadata helper, matching the already built AOSP host library.
scripts/installer/inst-docker.sh gcc -D_GNU_SOURCE -DHAVE_LINUX_TYPES_H \
  -DHAVE_SYS_IOCTL_H -DHAVE_UNISTD_H -DEROFS_MAX_BLOCK_SIZE=16384 -DEROFS_MT_ENABLED \
  -I"$A/external/erofs-utils/include" "$R/scripts/googlebook/erofs-inventory.c" \
  "$A/out/soong/.intermediates/external/erofs-utils/liberofs/linux_glibc_x86_64_static/liberofs.a" \
  "$A/out/soong/.intermediates/external/selinux/libselinux/libselinux/linux_glibc_x86_64_static/libselinux.a" \
  "$A/out/soong/.intermediates/external/pcre/libpcre2/linux_glibc_x86_64_static/libpcre2.a" \
  -llz4 -llzma -lz -lzstd -lpthread -o "$W/erofs-inventory"

scripts/installer/inst-docker.sh python3 "$R/scripts/googlebook/build-input-candidate.py" \
  --base "$HOME/anybook/installer/work/anal228-ruby-live-camera25" \
  --tools "$A/out/host/linux-x86/bin" --inventory "$W/erofs-inventory" \
  --key "$A/external/avb/test/data/testkey_rsa4096.pem" --out "$W/new-build"

"$HOME/anybook/kernel/src/prebuilts/ndk-r27/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android35-clang++" \
  -std=c++20 -O2 -Wall -Wextra -Werror -static-libstdc++ \
  -I"$A/external/libchrome-gestures" scripts/googlebook/input-replay-native.cpp \
  -ldl -o "$W/input-replay-native"

python3 scripts/googlebook/run-input-native.py --probe "$W/input-replay-native" \
  --ruby-system "$HOME/anybook/work/gbos-ruby/fs/system_a/system" \
  --apexes "$HOME/anybook/installer/work/anal228-ruby-audit-camera25/ruby-apex" \
  --patched-library "$W/image-v3/rebuilt/system/lib64/libinputflinger.so" \
  --output "$W/native-new.json"
```

The prepared artifact is pinned separately from its recipe. EROFS/AVB/FAT build
metadata can make a newly rebuilt image's digest differ; a rebuild requires
fresh audit/rehearsal and an explicit reviewed-pin update before the installed
preparer accepts it.

## Storage report

The owner's limited available storage is explained by the installer's deliberate
8 GiB userdata copy, not evidence that files disappeared. The rest of the SSD is
unallocated. This candidate does **not** expand storage.

A correct repair must grow the final partition without moving its start/UUID,
retain both GPT copies, reopen the full-sized encrypted mapping using the existing
KeyMint-wrapped key, and grow F2FS with data offline. It must also preserve
fscrypt policies, checkpoint state, compression/quota features and per-file
ciphertext, then verify the owner's current credentials and files after reboot.

Source inspection finds no automatic growth in the current fstab/fs_mgr path.
The shipped kernel's F2FS resize ioctl rejects growth. The bundled `resize.f2fs`
explicitly rejects `-s` for expansion; normal expansion can move main-area data
blocks. `dm-default-key` skips its metadata key for encrypted file-content bios
and uses sector-dependent DUNs for other I/O. Consequently a raw offline block
mover through the decrypted mapping needs specific validation; copying preserved
encryption-key files alone does not establish correctness. This is a risk from
the source review, not a measured claim that the user's data is corrupt.

Next storage work: measure the actual NVMe and current filesystem/checkpoint
state when accessible; build an encrypted disposable fixture with PIN, apps and
known CE/DE files; test a key-aware offline growth method, interruptions and
restoration before enabling it on the laptop. If direct growth cannot preserve
encrypted blocks, evaluate a same-device filesystem migration preserving fscrypt
policy/keys and metadata. Reformatting the current userdata is not an acceptable
repair. Do not consume all spare space before deciding whether recoverable system
slots need a small reservation.

## Primary sources checked 2026-10-20

- [AOSP HardwareStateConverter](https://android.googlesource.com/platform/frameworks/native/+/refs/heads/main/services/inputflinger/reader/mapper/gestures/HardwareStateConverter.cpp):
  current source still contains the post-SYN reset; retrieved directly from
  Gitiles when the web renderer failed.
- [Gestures tap state machine](https://android.googlesource.com/platform/external/libchrome-gestures/+/6c2310952338e9f094a1aeb6a83f7356ff5d6042/src/immediate_interpreter.cc):
  normal held drag has no one-second expiry. Local reference source and the real
  Ruby library controls agree; physical device behavior remains to be measured.
- [Metadata encryption](https://source.android.com/docs/security/features/encryption/metadata)
  and [AOSP MetadataCrypt](https://android.googlesource.com/platform/system/vold/+/307fbdc3bb083fb4db8078bd9465581fd0d1d923/MetadataCrypt.cpp):
  key-backed mapping precedes filesystem checking/mounting.
- [F2FS resize implementation](https://android.googlesource.com/platform/external/f2fs-tools/+/c64468cb6397fb63bded0f549438b472f7e7cf88/fsck/resize.c):
  safe mode rejects expansion; normal growth can relocate blocks.
- Local built kernel `fbfdd65b0fd1d020a560c54988cdccaec73a6b0a`,
  `fs/f2fs/gc.c:f2fs_resize_fs` and `drivers/md/dm-default-key.c:default_key_map`;
  upstream [metadata-encryption target](https://android.googlesource.com/kernel/common/+/refs/heads/android-mainline/drivers/md/dm-default-key.c).
