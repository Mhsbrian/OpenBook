# Firmware manifest: AnyBook G14 (ANAL-198)

- Source: linux-firmware `38c1a7096dfb2188f55f342b835f14c362c59409` (https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/tree/WHENCE?id=38c1a7096dfb2188f55f342b835f14c362c59409)
- Subset: `firmware-subset.tsv` (ANAL-171, 10431024 tuning added by ANAL-175), 137 files, 52.6 MB, staged as `/vendor/firmware/<linux-firmware path>`
- Every file's sha256 matches the subset list and its git blob matches linux-firmware at that commit: yes
- Used by the GA403WR: 24 files, 6.9 MB. The rest serves other Zen 4/Zen 5 laptops (Phoenix, Hawk Point, Strix Halo, Krackan; MT7921/MT7922; rtw89).

| Licence file (all redistributable per WHENCE) | Files | MB |
|---|---|---|
| `LICENCE.mediatek` | 11 | 6.2 |
| `LICENCE.rtlwifi_firmware.txt` | 30 | 26.7 |
| `LICENSE.amdgpu` | 72 | 15.3 |
| `LICENSE.amdnpu` | 12 | 4.2 |
| `LICENSE.cirrus` | 12 | 0.2 |

## Missing

| File | Requested by | GA403WR | Note |
|---|---|---|---|
| `amdnpu/17f0_20/npu.sbin` | amdxdna | no | declared by the driver, absent from linux-firmware; the GA403WR's NPU is rev 10 (17f0_10) |

## Notes

- GA403WR speaker tuning is not missing. linux-firmware has no files named 10431024 in its git tree, which is what ANAL-171 and the ANAL-198 issue text went by, but WHENCE (lines 9731-9736 at 38c1a709) creates cirrus/cs35l56-b0-dsp1-misc-10431024-* as links to the 10431044 tuning and CS35L56_Rev3.11.16.wmfw. The laptop loads the spkid1 set (ANAL-175 root inventory). They are staged here as regular files.

## Files

