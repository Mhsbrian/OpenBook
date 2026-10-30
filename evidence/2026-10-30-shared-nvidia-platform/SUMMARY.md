# Shared kernel and vendor layer with NVIDIA's open driver: AOSP G14 build and QEMU checks (ANAL-319)

2026-10-30. Branch `anal-319/shared-nvidia-platform`. Nothing was written to the laptop or a USB stick: the G14
runs the Googlebook (Ruby) image, and these are VM results.

## Inputs

- **Kernel:** not rebuilt. `kernel/` equals GoodBook `792d203` (tree `d4658773`), whose kernel R5–R9 shipped. The
  staged package is `~/anybook/kernel/g14/anybook-g14-gbos-16302624-anal297`, and every image matches the R5
  hand-off pins (ANAL-297 revision 2, `b2b67e43…`):
  - bzImage `37467ae9…`, release `6.18.21-android17-5-g2461ae8277e6`;
  - `vendor_dlkm.img` `e008193f…`;
  - `system_dlkm.img` `62b1bb96…`.

  [`g14-kernel-PROVENANCE.txt`](g14-kernel-PROVENANCE.txt) records the staging. Before it, the tree held the
  2026-10-17 kernel ([`g14-kernel-PROVENANCE-before.txt`](g14-kernel-PROVENANCE-before.txt)).
- **NVIDIA GSP firmware:** staged by `scripts/g14-stage-kernel.sh` from ANAL-297's
  `kernel-nvidia-open-firmware.py` output. `gsp_ga10x.bin` `a20100ca…`, `ucodes_ga10x.bin` `eed53d76…` and the
  licence `c692fb14…` are each checked against `kernel/firmware/anybook-nvidia-open.tsv`.
- **AOSP:** `anybook_g14_x86_64-cp2a-userdebug`, `droid` ([`aosp-build.txt`](aosp-build.txt)):
  - the first build passed in 12:05;
  - the rebuild after the policy fix below passed in 5:22, with the SELinux neverallow checks;
  - sizes and hashes are in [`image-sizes.txt`](image-sizes.txt). `vendor.img` is 222.9 MB with the firmware, and
    `super` fits.
- **Disk image:** `scripts/g14-image.sh --label openbook-g14-anal319b`, sha256 `193d237c…`
  ([`disk-image.json`](disk-image.json)).

## QEMU/KVM + OVMF, the G14 product as a generic PC (no AMD or NVIDIA GPU)

**[`qemu-g14/`](qemu-g14/): `expect-g14.json`, the product's standard check. 58/58 steps.**
- `boot_completed` at 15.3 s, with 148 modules live; it reaches OpenBook's first-run setup on SwiftShader.
- `openbook-pc-setup-test`: 154 ok, 0 failures. `dgpu-power-check`: no NVIDIA GPU enumerated, nothing to do.
- **SELinux denials, 4.** Against the last product run before the port (`anal192e`, 2026-10-18, installer end to end):
  - SystemUI reading `bluetooth_lea_prop` (2) and keystore's gatekeeper lookup (1) are in both runs;
  - `shell` reading `/proc/sys/kernel/tainted` (1) is the check's own `cat`.

  **No new denial.**

**[`qemu-g14-first-boot/`](qemu-g14-first-boot/): the same check before the fix. 58/58, 5 denials.** The extra one
was new: `vendor_init` reading `openbook.gfx.request` as `default_prop`. The switcher's init trigger reads that
property, and on the Googlebook image only its system layer defines it. Commit `31901a42` defines it in the AOSP
product's system_ext policy, with the same type and grant, and the denial is gone.

**[`qemu-g14-nvidia/`](qemu-g14-nvidia/): `scripts/installer/expect-g14-nvidia.json`, new. 23/23 steps.**
- `nvidia`, `nvidia-modeset`, `nvidia-drm` and `nouveau` all carry the running kernel's vermagic.
- All four are on `vendor_dlkm`'s blocklist, and none is live. The single `modules.load` hit is
  `nvidia-wmi-ec-backlight`, the backlight driver.
- `modules.options` carries `NVreg_DynamicPowerManagement=0x02` and `nvidia-drm modeset=1`.
- The GSP firmware and its licence are in `/vendor/firmware`, with the pinned sha256s.
- `/odm/etc/ueventd.rc` has the `/dev/nvidiactl`, `/dev/nvidia-modeset` and `/dev/nvidia*` rules. There are no
  nodes, because QEMU has no NVIDIA GPU.
- The switcher reads `firmware absent (unknown)`, committed Hybrid, firmware writes off, and no asus-wmi MUX, so
  nothing is saved. `vendor.openbook.gfx.mode=unknown`, so the boot load of NVIDIA's driver does not run, and
  `ro.gfx.driver.0` stays empty.
- `dgpu-report`'s health line reads `state=absent … nvrm=0 xid=0`.
- No denial involving NVIDIA, the GPU, the switcher or `vendor_modprobe`.
- Observed: libmodprobe warns "multiple options lines present" for nouveau, nvidia and nvidia-drm. It is the same
  `vendor_dlkm` the Googlebook releases ship, and the options apply.

## Not shown here (from the Googlebook images, same kernel and vendor files)

The driver loading and binding the GB205, runtime D3cold when idle and across s2idle, and the boot load in Hybrid
were shown on the G14 on 2026-10-26 to 2026-10-29 (ANAL-299, R7, R8). OpenBook's own image has not been installed
on the laptop with this change. Apps on the RTX need NVK on NVIDIA's driver, which stays private to GoodBook.

## Harness note

`g14-qemu.sh --again` boots silently on images with `openbook-bootsync`: once a boot is marked good, bootsync points
`loader.conf` back at `openbook-<slot>.conf`, which has no serial console. This is the same logic as before the port.
The NVIDIA check therefore ran on a fresh copy of the image.
