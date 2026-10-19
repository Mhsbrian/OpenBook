# Why the note is a system overlay while a computer-control session runs

An intermediate build of this round (2026-10-19, 00:10–00:18 UTC), on the earlier Q5 image (`q5-out`, `5c1d0c4`) with
Quire installed as the dev APK.

## The note as an ordinary overlay throughout (00:10–00:11 UTC)

A lab `CONTROL` run on Settings, from the bare desktop:

- `consent: dialog started above the waiting activity`, then "Only this time", then `cc: created: display 1920x1080`.
  The waiting activity was enough for the platform's check after Allow.
- `cc: launch: com.android.settings` started Settings on the session display. Its windows hide overlays, as every
  Settings page does (`SettingsBaseActivity` adds `HideNonSystemOverlayMixin`). Then `dumpsys window windows` showed
  the following.
  - "Hiding System Alert Windows" listed `com.android.settings/...Settings$NetworkDashboardActivity` and
    `...Settings`, both on the session display.
  - The note's window, `Quire`, at `frame=[590,233][1415,1041]` (the mirror), had
    `mIsForceHiddenNonSystemOverlayWindow=true` and `isOnScreen=false`.
- `mirror-hidden-during-run.jpg`: the person's screen while the agent tapped in Settings. The mirror, Pause, Take over
  and Stop are all missing.

WindowManager hides non-system overlays on every display when any window from another uid asks
(`WindowManagerService.updateNonSystemOverlayWindowsVisibilityIfNeeded`, `shouldHideNonSystemOverlayWindow`).

## The same run with the note as a system overlay while the session runs (00:17 UTC)

- The log shows `note: window system overlay (computer control running)`, and the window's
  `pfl=... SYSTEM_APPLICATION_OVERLAY`, `isOnScreen=true`.
- `mirror-shown-with-session-overlay.jpg`: Settings is open on the person's display too, so overlays are hidden.
  The mirror with Stop, Pause and Take over is still in view.
- At the end of the run the log shows `note: window ordinary overlay`.

The scripted checks in `../cf/` repeat this on the final in-tree build.
