# PR integration: Q6 confirmation corrections

The owner requested merging the open PRs. PR #115 at `96080bf` still reproduced both review findings: unclassified taps/submission and agent Undo of sensitive settings bypassed confirmation.

The fixes ask before those dispatches and before restoring the resolved sensitive change entry. Denial leaves the fake dispatch/settings untouched. Ordinary typing, identified non-sensitive taps and non-sensitive Undo remain automatic. The person’s explicit Undo click remains separate.

`python3 device/anybook/common/quire/tools/policy-test.py`: 17 pass, 0 fail. Against `96080bf` via `QUIRE_POLICY_SOURCE`: 5 pass, 12 fail. This adapts ANAL-217’s original production-code host probe with its boundary fakes and adds allow, unlabeled-target and per-setting Undo cases. The full ControlTools file and unchanged settings method text are compiled from the selected tree. These are dispatch tests, not actual message sending or real settings writes.

`compile-check.sh`: 53 app files, 357 classes, zero warnings; probe 2 files, 4 classes, zero warnings. No device, image rebuild, OTA, or model operation in this task.
