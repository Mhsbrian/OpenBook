# `openbook-live-20261017-anal178c`: one G14 stick from `main` at `ea3c25e` (ANAL-178, 2026-10-17)

The owner asked for one stick with everything merged so far. When this was built, no PR was open; #41–#49 were merged. It replaces `combined`.

## Build

- **Product:** the `combined` snapshot (`<data dir>/installer/inputs/openbook-live-20261017-combined`, `anybook_g14_x86_64-cp2a-userdebug`, built from `01750c5`), reused with `--inputs`. Nothing under `device/`, `aosp/` or the kernel changed between `01750c5` and `ea3c25e`, so the product is the same. Reusing it also left the AOSP lane alone: ANAL-191 holds it.
- **Image:** `scripts/installer-image.sh --inputs … --label openbook-live-20261017-anal178c --menu-timeout 10 --no-xz` at `ea3c25e`, clean tree. Its live-init is `main`'s, with ANAL-177's add-on hook.
- **Add-ons on the ESP**, both added with their owners' appliers (`--image`):
  - `openbook-powercheck-anal178-c`: rebuilt from `main`. The probe is byte-identical to `-a`, the add-on on `combined` and `anal178b`. Only `hwcheck.img` differs, by a few bytes, because its test modules are not byte-reproducible (`powercheck-addon-a-vs-c.txt`).
  - `openbook-gfxcheck-20261017`: ANAL-177's add-on, unchanged.
- **sha256:** `972ad8bd…` with the add-ons; `44bb7955…` before them (`.build.json`, `.sha256`). The ESP keeps 65.3 MB free.

## Tests (QEMU/KVM, q35 + OVMF, the image as a USB stick)

| Test | Result | Evidence |
|---|---|---|
| Live image matrix, final image (both add-ons on it) | **39/39** | `live-matrix-SUMMARY.md`, `live-matrix-results.json` |
| Its "save logs" case, `live-report.py --expect g14` | boot_completed 17.7 s; lid → sleep, short power press = 6 (lock or sleep); all five `bridge_*` verdicts true. Wi-Fi, audio, touchpad and LEDs: NO, because the VM has none | `logs-case-report.md`, `logs-case-report.json` |
| Power check, the stick's own entry | **10/10** steps, report saved, powered off | `powercheck-real-result.json` |
| Power check, VM entry (LPS0 fixture, s2idle) | **14/14**: the snapshot module logs at each S0i3 attempt, `openbook_pci_pm` puts its device in D3hot | `powercheck-vm-result.json`, `powercheck-vm-excerpt.txt` |
| Graphics check, quick lists (`scripts/graphics/gfx-qemu.sh`) | **6/6** steps in 194 s; `vk`, `gles-angle`, `egl`, `angle` ran; `vk14` and `gles-mesa` skipped (no AMD GPU); 0.9 MB of results. Same as ANAL-177's run on `combined` | `gfx-qemu.sh` output in `gfx-qemu-quick.txt` |

The add-on tests ran on the image before the add-ons went on, because each test applies its own add-on to a copy, as the owner's applier does. The live matrix ran on the final image.

**ESP room:** 65.3 MB free after both add-ons. On the G14, "save logs" boots have written 6–12 MB to the ESP (`g14/stick-*`, without the reports the host adds). The hardware-check reports so far were under 0.3 MB; the power check's kernel log is capped at 8 MB (`log_buf_len=8M`). With full lists, the graphics check's results come to about 2–5 MB (ANAL-177's 610M pre-check), and live-init caps them at the free room minus 24 MiB. Booting the graphics check last therefore keeps the other boots' logs whole.

**Not tested here:** anything on the G14 itself. The owner's run of this stick is the hardware test.
