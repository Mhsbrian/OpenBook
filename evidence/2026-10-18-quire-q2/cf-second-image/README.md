# Second Q2 image in Cuttlefish (2026-10-18, 15:56–16:04 UTC)

Build from `d0afeed` (all four AOSP patches and `RELEASE_PACKAGE_COMPUTER_CONTROL`, but **without**
`computer_control_per_app_consent`), 15:25–15:54 UTC. Superseded by the third image (`../cf/`), which adds per-app
consent, as the ANAL-217 review's version of Q2's acceptance asks. Only the results and the logs behind two findings are
kept here (screenshots and the desktop checks are pruned; the third image has them all).

| Check | Result |
|---|---|
| Desktop defaults | 16/16 |
| Facts and invocation (`q2/results-facts-invoke.tsv`) | 34 PASS, 1 INFO: the shake, Meta+Space and the assist key each open Quire's note, with the visible packages, `flagSecureFound=true` and a screenshot with no probe pixels |
| Computer control, run 1 and 2 (`q2/results-control-run1.tsv`, `-run2.tsv`, `control-log-run1.txt`, `-run2.txt`) | 12 PASS, 2 FAIL each: everything except the tap, because the session's accessibility tree was empty |
| Computer control, run 3 (`q2/results-control.tsv`) | 14/14, after the check started Settings fresh |
| Refusals (`q2/results-refuse.tsv`) | 10/10: "Don't allow", lock screen, an app outside the allowlist, `FLAG_SECURE` |
| Health over the whole session (`q2/health-whole-session.txt`) | No crash, ANR or restart; the three known denials |

**Global consent.** Without per-app consent the dialog asks for Quire as a whole ("Allow **Quire** to use screen
automation?", `q2/control-consent.png`).

**Accessibility tree and already-running apps.** Between runs 2 and 3, by hand on the same VM: Settings started fresh
on the session display gave 2 accessibility windows (with or without the consent dialog); Settings already running on
the main display gave 0. That diagnosis ran `logcat -c` (16:00–16:02), so this image's health evidence comes from the
events buffer, `dmesg` and process start times.
