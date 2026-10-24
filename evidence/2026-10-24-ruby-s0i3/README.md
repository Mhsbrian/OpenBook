# Deep sleep on the G14 under Ruby: desk work and diagnostics (ANAL-257), 2026-10-24

The write-up is `docs/googlebook-s0i3.md`. Nothing here ran on the laptop: these are desk reads of existing logs,
tables and source, and checks of the new tools on the build host and in QEMU. Private inputs (the owner's Linux
inventory, the kernel lane, the stick copies) stay on the build host.

| File | What |
|---|---|
| `desk/linux72-dgpu-timeline.txt` | The 2026-10-16 Linux 7.2.8 run: supergfx Integrated, NVIDIA unloaded at 216 s, pciehp re-enumerating the dGPU after every resume, no "didn't reach deepest state" and no "PTM enabled" line |
| `desk/osc-platform.md` | Platform `_OSC`: the two kernels' masks (`0x00267cee` vs `0x006e7eff`) and what the G14 firmware reads |
| `desk/kernel-config-diff.txt` | PM-relevant configuration: GKI vmlinux vs Linux 7.2.8 |
| `desk/source-review.md` | PTM, thunderbolt, PCI core and amd_pmc: GKI 6.18.21 vs v7.2/v7.3 |
| `desk/dmesg-comparison.md` | The same laptop's kernel logs under both kernels |
| `module/build.json` | `openbook_sleep_diag.ko` `7362ffcb…`: build, vermagic, KMI and CRC checks against the G14 kernel |
| `module/undefined-symbols.txt`, `module/modversions.txt` | The 32 symbols it imports and their 33 CRCs |
| `module/vm-result.json`, `module/vm-serial-excerpt.txt` | QEMU on the G14 bzImage: 17/17 |
| `module/ptm_plan_test.txt` | The PTM clear/restore order against a mock config space: 10/10 |
| `tests.txt` | Every check of this issue, with commands |

No handoff yet. The first one (module plus two USB boot entries) was withdrawn on 2026-10-24 when the owner
dropped USB sticks: the module ships in one combined vendor update with the root lab helper, ANAL-238's report and
ANAL-239's nouveau, rebuilt for ANAL-239's kernel, and its `anybook-handoff/1` file comes with that update.
