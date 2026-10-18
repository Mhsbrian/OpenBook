# Quire: interaction and motion design (ANAL-215)

As of 2026-10-18. This is the design for Q3 of the Quire epic (ANAL-214): how a person calls Quire, works with an agent in the note, gives consent, watches the agent drive the system, and sees the result. It is the spec Q5 (ANAL-219) builds to. The brief is `docs/quire.md` §1; the platform facts it relies on are `docs/quire.md` §2, §4 and §6.

Labels: **C** = confirmed (read in a primary source or in `docs/quire.md`'s confirmed sections, or measured here), **HYPOTHESIS** = a design assumption the Porter checks (§7 lists them all).

- **Prototype:** [`quire-design/index.html`](quire-design/index.html). Open it for the gallery; add `?play=1` for the clickable version (shake the pointer, press Meta+Space, click the taskbar button, hold the mic, select text; Esc folds the note; the HUD toggles Remove animations).
- **Renders:** [`quire-design/png/`](quire-design/png/) (1920×1080, PNG, plus `gallery.png` with every state) and [`quire-design/g14/`](quire-design/g14/) (2880×1800, the G14 panel at 240 dpi, so 1920×1200 dp at 1.5×; JPEG q92 4:4:4, 22 MB, because the same set as PNG weighs 35 MB). Every state, light and dark. `scripts/quire/render-design.sh` regenerates them; `G14_PNG=1` keeps the G14 set as PNG.
- **Contrast:** `scripts/quire/contrast-check.py` reads the tokens from the prototype and checks every pair in §4.5.

Every value on the screens is sample data. The desktop, the Settings window and the Notes window are stand-ins drawn in Google Sans with OpenBook's circle icons and corner radii, so the note can be judged against the real look.

## Summary

- **The note is a leaf.** A quire is a gathering of folded pages; OpenBook's mark is two pages and a spark. Quire's note is one small page that unfolds from the pointer and folds back into it. Its glyph is a page with a folded corner, drawn in the brand gradient. That is the only brand colour in the design; everything else is the device's dynamic colour, so the note matches the wallpaper like the rest of the system. No sparkle, no glow bar, no four-point star: nothing borrowed from Gemini or Magic Pointer.
- **Anchored to attention.** The note opens where the person is looking: at the pointer after a shake or a key, at the end of a selection, above the taskbar button. It never opens in a corner. It stays beside the pointer and is never larger than 60 % of the screen height.
- **Consent is a card in the flow, not a dialog over it.** The step stops, the card names exactly what will change (old value → new value, the command, or the diff), and offers Don't allow, Allow for this task, Allow. The first Tab stop is Don't allow.
- **The mirror is the note, grown.** When an agent drives an app, the same note expands to 760 dp and shows the session display with the agent's pointer drawn on it. Pause, Stop and Take over are always visible.
- **Motion is springs, not easing**, and every spring is a token with a stiffness and a damping ratio that Compose and `SpringAnimation` take as they are. With Remove animations, every spatial change becomes a cut and every loop becomes a still.
- **Contrast is measured, not assumed.** Every text pair meets 4.5:1 and every non-text pair 3:1, in light and dark, at the note's worst backdrop. The light note needed 92 % opacity to pass; 84 % failed.

## 1. The idea

The person is in the middle of something. Quire must arrive without asking them to look elsewhere, show what it understood, work in plain sight, ask before it changes anything, and leave without a trace. So:

- **One surface, the note.** Composing, streaming, steps, plans, consent, the mirror, the result and the settings undo list are states of one card, not separate panels. The card reflows between them with one spring.
- **Three things always visible in the note:** which agent is answering, what Quire took in, and how to stop. The agent chip and the intake chip sit in the header; the footer always names what Esc does.
- **Nothing happens off screen.** Steps tick in the note. The mirror is in the note. Background work lives behind the taskbar button, with a ring for progress and a count.
- **The system's own consent stays the system's.** Computer control shows the platform's consent dialog (`RequestComputerControlAccessActivity`, C). Quire does not draw it, and the note says it is waiting for it.

## 2. Invocation

What the person does, what appears in the first 100 ms, where the note anchors, and what Quire takes in.

| Entry | First 100 ms | Anchor | Intake | Screen |
|---|---|---|---|---|
| **Shake** the pointer (contextual cursor gesture, C) | The **halo** blooms around the hotspot: a 32 dp ring, 2 dp, brand conic gradient, 0 → 1 with `spring.tick` (full size in ≈ 90 ms). The window under the pointer gets the **intake outline**. Label "Ask Quire" fades in beside it (120 ms). | The hotspot, 18 dp right and below | The window under the pointer: its name, a screenshot cropped to its bounds, and the selection if it has one | `invoke-shake` |
| **Meta+Space**, the assist key, the Copilot key (assistant role, C) | Same halo at the pointer if it moved in the last 10 s, with the label "Quire Meta Space". If the pointer has been still longer than that, or is off screen, the note rises from the taskbar button instead. | As above, or the taskbar button | The focused window | `invoke-key` |
| **Taskbar button** | The leaf glyph scales 1 → 0.9 → 1 (`spring.tick`) and the note rises from it. No halo. | Centred on the button, 12 dp above the taskbar | Nothing. The chip offers "Add what's on screen". | `invoke-taskbar` |
| **Hold to talk** (the mic key, or hold the assist key; Q7) | The halo appears as a 40 dp **mic ring** that breathes; the mic indicator and the privacy dot show in the status bar. The note opens as the listening card with the live transcript. Release sends. | The pointer | The focused window | `invoke-voice` |
| **Ask Quire on a selection** (the floating text toolbar, `ACTION_PROCESS_TEXT`; HYPOTHESIS, §7) | The selection keeps its highlight. The toolbar item shows the leaf. The halo appears at the toolbar item. | The end of the selection | The selected text as a quoted chip, plus the window name | `invoke-selection` |
| Any entry over a **secure window** (`EXTRA_FLAG_SECURE_FOUND`, C) | The halo answers as usual. | The pointer | Nothing. The chip reads "Secure window · not taken in" with a lock. | `invoke-secure` |

Rules:

- **The halo tracks the pointer** until the note opens. If the pointer leaves the window it was over, the intake outline moves with it. Esc or a click elsewhere cancels the halo with a 200 ms fade and nothing else happens.
- **The intake outline** is a 2 dp stroke in `primary` at 55 % with a 10 dp glow at 18 %, following the window's corner radius. For a pointer region (an image, a table) it is a 12 dp-radius rectangle around the region.
- **The intake chip** in the note always says what was taken in: "Settings · Display" with a 32×20 dp thumbnail, "Region · Notes", the quoted selection, or the lock. Its close button drops the intake before sending.
- **The halo is drawn by SystemUI** above all windows (the same layer as the contextual cursor's own feedback), so it appears even when the app under the pointer is slow.

## 3. The note

### 3.1 Anatomy and geometry

```text
┌─ header ───────────────────────────────────────────────┐  12 dp top, 16 left, 12 right
│ [leaf 22] [CC Claude Code · on this laptop ▾]   [⤓] [✕] │
│ [intake chip]                                           │  prompt block: 10 dp top
│ The person's prompt (15/22, 500)                        │
├─ body (scrolls) ────────────────────────────────────────┤  8 dp top, 16 sides, 10 dp between blocks
│ thought · answer · steps · plan · consent · changes ·   │
│ result · error · auth · code · image                    │
├─ suggestions (optional) ────────────────────────────────┤
│ (chip) (chip) (chip)                                    │
├─ composer ──────────────────────────────────────────────┤  8 dp top, 12 left, 10 right/bottom
│ [ field 40 dp ..................... ] [mic 40] [send 40]│
│ footer: Working · 6 s                        Esc stop   │  12/16, on-surface-variant
└─────────────────────────────────────────────────────────┘
```

| Property | Value |
|---|---|
| Width | 400 dp. **Wide** 480 dp when a code block or a long answer arrives. **Mirror** 760 dp. |
| Max height | 60 % of the display height; the body scrolls, header and composer stay |
| Corner radius | 28 dp (`config_dialogCornerRadius`, C). Cards inside: 16 dp. Chips and buttons: pill. Field: 20 dp. |
| Surface | `note-bg`: `surface` at 92 % (light), `surfaceContainer` at 80 % (dark), over the system's background blur at the same radius SystemUI's shade uses (34 dp, C). 1 dp outline `outlineVariant` at 50 %. Shadow 0 12 32 at 18 % of `#1B1B21` (light), 50 % black (dark). |
| Placement from the pointer | hotspot + (18, 18) dp. Flips to the left of the hotspot when it would come within 24 dp of the right edge. Moves up to stay 16 dp above the taskbar; the transform origin stays on the hotspot so the unfold still comes from the pointer. |
| Placement from the taskbar | Centred on the Quire button, 12 dp above the taskbar. Transform origin: bottom centre. |
| Layer | Above app windows, below the system dialogs, the status bar and the mic indicator (SystemUI overlay window; Q5 decides the window type) |

### 3.2 States

Each state is one screen in the prototype, in light and dark, at both sizes. The last column is what drives it; §7 is the full mapping with the open questions.

| State | What the note shows | Driven by | Screen |
|---|---|---|---|
| **Composing** | Agent chip, intake chip, three suggestion chips for the window under the pointer, the field with focus, footer "Enter send · Esc close". The field grows to 4 lines, then scrolls. | Local; the suggestions come from the intake (window name, selection) | `compose` |
| **Listening** | Seven level bars (`primary`), the transcript with the recognised part in `on-surface` and the partial in `on-surface-variant`, footer "Listening · release to send · Esc cancel". | Q7's speech to text, partial and final results | `invoke-voice` |
| **Choosing the agent** | The chip opens a list grouped by where agents run: On this laptop, Paired computers, with each agent's sign-in state and "Connect an agent · or pair a computer" at the end. The last used agent is preselected. | `quired agents` and each agent's `initialize` → `authMethods` (C) | `agent-picker` |
| **Streaming** | The leaf breathes. Thought chunks collapse to one line, "Thinking…", that is replaced by the answer as soon as the first message chunk arrives. Message chunks append with a caret; no per-character animation. Footer "Answering · 2 s · Esc stop". | `session/update`: `agent_thought_chunk`, `agent_message_chunk` (C) | `streaming` |
| **Steps ticking** | One line per tool call: a status mark, a kind icon, the title. Pending: a hollow ring in `on-surface-variant`. Running: a 12 dp spinner. Done: a filled check in `success`, popping in with `spring.tick`. Failed: a filled cross in `error`, line text in `error`. The title is the agent's `title` ("Reading Wi-Fi settings"). | `tool_call`, `tool_call_update` with `kind` and `status` (C) | `steps` |
| **Plan** | A card "Plan · 1 of 4" with a numbered list; done entries get a check and a strike; the active entry's number fills with `primary`; a priority label shows only when the agent sets one. Updates in place. No consent needed to show a plan. | `plan` with `entries[].status` and `priority` (C) | `plan` |
| **Consent, settings** | The step stops. A card outlined 1.5 dp in `primary`: shield icon, "Change 2 settings", the tool's name at the right, one row per change (name, where it lives, old → new as a pill), a sentence on undo, and the three buttons. | `session/request_permission` with `options` (C). The rows come from the OS settings tool's request (Q6). | `consent` |
| **Consent, command or file** | The same card with the command in a monospace chip, or a diff with added lines tinted `success-container` and removed lines `error-container`. | Same; `tool_call.content` of type `diff` or the command title (C) | `consent-command` |
| **Consent, computer control** | The platform's own dialog appears (not Quire's). The note shows "Asking to use Settings" as a running step and a result line "Waiting for your permission". | `ComputerControlConsentManager` → `RequestComputerControlAccessActivity` (C) | `consent-system` |
| **Live mirror** | The note expands to 760 dp: an automation chip ("Using Settings", `tertiary-container`), the page title, the mirror (16:10, 16 dp radius) with the agent's pointer in brand blue, a 36 dp tap ring and a focus ring on the control it targets, the current steps under it, and Stop · Pause · Take over. The taskbar's Quire button breathes while this runs. | `InteractiveMirror` (C); the agent's pointer and the highlights are drawn by Quire from the session's injected input (HYPOTHESIS) | `mirror` |
| **Mirror, paused** | The automation chip turns grey, "Paused". A scrim over the mirror says "Paused · click in the mirror to act, or Take over". The mirror becomes interactive. Resume replaces Pause. | Quire stops forwarding the agent's input tool calls; `InteractiveMirror` made interactive (HYPOTHESIS, §7) | `mirror-paused` |
| **Done** | The steps fold into one chip ("4 steps ✓", expandable), one sentence of result, a sub-line with the count of changes and the time, and buttons: Undo, Show changes. The note stays until the person closes it; closing folds it into the pointer. | `session/prompt` returns `stopReason: end_turn` (C) | `done` |
| **Error** | A card with the error icon: what stopped, in one sentence; details behind a disclosure; Show log · Try again. The failed step stays in the list. | `stopReason` of `refusal`, `max_tokens`, `max_turn_requests`, `cancelled`; or `quired` reporting the agent's exit and stderr (C) | `error` |
| **Agent not signed in** | A card with the key icon: "Cursor needs to sign in", the agent's methods as rows, and Use Claude Code instead · Sign in. Sign-in happens in the agent's own flow. | `authenticate` with `authMethods`; error `-32000` (C) | `signin` |
| **Running in the background** | The note folds into the taskbar button. The button shows a progress ring and a count. Clicking it opens a tray: one row per task with status (needs your answer, running, done), the prompt, the agent, and New · History. A row opens that task's note. | Quire core's session list; a pending `request_permission` marks "needs your answer" | `background` |
| **Settings help** | Before Allow, the consent card lists each setting old → new. After Allow, a card "Changed 3 settings · just now" with the same rows, each with its own undo, and Undo all. The changed rows are outlined in the Settings window. | The settings tool's change log with undo (Q6) | `settings-help` |
| **Long output** | The note widens to 480 dp, the body scrolls, and a "Jump to latest" pill appears when the person scrolls up while text is still arriving. The footer offers "Open as a document". | Message chunks; the document opens in the Notes app (HYPOTHESIS) | `long-output` |
| **Code** | A block in Google Sans Code 12.5/18 on `inverse-surface` (light) or `surfaceContainerLowest` (dark), with the language and a copy button. Run it · Save as file. Running it would be a consent step. | Message chunks with fenced code; `tool_call.content` of type `content` | `code` |
| **Images** | A thumbnail with a caption and an expand button; it grows in place to the note's width. A pointer region intake is cropped to the region, never the whole screen. | `ContentBlock` of type `image` (C); the screenshot from `EXTRA_SCREENSHOT` cropped by Quire | `images` |
| **No agent connected** | The agent chip reads "not connected". A card lists the agents found and their state, with Pair a computer · Connect Claude Code. No composer: there is nobody to send to. | `quired agents` (C) | `no-agent` |
| **Offline** | For a paired computer or a cloud agent: "Brian's desk can't be reached", the prompt kept in the field, Retry · Use Claude Code on this laptop. Local agents are unaffected and show nothing. | Quire core's connector state | `offline` |

### 3.3 Consent rules

1. **Every change goes through a card.** Nothing that changes the system happens without Allow, unless the person gave standing permission for that tool in Quire's settings. The card always names the thing that changes, never only the tool.
2. **The buttons map to ACP's option kinds:** Allow → `allow_once`; Allow for this task → `allow_always`, which Quire scopes to the session (as `quired` does today, C); Don't allow → `reject_once`. `reject_always` is in the card's overflow as "Don't allow this again for this task", so a mistaken click cannot reach it.
3. **Focus lands on the card**, which TalkBack reads in full. The first Tab stop is Don't allow, then Allow for this task, then Allow. Enter activates only the focused button. There is no single-key shortcut.
4. **Esc while a card is open cancels the run**, which answers the request as `cancelled`, as ACP requires (C).
5. **Platform consent stays platform.** For computer control, the system dialog appears over everything and the note waits. If the dialog is denied, the note ends with "Settings was not opened. You didn't allow computer control."

### 3.4 The mirror

- The session display is 1280×800 dp, mirrored at 0.55 into a 736×460 dp view inside the 760 dp note. That keeps text legible at 1.5× and the whole note under 60 % of the G14's height.
- **The agent's pointer** is OpenBook's arrow with the body in brand blue `#4355B9`, so it is never mistaken for the person's own. A tap draws a 36 dp ring in `primary` that fades in 200 ms. The control the agent is about to use gets a 2 dp focus ring.
- **Pause** stops the agent's input and makes the mirror interactive, so the person can act inside the session and resume. **Take over** calls `handOverApplications()` (C): the app moves to the person's display, the session ends, the note folds to Done with "Settings is on your screen now". **Stop** closes the session and the app.
- The **automation indicator** is two things: the taskbar's Quire button breathing, and the platform's own indicator on the automated app (`enable_app_automation_indicator`, C). Only the first is drawn here; the second is the platform's.
- Secure content blocks the session (C). The mirror then shows the platform's block reason as an error row: "Settings showed a protected screen, so the session stopped."

### 3.5 The taskbar button and the tray

- The button sits in the taskbar's system group, right after All apps and before the divider. 44 dp, the leaf at 24 dp.
- **Idle:** the leaf. **Running:** the leaf breathes (1.6 s) and a 2.5 dp ring in `primary` shows progress when the agent has a plan; otherwise the ring spins. **Needs an answer:** a count badge in `primary`.
- Clicking opens the tray (400 dp) above the button with `spring.settle`. Each row: a status mark, the prompt on one line, the status line (needs your answer · running · done 4 min ago), the agent's name, a chevron. Rows open that task's note at the taskbar anchor.
- History lists finished tasks for 24 h with their undo lists.

### 3.6 Undo

- Every settings change Quire makes is a row with old → new and its own undo. Undo all restores the previous values in reverse order.
- Undo stays available in the note, and for 24 h from the tray's History (the Q6 audit log).
- Undo is itself a change and shows as a step, but needs no consent: it only restores what the person already allowed.

## 4. Visual system

### 4.1 Type

Google Sans for everything in the note (the system's `google-sans*` families, C). Google Sans Code for code. Sizes in sp; line height after the slash.

| Role | Size | Weight | Used for |
|---|---|---|---|
| `quire.type.prompt` | 15/22 | 500 | The person's prompt |
| `quire.type.body` | 15/22 | 400 | Answers, results |
| `quire.type.label` | 14/20 | 400 | Steps, plan entries, auth rows, field text |
| `quire.type.chip` | 13/20 | 500 | Agent chip, intake chip, buttons, card titles (600) |
| `quire.type.meta` | 12/16 | 400 | Footer, change rows' "where", timestamps, kbd hints |
| `quire.type.code` | 12.5/18 | 400 | Code blocks, commands, diffs (Google Sans Code) |
| `quire.type.sysdialog` | 22/28 | 400 | The platform dialog's title (platform-owned) |

### 4.2 Spacing and shape

| Token | Value |
|---|---|
| Spacing scale | 4, 8, 12, 16, 24, 32 dp. Block gap 10 dp inside the body; chip gap 6 dp; button gap 8 dp. |
| Note radius | 28 dp |
| Card radius | 16 dp |
| Mirror, image, code radius | 16, 12, 12 dp |
| Field radius | 20 dp |
| Chips, buttons | pill |
| Button height | 36 dp, 16 dp side padding (12 for text buttons) |
| Icon button | 32 dp, icon 20 dp |
| Composer buttons | 40 dp |
| Step row | 28 dp min height, 10 dp gap, 20 dp status mark, 16 dp kind icon |
| Focus ring | 2 dp `primary`, 2 dp offset (buttons: a 2 dp `surface` gap then 2 dp `primary`) |

### 4.3 Colour

All roles are Material 3 TonalSpot, derived by Android 17 from the current wallpaper. The prototype uses the values `scripts/brand/monet.py`'s library computes for the Folio wallpapers (seed `#959DE5` light, `#9F87FE` dark), which the device matched within 3 RGB units in ANAL-207 (C). Q5 reads them from the theme (`android.R.attr.colorPrimary` and the `system_*` palettes), never from constants.

| Use | Role | Light | Dark |
|---|---|---|---|
| Answer text, titles | `onSurface` | `#31323B` | `#E9E3EF` |
| Secondary text, footer, pending marks | `onSurfaceVariant` | `#5E5E68` | `#AEA9B5` |
| Filled button (Allow, send, Take over), progress ring, focus ring, focus rings in the mirror | `primary` / `onPrimary` | `#565B8C` / `#FBF8FF` | `#CBC0ED` / `#423B5F` |
| New value pill | `primaryContainer` / `onPrimaryContainer` | `#C0C5FD` / `#393E6D` | `#554D73` / `#E7DFFF` |
| Tonal button, intake chip, selected agent, Ask Quire toolbar item | `secondaryContainer` / `onSecondaryContainer` | `#E0E0F9` / `#4F5065` | `#3D394D` / `#C3BCD4` |
| Automation chip | `tertiaryContainer` / `onTertiaryContainer` | `#F0CBF8` / `#5C4166` | `#F1C0E6` / `#5E3958` |
| Error text, failed step, Stop | `error` | `#A8364B` | `#F97386` |
| Done check, mic indicator | `success`-tinted (from the green `system_accent` is not available; use `#2F6B45` / `#9BD5A8`, containers `#BDEBCB` / `#1E4A2F`) | | |
| Halo label, Jump pill, code block (light) | `inverseSurface` / `inverseOnSurface` | `#0E0E12` / `#E9E3EF` | `#FDF8FE` / `#31323B` |
| Card, field | `surfaceContainer` (light), `surfaceContainerHigh` (dark) | `#EFECF6` | `#201F26` |
| Note | `note-bg` | `surface` `#FBF8FE` at 92 % | `surfaceContainer` `#1A191F` at 80 % |
| Outline | `outlineVariant` | `#B2B1BC` | `#494650` |

The **brand gradient** (`#7E8CFF → #4355B9`, fold `#FFB38A → #FF7A9C`, halo conic through `#D08BFF`) appears only on the leaf glyph, the halo, and the agent's pointer in the mirror.

### 4.4 The glyph and the halo

- **Leaf:** a 24 dp page, 16×18 with 3.5 dp corners, the top-right corner folded as a 6 dp triangle in the spark gradient. In the note header at 22 dp, in chips at 14–16 dp, in the taskbar at 24 dp. While the agent thinks it breathes (§5). It is OpenBook's own; it is not a star, a sparkle or a ring of light.
- **Halo:** a 32 dp ring with a 2 dp conic stroke. Listening: 40 dp. It blooms with `spring.tick` and fades out 200 ms after the note has opened. It is never shown at the same time as the note at rest.

### 4.5 Contrast (measured)

`scripts/quire/contrast-check.py --md`, run on the prototype's tokens. "Worst backdrop" means the translucent note composited over black (for dark text) or white (for light text), which bounds every real backdrop under the blur.

| Pair (foreground on background) | Light | Dark | Target |
|---|---|---|---|
| Answer text on the note | 10.1:1 pass | 7.3:1 pass | 4.5:1 (worst backdrop) |
| Secondary text on the note | 5.1:1 pass | 8.0:1 pass | 4.5:1 (worst backdrop) |
| Secondary text on a card | 5.5:1 pass | 7.6:1 pass | 4.5:1 |
| Secondary text on a card (dark uses surface-high) | 5.2:1 pass | 7.1:1 pass | 4.5:1 |
| Filled button: Allow | 6.1:1 pass | 6.1:1 pass | 4.5:1 |
| Tonal button: Allow for this task | 6.1:1 pass | 6.1:1 pass | 4.5:1 |
| Text button: Don't allow | 5.1:1 pass | 5.4:1 pass | 4.5:1 (worst backdrop) |
| New value pill | 6.1:1 pass | 6.1:1 pass | 4.5:1 |
| Mic indicator | 9.6:1 pass | 7.7:1 pass | 4.5:1 |
| Automation chip (Using Settings) | 6.1:1 pass | 6.1:1 pass | 4.5:1 |
| Halo label, Jump pill | 15.3:1 pass | 12.1:1 pass | 4.5:1 |
| Danger text: Stop | 5.1:1 pass | 6.8:1 pass | 4.5:1 (worst backdrop) |
| Intake chip | 6.1:1 pass | 6.1:1 pass | 4.5:1 |
| Done check (icon, non-text) | 5.0:1 pass | 5.5:1 pass | 3.0:1 (worst backdrop) |
| Focus ring (non-text) | 5.1:1 pass | 5.4:1 pass | 3.0:1 (worst backdrop) |
| Pending-step outline (non-text) | 5.1:1 pass | 8.0:1 pass | 3.0:1 (worst backdrop) |
| Field outline on focus (non-text) | 5.5:1 pass | 10.2:1 pass | 3.0:1 |

What the check changed: at 84 % the light note failed three pairs (4.2:1) over a black backdrop, so the light note is 92 %. The pending step's ring was `outline` (2.8:1) and is now `onSurfaceVariant`. Other wallpapers give other roles; Q5 runs the same check against the device's actual palette for all eight OpenBook wallpapers, and the note's alpha is the one knob to turn if one fails.

### 4.6 Icons

Material Symbols Rounded (Apache-2.0, already in the tree for Settings), weight 400, optical size 24, filled for status marks and the mic indicator, outlined elsewhere. Kinds map to icons: read → `visibility`, edit → `edit`, delete → `delete`, move → `drive_file_move`, search → `search`, execute → `terminal`, think → `psychology`, fetch → `language`, other → `more_horiz`; Quire's own tools: setting → `tune`, app → `apps`, window → `select_window`.

## 5. Motion

### 5.1 Tokens

Springs are given as stiffness and damping ratio, mass 1, which is what Compose's `spring(dampingRatio, stiffness)` and `androidx.dynamicanimation.SpringForce` take. The settle time is the time to within 1 % at 60 Hz, for reference only; springs have no duration. Durations are for opacity and other non-spatial changes, with Material 3's easing.

| Token | Value | Settle | Used for |
|---|---|---|---|
| `quire.spring.unfold` | stiffness 380, damping 0.80 | ≈ 300 ms, one 3 % overshoot | The note out of the pointer or up from the taskbar |
| `quire.spring.settle` | 700, 0.90 | ≈ 170 ms | Reflow when content grows, the agent picker, the tray |
| `quire.spring.expand` | 300, 0.85 | ≈ 270 ms | The note into the mirror and back |
| `quire.spring.fold` | 900, 1.00 | ≈ 130 ms, no overshoot | The note into the pointer or the taskbar |
| `quire.spring.tick` | 1400, 0.70 | ≈ 150 ms (full size at ≈ 90 ms) | The halo bloom, the check-mark pop, the taskbar press |
| `quire.duration.fade` | 120 ms, standard `(0.2, 0, 0, 1)` | | Labels, chips, the caret, the tap ring |
| `quire.duration.fade.slow` | 200 ms, standard | | The halo out, the system dialog in |
| `quire.loop.breathe` | scale 1 → 1.08 → 1, 1600 ms, standard, loop | | The leaf while thinking, the mic ring, the taskbar button while an app is driven |
| `quire.loop.spinner` | 1 rotation per 1000 ms, linear | | The running step |
| `quire.loop.caret` | 1 Hz, step | | Streaming text |
| `quire.loop.levels` | 1100 ms ease-in-out per bar, staggered 50 ms | | The mic level bars |

### 5.2 Choreography

**Out from the pointer** (`invoke-shake` → `compose`)

1. t = 0: the halo scales 0 → 1 with `spring.tick`; the intake outline fades in over 120 ms. The label fades in at the same time.
2. t = 150 ms: the note appears at scale 0.2 with its transform origin on the hotspot and opacity 0, then scales to 1 with `spring.unfold` while its opacity goes to 1 over 120 ms. The label fades out over 120 ms.
3. t = 390 ms: the halo fades out over 200 ms. The field has focus from the first frame the note exists.

**Settle** (content arrives): the note's height, and width when it changes class, animate with `spring.settle` from the old size to the new. Content inside is laid out at its final position and fades in over 120 ms; nothing slides. If the note would leave the screen, its position moves with the same spring.

**Expand into the mirror** (`consent-system` → `mirror`): width 400 → 760 and height to fit, both with `spring.expand`; the mirror surface fades in over 200 ms once the size has settled 90 %. The transform origin stays where the note was anchored, so it grows away from the pointer. Back from the mirror uses the same spring in reverse.

**Steps tick:** a new step fades in (120 ms). When it completes, the check scales 0.6 → 1 with `spring.tick` and the spinner is replaced in the same frame. When the run ends, the step list collapses to its chip with `spring.settle`.

**Fold back** (`done` → nothing): scale 1 → 0.2 towards the transform origin (the hotspot, or the taskbar button's centre) with `spring.fold`; opacity 1 → 0 over the last 60 % of the travel. Into the taskbar, the note also translates to the button; on arrival the button does its press (`spring.tick`) and the ring or badge appears.

**The tray** opens from the button with `spring.settle` on scale 0.9 → 1 and a 120 ms fade, origin bottom centre.

### 5.3 Remove animations

Android's "Remove animations" sets the animator duration scale to 0 (`ValueAnimator.areAnimatorsEnabled()` is false). `SpringAnimation` does not read that scale, so Q5 checks it itself. With it on:

| Token | Behaviour |
|---|---|
| `spring.unfold`, `settle`, `expand`, `fold` | A cut to the final geometry. The note appears at rest and disappears in one frame. |
| `spring.tick` | The halo appears at full size; the check appears at full size; the taskbar button does not press. |
| `duration.fade`, `fade.slow` | 0 ms. |
| `loop.breathe` | Still. The thinking state is shown by the "Thinking…" line and the footer text instead of the glyph. |
| `loop.spinner` | A still ring with a 270° arc. |
| `loop.caret` | A still caret. |
| `loop.levels` | The bars show the current level and update without easing. |

Nothing is conveyed by motion alone: every state also has text or a shape, so Remove animations loses nothing.

### 5.4 Frame budget

The note is one window with a blurred backdrop; the only continuous work while idle is the caret (1 Hz) and the breathe loop on a 22 dp glyph. The mirror's cost is the platform's. Q5 measures the open, stream, consent and fold at 60 fps on the G14 (ANAL-219's acceptance), and the blur at the shade's radius is within B2's budget by construction (same radius, smaller area).

## 6. Accessibility

### 6.1 Keyboard paths

| Goal | Keys |
|---|---|
| Open Quire | Meta+Space; the assist key; Tab to the taskbar's Quire button and Enter |
| Send | Enter. Shift+Enter inserts a new line. |
| Stop a run | Esc (while working: cancels, and answers any open permission request as cancelled) |
| Close the note | Esc (when idle). A second Esc never does anything destructive. |
| Hold to talk | Hold the mic key or the assist key; release sends. Esc while holding cancels. |
| Change the agent | Tab to the chip, Enter, arrows, Enter. Esc closes the list. |
| Answer consent | Tab to Don't allow, Allow for this task, Allow; Enter. Nothing is chosen by default. |
| Mirror | Tab to Pause, Stop, Take over. When paused, Tab into the mirror to act inside the session; Esc returns to the buttons. |
| Scroll a long answer | Page Up / Page Down in the body; Ctrl+End jumps to latest |
| Copy a code block | Tab to the copy button, Enter; or select and Ctrl+C |
| Background | Tab to the header's background button, Enter; or Meta+Space again from anywhere |
| Open the tray | Tab to the taskbar's Quire button, Enter; arrows between tasks |

### 6.2 Focus order

Header left to right (leaf is not focusable): agent chip → background → close. Then the intake chip's remove button, then the body top to bottom (steps are a list, not focusable individually; cards and their buttons are), then the suggestion chips, then the field → mic → send. Initial focus: the field on open; the consent card when it arrives; the result's first button on Done; the first auth method on sign-in; Resume when paused. Focus never jumps while the person is typing; a consent card arriving during typing is announced and reachable with Tab, and takes focus only if the field is empty.

### 6.3 TalkBack

| Element | Role | Label and announcements |
|---|---|---|
| Halo | live region, polite | "Quire. Pointing at Settings." / "Pointing at a secure window; nothing is taken in." |
| Note | dialog | "Quire. Claude Code on this laptop." Opening announces the intake: "Taking in Settings, Display." |
| Agent chip | button | "Agent: Claude Code on this laptop. Change." |
| Intake chip | group with a button | "Taking in Settings, Display. Remove." / "Selection from Notes: 'The conference runs…'. Remove." |
| Field | edit text | "Ask Quire." Hint: "Enter sends, Shift Enter new line." |
| Mic | button | "Hold to talk." While held: "Listening." The transcript is a live region, polite. |
| Thinking | live region, polite | "Claude Code is thinking." once; not repeated per chunk. |
| Answer | text, live region polite | Announced in sentences as they complete, not per chunk. |
| Steps | list | Each: "Reading Display settings, done." / "Turning on Battery saver, running." Changes announced politely, one per step. |
| Plan | list | "Plan, 1 of 4 done." Entries: "2, Turn off notifications during the talk, high priority, in progress." |
| Consent card | group, live region assertive | "Claude Code asks to change 2 settings. Battery saver, off to on. Brightness level, 80 % to 40 %. You can undo this. Buttons: Don't allow, Allow for this task, Allow." |
| Mirror | image, live region polite | "Live view of Settings, used by Claude Code. Step 2 of 4, tapping Connected devices." Updates per step, never per frame. Paused: "Paused. The mirror is interactive." |
| Result | live region polite | "Done. Battery saver is on and brightness is at 40 %. Changed 2 settings. Undo available." |
| Error | live region assertive | "Claude Code stopped. The agent closed the connection before finishing. Nothing was changed." |
| Taskbar button | button | "Quire." / "Quire, 2 tasks running, 1 needs your answer." |
| Tray row | button | "Turn on Battery saver and lower the brightness. Needs your answer. Claude Code." |
| Mic indicator | image | "Microphone in use by Quire." |

### 6.4 Text size and display size

The note is laid out in dp and sp, so Display size and Text size apply. At Text size "largest" (1.3×), the note's width stays 400 dp and the body wraps; the three consent buttons wrap to two rows (Allow stays right-aligned on its own row). At 2× display scaling on the G14 the note is 800 px wide, still under half the screen.

### 6.5 Contrast

§4.5. Both themes pass, at the note's worst backdrop, for every text and non-text pair in the design.

## 7. Mapping to ACP and the OS tools, and what the Porter checks

Each state's driver, and whether it exists today. **C** is from `docs/quire.md` §2, §4 or §6. **⚑** marks a gap or an assumption to confirm before Q5 builds that state.

| State or element | ACP event or OS action | Status |
|---|---|---|
| Shake → halo | `GestureDetectionInteractor` → `invokeContextualSearch(ENTRYPOINT_SYSTEM_ACTION)` | C. ⚑ The halo must be drawn by SystemUI before the contextual search activity starts, so Q5 adds it to the contextual cursor's feedback path, not to Quire's activity. |
| Key → halo | `ROLE_ASSISTANT`, the assist key, Meta+Space | C for the role. ⚑ Meta+Space is Q2's; the "pointer moved in the last 10 s" rule needs the last pointer event time from SystemUI. |
| Intake: window under the pointer, name and screenshot | `EXTRA_SCREENSHOT`, `EXTRA_VISIBLE_PACKAGE_NAMES` | C for the screenshot and the packages. ⚑ Cropping to the window needs the window's bounds under the pointer (the OS tools' "list windows", Observe tier). |
| Intake: secure window | `EXTRA_FLAG_SECURE_FOUND` | C. |
| Ask Quire on a selection | `ACTION_PROCESS_TEXT` in the floating toolbar, with `EXTRA_PROCESS_TEXT` | ⚑ HYPOTHESIS: standard Android since 6.0 for apps that use the default text toolbar; the Porter confirms it reaches Quire's activity under the assistant role and what WebView and Compose text do. |
| Hold to talk | The assistant role's voice session; Q7's recogniser | ⚑ Q7. The design needs partial results (the grey partial words). |
| Agent chip and picker | `quired agents`; `initialize` → `authMethods` | C. |
| Streaming, thinking | `agent_message_chunk`, `agent_thought_chunk` | C. |
| Steps | `tool_call`, `tool_call_update` (`kind`, `status`, `title`) | C. |
| Plan | `plan` entries with `status`, `priority` | C. |
| Consent card buttons | `session/request_permission` → `allow_once`, `allow_always`, `reject_once`, `reject_always` | C. ⚑ "Allow for this task" = `allow_always` scoped by Quire to the session. The Porter confirms the OS tools' requests carry the structured old → new values the card shows, not only a title. |
| Consent: diff and command | `tool_call.content` of type `diff`; the title for commands | C for ACP. ⚑ Claude Code's adapter gives titles ("Run make test"); the diff content for its edits is to confirm. |
| Platform consent | `RequestComputerControlAccessActivity` | C. ⚑ Its look is the platform's; the render shows a stand-in. |
| Mirror | `InteractiveMirror` on the session display | C. ⚑ The mirror's size (1280×800 dp session display) is a choice to confirm against `ComputerControlSessionParams`. |
| Agent pointer and tap ring in the mirror | Drawn by Quire from the input it injects for the agent | ⚑ HYPOTHESIS: Quire core sees every injected tap and can draw it; confirm that `requestScreenshot` and input injection go through the core, not straight from the agent. |
| Pause | Quire core stops forwarding input tool calls; the mirror made interactive | ⚑ No platform "pause" is known. The design relies on Quire owning the input path. If the agent's `tool_call` blocks while paused, the step shows "Paused". |
| Take over | `handOverApplications()` | C. |
| Stop | Close the session | C (the user can close it). |
| Automation indicator | Launcher3 `enable_app_automation_indicator`; Quire's own taskbar breathe | C for the flag. ⚑ What the platform indicator looks like is unseen; the design adds the Quire button's breathe and does not draw the platform's. |
| Done, error | `stopReason`; `quired`'s exit and stderr report | C. |
| Not signed in | `authenticate`, `-32000 Authentication required` | C. |
| Background and tray | Quire core's session list | ⚑ Core-side state; the count of pending `request_permission` is what the badge shows. |
| Settings help, undo | The settings tool's change log with undo (Q6) | ⚑ Q6. The card needs each change's old value, new value and a stable id for undo. |
| Long output → document | Opens the text in Notes (or Files) | ⚑ Which app; HYPOTHESIS. |
| Images | `ContentBlock` type `image` | C. |
| Offline | Connector state in the core | ⚑ Core-side. |
| Taskbar button | Launcher3 taskbar | ⚑ A Launcher3 change (Q5); the position (after All apps) is a design decision. |

## 8. For Q5

- **One component, many states.** Build the note as one Compose surface with a state object that mirrors §3.2; the prototype's `quire.js` has that shape (`note(n)` takes `blocks[]`, `mirror`, `listening`, `consent`). Reflow is one `spring.settle` on size.
- **Layers.** The halo and the intake outline: SystemUI, above all windows, no touch. The note: a SystemUI overlay window that takes focus and keyboard, below the status bar and system dialogs. The tray: Launcher3's taskbar popup.
- **Springs:** `spring(dampingRatio, stiffness)` in Compose, or `SpringForce` in dynamicanimation. Check `ValueAnimator.areAnimatorsEnabled()` on every spring and snap when false (§5.3).
- **Dynamic colour:** use the theme's roles (§4.3) and run `scripts/quire/contrast-check.py` against the device's palette for the eight OpenBook wallpapers before sign-off; adjust only `note-bg`'s alpha.
- **Fonts:** `google-sans-text` for the note, `google-sans-flex` for nothing (the note has no display sizes), Google Sans Code for code (OFL; add it to the font set if it is not shipped yet, ⚑).
- **What to record for acceptance:** each screen id in §3.2 as a Cuttlefish capture next to its render, both themes; the four motion paths in §5.2 at 60 fps on the G14; the keyboard paths in §6.1 and the TalkBack labels in §6.3.

## 9. Edge states: covered and remaining

Covered in this design: empty (first run, `no-agent`), loading (streaming, steps, "Waiting for your permission"), error (`error`, denied consent, offline, secure window, blocked session), overflow (long output, code, wide note), long strings (prompt wraps; chips truncate with an ellipsis; the tray truncates the prompt to one line), keyboard focus (§6.2), light and dark (every screen), two sizes (both renders), text scaling (§6.4), Remove animations (§5.3).

Remaining, for Q5 to design in the build: right-to-left layout (the note mirrors; the halo and intake are symmetric; the pointer offset flips), a second display (the note opens on the display with the pointer), the lock screen (Quire does not open; the contextual cursor already requires the device to be unlocked, C), and the note's behaviour when the window under the pointer closes while the note is open (the intake chip stays; it is a snapshot).

## Reproduce

```text
scripts/quire/render-design.sh            # both sizes, every state, light and dark, into docs/quire-design/png/ and g14/
scripts/quire/render-design.sh fhd consent mirror   # one size, chosen screens
scripts/quire/contrast-check.py --md      # the table in §4.5; exit 1 if any pair fails
docs/quire-design/index.html?play=1       # the clickable prototype
```

Fonts are fetched into the host data dir (`~/anybook/quire/fonts`) and linked into `docs/quire-design/fonts/`, which is gitignored. Google Sans, Google Sans Flex and Google Sans Code are OFL-1.1; Material Symbols Rounded is Apache-2.0. The same trademark reading as ANAL-202 applies: the fonts are used, never named in the product.
