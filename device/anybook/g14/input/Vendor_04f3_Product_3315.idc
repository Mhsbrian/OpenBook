# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# ELAN touchpad of the ROG Zephyrus G14 2025 (GA403WR): I2C HID "ASCE1206:00 04F3:3315" on AMDI0010
# (evidence/2026-10-16-ga403wr-inventory/input-devices.txt).

# Internal: no aggressive wake, and with the built-in keyboard it puts the panel into desktop mode.
device.internal = 1
touch.deviceType = touchPad

# Gesture tuning (gestureProp.*, pressure calibration, palm rejection) waits for measurements on the laptop
# (ANAL-178); until then the touchpad stack's defaults apply.
