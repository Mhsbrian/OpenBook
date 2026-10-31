# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# ELAN touchpad of the ROG Zephyrus G14 2025 (GA403WR): I2C HID "ASCE1206:00 04F3:3315" on AMDI0010
# (evidence/2026-10-16-ga403wr-inventory/input-devices.txt).

# Internal: no aggressive wake, and with the built-in keyboard it puts the panel into desktop mode.
device.internal = 1

# On the G14 InputReader classes this device TOUCH | TOUCH_MT | TOUCHPAD (ANAL-190 live-001, dumpsys input), so
# Android 17 drives it with TouchpadInputMapper and the ChromeOS gestures library: tap to click, two-finger scroll
# and swipes, palm rejection. touch.deviceType is only read by the older TouchInputMapper; it stays as the setting
# for builds with the gestures library switched off.
touch.deviceType = touchPad

# Gesture tuning (gestureProp.* properties, read by TouchpadInputMapper from this file) waits for measurements on
# the laptop: the axis ranges and resolution (getevent -lp, in the live stick's "save logs" capture) and how taps,
# scrolls and palms feel (docs/power-input.md). Until then the gestures library's defaults apply.
