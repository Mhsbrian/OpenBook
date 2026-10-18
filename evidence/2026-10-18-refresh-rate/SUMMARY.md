# Refresh rate: the 60 fps cap and its fix (ANAL-212), 2026-10-18

Details: `docs/graphics-amd.md`, "Refresh rate on the G14's 120 Hz panel".

## G14, before (existing captures)

`g14-captures.md`: on every enforcing desktop session (`anal176s`, `anal178c`, `desktop2`, `desktop3`):
- the panel ran 2880x1800 at 120 Hz;
- DisplayManager's primary render range was [0, 60];
- SurfaceFlinger spent most of its time drawing at 60 (`anal176s`: 76.0 s at 60, 5.9 s at 120).

## Static check of the RRO

`overlay-check.txt`: `aapt2` links `AnyBookDesktopFrameworkOverlay` against the G14 product's `framework-res.apk`.
`idmap2` (public and product policies, overlayable checks on) maps `config_defaultRefreshRate` → 0 and
`config_defaultPeakRefreshRate` → 1000. The framework's own values are 60 and 0.

## QEMU, same harness, before and after

`scripts/graphics/refresh-qemu.sh IMG RUN`. Each run is one boot of the G14 live image on its serial-console entry, with
virtio-vga at 1920x1200, KVM, 6 vCPUs and SwiftShader. QEMU's display runs one 75 Hz mode. While Settings scrolls under
12 `input swipe`s, the harness samples SurfaceFlinger's render rate 12 times.

| | `qemu-before/` | `qemu-after/` |
|---|---|---|
| Image | `openbook-live-20261018-anal211b` (main before this change) | `openbook-live-20261018-anal212` (this branch, `7c7f7fa` + the change; build 29 min, m exit 0) |
| `config_defaultRefreshRate`, `config_defaultPeakRefreshRate` (`cmd overlay lookup`) | 60, 0 | **0, 1000** |
| DisplayModeDirector | `mDefaultRefreshRate: 60.0`; `PRIORITY_DEFAULT_REFRESH_RATE -> RenderVote [0, 60]` | `mDefaultRefreshRate: 0.0`, no default vote; peak votes [0, 1000] |
| SurfaceFlinger `displayManagerPolicy` | primary `render=[0, 60]` | primary `render=[0, 1000]` |
| Render rate while scrolling (12 samples) | **37.5 Hz × 12** | **75 Hz × 12** |
| Seconds by render rate, boot to the end | 75 Hz: 25.1, 37.5 Hz: 66.2 | 75 Hz: 81.8 |
| Battery saver (`low_power`) | 0 | 0 |
| Verdicts (`refresh.md`) | config NO, policy NO, scroll NO | config yes, policy yes, scroll yes |

The "before" run was made twice, once swiping a pane that does not scroll and once swiping the list. Both gave
12 × 37.5 Hz. Only the list run is kept.

After the change, SurfaceFlinger stayed at 75 the whole time, with no lower render rate when idle. Two reasons: no
idle timer is set (Googlebook sets 1000 ms; deferred, see the doc), and nothing in the VM voted lower.

## Not shown here

- **The G14 itself:** next stick. The new `refresh_rate` verdict in `live-report.py` reads it from the "save logs"
  capture.
- **Power on battery.** Not measured.
