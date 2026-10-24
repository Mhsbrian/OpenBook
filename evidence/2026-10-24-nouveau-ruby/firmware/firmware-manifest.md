# Firmware manifest: AnyBook G14 (ANAL-198)

- Source: linux-firmware `38c1a7096dfb2188f55f342b835f14c362c59409` (https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/tree/WHENCE?id=38c1a7096dfb2188f55f342b835f14c362c59409)
- Subset: `firmware-subset.tsv` (ANAL-171, 10431024 tuning added by ANAL-175), 3 files, 64.0 MB, staged as `/vendor/firmware/<linux-firmware path>`
- Every file's sha256 matches the subset list and its git blob matches linux-firmware at that commit: yes
- Used by the GA403WR: 3 files, 64.0 MB. The rest serves other Zen 4/Zen 5 laptops (Phoenix, Hawk Point, Strix Halo, Krackan; MT7921/MT7922; rtw89).

| Licence file (all redistributable per WHENCE) | Files | MB |
|---|---|---|
| `LICENCE.nvidia` | 3 | 64.0 |

## Missing

| File | Requested by | GA403WR | Note |
|---|---|---|---|

## Notes

- GA403WR speaker tuning is not missing. linux-firmware has no files named 10431024 in its git tree, which is what ANAL-171 and the ANAL-198 issue text went by, but WHENCE (lines 9731-9736 at 38c1a709) creates cirrus/cs35l56-b0-dsp1-misc-10431024-* as links to the 10431044 tuning and CS35L56_Rev3.11.16.wmfw. The laptop loads the spkid1 set (ANAL-175 root inventory). They are staged here as regular files.

## Files

| Path | Bytes | sha256 | Source | Licence | Module | GA403WR |
|---|---|---|---|---|---|---|
| `vendor/firmware/nvidia/gb205/gsp/fmc-570.144.bin` | 199820 | `cb59a35c1d4bd127…` | nvidia/gb202/gsp/fmc-570.144.bin (WHENCE link nvidia/gb205/gsp/fmc-570.144.bin) | LICENCE.nvidia | nouveau | yes |
| `vendor/firmware/nvidia/gb205/gsp/bootloader-570.144.bin` | 200812 | `d40b48e431d1707d…` | nvidia/gb202/gsp/bootloader-570.144.bin (WHENCE link nvidia/gb205/gsp/bootloader-570.144.bin) | LICENCE.nvidia | nouveau | yes |
| `vendor/firmware/nvidia/gb205/gsp/gsp-570.144.bin` | 63571696 | `a8c3ebeed280323a…` | nvidia/ga102/gsp/gsp-570.144.bin (WHENCE link nvidia/gb205/gsp/gsp-570.144.bin) | LICENCE.nvidia | nouveau | yes |
