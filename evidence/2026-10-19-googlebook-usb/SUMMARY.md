# Experimental Googlebook USB write — 2026-10-19

The owner attached the previously discussed 62 GB SanDisk Ultra and requested
its update after being told about the VM stability failure. The single attached
USB matched that device. The operation used `scripts/installer/write-stick.sh`
from commit `86fc790bfdb8ff0f40977da9d8a37fe3b2691148`, first in dry-run mode,
then with its exact whole-device by-id confirmation. No new candidate was built.

- Device capacity: **62,109,253,632 bytes**, USB, removable SanDisk Ultra.
- Image size: **12,766,412,800 bytes**.
- Image and full device readback SHA-256:
  `5b21c93932dc39deb46b4462ebafcf17a943de93dbfd2d005d5233e142e66e1e`.
- Existing reports backed up: **3 files, 18,096 bytes**, retained privately
  under `$DATA/installer/stick-backup/20261019T191953Z`.
- Write: **717 seconds**. Full readback/hash verification: **96 seconds**.
- The writer completed successfully and powered off the stick. A subsequent
  block-device inventory no longer listed the USB. It is safe to unplug.

`result.json` records the result; `write-stick.log` retains the complete writer
output with the device serial and local data-root path redacted. The backup
reports themselves and recovery-derived image are not published.

This is the same candidate whose UEFI/USB VM run reached Google's welcome
screen and then suffered a system-server SIGSEGV/zygote restart. Missing zram
and desktop-service integration gaps also remain. Physical G14 boot, AMD GPU,
TPM, setup and application behavior have not been tested by this write.
The installed G14 system, internal storage and firmware were not modified by
this operation. The Googlebook installer option remains disabled.

For the first trial, select the stick in the G14's one-time UEFI boot menu,
then **Googlebook on OpenBook - experimental live boot** (the default entry).
Check welcome, keyboard and touchpad; note any restart, black screen or freeze.
Shut the live system down before removing the stick. Its userdata is fixed at
8 GiB; the remaining stick capacity is not automatically allocated.

VM evidence: `evidence/2026-10-19-googlebook-live/`.
Reproduction and trial instructions: `docs/googlebook-live.md`.
