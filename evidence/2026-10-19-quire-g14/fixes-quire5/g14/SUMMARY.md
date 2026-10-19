# The G14 on quire5 (2026-10-19)

| When (UTC) | What | Result |
|---|---|---|
| 12:25 | `state` baseline, `ota --dry-run` (`precheck.txt`) | slot A, `…/20261019.quire2`; checks passed |
| 12:25 | `ota --yes` (`ota-apply.log`) | slot B written in 88 s; `verified slot b: images match vbmeta_b (4aa4ffa2…, the package's) … systemd-boot starts slot b next` |
| 12:24–12:35 | the idle rule | input at 12:23:40 (someone at the laptop), then nothing for 11 min, launcher in front, no media |
| 12:35 | reboot | slot B up at 12:36; the owner unlocked it within a minute |
| 12:36 | `ota-status-after.log` | slot B, `…/20261019.quire5`; marked good 12:36:00; merge completed 12:36:05; ESP default slot B |
| 12:37 | `state` against 12:25 | the same 160 packages and versions, user, PIN, 1 account, 2 Wi-Fi networks; Settings: boot counters and the wallpaper colour cache only. The user's files went 165 → 166 with none modified in the window (MediaProvider indexing at boot); none removed |
| 12:38 | `binaries-on-device.txt`, `health.txt` | Quire, SystemUI, the AVF APEX and the composer match the target files; 120 Hz; no crash or ANR; no denial from Quire or AVF |

## The owner's own use after the restart

From Quire's log on the laptop. The prompts' text is not logged.

- **12:37:45, the first call:** Quire asked the Terminal app to start the Linux environment, and it was READY at 12:37:48. The owner opened nothing.
- **12:37:45, 50, 55, shakes:** each note was hidden 0.8 to 1.8 s later by a click outside it (`source=0x2002 buttons=1`, a mouse or touchpad click).
- **12:38:01 and 12:38:17, Meta+Space:** each note got a stray touch 200 and 72 ms after it appeared. The new grace ignored it, so the note stayed; those touches used to close it at once ("blinks").
- **12:38:17, a typed prompt:** sent to opencode in the Linux environment at 12:38:24. The owner pressed Esc at 12:38:40, before an answer.
- **12:38:42, the next prompt:** sent at 12:38:48, answered `end_turn` at 12:39:01 (13 s).
