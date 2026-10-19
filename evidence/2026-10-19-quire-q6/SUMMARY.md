# Quire Q6: every agent knows it is OpenBook's assistant and can drive the laptop (ANAL-220)

2026-10-19. What was built and how it works: `docs/quire.md` §10. The update to the G14 is in `g14/` once it ran.

## Host

- `quired` 0.3.0: `go test -race ./...` passes, with new tests for the tools relay (`internal/serve/tools_test.go`):
  the skill files in a new session folder only (never in a folder the client names, never over a file), the MCP server
  added to the session with a private socket (0600 in a 0700 folder), a call refused outside a turn and never sent to
  Quire core, relayed with quired's session id during a turn, ended as an error when the turn is cancelled, and the
  socket gone when the connection closes.
- Quire core: `tools/compile-check.sh` OK (53 Kotlin files, 0 warnings).

## The rehearsal VM (`vm/`)

The G14's state (`openbook-ota-20261019-quire5`, slot B; `r2` `after-ab-from-after-ba`) in QEMU, Quire from this
branch installed over it, the Linux environment with `quired` 0.3.0 and opencode 1.19.3 (free model, no account):
Q4's device check 0 failures (`linux-env` log not kept; the same check as before, "QUIRE OK" in 11.6 s).

| Prompt, word for word | Log | Result |
|---|---|---|
| "open chrome and go to fox news" (typed in the note) | `prompt-foxnews.log` | Fox News opened in the VM's only browser; Chrome isn't in the VM, and the agent said so (`prompt-foxnews.png`) |
| "turn on dark theme" | `prompt-dark.log` | Dark theme on, Undo in the note (`prompt-dark.png`) |
| "make the text bigger" | `prompt-bigger.log` | text size up one step |
| "turn on battery saver" | `prompt-saver.log` | on (already on from the broker check; on simulated battery power) |
| "open Files and show my Downloads" | `prompt-files.log` | Files on Downloads |
| "what's on my screen?" (Files in front) | `prompt-screen.log` | Files' assist structure read |

Through the broker directly (lab `TOOL`, real taps):

- `settings-changes-undo.png`, `settings-after-undo.png`: three changes listed with their undos; Undo on Dark theme put
  it back (`cmd uimode night`: no).
- `delete-confirmation-over-files.png`: the delete card shown above Files, which hides overlays. Don't allow left the
  file; Allow deleted the other one.
- `screen-consent-covered-before-fix.png` → `screen-consent-platform-dialog.png`: the platform's "Allow Quire to use
  screen and app data?" was covered by the note; the note now steps aside for it.
- `control-mirror-settings.png`: computer control on Settings after the platform's consent, in the mirror; a tap on
  "Connected devices" found by its text.
- Refused: `Android/data/…` ("other apps' own files"), `/storage/emulated/0/../../../data` (outside shared storage),
  Chrome when it isn't installed (with the list of browsers).

Not run, by the owner's request to keep testing short: the full matrix on a second agent, and the Bluetooth and delete
prompts through an agent (their tools were checked through the broker above).
