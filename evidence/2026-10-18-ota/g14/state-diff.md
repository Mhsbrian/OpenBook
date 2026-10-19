# The G14's state before and after the update (`g14-adb.sh state`, read-only)

Values that identify the owner (serial number, package names, Settings values, Wi-Fi names, account names) are
withheld here; the full JSON stays on the build host. Before: 2026-10-18 23:21Z (slot A); after: 23:25Z (slot B).

| Fact | Before | After |
|---|---|---|
| boot_completed | 1 | 1 |
| build_date_utc | 1792331042 | 1792362725 |
| fingerprint | OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys | OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys |
| lock_disabled | false | false |
| media_files | 188 | 186 |
| media_kib | 552151 | 552143 |
| selinux | Enforcing | Enforcing |
| slot | _a | _b |
| user_state | RUNNING_UNLOCKED | RUNNING_UNLOCKED |
| vbmeta | 6d3735b9f31f31e923025243af06f6396673f8efcaef6b6fa3de862367498acf | e0ec4b9ccb2df1e7b01c41e097b3d2b4ee56d14a3d1ecbf92db28b49acaa4fac |
| wifi_networks | 2 | 2 |
| serialno | (withheld) | same |
| accounts | 1 | 1 (`dumpsys account` "Accounts: 1"; the counter in the JSON also matched session lines) |
| users | 1 | 1 (same) |
| packages | 153 | 153; versions changed: 0 |
| packages gone / new | ['com.android.provision'] | ['org.openbook.setup'] |
| Settings global | 156 keys | 156 keys; gone 0, new 0, changed: boot_count, global_color_palette_version, time_to_full_millis |
| Settings secure | 113 keys | 113 keys; gone 0, new 0, changed: none |
| Settings system | 43 keys | 43 keys; gone 0, new 0, changed: none |

**Reading it:**
- `com.android.provision` → `org.openbook.setup`: the image's setup app changed (#100, on `main` since the installed build).
  OpenBook setup steps aside on a provisioned system; the laptop came back to the launcher.
- The three changed global Settings are counters the system updates at every boot (`boot_count`) or while charging.
- **Shared storage, 188 → 186 files (−8 KiB):** the difference is in MediaProvider's own recovery database
  (`.transforms/recovery/leveldb-*`), which rotates its log files at boot. The owner's files (downloads, app data) are
  there. This was checked by count and by listing, not by per-file hashes: the "before" state kept no file list
  (`state` records one from now on).
- The laptop was unlocked with its PIN within a minute of the reboot (`RUNNING_UNLOCKED` at 23:25Z): the screen lock and
  the credential-encrypted storage came through the update.

