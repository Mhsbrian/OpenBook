# RB-20261021-02 physical write (ANAL-252), 2026-10-22

`physical-write.json` records the identified write of RB-20261021-02, the Settings search fix,
to the SanDisk Ultra ending 2034. B Honey approved it on ANAL-252 and ANAL-229. It was run from
the ANAL-229 session with the frozen plan v1 tools (`b75b573`).

- **Backup:** two direct reads of the 12,766,412,800-byte used extent match (`916108d0…`).
  Since the last write (`f1e7410b…`), only `EFI` and `metadata` differ. The desktop had
  auto-mounted `metadata` read-write; it was unmounted before the backup. `super`, `vbmeta_a`,
  the boot partitions and `userdata` are identical.
- **Recomposition:** the installer pin (`16d5d5ed…`) and laptop record (`3de437ad…`) are
  byte-identical to the frozen provisional artifacts. The installer initrd's 934 files are
  identical; only archive timestamps differ.
- **Write:** after a read-only preflight, `super`, `vbmeta_a` and `EFI` were written, 11:52–11:59
  UTC. The full readback matches the final image `233eed28…`. All 8,805,941,248 protected bytes
  are unchanged, and the stick was powered off.
