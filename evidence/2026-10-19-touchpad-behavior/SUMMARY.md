# ANAL-226: investigation, not a fixed touchpad

On 2026-10-19 the installed G14 was read over adb, without settings changes,
input injection, image writes, or a reboot. It runs `20261019.photos1` in slot A.
The package manifest names integration tree `d3e04fd`.

Tap dragging is already enabled in both Settings and the gesture mapper. The
earlier disabled-default explanation is insufficient for a failure now.
The touchpad exposes no pressure axis, and the bundled gestures implementation
bypasses minimum tap-pressure checks for it.

- `gesture-settings.txt`: allowlisted settings only, extracted from the live
  input dump. No app/window names, account data, or serial numbers.
- `results.json`: passive capture counts, source revision, test results and
  explicit outstanding checks. The raw capture's digest permits correlation
  with the private working copy; raw input and full dumps are not committed.
- `replay-tests.txt`: eight passing synthetic harness checks, including tap
  dragging on/off, staggered scroll, palm and three-finger swipe. These do not
  certify a physical fix.

Reproduction commands, primary-source references, and the remaining physical
capture, libinput comparison, QEMU and OTA gates are in
`docs/touchpad-behavior.md`. No candidate image has been built or staged because
there is no demonstrated behavioral fix yet.
