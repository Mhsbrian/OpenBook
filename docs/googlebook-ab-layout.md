# Ruby A/B layout and the OpenBook OTA pipeline (ANAL-229)

2026-10-22. The foundation for OpenBook-delivered full-system updates on the G14,
and the fix for the laptop's 98%-full data partition. Planning and the first
built/tested piece; nothing here touches the laptop.

## Two facts that set the direction

Both confirmed from the installed Ruby image (`avbtool info_image`, the GPT, and
the hardware update check on 2026-10-22):

1. **A single-slot system cannot take an OpenBook OTA through the stock
   updater.** update_engine writes the *other* slot's `boot`/`vbmeta` and a
   Virtual A/B snapshot of `super`, then one reboot switches. Ruby as installed
   has one slot (no `_b`). Even a system-only change needs a new `vbmeta`, which
   is a per-slot static partition — so there is no single-slot shortcut. The
   USB Update path stays the only no-repartition route; over-the-air needs a
   second slot. This is why the layout comes first.

2. **vbmeta must be rebuilt to cover the boot chain — and the pristine
   Googlebook image already does.** The *pristine* Googlebook `vbmeta_a` (signed
   with Google's key) covers the full chain: `boot`, `init_boot`, `vendor_boot`,
   `pvmfw` plus the six `super` partitions. Our *research* reassembler instead
   rebuilds `vbmeta` from only the six logical images, so our candidate's
   `vbmeta` omits the boot descriptors; the research image still boots only
   because `boot`/`init_boot`/`vendor_boot` are unchanged Googlebook originals
   loaded by the loader path. (An earlier note here, read off the research
   re-pack, wrongly said Ruby omits boot coverage.) For the A/B build we rebuild
   `vbmeta` the Googlebook way, covering the boot chain and signed with the
   OpenBook key. That lets `update_engine` verify a boot update **and** keeps the
   existing `openbook-bootsync` (ANAL-223) usable unchanged — it requires boot
   descriptors in `vbmeta_SLOT`, which are then present. No Ruby-specific
   bootsync mode is needed. Confirmed with `avbtool`
   (`evidence/2026-10-22-ruby-ab/vbmeta-coverage.json`).

## What already exists to build on

The OpenBook AOSP track already ships and has hardware-proven A/B:
`device/anybook/common/bootsync/` (the systemd-boot boot-control HAL and
`openbook-bootsync`), `scripts/ota/` (`make-ota.sh`, `ota-qemu.py`,
`bootsync-test.py`) and `scripts/installer/` (the install engine, `mklive.py`,
`e2e-qemu.sh`). The whole-disk A/B layout is specified in `installer.md` §3.2.
The Ruby work is to bring that layout and boot chain to the Ruby hybrid: build
the two-slot `super` and ESP, and rebuild `vbmeta` to cover the boot chain so
bootsync works unchanged (fact 2).

## The layout v2, sized for small and large OTAs (`scripts/googlebook/plan-ruby-ab.py`)

Partition sizes are fixed once the fresh installer writes them, so they are chosen
for the largest update the laptop should ever take, not for today's content. The
reference is Google's own two-slot Ruby layout, read from the GPT of Google's
recovery image (2026-10-22). Three rules, enforced by `validate()`:

1. **Every A/B partition in Google's layout exists, at least at Google's size.**
   update_engine fails if a payload names a partition the device lacks, and
   Google's vbmeta covers `pvmfw`. So `pvmfw`, `recovery` and `ota_recovery` are
   added (blank) and vbmeta grows to Google's 4 MiB. Any payload built for
   Google's partition set (Google's own, or one we capture and re-sign) finds
   every target.
2. **Partitions holding OpenBook content get ≥ 2× headroom:** our AMD kernel
   (25.6 MiB today) in `boot`, our ramdisks in `init_boot`/`vendor_boot`.
3. **super = 2 × Google's dynamic-partition group cap (24 GiB).** Even an update
   that rewrites the whole 12.88 GB group keeps its Virtual A/B snapshot inside
   super, so an OTA never depends on free space in /data. That matters on this
   laptop: /data reached 98% on 2026-10-22, and a v1-sized super would have
   needed /data for a large update.
4. The ESP holds both slots' boot files at their partitions' maximum sizes.

On the G14's 1 TB SSD:

| Partition | Size | Google's | Why |
|---|---|---|---|
| EFI | 1 GiB | 64 MiB (+ChromeOS KERN) | both slots' kernel+ramdisks at maximum, with margin |
| misc / metadata | 4 / 64 MiB | 4 / 64 MiB | Google's |
| boot_a/_b | 128 MiB | 64 MiB | OpenBook AMD kernel (25.6 MiB today) |
| init_boot_a/_b | 16 MiB | 8 MiB | OpenBook generic ramdisk (2.9 MiB today) |
| vendor_boot_a/_b | 64 MiB | 32 MiB | Google's own needs 30.3 MiB |
| vbmeta_a/_b | 4 MiB | 4 MiB | Google's (was 1 MiB in v1) |
| pvmfw_a/_b | 4 MiB | 4 MiB | new: in Google's vbmeta, so Google payloads may carry it |
| recovery_a/_b | 32 MiB | 32 MiB | new: present so Google-shaped payloads apply |
| ota_recovery_a/_b | 128 MiB | 128 MiB | new: present so Google-shaped payloads apply |
| super | 24 GiB | 12 GiB | whole-group update snapshot fits in super |
| userdata | **~905.7 GiB** | rest | was a fixed ~8 GiB single-slot |

Fixed system area ≈ 26 GiB (v1: 12.8 GiB); the OTA headroom costs 14 GiB of the
1 TB. Google's `desktop_security_*`/`frp_persist` partitions are not added: the
running system does not use them (absent today), and OTAs never write them.
`plan-ruby-ab-test.py` covers the rules (12 tests).

