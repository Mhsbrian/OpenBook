# ANAL-219 (Quire Q5): the Checker's three safety findings, fixed (2026-10-19)

The Checker held PR #110 at `88bf79b` on 2026-10-18 with three blockers (ANAL-219, comment of 19:59 UTC). This round
fixes all three, with a regression check for each. Q5 is built and documented in `docs/quire.md` §9, the earlier
evidence is in `evidence/2026-10-18-quire-q5/`, and the open decision this round raises is in §8, item 10.

## What changed

| Finding | Change | Code |
|---|---|---|
| 1. The overlay exemption defeated other windows' protection, and the note could be clamped back over the consent dialog | The note and the tray are **ordinary** application overlays, and hide whenever a window on screen asks to hide overlays. The note's window is only the card and its shadow, so clicks beside the card reach the app below. Quire asks for computer control from **`ConsentWaitActivity`**, an inert, transparent activity of its own, which no overlay rule hides. It starts the platform's dialog, so the dialog opens and stays above it. While the dialog is up, the note steps aside and the activity shows the waiting card. No geometry places anything of Quire's beside or over the dialog any more. **While a session runs**, the note is a system overlay again, so the mirror, Pause, Take over and Stop stay in view (see below) | `note/NoteWindow.kt`, `note/ConsentWaitActivity.kt`, `note/ControlRun.kt`, `control/ComputerControl.kt`, `note/TrayWindow.kt` |
| 2. ACP consent could be attributed to the wrong agent | A session belongs to the **connection** it was opened on. Updates, permission requests, cancels, releases and disconnects are routed by connection plus session ID | `note/SessionRoutes.kt`, `note/Agents.kt`, `note/Task.kt` |
| 3. Missing bounds silently broadened the disclosed capture | A window is taken in only when SystemUI said which one. That needs the pointer inside non-empty bounds that are on the display, the window's package, bounds read at most 3 s earlier, and that package on the screenshot. Otherwise **nothing** is taken in. The crop is named after that package, not after the first visible app. frameworks/base `0008` now passes the package and the time with the bounds, and never picks the home task | `invocation/IntakePolicy.kt`, `invocation/ContextualSearchActivity.kt` (`Calls`), `assist/QuireSession.kt`, `aosp/patches/frameworks/base/0008` |

**Why the session runs as a system overlay.** In an intermediate build of this round, the note was an ordinary overlay
throughout. As soon as Settings started on the computer-control display, WindowManager hid the note: Settings hides
overlays on every page, and the rule is global across displays. The person then saw nothing while the agent tapped:
no mirror, no Pause, no Stop. The screenshots and window state are in `why-session-overlay/`. So for a running
session's life, and only then, the note is a system application overlay.

**Found on the way:**
- The platform's consent dialog asks to hide overlays, but VirtualDeviceManager holds neither permission that makes
  that count. While the dialog was up, only Settings' windows were hiding overlays (`cf/consent/*-windows.txt`). The
  note steps aside from the dialog by itself.
- Over the desktop, SystemUI's "window under the pointer" was the launcher's home task, which spans the display. A
  call there would have sent the whole screen under the launcher's name. `0008` now skips the home task, and Quire
  refuses the desktop, SystemUI and itself.
- Settings, Files and the permission screens hide overlays on every page (`SettingsBaseActivity`, DocumentsUI's
  `BaseActivity`, PermissionController). With the note honouring them, it does not show over them. See "Open decision"
  below.

## Builds

| Build | Repo | Result | Log (host, `~/anybook/logs/aosp/`) |
|---|---|---|---|
| `anybook_cf_x86_64_pc-cp2a-userdebug` `droid QuireSecureProbe`, `0008` with package and time | `e51eff1` + this round's work tree | OK in 34:06 (other branches had built in between) | `build-20261018T235456Z.log` |
| The same, `0008` also skipping the home task | the four fix commits (`f60e5c5`) | OK in 6:23 | `build-20261019T003117Z.log` |
| The same, with the lab reporting the mirror's controls; the image for `regression/` | `07f0495` | OK in 1:22; snapshot `~/anybook/aosp/cf/q5s-out3` | `build-20261019T004804Z.log` |
| The same, with the note's still beneath the consent dialog (Atelier's ruling 1); the image for `cf/` and `atelier-still/` | `45e773a` | OK in 1:22; snapshot `~/anybook/aosp/cf/q5s-out4` | `build-20261019T020844Z.log` |

