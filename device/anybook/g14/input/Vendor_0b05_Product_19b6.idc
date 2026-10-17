# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# ASUS N-KEY keyboard of the ROG Zephyrus G14 2025 (GA403WR): USB 0b05:19b6, "ITE Tech. Inc. ITE Device(8910)"
# (evidence/2026-10-16-ga403wr-inventory/input-devices.txt). It sits on USB but is the laptop's own keyboard.

# Built in: the default keyboard (id 0), and with the internal touchpad it puts the panel into desktop mode.
keyboard.builtIn = 1
device.internal = 1

# The keyboard backlight (asus::kbd_backlight) is a child of this HID device (G14 live boot, ANAL-190 live-001),
# so InputReader finds it by itself; device.additionalSysfsLedsNode would register it a second time.
