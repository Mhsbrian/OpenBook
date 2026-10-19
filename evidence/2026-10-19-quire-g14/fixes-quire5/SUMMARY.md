# Quire on the G14, round 2: the owner's report fixed (ANAL-225)

2026-10-19.

## The owner's report

- Quire kept appearing from ordinary touchpad use and vanished again ("blinks").
- After a reboot, the Linux environment needed opening Terminal by hand.

Quire's log on the laptop showed:
- 9 shake invocations in 5 minutes, each note closed again within 1 to 2 s;
- the Meta+Space notes worked;
- a question over Chrome got its answer at 10:51.

## Fixes

| Commit | What |
|---|---|
| `1b0599a` (frameworks/base 0009) | a shake reversal needs 12 dp back from the turning point; pixel jitter is no longer a shake |
| `1b0599a` (`note/NoteWindow.kt`) | outside touches that aren't clicks (touchpad swipes and pinches, a pointer touch with no button) and anything within 500 ms of the note appearing don't hide it; each outside touch and Esc is logged |
| `1b0599a` (Virtualization 0002) | the Terminal app's agent bridge gets `start`: install if needed, then start the VM, without the Terminal's UI |
| `1b0599a`, `dcaa459`, `eb43243` | Quire starts a stopped Linux environment whenever it's called. A prompt to a connected agent waits for it and retries quired while it comes up. Off or not installed, the note offers Set up the Linux environment. The start waits out the Terminal app's state-publication lag (the Checker's Hold on `dcaa459`) |

## Evidence (package `openbook-ota-20261019-quire5`, fingerprint `…/20261019.quire5`)

- **OTA rehearsal from the laptop's state** (`after-ba`, quire2 on slot A; `qemu/`):
  - A→B 13/13;
  - rollback 13/13;
  - power cut 10/10.
- **`quire-vm/stopped/`:** the Linux environment installed, then the Terminal app force-stopped.
  - Quire started it itself.
  - The shake (25-count strokes) and Meta+Space opened the note beside the pointer.
  - Connect opencode, the first typed prompt, then "QUIRE OK" in the note.
  - The Settings demo with consent.
  - Health clean: **20 PASS, 0 FAIL**.
- **`quire-vm/firstrun/`:** only the image in `/sdcard/linux`, with the Linux environment off.
  - Set up the Linux environment in the note gave opencode listed after 32 s.
  - Connect, a typed prompt, then "QUIRE OK" in 11.9 s: **15 PASS, 0 FAIL**.
- **Bridge regression on the image's runtime:** 24/24, in both runs.
- **`connector-test.txt`:** the real `Connectors.kt` against a scripted bridge, 10/10. On `dcaa459` it fails 3, the Checker's two among them.
