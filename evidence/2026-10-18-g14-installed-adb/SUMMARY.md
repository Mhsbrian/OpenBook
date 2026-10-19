# The installed G14 over the network: adb from the build host (ANAL-222, 2026-10-18)

The owner installed OpenBook on the G14's NVMe disk (whole disk, `ro.boot.openbook.installed=whole`, build `CP2A.260605.016 eng.builde` userdebug, enforcing), set a PIN, and joined the home Wi-Fi as `192.168.50.11`. The build host (`192.168.50.217`, same LAN) reached it over adb with `scripts/g14-adb.sh` and no stick. The how-to is `docs/adb-debug.md`.

The owner was working in Developer options at the same time. They toggled USB and Wireless debugging, opened pairing, turned persistent logging off, and rebooted at 16:02:09Z. Those events are in the files below.

| | Result |
|---|---|
| Reach | The G14 advertises `_adb._tcp` on 5555 and `_adb-tls-connect._tcp` on a random port as "OpenBook on ROG Zephyrus G14 (GA403WR)". `adb connect 192.168.50.11:5555` worked at once |
| Authorization | **None.** adbd logs `authentication not required`, there are 0 keys in `adb_keys`, and `adb root` works over the network: userdebug, `ro.adb.secure` unset, `orange`. This applies on any network the laptop joins (`docs/adb-debug.md` §5) |
| USB | No device-mode controller (`/sys/class/udc` empty); xHCI hosts only. A USB cable cannot carry adb (`adb-facts.txt`) |
| Across a reboot | Kernel 16:02:09.9Z: init second stage 0.7 s, zygote 4.5 s, screen 6.7 s, **desktop 7.7 s**, Wi-Fi 11.0 s (before unlock), **adb answering by about 12 s**, with nothing done on the laptop (`boot-timeline.txt`) |
| Switches | Every USB or Wireless debugging toggle and every `adb root` restarted adbd and left the host "offline" until it reconnected. USB debugging off with Wireless debugging on still served 5555 without authorization (`adb-toggles-previous-boot.txt`) |
| Persistent logs | The product's `logcatd` (16 files) was turned off from Developer options at 15:56:51Z, which **cleared `/data/misc/logd`**, so the first boot's logs are gone. Back on since 16:04Z (`g14-adb.sh persist-logs on`): `logcatd` running, files accumulating |
| Capture | `g14-adb.sh capture` took **34 s** and saved the "save logs" set (12 files, 8.1 MiB). `live-report.py --expect g14`: **21 yes, 0 NO, 3 unknown** (no sleep, lid or touchpad use yet). Among them: amdgpu HAL, eDP 2880×1800 at 120 Hz, Wi-Fi, touchpad, keyboard, dGPU in D3cold, backlight, battery (health HAL 87.8 %), amd-pstate-epp, key layouts, lid/power config (`capture/report.md`) |
| Crashes | 0 tombstones, 0 ANRs; dropbox 142 entries since install (`capture/prior-boots.txt`) |
| Denials | 12 kernel-log lines, 9 kinds (`capture/avc.md`). Known: keystore → Gatekeeper, SystemUI's Bluetooth LE audio property, `system_server` → `wifi_hal_prop`. **Not seen before:** `system_app` binder calls to the audio, AuthSecret and Bluetooth HALs, and lookups of `system_suspend_control*` and `tracingproxy`, all at 16:03:13Z from the Settings process (pid 1475, started at boot as FallbackHome). The cause is not found yet |

Files:
- `adb-facts.txt`: adbd properties and listeners, USB controllers, USB network modules, logpersist, kernel log, pstore, Wi-Fi power save, boot reasons. Read as root at 16:08Z.
- `boot-timeline.txt`: the 16:02Z boot.
- `adb-toggles-previous-boot.txt`: the first boot's adbd and logpersist events, transcribed from a live read. That boot's logs were not persisted.
- `capture/`: the masked report, AVC summary, `summary.json` and `prior-boots.txt` from `g14-adb.sh capture --redact`.

The full logcat, collect file, kernel log and screen capture stay on the host (`<data dir>/installer/g14/adb-first/`). The installed system's Wi-Fi logs name about 40 neighbouring networks from scans, which would locate the owner. The masked copy now hides them, along with the owner's own network and the Wireless debugging pairing code (`live-report.py` redaction, extended in this PR), but full logs are still not committed.

Reproduce:
```bash
scripts/g14-adb.sh find && scripts/g14-adb.sh connect
scripts/g14-adb.sh persist-logs on
scripts/g14-adb.sh capture --redact ~/anybook/installer/g14/adb-first-redacted ~/anybook/installer/g14/adb-first
```
