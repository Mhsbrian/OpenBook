# RB-20261021-02: Settings search fix on the Ruby USB (ANAL-234, ANAL-252)

RB-20261021-01 with one change in `system`: the native bridge is the source-built Digitalis
`libberberis_arm64.so` instead of Houdini, which refuses AMD CPUs. Settings Services' ARM64 search
library can then load. The candidate comes from PR #124's `build-bridge-candidate.py`, applied to
RB-20261021-01's module candidate (`4b110e75…`). Everything else is unchanged: APKs, framework,
ART, compiled policy, kernel, vendor, `vendor_dlkm` with the lid guard, GPT and data format.

## Packaging

The same chain as RB-20261021-01, except stage A reviews `system` instead of `vendor_dlkm`.
`preserve-update.py` now accepts either, one at a time, and the output still needs the installer
re-pin.

```sh
Q="scripts/installer/inst-docker.sh python3 $REPO/scripts/googlebook"
$Q/preserve-update.py --snapshot "$BACKUP" --snapshot-sha256 "$BACKUP_SHA" \
  --base-manifest "$RB20261021_01/manifest.json" --candidate "$CANDIDATE" --allow-logical system --out "$W/stage-a-system"
$Q/migration-package.py pin --base "$W/stage-a-system" --out "$W/pin" --build RB-20261021-02-usb \
  --dmi-prefix "ROG Zephyrus G14 GA403WR"
$Q/laptop-update.py spec --previous-manifest "$RB20261021_01/manifest.json" --previous-build RB-20261021-01 \
  --new-manifest "$W/stage-a-system/manifest.json" --pin "$W/pin/source.json" --allow-logical system \
  --out "$W/laptop-update.json"
# input/ holds source.json and laptop-update.json
docker run --rm --network none -u "$(id -u):$(id -g)" -v "$W/input:/input:ro" -v "$W/installer:/out" \
  openbook-ruby-installer:anal229-laptop-update
$Q/migration-package.py add --snapshot "$W/stage-a-system/ruby-live.img" --snapshot-sha256 "$STAGE_A_SHA" \
  --base-manifest "$W/stage-a-system/manifest.json" --installer "$W/installer" --out "$W/stage-b-installer" \
  --replace-installer-sha256 "$OLD_INSTALLER_BUILD_JSON_SHA"
$Q/compose-usb-plan.py --backup "$BACKUP" --backup-sha256 "$BACKUP_SHA" \
  --stage "$W/stage-a-system" --stage "$W/stage-b-installer" --pin "$W/pin/source.json" --out "$W/final"
```

Stage B keeps the existing sleep-diagnostics entry. That entry boots `ruby/initrd-logs.img`, which
stage A re-pins to the new vbmeta digest, so no stage C is needed. Use the installer image tag
above; `latest` predates the laptop-update entries. Its four embedded scripts are byte-identical to
this branch.

## Results (`evidence/2026-10-22-rb-20261021-02/`)

- **Ruby VM, instrumented copy.**
  - Boot completes with `libberberis_arm64.so` selected and the lid guard present.
  - Over 20 search cycles: no Settings Services crash or ANR, no `libicing` ELF error, no `UnsatisfiedLinkError`.
  - ARM probe 17 pass / 3 fail (known: NaN rules, SIGILL metadata, CPU_ABI); x86_64 control 18/0/2.
- **Synthetic laptop**, camera25 → RB01 → RB-20261021-01 → RB-20261021-02.
  - A wrong confirmation writes nothing.
  - Update writes only EFI/super/vbmeta_a.
  - Android boots with all six verity roots and the four metadata-key files unchanged.
  - Restore returns RB-20261021-01 byte for byte, and it boots.
  - The VM-only SwiftShader `execmem` system-server crash appears 3 times after the update and once after restore; no Digitalis frame is involved.
- **Provisional real-stick plan**, against the last written image `f1e7410b`: final `df030698…`. The physical writer's validator accepts it: 3 writes, 8,805,941,248 protected bytes. The plan to write is rebuilt against a fresh backup.

## Owner steps

1. Put the SanDisk ending 2034 in the host. The coordinator takes a fresh backup by two direct
   reads, recomposes the plan against it, runs the read-only preflight, and names the final
   checksum for the write confirmation.
2. After the verified write, optionally boot the stick's **live** entry on the G14. Search can then
   be checked over adb on the full new system before the laptop's NVMe is touched.
3. Run **Update the laptop's Googlebook system - keep data**. If anything misbehaves, run
   **Restore previous laptop system**.
