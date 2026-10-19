# quire8 on the G14 (2026-10-19 14:45Z): the owner's reports from the quire7 session

**What the owner saw**
- **Aurora Store refused three times:** "IllegalArgumentException: Invalid target package for ComputerControl: com.aurora.store". The image's automatable list named only Settings.
- **The note jumping back to its anchor mid-task.** Quire's log shows the window being added again twice within 300 ms at each `read_screen` (system overlay, then ordinary). A window added again starts display-wide and takes its frame a frame later.
- **Desktop icons missing:** the launcher's database was unchanged since 2026-10-18 22:26. Its 9 desktop items and 5 taskbar items were all there, and they were on screen at 14:33Z. Nothing was lost.

**What quire8 changes:** `docs/quire.md` §10.3, commit `a3e6cd1`.

**The update**
- `precheck.txt`, `ota-apply.log`, `ota-status-after.log`: slot A, the package's vbmeta `c0f908e8…`, marked good, merge completed.
- `g14-adb.sh state` before and after, counts only: the same users, packages, versions and settings (boot counters aside); the person's files the same.

**Computer control on Aurora Store**, through the broker (lab `TOOL`):
- `control_start` opened it in 4.9 s, with 24 controls read. No consent dialog appeared: this laptop already had the platform's consent.
- `control_tap` on "Top charts" landed; the agent then read the Top free list and its switches.
- `control_end` closed the session (`CALLER_INITIATED`).
- No Quire crash.
