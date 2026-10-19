# G14 touchpad behavior (ANAL-226)

## Device facts, 2026-10-19

The installed G14 now runs `20261019.photos1`, slot A, from integration tree
`d3e04fd` (the package manifest). Any next image must start from that tree,
preserving its Quire and Photos fixes; the issue's older `quire2` baseline is
outdated. This investigation made no laptop setting change and no image update.

Read-only `settings get system touchpad_tap_dragging` returned **1**.
`dumpsys input` independently reported **Tap Drag Enable: true**, **Tap Enable:
true**, **Tap Drag Lock Enable: false**. The hypothesis that tap dragging is
simply disabled does not explain a failure in this current state. AOSP's
fallback for an unset preference is still 0; that is a separate default-policy
question, not a demonstrated fix for this report.

`getevent -lp` confirms ELAN `04f3:3315`, five slots, X 0–3905, Y 0–2382,
31 units/mm on both axes. It reports `ABS_MT_TOOL_TYPE`, but no pressure or
contact-size axes. Android passes `reports_pressure=false` to gestures.
The bundled library explicitly bypasses minimum tap-pressure checks for these
devices. Copying ChromeOS Flex's pressure threshold cannot address that path.

## Reference sources checked 2026-10-19

- [libinput tapping documentation](https://wayland.freedesktop.org/libinput/doc/latest/tapping.html):
  tap dragging is normally enabled when tapping is enabled.
- [libinput tap state machine](https://gitlab.freedesktop.org/libinput/libinput/-/blob/main/src/evdev-mt-touchpad-tap.c):
  tap timeout 180 ms, and after a one-finger tap release another 180 ms to
  begin dragging (160 ms + 20 ms per finger). These are different transitions.
- [ChromeOS ELAN configuration](https://chromium.googlesource.com/chromiumos/platform/xorg-conf/+/refs/heads/main/50-touchpad-cmt-elan.conf):
  17 ms input queue delay, vertical close-distance threshold 35. It also
  overrides resolution to 33, which would contradict this device's measured
  31. It is not a drop-in configuration for every ELAN pad.
- [ChromeOS Flex/reven configuration](https://chromium.googlesource.com/chromiumos/platform/xorg-conf/+/refs/heads/main/50-touchpad-cmt-reven.conf):
  minimum tap pressure 1. The pressure-less exception above already applies.
- [ChromeOS zork configuration](https://chromium.googlesource.com/chromiumos/platform/xorg-conf/+/refs/heads/main/50-touchpad-cmt-zork.conf):
  device-specific overrides match different ELAN product IDs, not `3315`.
- [AOSP InputSettings](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/core/java/android/hardware/input/InputSettings.java)
  and [TouchpadInputMapper](https://android.googlesource.com/platform/frameworks/native/+/refs/heads/main/services/inputflinger/reader/mapper/TouchpadInputMapper.cpp):
  the Settings preference overrides any IDC `Tap Drag Enable` value.

The actual library tested is AOSP `external/libchrome-gestures` at
`6c2310952338e9f094a1aeb6a83f7356ff5d6042`, from the local build tree. Its tap
state machine lives in `src/immediate_interpreter.cc`; newer Chromium sources
have moved that code. Local source and the device dump agree on a 200 ms tap
timeout and 150 ms inter-tap timeout. A timing difference is a hypothesis to
test, not proof of the owner's failure.

## Capture and offline replay

Build outside the repository and outside the shared AOSP tree. Requires C++20
clang, make, pkg-config, jsoncpp and gtest headers. No root, VM, AOSP build
lane, `/dev/uinput`, or laptop writes are needed.

```bash
bash scripts/power/touchpad/build-replay.sh \
  "$HOME/anybook/aosp/src/external/libchrome-gestures" "$HOME/anybook/power/touchpad-replay"
python3 scripts/power/touchpad/replay-test.py \
  "$HOME/anybook/power/touchpad-replay/gesture-replay" -v
```

Use the existing private adb server, discover the touchpad node from
`getevent -lp`, and record **only that node**. On this boot it was `event13`;
never assume the number survives a reboot. A 45-second capture is bounded:

```bash
adb -P 5222 -s 192.168.50.11:5555 shell \
  'timeout 45 getevent -lt /dev/input/event13' > touchpad-private.txt
python3 scripts/power/touchpad/getevent-to-frames.py touchpad-private.txt frames.json
"$HOME/anybook/power/touchpad-replay/gesture-replay" frames.json > gestures.json
```

`timeout` may return 124 when its recording completes normally. Keep raw traces
private. Do not record the keyboard. Before starting the test motions, touch
then release once: the converter discards any partially observed contact and
synchronizes at the first complete release. It preserves MSC timestamps on
frames without one, as the existing palm lift-off patch does. Lost events
(`SYN_DROPPED`), an incomplete capture, and unexpected formats fail explicitly.

The replay uses the real library, its timer callbacks, and the G14's measured
hardware capabilities. Tap and drag are on, drag lock off. It uses the library's
default acceleration curves, not Android's custom curves. It excludes Android
event dispatch, apps, keyboard suppression notifications, and kernel/HID
processing. Pointer distances and app behavior are **not** full-system results.
This is a classifier diagnostic, not a replacement for the UHID/QEMU or
libinput tests. The JSON `properties` object can override individual library
properties for controlled experiments; no such override ships to the device.

## Results and remaining gate

The 45-second passive capture yielded 6,439 synchronized frames over 44.733 s:
52 empty, 5,931 one-contact and 456 two-contact frames; 142 frames contain a
kernel-marked palm. There were 690 physical-button frames. It contains no
three-finger contact and no labeled failing tap-drag or scroll attempt.
Two-contact kernel reports cannot be called false positives without knowing
what the person was doing. Do not interpret `BTN_TOOL_DOUBLETAP` as a click:
it describes the number of contacts; the gesture library decides the click.

Eight automated checks pass: parser handling of palms and missing timestamps,
rejection of lost events and incomplete captures, tap-to-click, tap-drag on/off,
scroll starts with contacts arriving together/49 ms/98 ms apart, palm suppression,
and three-finger swipe. These are **synthetic harness controls**, not evidence
that the reported physical failures are fixed. The current library can produce
a held button for a valid tap-drag sequence without a patch.

Still required before choosing a fix:

1. A labeled physical capture while the owner reproduces the failure, with
   a tap, tap-then-hold-and-move, single-finger motion, simultaneous and
   staggered two-finger scroll, tap becoming scroll, palm, and three-finger swipe.
2. Replay those same motions through libinput and Android/UHID. libinput source
   review is complete; **libinput runtime comparison has not run**.
3. Change only behavior where the comparison shows an improvement. Then build
   from the installed image tree, run the required QEMU OTA/recovery rehearsal,
   and update the G14 under the existing authorization. No candidate image was
   built or staged by this investigation because no fix is yet established.
4. Capture before/after on the laptop and obtain the owner's feel comparison.

Evidence: `evidence/2026-10-19-touchpad-behavior/`. The raw input dump includes
window metadata and remains private; the committed summary contains counts and
touchpad configuration only.