All four ran under the lane lock (`scripts/aosp-docker.sh`, `AOSP_JOBS=24`), and frameworks/base got its 8 patches.
**Which Quire ran:** each time the image's own, built in-tree by Soong (`/system_ext/priv-app/OpenBookQuire`, no dev
APK), its sources compared file by file with the commit named above. The probe is the image build's
`QuireSecureProbe.apk`. Each boot was fresh (`/data` new), on the AMD lane: `CF_GPU=amd`, `gfxstream_guest_angle`,
1920×1080 at 160 dpi.

## Results

### The regressions: `scripts/quire/q5-safety-check.py` (`cf/`)

**54 PASS, 0 FAIL, 0 INFO** on `45e773a`'s image, after Atelier's ruling 1 changed when the dialog opens. It was also
54/54 on `07f0495`'s image before that change. Files: `cf/results.tsv`, `cf/checks.log`, with screenshots, window dumps
and the ACP payloads.

- overlay: 7
- consent: 18 (1920×1080, 1280×800, and Don't allow)
- agents: 10
- intake: 19

| Section | What it shows |
|---|---|
| **overlay** (finding 1) | The probe's `ProtectedActivity` calls `Window.setHideOverlayWindows(true)`, as a bank would, from an ordinary app. Over it, the note is `mIsForceHiddenNonSystemOverlayWindow=true`, `isOnScreen=false`, and so is the tray. A tap where the card would be reaches the probe (`flags=0x0`). The note shows again once the probe goes. With the probe hiding nothing, the note's window is the card plus 33 px of shadow, not the display, and clicks beside it reach the probe (`flags=0x2`, partly obscured, not blocked), with no "Untrusted touch" in the log |
| **consent** (finding 1) | With Settings on screen, which hides overlays: at 1920×1080 and at **1280×800** (the Checker's case: note at 900,300). Quire asks from its waiting activity. While the dialog is up, no Quire window on screen is above it, the waiting activity is beneath it, and the note is not on screen. "Only this time" creates the session, so the platform found Quire on screen without any exemption. While the session runs, the note (mirror, Stop) is on screen with `SYSTEM_APPLICATION_OVERLAY`, though Settings hides overlays on both displays. Stop, tapped where the lab says the button is, ends the run, and the note is an ordinary overlay again. "Don't allow" is refused (`dialogShown=true`) and leaves no waiting activity |
| **agents** (finding 2) | Agents A and B both answer `session/new` with `session-1`. Each permission request reaches only its own agent's task (the log names task, connection and session). A's card says "Agent A runs this on this laptop", and B's says Agent B's. Esc on A's card answers A `cancelled` and sends `session/cancel` to A, and B receives nothing. Allow on B's card answers B only. With a second task on A (`session-1` again), closing A's connection fails only that task. B's run goes on, streams "B is still here after A left.", and ends `end_turn`. The ACP traffic each agent saw is in `agents/peer-*.json` |
| **intake** (finding 3) | An agent that accepts images records what it receives (`intake/*.json`, plus the images). The real Meta+Space with the pointer still for 11 s gives `anchor=taskbar`, `reason=no-pointer`, and one text block, no image. Over the desktop: `reason=no-bounds`, no image. The real Meta+Space and the real shake over the probe's window, with Files in front elsewhere (so Files is the first visible app), give `source=dev.openbook.quire.secureprobe`, a crop equal to the probe's frame, the text naming "Quire secure probe", and an image that differs from the host's own screenshot by a mean 0.2/255. Made-up calls through the lab cover what SystemUI never sends: no pointer, no bounds, empty, inverted or off-display bounds, the pointer outside them, no package, the desktop's package, no time, stale (4 s) or future bounds, a package not on screen, and the secure flag. Each takes in nothing, with its reason, and the agent receives no image and no window text. A valid made-up call takes in exactly its 800×600 bounds: the generated screenshot's pixels encode their position, and the image's corners read back as the crop's corners |

**Host tests** (`device/anybook/common/quire/tools/unit-test.sh`, `unit-tests.txt`): **37 passed, 0 failed.**
- `SessionRoutes`, 13: colliding IDs, look-alike connections, release by the wrong owner, a stale release after a new
  owner, a disconnect that leaves others.
- `IntakePolicy`, 24: every refusal and its order, the 3 s edge, partly off-screen windows, full-screen windows, the
  desktop, the secure flag.

### Q5 again, with nothing behind the note: `scripts/quire/q5-cf-check.py --desk none` (`regression/`)

**76 PASS, 0 FAIL, 14 INFO** (`regression/results.tsv`, `regression/checks.log`).

- **States:** 28 PASS and 6 INFO per theme, with side-by-sides in `regression/side-by-side/`. The INFO rows are the
  earlier round's five (lab-driven or not built), plus `mirror-takeover`: after Take over the note is hidden behind
  Settings.
- **Keyboard:** 9/9.
- **Labels:** 109 controls in 27 UI dumps, every one labelled. This time the dumps are committed
  (`regression/light/`, `regression/dark/`).
- **Remove animations:** cuts the unfold and the fold.
- **Frames** (a Cuttlefish proxy): 1196, 0 janky, p90 5 ms, p99 6 ms. The window now follows the card, so it changes
  size while text streams.
- **Recordings:** three, re-encoded at 1280 wide for the repository. The contact sheets were made from the originals.
- **Health:** no Quire crash, no ANR, no SystemUI restart (one start, at boot: the running process), no SELinux denial
  for Quire, none new.

The new window code (an ordinary overlay that fits the card) changes how every state is drawn, so all of Q5's states
ran again in both themes next to their renders. So did the keyboard paths, labels, Remove animations, frames, the three
recordings and health. Settings and Files hide overlays on every page, so the run uses `--desk none`: nothing behind the
note. The side-by-sides therefore differ from the renders in what is behind the card.

**Earlier runs in this round** (`earlier-runs/first-final-run/`). The first final run on this image had one harness
failure in each script. All three are fixed in the checks, not in Quire, and the run above is a second fresh boot.

- In the safety check, a UI dump came back empty while B's card was on screen (the screenshot is kept). The dump is now
  retried.
- In health, the launcher was blamed with an ANR. The harness had sent Esc while nothing had input focus, right after
  stopping Settings. `clean()` now sends Esc only when input has a focused window.
- In health, the SystemUI start at boot was counted as a restart. A restart is now a start of any other process.

### Atelier's ruling 1: a still of the note beneath the consent dialog (`atelier-still/`, `45e773a`)

Atelier signed off on the build at `69cf4d1` and accepted the waiting surface beneath the dimmed dialog, with one
change: the surface is a still of the note at the note's geometry, so the only change on screen is the scrim.

- **What it shows:** the header with the leaf and agent chip, the intake chip, the prompt, the steps with "Asking to
  use Settings" running, and the waiting row. No composer, no footer, nothing focusable.
- **How it works:**
  - `NoteCard.still()` draws the sections above the composer into a bitmap, once the card has laid out the waiting
    row. A block still fading in is drawn at full opacity.
  - The waiting activity shows it at the card's place, on the note's surface.
  - The dialog starts only once that frame is on screen, and the note steps aside as it starts. So, as before,
    nothing of Quire's is over the dialog.
- `q5-cf-check.py --states control` in both themes, then health: **13 PASS, 0 FAIL, 2 INFO**.
  - `consent-system` and `consent-system-dark` are in `atelier-still/side-by-side/`. The mirror, Pause and Take over
    run again with it.
  - Health: no Quire crash, ANR, SystemUI restart or new denial.
- At 1280×800 (`cf/consent/1280x800.jpg`), the still sits under the dialog.
- In the safety check, Settings was on screen and hid the note itself. The still beneath the dialog still showed: it is
  the waiting activity's inert image, not the overlay.
- `regression/side-by-side/consent-system*.jpg` show the first round's two-line card, which this replaces.

## Where the build now differs from the renders, beyond `evidence/2026-10-18-quire-q5/SUMMARY.md`

| State | Render | Build | Why |
|---|---|---|---|
| Any state over Settings or Files | The note over the app | The note does not show | Both hide overlays on every page, and the note honours that (finding 1). The intake and the agent still work. Open decision below |
| `consent-system` | The note, undimmed, waiting beside the platform's dialog | The dialog over the dimmed desktop, with a still of the note beneath the dim, at the note's place | The still is drawn by the activity beneath the dialog, so nothing of Quire's can cover the dialog at any display size. Atelier accepted this on 2026-10-19 and asked for the still (header, intake, prompt, steps, the waiting row; no composer, no footer) in place of the first round's two-line card. See "Atelier's ruling" below |
| `mirror-takeover` | "Settings is on your screen now" in the note | The note is hidden behind Settings once Settings is on the person's display | After the run the note is ordinary content again. Reported as INFO, not as a pass |

## Open decision (for the owner and the Checker)

AOSP gives a system application overlay the right to stay visible over windows that hide overlays. That is what
`SYSTEM_APPLICATION_OVERLAY` is documented to do. The Checker asked that the note's ordinary content honour those
windows instead, and it now does. The cost: Settings, Files and the permission screens hide overlays on every page, so
the note does not show over the apps Quire most often helps with. Calling Quire over them opens a note nobody sees.
The three ways forward are in `docs/quire.md` §8, item 10:

- keep this;
- move the note into the assistant's own window (`TYPE_VOICE_INTERACTION`, which AOSP never hides);
- a frameworks/base change: system overlays hide for windows that use the public `HIDE_OVERLAY_WINDOWS` permission
  (any installed app, and Files), and stay for windows of apps holding `HIDE_NON_SYSTEM_OVERLAY_WINDOWS` (Settings, the
  permission controller, the package installer).

Nothing of the second or third is built.

## Not done here

- The G14: frames, blur, TalkBack and the Launcher3 taskbar button, as before.
- Take over: Atelier ruled that a note hidden in place is a symptom. If the owner keeps the overlay rule, Take over
  folds the note into the taskbar as a finished task. If the note moves to the assistant's window, the design's Done
  state stands. Either way, it waits for the decision below.
- The frameworks/base unit tests (SystemUI multivalent) were not run. The behaviour of `0008` is checked from outside,
  through the real Meta+Space and shake above.

## Reproduce

```bash
# Image under the lane lock and its snapshot: ~/anybook/work/anal219s/build-cf.sh (SNAP=... for the directory), which
# runs the same commands as evidence/2026-10-18-quire-q5/SUMMARY.md's "Reproduce".
export CF_OUT=~/anybook/aosp/cf/q5s-out4 CF_STAGE=~/anybook/aosp/cf/q5s CF_NAME=anybook-cf-q5s CF_DEVICE=anybook_vsoc_x86_64 \
  CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_ADB_PORT=16229 CF_WEBRTC_PORT=11229 CF_ARGS=--vhost_user_vsock=true \
  ANDROID_ADB_SERVER_PORT=5229
scripts/cf-boot.sh up && scripts/cf-boot.sh wait && ~/anybook/android-sdk/platform-tools/adb connect 127.0.0.1:16229
scripts/quire/q5-safety-check.py 127.0.0.1:16229 OUT/cf --probe ~/anybook/aosp/cf/q5s-out4/apk/QuireSecureProbe.apk   # q5s-out3 for regression/
scripts/quire/q5-cf-check.py 127.0.0.1:16229 OUT/regression --only states,keyboard,a11y,motion,frames,video,health \
  --desk none --design PATH/TO/docs/quire-design    # PR #98 at e0ace54
device/anybook/common/quire/tools/unit-test.sh
scripts/cf-boot.sh down
```
