Medians over rounds; times in ms. HWUI columns are SystemUI's `dumpsys gfxinfo` (Settings' for the scroll). SF columns are SurfaceFlinger TimeStats over the same cycles: RE = RenderEngine time per GPU-composed frame (p90 = histogram bucket); blur radius = the largest `backgroundBlurRadius` behind the open panel.

| Scenario | Blur | Rounds | frames | janky % | p50 | p90 | GPU p50 | GPU p90 | SF frames | SF missed % | SF frame avg | RE avg | RE p90 | blur radius |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| shade | on | 3 | 1615 | 6.5 | 11 | 20 | 1 | 1 | 1562 | 0.3 | 4.9 | 4.6 | 7 | 34 |
| shade | off | 3 | 1633 | 6.5 | 11 | 18 | 1 | 1 | 1658 | 0.1 | 4.0 | 0 | 5 | 0 |
| shade | on − off | | -18 | -0.0 | 0 | +2 | 0 | 0 | -96 | +0.2 | +0.9 | +4.6 | +2 | +34 |
| qs | on | 3 | 1545 | 7.0 | 9 | 24 | 1 | 1 | 1814 | 0.1 | 4.6 | 4.5 | 6 | 34 |
| qs | off | 3 | 1521 | 12.2 | 12 | 31 | 1 | 1 | 1828 | 0 | 3.9 | 0 | – | 0 |
| qs | on − off | | +24 | -5.2 | -3 | -7 | 0 | 0 | -14 | +0.1 | +0.7 | +4.5 | – | +34 |
| settings-scroll | on | 2 | 759.5 | 3.9 | 12.5 | 22 | 1 | 1 | – | – | – | – | – | – |
| settings-scroll | off | 3 | 716 | 0.3 | 7 | 11 | 1 | 1 | – | – | – | – | – | – |
| settings-scroll | on − off | | +43.5 | +3.6 | +5.5 | +11 | 0 | 0 | – | – | – | – | – | – |

Per pair of adjacent rounds (host load: blur-bench.sh's readings at each round's start and end, Cuttlefish only):

| Scenario | Rounds (on, off) | Host load | janky % on / off | p90 ms on / off | SF missed % on / off | SF frame avg ms on / off | RE avg ms (on) |
|---|---|---|---|---|---|---|---|
| shade | r1, r2 | 24–54 | 6.5 / 2.4 | 20 / 13 | 0.3 / 0.1 | 4.9 / 3.7 | 4.6 |
| shade | r3, r4 | 14–59 | 5.9 / 9.9 | 20 / 28 | 0.3 / 0.2 | 4.7 / 4.2 | 4.4 |
| shade | r5, r6 | 61–70 | 10.3 / 6.5 | 29 / 18 | 0.3 / 0.1 | 5.4 / 4.0 | 5.2 |
| qs | r1, r2 | 24–54 | 6.5 / 1.6 | 24 / 9 | 0 / 0 | 4.6 / 2.5 | 4.5 |
| qs | r3, r4 | 14–59 | 7.0 / 12.2 | 22 / 31 | 0.1 / 0.1 | 3.9 / 3.9 | 3.8 |
| qs | r5, r6 | 61–70 | 16.5 / 12.5 | 36 / 32 | 0.2 / 0 | 5.4 / 4.2 | 5.2 |
| settings-scroll | r3, r4 | 14–59 | 5.1 / 2.4 | 26 / 14 | – / – | – / – | – |
| settings-scroll | r5, r6 | 61–70 | 2.7 / 0.3 | 18 / 11 | – / – | – / – | – |

Verdicts (G14 thresholds):

- **blur_applied: FAIL.** shade/on: 1 blurred layer(s), radius up to 34; qs/on: 1 blurred layer(s), radius up to 34; shade/off: 1 blurred layer(s), radius up to 34; qs/off: 0 blurred layer(s), radius up to 0; SystemUI supportsBlursOnWindows with blur on: true, true, true
- **no_gpu_hang: PASS.** no amdgpu fault/reset line, no restart in any round
- **frame_cost: PASS.** shade: SystemUI janky % (on) = 6.5 <= 10.0; shade: SystemUI janky % on − off (paired) = 3.9 <= 5.0; shade: SF missed % on − off (paired) = 0.2 <= 2.0; shade: RenderEngine avg ms (on) = 4.6 <= 6.0; shade: RenderEngine p90 bucket ms (on) = 7 <= 8; qs: SystemUI janky % (on) = 7.0 <= 10.0; qs: SystemUI janky % on − off (paired) = 4.0 <= 5.0; qs: SF missed % on − off (paired) = 0.1 <= 2.0; qs: RenderEngine avg ms (on) = 4.5 <= 6.0; qs: RenderEngine p90 bucket ms (on) = 6 <= 8