### Preflight for every OTA: `check-ota-fit.py`

Before any payload ships, small or large, OpenBook-built or a captured Google one,
`check-ota-fit.py --layout L --payload P` checks it against the installed layout:
every partition it writes exists; static images fit; all six dynamic partitions
are present (update_engine builds the new slot from exactly the payload's list);
groups fit super; the Virtual A/B snapshot (delta_generator's
`estimate_cow_size`, or the whole new size) plus growth fits super's free space
beside the installed slot, or how much /data it would need; both slots' boot
files fit the ESP; format sanity. It decodes the manifest itself (no AOSP
checkout needed; cross-checked against AOSP's generated bindings).
`check-ota-fit-test.py` (8 tests) includes the worst case: a whole-group rewrite
fits v2 but would have needed > 10 GiB of /data on v1, and a Google-shaped
payload carrying `pvmfw`/`recovery`/`ota_recovery` applies on v2 but not v1.

### Payload format choices (`build-ruby-ab-ota.py`)

- Complete: all six dynamic partitions plus the boot chain, always.
- Incremental when the installed source is known (`--source`), full otherwise.
- Virtual A/B snapshot compression **lz4** (delta_generator's default is gz,
  several times more CPU on the laptop during an update).
- Full payloads use **zstd** replace operations (`--enable_replace_zstd`),
  which decompress several times faster than the default xz.

## Milestones

1. **Layout** — done (`plan-ruby-ab.py`, tested).
2. **Ruby A/B image builder** — done, and the disk boots.
   - `build-ruby-ab-super.py`: the 12 GiB Virtual A/B `super`, geometry from the
     pristine Googlebook `super`, slot B an empty group, slot A byte-identical.
   - `build-ruby-ab-image.py`: assembles the disk — the two-slot GPT, slot A's
     boot images, `vbmeta_a` rebuilt to cover the boot chain (signed), and the
     ESP with systemd-boot and slot A in openbook-bootsync's layout, extracted
     exactly as `bootsync.c` does. openbook-bootsync's own `status` reports slot A
     `in_sync` byte-for-byte with a good entry.
   - `ab-qemu.py`: boots it as the internal NVMe in QEMU. All 9 checks pass:
     boot completed on slot A, the A/B boot HAL sees 2 slots and marked slot A
     successful (markBootSuccessful → bootsync mark-good), bootsync still in sync,
     userdata formatted at its full planned size and mounted (encrypted),
     metadata formatted, no AVB errors, no bootsync/HAL SELinux denials.
3. **OpenBook-signed OTA into slot B, reboot, fallback** — done, VM-proven.
   - `build-ruby-ab-ota.py` builds a complete payload (all six dynamic partitions
     + the boot chain; a partition left out does not exist in the new slot) as a
     full or **incremental** update (`--source`): the incremental for the test
     release is 2.66 MB, signed with the OpenBook key.
   - `ab-ota-qemu.py --phase apply`: the stock update_engine applies it, bootsync
     verifies and activates slot B, the system reboots (11/11). `--phase boot`:
     slot B boots, is marked good and merges (7/7). `verify-ab-slot.py`: merged
     slot B equals the release byte for byte (10/10 partitions). `--phase
     fallback`: with vbmeta_b corrupted, three slot-B attempts fail and
     systemd-boot starts slot A by itself; the update rolls back (7/7).
   - Evidence: `evidence/2026-10-22-ruby-ab/ab-ota-*.json`. VM runs use TCG (Ruby
     needs AVX-VNNI, which the Zen 4 build host lacks).
   - **Small and large, on layout v2** (`evidence/2026-10-22-ruby-ab/v2/`):
     `ab-ota-suite.sh` runs apply → reboot into B → byte-for-byte verify →
     fallback. A 2.69 MB incremental and a 5.04 GB full payload (system grown by
     2 GiB) both pass every phase; the large one's snapshot (7.17 GiB) stays in
     super.

4. **Fresh installer** for layout v2 — next. It writes exactly the v2 layout
   (now proven for small and large OTAs), erases the SSD, names it, keeps
   nothing. Explicit device-named approval before any physical install.
5. **Capture + patch Google OTAs**: the offer is visible to an authorized flow
   (seen on hardware 2026-10-22); rebuild stock partitions on the host, re-apply
   the OpenBook layer, sign with the OpenBook key, deliver via milestone 4.

## Reproduce

```sh
python3 scripts/googlebook/plan-ruby-ab.py \
  --candidate "$RB_20261022_01_CANDIDATE_DIR" --disk-bytes 1000204886016 --out layout.json
python3 scripts/googlebook/plan-ruby-ab-test.py

# assemble the disk and boot it (in the installer container)
scripts/installer/inst-docker.sh python3 scripts/googlebook/build-ruby-ab-image.py \
  --candidate "$CANDIDATE" --super-img "$AB_SUPER" --tools "$AOSP_HOST_BIN" --key "$AVB_KEY" \
  --out "$IMG" --disk-bytes 34359738368 --vm
scripts/installer/inst-docker.sh python3 scripts/googlebook/ab-qemu.py --image-dir "$IMG" \
  --qemu "$TCG_QEMU" --bootsync "$BOOTSYNC_HOST" --out "$VM"

# build + verify the A/B super (needs lpmake/lpdump/lpunpack on LD_LIBRARY_PATH)
python3 scripts/googlebook/build-ruby-ab-super.py --logical "$SLOT_A_LOGICAL_DIR" \
  --reference-super "$PRISTINE_GOOGLEBOOK_SUPER" --tools "$LP_TOOLS_DIR" --out "$OUT"
python3 scripts/googlebook/build-ruby-ab-super-test.py
```
