# On-laptop updater, phase 2 groundwork (ANAL-229, 2026-10-23)

**Owner requirement:** a visible, themed app, **OpenBook Update**, with notifications and an explicit
"install and restart" approval, not a hidden service. Design: `docs/googlebook-on-device-updater.md`.
This work proves the engine and its SELinux domain on the real image, and makes the rebase able to
carry them onto future Google builds. The init-service build is VM validation only; the app replaces it.

| Evidence | Result |
|---|---|
| `candidate-service.json` (`build-updater-candidate.py`, base RB-20261023-02 `75fa0196…`) | engine + `openbook_updater` domain. Policy compiled with the image's exact policy inputs, neverallows included; sources match `pins.json` |
| `vm-service-boot.json`, `vm-prod-init-lines.txt` | boot 9/9 on two slots; service started; **0 denials** |
| `vm-vmcheck-boot.json`, `vm-vmc-init-lines.txt` | boot 9/9; one check as `nobody` in its domain: `exited with status 3` in 3.4 s, the clean network error in a NIC-less VM; **0 denials** |
| `rebase-reproducibility.json` | candidate R → 16658739 rebased twice with the new append-merge, recompile and content-derived UUID/salt: byte-identical `system` and vbmeta; content equal to the shipped `75fa0196…` |

## Review

Two rounds over this work; every valid finding fixed and tested.

**First round:**
- `log()` hid toybox `log` and recursed;
- a here-document needed `/data/local/tmp`;
- the rebase couldn't carry the policy edits onto changed Google policy;
- the added-files record certified itself, so it needs `pins.json`;
- the daily `sleep` stopped during suspend;
- the lock was held for the service's lifetime;
- automatic downloads ran without consent;
- a type guard was missing; additions were normalised in several places;
- the log grew without bound.

**Second round:**
- the first check was 15 minutes late;
- the service variant was marked deployable;
- auto-download didn't check for metered networks;
- the policy compile lacked the reviewed-version guard and duplicated the input list;
- file contexts weren't a pure append;
- the hash-file branch could fail with a KeyError;
- a stale kmsg note;
- a backwards clock jump could postpone checks;
- STATUS.md wasn't updated.

The VM also exposed what neither round predicted: `stdio_to_kmsg` writes through `/dev/kmsg_debug`,
labelled `tmpfs`, and `/dev/kmsg` is `0600 root`. Dropped; the updater logs to logcat and its own capped file.
