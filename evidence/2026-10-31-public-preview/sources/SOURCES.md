# Source for OpenBook 0.1.0-preview.1

OpenBook's image contains software under the GNU GPL and LGPL. This is its complete corresponding source,
published next to the image so you can get it from the same place. OpenBook's own code is in
https://github.com/Mhsbrian/OpenBook (Apache-2.0).

| File | What it is |
|---|---|
| `openbook-0.1.0-preview.1-source-kernel.tar.xz` | Linux 6.18.21-android17-5-g2461ae8277e6: Google's Android common kernel with OpenBook's commits, the Kleaf build files with OpenBook's commit, OpenBook's kernel modules, nouveau and NVIDIA's open modules (Dual MIT/GPL), the pinned manifest and the patch series. Build: `docs/kernel.md` in the OpenBook repository |
| `openbook-0.1.0-preview.1-source-userspace.tar.xz` | the Android projects below, as built, and Mesa's libelf (elfutils, LGPL-3.0+) with Mesa itself |
| `openbook-0.1.0-preview.1-source-systemd-boot.tar.xz` | systemd-boot 262-1 (LGPL-2.1+): systemd's upstream source and Arch Linux's packaging |
| `aosp-manifest.xml` | every Android project in the build, at its exact revision (all public at android.googlesource.com) |

## Kernel revisions

```
kernel release: 6.18.21-android17-5-g2461ae8277e6
common: 2461ae8277e6c5b44741cbdec16e9eff0aa0b580 = public 3938c8d97142d5cf31543aa96f864a2cf832dda0 + 5 OpenBook commits (patches/common)
build/kernel: 901d2e05b785ab4e1303001f892a9ccc45b8adb7 = public 5877a40116cd6d60c873dea521e532e65e9da8fd + 1 OpenBook commits (patches/build-kernel)
devices/anybook/nvidia: a362ba7a6d142da8751400b44a7873410876afda a362ba7
devices/anybook/nvidia_open: 8953b3d64def983a6021cd6dbc61d450e26566bb 8953b3d
Every other project of the Kleaf workspace (toolchains, build tools) is public at manifest-pinned.xml's revisions.
```

## Userspace: copyleft binaries in the image, and their source

From the image's own NOTICE files (`scripts/release/notice-scan.py`).

| Source | Licence texts | Binaries in the image |
|---|---|---|
| `external/angle` | GPL | `/system/lib64/libEGL_angle.so`, `/system/lib64/libGLESv1_CM_angle.so`, `/system/lib64/libGLESv2_angle.so` |
| `external/bpftool` | GPL | `/system/bin/bpftool` |
| `external/dnsmasq` | GPL | `/system/bin/dnsmasq` |
| `external/e2fsprogs` | GPL/LGPL | `/system/bin/blkid`, `/system/bin/e2freefrag`, `/system/bin/e2fsck`, `/system/bin/e2fsdroid`, `/system/bin/mke2fs`, `/system/bin/mkfs.ext2` … |
| `external/exfatprogs` | GPL | `/system/bin/fsck.exfat`, `/system/bin/mkfs.exfat` |
| `external/f2fs-tools` | GPL/LGPL | `/system/bin/defrag.f2fs`, `/system/bin/dump.f2fs`, `/system/bin/fsck.f2fs`, `/system/bin/make_f2fs`, `/system/bin/resize.f2fs`, `/system/bin/sload_f2fs` |
| `external/fec` | LGPL | `/system/lib64/libfec_rs.so` |
| `external/gptfdisk` | GPL | `/system/bin/sgdisk` |
| `external/hyphenation-patterns` | LGPL | `/system/usr/hyphen-data/hyph-hy.hyb`, `/system/usr/hyphen-data/hyph-hy.lic.txt`, `/system/usr/hyphen-data/hyph-ru.hyb`, `/system/usr/hyphen-data/hyph-ru.lic.txt` |
| `external/iproute2` | GPL | `/system/bin/ip`, `/system/bin/ss`, `/system/bin/tc`, `/system/lib64/libiprouteutil.so`, `/system/lib64/libnetlink.so` |
| `external/iptables` | GPL | `/system/bin/ip6tables`, `/system/bin/ip6tables-restore`, `/system/bin/ip6tables-save`, `/system/bin/iptables`, `/system/bin/iptables-restore`, `/system/bin/iptables-save` … |
| `external/libcap` | GPL | `/system/lib64/libcap.so` |
| `external/libexif` | LGPL | `/system/lib64/libexif.so`, `/vendor/lib64/libexif.so` |
| `external/libnl` | LGPL | `/system/lib64/libnl.so`, `/vendor/lib64/libnl.so` |

