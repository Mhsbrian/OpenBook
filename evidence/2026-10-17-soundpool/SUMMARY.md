# ANAL-179: SystemUI's SoundPool sounds under enforcing (2026-10-17)

ANAL-198's follow-up (PR #64) made Codec2 decode on the G14 product. One new denial then showed: `audioserver` could not use SystemUI's SoundPool memory (`evidence/2026-10-17-kernel-g14-r2/`). Everything here ran in QEMU/KVM on the build host, with SELinux **enforcing** (`getenforce` in `bootsound.txt`) and QEMU's HDA output recorded to a WAV file. Check: `scripts/installer/expect-g14-soundpool.json`, run as `QEMU_AUDIO=1 scripts/g14-qemu.sh IMG RUN <abs path to the expect file>`.

What the check does:
1. Boot. SystemUI plays the unlock sound when the boot's lock screen goes away ("No authentication on boot"), through SoundPool.
2. Read the denials and SystemUI's log (`bootsound.txt`).
3. Turn the lock screen on for the test (`cmd lock_settings set-disabled false`), then sleep, wake and `wm dismiss-keyguard`, so the unlock sound plays again. Turn the lock screen back off (`locksound.txt`).
4. Collect all denials (`avc.txt`), logcat and dmesg.
5. `wav-tone.py --activity` lists what reached QEMU's codec (`audio-out-activity.json`).

| | `before/`: `main` (ANAL-198's `openbook-g14-anal198-main`) | `after/`: `main` + `system_ext/audioserver.te` (`anal179-sp-a`) |
|---|---|---|
| Kernel | `6.18.21-android17-5-gfbfdd65b0fd1` (bzImage `55b86074…`) | the same |
| SELinux | enforcing | enforcing |
| `audioserver → appdomain_tmpfs:file { read write }` | **2 denials** (one per unlock sound), `scontext=u:r:audioserver:s0 tcontext=u:object_r:appdomain_tmpfs:s0:c512,c768`, the fd `/memfd:MemoryHeapBase` | **0** |
| SystemUI's log | `AudioFlinger could not create track` and `SoundPool::Stream: play_l: error -2147483646 creating AudioTrack`, twice; binder `BR_FAILED_REPLY ... Operation not permitted` | no failure |
| What reached the codec | **nothing** (a 44-byte WAV, header only) | **two sounds**, 0.10 s and 0.15 s, peak −26.9 dBFS: the boot's and the test's unlock sound |
| Other denials | `platform_app bluetooth_lea_prop`, `keystore hal_gatekeeper_service` (AOSP's own) | the same |

`regress/`: the standard product boot check (`expect-g14.json`) on the fixed image passes 58/58 steps. It shows 4 denials: `bluetooth_lea_prop` ×2, `shell proc`, and keystore → gatekeeper. ANAL-198's run on `main` showed 5, the fifth being this one (`evidence/2026-10-17-kernel-g14-r2/product-qemu/regress/avc.txt`).

The two sounds are the product's `/product/media/audio/ui/Unlock.ogg`. Decoded on the host with ffmpeg, it is one 0.15 s stretch above −50 dBFS, peaking at −9.8 dBFS. In QEMU it played 17 dB lower, at the system stream's volume.

**Why one TE rule is enough (no MLS change):**
- The memfd carries SystemUI's categories (`s0:c512,c768`), and `audioserver` runs at `s0`.
- AOSP's `private/mls` exempts `appdomain_tmpfs` from its file read and write constraints (`t2 == appdomain_tmpfs or ...`). Only `open` is limited by category, and the fd reaches `audioserver` already open, over binder.
- AOSP grants the same access as `audioserver appdomain:memfd_file` (`private/audioserver.te`). That rule only applies with the `memfd_class` policy capability, which AOSP 17 leaves off. So on this kernel the memfd is a tmpfs file with its creator's type, and `allow audioserver appdomain_tmpfs:file { getattr map read write }` is the same grant in that form.
- AOSP gives `mediaserver`, `system_server` and `mediaextractor` exactly this rule (`private/*.te`). The build's neverallow checks pass.

The alternatives were rejected:
- Making `appdomain_tmpfs` an `mlstrustedobject` would drop the category isolation between apps' memfds.
- Making `audioserver` an `mlstrustedsubject` would exempt all of its file access from MLS.
- A separate tmpfs type for SystemUI would not cover other apps' SoundPool use.
