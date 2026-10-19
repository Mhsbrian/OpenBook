# Pre-test on an image without Quire (2026-10-18, 13:50–13:55 UTC)

While the build lane was busy, Quire was packaged by hand (`device/anybook/common/quire/tools/compile-check.sh`'s
classes, `d8`, `zipalign`, signed with AOSP's test platform key) and installed into `/data` on Cuttlefish booted from
ANAL-207's snapshot of `main` (`~/anybook/aosp/cf/b6-snap2-134356`, `build.txt`). Then
`cmd role add-role-holder android.app.role.ASSISTANT dev.openbook.quire`.

That image has no Quire overlay, so `ContextualSearchManagerService` is not even started (SystemServer starts it only
when `config_defaultContextualSearchPackageName` is set), and computer control's flags are compiled out. What it showed:

| Check | Result |
|---|---|
| The role binds Quire's VoiceInteractionService | `Quire: assistant: ready`; `voice_interaction_service=dev.openbook.quire/.assist.QuireVoiceInteractionService` |
| Meta+Space (`input keycombination KEYCODE_META_LEFT KEYCODE_SPACE`) | `VoiceInteractionManager: showSessionForActiveService()`, then `Quire: assistant: session shown trigger=assistant_shortcut invocationType=0 keyboardHint=true display=0 showFlags=0x4` |
| The assist key (`input keyevent KEYCODE_ASSIST`) | `Quire: assistant: session shown trigger=assist_key invocationType=7 keyboardHint=false display=0 showFlags=0x4` |
| Contextual search from the session | `Quire: assistant: no ContextualSearchManager` (expected on this image) |
| The note, started directly with contextual search's extras | `invocation: trigger=system_action entrypoint=9(SYSTEM_ACTION) visible=[com.android.settings, com.android.launcher3] flagSecureFound=true screenshot=none ...`, saved as JSON; `note-synthetic-extras.png` |
| A computer-control request with the flag compiled out | **Found a crash:** the platform throws `IllegalStateException: Cannot create ComputerControlSession - flag disabled`, which Quire did not catch. Fixed (every platform refusal is reported); then `cc: request refused by the platform: IllegalStateException: ...`, `control-flag-off.png` |
| The lock-screen sequence of `scripts/quire/q2-cf-check.py` | A lab command with `delayMs` runs while the keyguard shows (`isKeyguardShowing=true`) |
| The check script's window detection | Found the probe's window, its frame and `FLAG_SECURE`, after fixing the parser |

Also found: AOSP 17 declares only two of the `computer_control_*` flags cp2a carries values for (docs/quire.md §2.4).
