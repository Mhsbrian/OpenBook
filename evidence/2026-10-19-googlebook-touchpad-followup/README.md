# Ruby touchpad follow-up (ANAL-228)

The owner reports unwanted item activation during two-finger scrolling, perhaps
limited to Settings, with tapping disabled. The Play Store report is withdrawn:
the owner had disabled it intentionally. No package, account, security setting,
input setting or physical image was changed during this investigation.

## Confirmed static compatibility gaps

Read-only inspection of the retained Ruby `system/lib64/libinputflinger.so`,
SHA-256 `e27014ec1e2e4d611cdd6df2c1175d86d679d1353ee970f190e831953fbcb3e4`,
confirms that neither of OpenBook's two input fixes is present. This system
payload was unchanged by the vendor-only services21 update.

- `EventHub::Device::configureFd`, symbol address `0x1cd0e0`: the condition at
  `0x1cd101` tests class bit `0x1` before the `EVIOCSREP` call. It excludes
  touchpad bit `0x10000`. OpenBook patch `frameworks/native/0001` includes both.
- `HardwareStateConverter::processRawEvent`, symbol address `0x24cad0`: after
  producing a state and finishing sync, it clears the timestamp member at
  offset `0x40` (`0x24cb58`). The same member receives `MSC_TIMESTAMP` at
  `0x24cb76`. OpenBook patch `frameworks/native/0002` preserves this member
  across sync and only resets it at an explicit device reset/timestamp event.

Reproduce locally with `nm -D -C` and bounded `objdump -d -C --start-address`
and `--stop-address` on the locally licensed image. No binary, disassembly
dump or proprietary image is redistributed here. The earlier Ruby dump
classifies this touchpad as TOUCH | TOUCH_MT | TOUCHPAD, without KEYBOARD;
it contains 253 backward-clock warnings and 270 spurious callbacks.
These counts belong to the **pre-update capture**, not a new live test.

This is a real difference from patched OpenBook. It does not establish that
repeat frames are currently generated or that they cause the owner's clicks.
The effective repeat configuration, active-user tap setting, raw motion and
application dispatch remain unobserved on this boot.

## Diagnostic correction and controls

The converter previously always preserved MSC, silently modeling patched
OpenBook when fed a Ruby trace. It now offers explicit `--msc-policy
reset-on-sync` and effective `--tap-to-click` / `--tap-dragging` settings. It
retains all frames and original event-time differences; no device changes or
timestamp smoothing are performed.

Eleven replay checks pass with the isolated AOSP gestures build at
`6c2310952338e9f094a1aeb6a83f7356ff5d6042`. A synthetic two-finger scroll with
MSC-less frames every ~41 ms produces **13 backward-clock warnings** with
reset-on-sync and **zero** with preserved MSC. Both produce scrolling and
**zero button-change gestures** with tapping off. This supports the clock-gap
diagnosis and explicitly does not reproduce unwanted clicks.

Seven capture privacy/failure checks also pass. The read-only collector now
includes kernel input-device capabilities and individual checks for the seven
restored desktop services. A successful `service check` command is not proof
of registration: inspect its `found` / `not found` result.

Source review on 2026-10-19: AOSP's
[UncapturedGestureConverter](https://android.googlesource.com/platform/frameworks/native/+/refs/heads/main/services/inputflinger/reader/mapper/gestures/UncapturedGestureConverter.cpp)
converts scrolling into DOWN/MOVE/UP events classified TWO_FINGER_SWIPE,
separately from button-change gestures. Consequently an offline gestures-only
test cannot rule out application dispatch behavior. This source is a diagnostic
reference, not a claim that Ruby is the identical revision. Read locally at
`frameworks/native/services/inputflinger/reader/mapper/gestures/` after the web
viewer could not render the source.

## Live access and next observation

The authorized G14 address responds to ping, but its previous TLS port refuses
connections. No G14 mDNS record or connected ADB transport was found. A bounded
TCP check of that address alone found three open high ports; none completed an
ADB handshake. Those trial offline transports were disconnected. No unrelated
device was accessed and no new live diagnostics were obtained.

Resume with the current **IP address & Port** on the main Wireless debugging
screen, keeping the laptop awake. The saved pairing may still work; do not ask
for a new code unless authentication actually requires it. See the official
[ADB connection guide](https://developer.android.com/tools/adb#connect-to-a-device-over-wi-fi).

Once connected:

1. Verify the Ruby live identity and collect current-user preferences, effective
   mapper state, mmd/swap, desktop services, watchdog history and Wi-Fi/audio.
2. Discover the ELAN touchpad and companion mouse nodes. Record only touchpad
   motion (never keyboards), with a labeled Settings reproduction and the same
   motion in a second app. Keep raw traces private and preserve access denials.
3. Check raw repeats/buttons and MSC-less frames, then compare converted
   gestures with dispatched event classification. Confirm a correction on the
   actual failing path before building another preserving update.

Physical zram/service validation, speaker audibility and watchdog stability
remain pending; installation remains gated. ADB access is the current blocker.
