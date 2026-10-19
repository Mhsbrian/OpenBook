# Quire: the note, glass and ink (ANAL-227, revising ANAL-215)

As of 2026-10-19. This is the design for Quire's note: how a person calls Quire, works with an agent in the note, watches the agent act, is asked before anything destructive, and sees the result. It revises Q3 (ANAL-215, 2026-10-18) after the owner used the Q5 build on the G14 and set the direction on ANAL-225: the note must be clear, glassy and holographic, feel like a tangible pen on paper, and be effortless. Everything Q3 got right stays: the states, the keyboard paths, TalkBack, honest copy after a stop, the platform's own consent for computer control. What changes is the material, the motion, how much is on screen in the first moment, and the consent model, which follows Q6 (ANAL-220): the agent reads and acts freely and asks only before a destructive action.

The brief is `docs/quire.md` §1; the platform facts the design relies on are `docs/quire.md` §2, §4 and §6, and Q3's mapping in §9 here.

Labels: **C** = confirmed (read in a primary source, in `docs/quire.md`'s confirmed sections, or measured here), **HYPOTHESIS** = a design assumption the Porter checks (§9 and §10 list them).

- **Prototype:** [`quire-design/index.html`](quire-design/index.html). Open it for the gallery; add `?play=1` for the clickable version (shake the pointer, press Meta+Space, click the taskbar button, hold the mic, select text; type "open chrome and go to fox news", "turn on dark theme", "delete the newest file in downloads" or "in settings, find bluetooth and turn it off" to see the Q6 paths; Esc stops a run or closes an idle note; the HUD toggles Remove animations and Blur off). `?wall=bloom|strata|tide` puts another wallpaper behind the glass; `?glass=0` renders the platform's blur-off fallback.
- **Renders:** [`quire-design/png/`](quire-design/png/) (1920×1080, PNG, plus `gallery.png` with every state and `wallpapers.png` with the note over all eight OpenBook wallpapers) and [`quire-design/g14/`](quire-design/g14/) (2880×1800, the G14 panel at 240 dpi, so 1920×1200 dp at 1.5×; JPEG q92 4:4:4). Every state, light and dark. `scripts/quire/render-design.sh` regenerates them.
- **Contrast:** `scripts/quire/contrast-check.py` reads the tokens from the prototype and checks every pair in §7.4 through its whole stack (paper over glass over the backdrop) at the worst backdrop; `scripts/quire/q7-contrast.py` does the same on the system's own roles for all eight wallpapers, light and dark. Both pass at the glass's 80 % (§7.4).

Every value on the screens is sample data. The desktop, Settings, Chrome and Notes are stand-ins drawn in Google Sans with OpenBook's circle icons and corner radii, so the note can be judged against the real look.

## Summary

- **Glass.** The note is the system's background blur at the shade's radius (34 dp) under the note's own colour at 80 %, lit from the top-left, with a 1.5 dp holographic rim in the brand's hues and a deep soft shadow. It is a pane of glass laid on the desktop; what is behind it shows through as colour. Cards inside are sheets of paper on the glass. Text is ink.
- **A pen on paper.** The sheet unrolls from the pen tip. The person's words are written in ink and the pen rules a line under them. The agent's words arrive as ink, word by word. Each tool call is a mark: an ink dot while it runs, a tick drawn as a stroke when it is done. The rim's light turns slowly while the agent works and stands still when it is done. Closing rolls the sheet back into the pen.
- **Effortless.** The first moment is two things: one field with focus, and one quiet line under it that names the agent, what was taken in, and how to leave. No header, no chips, no suggestions, no buttons. Q3's first moment had eleven interactive things on screen; this has four. The agent acts without asking, each change carrying its own Undo; the only question is before a destructive action.
- **Measured, with fallbacks.** The blur is the platform's; ANAL-203 measured its cost (§4.5). When the platform turns blur off (battery saver, thermal, Developer options) the note becomes near-opaque paper with the same layout, and every loop stops. Contrast is scored through the translucent stack at the worst backdrop and passes on all eight wallpapers at 80 %; alpha is the one knob.

## 1. The idea

The person is in the middle of something. Quire must arrive without asking them to look elsewhere, show what it understood, work in plain sight, ask only when it must, and leave without a trace. So:

- **One sheet, the note.** Composing, streaming, steps, plans, the destructive question, the mirror, the result and the undo list are states of one pane of glass, not separate panels. The sheet reflows between them with one spring.
- **Three things always on the quiet line:** which agent is answering, what Quire took in, and how to leave. It is the last line of the note in every state. There is no header.
- **The pen.** The note is a sheet that the pen draws out, writes on, marks, and rolls away. Every motion is a thing the pen does; nothing moves for decoration.
- **Nothing happens off screen.** Steps tick in the note. The mirror is in the note. Background work lives behind the taskbar button, with a ring for progress and a count.
- **Ask only before harm.** Q6's rule: the agent reads, reviews and changes the laptop through Quire's tools without asking; every change carries its own Undo. The one card that asks is for a destructive action (delete, uninstall, clear data, send, pay, the lock screen, accounts, adb). The platform's own consent for computer control stays the platform's (§3.3).

## 2. Invocation

What the person does, what appears in the first 100 ms, where the note anchors, and what Quire takes in. Unchanged from Q3 except the note's arrival (§5.2).

| Entry | First 100 ms | Anchor | Intake | Screen |
|---|---|---|---|---|
| **Shake** the pointer (contextual cursor gesture, C; Meta+G reaches the same path, C) | The **halo** blooms around the hotspot: a 32 dp ring, 2 dp, brand conic gradient, 0 → 1 with `spring.tick` (full size in ≈ 90 ms). The window under the pointer gets the **intake outline**. Label "Ask Quire" fades in beside it (120 ms). Then the sheet unrolls from the hotspot (§5.2). | The hotspot, 18 dp right and below | The window under the pointer: its name, the display screenshot cropped to `sourceBounds`, and the selection if it has one | `invoke-shake`, `open` |
| **Meta+Space**, the assist key, the Copilot key (`KEY_GESTURE_TYPE_LAUNCH_ASSISTANT` → the assistant role's voice-interaction session, C) | Same halo at the pointer if it moved in the last 10 s, with the label "Quire Meta Space". If the pointer has been still longer than that, or is off screen, the sheet rises from the taskbar button instead. | As above, or the taskbar button | The focused window, from the assist data (C) | `invoke-key` |
| **Taskbar button** | The leaf glyph scales 1 → 0.9 → 1 (`spring.tick`) and the sheet unrolls upward from it. No halo. | Centred on the button, 12 dp above the taskbar | Nothing. The quiet line offers "Add what's on screen". | `invoke-taskbar` |
| **Hold to talk** (the mic key, or hold the assist key; Q7) | The halo appears as a 40 dp **mic ring** that breathes; the mic indicator and the privacy dot show in the status bar. The note opens as the listening sheet with the live transcript in ink. Release sends. | The pointer | The focused window | `invoke-voice` |
| **Ask Quire on a selection** (`ACTION_PROCESS_TEXT`, C) | Android lists the handler in the text toolbar's overflow as a plain label (C). The selection keeps its highlight; the halo appears at the pointer when the item is chosen. | The pointer | The selected text, quoted on the quiet line, plus the window name from `getCallingPackage()` (C) | `invoke-selection` |
| Any entry over a **secure window** (`EXTRA_FLAG_SECURE_FOUND`, C) | The halo answers as usual. | The pointer | Nothing. The quiet line reads "Secure window · nothing taken in" with a lock. | `invoke-secure` |

Rules (unchanged from Q3): the halo tracks the pointer until the note opens; Esc or a click elsewhere cancels it with a 200 ms fade. The intake outline is a 2 dp stroke in `primary` at 55 % with a 10 dp glow at 18 %. The halo and the outline are drawn by SystemUI above all windows; the intake's bounds come from SystemUI (`ContextualSearchConfig.sourceBounds`, C). Quire must be force-queryable (C).

## 3. The note

### 3.1 Anatomy and geometry

The first moment, and the note once it has grown:

```text
┌─ the first moment ──────────────────────────────────┐  width 400 dp, height 88 dp
│ ( [leaf] Ask Quire|                      [mic] [↑] ) │  the field: 44 dp, radius 22, paper on glass
│ [CC Claude Code] · [▭ Settings · Display]      Esc close ✕ │  the quiet line: 12/16, 24 dp tall
└──────────────────────────────────────────────────────┘

┌─ grown ─────────────────────────────────────────────┐  14 dp top, 16 sides
│ Turn on dark theme                                   │  the prompt in ink, 15/22, 500
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│  the rule: 1.5 dp primary, fading to the right
├─ body (scrolls) ─────────────────────────────────────┤  10 dp top, 10 dp between blocks
│ ✓  ◉ Reading Display settings                        │  steps: 28 dp rows
│ ✓  ⚙ Settings: Dark theme on            [↶ Undo]     │  a change carries its undo, on paper
│ ◉  Dark theme is on.                                 │  result
│    Changed 1 setting · 2 s                           │
├─ composer ───────────────────────────────────────────┤  8 dp top, 10 sides
│ ( [leaf] Ask a follow-up                 [mic] [↑] ) │
│ [CC Claude Code] · [▭ Settings]      Done  Esc close ✕ │  the quiet line
└──────────────────────────────────────────────────────┘
```

| Property | Value |
|---|---|
| Width | 400 dp. **Wide** 480 dp when a code block or a long answer arrives. **Mirror** 760 dp. |
| Height | The first moment is 88 dp. Max 60 % of the display height; the body scrolls, the prompt, composer and quiet line stay. The mirror is the one exception: 748 dp tall (§3.4). |
| Corner radius | 28 dp (`config_dialogCornerRadius`, C). Paper inside: 16 dp. The field: 22 dp. Pills and buttons: pill. |
| Surface | **Glass** (§4.1): the system's background blur at 34 dp under `surface` at 80 % (light) or `surfaceContainer` at 80 % (dark); a 1 dp specular line inside the top edge; the holographic rim; a bloom from the top-left; shadow 0 24 48 at 22 % of `#1B1B21` (light) or 55 % black (dark). |
| Placement from the pointer | hotspot + (18, 18) dp. Flips to the left of the hotspot when it would come within 24 dp of the right edge. Moves up to stay 16 dp above the taskbar; the transform origin stays on the hotspot, so the sheet still unrolls from the pen. |
| Placement from the taskbar | Centred on the Quire button, 12 dp above the taskbar. Transform origin: bottom centre; the sheet unrolls upward. |
| Layer | Above app windows, below the system dialogs, the status bar and the mic indicator. Owned by Quire core (`TYPE_APPLICATION_OVERLAY` as a privileged app, C: Q5 built it so). The halo and the intake outline stay in SystemUI. |

### 3.2 States

Each state is one screen in the prototype, in light and dark, at both sizes. New since Q3 are marked **Q6** or **Q7**; §9 maps each to what drives it.

| State | What the note shows | Driven by | Screen |
|---|---|---|---|
| **The first moment** (Q7) | The field with focus and the leaf in it; the quiet line: agent, intake, Esc close, ×. Nothing else. | Local | `open`, `invoke-taskbar`, `invoke-secure`, `invoke-selection` |
| **Composing** | Typed letters appear at once (typing is the person's own act; no latency is added). The field grows to 4 lines, then scrolls. The quiet line reads "Enter send". | Local | `compose` |
| **Listening** | Seven level bars in `primary`, the transcript in ink with the partial word in soft ink, the quiet line "Listening · release to send · Esc cancel". | Q7's speech to text | `invoke-voice` |
| **Choosing the agent** | The agent's name on the quiet line opens a glass list above it, grouped by where agents run, each with its sign-in state. The last used agent is preselected. | `quired agents`, `initialize` → `authMethods` (C) | `agent-picker` |
| **Streaming** | The prompt in ink under the rule. "Thinking…" with the breathing leaf until the first message chunk; then the answer arrives as ink, word by word (§5.2). The rim's light turns. Quiet line "Answering · 2 s · Esc stop". | `agent_thought_chunk`, `agent_message_chunk` (C) | `streaming` |
| **Tool steps** (Q6) | One line per tool call: a mark, a kind icon, the title with the value in medium weight ("Going to **foxnews.com**"). Running: the ink dot. Done: a tick drawn as a stroke in `success`. Failed: a cross in `error`. No card, no question. | `tool_call`, `tool_call_update` with `kind`, `status`, `title` (C); Quire's tools report the value | `steps` |
| **A change, with its undo** (Q6) | A step that changed a setting ("Settings: Dark theme **on**") carries an Undo pill on paper at its right. Undo turns the pill into "Undone" and strikes the step. The result line sums it up: "Dark theme is on. · Changed 1 setting · 2 s". | The settings tool's change log (Q6) | `setting-undo` |
| **Plan** | A paper card "Plan · 1 of 4" with a numbered list; done entries get a check and a strike; the active entry's number fills with `primary`. | `plan` with `entries[].status` and `priority` (C) | `plan` |
| **The destructive question** (Q6) | The run stops. A paper card rimmed in `error` at 70 %: the delete icon, "Delete this file?", the file on its own row (icon, name, where · size · when), one sentence on what happens and whether it can be undone, and two buttons: **Delete** on `errorContainer`, **Keep it** filled in `primary`. Keep is the default focus. | Quire's broker, before a destructive tool call (Q6); options are Quire's own | `confirm-destructive` |
| **An agent's own request** | ACP agents may still ask before their own actions (a file write, a command). The same paper card as Q3 with the diff or the command and the agent's own options, labelled by the agent (§3.3 rule 3). Quire's tools never raise this card for a non-destructive action. | `session/request_permission` with `options[]` (C) | `consent-command` |
| **Consent, computer control** | The platform's own dialog appears (not Quire's, C). The note shows "Asking to use Settings" as a running step and "Waiting for your permission". | `onSessionPending` → `RequestComputerControlAccessActivity` (C) | `consent-system` |
| **Live mirror** | The note expands to 760 dp. The session display shows as a pane set into the glass (16:10, 16 dp radius, an inner shadow), zoomed 2× on the control the agent acts on, with the agent's pointer in brand blue and a tap ring. Under it the steps, then Stop (on `errorContainer`) · Pause (paper) · Take over (filled), then the quiet line. | `InteractiveMirror` (C); pointer and highlights drawn by Quire core (C) | `mirror` |
| **Mirror, paused** | The automation chip turns grey, "Paused"; the view returns to the whole display; a scrim says "Paused · click in the mirror to act, or Take over"; Resume replaces Pause. | `notifyBlocked()` + `setInteractive(true)`; `requestUnblock()` (C) | `mirror-paused` |
| **Done** | The steps fold into one chip on paper ("4 steps ✓"), one sentence of result, a sub-line with the count of changes and the time, and Undo on paper. The note stays until the person closes it; closing rolls the sheet into the pen. | `stopReason: end_turn` (C) | `done` |
| **Stopped** | After Esc or Stop. The steps stay with the interrupted one marked; "Stopped after 3 of 4 steps." and the honest sub-line (§3.3 rule 6); each confirmed change keeps its Undo. | `session/cancel`; `stopReason: cancelled` (C) | `stopped` |
| **Error** | A paper card rimmed in `error` at 50 %: what stopped, details behind a disclosure, Show log · Try again (paper). | `stopReason` of `refusal`, `max_tokens`, `max_turn_requests`; `quired`'s exit report (C) | `error` |
| **Agent not signed in** | A paper card with the key icon, the agent's methods as rows, Use Claude Code instead · Sign in. | `authenticate` with `authMethods`; error `-32000` (C) | `signin` |
| **Hidden, running in the background** | The sheet rolls into the taskbar button. The button shows a progress ring and a count. The tray, in the same glass, lists tasks: needs your answer, running (the ink dot), done. | Quire core's session list | `background` |
| **Several settings changed** | A paper card "Changed 3 settings · just now" with old → new rows, each with its own undo, and Undo all. The changed rows are outlined in Settings. | The settings tool's change log (Q6) | `settings-help` |
| **Long output** | The note widens to 480 dp, the body scrolls, "Jump to latest" appears when the person scrolls up while text arrives; "Open as a document" on the quiet line. | Message chunks; the Storage Access Framework (C) | `long-output` |
| **Code** | A block in Google Sans Code 12.5/18 on `inverseSurface` (light) or black at 55 % on the glass (dark), with the language and a copy button. | Message chunks with fenced code | `code` |
| **Images** | A thumbnail on paper with a caption and an expand button; a region intake is cropped to the region. | `ContentBlock` of type `image` (C) | `images` |
| **No agent connected** | The quiet line reads "not connected". A paper card lists the agents found with Pair a computer · Connect Claude Code. No field: there is nobody to send to. | `quired agents` (C) | `no-agent` |
| **Offline** | "Brian's desk can't be reached", the prompt kept in the field, Retry · Use Claude Code on this laptop. | Quire core's connector state | `offline` |
| **Blur off** (Q7) | The same layout as paper at 96 %, no bloom, the rim at 60 % of its opacity, the shadow kept. No loop runs. | `WindowManager.isCrossWindowBlurEnabled()` false (§4.5) | `glass-off` |

### 3.3 Consent rules

Q3's rules 3 to 6 stand; rules 1 and 2 follow Q6.

1. **Act, then show; ask only before harm.** Quire's tools (settings, apps and the web, the screen, files, windows, clipboard, media) run without a card. Every call is a step; every change is a step with its own Undo. The broker raises a card only for the destructive tier Q6 defines: deleting files, uninstalling or disabling apps, clearing app data, factory reset, sending messages or email, purchases, changing the screen lock, accounts, adb or developer settings. The card names exactly the thing (the file, the app, the recipient) and what happens, never only the tool.
2. **The destructive card is Quire's own.** Two options, Quire's wording: the destructive verb ("Delete", "Uninstall", "Send") on `errorContainer`, and the safe one ("Keep it", "Keep the app", "Don't send") filled in `primary`. The safe option takes focus; Enter on the card does nothing until a button is focused. There is no "always allow" for a destructive action.
3. **An agent's own request keeps the agent's options.** `session/request_permission` carries `options[]` with the agent's `optionId`, `name` and `kind`; Quire renders them as the agent named them, reject kinds first, `allow_once` last, styled by kind (text, tonal, filled), and returns the chosen `optionId` (C). `quired` pre-allows Quire's own tools for Claude Code so one call raises one card (C); ⚑ native ACP agents may still ask before calling a Quire tool; Q6 handles that agent by agent.
4. **Focus lands on the card**, which TalkBack reads in full. Tab then moves through the options in the order shown. Enter or Space activates only the focused button. There is no single-key shortcut.
5. **Esc while a card is open stops the run.** The pending request is answered with `outcome: cancelled` (C), `session/cancel` is sent, and the note shows Stopped. For the destructive card, Esc deletes nothing. Esc never hides a running task; hiding is the × on the quiet line, Meta+Space, the taskbar button, or a click elsewhere.
6. **Platform consent stays platform**, with Q3's copy for `ERROR_PERMISSION_DENIED`, `ERROR_DEVICE_LOCKED` and `ERROR_SESSION_LIMIT_REACHED` (C).
7. **Copy after a stop or an error is honest about effects** (Q3 rule 6, unchanged): what is confirmed changed (each with Undo), what is confirmed unchanged, and what was interrupted and may be partly applied, with where to check. Cancellation is not rollback.

### 3.4 The mirror

Unchanged from Q3 in behaviour (the session display is the reference display, C; the view zooms 2× on the agent's target; Pause is `notifyBlocked()` + `setInteractive(true)`, Resume is `requestUnblock()`, Take over is `handOverApplications()`, C; secure content and biometric prompts block the session and do not close it, C). What changes is the look: the mirror is a pane set into the glass, with an inner shadow (0 2 10 at 28 % black) and a 1 dp paper outline, so it reads as a window in the sheet rather than a card on it. Stop sits on `errorContainer`, Pause on paper, Take over filled. The note's own blur is cut out under the pane (Q5 already does this, C: the mirror's surface sits below the window).

### 3.5 The taskbar button and the tray

As Q3: the button after All apps, 44 dp, the leaf at 24 dp; running: the leaf breathes and a 2.5 dp ring in `primary` shows progress; needs an answer: a count badge. The tray is the same glass as the note; rows on hover lift onto paper; a running row shows the ink dot.

### 3.6 Undo

- Every change Quire makes is undoable from the step that made it, from the Done card's "Undo" (one change) or "Undo all", and for 24 h from the tray's History (the Q6 audit log).
- Undo is itself a step and needs no question: it restores what the person already had.
- A destructive action that the platform can reverse (a file to the bin) says so on the card and offers Undo on its step; one it cannot reverse says "This can't be undone." on the card.

## 4. Material: glass, paper, ink

Three materials, each with one job. Glass is the note: it shows what is behind it. Paper is anything laid on the glass that the person can act on: cards, the field, pills. Ink is text and marks. Brand colour appears only on the leaf, the halo and the rim.

### 4.1 Glass

| Token | Light | Dark | What it is |
|---|---|---|---|
| `quire.glass.blur` | 34 dp | 34 dp | The system's background blur (`BackgroundBlurDrawable`, C: Q5 uses it), at the radius SystemUI's shade uses (C); 51 px at 240 dpi |
| `quire.glass.tint` | `surface` at 80 % | `surfaceContainer` at 80 % | The note's own colour over the blur. 80 % is the lowest alpha at which every pair in §7.4 passes at the worst backdrop on all eight wallpapers (§7.4) |
| `quire.glass.specular` | white at 75 %, 1 dp, inside the top edge | white at 18 % | Light on the top edge of the pane |
| `quire.glass.outline` | white at 55 %, 1 dp, inside | white at 14 % | The pane's edge where it meets the desktop |
| `quire.glass.rim` | 1.5 dp conic stroke of the halo's hues (`#7E8CFF → #C58BFF → #FF7A9C → #FFB38A → #8FD6FF`), at 70 % | the same hues lightened (`#A9B6FF → #DDBDFF → #FFB0C4 → #FFD3B3 → #B8E8FF`), at 80 % | The holographic edge: the halo's light, caught in the glass. Its angle starts at 200° (brightest at the top-left) and turns while the agent works (§5.1) |
| `quire.glass.glow` | `#7E8CFF` at 18 %, 24 dp | `primary` at 16 %, 24 dp | A soft outer glow on the rim |
| `quire.glass.bloom` | white at 34 %, radial from the top-left corner, to 62 % of the width | white at 7 % | Light falling on the glass |
| `quire.glass.shadow` | 0 24 48 at 22 % `#1B1B21`, plus 0 2 6 at 8 % | 0 24 48 at 55 % black, plus 0 2 6 at 30 % | Depth: the sheet floats above the desktop |
| Prototype only | `saturate(1.4)` on the blurred backdrop | | CSS only. Android's blur has no saturation; the tint at 80 % does the work on the device, and the renders are a touch more vivid than the build will be (HYPOTHESIS until the Porter's capture; §10) |

The glass is drawn in three layers, back to front: the blur (platform), the tint with the specular and outline (one rounded rect), and the rim with its glow (one stroked path). The bloom is a radial gradient in the tint layer. Nothing else is translucent over the desktop; paper is translucent over the glass only.

### 4.2 Paper

| Token | Light | Dark | Used for |
|---|---|---|---|
| `quire.paper` | `surfaceContainerLowest` at 72 % | `surfaceContainerHigh` at 80 % | Cards: plan, the destructive question, an agent's request, changes, error, sign-in, agents; the folded-steps chip; the undo pill; paper buttons |
| `quire.paper.line` | white at 90 %, 1 dp, inside the top edge | white at 10 % | The lit edge of a sheet |
| `quire.paper.outline` | `outlineVariant` at 40 % | `outlineVariant` at 60 % | The sheet's edge |
| `quire.field` | `surfaceContainerLowest` at 80 % | `surfaceContainerHighest` at 85 % | The field, change rows, the command chip, the diff, details |
| Radius | 16 dp cards, 22 dp field, 10 dp rows, pill for pills | | |

Paper sits on glass, so the same word can be read as "a sheet on the pane": it is a little more opaque than the glass, lit on its top edge, and never blurred on its own (the glass under it already is).

### 4.3 Ink

| Token | Light | Dark | Used for |
|---|---|---|---|
| `quire.ink` | `onSurface` | `onSurface` | Answers, the prompt, titles, step titles, text buttons, pill labels |
| `quire.ink.soft` | `onSurface` blended 85 % over the note's colour (`#4F5058` on Folio) | the same (`#CAC5D0` on Folio) | The quiet line, kind icons, pending steps, placeholders, sub-lines, card metadata |
| `quire.ink.rule` | `primary` at 55 %, fading to transparent at the right | the same | The rule under the prompt |
| `quire.ink.caret` | `primary`, 2 dp | the same | The caret in the field and at the end of streaming text |
| `quire.ink.mark` | `primary` (the running dot), `success` (the tick), `error` (the cross) | the same | The pen's marks on steps |

Soft ink is derived, not a fixed grey: `onSurfaceVariant` fails at the worst backdrop once the glass is below 92 % (ANAL-215 measured 4.0:1 at 80 %), while `onSurface` at 85 % over the note passes at 80 % on every wallpaper (§7.4). The build computes it from the two roles.

### 4.4 Buttons on glass

| Kind | Look | Used for |
|---|---|---|
| Filled | `primary` / `onPrimary` | The safe choice (Keep it), Take over, Connect, Sign in, send |
| Tonal | `secondaryContainer` / `onSecondaryContainer` | An agent's `allow_always` option; the picker's selection |
| Paper | `quire.paper` with its line and outline, label in ink | Undo, Pause, Try again, Run it, New, Use another agent |
| Text | Label in ink, no surface | Show changes, Show log, History, an agent's reject option |
| Stop pill | `errorContainer` / `onErrorContainer`, with the stop icon | Stop in the mirror; the destructive verb (Delete) |

Text buttons are ink, not `primary`: at the worst backdrop a `primary` label on 80 % glass is 3.8:1 in light (§7.4), and ink is 7.5:1. The same holds for Stop: `error` as text is 3.4:1 on the dark glass over white, so Stop and Delete sit on `errorContainer`, which is 4.5:1 or better on every wallpaper (the closest pair in the whole design; the system's own role pair).

### 4.5 Cost and fallbacks

**What the blur costs (C, ANAL-203, `docs/googlebook-ui.md` §2.3).** The shade's blur in Cuttlefish costs SurfaceFlinger 2.8 to 4.0 ms of RenderEngine time per GPU-composed frame, full screen at 1920×1080 at 60 Hz; on the G14 the shade draws its blur at radius 51 px with no GPU hang, and its per-frame cost is still unmeasured (`frame_cost` waits for the graphics check). The G14 thresholds B2 set are RenderEngine ≤ 6 ms average and p90 ≤ 8 ms per GPU-composed frame, against a 120 Hz frame of 8.3 ms. Blur forces GPU composition for the frame, which on the G14 is the case for most frames anyway (`use_overlay_planes=false`, C).

**What the note asks for.** The note blurs only its own area: 400×88 dp in the first moment and at most 480 dp × 60 % of the display height when grown, so at 1.5× between 0.16 and 0.7 Mpx of the G14's 5.2 Mpx panel, 3 % to 13 % of what the shade blurs. The Kawase dual filter's cost scales with the blurred area, so the note's blur should cost between 0.1 and 0.6 ms per frame by proportion (HYPOTHESIS; a different GPU and a smaller surface, so the Porter measures it, §10). The mirror state cuts the blur out under the pane (Q5, C), which keeps the largest note at the same cost as a 760×180 dp strip.

**Budgets the Porter measures against, on the G14 at 120 Hz** (the acceptance for this issue):

| Path | Budget |
|---|---|
| The note's blur | ≤ 1.5 ms RenderEngine per GPU-composed frame while the note is up, measured as B2 does (`scripts/ui/blur-report.py`'s method on `dumpsys SurfaceFlinger --timestats`) |
| Open (unroll + rim) | ≤ 2 janky frames in the open, `dumpsys gfxinfo dev.openbook.quire` |
| Streaming (ink, 10 s answer) | janky frames ≤ 5 % |
| Fold | ≤ 1 janky frame |
| Rim while working | one invalidation per frame of the rim view only, ≤ 0.3 ms CPU; nothing else redraws |
| Idle note | zero invalidations except the caret at 1 Hz |

If the blur budget fails, the knob is the radius (34 → 24 dp), not the alpha; if the rim's turn fails, it stands still (the design loses nothing, §5.3).

**Blur off.** `WindowManager.isCrossWindowBlurEnabled()` is false, with a listener for changes (`addCrossWindowBlurEnabledListener`), when WM's `BlurController` turns blur off: battery saver, thermal status SEVERE or above, tunnel mode, or `Settings.Global.disable_window_blurs` from Developer options (C for the controller's rules, `docs/googlebook-ui.md` §2.3; ⚑ the Porter confirms the API in our tree). This is also the "Reduce transparency" case: Android has no such setting, so the platform's own switch is the one honoured. With it off:

| | Glass on | Blur off |
|---|---|---|
| Note | tint at 80 % over the blur | tint at 96 %, no blur |
| Bloom | on | off |
| Rim | 70 % / 80 % | 60 % of that, no glow |
| Paper, field | translucent | opaque (`surfaceContainerLowest` / `surfaceContainerHigh`) |
| Shadow, outline, specular | on | shadow and outline on; specular off |
| Loops (rim turn, leaf breathe, ink dot, caret) | on | off: economy. The running mark is a still dot with a halo; the rim stands at 200° |

Contrast at 96 % passes trivially (every pair is at or above its glass-on value). The layout does not change, so nothing moves when blur switches mid-task; the note re-draws its surface on the listener.

**Remove animations** (`ValueAnimator.areAnimatorsEnabled()` false) is separate from blur off and is §5.3: every spring and fade is a cut, the glass stays.

## 5. Notepen to paper: motion

### 5.1 Tokens

Springs are stiffness and damping ratio, mass 1 (Compose `spring(dampingRatio, stiffness)`, `SpringForce`). Durations are for non-spatial changes, with Material 3's easing. The last column is the Remove-animations behaviour.

| Token | Value | Settle | Used for | Remove animations |
|---|---|---|---|---|
| `quire.spring.unfold` | stiffness 380, damping 0.80 | ≈ 300 ms, one 3 % overshoot | The sheet's scale 0.6 → 1 out of the pen or up from the taskbar | A cut to the final geometry |
| `quire.spring.settle` | 700, 0.90 | ≈ 170 ms | Reflow when content grows; the picker; the tray | A cut |
| `quire.spring.expand` | 300, 0.85 | ≈ 270 ms | The note into the mirror and back; the mirror's zoom | A cut |
| `quire.spring.fold` | 900, 1.00 | ≈ 130 ms, no overshoot | The sheet back into the pen or the taskbar | A cut |
| `quire.spring.tick` | 1400, 0.70 | ≈ 150 ms (full size at ≈ 90 ms) | The halo bloom, the taskbar press | Appears at full size |
| `quire.duration.unroll` | 220 ms, emphasised decelerate `(0.05, 0.7, 0.1, 1)` | | The sheet's clip from 0 to its full height, from the origin | A cut |
| `quire.duration.rim` | 200 ms, standard `(0.2, 0, 0, 1)` | | The rim lighting up at the end of the unroll | Lit at once |
| `quire.duration.unwrite` | 160 ms, emphasised accelerate `(0.3, 0, 0.8, 0.15)` | | The rim going dark before the fold | Dark at once |
| `quire.duration.ink` | 160 ms, standard; stagger 24 ms per word, at most 6 words in flight | | A word arriving: opacity 0 → 1 and a 2 dp rise | Appears at once |
| `quire.duration.rule` | 240 ms, emphasised decelerate, after a 120 ms delay | | The rule drawn left to right under the sent prompt | Drawn at once |
| `quire.duration.draw` | 180 ms, emphasised decelerate | | A tick or cross drawn as a stroke (path length 17 dp and 23 dp at 20 dp) | Drawn at once |
| `quire.duration.fade` | 120 ms, standard | | Labels, the halo label, the tap ring, a new step row | 0 ms |
| `quire.duration.fade.slow` | 200 ms, standard | | The halo out, the system dialog in, Chrome appearing behind the note | 0 ms |
| `quire.loop.rim` | one turn per 12 s, linear, while the agent works | | The rim's light moving around the sheet: "it is thinking" | Still, at 200° |
| `quire.loop.breathe` | scale 1 → 1.08 → 1, 1600 ms, standard | | The leaf while thinking, the mic ring, the taskbar button while an app is driven | Still |
| `quire.loop.inkdot` | scale 1 → 1.35 → 1 and opacity 0.9 → 0.55 → 0.9, 900 ms, ease-in-out | | The running step's mark | A still dot with a 3 dp halo at 30 % |
| `quire.loop.caret` | 1 Hz, step | | The caret | A still caret |
| `quire.loop.levels` | 1100 ms ease-in-out per bar, staggered 50 ms | | The mic level bars | The current level, no easing |

### 5.2 Choreography

**Out from the pen** (`invoke-shake` → `open`)

1. t = 0: the halo scales 0 → 1 with `spring.tick`; the intake outline and the label fade in over 120 ms.
2. t = 150 ms: the sheet appears at scale 0.6 with its transform origin on the hotspot and opacity 0, clipped to zero height at its origin edge. It unrolls (the clip opens to the full height over 220 ms, `duration.unroll`) while it scales to 1 with `spring.unfold` and fades in over 120 ms. The rim is dark until t ≈ 310 ms, then lights up over 200 ms (`duration.rim`), so the last thing to arrive is the light on the edge. From the taskbar, the sheet unrolls upward from the button.
3. t = 390 ms: the halo fades out over 200 ms. The field has focus from the first frame the sheet exists; the label fades out as the sheet appears.

**The words** (`compose` → `streaming`)

- Typing adds letters at once. On Enter the field's text moves to the prompt line and is written in ink: each word arrives with `duration.ink`, 24 ms apart. Then the rule is drawn under the words, left to right (`duration.rule`), and the body opens with `spring.settle`.
- "Thinking…" shows with the breathing leaf until the first message chunk. The rim begins its turn (`loop.rim`) on send and stops when the run ends.
- The answer arrives as ink: each new word rises into place (`duration.ink`), at most six in flight; when chunks arrive faster than that, later words appear without the stagger, so the text never lags the agent by more than ≈ 150 ms. Sentences complete; nothing moves after it has arrived. The caret sits after the last word.

**The marks** (`steps`)

- A new step row fades in (120 ms). Its mark is the ink dot, pulsing (`loop.inkdot`).
- When the step completes, the dot is replaced in the same frame by the tick, drawn as a stroke from its start to its end (`duration.draw`). A failed step draws the cross the same way in `error`.
- A change's Undo pill fades in with the tick (120 ms). Pressing it strikes the step, turns the pill into "Undone", and the result line re-flows with `spring.settle`.
- When the run ends, the step list folds into its chip with `spring.settle`; the rim stops turning.

**The question** (`confirm-destructive`): the card fades in on paper (120 ms) and the note reflows with `spring.settle`; focus lands on the card, then Tab reaches Keep. The rim keeps turning: the run is waiting, not over.

**Into the mirror** (`consent-system` → `mirror`): width 400 → 760 and height to fit, both with `spring.expand`; the pane fades in over 200 ms once the size has settled 90 %. The transform origin stays where the note was anchored. Back from the mirror uses the same spring in reverse.

**Settle** (content arrives): the note's height, and width when it changes class, animate with `spring.settle`. Content inside is laid out at its final position and fades or inks in; nothing slides. If the note would leave the screen, its position moves with the same spring.

**Fold back** (`done` → nothing)

1. The rim goes dark over 160 ms (`duration.unwrite`).
2. The sheet rolls up towards its origin: the clip closes towards the origin edge and the scale goes 1 → 0.6 with `spring.fold`; opacity 1 → 0 over the last 60 % of the travel. Into the taskbar, the sheet also travels to the button; on arrival the button presses (`spring.tick`) and the ring or badge appears.

**The tray** opens from the button with `spring.settle` on scale 0.9 → 1 and a 120 ms fade, origin bottom centre.

### 5.3 Remove animations, and economy

Android's "Remove animations" sets the animator duration scale to 0 (`ValueAnimator.areAnimatorsEnabled()` is false). `SpringAnimation` does not read that scale, so the build checks it itself (Q5 does, C: `Motion.enabled`). With it on, every token behaves as the last column of §5.1: the sheet appears at rest and disappears in one frame; words, rules and ticks are drawn at once; every loop is still. Nothing is conveyed by motion alone: every state also has text or a shape, so Remove animations loses nothing.

**Economy** is the other switch: when the platform turns blur off (§4.5), the loops stop too, but springs and fades stay. The person asked for battery, not for stillness; a 300 ms unroll costs nothing against a loop that runs for a minute.

### 5.4 Frame budget

The note is one window with a blurred backdrop. While a run is on, the continuous work is the rim's turn (one stroked path, one invalidation per frame on its own view), the ink dot on one 8 dp mark, the breathing 18 dp leaf, and the words arriving (alpha and a 2 dp translate on spans, at most six at a time). At rest the only work is the caret at 1 Hz. The mirror's cost is the platform's. §4.5 gives the numbers the Porter measures against at 120 Hz.

## 6. Easier

What was on screen in Q3's first moment, and what is now:

| Q3 (`compose`) | Q7 (`open`) |
|---|---|
| Header: leaf, agent chip with where and a chevron, Hide, Close | gone; the agent's name is on the quiet line |
| Intake chip with a thumbnail and a remove button | the intake on the quiet line, as text with a 20×13 thumbnail; clicking it drops the intake |
| Three suggestion chips | gone |
| The field, a mic button and a send button beside it | one pill: the leaf, the field, the mic and send inside it |
| Footer with two key hints | the quiet line: agent · intake · Esc close · × |
| 11 interactive things, 7 lines | 4 interactive things (the field, the agent, the intake, ×), 2 lines, 88 dp tall |

Rules:

- **One place to type.** The field is the only control that takes text, and it always has focus when the note opens, after a send, and after a run ends (unless a card or a result button takes it, §8.2). Its placeholder is "Ask Quire", then "Ask a follow-up".
- **The agent is shown quietly.** A 14 dp avatar and the name, in 12 sp, on the quiet line. Where it runs ("on this laptop", "in the Linux environment", "on Brian's desk") is in the picker, in the tooltip and in the TalkBack label, not on the line; the one exception is "not connected", which shows beside "No agent". The name is a button: it opens the picker.
- **No chrome until it is needed.** No header. The × is on the quiet line, 24 dp. Hide and Close are the same ×: while a task runs it hides (the task keeps running), otherwise it closes. The key hint beside it says which.
- **Nothing asks unless it must.** Non-destructive changes happen and show their Undo. The destructive card is the one question, and the safe answer is the obvious one.
- **Suggestions are out.** Q6 makes the agent know where it is; it does not need the person to pick a starter. If the owner wants them back, they return as one quiet "Try:" line, never as chips.
- **The quiet line gives way in order.** While a state shows, the intake keeps the app's name only ("Settings · Display" → "Settings") and an empty intake ("Add what's on screen") is dropped; if the line still does not fit, the intake's name truncates. The state text carries no elapsed time (that is on the result's sub-line). The agent's name, the state and the key hint never truncate.

## 7. Visual tokens

### 7.1 Type

Google Sans for everything in the note (the system's `google-sans*` families, C). Google Sans Code for code. Sizes in sp; line height after the slash. Unchanged from Q3.

| Role | Size | Weight | Used for |
|---|---|---|---|
| `quire.type.prompt` | 15/22 | 500 | The person's prompt |
| `quire.type.body` | 15/22 | 400 | Answers, results |
| `quire.type.label` | 14/20 | 400 | Steps, plan entries, auth rows, the field; the step's value at 500 |
| `quire.type.chip` | 13/20 | 500 | Buttons, pills, card titles (600) |
| `quire.type.meta` | 12/16 | 400 | The quiet line (the agent's name at 500), sub-lines, change rows' "where", key hints |
| `quire.type.code` | 12.5/18 | 400 | Code blocks, commands, diffs (Google Sans Code) |
| `quire.type.sysdialog` | 22/28 | 400 | The platform dialog's title (platform-owned) |

### 7.2 Spacing and shape

| Token | Value |
|---|---|
| Spacing scale | 4, 8, 12, 16, 24, 32 dp. Block gap 10 dp inside the body; button gap 8 dp (6 dp between a card's options). |
| Note radius | 28 dp |
| Paper radius | 16 dp |
| Field | 44 dp tall, radius 22; 14 dp left padding, 6 dp right; the leaf 18 dp; mic and send 32 dp inside it |
| Mirror pane, image, code radius | 16, 12, 12 dp |
| Pills (undo, folded steps, stop) | 24 dp tall (undo), 28 dp (folded steps), 36 dp (stop); pill radius |
| Button height | 36 dp, 16 dp side padding (10 for text buttons) |
| Icon button | 32 dp, icon 20 dp; on the quiet line 24 dp, icon 18 dp |
| Step row | 28 dp min height, 10 dp gap, 20 dp mark, 16 dp kind icon |
| Quiet line | 24 dp tall, 12/16; 16 dp left, 10 dp right, 8 dp bottom |
| Rim | 1.5 dp |
| Focus ring | 2 dp `primary`, 2 dp offset (buttons: a 2 dp `surface` gap then 2 dp `primary`) |

### 7.3 Colour

All roles are Material 3 TonalSpot, derived by Android 17 from the current wallpaper. The prototype uses the values `scripts/brand/monet.py`'s library computes for the Folio wallpapers (seed `#959DE5` light, `#9F87FE` dark; spec 2025). The build reads them from the theme (`system_*` colours; Q5's `Palette.kt`, C), never from constants; the only fixed colours are the success green and the brand's hues.

| Use | Role | Light | Dark |
|---|---|---|---|
| Ink | `onSurface` | `#31323B` | `#E9E3EF` |
| Soft ink | `onSurface` ⊕ note 85 % | `#4F5058` | `#CAC5D0` |
| The glass | `surface` / `surfaceContainer` at 80 % | `#FBF8FE` | `#1A191F` |
| Paper | `surfaceContainerLowest` at 72 % / `surfaceContainerHigh` at 80 % | `#FFFFFF` | `#201F26` |
| The field | `surfaceContainerLowest` at 80 % / `surfaceContainerHighest` at 85 % | `#FFFFFF` | `#27252D` |
| Filled button, focus ring, caret, rule, the ink dot, the agent's pointer rings | `primary` / `onPrimary` | `#565B8C` / `#FBF8FF` | `#CBC0ED` / `#423B5F` |
| New value pill | `primaryContainer` / `onPrimaryContainer` | `#C0C5FD` / `#393E6D` | `#554D73` / `#E7DFFF` |
| Tonal button, the picker's selection | `secondaryContainer` / `onSecondaryContainer` | `#E0E0F9` / `#4F5065` | `#3D394D` / `#C3BCD4` |
| Automation chip | `tertiaryContainer` / `onTertiaryContainer` | `#F0CBF8` / `#5C4166` | `#F1C0E6` / `#5E3958` |
| Stop pill, Delete | `errorContainer` / `onErrorContainer` | `#F97386` / `#6E0523` | `#871C34` / `#FF97A3` |
| The cross, the error card's rim, failed step text | `error` | `#A8364B` | `#F97386` |
| The tick, the mic indicator | `success` (fixed: `#2F6B45` / `#9BD5A8`; containers `#BDEBCB` / `#1E4A2F`) | | |
| Halo label, Jump pill, code block (light) | `inverseSurface` / `inverseOnSurface` | `#0E0E12` / `#E9E3EF` | `#FDF8FE` / `#31323B` |
| Paper outline | `outlineVariant` at 40 % / 60 % | `#B2B1BC` | `#494650` |

The **brand hues** (`#7E8CFF → #4355B9`, fold `#FFB38A → #FF7A9C`, halo conic through `#D08BFF`) appear only on the leaf, the halo, the rim and the agent's pointer in the mirror.

### 7.4 Contrast (measured)

`scripts/quire/contrast-check.py --md`, on the prototype's tokens. Every pair is composited through its stack (paper or field over the glass) over black and over white, and scored at the lower ratio; that bounds every real backdrop under the blur, which averages what is behind and never makes it darker than black or lighter than white.

| Pair (foreground on background) | Light | Dark | Target |
|---|---|---|---|
| Ink: answer text, titles, text buttons, on the glass | 7.5:1 pass | 7.3:1 pass | 4.5:1 (worst backdrop) |
| Soft ink: the quiet line, step kinds, pending steps, on the glass | 4.8:1 pass | 5.4:1 pass | 4.5:1 (worst backdrop) |
| Soft ink on paper (cards) | 7.0:1 pass | 8.7:1 pass | 4.5:1 (worst backdrop) |
| Soft ink in the field (placeholder) and on change rows | 7.3:1 pass | 8.4:1 pass | 4.5:1 (worst backdrop) |
| Ink on paper (undo pill, paper button) | 11.1:1 pass | 11.8:1 pass | 4.5:1 (worst backdrop) |
| Filled button: Keep it, Take over, send | 6.1:1 pass | 6.1:1 pass | 4.5:1 |
| Tonal button, agent picker selection | 6.1:1 pass | 6.1:1 pass | 4.5:1 |
| Stop pill, Delete | 4.6:1 pass | 4.5:1 pass | 4.5:1 |
| New value pill | 6.1:1 pass | 6.1:1 pass | 4.5:1 |
| Mic indicator | 9.6:1 pass | 7.7:1 pass | 4.5:1 |
| Automation chip (Using Settings) | 6.1:1 pass | 6.1:1 pass | 4.5:1 |
| Halo label, Jump pill, paused pill | 15.3:1 pass | 12.1:1 pass | 4.5:1 |
| Done tick (non-text) on the glass | 3.8:1 pass | 5.5:1 pass | 3.0:1 (worst backdrop) |
| Focus ring (non-text) on the glass | 3.8:1 pass | 5.4:1 pass | 3.0:1 (worst backdrop) |
| Focus ring (non-text) on paper | 5.6:1 pass | 8.7:1 pass | 3.0:1 (worst backdrop) |
| Pending-step ring, soft ink (non-text) | 4.8:1 pass | 5.4:1 pass | 3.0:1 (worst backdrop) |
| Field outline on focus (non-text) | 5.8:1 pass | 8.3:1 pass | 3.0:1 (worst backdrop) |
| Running mark, the ink dot (non-text) | 3.8:1 pass | 5.4:1 pass | 3.0:1 (worst backdrop) |

**All eight wallpapers** (`scripts/quire/q7-contrast.py --md`, the system's own roles for each wallpaper's seed, light and dark, glass at 80 %): every pair passes on every wallpaper. The closest pair everywhere is the Stop pill at 4.54 to 4.58:1, which is the system's own `errorContainer` / `onErrorContainer` pair and does not depend on the glass. The next closest is soft ink on the glass in light at 4.8:1 over black. Lowering the glass below 80 % fails soft ink first (4.1:1 at 74 %); raising it gains nothing visible. 80 % is the number.

What the check changed from Q3: text buttons and Stop were `primary` and `error` as text on the note; at 80 % they are 3.8:1 and 3.4:1 at the worst backdrop, so text buttons are ink and Stop is a pill (§4.4). Secondary text was `onSurfaceVariant` (4.0:1 at 80 %); it is soft ink (§4.3). The pending ring follows soft ink. With those three changes the glass could come down from 92 % to 80 %.

The rim, the bloom, the specular and the rule are decorative and have no target; the rim never carries meaning that the step's text does not.

### 7.5 Icons

Material Symbols Rounded (Apache-2.0), weight 400, optical size 24, filled for status marks and the mic indicator, outlined elsewhere. Kinds map to icons as in Q3: read → `visibility`, edit → `edit`, delete → `delete`, move → `drive_file_move`, search → `search`, execute → `terminal`, think → `psychology`, fetch and web → `language`, file → `folder`, other → `more_horiz`; Quire's own tools: setting → `tune`, app → `apps`, window → `select_window`. The tick and the cross are not symbols: they are strokes the build draws (§10).

## 8. Accessibility

### 8.1 Keyboard paths

| Goal | Keys |
|---|---|
| Open Quire | Meta+Space; the assist key; Tab to the taskbar's Quire button and Enter |
| Send | Enter. Shift+Enter inserts a new line. |
| Stop a run | Esc, or Tab to Stop in the mirror. Cancels the run, answers any open request as cancelled (deletes nothing), and shows Stopped. Esc never hides a running task. |
| Close the note | Esc (when idle, done or stopped), or Tab to × on the quiet line. A second Esc never does anything destructive. |
| Hide a running task | Tab to × on the quiet line, Enter; or Meta+Space from anywhere; or Enter on the taskbar's Quire button. The task keeps running; Meta+Space or the taskbar button brings it back. |
| Hold to talk | Hold the mic key or the assist key; release sends. Esc while holding cancels. |
| Change the agent | Tab to the agent's name on the quiet line, Enter, arrows, Enter. Esc closes the list. |
| Drop the intake | Tab to the intake on the quiet line, Enter |
| Answer the destructive question | Focus is on the card. Tab reaches Keep it first, then Delete; Enter or Space. Nothing is chosen by default. |
| Answer an agent's request | Focus is on the card. Tab to the agent's options in the order shown, reject first; Enter or Space. |
| Undo a change | Tab to the step's Undo pill, Enter; or to Undo on the result |
| Mirror | Tab to Stop, Pause, Take over. When paused, Tab into the mirror to act inside the session; Esc returns to the buttons. |
| Scroll a long answer | Page Up / Page Down in the body; Ctrl+End jumps to latest |
| Copy a code block | Tab to the copy button, Enter; or select and Ctrl+C |

### 8.2 Focus order

The field → mic → send; then the body top to bottom (steps are a list; an Undo pill, a card and its buttons are stops); then the quiet line left to right: the agent's name → the intake → ×. Initial focus: the field on open; the destructive card when it arrives (then Tab to Keep); an agent's request card when it arrives; the result's first button on Done; the first auth method on sign-in; Resume when paused. Focus never jumps while the person is typing; a card arriving during typing is announced and reachable with Tab, and takes focus only if the field is empty.

### 8.3 TalkBack

| Element | Role | Label and announcements |
|---|---|---|
| Halo | live region, polite | "Quire. Pointing at Settings." / "Pointing at a secure window; nothing is taken in." |
| Note | dialog | "Quire. Claude Code on this laptop." Opening announces the intake: "Taking in Settings, Display." |
| Field | edit text | "Ask Quire." Hint: "Enter sends, Shift Enter new line." |
| Mic | button | "Hold to talk." While held: "Listening." The transcript is a live region, polite. |
| Quiet line: agent | button | "Agent: Claude Code on this laptop. Change." |
| Quiet line: intake | button | "Taking in Settings, Display. Remove." / "Selection from Notes: 'The conference runs…'. Remove." / "Secure window, nothing taken in." |
| Quiet line: × | button | "Close." / while running: "Hide the note; the task keeps running." |
| Thinking | live region, polite | "Claude Code is thinking." once; not repeated per chunk. |
| Answer | text, live region polite | Announced in sentences as they complete, not per word. |
| Steps | list | Each: "Opening Chrome, done." / "Going to foxnews.com, running." / "Settings: Dark theme on, done. Undo available." Changes announced politely, one per step. |
| Undo pill | button | "Undo: Settings, Dark theme on." After: "Undone." |
| Plan | list | "Plan, 1 of 4 done." Entries: "2, Turn off notifications during the talk, high priority, in progress." |
| Destructive card | group, live region assertive | "Claude Code wants to delete a file. report-draft.pdf, in Downloads, 2.4 megabytes, today 11:40. It goes to the bin and can be restored from Files for 30 days. Buttons: Keep it, Delete." |
| Agent's request card | group, live region assertive | As Q3: the title, the rows, then "Buttons:" and the agent's own names. |
| Mirror | image, live region polite | "Live view of Settings, used by Claude Code. Step 2 of 4, tapping Connected devices." Updates per step, never per frame. Paused: "Paused. The mirror is interactive." |
| Result | live region polite | "Done. Dark theme is on. Changed 1 setting. Undo available." |
| Error | live region assertive | "Claude Code stopped. The agent closed the connection before finishing. Nothing was changed." |
| Stopped | live region assertive | "Stopped after 3 of 4 steps. Battery saver was turned on. Lowering brightness was interrupted and may be partly applied; check Display settings. Undo available." |
| Taskbar button | button | "Quire." / "Quire, 2 tasks running, 1 needs your answer." |
| Tray row | button | "Delete the newest file in Downloads. Needs your answer. Claude Code." |
| Mic indicator | image | "Microphone in use by Quire." |

The rim, the bloom, the ink reveal and the marks' drawing have no announcements: they repeat what the text says.

### 8.4 Text size and display size

The note is laid out in dp and sp, so Display size and Text size apply. At Text size "largest" (1.3×), the note's width stays 400 dp and the body wraps; the quiet line gives way in its order (§6) and, if the state text still does not fit, wraps to a second line with the agent and intake on the first and the state and × on the second. The destructive card's two buttons stay on one row to 1.3×. At 2× display scaling on the G14 the note is 800 px wide, still under half the screen.

## 9. Mapping to ACP and the OS tools, and what the Porter checks

Q3's §7 mapping stands as confirmed by the Porter on ANAL-217 and built in Q5 (C). The rows that are new or changed:

| State or element | ACP event or OS action | Status |
|---|---|---|
| Tool steps with values ("Going to foxnews.com", "Settings: Dark theme on") | `tool_call` / `tool_call_update` `title` and `kind` (C); the value from the broker's own call record (Q6) | ⚑ Q6: the broker knows the argument and the result of every Quire tool call; the step shows them. The `title` from an agent's own tool call shows as is. |
| Undo on a step | The settings tool's change log (Q6): namespace, key, old, new; restore only if the setting still holds the new value | ⚑ Q6 requirement, confirmed as such on ANAL-215's review; the pill is the log's row. |
| The destructive card | The broker's own card, raised while it holds the MCP `tools/call` for a destructive-tier tool (Q6), with Quire's two options; the broker refuses the call until answered | ⚑ Q6. The tier list is ANAL-220's. The card's copy comes from the tool: the object, where, what happens, reversible or not. |
| No card for other tools | The broker executes and records the call | ⚑ Q6 replaces Q3's "every mediated change goes through a card". |
| Blur off | `WindowManager.isCrossWindowBlurEnabled()` and `addCrossWindowBlurEnabledListener` (Android 12+ API); WM's `BlurController` rules (C, `docs/googlebook-ui.md` §2.3) | ⚑ The Porter confirms the API in our tree and that the note's `BackgroundBlurDrawable` is dropped (not just hidden) when it is false. |
| The rim | A stroked path with a `SweepGradient`, rotated by a `ValueAnimator` while a run is on | Design; §10 gives the draw. |
| Ink reveal | Alpha and a 2 dp translate on word spans of the streaming `TextView`, or a per-word layer in the custom text view Q5 draws | ⚑ The Porter picks the mechanism; §10 lists both. |
| The sheet's unroll and fold | `View.setClipBounds` from the origin edge, with the scale spring Q5 has | Design; §10. |
| Chrome appearing behind the note | The apps tool opens the activity; the note stays on top (`TYPE_APPLICATION_OVERLAY`, C) | C for the layer. |

Everything else in Q3's §7 is unchanged: invocation, intake, the agent chip and picker (now on the quiet line), streaming, plan, the agent's own `request_permission`, platform consent, the mirror, pause, take over, secure content, done, error, sign-in, hidden tasks, long output, images, offline, the taskbar button.

## 10. For the Porter

- **The surface.** Keep Q5's one `BackgroundBlurDrawable` at 34 dp; set its colour to the note's colour at 80 % (`Palette.NOTE_ALPHA = 0.80f`). Draw the specular as a 1 dp line inside the top edge and the outline as a 1 dp inset stroke, in the same draw as the tint. The bloom is a `RadialGradient` (white at 34 % / 7 % to transparent at 62 % of the width, centred on the top-left corner) painted over the tint. The rim is a separate `View` above the content: a rounded-rect `Path` inset by 0.75 dp, stroked 1.5 dp with a `SweepGradient` of the five hues (§4.1; the lightened set in dark), `Paint.alpha` at 70 % / 80 %, with a `BlurMaskFilter` of 24 dp at 18 % under it for the glow (or a second, wider stroke at low alpha if the mask filter costs more than 0.3 ms). Rotate the gradient's matrix with a `ValueAnimator` of 12 s, linear, `RESTART`, running only while `running` is true and `Motion.enabled` and blur is on; invalidate only the rim view. The sheet's shadow stays the `elevation` Q5 uses, with the ambient and spot colours set to §4.1's.
- **Blur off.** Listen with `addCrossWindowBlurEnabledListener`; when false, swap the background for a rounded rect at 96 %, drop the bloom, set the rim's alpha to 60 % of its value and cancel every loop (`Motion.economy = true`). Swap back on true. The layout does not change.
- **Paper.** `Palette.card` becomes `surfaceContainerLowest` at 72 % (light) / `surfaceContainerHigh` at 80 % (dark); `Palette.field` becomes `surfaceContainerLowest` at 80 % / `surfaceContainerHighest` at 85 %; each paper rect gets a 1 dp line inside its top edge (`quire.paper.line`) and the outline at 40 % / 60 %.
- **Ink.** `Palette.inkSoft = blend(onSurface, note, 0.85)` replaces `onSurfaceVariant` everywhere the note draws secondary text, pending marks and kind icons. Text buttons use `onSurface`. Stop and the destructive verb use `errorContainer` / `onErrorContainer`.
- **No header.** Remove `NoteView`'s header row; the quiet line is a new row after the composer: the agent (avatar 14 dp + name, a button that opens the picker above it), the intake (thumbnail 20×13 + name, a button that drops it; the page is dropped from the name while a state shows), a spacer, the state text, the key hint, and × (24 dp; Hide while running, Close otherwise). The picker anchors to the quiet line and opens upward.
- **The composer.** One pill, 44 dp, radius 22: the leaf 18 dp, the `EditText`, the mic 32 dp and send 32 dp inside it. Send is filled only when there is text.
- **The prompt.** Written in ink with the rule under it: a 1.5 dp line in `primary` at 55 % fading to transparent over the right 30 %, drawn with a width animation (0 → 100 %, 240 ms, emphasised decelerate, 120 ms after send). The words: see ink reveal.
- **Ink reveal.** Two ways that fit Q5's custom text drawing; pick by cost. (a) Spans: each new word gets a span whose alpha and vertical offset animate over 160 ms (a `ReplacementSpan` or a custom `CharacterStyle` with an animated paint), staggered 24 ms, at most six live; invalidate the text view per frame while any is live. (b) Layers: the streaming `TextView` draws committed text once, and a small overlay view draws the last ≤ 6 words with their own alpha and offset until they settle. Either way, with `Motion.enabled` false, words appear at once.
- **The marks.** The running mark: an 8 dp circle in `primary`, scale 1 → 1.35 → 1 and alpha 0.9 → 0.55 → 0.9 over 900 ms, `RESTART`; still with a 3 dp halo at 30 % in economy or Remove animations. The tick: a `Path` (`M4.5 10.5 l3.6 3.6 l7.4 -7.6` in a 20 dp box), stroked 2.2 dp round, drawn with `PathMeasure` from 0 to its length over 180 ms, emphasised decelerate, in `success`. The cross: `M6 6 l8 8 M14 6 l-8 8`, the same way, in `error`. The Undo pill: 24 dp, paper, the undo symbol at 15 dp and "Undo" at 12 sp 500; after undo, "Undone" with the check, no surface, soft ink; the step title struck.
- **The destructive card.** `Block.Consent` with `source = BROKER` and exactly two `Option`s whose kinds are `reject_once` (safe) and `allow_once` (destructive); draw it with the `error` rim at 70 % (1.5 dp), the delete symbol in `error`, a file row (icon, name, sub) and the sentence; style the `allow_once` option as the stop pill and the `reject_once` as filled, the reverse of an agent's card, because here the safe choice is the one to make easy. Focus the card, then Tab reaches the filled button first (order the buttons: Delete, Keep it; focus order: Keep it, Delete).
- **The unroll.** At open, set `clipBounds` to a zero-height rect at the origin edge and animate it to the full bounds over 220 ms (emphasised decelerate) while the scale spring runs from 0.6 (Q5's `SpringValue` with `Motion.UNFOLD`); fade in over 120 ms; start the rim's alpha at 0 and animate it to full over 200 ms starting at 160 ms. The fold is the reverse: rim alpha to 0 over 160 ms (emphasised accelerate), then `clipBounds` closing towards the origin and the scale spring to 0.6 (`Motion.FOLD`), alpha over the last 60 %. From the taskbar the origin edge is the bottom.
- **Springs:** unchanged (`Motion.kt`); check `Motion.enabled` on every spring and loop.
- **Dynamic colour:** run `scripts/quire/q7-contrast.py` against the device's palette (`--device` with `q5-cf-check.py`'s "contrast" section) for the eight wallpapers before sign-off; adjust only the glass alpha, and tell me if it moves.
- **What to record for acceptance** (this issue's): each screen id in §3.2 as a G14 capture next to its render, both themes, on the Folio wallpapers and the first moment on all eight; the four motion paths in §5.2 at 120 fps on the G14 with `dumpsys gfxinfo` against §4.5's budgets; the blur's RenderEngine cost with and without the note; blur off (`wm disable-blur 1`) showing the fallback; Remove animations showing the cuts; the keyboard paths in §8.1 and the TalkBack labels in §8.3.

## 11. Edge states: covered and remaining

Covered in this design: empty (first run, `no-agent`; the first moment, `open`), loading (streaming, steps, the ink dot, "Waiting for your permission"), error (`error`, `stopped`, the destructive question kept, denied consent, offline, secure window, blocked session), overflow (long output, code, wide note), long strings (the prompt wraps; the quiet line gives way in order and then wraps; the tray truncates the prompt to one line; a long file name on the destructive card wraps on its row), keyboard focus (§8.2), light and dark (every screen), two sizes (both renders), all eight wallpapers (`wallpapers.png` and `q7-contrast.py`), blur off (`glass-off`), Remove animations (§5.3), text scaling (§8.4).

Remaining, for the build: right-to-left layout (the note mirrors; the rim's angle mirrors so the light stays at the top-leading corner; the rule fades towards the trailing edge), a second display (the note opens on the display with the pointer), the lock screen (Quire does not open; C), the window under the pointer closing while the note is open (the intake stays; it is a snapshot), a card whose turn ends while it is open (it reads "The agent moved on" and closes), and a destructive card hidden behind the taskbar: the badge counts it, the tray row says "Needs your answer · Delete this file?", and nothing is deleted until it is answered.

## Reproduce

```text
scripts/quire/render-design.sh                 # both sizes, every state, light and dark, plus wallpapers.png and gallery.png
scripts/quire/render-design.sh fhd open steps  # one size, chosen screens
scripts/quire/render-design.sh walls           # the note over all eight wallpapers
scripts/quire/contrast-check.py --md           # the table in §7.4; exit 1 if any pair fails
~/anybook/tools-local/brand-venv/bin/python scripts/quire/q7-contrast.py --md   # all eight wallpapers; --alpha 0.76 to try another glass
docs/quire-design/index.html?play=1            # the clickable prototype; ?play=1&glass=0 for blur off
docs/quire-design/index.html?screen=open&wall=tide&theme=dark   # one screen, another wallpaper
```

Fonts are fetched into the host data dir (`~/anybook/quire/fonts`) and linked into `docs/quire-design/fonts/`, which is gitignored. Google Sans, Google Sans Flex and Google Sans Code are OFL-1.1; Material Symbols Rounded is Apache-2.0. The same trademark reading as ANAL-202 applies: the fonts are used, never named in the product.
