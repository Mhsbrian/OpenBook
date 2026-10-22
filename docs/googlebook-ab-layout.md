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

## The layout (built: `scripts/googlebook/plan-ruby-ab.py`)

`plan-ruby-ab.py` turns a reviewed single-slot Ruby candidate into the two-slot
whole-disk plan, anchored to the candidate's real partition sizes, and validates
it (contiguous, MiB-aligned, within the disk, matched slot sizes, `super` ≥
content, `userdata` last). On the G14's ~1 TB SSD, from the RB-20261022-01
candidate:

| Partition | Size | Source |
|---|---|---|
| EFI | 512 MiB | candidate (two slots of ESP boot artifacts) |
| misc | 4 MiB | blank |
| boot_a / boot_b | 64 MiB each | candidate / blank |
| init_boot_a / _b | 8 MiB each | candidate / blank |
| vendor_boot_a / _b | 64 MiB each | candidate / blank |
| vbmeta_a / _b | 1 MiB each | candidate / blank |
| metadata | 64 MiB | blank |
| super | 12 GiB | candidate (Virtual A/B) |
| userdata | **~919 GiB** | blank |

Fixed system area ≈ 12.83 GiB. `userdata` goes from the fixed ~8 GiB it is now
to ~919 GiB — the storage fix. Slot B starts blank; the first OpenBook OTA fills
it and one reboot switches. `plan-ruby-ab-test.py` covers it (7 tests).

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
3. **QEMU: OpenBook-signed full OTA into slot B** — next. Build an
   OpenBook-signed Virtual A/B payload from a release, apply it through the stock
   update_engine, let bootsync `activate b`, reboot-switch, `mark-good`, merge;
   then a **broken slot B → automatic fallback to A** (bootsync's 3-try counter).
4. **Fresh installer** for this layout (erases the SSD, names it, keeps nothing),
   which is the install the owner is waiting for. Explicit device-named approval.
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
