# The G14 lab update: one Wi-Fi update for every sleep experiment over adb (ANAL-257), 2026-10-24

Owner direction 2026-10-24 (ANAL-187, ANAL-257): no USB sticks; test on the installed G14 over wireless adb. This
branch combines ANAL-238's dGPU report and hold (PR #126), ANAL-239's nouveau and its kernel (PR #131) and this
issue's diagnostics module (PR #130), and adds the root lab helper. Write-up: `docs/googlebook-s0i3.md` §4.
Nothing here ran on the laptop or wrote a device.

## Inputs built here
| Artifact | SHA-256 | From |
|---|---|---|
| bzImage `6.18.21-android17-5-g206eb00bd0c4` | `d8590aee9c0469ac…` | `kernel-g14-package.sh`, label `anybook-g14-gbos-16302624-anal257`, repo `475a3536`, in a reflink copy of the kernel lane |
| boot.img | `944da373d7c89830…` | same build |
| system_dlkm.img | `c635f0af3b4e5b15…` | same build |
| vendor_boot.img (bare metal) | `b499ebf164191767…` | same build (byte-identical to ANAL-239's) |
| vendor_dlkm.img (bare metal) | `c74c86c1299f9598…` | same build: nouveau, drm_gpuvm and openbook_sleep_diag blocklisted |
| `openbook_sleep_diag.ko` | `2d58051a9d801d9b…` | same build |
| `nouveau.ko`, `drm_gpuvm.ko`, `openbook_lid_guard.ko` | `5818ae6c…`, `38ab8f5c…`, `f62ebe3a…` | same build; byte-identical to ANAL-239's |
| vendor `/bin/openbook-pc-setup` | `5d853eb3f3496065…` | `device/anybook/common/pc/bin/openbook-pc-setup.sh` |
| vendor `/etc/init/hw/init.openbook.rc` | `13c5b12a3317b096…` | `device/anybook/common/pc/init.openbook.rc` |
| vendor `/etc/selinux/vendor_sepolicy.cil` | `95b61f5e6860804f…` | RB-20261023-03's plus 7 statements (`build-dgpu-diag-candidate.py`) |
| vendor `/etc/selinux/vendor_property_contexts` | `b4bd6a06e1e5eb80…` | RB-20261023-03's plus the lab switch |
| GSP firmware (fmc, bootloader, gsp 570.144) and `LICENCE.nvidia` | as in `handoff-ANAL-239.json` | ANAL-239, unchanged |

Full hashes: `kernel-g14/images.json`, `policy/candidate-vmcheck-result.json`.

## Files
| File | What |
|---|---|
| `kernel-g14/` | The package reports: images and hashes, module lists (0 problems; bare metal 137 loaded, 6 blocklisted), signatures, the 5 standard QEMU first-stage boots (all PASS), lists as built |
| `qemu-guest/` | `scripts/lab-guest-check.sh` on that kernel, QEMU vm and nvme runs: 45/45 each |
| `policy/policy-check.json` | `build-dgpu-diag-candidate.py --check-policy-only` on RB-20261023-03's candidate C (`71da0228…`): both policies compile with neverallows; 19 probes as designed |
| `policy/candidate-vmcheck-result.json` | The VM-check candidate `e652f813…` (not deployable): vendor, system and vendor_dlkm rebuild details |
| `tests.txt` | Every check, with its command |

## Not yet
- The Ruby VM boot of the VM-check candidate (`scripts/googlebook/dgpu-vm.sh` with `LAB_MODULE`; it adds a lab
  session to ANAL-238's report and judge): it waits for the Ruby release lock, held by RB-20261024-01.
- The deployable candidate, payload and update rehearsal: the release's steps.
- Hardware: nothing ran on the G14.