```
external/angle 1f4500d3906c24de59eec5b9cda17a2ad2a8ba2d
external/bpftool 707a2f3848c4b87b1b37890da1f4ca5d22390ee0
external/dnsmasq 37720d7ebe90b68428dc265204cebf26990f4edd
external/e2fsprogs 3eb17241db7cd4408cc1bce9d25b602465ace8ff
external/exfatprogs 02af625a7b521040c883aa91910a8278e22a21ff
external/f2fs-tools c64468cb6397fb63bded0f549438b472f7e7cf88
external/fec 90857deb7973c0ca24c79b9c1809fc9667f32c4f
external/gptfdisk e6867acc464878771f1cc139e14e058238ace238
external/hyphenation-patterns 487eaf7776fa0733d9835747032288ab0b549a70
external/iproute2 98d58311c2235def6596bda3a0da9366de2979e0
external/iptables df1a07fd3d0c157a71a4c157cc728062a01032b2
external/libcap 9a2ead0b5a377a75849cb0656aa553b5452a7080
external/libexif e180c53a25cc0f26e6e0caf4a2708c41b8ec5214
external/libnl 2be7f4458cf7c7831df8fbac395e6a7222d0d13f
mesa-build/elfutils 219c3a368b121307f2e05593cee89b8591cc40b9 (libelf_mesa.so, LGPL-3.0+ / GPL-2.0+)
mesa-build/mesa f30f204df44c09d41adaef97a550749a4cf4dac2 (Mesa, MIT; for relinking against a changed libelf)
```

## Licence texts that name the GPL but need no source here

These binaries' notices carry a GPL or LGPL text for a component that is not under it in the binary, so the
source is not included above. All of it is public at the revisions in `aosp-manifest.xml`.

| Source | Binaries | Why |
|---|---|---|
| `frameworks/base` | 3: `/product/priv-app/StatementService/StatementService.apk`, `/system_ext/app/AccessibilityMenu/AccessibilityMenu.apk`, `/system_ext/priv-app/SystemUI/SystemUI.apk` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/AvatarPicker` | 1: `/system_ext/priv-app/AvatarPicker/AvatarPicker.apk` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/Calendar` | 1: `/product/app/Calendar/Calendar.apk` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/Camera2` | 3: `/product/app/Camera2/Camera2.apk`, `/product/app/Camera2/lib/x86_64/libjni_jpegutil.so`, `/product/app/Camera2/lib/x86_64/libjni_tinyplanet.so` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/Contacts` | 1: `/product/priv-app/Contacts/Contacts.apk` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/DeskClock` | 1: `/product/app/DeskClock/DeskClock.apk` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/Dialer` | 1: `/product/priv-app/Dialer/Dialer.apk` | the notice is prebuilts/tools' whole licence collection (416 KB); its LGPL entries are build tools there such as JNA 3.4.0, and the app's dex has no JNA classes (checked 2026-10-31) |
| `packages/apps/Gallery2` | 4: `/product/app/Gallery2/Gallery2.apk`, `/product/app/Gallery2/lib/x86_64/libjni_eglfence.so`, `/product/app/Gallery2/lib/x86_64/libjni_filtershow_filters.so` … | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/ImsServiceEntitlement` | 1: `/product/priv-app/ImsServiceEntitlement/ImsServiceEntitlement.apk` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/Launcher3` | 1: `/system_ext/priv-app/Launcher3QuickStep/Launcher3QuickStep.apk` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/Messaging` | 1: `/product/app/messaging/messaging.apk` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/Settings` | 1: `/system_ext/priv-app/Settings/Settings.apk` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/SettingsIntelligence` | 1: `/product/priv-app/SettingsIntelligence/SettingsIntelligence.apk` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/StorageManager` | 1: `/system_ext/priv-app/StorageManager/StorageManager.apk` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/apps/ThemePicker` | 1: `/system_ext/priv-app/ThemePicker/ThemePicker.apk` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `packages/inputmethods/LatinIME` | 2: `/product/app/LatinIME/LatinIME.apk`, `/product/app/LatinIME/lib/x86_64/libjni_latinime.so` | Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's Exhibit A, for components under "MPL-1.1 or GPL-2.0" (used under the MPL). The apps are Apache-2.0 |
| `vendor/anybook/mesa` | 10: `/vendor/etc/libdrm/amdgpu.ids`, `/vendor/lib64/egl/libEGL_mesa.so`, `/vendor/lib64/egl/libGLESv1_CM_mesa.so` … | Mesa's libelf (elfutils, LGPL-3.0+): mesa-build/ in the userspace tarball |
| `device/anybook/common/installer/app` | 1: `/system_ext/priv-app/OpenBookInstaller/OpenBookInstaller.apk` | OpenBook's own app (Apache-2.0); its GPL text is Kotlin's, as above. Source: the OpenBook repository |
| `device/anybook/common/quire` | 1: `/system_ext/priv-app/OpenBookQuire/OpenBookQuire.apk` | OpenBook's own app (Apache-2.0); its GPL text is Kotlin's, as above. Source: the OpenBook repository |
| `device/anybook/common/setup` | 1: `/system_ext/priv-app/OpenBookSetup/OpenBookSetup.apk` | OpenBook's own app (Apache-2.0); its GPL text is Kotlin's, as above. Source: the OpenBook repository |

If something here is missing or wrong, open an issue at https://github.com/Mhsbrian/OpenBook/issues and we will
publish it. This offer is valid for three years from the release date, for anyone who has the image.
