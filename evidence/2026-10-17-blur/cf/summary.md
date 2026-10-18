Medians over rounds; times in ms. HWUI columns are SystemUI's `dumpsys gfxinfo` (Settings' for the scroll). SF columns are SurfaceFlinger TimeStats over the same cycles: RE = RenderEngine time per GPU-composed frame (p90 = histogram bucket); blur radius = the largest `backgroundBlurRadius` behind the open panel.

| Scenario | Blur | Rounds | frames | janky % | p50 | p90 | GPU p50 | GPU p90 | SF frames | SF missed % | SF frame avg | RE avg | RE p90 | blur radius |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| shade | on | 3 | 1577 | 11.9 | 13 | 31 | 1 | 1 | 1655 | 0.9 | 5.9 | 6.0 | 10 | 34 |
| shade | off | 3 | 1599 | 8.1 | 12 | 25 | 1 | 1 | 1645 | 0 | 4.0 | 0 | – | 0 |
| shade | on − off | | -22 | +3.7 | +1 | +6 | 0 | 0 | +10 | +0.9 | +2.0 | +6.0 | – | +34 |
| qs | on | 3 | 1491 | 11.1 | 11 | 32 | 1 | 1 | 1797 | 0.2 | 4.5 | 4.4 | 6 | 34 |
| qs | off | 3 | 1578 | 12.2 | 12 | 32 | 1 | 1 | 1782 | 0 | 4.0 | 0 | – | 0 |
| qs | on − off | | -87 | -1.1 | -1 | 0 | 0 | 0 | +15 | +0.2 | +0.5 | +4.4 | – | +34 |
| settings-scroll | on | 3 | 738 | 2.7 | 11 | 18 | 1 | 1 | – | – | – | – | – | – |
| settings-scroll | off | 2 | 740 | 5.1 | 16.5 | 27.5 | 1 | 1 | – | – | – | – | – | – |
| settings-scroll | on − off | | -2 | -2.3 | -5.5 | -9.5 | 0 | 0 | – | – | – | – | – | – |

Per pair of adjacent rounds (host load: blur-bench.sh's readings at each round's start and end, Cuttlefish only):

| Scenario | Rounds (on, off) | Host load | janky % on / off | p90 ms on / off | SF missed % on / off | SF frame avg ms on / off | RE avg ms (on) |
|---|---|---|---|---|---|---|---|
| shade | r1, r2 | 14–27 | 3.6 / 4.6 | 16 / 19 | 0 / 0.3 | 4.2 / 3.3 | 4.0 |
| shade | r3, r4 | 27–85 | 11.9 / 10.1 | 31 / 26 | 0.9 / 0 | 5.9 / 4.0 | 6.0 |
| shade | r5, r6 | 85–92 | 16.9 / 8.1 | 40 / 25 | 1.3 / 0 | 6.3 / 4.2 | 6.1 |
| qs | r1, r2 | 14–27 | 0.8 / 0.9 | 8 / 8 | 0 / 0 | 2.7 / 2.2 | 2.8 |
| qs | r3, r4 | 27–85 | 11.1 / 12.5 | 32 / 32 | 0.2 / 0 | 4.5 / 4.0 | 4.4 |
| qs | r5, r6 | 85–92 | 19.2 / 12.2 | 46 / 32 | 0.2 / 0 | 5.5 / 4.3 | 5.4 |
| settings-scroll | r1, r2 | 14–27 | 0.7 / 0.5 | 11 / 21 | – / – | – / – | – |
| settings-scroll | r3, r4 | 27–85 | 2.7 / 9.6 | 18 / 34 | – / – | – / – | – |

Verdicts (G14 thresholds):

- **blur_applied: PASS.** shade/on: 1 blurred layer(s), radius up to 34; qs/on: 1 blurred layer(s), radius up to 34; shade/off: 0 blurred layer(s), radius up to 0; qs/off: 0 blurred layer(s), radius up to 0; SystemUI supportsBlursOnWindows with blur on: true, true, true
- **no_gpu_hang: PASS.** no amdgpu fault/reset line, no restart in any round
- **frame_cost: FAIL.** shade: SystemUI janky % (on) = 11.9 > 10.0: FAIL; shade: SystemUI janky % on − off (paired) = 1.8 <= 5.0; shade: SF missed % on − off (paired) = 0.9 <= 2.0; shade: RenderEngine avg ms (on) = 6.0 <= 6.0; shade: RenderEngine p90 bucket ms (on) = 10 > 8: FAIL; qs: SystemUI janky % (on) = 11.1 > 10.0: FAIL; qs: SystemUI janky % on − off (paired) = -0.1 <= 5.0; qs: SF missed % on − off (paired) = 0.2 <= 2.0; qs: RenderEngine avg ms (on) = 4.4 <= 6.0; qs: RenderEngine p90 bucket ms (on) = 6 <= 8
