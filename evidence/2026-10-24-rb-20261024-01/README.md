# RB-20261024-01 (R1): built and rehearsed; stopped before the G14 install (ANAL-258, 2026-10-24)

Plan v1 is `d09795d1ad9eda6390d4daa6076ac1423dfcd32454b3e9dcb50b7900aed082f7`. B Honey approved it on ANAL-232 (`01a16e60…`), together with the install **if every test passed**. One after-update check did not pass, so **nothing was written to the G14 or the stick.**

## Built

The source's R1 chain (`rb04-build.sh`), run under the Ruby track lock:
1. `build-safety-candidate.py` on `75fa0196…`: candidate `ea069689…`.
2. `build-update-app-candidate.py --adapter` (APK `cd2c896e…`, adapter `b80879f2…`): candidate `93fa63e6…`.
3. The release directory is the candidate's `system` plus RB-20261023-03's other nine images.
4. `embed-adapter-layer.sh` with Google 16658739.

The release images equal the plan's expected hashes **10/10** (`r1-release-images.SHA256SUMS`): `system` `6f2abd2d…`, `vbmeta` `4cfa2acc…`.

| Check | Result |
|---|---|
| Static content of `system` (`r1-static.txt`) | adapter `b80879f2…`; rules `2b806321…`; `gscutil.rc` `61149fa1…` and `gscutil-executor.rc` `5105310d…`; app 2.0 `cd2c896e…`; the 1.0 directory removed; layer present |
| Firmware safety, release images (`fws-images.json`) | pass |
| Laptop payload P (`payload-laptop.json`) | `15779f0297ac6508a2ce54bd8d4382bcacdc2698cab0469f4818f9c981c57ad6`: incremental from RB-20261023-03, 3,363,107 bytes, OpenBook-signed. Firmware safety (no postinstall) passes, and it fits the G14 layout |
| Control | RB-20261023-03's ten images rebuilt byte for byte with these tools |
| Update rehearsal (`vm/r1-into-b/`) | VM slot A holds RB-20261023-03 (app 1.0) plus the per-payload apply driver, with data. R1 into slot B: apply 11/11; boot B 7/7, merged; slot B byte-identical 10/10 |
| Fallback | `vbmeta_b` corrupted: three B boots fail, then A boots by itself, **7/7** |
| Firmware safety after the update (`judges/`) | Against RB-20261023-03's fresh first boot, 18/19: `check_tpm_clear` exits 1 instead of 2. In the same VM, RB-20261023-03's own first boot exits 2 and its later (fallback) boot exits 1, so the exit code follows boot history, not R1. **Against that like-for-like baseline: 19/19.** `gscutil` no longer starts, with no denials; gscd, KeyMint, Weaver and update_engine are unchanged |
| **App after the update** (`vm/vmcheck-into-b/app-after-update.json`) | **Not passed: 11/16.** App 2.0 is installed as a privileged system app in slot B (`OpenBookUpdate-v2`, versionName 2.0), runs in `openbook_update_app` for user 10, has REBOOT and notifications granted, and starts its boot work on slot B. The kernel shows no denials for it, and the live log shows no crash. But the VM report's output stops right after the app's screen opens (`am start` "Complete"), on two separate boots (`judges/app-report-excerpt-*.txt`). The report service exits 0 after 119 s each time, yet none of its later lines (second process check, refresh broadcast, the app's log, "done") reach the console, and the app never logs `check finished` or `refresh requested`. The same report completed for app 1.0. The update check and the refresh path after an update are therefore **unconfirmed**; the cause is not found |

The third boot's `snapshot_merged` is false only because the merge had already completed on the second boot (7/7).

## Decision

Under the approved terms ("if anything fails, I stop and tell you"), the install was not run. P, the release images, the VM disks and the logs are kept on the host to rerun the app check.
