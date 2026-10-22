# Layout v2: ready for small and large OTAs (ANAL-229, 2026-10-22)

The fresh installer fixes partition sizes for good, so v2 sizes them for the largest update the
laptop should take. Both a small and a large OpenBook OTA were then run end to end on a v2 disk in
QEMU (TCG; Ruby needs AVX-VNNI, which the Zen 4 build host lacks).

- `google-ruby-gpt.json`: Google's own two-slot Ruby partition set (names and sizes only), read
  from the GPT of Google's recovery image. The reference for v2.
- `layout-1tb.json`: v2 on the G14's 1 TB SSD (`plan-ruby-ab.py`): every A/B partition of
  Google's layout at ≥ Google's size (adds `pvmfw`, `recovery`, `ota_recovery`; vbmeta 4 MiB),
  ≥ 2× headroom where OpenBook content lives (`boot` 128 MiB, `init_boot` 16 MiB), a 24 GiB super
  (2 × Google's 12.88 GB group cap, so any update's snapshot fits in super and never needs /data),
  a 1 GiB ESP. userdata ≈ 905.7 GiB.
- `fit-small-1tb.json`, `fit-large-1tb.json`: `check-ota-fit.py` preflight of both payloads on
  the 1 TB layout: both fit; the large one needs 7.17 GiB of snapshot of 20.65 GiB free in super.
- `payload-small.json`: incremental, 10 partitions, 2.69 MB, signed with the OpenBook key.
- `large-release-fixture.json` + `payload-large.json`: the large release grows `system` by 2 GiB
  of incompressible data (5.65 GB of dynamic partitions, vs 3.6 GB today) and ships as a **full**
  payload: 5.04 GB, zstd replace operations, lz4 snapshot compression, signed with the OpenBook
  key. A full payload is what a new Google base needs: it has no dependency on what is installed.
- `small-*.json`, `large-*.json`: `ab-ota-suite.sh` results. Both suites pass every phase:
  - apply (11/11): stock update_engine; libsnapshot `Unverified`; setActiveBootSlot → bootsync
    activate b; slot-B static partitions equal the release; orderly reboot. Large: 710 s; small:
    780 s (both mostly Android boot under emulation).
  - boot (7/7): slot B boots, is marked good, all six snapshots merge, state back to None.
  - verify (10/10): merged slot B is byte-identical to its release, including the grown system.
  - fallback (7/7): vbmeta_b corrupted after the apply; three slot-B boots fail, slot A starts by
    itself, the update is rolled back. For the large update that means a 5.65 GB snapshot discarded
    and slot A intact.
- Harness finding: NVMe instance numbers follow probe completion, not PCI slot order (seen both
  ways), so the disposable apply driver tries both nvme0n1 and nvme1n1; only the bare-ext4 payload
  drive mounts. The first small run lost that race (payload not mounted, nothing written) and was
  re-run after the fix. The large run used the earlier harness build and won the race; the fix
  changes only that test-only mount, not the OTA.
