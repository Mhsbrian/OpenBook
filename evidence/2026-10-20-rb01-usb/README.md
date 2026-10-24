# RB-20261020-01 configured USB deployment

Source work: ANAL-228/229. Release: ANAL-233. Packaging source and approval are
recorded in `result.json` and `config/releases/RB-20261020-01-plan-v2.json`.
The corrected Android payload is unchanged from the prior RB01 input; the new
work enables only that exact transition and safely replaces/rebinds its installer.

The 41 regression checks, full encrypted-state observation and key-retention
check, both wrong-confirmation paths, normal-console cancellation and visual
review passed their functional assertions. Prior full-install/restart evidence
is reused because the installer program and build code are byte-identical;
the new source pin and final installer payload were independently verified.

The configured USB passed all protected-range and source-pin checks, then the
guarded writer performed another complete direct backup comparison, wrote only
super/vbmeta/EFI, verified the complete used extent using direct I/O, and powered
off. Owner data was never booted in a VM. No laptop/firmware write occurred.

One known system-server crash recurred during the 760.7-second VM observation.
Preservation and installer checks do not establish stability or physical G14
acceptance. USB boot, existing credential unlock/apps and trackpad behavior are
pending owner hardware checks. No automatic rollback is claimed.

Configured attempt 1 stopped at the input/output path guard before creating an
image. The container backup mount was corrected; frozen source and image inputs
did not change. Both attempt logs are retained privately.

Cleanup manifests enumerate only completed scratch from this task and record
actual filesystem free space before/after; they do not infer reclaimed bytes
from sparse/reflink apparent sizes. Candidate/installer artifacts, original
backups, recovery records and all test evidence remain. Private raw logs,
images, keys and cleanup paths are not included here.
