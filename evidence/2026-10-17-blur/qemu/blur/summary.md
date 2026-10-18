Medians over rounds; times in ms. HWUI columns are SystemUI's `dumpsys gfxinfo` (Settings' for the scroll). SF columns are SurfaceFlinger TimeStats over the same cycles: RE = RenderEngine time per GPU-composed frame (p90 = histogram bucket); blur radius = the largest `backgroundBlurRadius` behind the open panel.

| Scenario | Blur | Rounds | frames | janky % | p50 | p90 | GPU p50 | GPU p90 | SF frames | SF missed % | SF frame avg | RE avg | RE p90 | blur radius |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| shade | on | 1 | 192 | 60.4 | 65 | 150 | 1 | 1 | 254 | 21.6 | 22.8 | 21.7 | 34 | 34 |
| shade | off | 1 | 219 | 48.9 | 53 | 109 | 1 | 1 | 330 | 2.4 | 16.2 | 13.8 | 20 | 0 |
| shade | on − off | | -27 | +11.6 | +12 | +41 | 0 | 0 | -76 | +19.2 | +6.5 | +7.8 | +14 | +34 |
| qs | on | 1 | 155 | 76.1 | 93 | 150 | 1 | 1 | 259 | 18.1 | 21.0 | 19.6 | 32 | 34 |
| qs | off | 1 | 186 | 56.5 | 61 | 113 | 1 | 1 | 273 | 1.5 | 15.5 | 12.3 | 16 | 0 |
| qs | on − off | | -31 | +19.7 | +32 | +37 | 0 | 0 | -14 | +16.7 | +5.5 | +7.3 | +16 | +34 |

Per pair of adjacent rounds (host load: blur-bench.sh's readings at each round's start and end, Cuttlefish only):

| Scenario | Rounds (on, off) | Host load | janky % on / off | p90 ms on / off | SF missed % on / off | SF frame avg ms on / off | RE avg ms (on) |
|---|---|---|---|---|---|---|---|
| shade | r1, r2 | – | 60.4 / 48.9 | 150 / 109 | 21.6 / 2.4 | 22.8 / 16.2 | 21.7 |
| qs | r1, r2 | – | 76.1 / 56.5 | 150 / 113 | 18.1 / 1.5 | 21.0 / 15.5 | 19.6 |

Verdicts (G14 thresholds):

- **blur_applied: PASS.** shade/on: 1 blurred layer(s), radius up to 34; qs/on: 1 blurred layer(s), radius up to 34; shade/off: 0 blurred layer(s), radius up to 0; qs/off: 0 blurred layer(s), radius up to 0; SystemUI supportsBlursOnWindows with blur on: true
- **no_gpu_hang: PASS.** no amdgpu fault/reset line, no restart in any round
- **frame_cost: FAIL.** shade: SystemUI janky % (on) = 60.4 > 10.0: FAIL; shade: SystemUI janky % on − off (paired) = 11.6 > 5.0: FAIL; shade: SF missed % on − off (paired) = 19.2 > 2.0: FAIL; shade: RenderEngine avg ms (on) = 21.7 > 6.0: FAIL; shade: RenderEngine p90 bucket ms (on) = 34 > 8: FAIL; qs: SystemUI janky % (on) = 76.1 > 10.0: FAIL; qs: SystemUI janky % on − off (paired) = 19.7 > 5.0: FAIL; qs: SF missed % on − off (paired) = 16.7 > 2.0: FAIL; qs: RenderEngine avg ms (on) = 19.6 > 6.0: FAIL; qs: RenderEngine p90 bucket ms (on) = 32 > 8: FAIL