| Path | Bytes | sha256 | Source | Licence | Module | GA403WR |
|---|---|---|---|---|---|---|
| `vendor/firmware/amdgpu/psp_13_0_11_toc.bin` | 2560 | `11e3529d748e2b6b…` | amdgpu/psp_13_0_11_toc.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/psp_13_0_11_ta.bin` | 254976 | `d54846f099aaa5f4…` | amdgpu/psp_13_0_11_ta.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/psp_14_0_0_toc.bin` | 2560 | `da82e510ba90b393…` | amdgpu/psp_14_0_0_toc.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/psp_14_0_0_ta.bin` | 254976 | `d54846f099aaa5f4…` | amdgpu/psp_14_0_0_ta.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/psp_14_0_1_toc.bin` | 2560 | `c629a9996fbdd487…` | amdgpu/psp_14_0_1_toc.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/psp_14_0_1_ta.bin` | 254976 | `d54846f099aaa5f4…` | amdgpu/psp_14_0_1_ta.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/psp_14_0_4_toc.bin` | 2560 | `bbb69c7d83f4400a…` | amdgpu/psp_14_0_4_toc.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/psp_14_0_4_ta.bin` | 254976 | `d54846f099aaa5f4…` | amdgpu/psp_14_0_4_ta.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/psp_13_0_4_toc.bin` | 2560 | `11e3529d748e2b6b…` | amdgpu/psp_13_0_4_toc.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/psp_13_0_4_ta.bin` | 254976 | `d54846f099aaa5f4…` | amdgpu/psp_13_0_4_ta.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/psp_14_0_5_toc.bin` | 2560 | `3f9c34ea742e3f7b…` | amdgpu/psp_14_0_5_toc.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/psp_14_0_5_ta.bin` | 254976 | `d54846f099aaa5f4…` | amdgpu/psp_14_0_5_ta.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_1_imu.bin` | 132352 | `ac71f4eec713fc35…` | amdgpu/gc_11_0_1_imu.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_4_imu.bin` | 132352 | `ac71f4eec713fc35…` | amdgpu/gc_11_0_4_imu.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_0_imu.bin` | 132352 | `469add57cafead90…` | amdgpu/gc_11_5_0_imu.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/gc_11_5_1_imu.bin` | 132352 | `0aaca8a01b2237fc…` | amdgpu/gc_11_5_1_imu.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_2_imu.bin` | 132352 | `fb684842839c61a0…` | amdgpu/gc_11_5_2_imu.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_3_imu.bin` | 132352 | `fb684842839c61a0…` | amdgpu/gc_11_5_3_imu.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_1_pfp.bin` | 263424 | `449c72cae1c57838…` | amdgpu/gc_11_0_1_pfp.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_1_me.bin` | 263424 | `62c5e749ad848941…` | amdgpu/gc_11_0_1_me.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_1_mec.bin` | 268160 | `b0a4006b3934adc1…` | amdgpu/gc_11_0_1_mec.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_1_rlc.bin` | 157040 | `5f07dc1f0a75ecd9…` | amdgpu/gc_11_0_1_rlc.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_4_pfp.bin` | 263424 | `e475f7e1afd6d475…` | amdgpu/gc_11_0_4_pfp.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_4_me.bin` | 263424 | `e310c7293da21f80…` | amdgpu/gc_11_0_4_me.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_4_mec.bin` | 268160 | `9b73415db92b1854…` | amdgpu/gc_11_0_4_mec.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_4_rlc.bin` | 159152 | `257ced82d7bec412…` | amdgpu/gc_11_0_4_rlc.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_0_pfp.bin` | 263424 | `82ccf0265d841351…` | amdgpu/gc_11_5_0_pfp.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/gc_11_5_0_me.bin` | 263424 | `338019a1fcdab397…` | amdgpu/gc_11_5_0_me.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/gc_11_5_0_mec.bin` | 268160 | `5e022bae6638967d…` | amdgpu/gc_11_5_0_mec.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/gc_11_5_0_rlc.bin` | 166528 | `0dc8b6ef5530a4a5…` | amdgpu/gc_11_5_0_rlc.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/gc_11_5_1_pfp.bin` | 263424 | `633404d8db1dc03f…` | amdgpu/gc_11_5_1_pfp.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_1_me.bin` | 263424 | `4c4dd30c22d4f7f2…` | amdgpu/gc_11_5_1_me.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_1_mec.bin` | 268160 | `e49964d5e58686c5…` | amdgpu/gc_11_5_1_mec.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_1_rlc.bin` | 161040 | `92731ecabbeb7786…` | amdgpu/gc_11_5_1_rlc.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_2_pfp.bin` | 263424 | `baee1456dd1800cd…` | amdgpu/gc_11_5_2_pfp.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_2_me.bin` | 263424 | `cab2999186d26c0e…` | amdgpu/gc_11_5_2_me.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_2_mec.bin` | 268160 | `9691d7bff5d2c933…` | amdgpu/gc_11_5_2_mec.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_2_rlc.bin` | 162096 | `c9ad70b8ac309257…` | amdgpu/gc_11_5_2_rlc.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_3_pfp.bin` | 263424 | `fee840b049b5e082…` | amdgpu/gc_11_5_3_pfp.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_3_me.bin` | 263424 | `94e2d74e834725b3…` | amdgpu/gc_11_5_3_me.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_3_mec.bin` | 268160 | `d368f3886b9245dd…` | amdgpu/gc_11_5_3_mec.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_3_rlc.bin` | 162064 | `10a68940c6258d58…` | amdgpu/gc_11_5_3_rlc.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/sdma_6_0_1.bin` | 34560 | `708c2c2c45262c98…` | amdgpu/sdma_6_0_1.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/sdma_6_1_0.bin` | 34560 | `85f9f3714de68eee…` | amdgpu/sdma_6_1_0.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/sdma_6_1_1.bin` | 34560 | `e7b7a23923ab6916…` | amdgpu/sdma_6_1_1.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/sdma_6_1_2.bin` | 34560 | `5947d78eb308a3f6…` | amdgpu/sdma_6_1_2.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/sdma_6_1_3.bin` | 34560 | `8c651f32cbf030b6…` | amdgpu/sdma_6_1_3.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_1_mes.bin` | 287712 | `4844bb3873ba1c14…` | amdgpu/gc_11_0_1_mes.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_1_mes_2.bin` | 267008 | `ba113d5a49b1465b…` | amdgpu/gc_11_0_1_mes_2.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_1_mes1.bin` | 235600 | `3a8b60ea88b7adbb…` | amdgpu/gc_11_0_1_mes1.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_4_mes.bin` | 287712 | `4844bb3873ba1c14…` | amdgpu/gc_11_0_4_mes.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_4_mes_2.bin` | 267008 | `08b3cf39981f734c…` | amdgpu/gc_11_0_4_mes_2.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_0_4_mes1.bin` | 234928 | `a213a350546abaab…` | amdgpu/gc_11_0_4_mes1.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_0_mes_2.bin` | 263632 | `01fc7ba18a4d9d7e…` | amdgpu/gc_11_5_0_mes_2.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/gc_11_5_0_mes1.bin` | 238560 | `c0ae823eb2f3801b…` | amdgpu/gc_11_5_0_mes1.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/gc_11_5_1_mes_2.bin` | 263920 | `027d59f8deb9fb8a…` | amdgpu/gc_11_5_1_mes_2.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_1_mes1.bin` | 238720 | `02edbd9fe20ff739…` | amdgpu/gc_11_5_1_mes1.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_2_mes_2.bin` | 263632 | `7b2d6c90a29308d6…` | amdgpu/gc_11_5_2_mes_2.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_2_mes1.bin` | 238176 | `b1bae04df479014e…` | amdgpu/gc_11_5_2_mes1.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_3_mes_2.bin` | 263632 | `7b2d6c90a29308d6…` | amdgpu/gc_11_5_3_mes_2.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/gc_11_5_3_mes1.bin` | 238176 | `b1bae04df479014e…` | amdgpu/gc_11_5_3_mes1.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/vcn_4_0_2.bin` | 395664 | `0312642f73717256…` | amdgpu/vcn_4_0_2.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/vcn_4_0_5.bin` | 395664 | `0317ff9e75c9feef…` | amdgpu/vcn_4_0_5.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/vcn_4_0_6.bin` | 395664 | `0317ff9e75c9feef…` | amdgpu/vcn_4_0_6.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/vcn_4_0_6_1.bin` | 395664 | `d98a5ac94be0eac7…` | amdgpu/vcn_4_0_6_1.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/vpe_6_1_0.bin` | 25984 | `10a900e43e8633bc…` | amdgpu/vpe_6_1_0.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/vpe_6_1_1.bin` | 25984 | `36cfb5c08a28dd60…` | amdgpu/vpe_6_1_1.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/vpe_6_1_3.bin` | 25984 | `e4545e48016f8cce…` | amdgpu/vpe_6_1_3.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/umsch_mm_4_0_0.bin` | 386656 | `6062fdd774e89251…` | amdgpu/umsch_mm_4_0_0.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/dcn_3_1_4_dmcub.bin` | 350624 | `454d3eb73045d0a4…` | amdgpu/dcn_3_1_4_dmcub.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdgpu/dcn_3_5_dmcub.bin` | 522784 | `d6fd4f73fe46c472…` | amdgpu/dcn_3_5_dmcub.bin | LICENSE.amdgpu | amdgpu | yes |
| `vendor/firmware/amdgpu/dcn_3_5_1_dmcub.bin` | 522656 | `9903b94852601b1e…` | amdgpu/dcn_3_5_1_dmcub.bin | LICENSE.amdgpu | amdgpu | no |
| `vendor/firmware/amdnpu/1502_00/npu.sbin` | 246656 | `718142a5778b003e…` | amdnpu/1502_00/npu.sbin.1.5.2.380 (WHENCE link amdnpu/1502_00/npu.sbin) | LICENSE.amdnpu | amdxdna | no |
| `vendor/firmware/amdnpu/17f0_10/npu.sbin` | 376768 | `81831072efc3db9e…` | amdnpu/17f0_10/npu.sbin.1.0.0.63 (WHENCE link amdnpu/17f0_10/npu.sbin) | LICENSE.amdnpu | amdxdna | yes |
| `vendor/firmware/amdnpu/17f0_11/npu.sbin` | 376768 | `7f1cc47f1b462d92…` | amdnpu/17f0_11/npu.sbin.1.0.0.166 (WHENCE link amdnpu/17f0_11/npu.sbin) | LICENSE.amdnpu | amdxdna | no |
| `vendor/firmware/amdnpu/1502_00/npu.sbin.1.5.2.380` | 246656 | `718142a5778b003e…` | amdnpu/1502_00/npu.sbin.1.5.2.380 | LICENSE.amdnpu | amdxdna | no |
| `vendor/firmware/amdnpu/1502_00/npu.sbin.1.5.5.391` | 248592 | `d13ff9fb95c6cea4…` | amdnpu/1502_00/npu.sbin.1.5.5.391 | LICENSE.amdnpu | amdxdna | no |
| `vendor/firmware/amdnpu/1502_00/npu_7.sbin` | 248592 | `d13ff9fb95c6cea4…` | amdnpu/1502_00/npu.sbin.1.5.5.391 (WHENCE link amdnpu/1502_00/npu_7.sbin) | LICENSE.amdnpu | amdxdna | no |
| `vendor/firmware/amdnpu/17f0_10/npu.sbin.1.0.0.63` | 376768 | `81831072efc3db9e…` | amdnpu/17f0_10/npu.sbin.1.0.0.63 | LICENSE.amdnpu | amdxdna | yes |
| `vendor/firmware/amdnpu/17f0_10/npu.sbin.1.1.2.64` | 429680 | `7ed0f242f253b581…` | amdnpu/17f0_10/npu.sbin.1.1.2.64 | LICENSE.amdnpu | amdxdna | yes |
| `vendor/firmware/amdnpu/17f0_10/npu_7.sbin` | 429680 | `7ed0f242f253b581…` | amdnpu/17f0_10/npu.sbin.1.1.2.64 (WHENCE link amdnpu/17f0_10/npu_7.sbin) | LICENSE.amdnpu | amdxdna | yes |
| `vendor/firmware/amdnpu/17f0_11/npu.sbin.1.0.0.166` | 376768 | `7f1cc47f1b462d92…` | amdnpu/17f0_11/npu.sbin.1.0.0.166 | LICENSE.amdnpu | amdxdna | no |
| `vendor/firmware/amdnpu/17f0_11/npu.sbin.1.1.2.65` | 429680 | `3e3c996ef1e562e9…` | amdnpu/17f0_11/npu.sbin.1.1.2.65 | LICENSE.amdnpu | amdxdna | no |
| `vendor/firmware/amdnpu/17f0_11/npu_7.sbin` | 429680 | `3e3c996ef1e562e9…` | amdnpu/17f0_11/npu.sbin.1.1.2.65 (WHENCE link amdnpu/17f0_11/npu_7.sbin) | LICENSE.amdnpu | amdxdna | no |
| `vendor/firmware/mediatek/mt7925/WIFI_RAM_CODE_MT7925_1_1.bin` | 1392088 | `23ff53b4bb639b30…` | mediatek/mt7925/WIFI_RAM_CODE_MT7925_1_1.bin | LICENCE.mediatek | mt7925e | yes |
| `vendor/firmware/mediatek/mt7925/WIFI_MT7925_PATCH_MCU_1_1_hdr.bin` | 188192 | `8eb46014d2a6b412…` | mediatek/mt7925/WIFI_MT7925_PATCH_MCU_1_1_hdr.bin | LICENCE.mediatek | mt7925e | yes |
| `vendor/firmware/mediatek/WIFI_RAM_CODE_MT7961_1a.bin` | 802808 | `3edec74ffe341b91…` | mediatek/WIFI_RAM_CODE_MT7961_1a.bin | LICENCE.mediatek | mt7921e | no |
| `vendor/firmware/mediatek/WIFI_MT7961_patch_mcu_1a_2_hdr.bin` | 100384 | `a766c4e39815e554…` | mediatek/WIFI_MT7961_patch_mcu_1a_2_hdr.bin | LICENCE.mediatek | mt7921e | no |
| `vendor/firmware/mediatek/WIFI_RAM_CODE_MT7961_1.bin` | 792036 | `b94217a951518a9c…` | mediatek/WIFI_RAM_CODE_MT7961_1.bin | LICENCE.mediatek | mt7921e | no |
| `vendor/firmware/mediatek/WIFI_MT7961_patch_mcu_1_2_hdr.bin` | 92192 | `a276c06c2b772adb…` | mediatek/WIFI_MT7961_patch_mcu_1_2_hdr.bin | LICENCE.mediatek | mt7921e | no |
| `vendor/firmware/mediatek/WIFI_RAM_CODE_MT7922_1.bin` | 1231252 | `d100e5e04c324fc8…` | mediatek/WIFI_RAM_CODE_MT7922_1.bin | LICENCE.mediatek | mt7921e | no |
| `vendor/firmware/mediatek/WIFI_MT7922_patch_mcu_1_1_hdr.bin` | 137632 | `7fc9075d6d54b31e…` | mediatek/WIFI_MT7922_patch_mcu_1_1_hdr.bin | LICENCE.mediatek | mt7921e | no |
| `vendor/firmware/mediatek/BT_RAM_CODE_MT7922_1_1_hdr.bin` | 517398 | `299942dbec7d34af…` | mediatek/BT_RAM_CODE_MT7922_1_1_hdr.bin | LICENCE.mediatek | btmtk | no |
| `vendor/firmware/mediatek/BT_RAM_CODE_MT7961_1_2_hdr.bin` | 533870 | `7a440a0f7404c73a…` | mediatek/BT_RAM_CODE_MT7961_1_2_hdr.bin | LICENCE.mediatek | btmtk | no |
| `vendor/firmware/mediatek/mt7925/BT_RAM_CODE_MT7925_1_1_hdr.bin` | 448367 | `be7c18e37221e277…` | mediatek/mt7925/BT_RAM_CODE_MT7925_1_1_hdr.bin | LICENCE.mediatek | btmtk | yes |
| `vendor/firmware/rtw89/rtw8851b_fw.bin` | 1164440 | `945c854d7cf69dd9…` | rtw89/rtw8851b_fw.bin | LICENCE.rtlwifi_firmware.txt | rtw89_8851b | no |
| `vendor/firmware/rtw89/rtw8852a_fw.bin` | 1428272 | `7eb1fe457f5a704b…` | rtw89/rtw8852a_fw.bin | LICENCE.rtlwifi_firmware.txt | rtw89_8852a | no |
| `vendor/firmware/rtw89/rtw8852b_fw-1.bin` | 1245944 | `5b68415e3bfe7271…` | rtw89/rtw8852b_fw-1.bin | LICENCE.rtlwifi_firmware.txt | rtw89_8852b | no |
| `vendor/firmware/rtw89/rtw8852c_fw-2.bin` | 2644326 | `916e87d1470bce54…` | rtw89/rtw8852c_fw-2.bin | LICENCE.rtlwifi_firmware.txt | rtw89_8852c | no |
| `vendor/firmware/rtw89/rtw8922a_fw-4.bin` | 1849226 | `d11927f593c82879…` | rtw89/rtw8922a_fw-4.bin | LICENCE.rtlwifi_firmware.txt | rtw89_8922a | no |
| `vendor/firmware/rtl_bt/rtl8851bu_fw.bin` | 49760 | `7fcf88c00b2548a5…` | rtl_bt/rtl8851bu_fw.bin | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtl_bt/rtl8851bu_config.bin` | 6 | `6c28a3f07c6a30ed…` | rtl_bt/rtl8761bu_config.bin (WHENCE link rtl_bt/rtl8851bu_config.bin) | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtl_bt/rtl8852au_fw.bin` | 63352 | `fb52f72e986d4c96…` | rtl_bt/rtl8852au_fw.bin | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtl_bt/rtl8852au_config.bin` | 6 | `6c28a3f07c6a30ed…` | rtl_bt/rtl8761bu_config.bin (WHENCE link rtl_bt/rtl8852au_config.bin) | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtl_bt/rtl8852bu_fw.bin` | 129733 | `c2b0d34a4ff8a8ea…` | rtl_bt/rtl8852bu_fw.bin | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtl_bt/rtl8852bu_config.bin` | 6 | `6c28a3f07c6a30ed…` | rtl_bt/rtl8761bu_config.bin (WHENCE link rtl_bt/rtl8852bu_config.bin) | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtl_bt/rtl8852btu_fw.bin` | 128140 | `bd162fd3b70e805c…` | rtl_bt/rtl8852btu_fw.bin | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtl_bt/rtl8852btu_config.bin` | 6 | `6c28a3f07c6a30ed…` | rtl_bt/rtl8761bu_config.bin (WHENCE link rtl_bt/rtl8852btu_config.bin) | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtl_bt/rtl8852cu_fw.bin` | 113336 | `9b8b27741a914c1c…` | rtl_bt/rtl8852cu_fw.bin | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtl_bt/rtl8852cu_fw_v2.bin` | 112953 | `d1314df53b8f4282…` | rtl_bt/rtl8852cu_fw_v2.bin | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtl_bt/rtl8852cu_config.bin` | 6 | `6c28a3f07c6a30ed…` | rtl_bt/rtl8761bu_config.bin (WHENCE link rtl_bt/rtl8852cu_config.bin) | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtl_bt/rtl8922au_fw.bin` | 71360 | `112290ca9dc39850…` | rtl_bt/rtl8922au_fw.bin | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtl_bt/rtl8922au_config.bin` | 6 | `6c28a3f07c6a30ed…` | rtl_bt/rtl8922au_config.bin | LICENCE.rtlwifi_firmware.txt | btrtl | no |
| `vendor/firmware/rtw89/rtw8851b_fw-1.bin` | 1408706 | `1c4ccb5fa06bf564…` | rtw89/rtw8851b_fw-1.bin | LICENCE.rtlwifi_firmware.txt | rtw89 | no |
| `vendor/firmware/rtw89/rtw8852a_fw-1.bin` | 1958648 | `fdb5513cf7372440…` | rtw89/rtw8852a_fw-1.bin | LICENCE.rtlwifi_firmware.txt | rtw89 | no |
| `vendor/firmware/rtw89/rtw8852b_fw-2.bin` | 1554594 | `6ff6aeb56bb5b85c…` | rtw89/rtw8852b_fw-2.bin | LICENCE.rtlwifi_firmware.txt | rtw89 | no |
| `vendor/firmware/rtw89/rtw8852b_fw.bin` | 1035232 | `5b9c224ae014e0ae…` | rtw89/rtw8852b_fw.bin | LICENCE.rtlwifi_firmware.txt | rtw89 | no |
| `vendor/firmware/rtw89/rtw8852bt_fw-1.bin` | 937688 | `164e5e2243b1241a…` | rtw89/rtw8852bt_fw-1.bin | LICENCE.rtlwifi_firmware.txt | rtw89 | no |
| `vendor/firmware/rtw89/rtw8852bt_fw.bin` | 928714 | `b75914312181a2cd…` | rtw89/rtw8852bt_fw.bin | LICENCE.rtlwifi_firmware.txt | rtw89 | no |
| `vendor/firmware/rtw89/rtw8852c_fw-1.bin` | 2375560 | `95e4226f7a4c2a50…` | rtw89/rtw8852c_fw-1.bin | LICENCE.rtlwifi_firmware.txt | rtw89 | no |
| `vendor/firmware/rtw89/rtw8852c_fw.bin` | 1532656 | `e05e704911ec5d65…` | rtw89/rtw8852c_fw.bin | LICENCE.rtlwifi_firmware.txt | rtw89 | no |
| `vendor/firmware/rtw89/rtw8922a_fw-1.bin` | 1583434 | `4340bc322912f30f…` | rtw89/rtw8922a_fw-1.bin | LICENCE.rtlwifi_firmware.txt | rtw89 | no |
| `vendor/firmware/rtw89/rtw8922a_fw-2.bin` | 1586954 | `9ca08cd3098b954c…` | rtw89/rtw8922a_fw-2.bin | LICENCE.rtlwifi_firmware.txt | rtw89 | no |
| `vendor/firmware/rtw89/rtw8922a_fw-3.bin` | 1238542 | `484f496bc149706b…` | rtw89/rtw8922a_fw-3.bin | LICENCE.rtlwifi_firmware.txt | rtw89 | no |
| `vendor/firmware/rtw89/rtw8922a_fw.bin` | 1537690 | `84458f2fa7c9a730…` | rtw89/rtw8922a_fw.bin | LICENCE.rtlwifi_firmware.txt | rtw89 | no |
| `vendor/firmware/cirrus/cs35l56-b0-dsp1-misc-10431024-spkid0-amp1.bin` | 8264 | `80991ea93c5cb52a…` | cirrus/cs35l56-b0-dsp1-misc-10431044-spkid0-amp1.bin (WHENCE link cirrus/cs35l56-b0-dsp1-misc-10431024-spkid0-amp1.bin) | LICENSE.cirrus | cs35l56 | no |
| `vendor/firmware/cirrus/cs35l56-b0-dsp1-misc-10431024-spkid0-amp2.bin` | 8264 | `5f691b512e95995d…` | cirrus/cs35l56-b0-dsp1-misc-10431044-spkid0-amp2.bin (WHENCE link cirrus/cs35l56-b0-dsp1-misc-10431024-spkid0-amp2.bin) | LICENSE.cirrus | cs35l56 | no |
| `vendor/firmware/cirrus/cs35l56-b0-dsp1-misc-10431024-spkid0.wmfw` | 31996 | `12c6d4fe63dc6a47…` | cirrus/cs35l56/CS35L56_Rev3.11.16.wmfw (WHENCE link cirrus/cs35l56-b0-dsp1-misc-10431024-spkid0.wmfw) | LICENSE.cirrus | cs35l56 | no |
| `vendor/firmware/cirrus/cs35l56-b0-dsp1-misc-10431024-spkid1-amp1.bin` | 8256 | `108671391e61a596…` | cirrus/cs35l56-b0-dsp1-misc-10431044-spkid1-amp1.bin (WHENCE link cirrus/cs35l56-b0-dsp1-misc-10431024-spkid1-amp1.bin) | LICENSE.cirrus | cs35l56 | yes |
| `vendor/firmware/cirrus/cs35l56-b0-dsp1-misc-10431024-spkid1-amp2.bin` | 8256 | `380e8f976532c5d6…` | cirrus/cs35l56-b0-dsp1-misc-10431044-spkid1-amp2.bin (WHENCE link cirrus/cs35l56-b0-dsp1-misc-10431024-spkid1-amp2.bin) | LICENSE.cirrus | cs35l56 | yes |
| `vendor/firmware/cirrus/cs35l56-b0-dsp1-misc-10431024-spkid1.wmfw` | 31996 | `12c6d4fe63dc6a47…` | cirrus/cs35l56/CS35L56_Rev3.11.16.wmfw (WHENCE link cirrus/cs35l56-b0-dsp1-misc-10431024-spkid1.wmfw) | LICENSE.cirrus | cs35l56 | yes |
| `vendor/firmware/cirrus/cs35l56-b0-dsp1-misc-10431b13-spkid0-amp1.bin` | 8196 | `e2ef9882d2034113…` | cirrus/cs35l56-b0-dsp1-misc-10431b13-spkid0-amp1.bin | LICENSE.cirrus | cs35l56 | no |
| `vendor/firmware/cirrus/cs35l56-b0-dsp1-misc-10431b13-spkid0-amp2.bin` | 8196 | `e22124a8f1eb2a4e…` | cirrus/cs35l56-b0-dsp1-misc-10431b13-spkid0-amp2.bin | LICENSE.cirrus | cs35l56 | no |
| `vendor/firmware/cirrus/cs35l56-b0-dsp1-misc-10431b13-spkid0.wmfw` | 31996 | `12c6d4fe63dc6a47…` | cirrus/cs35l56/CS35L56_Rev3.11.16.wmfw (WHENCE link cirrus/cs35l56-b0-dsp1-misc-10431b13-spkid0.wmfw) | LICENSE.cirrus | cs35l56 | no |
| `vendor/firmware/cirrus/cs35l56-b0-dsp1-misc-10431b13-spkid1-amp1.bin` | 8192 | `bf2e99b36de6ec77…` | cirrus/cs35l56-b0-dsp1-misc-10431b13-spkid1-amp1.bin | LICENSE.cirrus | cs35l56 | no |
| `vendor/firmware/cirrus/cs35l56-b0-dsp1-misc-10431b13-spkid1-amp2.bin` | 8192 | `41325e7109807adb…` | cirrus/cs35l56-b0-dsp1-misc-10431b13-spkid1-amp2.bin | LICENSE.cirrus | cs35l56 | no |
| `vendor/firmware/cirrus/cs35l56-b0-dsp1-misc-10431b13-spkid1.wmfw` | 31996 | `12c6d4fe63dc6a47…` | cirrus/cs35l56/CS35L56_Rev3.11.16.wmfw (WHENCE link cirrus/cs35l56-b0-dsp1-misc-10431b13-spkid1.wmfw) | LICENSE.cirrus | cs35l56 | no |
