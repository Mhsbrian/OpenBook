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

## Intercept → patch → update: turning Google's updates into G14 updates

The goal of ANAL-229. Five stages; the first two are built and verified.

1. **Intercept** (`capture-google-ota.py`). Google offers updates to the G14 per
   device (seen 2026-10-22; the public recovery manifest still lists only
   16452207, dated 2026-10-05). After the owner presses *Check for update*, the
   offer is read from the laptop's logs over adb, read-only: the URL, payload
   offset/size and hash headers from update_engine's ApplyPayload request, or an
   OTA-like URL from GMS logs (with the OpenBook certificate installed, GMS may
   stop before update_engine). Saved privately; other Google downloads (speech
   packs etc.) are never taken as offers.
2. **Inspect, download, reconstruct** (`inspect-google-ota.py`,
   `stage-stock-source.py`, `reconstruct-google-release.py`). Read the OTA zip by
   HTTP Range: Google's metadata (from/to build), the payload manifest, and, for
   an incremental, whether every source partition matches our staged stock
   16452207 images (all 13 of Google's slot-A partitions). Download and verify
   the payload against Google's FILE_HASH, then rebuild Google's new partitions
   with AOSP's `ota_extractor`, each checked against the hash in Google's signed
   manifest. Proven on our own incremental: byte-identical output; a wrong
   source is refused.
3. **Patch** (rebase the OpenBook layer onto Google's new framework). Mapped,
   not built yet. Today's hybrid keeps Google's `system`, `system_ext` and
   `product` byte-for-byte over OpenBook's AMD vendor stack, made by
   `gbos-unpack.sh` → `compat-audit.py` (VINTF + strict SELinux compile) →
   `hybrid-probe.py prepare` → `live-image.py`, then the RB patch layers. Plan:
   - an adapter from `reconstruct-google-release.py` output to the
     `gbos-unpack.sh` layout, so `compat-audit.py` and `hybrid-probe.py` take a
     new Google build unchanged; their Google-specific checks (TPM ueventd rule,
     timberslide rc, Wi-Fi overlay) fail loudly if Google changed those files;
   - one combined `build_system()` pass for the system patches, plus
     `build-module-candidate.py` for the lid guard (vendor side, no Google pin);
   - re-derive the trackpad correction per build: it is an 8-byte patch pinned
     to the whole `libinputflinger.so` hash (or drop it if Google fixed the bug);
     Digitalis is content-based, but its builder must come onto this branch
     (PR #124); the certificate swap pins Google's stock `otacerts.zip` (likely
     unchanged while Google keeps its key);
   - golden test first: rebuild today's release from stock 16452207 through the
     new pipeline and compare it with RB-20261022-01 / candidate R.
   Risks: the new framework's VINTF matrix against the fixed OpenBook vendor and
   6.18 kernel; SELinux mapping `202604` and the regenerated policy hashes;
   system size; Digitalis against Google's new libraries.
4. **Sign and prove**: `build-ruby-ab-ota.py` (OpenBook key), `check-ota-fit.py`,
   VM boot and the small/large OTA suites.
5. **Update**: a new Google framework changes `system_ext` and `product`, which
   the single-slot USB Update path refuses (`preserve-update.py`,
   `laptop-update.py`: only `system`/`vendor_dlkm`). So patched Google updates
   reach the laptop through the two-slot layout: fresh install onto v2, then
   OpenBook-signed OTAs (`g14-ota.sh`, automatic fallback).

## On-device: the self-contained updater (ANAL-229's end state)

The five stages above are proven, but they run on the build **host** and are driven
by hand (today, with an AI assistant). That is the development harness, not the
product. The goal is that **the laptop does this itself**: notice Google's update,
download it, adapt it to the G14, and install it — no workstation, no assistant in
the loop. The host pipeline exists to prove each step is deterministic and correct
*before* it is moved onto the device.

**What the laptop already holds**, so it needs no host for the parts that matter:
its OpenBook AMD vendor stack (`vendor`, `vendor_dlkm`, `system_dlkm`, the boot
chain) — these never come from Google; the currently-installed Google framework;
and the OpenBook `otacerts.zip`, so it trusts OpenBook-signed updates, not Google's.

On-device form of each stage (an OpenBook privileged service shipped in the image):

| Stage | Host harness (proven) | On-device component |
|---|---|---|
| Watch / notice | `capture-google-ota.py` over adb; `watch-google-ruby.py` | reads its *own* update offer / polls the recovery manifest locally |
| Download | `inspect` + `reconstruct` on the host | fetches Google's package to local scratch |
| Adapt (patch) | host rebase: unpack → re-apply layers | extract Google's new framework, merge with the resident vendor stack, re-apply the fixed patches (deterministic file ops) |
| Sign | OpenBook master key on the host | **device-local key**, its public cert enrolled in this laptop's `otacerts.zip`; the master key never leaves the build host |
| Install | `g14-ota.sh` streams from the host | local client hands the signed payload to the resident `update_engine` → slot B → reboot, with A/B fallback (milestone 3, driven locally) |

**The one decision that shapes the build — signing on-device.** `update_engine`
installs only payloads signed by a key in `otacerts.zip`. For the laptop to sign
the update it adapts, it needs a private key present. The clean, safe model:
generate a **per-laptop key on the device**, bake its public cert into that
laptop's hybrid at install time, and keep the private key in a protected on-device
store. The master OpenBook OTA key stays on the build host (constraint: it never
enters an image, a log, or a device). This is legitimate — the owner's device, the
owner's key, no bypass of Google's or anyone else's protections — but it is a
security choice the owner should confirm.

**What moving on-device still needs** — honestly, a milestone, not a script:
- the two-slot **v2 layout on the laptop** (milestone 4): a single slot cannot do
  A/B, and `/data` is ~93–98% full with no room to stage a download. The on-device
  updater presupposes the fresh install that has been on hold;
- the small toolset built for **x86_64 Android** and shipped in the OpenBook image
  (partition extract, payload generation, `avbtool` / erofs / `secilc` equivalents),
  so no host tools are needed at run time;
- the patch steps reduced to **deterministic on-device operations** — the trackpad
  8-byte patch, the certificate (already resident) and the native-bridge
  properties/libraries are plain file edits; the heavier compat / VINTF / SELinux
  checks either run from their Android-native tools on-device, or are pre-validated
  per Google base build by the host harness before that base is trusted.

Until those land, the host pipeline is how a patched Google update reaches the
laptop; the on-device service is the target it converges on, one proven stage at a
time.


## The owner OTA path: how a wireless update reaches the laptop

On a user build, AOSP lets only `system_server`, `system_app`, `gmscore_app` and a
GKI hook talk to update_engine, so an adb session cannot hand it an update.
Releases built with `build-ota-trust-candidate.py --owner-ota-policy` add the
**owner OTA policy**: four rules letting the owner's paired adb shell drive the
stock update_engine (binder call/transfer and fd use, both ways), the exact
rules every VM apply used. Nothing else.

The payload is **streamed over HTTP** from the owner's build host, the standard
A/B delivery: update_engine downloads it straight into the other slot, so the
laptop needs no staging space (its /data was 93–98% full), and plain `http://`
is allowed on user builds (`libcurl_http_fetcher.cc`; update_engine is a
`net_domain`). Staging in `/data/local/tmp` was tried first and rejected at
policy compile time by AOSP's neverallow: other domains may not search that
directory or open shell files. Integrity never depends on the transport:
update_engine checks the payload's signature against the installed OpenBook
certificate (and FILE_HASH/METADATA_HASH) before the slot switch.

- `serve-payload.py`: serves exactly `payload.bin` and its properties on one
  address, with the HTTP Range requests update_engine uses, until idle
  (`serve-payload-test.py`, 7 tests over a real socket).
- `g14-ota.sh`: preflight (`check-ota-fit.py`) → read-only device checks
  (OpenBook certificate installed, a second slot) → serve → `update_engine_client
  --update --payload=http://…` → optional reboot and slot check. It refuses
  without `--approved "<release> to the G14"`; `--dry-run` stops before serving.
  Dry run on the G14 (RB-20261022-01, 2026-10-22): preflight fits, certificate
  present, one slot → refused, as expected until the fresh install.
- Still to do before the first wireless update: a VM rehearsal of the HTTP leg.
  The VNNI/GFNI-emulating QEMU build has no user-mode networking, so it needs
  rebuilding with slirp (or passt).

## Fresh installer for layout v2 (design)

Built on the Ruby stick's offline installer (`migrate.py --fresh`), which
already has the G14 DMI pin, internal-NVMe-only targets that refuse the USB, a
typed `FRESH ERASE <serial>` phrase, write-then-readback and a QEMU rehearsal
that types the prompt (`migration-qemu.py`). The AOSP engine's layout is
data-driven, but it accepts only OpenBook AOSP sticks and runs inside live
Android, which the Ruby stick does not boot. To add:
1. GPT generated from `plan-ruby-ab.py` for the real disk size (19 partitions)
   instead of copying the stick's single-slot rows.
2. A pin listing the prebuilt slot-A images (ESP files, boot chain, vbmeta,
   super) with SHA-256s.
3. Bind `androidboot.boot_part_uuid` to the new ESP at install time, keeping
   the bootsync layout and the vbmeta digest.
4. Sparse/extent writes for the 24 GiB super (content ≈ 3.6 GB).
5. Zero slot B, misc and metadata (first MiB of the rest), as the AOSP engine does.
6. A dry-run plan hash and power-cut cases, from the AOSP engine's tests.
7. A v2 `migration-qemu.py` case: the 19-partition GPT, blank slot B, userdata
   filling the disk, then boot slot A and run one OTA.
The image it writes must be a release with the owner OTA policy (candidate R),
so the first update after the reinstall can arrive wirelessly.

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
