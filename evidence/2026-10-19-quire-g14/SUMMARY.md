# Quire on the G14: one update with Q2, Q5 and Q4 (ANAL-225)

2026-10-19. The update the installed G14 gets: its current tree plus Quire, rehearsed in QEMU from the laptop's own
state, then checked as the person meets Quire: the note, an agent in the Linux environment, and the Settings demo.
The laptop step is in `g14/`.

## What is in it

| | Commit | What |
|---|---|---|
| Base: the laptop's tree | #112 `25b899f` + #109 `3a81419` + #106 `10bd84a` + #104 `d15c25c` | the update machinery, 120 fps, the touchpad palm fix, the installer fix. No difference in `device/`, `aosp/` or `kernel/` from `481c5c8`, the tree of `openbook-ota-20261018-cand1` that the G14 runs |
| Quire, at the heads the Checker approved | #108 `dd56681` (with #94), #110 `52a3bc2`, #111 `72ee925` | Q2 platform hooks, Q5 the note, Q4 the Linux environment and `quired serve` |
| New in this PR (#113) | `7abe7f8`, `df1b47d` | the note reaches the Linux environment's agents; its transport is shut down before its reader is awaited, and released (the Checker's Hold on `7abe7f8`) |
| | `afb905e` | each update build gets its own fingerprint; `g14-adb.sh ota` refuses the running one |
| | `9c79987`, `b3be816`, `24273fa`, `419754e`, `f7e2891` | tooling: `pkg.env` quoting and `quire-qemu.py`; the rehearsal's bootsync probe as root; `g14-quire-check.py` |

Package `openbook-ota-20261019-quire2` (`packages/`): 994 MB, fingerprint `…/20261019.quire2:userdebug/test-keys`,
vbmeta `1d2d8f5e…`. The image build was `m exit 0` (first full build 30 min 44 s; the rebuilds after the fixes were
incremental). In its target files: `OpenBookQuire.apk` (new), `com.android.virt.apex` 64 MB with crosvm, virtmgr, vmnic
and the Terminal app (it was 1.4 MB without AVF), `openbook-pc-setup` with the KVM check; the composer
(`android.hardware.composer.hwc3-service.drm`, the 120 fps fix) is byte for byte the laptop's.
`openbook-ota-20261019-quire1.json` is the first package. It was never sent to the laptop: it has the running build's
fingerprint (below).

## The update, in QEMU from the laptop's state (`qemu/`)

The run `r2`, from `after-ab` (slot B with the new boot HAL: the G14 since 2026-10-18 23:24Z), with the real
`g14-adb.sh ota`:

| Case | What | Result |
|---|---|---|
| `ba` | the update the laptop gets: B → A through the boot HAL; PIN, app, setting, 4 MiB file and serial kept; no setup screen; the merge completes; ESP and `misc` agree; no denial for bootsync, the boot HAL or the ESP | 13/13 |
| `rollback-from-after-ab` | the same build with a kernel that cannot start (`-broken`): three tries, then slot B again by itself, data intact; then the good package from there | 13/13 |
| `cut-from-after-ab` | power cut at 40 %: slot B boots with its data; the re-run resumes and completes | 10/10 |

`qemu/SUMMARY.md` and `results.json` also list the 2026-10-18 cases of `r2` (`prep`, `ab`, `rollback`, `cut`), which
this package did not run. `qemu/ba-quire1-probe/`: the first `ba` runs failed one check, "bootsync from the package",
while the update itself was right. The harness looked for `/vendor/bin/openbook-bootsync` from an unprivileged shell,
which SELinux doesn't let see that binary; it looks as root now (`b3be816`).

## Quire in the updated VM (`quire-vm/`)

`scripts/ota/quire-qemu.py` boots a copy of `ba`'s result and runs, in order:

| Step | Result |
|---|---|
| `bridge/`: the Linux-environment adapter on the VM's Android runtime (`tools/bridge-test.sh`, the Checker's probe plus one case) | `df1b47d`: 23/23. The same test on `7abe7f8`'s sources: 21/23, failing exactly the Checker's two cases (idle close, descriptor after end of stream) |
| `linux-env/`: the guest image pushed over adb the way the laptop gets it (`linux-env-adb.sh check`; `quired` 0.2.1 built from `92ca342`, identical to `72ee925` under `quire/`) | 0 failures: KVM nested, AVF, the person's steps, running in 28 s, Quire core lists opencode 1.19.3, "QUIRE OK" from the guest |
| `quire/`: `g14-quire-check.py`, as a person: the shake and Meta+Space on the desktop | the note opens on screen, 68 to 86 px from the pointer |
| | over Settings the note is made and hidden (Settings hides overlays): the reviewed behaviour, reported |
| | the note lists "opencode · in the Linux environment"; Connect opencode; the prompt typed and sent with Enter; "QUIRE OK" in the note, `end_turn` in 7.9 s (`agent-answer.png`) |
| | the Settings demo: the platform's consent dialog, "Only this time", Display then Dark theme through the session in the mirror, Stop; Dark theme unchanged |
| | no crash or ANR of Quire, SystemUI or the Terminal app; no SELinux denial for Quire or AVF |
| | 18 PASS, 0 FAIL, 3 INFO |

