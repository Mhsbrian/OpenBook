# G14 before the fix: the owner's `anal192d` session (2026-10-18)

- **Stick:** `openbook-live-20261018-anal192d` (`main` `81578c1` + #83). It still has AOSP's
  `config_defaultRefreshRate` of 60, because #88 came after it.
- **Session:** 11:00–12:10Z.
- **Source:** the build host's read-only copy, `~/anybook/installer/g14/stick-20261018T123221Z/`. The stick itself was
  not touched, and nothing was written into that copy.
- **Compare with:** `anal192e` (`main` + #88), using the same tools.

## SurfaceFlinger in the two captured boots (`collect-final.txt`, `dumpsys SurfaceFlinger`)

Source: `live-report.py`'s `refresh_rate` (#88).

| Boot | Uptime at capture | Active mode | Primary range | App-request range | Seconds by render rate | Missed frames: total / HWC / GPU |
|---|---|---|---|---|---|---|
| `live-001` "save logs" (enforcing off) | 124.6 s | 2880x1800 at 120 Hz | physical [0, inf], **render [0, 60]** | [0, inf], [0, inf] | 120 Hz: 4.1, **60 Hz: 84.2** | 1242 / 1182 / 797 |
| `live-002` "ARM apps check" | 619.2 s | 2880x1800 at 120 Hz | physical [0, inf], **render [0, 60]** | [0, inf], [0, inf] | 120 Hz: 4.1, **60 Hz: 580.5** | 1104 / 401 / 1020 |

- `refresh_rate`: NO in both boots.
- The render rate at capture was 60 Hz in both.
- Neither boot has an idle timer, and both have a 200 ms touch timer.

## The owner's default boot, from its persisted logcat (`live-001/prior/misc/logd`)

This boot has no dumpsys. Instead, `scripts/graphics/render-rate-timeline.py` adds up the time between the
render-rate changes that DisplayManager logs. Changes too brief to reach DisplayManager are missed, so 120 Hz is an
undercount: in the "save logs" boot, SurfaceFlinger counted 4.1 s at 120 that the log doesn't show.

| Boot | Log span | Screen on | 120 Hz | 60 Hz | 30 Hz | 120 Hz stretches |
|---|---|---|---|---|---|---|
| Default "OpenBook" boot | 11:00:33–11:59:43 (59.2 min) | 3520.8 s (never off) | 3.5 s (0.1 %) | **3509.1 s (99.7 %)** | 8.1 s (0.2 %) | 17, median 0.11 s, longest 1.3 s |

- 120 Hz came only from apps that asked for it explicitly. The panel's mode stayed at 120 Hz throughout: there is no
  mode-change line, and the active mode is 120 Hz in both captures.
- The last-started app at each 120 Hz stretch was Files, Chrome, the WebView shell, Aurora Store or the installer.

## What `anal192e` should show

- **Primary render range** [0, 1000] in both captures, and `refresh_rate` yes.
- **Most screen-on time at 120 Hz.** Some lower rates are expected wherever content asks for less (the frame-rate
  categories are `normal=60`, `high=90`).
- **Missed frames, per minute of uptime, against the table above.** At 120 Hz, SurfaceFlinger's GPU composition of
  the 2880x1800 frame (overlay planes off, blur on) has 8.3 ms instead of 16.7 ms. HYPOTHESIS: missed frames may rise.
  If they do, it's a frame-pacing problem to fix in its own right; it is not a reason to bring back the cap.

Reproduce:
```bash
S=~/anybook/installer/g14/stick-<ts>
python3 -I scripts/graphics/render-rate-timeline.py $S/live-001/prior/misc/logd
python3 -I -c 'import importlib.util as u,sys; s=u.spec_from_file_location("lr","scripts/installer/live-report.py"); m=u.module_from_spec(s); s.loader.exec_module(m); print(m.refresh_rate(m.sections(sys.argv[1]+"/collect-final.txt").get("SF","")))' $S/live-001
```
