# Status

As of 2026-11-02. This page changes at release time (`CONTRIBUTING.md`). Day-to-day progress, test results and
decisions are on the issues. The history of this page is in Git.

## Latest release

**OpenBook 0.1.0-preview.2** (2026-10-31): a `userdebug` developer preview for the ASUS ROG Zephyrus G14 (2025,
GA403WR), signed with AOSP test keys.

- **In it:** the Android 17 desktop, OpenBook's GKI 6.18 kernel and AMD vendor modules, NVIDIA's open kernel driver
  615.78.08 with its GSP firmware (shipped unmodified under its licence's §1.1(d), with the licence next to the
  image), the graphics-mode switcher with firmware writes off, the installer, A/B updates, and Quire.
- **Checked on the release build in QEMU:** live stick 32/32, installed disk 58/58, NVIDIA 23/23, download test 9/9.
  adbd asks before it lets a computer in (`ro.adb.secure=1`); preview.1 didn't and was withdrawn after 12 minutes.
- **Not yet checked:** this exact image booting on the G14.
- **Downloads are broken for the public:** since the repository went private, the GitHub links on openbook.page
  return 404. Only the torrent works. Fixing that, and the source package, is M0.1 (ANAL-341).

## On the G14 today

Since 2026-10-23 the reference laptop has run the sibling image built on Google's Googlebook OS (GoodBook). It uses the
same kernel and vendor layer. OpenBook's last install there was `20261019.armfix1`, in slot B, as an A/B update.

| Area | State |
|---|---|
| Boot and install | The installer put OpenBook on the internal NVMe (2026-10-18). Later builds arrived over Wi-Fi as A/B updates with automatic rollback. The VM suite passes 79/79 install checks and 55/55 update and rollback checks. |
| Radeon 890M | amdgpu drives the panel at 120 Hz (959/959 frames on time). The desktop renders on ANGLE and RADV. dEQP: Vulkan 1.4 has 45,220 passes and 5 failures, GLES has 0 failures. |
| NVIDIA RTX 5070 Ti Laptop | NVIDIA's open driver loads after boot, binds the GPU and holds it in D3cold when it's idle, across sleep too (shown on the sibling image). Apps can't use the RTX yet. |
| Input, Wi-Fi, Bluetooth | Touchpad, keyboard, lid sleep and wake, Wi-Fi with internet, and Bluetooth pairing work. |
| Power | amd-pstate-epp works, and Android's sleep and wake work. S0i3 isn't reached yet. |
| Audio | Speakers and microphone work through ALSA. Android's audio path still needs a listening check. |
| ARM apps | The open Digitalis bridge, built from source: 14 of 16 ARM-only test apps run, and ARM64 Chromium renders. |
| Desktop look | Google Sans, circular icons, blur, Googlebook's desktop flags, OpenBook's wallpapers, boot animation, sounds and first-run setup. Google apps through the microG option or your own package. |
| Quire | The note, consent, a live mirror of agent actions, agents in the Linux environment, and full-laptop control that confirms destructive actions. |

`docs/HARDWARE.md` has the full driver and firmware map, and `docs/COMPAT-MATRIX.md` has the ARM app matrix.

## Known issues

- Apps can't render on the NVIDIA GPU. The clean-room NVK driver is M1's main work.
- Deepest idle (S0i3) isn't reached. A diagnostics module is in the kernel to find the blocker.
- Rendering into Android hardware buffers on the Radeon is open. A GPU hang resets the whole GPU and restarts the UI.
- Touchpad feel: a scroll start can read as two fingers, and tap-and-drag doesn't work yet.
- Bluetooth audio connects, but nobody has listened to it under SELinux enforcing yet.
- Previews are `userdebug` builds with test keys. Release keys and a `user` build come with the public beta (M2).

## Milestones

The plan of record is ANAL-334 (2026-11-02). `docs/PLAN.md` has the roadmap.

| Milestone | Goal | State |
|---|---|---|
| **M0** Reset | Repository holds source and docs only, CI enforces it, builds reproduce from a clean checkout, one copy of the code shared with GoodBook, a light release process | In progress: repository cleanup (ANAL-340), public downloads (ANAL-341), release process (ANAL-342). Then the reproducible build (ANAL-343) and shared code (ANAL-344). |
| **M1** 0.1.0-preview.3: NVIDIA for apps | Apps on the RTX with a per-app choice and an on/off switch, Eco ↔ Hybrid, a speed baseline, published | In progress (ANAL-336) |
| **M2** 0.2.0 public beta | Fresh public repository, release keys, `user` build, project license, install or live-only stick | Planned |
| **M3** Experience parity | Quire voice, performance, Chrome and the Linux environment, a second laptop | Planned |
