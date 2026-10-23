# Two-slot fresh install from the stick (ANAL-229, 2026-10-23)

The stick's own installer can now set the laptop up on the two-slot layout (v2): the
new menu entry **Fresh install Googlebook to SSD (two slots) - ERASE SSD DATA**
lays the stick's pinned system out as the Ruby A/B disk that was built and booted
in QEMU. Development build `candidate-R-ab-dev`. Nothing was written to any physical device.

**How:** `build-ruby-ab-install.py` compares the A/B reference image with the stick and records
where every byte comes from. Every partition except userdata's interior is covered exactly,
and the plan is bound to the stick pin's SHA-256.

| Source | What | Bytes |
|---|---|---|
| The stick (`usb`) | boot images and the six logical partitions, byte-identical | 3,736,584,192 |
| The bundle | ESP, super's LP metadata, re-signed `vbmeta_a` | 38,297,600 |
| Zeros | slot B, misc, metadata, super's free space, userdata's two edges | 23,936,884,736 |

The bundle is embedded in the installer initrd. `migrate.py --fresh --ab-plan` checks the plan against
the pin and the bundle, clears the old partition table first, then writes and reads back each region.
The new GPT is written last, sized to the actual disk. A power cut or failed readback therefore
leaves no bootable half-install.

| File | What it shows |
|---|---|
| `ab-install.json` | the plan: partitions, GUIDs, 36 writes with SHA-256s |
| `ab-install-proof.json` | the real engine ran the plan into a blank 1 TB disk: 27.7 GB compared, identical to the reference outside userdata's interior |
| `installer-build.json` | installer `openbook-ruby-installer:anal229-ab`; same kernel and packages as RB-20261022-01's installer; pin `d49502ef…` |
| `stage-b-update.json`, `final-update.json` | stick menu change: the two-slot Fresh entry replaces the one-slot one; the single-slot Update/Restore entries are retired. Writes `EFI`/`vbmeta_a`/`super` only; protected bytes unchanged |
| `stick-candidate.json` | candidate R system (RB-20261022-01 + owner OTA policy) on the RB-20261022-01 stick image → `42c934f1…` |
| `rehearsal-install.json`, `install-transcript.txt` | QEMU booted this stick image's two-slot entry, typed the disk and `FRESH ERASE <serial>`; installed in 79 s; installed NVMe identical to the reference (27.7 GB compared); stick and decoy disk unchanged |
| `rehearsal-boot.json` | the installed NVMe booted: 9/9 (boot completed on slot A, boot HAL sees two slots, slot A marked successful, bootsync in sync and good, userdata formatted at 905.7 GiB and mounted, metadata ext4, no AVB errors) |

**Limits:**
- Not run on the G14.
- The physical TPM (Google's `gscd`) keeps the current install's state. A VM always starts with a fresh TPM.
- The G14's exact SSD size is read at install time and shown before confirmation; the plan fits any disk with at least 8 GiB of userdata.
- The VM boot adds a serial console to the installed entry on a copy (test fixture); production keeps the hardware entry.
