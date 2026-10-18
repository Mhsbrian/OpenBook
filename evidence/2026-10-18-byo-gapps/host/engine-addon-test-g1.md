# Install engine, add-on path (ANAL-210): 19/19

| Case | Check | Result |
|---|---|---|
| inventory | add-to-image.sh puts the add-on on a copy of the live image | pass |
| inventory | plain stick: microg catalogued, not on the stick | pass |
| inventory | add-on stick: on the stick, with its title, version and size | pass |
| same-plan | plan without add-ons succeeds | pass |
| same-plan | no add-on key, operation or file in it | pass |
| same-plan | main's engine accepts it (its own re-computation has the same sha256) | pass |
| old-apply | main's engine installs and verifies it | pass |
| plan-addon | plan with --addon microg succeeds | pass |
| plan-addon | the request names the add-on | pass |
| plan-addon | a check_addon operation right after check_source | pass |
| plan-addon | the three APKs, with the image's sha256 and size, from the same path on the stick | pass |
| apply-addon | the install verifies | pass |
| apply-addon | the new EFI partition holds the three APKs with the pinned sha256 (mtools read-back) | pass |
| apply-addon | the new EFI partition passes fsck.fat | pass |
| apply-addon | every other file is as in the plan | pass |
| refuse-not-on-stick | --addon on a stick without it: refused, no_addon | pass |
| refuse-no-catalogue | --addon on an image without the catalogue: refused, no_addon | pass |
| refuse-corrupt | a corrupted add-on APK: apply refuses at check_source | pass |
| refuse-corrupt | the target is unchanged | pass |
