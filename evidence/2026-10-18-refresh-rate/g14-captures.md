# The refresh_rate verdict on the G14 captures already in the repo (before ANAL-212)

`scripts/installer/live-report.py`'s `refresh_rate` (ANAL-212), run on each session's `collect-final.txt` (its `SF` section, `dumpsys SurfaceFlinger | head -n 250`).

| Session | Verdict | Active mode | Primary render max | Render rate at capture | Seconds by render rate |
|---|---|---|---|---|---|
| `2026-10-16 installer g14-live` | yes | 2880x1800 at 120.0 Hz | none | 120.0 Hz | {"120.00": 587.0} |
| `g14-anal176s` | NO | 2880x1800 at 120.0 Hz | 60.0 | 60.0 Hz | {"120.00": 5.9, "60.00": 76.0, "24.00": 2.4, "30.00": 2.1} |
| `g14-anal178c` | NO | 2880x1800 at 120.0 Hz | 60.0 | 120.0 Hz | {"120.00": 28.2, "60.00": 25.6} |
| `g14-desktop2` | NO | 2880x1800 at 120.0 Hz | 60.0 | 60.0 Hz | {"120.00": 11.5, "60.00": 49.9} |
| `g14-desktop3` | NO | 2880x1800 at 120.0 Hz | 60.0 | 60.0 Hz | {"120.00": 12.9, "60.00": 53.2} |

The 2026-10-16 session was captured before DisplayManager had sent SurfaceFlinger a policy (`mDisplayModeSpecsInvalid=true` in its `dumpsys display`), so SurfaceFlinger still had its own unbounded default.
