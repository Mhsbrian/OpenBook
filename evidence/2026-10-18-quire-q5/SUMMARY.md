# ANAL-219 (Quire Q5): the Quire surface, built to Q3's design (2026-10-18)

The write-up is `docs/quire.md` §9 (built) and §8 (findings); the design is PR #98, `docs/quire-design.md` at
`e0ace54`.

**What changed**
- `device/anybook/common/quire/app/src/dev/openbook/quire/`:
  - `note/`: the note (a system application overlay of Quire core's uid), one card for every state, the mirror
    panel, tasks that map ACP to blocks, Esc / Hide / Stop, the tray, a computer-control run, the lab receiver.
  - `acp/`: an ACP v1 client.
  - `ui/`: colour roles from the system palette, type, motion tokens as springs, the leaf, the agent's pointer, the
    focus ring.
  - `invocation/`: contextual search hands the call to the note; "Ask Quire" on a selection.
  - `control/`: computer control's events, Pause and Resume, the mirror's zoom.
- frameworks/base `0008` (SystemUI): the halo and the intake outline, and the pointer and window bounds for
  contextual search, from the shake and from Meta+Space or the assist key.
- `scripts/quire/q5-cf-check.py` (the checks), `q5-acp-agent.py` (scripted ACP agents), `q5-contrast.py`;
  `device/anybook/common/quire/tools/build-apk.sh` and `subset-icons.py`; fonts in `res/font` (`fonts/README.md`).

## Builds

| Build | Repo | Result | Log (host, `~/anybook/logs/aosp/`) |
|---|---|---|---|
| `OpenBookQuire` for `anybook_cf_x86_64_pc-cp2a-userdebug` | `628fc59` | OK in 2:47 (Soong, in-tree Kotlin, the OFL licence module) | `build-20261018T183829Z.log` |
| `OpenBookQuire`, the final sources | `2ec9b15` | OK in 3:43 | `build-20261018T194443Z.log` |
| `anybook_cf_x86_64_pc-cp2a-userdebug` `droid QuireSecureProbe` | `5c1d0c4` | OK in 7:06 (incremental), frameworks/base 8 patches applied, SystemUI with `0008` compiled; snapshot `~/anybook/aosp/cf/q5-out` | `build-20261018T191007Z.log` |

Both ran under the lane lock (`scripts/aosp-docker.sh`, `AOSP_JOBS=24`). The image was booted on the AMD lane:
`CF_GPU=amd`, `gfxstream_guest_angle`, 1920×1080 at 160 dpi, `boot_completed` 19 s after `cvd create`, fresh `/data`.

**Which Quire ran.** The states, accessibility, Remove-animations and frames checks ran on the image's own
Quire (Soong, `5c1d0c4`). Four fixes found on the way were installed over it as the dev APK
(`tools/build-apk.sh`, the same sources) before the keyboard, video, contrast and health checks and the control
states were rerun: a lab-opened note no longer toggles an open one closed (only Meta+Space, the assist key and the
taskbar toggle), the zoom shows a wide control from its leading edge, the palette dump, and a Tab check that waits
for the dump. The final sources build in-tree (`2ec9b15`, above).

## Results (`cf/`)

**`scripts/quire/q5-cf-check.py`: 72 PASS, 1 FAIL, 12 INFO** (`cf/results.tsv`, the last run of each check;
`cf/results-all-runs.tsv` has every run, `cf/checks.log` the transcript).

| Section | Result |
|---|---|
| **States** (`cf/side-by-side/`, the capture left, the Q3 render right) | Every screen id of the design gallery in light and dark: 26 PASS and 5 INFO per theme. The content comes over ACP from the scripted agents; computer control is the platform's real session |
| **Invocation, the real paths** | The pointer shake: `anchor=pointer 566,233 bounds=Rect(269, 107 - 1651, 884)`, so the note opens beside the pointer and takes in the Settings window (frameworks/base `0008`). Meta+Space after the pointer moved: `anchor=pointer 715,376`; with a still pointer it rises from the taskbar (the 10 s rule). "Ask Quire" on a selection: `ACTION_PROCESS_TEXT`, 68 chars |
| **Computer control** | The platform's dialog with the note waiting beside it; the session (1920×1080); the mirror zoomed 2× on each control with the agent's pointer and focus ring; Pause → `blocked reason=3(CALLER_INITIATED)` and no tap while paused; Take over → `closed reason=4(SESSION_EMPTY)`, "Settings is on your screen now." |
| **Keyboard** (§6.1, §6.2) | 9/9: focus on the field when the note opens; focus on the consent card when it arrives; Tab order Don't allow → Allow for this session → Allow; Shift+Tab back; Enter answers `deny`; Esc at consent answers `cancelled` and stops; Esc mid-run stops and never hides; Meta+Space hides a running task and brings it back; Esc closes a finished note |
| **Accessibility** (§6.3) | PASS: 157 focusable or clickable controls in 28 UI dumps, every one labelled. INFO: TalkBack isn't in AOSP, so its walkthrough is for the G14 |
| **Remove animations** (§5.3) | PASS: `unfold animated=false`, `fold animated=false`; with animations on, `unfold animated=true` |
| **Frames** (Cuttlefish only) | INFO: 958 frames over three rounds of open, stream, consent and fold; 1 janky (0.10 %); p50 5 ms, p90 5 ms, p99 8 ms; 0 missed vsync (`cf/gfxinfo.txt`). The acceptance measurement is the G14's |
| **Video** | PASS ×3 (`cf/video/`): the shake and the halo, the note at the pointer, a streamed answer, the fold; consent by keyboard; the platform consent, the mirror on each control, Pause, Take over. `halo-frames.png`: the ring and "Ask Quire" at the pointer, then the note unfolding out of it |
| **Contrast** (§8) | PASS: 16 pairs on all 8 wallpapers × 2 themes (the closest, Stop on folio-light, 5.07:1 against 4.5:1), and on the device's own palette in light and dark; the device is within 6–7/255 of the predicted folio palette (`cf/contrast.md`, `cf/device-palette.json`) |
| **Health** | No Quire crash, no ANR, no SystemUI restart, no SELinux denial for Quire. **FAIL** "no new SELinux denials": six `mediaprovider_app → shell_data_file` denials at 927–942 s. They came from the check's first video attempt, which wrote its recordings to `/data/local/tmp`, where MediaProvider then looked; the check writes to `/sdcard/Movies` since, and the rerun added none. Otherwise only Cuttlefish's known `gceservice` denial (`cf/selinux-denials.txt`) |

The five INFO rows per theme are what is lab-driven or not built: `idle` (no Launcher3 button), `invoke-voice` (the
listening card without Q7's recogniser), `agent-picker`, and `consent` and `settings-help` (the broker's card and the
change list, raised from the lab until Q6's broker raises them).

**A real agent** (`real-agent/`): opencode 2.0.31 over its own ACP mode, bridged to the device, answered a prompt in
the note in 4 s, and with a window intake (three blocks, the screenshot included) replied that its model can't read
images (`log.txt`).

**Finding** (`pause-resume-finding.txt`): after Pause and Resume, the session's accessibility windows are gone for at
least 3 s; system_server's `ProxyAccessibilityServiceConnection.getWindows()` dereferences a null list. Quire ends the
run honestly and closes the session. Q6 needs a platform fix.

## Where the build differs from the renders

| State or element | Render | Build | Why |
|---|---|---|---|
| `consent` (settings) | Claude Code's option names | Quire's options (Don't allow · Allow for this task · Allow) | §3.3 rule 2: an OS tool's card is the broker's own. The agent's own card (`consent-command`) has the agent's names |
| `done` | Result line, Undo both · Show changes | Steps fold into one chip, the answer stays; no Undo | Undo exists only for changes made through Quire's broker (Q6); an agent's own turn has nothing Quire can undo |
| `background`, `idle`, `invoke-taskbar` | The Quire button in the taskbar with ring and badge; the tray as Launcher3's popup | No button; Quire draws the tray above the taskbar | The button is a Launcher3 change still to make |
| Intake outline | Stays while composing | Fades with the halo (≈600 ms) | SystemUI doesn't know when the note closes |
| Halo | Follows the pointer until the note opens | Drawn where the shake ended | Next increment |
| `invoke-selection` | The note at the pointer | Above the taskbar | `ACTION_PROCESS_TEXT` carries no geometry, and Quire should not hold INJECT_EVENTS to read the pointer |
| `invoke-voice` | Mic indicator and privacy dot | Not shown | They appear when the microphone is in use (Q7) |
| Type sizes | §4.1: label 14, chip and buttons 13, intake 13 | The prototype's CSS: 13.5, 13.5, 12.5 | The renders come from the CSS |
| Mirror | A 16:10 session | Cuttlefish's 16:9 session letterboxed in surface-dim when not zoomed | §3.4 allows the letterbox |
| `images` | "Region you pointed at" | "Image from the agent" | The image comes back over ACP from the scripted agent |

## Not done here

- **The G14:** 60 fps for open, stream, consent and fold, and the blur within B2's budget.
- **TalkBack walkthrough:** TalkBack isn't in AOSP.
- **The Launcher3 taskbar button** (the leaf after All apps, ring, badge, breathing).
- **Atelier's sign-off on the build** and **the Checker's on this evidence** (acceptance 4).

## Reproduce

```bash
# Image (lane lock), snapshot, boot (as ANAL-216's SUMMARY, with S=~/anybook/aosp/cf/q5-out)
flock ~/anybook/aosp/.lane.lock bash -c 'ANYBOOK_LANE_LOCK_HELD=1 AOSP_JOBS=24 scripts/aosp-docker.sh /repo/scripts/aosp-build.sh \
    anybook_cf_x86_64_pc-cp2a-userdebug droid QuireSecureProbe && <snapshot to ~/anybook/aosp/cf/q5-out>'
export CF_OUT=~/anybook/aosp/cf/q5-out CF_STAGE=~/anybook/aosp/cf/q5 CF_NAME=anybook-cf-q5 CF_DEVICE=anybook_vsoc_x86_64 \
  CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_ADB_PORT=16219 CF_WEBRTC_PORT=11219 CF_ARGS=--vhost_user_vsock=true \
  ANDROID_ADB_SERVER_PORT=5219
scripts/cf-boot.sh up && scripts/cf-boot.sh wait && ~/anybook/android-sdk/platform-tools/adb connect 127.0.0.1:16219
scripts/quire/q5-cf-check.py 127.0.0.1:16219 OUT --design PATH/TO/docs/quire-design   # PR #98's renders
~/anybook/tools-local/brand-venv/bin/python scripts/quire/q5-contrast.py --md --device OUT/device-palette.json
scripts/cf-boot.sh down
```
