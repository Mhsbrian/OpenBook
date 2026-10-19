# quire9 on the G14 (2026-10-19 15:21Z): the owner's second report

Report: the jolt is older than Q6; a long run ran off the screen; the agent kept tapping Install under Android's prompt.

**What the laptop showed (read-only, before the fixes)**
- **Android's prompt:** Aurora Store's install requests started the package installer's `CONFIRM_INSTALL` on display 0, the person's own screen, not the session display. The 760 dp note covered it, and the run went to 102 steps.
- **The icons:** the launcher's database held all 9 desktop items on screen 1 (the second page), and the launcher showed page 0. Launcher3's `AddWorkspaceItemsTask` always skips the first screen. Nothing had been deleted.
- **The jolt:** the laptop can't record video (its AVC encoder never starts), so it was caught in the VM. `../vm/open-jolt-before.png` is 31 raw screenshots taken back to back during an open: one frame shows the note about 225 px up and to the left, then it is back. `../vm/open-jolt-after.png` is the same with the trusted, display-wide window: no jump. A click beside the note still opened Files in the taskbar, and the note still closed on it.

**The update**
- Slot B, vbmeta `818cfcf5…`, marked good, merge completed (`precheck.txt`, `ota-apply.log`, `ota-status-after.log`).
- Users, packages, versions and settings unchanged (boot counters aside).

**The icons, moved**
- With page 0 empty, the 9 desktop items were moved from screen 1 to screen 0 in the launcher's database, and the launcher was restarted. A copy of the database as it was stays on the laptop at `/data/local/tmp/launcher_6_by_5.db.before-anal220`.
- The desktop then showed them all on its first page, also after Home.
- New installs go there too (Launcher3 patch 0003).
