# Changelog

What changed in each OpenBook release, for people who use it. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

Developer previews are `userdebug` builds signed with AOSP's public test keys. They are for testing, not for daily
use. The first target is the ASUS ROG Zephyrus G14 (2025, GA403WR).

## [0.1.0-preview.3] - 2026-11-03

### Added

- **Apps can run on the NVIDIA GPU.** OpenBook NVK, a Vulkan driver built on NVIDIA's open kernel driver, ships
  in the image as the system package `org.openbook.nvk`. OpenGL ES apps reach it through ANGLE. OpenBook Graphics
  adds an "NVIDIA GPU for apps" switch and a GPU choice for each app. The Radeon stays the default.
- **OpenBook Launcher**, OpenBook's own desktop launcher. It is a fork of AOSP Launcher3, running in its desktop form:
  - a glass taskbar with one line of state;
  - click a running app's taskbar icon to minimize it; middle-click it to open a new window;
  - Meta+1 to Meta+9 open or focus the taskbar's apps in order;
  - drag a pinned app off the taskbar to unpin it;
  - All Apps as a centred glass panel, with app names on up to two lines;
  - start typing on the desktop to search;
  - one glass menu for the desktop, the taskbar and All Apps;
  - Overview for desks;
  - one motion system for the launcher's animations.
- **New apps stay off the desktop.** Installing an app no longer adds its icon to the desktop. A setting turns
  this back on.
- **OpenBook Graphics** in the G14 image: the graphics-mode app (Eco and Hybrid) with its allow-list.

### Changed

- Vulkan 1.0 apps now draw on the RTX. Before, they couldn't create a swapchain on it.
- Frames from the RTX are copied into the window with the GPU's copy engine, which speeds up light OpenGL ES
  scenes on the RTX.
- The Eco and Hybrid switch is safer with NVIDIA's driver: the dGPU is powered off only when nothing holds it, and
  an unfinished switch is never repeated.

### Known issues

- Under heavy Vulkan stress tests, the RTX 5070 Ti Laptop GPU (GB205) can still hit driver errors.
- Apps on the RTX take longer to start than apps on the Radeon, because the GPU wakes from its deepest power state
  first.
- The images use AOSP's public test keys and report an unlocked (orange) verified-boot state.

## [0.1.0-preview.2] - 2026-10-31

### Security

- adb asks before it lets a computer in (`ro.adb.secure=1`). preview.1 let any computer on the same network open a
  root shell over adb without asking. Releases now check this from the image itself and refuse an image without it.

## 0.1.0-preview.1 - 2026-10-31 [withdrawn]

The first public build. It was withdrawn about 12 minutes after publication because of the adb issue that
preview.2 fixes. It added the live USB stick and its installer, NVIDIA's open kernel driver with its GSP firmware
(under NVIDIA's distribution terms), and the GPL/LGPL source bundle.

[0.1.0-preview.3]: https://github.com/Mhsbrian/openbook-releases/releases/tag/v0.1.0-preview.3
[0.1.0-preview.2]: https://github.com/Mhsbrian/openbook-releases/releases/tag/v0.1.0-preview.2
