## AnyBook kernel + our AOSP 17 userspace in Cuttlefish (ANAL-172, 2026-10-16)

**Kernel:** the ANAL-171 dist `anybook-amd-gbos-16302624`: `bzImage` sha256 `6d964789…`, release `6.18.21-android17-5-g44a90255c95f`, with its own signed GKI modules.
**Userspace:** ANAL-168's `aosp_cf_x86_64_pc-cp2a-userdebug` (`CP2A.260605.016`), as reflink copies of its images taken at 15:27:19 UTC (`*/snapshot-provenance.txt`).
- Every partition on the device reports fingerprint `generic/aosp_cf_x86_64_pc/…` and `ro.*.build.date.utc=1792156850` (13:20:50 UTC, ANAL-168's `m dist` rebuild) in `anybook/getprop.txt`.
- The second fingerprint file in the provenance, `anybook_cf_x86_64_pc`, belongs to ANAL-169, which builds a new product into the same `PRODUCT_OUT`. Its images were written at 15:38 UTC, after the snapshot.
**Swap mechanism:** `cvd create --kernel_path=<bzImage> --initramfs_path=<module tree>`. `assemble_cvd` rebuilds `vendor_boot`, `vendor_dlkm`, `system_dlkm`, `super` and the vbmeta images from that tree. Android is not rebuilt.

### Runs

| dir | module set | `cvd create` | `sys.boot_completed` | kernel start → `boot_progress_start` / `enable_screen` / boot animation done | expected modules live | live total |
|---|---|---|---|---|---|---|
| `anybook/` | GKI + AnyBook 138 + compatible board modules, `asus-nb-wmi` VM-blocklisted | 30 s | `1` at +33 s | 3.2 / 7.8 / 8.2 s | **169 / 169** | 176 |
| `anybook-repeat/` | same, same initramfs sha256 `77a0c460…` | 27 s | `1` at +30 s | 3.5 / 8.1 / 8.5 s | 169 / 169 | 176 |
| `board/` (control) | GKI + Cuttlefish board modules only | 24 s | `1` at +27 s | 3.4 / 8.1 / 8.6 s | 50 / 50 | 57 |
| `anybook-no-vm-blocklist/` (first attempt) | AnyBook set without the VM blocklist | 412 s ¹ | `1` at +415 s ¹ | 15.6 / 41.9 / 44.7 s ¹ | 169 / 170 | 176 |

¹ The host's load average was about 226 during this run (an AOSP build, a QEMU guest and several JVMs). `assemble_cvd` finished at 15:31:08 and the VM started at 15:37:01 (`launcher.log.gz`). The other three runs ran back to back at load 4–50.

All four boots report `uname -r` = `6.18.21-android17-5-g44a90255c95f`, `ro.kernel.version=6.18`, Android 17 / SDK 37 and a 1920×1080 display (`anybook/screen.png`, the lock screen).

### What loaded

- **First-stage init** (vendor ramdisk), `init: Loaded 18 kernel modules took 267 ms`: 8 GKI virtio/vsock/rfkill/libarc4 modules, 5 board modules (failover, net_failover, nd_virtio, virtio_net, virtio-rng) and **5 AnyBook modules**: cfg80211, mac80211, virtio_dma_buf, virtio-gpu, virtio_input. A failure at this stage is fatal, and none occurred.
- **`dlkm_loader`** (vendor_dlkm), `module load count is 154`: **132 AnyBook modules**, 19 board modules, and 3 GKI modules from `system_dlkm` pulled in as dependencies (bluetooth, btbcm, can-dev). `vendor.dlkm.modules.ready=true`.
- **GKI modules:** all 100 are signed by the ANAL-171 build and sit in `system_dlkm`; 14 are live. **0 signature rejections.** Unsigned AnyBook modules load under `MODULE_SIG_PROTECT` using KMI symbols only.
- **Log scan** (`log-scan.txt`, full guest console): 0 `Unknown symbol`, 0 `disagrees about version`, 0 `module verification failed`, 0 Oops/BUG/WARNING/Call Trace in all four runs.
- **Taint** is `6144` = `I` (`[Firmware Bug]: TSC doesn't count with P0 frequency!`, from crosvm's CPU model) + `O` (the out-of-tree board modules goldfish_*, v4l2loopback and virtio_media). **No AnyBook module sets a taint flag** (`drivers.txt`), which confirms ANAL-171's observation inside Android.

### Display path: virtio-gpu

AnyBook's `virtio-gpu.ko` loads in first stage: `[drm] Initialized virtio_gpu 0.1.0 for 0000:00:02.0 on minor 0`. It creates `card0` and `renderD128`. vkms is `card1` (`create_default_dev=0`). The display is 1920×1080 at 160 dpi, rendered by SwiftShader (`--gpu_mode=guest_swiftshader`, as in ANAL-168).

### amd-pstate

It is built in, not a module. In this VM it does not register:

```
amd_pstate: The CPPC feature is supported but currently disabled by the BIOS.
amd_pstate: the _CPC object is not present in SBIOS or ACPI disabled
```

The guest CPU advertises CPPC, but crosvm's ACPI tables have no `_CPC`. cpufreq runs on Cuttlefish's `dummy-cpufreq`. Testing amd-pstate needs bare metal.

### amdgpu (symbol resolution only)

`dlkm_loader: Loaded kernel module /vendor/lib/modules/extra/anybook/amdgpu.ko` at 1.43 s. `/sys/module/amdgpu/initstate` is `live`, and `/sys/bus/pci/drivers/amdgpu/` exists with no device bound: the VM has no AMD GPU (`drivers.txt`, PCI list). amdxdna, amd_pmc, amd_sfh, k10temp, mt7925e, mt7921e, rtw89, snd_pci_ps, snd_sof_amd_acp70 and hid_asus are also live, each with no hardware to probe. None of these drivers' probe paths are tested here.

### Every module that did not load, and why

| module | source | result | why |
|---|---|---|---|
| `asus-nb-wmi.ko` | AnyBook | **-ENODEV** (`No such device`) | The VM's ACPI has no ASUS WMI GUID. Same result as ANAL-171's QEMU test. In `anybook-no-vm-blocklist/`, `dlkm_loader` hit it, then failed its final `CHECK`, so it never set `vendor.dlkm.modules.ready`. Cuttlefish's `bt_vhci_forwarder` waits for that property, so virtual Bluetooth would not start. The VM image therefore blocklists the module, and `kernel-cf-boot.sh` loads it by hand after boot (`anybook/probe-blocklisted.txt`: `Failed to insmod … No such device`, exit 1). Its dependency asus-wmi loads. |
| `mac80211_hwsim.ko` | board | left out of the image | 1 CRC mismatch: `ieee80211_alloc_hw_nm` against AnyBook's mac80211 |
| `virt_wifi.ko` | board | left out of the image | 1 CRC mismatch: `wiphy_new_nm` against AnyBook's cfg80211 |
| `mt76-usb`, `mt76x0-common`, `mt76x0u`, `mt76x02-lib`, `mt76x02-usb`, `mt76x2-common`, `mt76x2u` | board | left out of the image | 4–33 CRC mismatches each against AnyBook's mt76 |
| `vivid.ko`, `snd-aloop.ko` | board | not loaded, by design | Cuttlefish's own `modules.blocklist` (snd-aloop would take ALSA card 0 from virtio-snd) |

The CRC mismatches have one cause (`board-build.txt`): Cuttlefish's `virtual_device.fragment` sets `CONFIG_NL80211_TESTMODE=y`, and the AnyBook device build does not. That option adds `testmode_*` members to `struct cfg80211_ops`, `struct ieee80211_ops` and the mt76 structs. One cfg80211/mac80211/mt76 can therefore serve either the AnyBook Wi-Fi drivers or Cuttlefish's virtual Wi-Fi, not both. The AnyBook copies win, because they are the product. **Effect: the AnyBook VM image has no virtual Wi-Fi.** Boot does not need it, and the `board/` control run keeps it.

Nine other board modules share a name with an AnyBook module (cfg80211, mac80211, mt76, btusb, btintel, btrtl, virtio-gpu, virtio_input, virtio_dma_buf). The AnyBook copy is used; `anybook/modset.md` compares their exported CRCs.

### Notes

- `adb shell dmesg` (`dmesg.txt.gz`) starts about 3 s into boot, because audit messages wrap the ring buffer. `kernel.log.gz` is the full guest console captured by the host, and the counts above use it.
- The board modules come from `//common-modules/virtual-device:virtual_device_x86_64_dist`, built on the same patched tree. That build recompiled the GKI with a new random module-signing key. `vmlinux.symvers`, `Module.symvers` and `System.map` are byte-identical to the ANAL-171 dist, so only its unsigned modules are used (`board-build.txt`).
