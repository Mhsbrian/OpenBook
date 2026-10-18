# openbook-bootsync host tests (openbook-live-20261018-anal192e.img)

56/56 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| fixture | the engine installs the live image onto a 64 GiB image file | PASS |  |
| installed | status: slot A's images verify against vbmeta_a | PASS |  |
| installed | status: slot A's ESP files are byte for byte what bootsync exports (kernel, both ramdisks, bootconfig) | PASS |  |
| installed | status: slot A good, slot B blank and without an entry | PASS |  |
| installed | status: systemd-boot starts openbook-a.conf (bootsync and the independent model agree) | PASS |  |
| installed | loader.conf as the installer wrote it | PASS |  |
| refuse-blank | activate b with slot B blank: refused | PASS |  |
| refuse-blank | the ESP is unchanged | PASS |  |
| refuse-corrupt | one byte of vendor_boot_b changed: refused (hash descriptor) | PASS |  |
| refuse-corrupt | the ESP is unchanged | PASS |  |
| refuse-key | activate b: refused (key_changed) | PASS |  |
| refuse-key | the ESP is unchanged | PASS |  |
| refuse-key | with --allow-new-key: accepted | PASS |  |
| refuse-unsigned | activate b: refused (unsigned) | PASS |  |
| refuse-unsigned | the ESP is unchanged | PASS |  |
| activate | activate b succeeds | PASS |  |
| activate | entries: openbook-a.conf and openbook-b+3.conf | PASS |  |
| activate | loader.conf: default openbook-a.conf, preferred openbook-b.conf, the installer's other lines kept | PASS |  |
| activate | B's bootconfig: slot _b, vbmeta_b's digest and size | PASS |  |
| activate | B's bootconfig keeps the install's own values (serial, boot_part_uuid, locale, installed) | PASS |  |
| activate | the entry: slot B's files, bootconfig last, version 'slot B', A's options | PASS |  |
| activate | openbook/b/kernel is boot_b's kernel | PASS |  |
| activate | fsck.fat: clean | PASS |  |
| activate | systemd-boot starts openbook-b+3.conf (bootsync and the independent model agree) | PASS |  |
| activate | status: slot B in sync, pending | PASS |  |
| again | activate b a second time: succeeds, the same files and contents | PASS |  |
| again | fsck.fat: clean | PASS |  |
| booted | systemd-boot's first try renames the entry (+3 -> +2-1; mren stands in) | PASS |  |
| booted | mark-good on b succeeds, after_update | PASS |  |
| booted | entries: openbook-b.conf only (A's goes: the merge overwrites slot A) | PASS |  |
| booted | loader.conf: default openbook-b.conf, no preferred line | PASS |  |
| booted | systemd-boot starts openbook-b.conf | PASS |  |
| booted | fsck.fat: clean | PASS |  |
| booted | mark-good again (every boot): nothing written | PASS |  |
| second | activate a on b succeeds | PASS |  |
| second | entries: openbook-a+3.conf, openbook-b.conf | PASS |  |
| second | loader.conf: default openbook-b.conf, preferred openbook-a.conf | PASS |  |
| second | systemd-boot starts openbook-a+3.conf | PASS |  |
| second | A's bootconfig: slot _a, the A build's vbmeta digest | PASS |  |
| second | A boots, mark-good on a: openbook-a.conf only, default a | PASS |  |
| second | fsck.fat: clean | PASS |  |
| rollback | after three failed tries (+0-3) systemd-boot starts openbook-a.conf | PASS |  |
| rollback | status on a: next boot a, B bad | PASS |  |
| rollback | mark-good on a: the preferred line goes, default a, B's bad entry stays | PASS |  |
| rollback | mark-good on a reports next boot a (the HAL resets misc to it) | PASS |  |
| reupdate | activate b again after the rollback: the bad entry replaced by openbook-b+3.conf | PASS |  |
| reupdate | fsck.fat: clean | PASS |  |
| cancel | activate a on a: B's entry and the preferred line go, A starts | PASS |  |
| disable | disable b on a: B's entry and the preferred line go, A starts | PASS |  |
| disable | disable a on a (the running slot): nothing changes | PASS |  |
| cut-files | stopped after 'files': fsck.fat clean, systemd-boot starts openbook-a.conf | PASS |  |
| cut-files | activate b again from that state completes | PASS |  |
| cut-entry | stopped after 'entry': fsck.fat clean, systemd-boot starts openbook-a.conf | PASS |  |
| cut-entry | activate b again from that state completes | PASS |  |
| cut-loader | stopped after 'loader': fsck.fat clean, systemd-boot starts openbook-b+3.conf | PASS |  |
| cut-loader | activate b again from that state completes | PASS |  |
