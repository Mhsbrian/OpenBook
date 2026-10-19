# PR integration: Q6 confirmation corrections

The owner requested merging the open PRs. PR #115 at `96080bf` still reproduced both review findings: unclassified taps/submission and agent Undo of sensitive settings bypassed confirmation.

The fixes ask before those dispatches and before restoring the resolved sensitive change entry. Denial leaves the fake dispatch/settings untouched. Ordinary typing, identified non-sensitive taps and non-sensitive Undo remain automatic. The person’s explicit Undo click remains separate.

`python3 device/anybook/common/quire/tools/policy-test.py`: 17 pass, 0 fail. Against `96080bf` via `QUIRE_POLICY_SOURCE`: 5 pass, 12 fail. This adapts ANAL-217’s original production-code host probe with its boundary fakes and adds allow, unlabeled-target and per-setting Undo cases. The full ControlTools file and unchanged settings method text are compiled from the selected tree. These are dispatch tests, not actual message sending or real settings writes.

`compile-check.sh`: 53 app files, 357 classes, zero warnings; probe 2 files, 4 classes, zero warnings. No device, image rebuild, OTA, or model operation in this task.

Additional integration checks: Go race tests pass across all packages; Quire host tests 37/37; connector tests 10/10; PC setup and build-unmount fixtures pass; a fresh isolated gestures build at `6c2310952338` passes 8/8 replay tests; prototype and eight-wallpaper contrast checks pass. Syntax checks pass for 22 changed Python files and 27 shell scripts. No unresolved conflict markers. The upstream OFL license remains byte-for-byte unchanged despite its CRLF/trailing whitespace.

Production integration matches the original #115 tree except for the documented Q6 corrections and the additions from #114 (design checks), #116 (Mesa YV12/microG diagnostics) and #117 (touchpad diagnostics). Existing G14/QEMU evidence was inspected; no new full OS build, VM boot or device deployment is claimed. PR screenshot URLs are pinned to immutable commits before branch cleanup.
