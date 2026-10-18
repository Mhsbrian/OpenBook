Medians over rounds; times in ms. HWUI columns are SystemUI's `dumpsys gfxinfo` (Settings' for the scroll). SF columns are SurfaceFlinger TimeStats over the same cycles: RE = RenderEngine time per GPU-composed frame (p90 = histogram bucket); blur radius = the largest `backgroundBlurRadius` behind the open panel.

| Scenario | Blur | Rounds | frames | janky % | p50 | p90 | GPU p50 | GPU p90 | SF frames | SF missed % | SF frame avg | RE avg | RE p90 | blur radius |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| shade | on | 1 | 239 | 11.7 | 14 | 25 | 1 | 1 | 308 | 0 | 5.4 | 5.2 | 7 | 34 |
| shade | off | 1 | 247 | 6.9 | 11 | 17 | 1 | 1 | 286 | 0 | 4.3 | 0 | – | 0 |
| shade | on − off | | -8 | +4.8 | +3 | +8 | 0 | 0 | +22 | 0 | +1.1 | +5.2 | – | +34 |
| qs | on | 1 | 228 | 4.4 | 12 | 20 | 1 | 1 | 181 | 0 | 5.3 | 4.8 | 6 | 34 |
| qs | off | 1 | 221 | 8.6 | 11 | 24 | 1 | 1 | 164 | 0 | 4.1 | 0 | – | 0 |
| qs | on − off | | +7 | -4.2 | +1 | -4 | 0 | 0 | +17 | 0 | +1.1 | +4.8 | – | +34 |

Verdicts (G14 thresholds):

- **blur_applied: PASS.** shade/on: 1 blurred layer(s), radius up to 34; qs/on: 1 blurred layer(s), radius up to 34; shade/off: 0 blurred layer(s), radius up to 0; qs/off: 0 blurred layer(s), radius up to 0; SystemUI supportsBlursOnWindows with blur on: true
- **no_gpu_hang: PASS.** no amdgpu fault/reset line, no restart in any round
- **frame_cost: FAIL.** shade: SystemUI janky % (on) = 11.7 > 10.0: FAIL; shade: SystemUI janky % on − off = 4.8 <= 5.0; shade: SF missed % on − off = 0 <= 2.0; shade: RenderEngine avg ms (on) = 5.2 <= 6.0; shade: RenderEngine p90 bucket ms (on) = 7 <= 8; qs: SystemUI janky % (on) = 4.4 <= 10.0; qs: SystemUI janky % on − off = -4.2 <= 5.0; qs: SF missed % on − off = 0 <= 2.0; qs: RenderEngine avg ms (on) = 4.8 <= 6.0; qs: RenderEngine p90 bucket ms (on) = 6 <= 8
