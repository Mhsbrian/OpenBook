# ANAL-211 (G2): bring your own Google apps package, an advanced installer step (2026-10-18)

Write-ups: `docs/installer.md` §15 and `docs/gapps.md` §5. **Only synthetic packages were used:** OpenBook's own dummy APKs and XMLs in LiteGapps' layout, built in the repo (`scripts/gapps/`). No Google package was downloaded, used or committed. Nothing ran on the G14; its steps are on ANAL-192.

**Image:** `openbook-live-20261018-anal211b`.
- What it is: the G14 product (`anybook_g14_x86_64-cp2a-userdebug`) from this branch at `66b6a65`. That is `main` `81578c1` (with ANAL-210's microG, #80) plus #83's boot-animation link.
- Build: built and staged under the lane lock; an incremental build of 1 min 21 s.
- sha256 `7b77b5a9299559968cfa7e8be7125d0d4e117c1c3c00eb4b741e055d2b31910c`.

## Results

| Test | Result | Files |
|---|---|---|
| Host tests (`scripts/gapps/engine-gapps-test.sh`), engine `66b6a65` against `main` `81578c1` | **89/89**. The check covers 3 encodings accepted and 26 negative packages, each refused with its rule. Without the step, installs are byte-identical to `main`'s engine. The install with the package is checked from outside the engine by `lpdump`, `avbtool info_image`/`verify_image`/`add_hashtree_footer`/`calculate_vbmeta_digest`, `fsck.erofs --extract` and xattr labels. Also covered: alongside a Windows-like disk, and a 256 MiB app at scale (check 1.5 s, install 15.8 s) | `host/engine-gapps-test.md` and `.json`, `lpdump.txt`, `product_a.avbinfo.txt`, `product_a.verify.txt`, `vbmeta_a.avbinfo.txt`, `labels.json`, `install-report.json`, `apk-certs.txt`, `packages.sha256` |
| The installer's own host suites with this engine | `engine-test.sh` 63/63 (on `anal206b`), ANAL-210's `engine-addon-test.sh` 19/19 | `host/engine-test-base.md`, `host/engine-addon-test-g1.md` |
| QEMU end to end (`scripts/gapps/gapps-e2e-qemu.sh`), `anal211b`, enforcing | **79/79** | `qemu-b/SUMMARY.md`, `results.json`, per case `sections/`, `serial.log.gz`, `report.json`; `qemu-b/inspect/`; `qemu-b/screens/` |
| — power cuts at five points of the package step (256 MiB package) | old table · blank · blank · blank · new table not activated: only the states the installer already guarantees (S9) | `qemu-b/g-cut-*`, `qemu-b/inspect/g-cut-*.json` |
| — the wizard: switch, package page, DocumentsUI on the USB drive, check, warning, Confirm, install | Done, verified, root digest `7860cb4a…`, vbmeta digest `82207cbb…`, 73 s | `qemu-b/screens/g4*.png`, `g5-confirm.png`, `g6-install.png`, `g7-done.png`, `qemu-b/g-ui/report.json` |
| — the installed disk alone | Enforcing, orange. `product-verity` with the report's root digest, `partition.product.verified=2`, and all product files readable. The three apps run from `/product`: privileged where in `priv-app/`, with the allowlisted permission and the default grants; the package's feature and power-save entries are read. Setup's step 4 and Settings › About show the (fake) GSF Android ID | `qemu-b/g-installed/sections/`, `qemu-b/screens/g-setup-register.png`, `g-settings-about-end.png`, `g-settings-register.png` |
| — one byte flipped in a package file inside the rebuilt product | `device-mapper: verity: 254:3: data block 74292 is corrupted` (the flipped block), then `Restarting system with command 'dm-verity device corrupted'` | `qemu-b/g-verity/` |
| Round 1, image `anal211a` (`98a3673`, before the latest `main`) | 78/79. The one failure was a real finding: `openbook_installd` was denied reading `ro.control_privapp_permissions`. Fixed (`get_prop`); 0 such denials in round 2 | `qemu-a/SUMMARY.md`, `qemu-a/g-ui/sections/avc.txt` |

## Not shown here
- **The G14.** Its steps are on ANAL-192.
- **A real GApps package.** The owner may try one locally; nothing from it may be committed.
- **OTAs** (`openbook-bootsync` isn't built): an update would replace `product` (H).
- **Fuzzing of the package parser.**
- **Other denials** in these boots aren't this step's: ANAL-210's `openbook-addons` writing `/dev/kmsg_debug`, MediaProvider and the test shell, SystemUI and `bluetooth_lea_prop`.

## Reproduce
`docs/installer.md` §15.9.
