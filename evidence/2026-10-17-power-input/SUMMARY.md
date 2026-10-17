# Evidence: power and input (ANAL-178), 2026-10-17

Everything here ran on the build host (Ryzen 9 7950X): QEMU/KVM, AOSP host tools, and analysis of the G14 data already in the repo. **Nothing in this folder ran on the G14.** The owner steps that do are in `docs/power-input.md` §1.5.

## s0i3-analysis/
| File | What it shows |
|---|---|
| `linux72-suspend-cycles.txt` | The laptop's own Linux 7.2.8 (owner's root inventory boot): 4 s2idle cycles, 0 "didn't reach deepest state" lines. Indirect evidence that Linux reaches S0i3 on this BIOS (C, indirect) |
| `parser-check-runs-5-7.txt` | `scripts/power/linux-s2idle.py`'s parsers on runs 5–7 (our kernel): SMU "Unknown/Fail", idle mask `0xffef9afd`, run 5–6's unmet `GPP0.SWUS`, wakes on IRQ 9 and 38, 18.6 s of frozen timekeeping (all CPUs in cpuidle's s2idle path). USB4_0's "not met" time is 78 416 µs in all three runs |
| `s0i3-report-runs-3-7.{md,json}` | `scripts/power/s0i3-report.py` on runs 3–7: no cycle reached S0i3; idle masks from the saved kernel logs |
| `amd_pmc-s2idle-6.18-vs-7.2.8.diff.gz` | `drivers/platform/x86/amd/pmc/` and `drivers/acpi/x86/s2idle.c`, our 6.18 tree vs v7.2.8: a refactor for this CPU (same SMU registers, OS hint, IP table), Lenovo-only suspend delay |

ACPI facts in `docs/power-input.md` §1.2 come from the owner's decoded tables, which stay on the build host (`~/anybook/hw/ga403wr-20261016-135706/`, not committed, as for ANAL-175).

## qemu/ (copy of `openbook-live-20261017-desktop2.img` + add-on `openbook-powercheck-anal178-a`)
| Run | Result |
|---|---|
| `vm-*` | VM entry with the LPS0 fixture SSDT and `mem_sleep_default=s2idle`, woken by the ACPI power button: **14/14 steps**, 73 s. The snapshot module logged at every "S0i3 attempt" (`s0i3-entry:`) and exit; step `pm:1af4:1044` moved the virtio-rng from `virtio-pci` to `openbook_pci_pm`, which put it into D3hot at suspend and back to D0; step `asus` loaded asus-wmi and hid-asus (asus-nb-wmi: -ENODEV, no ASUS WMI). `vm-hwcheck-001.json` has the three cycles (`"s0i3": null`: a VM has no AMD PMC) |
| `real-*` | The add-on's "OpenBook power check: S0i3" entry, unchanged: **10/10 steps**, 114 s, four cycles (S3 in QEMU), report written, powered off. The snapshot reports "no LPS0 device" there, as designed |
| `collect-*` | The live stick's save-logs COLLECT script from this checkout, run in Android 17 (same image, serial console): COLLECTRC 0, every new section filled on the image's own mksh/toybox (`collect-sections.json`; errors are the VM's missing cpufreq, thermal and backlight). The VM suspended itself after its screen timeout (`success=1 fail=1`, errno -16) |

Applier checks (not files): `add-to-live-stick.sh` refused a hardware-check image ("openbook-live.conf missing"), a bundle writing `loader/loader.conf`, and `/dev/sda`.

## addon/
The add-on as built (`openbook-powercheck-anal178-a`, 75 MiB): its JSON (kernel `6d964789…`, probe and test-module hashes, 265 modules, 152 firmware files), `MANIFEST.sha256`, `EXPECT`, the three menu entries, the README that goes on the stick, and the build log's vermagic lines (all three modules `6.18.21-android17-5-g44a90255c95f`).

## android/
| File | What it shows |
|---|---|
| `overlay-check.txt` | `OpenBookPcFrameworkOverlay`: `aapt2` compiles and links it against the G14 product's `framework-res.apk`; `idmap2` maps all 14 values under the vendor policy with overlayable checks on |
| `validatekeymaps.txt` | AOSP's `validatekeymaps`: all G14 `.kl`/`.idc` files, including the new `Asus_WMI_hotkeys.kl`, pass |
| `googlebook-ruby-laptop-config.txt` | The lid, power-button, dream and battery-saver values in Googlebook's own laptop overlay (ruby `FrameworkDesktopOverlay.apk`, read with `aapt2`; the image is never committed) |

Not built or booted: the overlay and layout need the AOSP lane (after ANAL-179).

## anal178b/ (AOSP lane, 2026-10-17 04:20–05:00 UTC, after ANAL-179 reached review)
The G14 product built from `anal-178/stick-integration` (ANAL-179's `stick-integration`, which carries ANAL-176's desktop4 fixes and `main`, merged with this branch, plus the health HAL), and the live image `openbook-live-20261017-anal178b` with the power check add-on on its ESP. Still **QEMU only**.

| File | What it shows |
|---|---|
| `product-check.txt` | Build `ea04243`: exit 0, 2:10 incremental, 45.7 GB peak RSS. In `PRODUCT_OUT`: `android.hardware.health-service.openbook` (no example health HAL), its VINTF fragment, both key layouts, and the PC overlay with 15 values (this issue's 14 and ANAL-179's jack setting) |
| `hals-test.txt` | `openbook_hals_test`: 18/18, including the three battery fixtures |
| `live-matrix-SUMMARY.md`, `live-matrix-results.json` | ANAL-190's live image matrix on the image as offered (with the add-on): **39/39** |
| `live-matrix-logs-case-report.md` | `live-report.py --expect vm` on the matrix's save-logs folder |
| `collect-*`, `lid-power-health.txt` | COLLECT inside Android on the same image: completes (`COLLECTRC=0`, AVC and END present after bounding `service list`); `getLidBehavior=LID_BEHAVIOR_SLEEP`, `mShortPressOnPowerBehavior=6`, `LONG_PRESS_POWER_GLOBAL_ACTIONS`, lid keyboard/navigation 1; `vendor.health-openbook` running |
| `powercheck-real-*` | The add-on's S0i3 entry, unchanged, on this image: 10/10 steps |
| `openbook-live-20261017-anal178b.{build.json,sha256}` | The image as offered: sha256 `be09ebb7…` (xz `96600a6e…`), the add-on recorded in the build record |

Found on the way: `service list` blocks in QEMU at the service after `IAuthSecret` on images with ANAL-179's Wi-Fi/Bluetooth/audio (also in `audionet3`'s own matrix), which cut the save-logs capture short before AVC and END; it is now bounded to 30 s.
