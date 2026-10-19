# First Q2 image in Cuttlefish (2026-10-18, 14:48–14:58 UTC)

Build `anybook_cf_x86_64_pc-cp2a-userdebug` from `af9a7b8` (frameworks/base patch 0005 only), 31 min under the lane
lock, booted in Cuttlefish on the AMD lane (`CF_GPU=amd`, `gfxstream_guest_angle`), boot complete 30 s after
`cvd create`. This image found three platform gaps, fixed in the second image (`../cf/`).

## What held

| Check | Result | Files |
|---|---|---|
| Desktop defaults (`scripts/ui/desktop-defaults.sh`, fresh boot) | 16/16 PASS, as on `main` | `defaults/` |
| Quire installed, privileged, its permissions, the assistant role, the contextual search package, the feature, the flags, the factory allowlists | 20/20 PASS | `q2-check/checks.log` (facts), `allowlist-boot-log.txt` |
| Meta+Space → Quire's note | `trigger=assistant_shortcut entrypoint=11(KEYBOARD_SHORTCUT) visible=[dev.openbook.quire.secureprobe, com.android.settings, com.android.settings, com.android.launcher3] flagSecureFound=true`, screenshot 1920×1080 with 0 probe-coloured pixels | `q2-check/invoke-meta_space*` |
| The assist key → Quire's note | `trigger=assist_key`, same visible packages, `flagSecureFound=true`, 0 probe-coloured pixels | `q2-check/invoke-assist_key*` |
| Computer control with the app op set to allowed by hand (`appops set dev.openbook.quire COMPUTER_CONTROL allow`, what "Always allow" does) | Session created (display 1920×1080), Settings' Dark theme page launched on display #2, Quire's mirror shows it, two session screenshots, a tap at (1857, 188) through the session turned Dark theme on (`cmd uimode night`: no → yes), `handOverApplications()` moved Settings to display #0 and closed the session (`SESSION_EMPTY`) | `mirror-settings-on-session-display.png`, `mirror-after-tap-dark-theme.png`, `session-screenshot.png` |

## Gaps found, fixed in the second image

1. **The shake, Meta+A and Meta+G never reached Quire.** Two causes:
   - Launcher3, which starts contextual search for all three, lacks `ACCESS_CONTEXTUAL_SEARCH`:
     `SecurityException: Permission Denial: Cannot call startContextualSearch from pid=0, uid=10092`
     (`platform-gaps-log.txt`). Fixed by `aosp/patches/packages/apps/Launcher3/0002` and a privapp entry.
   - SystemUI arms the shake detector only when logout is enabled, which the system user never is
     (`ContextualCursorInteractor`, `UserLogoutInteractor`). `cmd user is-headless-system-user-mode` is `false` on
     OpenBook. Fixed by `aosp/patches/frameworks/base/0006`.
2. **The consent dialog did not exist.** `RequestComputerControlAccessActivity` is in VirtualDeviceManager, which is
   installed only with `RELEASE_PACKAGE_COMPUTER_CONTROL` (cp2a: off). The request reached the consent step and Quire
   crashed on `ActivityNotFoundException: No Activity found to handle null` (seen in the crash buffer before a later
   `logcat -c` cleared it). Fixed by setting the flag in OpenBook's release map, and Quire now reports such a failure.
3. **A session's accessibility windows were always empty**, so "tap the node that says Use dark theme" found nothing
   (`cc: tap refused by Quire: no node with text "Use Dark theme" (0 accessibility windows)`). AOSP's
   `ComputerControlSession` registers its accessibility proxy before creating it: `NullPointerException ...
   AccessibilityManager.registerDisplayProxy` (`platform-gaps-log.txt`). Fixed by `aosp/patches/frameworks/base/0007`.

The computer-control checks above ran with the app op preset, so they skipped the consent dialog; the second image runs
them with the platform's dialog.
