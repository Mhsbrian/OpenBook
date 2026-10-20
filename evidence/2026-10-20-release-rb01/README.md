# RB-20261020-01, plan v1

This is the private Ruby/G14 corrective candidate continuing Fresh28, tracked
in Multica ANAL-233 under the ANAL-232 release hub. B Honey's verified comment
`01a15ab6-d813-746b-89f2-4884a7af9b03` authorizes the previously presented plan
and synthetic VM tests. It does not authorize a PR merge or physical write.
The unchanged plan is `config/releases/RB-20261020-01-plan-v1.json`;
`result.json` records its exact hash, source commit and actual artifact hashes.
The final image SHA-256 is
`7d0900ec13f41b08130ed99fc800f4739ab89ff8be6a046df908094a38220bc0`
(12,766,412,800 bytes). All required functional assertions completed; this is
a candidate for review, with the runtime limitations below.

The recipe uses the normal input-correction builder and offline installer from
`8294358eabd121c92e926768f8fdffa8894b9638`. It starts with pristine synthetic
camera25, corrects the input timestamp handling and AVB boot parameters,
regenerates the installer pin, and packages the fresh/migration/live choices.
The experimental native OTA guard and its test policy are excluded. No owner
data is used and QEMU networking is disabled.

## Evidence and limits

The result records full image/manifest/installer hashes, 7,292 metadata rows,
3,464 file/symlink comparisons, the sole eight-byte system-library change,
correct 4,032-byte unpadded AVB size and protected-range equality. It also
records 62 regression tests, eight actual-library native assertions, tool
identities and replay-source provenance.

The installed-preparer regression intentionally uses its retained exact-profile
fixture. This candidate is separately verified through the full builder audit,
native checks and VM tests. Those tests do not qualify this new artifact for
the existing current-laptop updater.

VM observations cover 760 seconds of live UEFI boot, a 1 TB fresh install,
restart without the USB, synthetic encryption-key retention, wrong erase
confirmation and the normal framebuffer/keyboard cancellation path. The restart
clone selects the existing serial entry to make boot observable; this is test
instrumentation and does not change the candidate's production boot entries.
See `result.json` for exact outcomes and runtime crash counts. Boot/storage
success does not establish system stability or physical credential unlock.
System-server fatal signals occurred once during live boot, twice after fresh
installation and once during restart, each with zygote exit/execmem findings.
These are not clean stability passes. Both cancellation tests preserve all
three disks; visual review confirms the erase warning, target-selection prompt
and subsequent power-off prompt on the normal console.

The live collector completed its ten-minute capture with no kernel overruns,
failed saves or unsaved bytes. An additional synthetic wake key during that
observation did not establish visible UI output; Android boot/setup is
established by captured logs, not the blank interim screen.

Attempts 1–4 stopped before image assembly while correcting test invocation,
fixture paths and passing-log recognition. Their logs are retained. Attempt 5
reuses five passed suites from attempt 2 after matching the pinned source,
builds the replay fixture from the recorded retained source, and assembles the
candidate. No failed artifact is promoted and no source/plan changes occurred.

## Retention and next operation

`cleanup.json` records actual host free-space changes. Completed extracted
trees, intermediate partitions and disposable test disks are removed only after
their results are collected. Private cleanup manifests retain the exact path
allowlists. The candidate, corrected input, installer, source pin, baselines,
owner backups, logs, screenshots and provenance remain private. Repeating
removed VM fixtures requires recreating them from the retained inputs.
The two scoped cleanup passes recovered a net **45.81 GiB**, leaving
**69.36 GiB free** at handoff. No owner backup, physical disk, unrelated task
or active build was removed. Future project work now budgets peak allocation
plus at least 40 GiB free reserve and records its cleanup.

This synthetic image must not replace the configured stick's current data.
The next operation needs the actual USB, a fresh verified backup and a
preserving preparation, followed by separate approval naming the resulting
checksum and exact device. No installed/stick pointer is advanced here.
Current-laptop data-preserving updates, encrypted-data expansion, automatic
Ruby rollback, Bluetooth microphone transport and speaker-stutter fixes remain
outside this release.
