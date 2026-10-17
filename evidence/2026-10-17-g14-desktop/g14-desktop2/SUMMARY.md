# G14 boots of `openbook-live-20261017-desktop2` (ANAL-176, 2026-10-17)

The owner wrote the image at 01:05 UTC (`write-stick.sh`, read back and verified against sha256 `1e6c7315…`) and booted the GA403WR. Only "save logs" showed the desktop; the default and safe-graphics entries stayed black. The stick was read back read-only (`read-stick-logs.sh`); the files here are redacted (`live-report.py --redact`). Analysis: `docs/g14-desktop.md` §9.

| Time (UTC) | Boot | What the stick shows |
|---|---|---|
| 01:11 | default entry (enforcing), the stick's first boot | `live-init-001.json`: userdata grown to 56.2 GiB. No logs (that entry saves none). Got as far as formatting `/data` and decompressing the APEXes (the next boot had nothing left to decompress), never reached `boot_completed` (bootstat) |
| 01:11–01:17 | probably "safe graphics" (also enforcing) | nothing recorded |
| 01:17:34 | "save logs" (permissive): `live-001` | `boot_completed` at 28.1 s; the owner opened Settings → Network; final capture at 73 s, then the scheduled power-off |
| 01:19:22 | "save logs": `live-002` | SurfaceFlinger aborted once at start ("couldn't find an OpenGL ES implementation", `ro.hardware.egl` not set yet), restarted; `boot_completed` at 28.1 s; Settings, Search, Gallery, wallpaper chooser; final capture at 73 s, power-off at 77 s. `screen-final.png` is the device's own screenshot of the desktop |

**Why the enforcing boots stayed black.** `live-NNN/dmesg.txt.gz`: `avc: denied { firmware_load } for comm="modprobe" path="/vendor/firmware/amdgpu/psp_14_0_0_toc.bin" … scontext=u:r:kernel:s0 tcontext=u:object_r:openbook_vendor_fw_file:s0 tclass=system permissive=1`, and the same for `mediatek/mt7925/WIFI_RAM_CODE_MT7925_1_1.bin`. With SELinux enforcing, amdgpu gets no firmware and never initialises: no display at all.

**Denials** (`live-NNN/avc.md`, `avc-summary.py` with kernel-side denials no longer counted as the helper's): 29 and 22 lines in the kernel log (66 in the first G14 boot), the only kernel-side one being `firmware_load`.

| File | |
|---|---|
| `live-NNN/report.md`, `report.json` | `live-report.py --expect g14` verdicts |
| `live-NNN/summary.json` | the helper's timings and properties |
| `live-NNN/dmesg.txt.gz`, `logcat-final.txt.gz`, `collect-final.txt.gz` | redacted logs |
| `live-NNN/screen-final.png` | the desktop on the G14's panel, 2880×1800, from `screencap` |
| `live-NNN/avc.md`, `avc.json` | denial summaries |
| `live-init-001.json` | the first boot's userdata growth |
