# First wireless two-slot update on the G14 (ANAL-229, 2026-10-23)

Owner approval: ANAL-229 `01a168b1…` ("Yes, you can test"). The test update reinstalls the installed
release, RB-20261023-02 (Google 16658739 patched for the G14), into the other slot. The system does not
change, so the test isolates the update machinery: delivery, signature, snapshot apply, slot switch,
"mark good" and merge.

**Payload** (`payload-laptop.json`, `fit-laptop.txt`): OpenBook-signed incremental, all ten partitions,
150,380 bytes; metadata signature verifies against the OpenBook certificate; fits (0.05 GiB snapshot,
20.65 GiB free in super).

**VM rehearsal first** (`vm/`): the same kind of payload on RB-20261023-02 plus the disposable apply
harness (built on the 16452207 base, carried to 16658739 with `rebase-google-build.py`).

| Phase | Result |
|---|---|
| apply | 11/11 |
| boot into slot B | 7/7, merged |
| verify | slot B byte-identical to the release, 10/10 |
| fallback | corrupt `vbmeta_b`: three failed B boots, then slot A; rolled back |

The suite's `summary.json` marks fallback `false`. That was a judge bug: it counted update_engine's
rollback cleanup line ("unmapped snapshot system_b") as a slot-B boot. With `booted_slot()` reading
only first-stage init lines (`ab-ota-qemu-test.py`), the same recorded logs judge 7/7
(`vm/fallback-rejudged.json`).

**On the laptop:**
1. `g14-dry-run.log`: running slot A, OpenBook certificate present, second slot present.
2. `laptop-apply-attempt1-lan.log`: the payload was served on the host's LAN address. The host
   firewall (ufw) dropped the laptop's connection, so update_engine reported
   `kDownloadTransferError`. Nothing was written.
3. `laptop-apply.log`, with `g14-ota.sh --via-adb`: the server ran on the host's 127.0.0.1, reached
   through `adb reverse` over the encrypted wireless-debugging connection. One ranged GET, then
   `ErrorCode::kSuccess` in 56 s.
4. Waited until the laptop was idle for 10 minutes, then restarted. Boot completed 52 s later on
   **slot B**.
5. `merge-after.txt`: update_engine idle; `--merge` reports `kSuccess`; "CleanupSuccessfulUpdate has
   previously completed".
6. `state-diff.md`: users, packages, per-user account counts and settings counts unchanged; same
   build and vbmeta digest.