## Found on the way

1. **Every OpenBook build had the same fingerprint** (`…/eng.builde:userdebug/test-keys`, no `BUILD_NUMBER`). After an
   update PackageManager kept its parse cache, which it keys by the fingerprint and, on `eng.*` builds, invalidates by
   mtimes that image files don't have. With `quire1`, the updated `com.android.virt` APEX kept the parse of the AVF-less
   build: `VirtualizationSystemService` never started, `IVmTethering` was looked up 1679 times, and the Linux environment
   stayed "starting" (`quire-vm/same-fingerprint/`). Quire's default notification grant was not applied either. With its
   own `BUILD_NUMBER`, the same tree works. `g14-adb.sh ota` now refuses a package with the device's fingerprint.
2. **The note and Q4's agents were not connected** at the approved heads. `7abe7f8` connects them; the Checker's Hold on
   its transport is fixed in `df1b47d` and waits for the recheck.
3. **`g14-adb.sh ota`'s `pkg.env`** broke on a quote in the manifest's tree text before anything was sent (`9c79987`).

## On the laptop (`g14/`)

| When (UTC) | What | Result |
|---|---|---|
| 05:45 | baseline: `state` and `capture --redact` (`capture-before/`, without the full logcat, dmesg and collect files) | slot B, `…/eng.builde`, vbmeta `e0ec4b9c…` |
| 05:45–10:25 | the previous run stopped at its usage limit right after the baseline | the kernel wake lock `anal225` it took against suspend stayed on the laptop (on AC) until 10:25, when this run released it |
| 10:25 | `state` again (the owner had used the laptop since), then `ota --dry-run` (`precheck.txt`) | checks passed: fingerprint differs, AC, update_engine idle, whole-disk install, bootsync on the device |
| 10:25 | `ota --yes` over Wi-Fi (`ota-apply.log`) | slot A written in 90 s; `verified slot a: images match vbmeta_a (1d2d8f5e…, the package's), ESP files in_sync, entry openbook-a+3.conf; systemd-boot starts slot a next` |
| 10:26 | the reboot | not done by me: the owner was using the laptop. The update waited as the next boot's default |
| 10:35 | the owner restarted and unlocked it | slot A, `…/20261019.quire2`, vbmeta `1d2d8f5e…`; marked good 10:35:24; merge completed 10:35:26; the ESP's default is slot A (`ota-status-after.log`) |
| 10:37 | `state` against 10:25 (`state-diff.md`) | the same user, PIN, 153 packages at the same versions (plus the 7 new ones), Settings (only boot counters, plus Quire as the assistant), 2 Wi-Fi networks, 1 account, the user's 163 files with an identical list hash |
| 10:38 | `capture --redact` (`capture-after/`), binaries, health | 22 yes, 1 NO (the installer's NVRAM entry, NO before too); the five changed binaries match the target files; 120 Hz; no crash, ANR or tombstone; no denial for Quire or AVF |
| 10:39 | AVF and the Linux environment's image | KVM, `IVmTethering` registered, Quire the assistant with its default grants; the guest image pushed, sha256 matches (`linux-env-push.log`) |

| 10:43 | the Linux environment on the G14 (`linux-env/`, `linux-env-adb.sh check`), at the owner's request not to wait for an idle laptop | 0 failures: KVM (`kvm_amd`, nested, NPT); the Terminal app installed the guest by itself and it ran after 21 s; Quire core reached `quired` 7.6 s after VM start and listed opencode 1.19.3; "QUIRE OK", `end_turn`, in 12.7 s |
| 10:45 | `g14-quire-check.py` on the G14 (`quire/`) | the shake and Meta+Space open the note on screen, 86 and 67 px from the pointer; over Settings it is made and hidden, as reviewed; the note lists `linux:opencode`; Connect opencode, the prompt typed, "QUIRE OK" in the note, `end_turn` in 5.3 s |
| 10:46 | the Settings demo | the platform's consent dialog ("Allow Quire to use screen automation with Settings?") opened, and a person at the laptop answered it at 10:46:44. The check had not found its button: the dialog isn't in uiautomator's dump. The session then opened Display and Dark theme in the mirror: "Opened Dark theme. In Settings · 2 taps · 12 s" (Quire's log). The check counts this as a FAIL, because its own step didn't tap the button |
| | health | no crash or ANR of Quire, SystemUI or the Terminal app. One denial the check counts as AVF's: system_server's OomAdjuster may not `setsched` AVF's virtio-sound helper (`crosvm_vu_snd`, AOSP policy); the Linux environment is unaffected |

Left out on purpose: the screenshots and UI dumps of the G14 run, because they show the owner's screen.

Follow-ups:
- `g14-quire-check.py` should find the consent dialog's buttons another way than uiautomator.
- Whether OpenBook allows system_server `setsched` on `crosvm_vu_snd`.

## Not covered here

- TalkBack, G14 frame timing and blur, and the taskbar button (Q5's own follow-ups); Q4's pairing.
- Test keys sign the update, as before; adb authorisation (`ro.adb.secure`) is unchanged, as the owner hasn't decided.
