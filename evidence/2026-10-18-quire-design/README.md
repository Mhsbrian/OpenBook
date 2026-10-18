# Quire Q3 design: evidence for the ANAL-217 recheck of PR #98

As of 2026-10-18, on the revised head of PR #98 (ANAL-215). Three corrections from the review of `2132c6a`, plus the two follow-ups.

## 1. Consent scope (`docs/quire-design.md` §3.3, §7)

The card now renders the agent's `options[]` with the agent's own `name` per button and returns the chosen `optionId`; `kind` only orders and styles. "Allow for this task" is reserved for a broker-enforced grant (⚑, Q2/Q6) and is not offered. "Every change goes through a card" is now stated as the contract for the mediated OS tools, not for arbitrary ACP agents. The sample card shows what `quired`'s Claude Code adapter sends today: Don't allow, Allow for this session, Allow.

## 2. Keyboard consent, Esc, hiding (`docs/quire-design/quire.js`)

`keyboard-check.js` (Playwright 1.64.1, system Chromium, 1920×1080) drives `index.html?play=1` with the keyboard only and records the prototype's state after each step; `keyboard/keyboard-check.log` is its output and `keyboard/*.jpg` the screenshots. Run it from the repository root:

```text
cd evidence/2026-10-18-quire-design && npm i playwright@1.64.1 && CHROME=/usr/bin/chromium node keyboard-check.js ../.. OUT
```

What it shows:

- **A.** Alt+Space → type → Enter reaches consent with focus on the card. Tab reaches Don't allow, Allow for this session, Allow, in that order. Enter on Don't allow answers `{outcome: selected, optionId: deny}`; the task is not running, no badge.
- **B.** Esc at consent answers the request `{outcome: cancelled}`, ends the run, shows "Stopped. … Nothing was changed.", and leaves no running badge or pending request. A second Esc closes the note.
- **C.** Tab ×2, Enter chooses Allow for this session (`optionId: always`). Esc after step 3 gives "Stopped after 3 of 4 steps. Battery saver was turned on. Lowering brightness to 40% was interrupted and may be partly applied; check Settings · Display." with Undo for the confirmed change.
- **D.** Alt+Space at consent hides the note: the task stays running, the pending request is kept, the taskbar button breathes with a badge "1" and the label "Quire, 1 task running, 1 needs your answer". Esc while hidden does nothing. Alt+Space reopens the note at the taskbar anchor in the consent state with focus on the card. Hiding mid-run shows a progress ring; a consent that arrives while hidden switches to the badge.
- **E.** The platform dialog opens with focus on Don't allow; Tab, Enter allows and opens the mirror. Tab order in the mirror note: Hide, Hide (close), Stop, Pause, Take over. Enter on Pause keeps focus on Resume; Shift+Tab, Enter on Stop gives "Stopped after 1 of 3 steps. Settings was closed. Tapping Connected devices was interrupted. Nothing was changed." Esc during step 3 names the interrupted step and where to check. Esc at the platform dialog: "Settings was not opened. Nothing was changed."
- **F.** Esc on an idle note closes it. Esc while an answer streams: "Stopped. The answer was cut off. Nothing was changed."
- **G.** The three agent-named buttons fit one row at 400 dp (91 + 166 + 66 in 340). The mirror note is 760×748 dp: 69 % of 1080, 62 % of 1200; the mirror view is 736×460 dp with the 1280×800 session at 0.55 (704×440).
- No page errors in any path.

Prototype limits: the composer field, mic and send, the agent chip and the suggestion chips are still static spans, so Tab leaves the note after the last button; §6.2's full order is Q5's.

## 3. Contrast (`scripts/quire/contrast-check.py`)

The check now composites the translucent note over black and over white and scores the lower ratio. `contrast-before-2132c6a.txt` is the corrected check run on the previous head's tokens (`--html`): secondary text on the dark note 4.0:1 and Stop 3.4:1, both FAIL, as the review found. `contrast-after.txt` is the same check on this head: the dark note is 92 % opaque (was 80 %), all 17 pairs pass, exit 0. §4.5's table is regenerated from it; every dark render and both consent renders are regenerated.

## Not done here

No Android build, TalkBack run, frame measurement or G14 operation. The Porter's confirmation of the §7 ⚑ rows is requested on ANAL-217.
