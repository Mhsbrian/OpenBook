# Boot time, anal178c vs anal176s, back to back (QEMU logs case, 2026-10-17 ~13:20Z)

The full matrix of anal176s read `boot_completed` at 28.8 s (first case) and 29.1 s (logs case). Every stage was about
twice as slow as in anal178c's own matrix, including the first stage (`second_stage_s` 3.5 s vs 2.7 s), which runs before
anything this branch changes. ANAL-191's installer-wizard VMs were running on the host at the same time. The same
logs case, run back to back for both images under the same load (load average about 7, ANAL-191's VMs still running):

| | anal178c (main at ea3c25e) | anal176s (+ PR #52) |
|---|---|---|
| `second_stage_s` | 2.6 | 2.6 |
| `boot_progress_start` | 5.9 s | 6.1 s |
| `boot_progress_enable_screen` | 10.7 s | 11.4 s |
| `boot_completed_s` | 17.6 | 17.8 |

No slowdown from the three fixes. Runs: `<data dir>/logs/installer/live-20261017-ab-anal178c`, `live-20261017-ab-anal176s`.

The same two runs, on the new check: anal178c fails "vold leaves the boot stick alone" (`disk:8,0` scanned, 10/11), anal176s passes it (`8:0` not managed, 11/11).
