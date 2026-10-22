# Google's Ruby October update, 16658739 (ANAL-229, 2026-10-22)

The owner pressed Check for update at 19:37. GMS completed its server check-in but handed nothing to
update_engine (no metadata fetched, no ApplyPayload), so there was no offer to intercept; the log window
covered the whole check. The same evening Google's public recovery listing switched Ruby from 16452207
(2026-10-05) to **16658739, CL3B.260622.276.R4 (2026-10-22)**: the full release, downloaded for the
owner's device only and verified against Google's MD5. It is kept private, never redistributed.

`review.json`: what changed (`diff-google-builds.py` on the two staged builds). It's the October security
update (2026-09-01 → 2026-10-01): 104 files in system, 40 in system_ext, 133 in product, mostly APEX
modules and Google apps. Nothing added or removed, the same partition sizes, and no SELinux or VINTF changes.
Every OpenBook patch layer's anchor is unchanged: the trackpad patch, the certificate swap and the owner
OTA policy apply as-is; Digitalis needs only its base pin moved. Google's vendor, kernel and boot changed
too, but the hybrid uses OpenBook's.
