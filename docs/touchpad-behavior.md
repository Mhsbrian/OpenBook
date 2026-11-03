# G14 touchpad behavior (ANAL-226)

How the G14's touchpad gestures (tap, tap-drag, scroll, palms, swipes) behave on OpenBook, how to capture and replay
them offline through the real gesture library, and what is still needed before changing any of it. The driver side
and the "Clock changed backwards" fix are in `docs/power-input.md` §2.

**State (as of 2026-10-19):** the owner reported tap-drag and scroll failures. They are not yet reproduced with a
labeled capture, so no fix is chosen and nothing is changed on the laptop.

## Device facts

- **Hardware** (`getevent -lp`): ELAN `04f3:3315`, five slots, X 0–3905, Y 0–2382, 31 units/mm on both axes. It
  reports `ABS_MT_TOOL_TYPE` (palms), but no pressure or contact-size axes.
- **No pressure.** Android passes `reports_pressure=false` to the gesture library, and the library bypasses its
  minimum tap-pressure checks for such devices. Copying ChromeOS Flex's pressure threshold therefore changes nothing.
- **Tap dragging is on.** `settings get system touchpad_tap_dragging` returns 1, and `dumpsys input` reports Tap
  Drag Enable: true, Tap Enable: true, Tap Drag Lock Enable: false. So "tap dragging is disabled" does not explain a
  failure. AOSP's fallback for an unset preference is still 0; that is a separate default-policy question.
- **The Settings preference wins.** AOSP's `InputSettings` and `TouchpadInputMapper` let it override any IDC
  `Tap Drag Enable` value.
- **Library timing.** The library is AOSP `external/libchrome-gestures` at
  `6c2310952338e9f094a1aeb6a83f7356ff5d6042`; its tap state machine is in `src/immediate_interpreter.cc` (newer
  Chromium sources have moved it). Source and the device dump agree on a 200 ms tap timeout and a 150 ms inter-tap
  timeout. A timing difference from other stacks is a hypothesis to test, not proof of the failure.

## Reference values (checked 2026-10-19)

- [libinput tapping documentation](https://wayland.freedesktop.org/libinput/doc/latest/tapping.html):
  tap dragging is normally enabled when tapping is enabled.
- [libinput tap state machine](https://gitlab.freedesktop.org/libinput/libinput/-/blob/main/src/evdev-mt-touchpad-tap.c):
  tap timeout 180 ms, and after a one-finger tap release another 180 ms to begin dragging (160 ms + 20 ms per
  finger). These are different transitions.
- [ChromeOS ELAN configuration](https://chromium.googlesource.com/chromiumos/platform/xorg-conf/+/refs/heads/main/50-touchpad-cmt-elan.conf):
  17 ms input queue delay, vertical close-distance threshold 35. It also overrides resolution to 33, which
  contradicts this device's measured 31, so it is not a drop-in configuration for every ELAN pad.
- [ChromeOS Flex/reven configuration](https://chromium.googlesource.com/chromiumos/platform/xorg-conf/+/refs/heads/main/50-touchpad-cmt-reven.conf):
  minimum tap pressure 1. The pressure-less exception above already applies.
- [ChromeOS zork configuration](https://chromium.googlesource.com/chromiumos/platform/xorg-conf/+/refs/heads/main/50-touchpad-cmt-zork.conf):
  its device-specific overrides match other ELAN product IDs, not `3315`.

## Capture and offline replay

**Build** outside the repository and outside the shared AOSP tree. It needs a C++20 clang, make, pkg-config, jsoncpp
and gtest headers; no root, VM, AOSP build lane, `/dev/uinput` or laptop writes.

```bash
bash scripts/power/touchpad/build-replay.sh \
  "$HOME/anybook/aosp/src/external/libchrome-gestures" "$HOME/anybook/power/touchpad-replay"
python3 scripts/power/touchpad/replay-test.py \
  "$HOME/anybook/power/touchpad-replay/gesture-replay" -v
```

**Capture** with the existing private adb server. Find the touchpad node in `getevent -lp` and record **only that
node**; its number can change across reboots (`eventNN` below). A 45-second capture is bounded:

```bash
adb -P 5222 -s "$OPENBOOK_G14_ADDR:5555" shell \
  'timeout 45 getevent -lt /dev/input/eventNN' > touchpad-private.txt
python3 scripts/power/touchpad/getevent-to-frames.py touchpad-private.txt frames.json
"$HOME/anybook/power/touchpad-replay/gesture-replay" frames.json > gestures.json
```

- `timeout` may return 124 when its recording completes normally.
- Keep raw traces private: a raw input dump includes window metadata. Do not record the keyboard.
- Before the test motions, touch then release once. The converter discards any partially observed contact and
  synchronizes at the first complete release.
- The converter keeps the last MSC timestamp for frames without one, as Android's palm lift-off patch does. Lost
  events (`SYN_DROPPED`), an incomplete capture and unexpected formats fail explicitly.
- Do not read `BTN_TOOL_DOUBLETAP` as a click: it gives the number of contacts, and the gesture library decides the
  click. Two-contact kernel reports cannot be called false positives without knowing what the person was doing.

**What the replay covers.** It runs the real library, its timer callbacks and the G14's measured hardware
capabilities, with tap and drag on and drag lock off. It uses the library's default acceleration curves, not
Android's custom curves. It leaves out Android event dispatch, apps, keyboard suppression notifications and
kernel/HID processing, so pointer distances and app behavior are **not** full-system results. It is a classifier
diagnostic, not a replacement for the UHID/QEMU or libinput tests. The JSON `properties` object can override
individual library properties for controlled experiments; no such override ships to the device.

## Tests

`replay-test.py` runs eight synthetic control checks, and they pass: parser handling of palms and missing
timestamps, rejection of lost events and incomplete captures, tap-to-click, tap-drag on and off, scroll starts with
contacts arriving together or 49 ms or 98 ms apart, palm suppression, and three-finger swipe. These control the
harness; they do not show that the reported physical failures are fixed. The current library produces a held
button for a valid tap-drag sequence without a patch.

A passive capture without labels cannot decide anything: the 45-second capture of 2026-10-19 had 5,931 one-contact
and 456 two-contact frames, 142 with a kernel-marked palm, and no labeled failing attempt.

## Before choosing a fix

1. A labeled physical capture while the owner reproduces the failure: a tap, tap-then-hold-and-move, single-finger
   motion, simultaneous and staggered two-finger scroll, tap becoming scroll, palm, and three-finger swipe.
2. Replay those same motions through libinput and Android/UHID. The libinput source review is done; **a libinput
   runtime comparison has not run**.
3. Change only behavior where the comparison shows an improvement. Then build from the installed image's tree, run
   the QEMU update and recovery rehearsal, and update the G14 with the owner's approval.
4. Capture before and after on the laptop, and get the owner's feel comparison.
