# microG on the G14, over wireless adb (ANAL-210, 2026-10-19)

The owner asked on ANAL-210 to put microG on the installed G14 over wireless adb. ANAL-210 is the add-on itself; see `docs/gapps.md` §6.

## What the laptop ran
- `20261019.quire9` (the A/B update of 15:18 UTC, tree `17581de`, PR #115), slot B, SELinux enforcing, on AC at 88 %.
- That tree includes PR #80. Its `target_files.zip` has:
  - `SYSTEM_EXT/bin/openbook-addons`;
  - the catalogue `SYSTEM_EXT/etc/openbook/addons/microg.json`;
  - the init file without `stdio_to_kmsg` (824 bytes).
- So **no image update was needed**.
- Before the install: no `com.google.android.gms`, `com.android.vending` or `com.google.android.gsf`.

## What was done (15:34–15:37 UTC)
1. A heads-up on ANAL-222. No other adb session was open to the laptop.
2. The add-on's three APKs, checked against the catalogue on the host, were pushed to `/data/local/tmp/openbook-microg/src/microg/`: 112 MB in 5 s. Their sha256 matched on the laptop.
3. As root (`adb root`), the image's own `/system_ext/bin/openbook-addons --from-dir /data/local/tmp/openbook-microg/src run` ran. That is the code path of the add-on on the boot disk, with only the files' location different. It took 2.7 s. Output: `addons-install.txt`.
4. Checks: `after-install.txt`. Then the pushed files were deleted and adbd went back to `unroot`. No reboot, and nothing on the screen.

## Results
| Check | Result |
|---|---|
| Packages | `com.google.android.gms` 252432034, `com.android.vending` 84022634, `com.google.android.gsf` 8, all in `/data/app` |
| Grants | GmsCore 10/10: location (coarse, fine, background), storage read and write, accounts, notifications, phone state, SMS, `INTERACT_ACROSS_USERS`. Companion 1/1 (notifications). `SYSTEM_ALERT_WINDOW` allow; GmsCore exempt from battery optimisation |
| **Signatures apps see** | GmsCore and Companion: Google's certificate, SHA-1 `38918a45…` (the value microG's self-check compares). The proxy: microG's own `9bd06727…`, as expected. Read headless with `SigCheck` through `getPackageInfo(GET_SIGNATURES)`, the path an app's call takes |
| Location | microG is the fused provider at once. The network provider appears after the next restart (`docs/gapps.md` §6.5) |
| SELinux | no denial from microG (`untrusted_app_29`) or `openbook-addons`. The only OpenBook-type denials are 2 from our own read-only `ls` of the binary as the shell user, before the install |
| State | `/data/misc/openbook_addons/microg.json`: `installed`, 0.3.17.252432. At each boot, the service finds no add-on on the ESP and leaves the apps alone |

## Not checked
- **microG's own self-check screen.** The laptop had been idle for only 7 minutes, with Chrome in front, so no screen-driving check was run. The table above covers the same items: signature spoofing, the three packages and their signatures, the 11 permissions and app-ops, and the battery exemption.
- **Device registration and push.** They are off until the owner turns them on in microG Services.
- **Network location.** It needs a restart, then microG's online Wi-Fi lookup (the G14 has no GPS or modem).
