# ANAL-198 on the owner's `anal192d` session: heap, ringtones, efivarfs (2026-10-18)

The stick was `openbook-live-20261018-anal192d` (`main` `81578c1` + #83, sha256 `db2a8203…`). Its kernel is #64's, `6.18.21-android17-5-gfbfdd65b0fd1`. Its boots ran on the G14 on 2026-10-18, about 11:00–12:15Z.

The source is the host copy `~/anybook/installer/g14/stick-20261018T123221Z/`, read only. That copy has three sets of logs:
- `live-001/prior/`: the default "OpenBook" boot. It ran under enforcing and lasted 59 minutes, and its persisted logcat includes kernel lines.
- `live-001/`: "save logs".
- `live-002/`: the ARM apps check.

The excerpts in `g14-anal192d/` carry only media, heap, efivarfs and amdgpu lines.

## On the G14

| Item | Result | Evidence |
|---|---|---|
| `system_heap.ko` | Loaded on all three boots. In use: refcount 49 and 53 in the two captures | `g14-anal192d/counts.txt` |
| DMA-BUF heap errors | `Could not open DMA-BUF heap` 0 times in each boot (64 in QEMU with the PR #26 kernel). `C2Store: Using DMABUF Heaps` 4 times | `counts.txt` |
| Vorbis decode | `c2.android.vorbis.decoder` created 10 times. No "No matching decoder" and no "Failed to create audio/vorbis decoder". `anal176t` had 15 of the latter | `counts.txt` |
| **A sound through MediaPlayer** | **Failed.** At 11:51:48Z SystemUI played the low-battery sound (the next boot's report shows the battery at 15 %). The decoder started, then `mediaserver`'s AudioTrack failed: "Could not get control block", MediaPlayer error (1, -19), no sound. The single memfd denial of the session caused it: `mediaserver` → `audioserver_tmpfs:file { read write }`, `permissive=0` | `g14-anal192d/lowbattery-sound-1151Z.txt` |
| Settings → Sound previews | **Not tried.** The Settings pages opened were Display, Apps and Accounts; SoundPicker never started. They would take the same MediaPlayer path, so they would have failed the same way | `counts.txt` |
| efivarfs | `efivarfs.ko` loaded. The installer's `openbook-installd.rc` (ANAL-191) mounts it read-write at `/sys/firmware/efi/efivars`, with no efivarfs denial. The installer's report was not saved this time, so its use of the boot entries is not shown | `counts.txt` |
| `amdgpu_firmware_info` | Not captured: the graphics check, which reads it, was not run. dmesg names DMUB `0x09005700` and VCN ENC 1.24 / DEC 9 rev 34, and the SMU initialised | `counts.txt` |
| GPU hangs | No amdgpu ring timeout, reset or page fault during the 59-minute enforcing session | `counts.txt` |

## The fix, and its proof in QEMU on the same image

The fix is `device/anybook/common/pc/sepolicy/system_ext/mediaserver.te`:

```
allow mediaserver audioserver_tmpfs:file { getattr map read write };
```

This is the tmpfs-file form of AOSP's `allow mediaserver audioserver:memfd_file …` (`private/mediaserver.te`). AOSP's rule needs the `memfd_class` policy capability, which AOSP 17 leaves off. It is the same gap #64 fixed for `mediaswcodec` and ANAL-179 fixed for `audioserver`.

The QEMU run (`qemu-anal192d/`) used the `anal192d` image itself. The image is identical by sha256, and the run booted a copy of it. The setup was:
- OVMF, with QEMU's HDA codec recording to a WAV file.
- SELinux enforcing throughout.
- The checks ran about 165 s after `boot_completed`. Android mutes notification sounds for 120 s after `BOOT_COMPLETED` ("avalanche"), and a first run inside that window played nothing.

| Phase | Low-battery sound (`cmd battery`) | Notification sound (`cmd notification post`) | `mediaserver` denials |
|---|---|---|---|
| `mplayer.txt`: the image's own policy | `Could not get control block`, MediaPlayer error (1, -19): the G14's failure | the same | 2 × `{ read write } audioserver_tmpfs`, `permissive=0` |
| `policyfix.txt`: as root, the device's split policy is recompiled with its own `secilc` plus the one rule, then loaded | | | |
| `mplayer2.txt`: the image with the rule, still enforcing | plays to the end (1.5 s, `onCompletion`), no error | plays to the end (1.9 s), no error | 0 (and no denial of any kind) |

- **The recompiled policy is the image's policy plus one rule.** It is 859,607 bytes, against 859,595 for the running policy: 12 bytes, one access-vector rule.
- **What QEMU's codec recorded** (`audio-activity.txt`): the boot's unlock sound, then two sounds of 1.05 s and 1.3 s above −50 dBFS. By order and length, these match the low-battery sound (1.45 s file) and Spark (1.94 s file). Phase 1 could not have produced audio, because its AudioTracks were never created.

## Policy build check (`sepolicy-check/`)

The product build has not run with the rule yet: the AOSP lane was busy. Instead, the AOSP host `secilc` compiled the G14 product's installed CIL files without `-N`. That means all 5,647 neverallow rules in `plat_sepolicy.cil` were checked:
- **The current policy:** rc 0.
- **Plus the rule:** rc 0, 12 bytes larger.
- **Negative control:** a forbidden `execute_no_trans` fails at `mediaserver.te:195`, as it should.

`audioserver-tmpfs-access.txt` lists which domains may use AudioFlinger's memfds. With the rule, they are apps, `mediaserver` and `audioserver`.

AOSP's third `audioserver:memfd_file` grant is to `system_server`, and it has no tmpfs form either. That would matter only for audio `system_server` plays itself, such as touch sounds through AudioService's SoundPool, which are off by default on this product (`def_sound_effects_enabled` false). It was not observed on the G14 or in QEMU, so it is not in this change.
