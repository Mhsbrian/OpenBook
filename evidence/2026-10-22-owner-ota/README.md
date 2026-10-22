# The owner OTA path (ANAL-229, 2026-10-22)

How an OpenBook update reaches the laptop without the USB stick. On a user build AOSP lets only
system_server, system_app, gmscore_app and a GKI hook talk to update_engine, so a release must add a
sanctioned path.

- **Policy** (`build-ota-trust-candidate.py --owner-ota-policy`): four rules, the owner's adb shell ↔
  update_engine (binder call/transfer, fd use). These are exactly the rules every VM apply used.
  Compiled with the platform's neverallow checks.
- **Rejected first:** letting update_engine read a payload staged in `/data/local/tmp`. The policy
  compiler refused it with AOSP's own neverallows (`shell.te`: other domains may not search that
  directory or open shell files: "passed around by file descriptor, but not directly opened"). The
  stock update_engine_client cannot pass a descriptor, so that path was dropped.
- **Delivery:** update_engine streams the payload over HTTP from the owner's host, the standard A/B
  delivery. No staging space is needed on the laptop, and plain http is allowed on user builds. The
  OpenBook signature check, not the transport, gates what installs. Tools: `serve-payload.py` (Range-
  capable, serves only the payload, stops when idle; 7 socket tests) and `g14-ota.sh` (preflight →
  read-only device checks → serve → apply → optional reboot; refuses without `--approved`).
- `candidate-r.json`: **candidate R** = RB-20261022-01 + the owner OTA policy, image `3999a99d…`. It
  changes only otacerts and the platform policy (and its hash).
- `candidate-r-v2-boot.json`: R on a v2 two-slot disk in QEMU, 9/9. Android recompiled the changed
  policy at boot; setup reached; 0 system_server crashes; no update_engine denials.
- `g14-dry-run.txt`: `g14-ota.sh --dry-run` on the G14 (RB-20261022-01): preflight fits, OpenBook
  certificate present, one slot → refused before serving, as designed until the fresh install.

Open: a VM rehearsal of the HTTP leg. The VNNI/GFNI-emulating QEMU build has no user-mode networking,
so it needs a rebuild with slirp (or passt). The first real wireless update follows the fresh install
onto layout v2.
