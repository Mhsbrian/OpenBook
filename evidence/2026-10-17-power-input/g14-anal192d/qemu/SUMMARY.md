# Touchpad frames without MSC_TIMESTAMP in QEMU (ANAL-178, 2026-10-18)

`scripts/power/touchpad/touchpad-qemu.sh` with `TP_MODE`: the G14's ELAN descriptor on uhid, four 2 s one-finger strokes.
- `plain`: normal lift-offs.
- `palm`: each stroke lifts with confidence 0, so hid-multitouch adds a lift-off frame without MSC_TIMESTAMP.
- `sticky`: reports pause for 150 ms mid-stroke, so the kernel's sticky-fingers timer releases the contact in a frame without MSC_TIMESTAMP.

Images:
- `openbook-live-20261018-anal192d`: the owner's stick image, with the EventHub patch `0001`.
- `openbook-live-20261018-anal178-converter-test`: `0001` plus `0002` (HardwareStateConverter keeps the last MSC_TIMESTAMP). The G14 product was built from `anal-178/anal192d` (`2b1371f`) under the lane lock (`build-20261018T145220Z`: `frameworks/native: base ae266dcb706d + 2 patches`). Test image only.

| Image | Mode | Frames / with MSC | "Clock changed backwards" |
|---|---|---|---|
| anal192d (0001 only) | plain | 2008 / 2008 | 0 |
| anal192d (0001 only) | palm | 2012 / 2008 | 4 |
| anal192d (0001 only) | sticky | 2012 / 2008 | 0 |
| 0001 + 0002 | plain | 2008 / 2008 | 0 |
| 0001 + 0002 | palm, 3 runs | 2012 / 2008 | 1, 1, 0 (`converter-palm` is the second run, `converter2-palm` the third) |
| 0001 + 0002 | sticky | 2012 / 2008 | 0 |

In the patched palm runs, each single error came at device open, not at a lift-off: in the second run at uptime 65.8 s, 2.9 s before the first stroke at 68.7 s. The plain runs on the same image had none (2 runs). It is not a palm frame. HYPOTHESIS: EventHub sends `EVIOCSREP` before `EVIOCSCLOCKID`, so the kernel's `EV_REP` notice carries the default (realtime) clock.

Unit tests (host `inputflinger_tests`, same build): `HardwareStateConverterTest.*`, 7/7, including the new `MscTimestampKeptForFramesWithoutOne` (`inputflinger-tests-HardwareStateConverter.txt`).
