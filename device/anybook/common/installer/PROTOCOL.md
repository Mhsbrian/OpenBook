# openbook-installd protocol (ANAL-191)

The installer app (`OpenBookInstaller`, `org.openbook.installer`) talks to the install engine's daemon,
`openbook-install daemon` (init service `openbook_installd`, started only when `ro.boot.openbook.live=1`), over a
UNIX stream socket that init creates: `/dev/socket/openbook_installd`. In Java/Kotlin:
`LocalSocket().connect(LocalSocketAddress("openbook_installd", LocalSocketAddress.Namespace.RESERVED))`.
SELinux lets only `platform_app` connect.

Framing: one JSON object per line (UTF-8, `\n`-terminated), both ways. Every request carries an integer `id`; every
message the daemon sends for that request carries the same `id`. A request gets exactly one final message
(`"ok": true|false`); `apply` and `attach` send `event` messages before it. The daemon serves one connection at a
time; a second connection waits. Requests on one connection are handled in order.

Errors: `{"id": N, "ok": false, "code": "short_code", "error": "Human-readable sentence."}`.
Codes: `bad_request`, `busy` (an install is running), `no_source` (not booted from an OpenBook stick, or its
manifest is missing or unreadable), `no_target`, `not_eligible` (see `why`), `plan_changed`, `confirm_mismatch`,
`power`, `io`, `internal`. The Google apps step (ANAL-211, `gapps_check` below) adds `refused`, `not_a_package`,
`no_package`, `no_gapps` (the plan names a package that is not staged, or changed), `gapps_clash` (the package adds
a file the image has), `gapps_not_confirmed`.

All sizes are bytes (integers). Strings from the engine (model names, details) are not localised; the app
localises everything it renders from ids and states.

## hello
`{"id":1,"cmd":"hello"}` →
```json
{"id":1,"ok":true,"version":1,"live":true,"selinux":"enforcing",
 "boot_disk":{"name":"sda","by_id":"usb-SanDisk_Ultra_4C53...-0:0","model":"SanDisk Ultra","size_bytes":30752636928},
 "source":{"label":"openbook-live-20261017x","fingerprint":"OpenBook/anybook_g14_x86_64/...","ok":true,"why":null},
 "efivars":true,
 "power":{"ac":true,"battery_pct":87,"ok":true},
 "logs_on_stick":true,
 "job":null}
```
`source.ok` false (with `why`) means installing is impossible from this boot (e.g. no install data on the stick).
`power.ok` is the S8 rule: AC connected, or battery at 50 % or more, or no battery at all (desktops, VMs).
`battery_pct` is null without a battery. `power` itself is null when the daemon cannot read the power supplies:
on Android only the health HAL may read them, so the app reads them (BatteryManager) and sends them with `apply`. `job` is null, or the `status` object below while an install runs or
after it finished.

## hwinfo
`{"id":2,"cmd":"hwinfo"}` →
```json
{"id":2,"ok":true,"hw":{
  "schema":"openbook-hwinfo/1",
  "machine":{"vendor":"ASUSTeK COMPUTER INC.","product":"ROG Zephyrus G14 GA403WR","board":"GA403WR",
             "firmware":"UEFI","secure_boot":"off","ram_bytes":33554432000,"cpu":"AMD Ryzen AI 9 HX 370"},
  "verdict":"ready",
  "components":[
    {"id":"cpu","state":"ready","value":"AMD Ryzen AI 9 HX 370","detail":"12 cores · amd-pstate-epp"},
    {"id":"gpu","state":"ready","value":"AMD Radeon 890M","detail":"amdgpu"},
    {"id":"display","state":"ready","value":"2880 × 1800","detail":"eDP-1"},
    {"id":"wifi","state":"ready","value":"MediaTek MT7925","detail":"mt7925e · Bluetooth hci0"},
    {"id":"touchpad","state":"ready","value":"ELAN touchpad","detail":"ASUP1205:00 04F3:3315"},
    {"id":"storage","state":"ready","value":"SK hynix PVC10","detail":"NVMe · 1.0 TB"},
    {"id":"audio","state":"limited","value":"Realtek ALC285 + CS35L56","detail":"speaker_tuning_missing"},
    {"id":"sleep","state":"new","value":"s2idle","detail":"untested_model"},
    {"id":"dgpu","state":"off","value":"NVIDIA GeForce RTX 5070 Ti Laptop","detail":"powered_down"},
    {"id":"battery","state":"ready","value":"87 %","detail":"charging"}
  ]}}
```
Component ids (fixed order): `cpu`, `gpu`, `display`, `wifi`, `touchpad`, `storage`, `audio`, `sleep`, `dgpu`,
`battery`. On Android the daemon may not read the DRM connectors, the input devices or the battery (SELinux), so
`display` and `touchpad` can come back `missing` and `battery` absent; the app fills them in from DisplayManager,
InputManager and BatteryManager and recomputes `verdict`. Components that do not apply are left out (`dgpu` without a second GPU, `battery` on a desktop).
States: `ready` (works), `limited` (works with a known gap; `detail` is a reason code), `new` (present but not
tested on this model yet), `off` (deliberately switched off), `missing` (not found, or no driver), `unknown`.
Reason codes in `detail` the app turns into sentences: `speaker_tuning_missing` ("Quieter until tuned"),
`untested_model`, `powered_down` ("Switched off to save power"), `software_rendering` (a VM or an unsupported GPU:
"Drawn in software"), `no_driver`, `not_found`, `s0i3_not_reached` (sleep works, the deepest state not yet),
`charging`, `on_battery`. Any other `detail` is shown as is.
`verdict`: `ready` (every component `ready`, `limited`, `new` or `off`), `limited` (something `missing` or
`software_rendering`), `unsupported` (no display or no storage).

## disks
`{"id":3,"cmd":"disks"}` →
```json
{"id":3,"ok":true,"disks":[
 {"name":"nvme0n1","by_id":"nvme-SK_hynix_PVC10_AN0BS4F2A","model":"SK hynix PVC10","vendor":"",
  "serial":"AN0BS4F2A","wwn":"eui.ace42e0035a1b2c3","size_bytes":1024209543168,"sector_size":512,
  "bus":"nvme","removable":false,"read_only":false,"boot_disk":false,
  "table":"gpt","os":["Windows","Linux"],
  "free_bytes":74088185856,"largest_free_bytes":74088185856,
  "partitions":[
    {"index":1,"name":"EFI system partition","type":"esp","fs":"vfat","label":"SYSTEM","bytes":272629760,
     "start":1048576,"os":"","encrypted":false,"mounted":false},
    {"index":3,"name":"Basic data partition","type":"msdata","fs":"ntfs","label":"Windows","bytes":442381172736,
     "start":290455552,"os":"Windows","encrypted":false,"mounted":false}],
  "layouts":{"whole":{"ok":true,"why":null},"alongside":{"ok":true,"why":null,"free_bytes":74088185856}},
  "warnings":[]}]}
```
Every disk is listed, the boot stick too (`boot_disk: true`, both layouts `ok: false`, `why: "boot_disk"`).
`type`: `esp`, `xbootldr`, `msreserved`, `msdata`, `msrecovery`, `linux`, `linux_swap`, `linux_lvm`, `luks`,
`android`, `apple`, `other`, `free`. `fs`: `vfat`, `ntfs`, `exfat`, `ext4`, `btrfs`, `xfs`, `f2fs`, `swap`,
`bitlocker`, `luks`, `erofs`, `` (unknown). `why` codes: `boot_disk`, `mounted`, `read_only`, `too_small`
(whole: disk below the minimum), `no_space` (alongside: largest free extent below the minimum), `no_gpt`
(alongside needs a GPT disk), `table_full`, `name_clash` (the disk already has Android partitions: use whole),
`busy`. `warnings`: `external` (USB/Thunderbolt disk other than the stick, S13), `encrypted` (BitLocker/LUKS on
the disk: erased with "whole", kept with "alongside", S12).

## plan (dry run, read-only)
`{"id":4,"cmd":"plan","target":"nvme-SK_hynix_PVC10_AN0BS4F2A","layout":"whole","locale":"en-US","keyboard":"us","set_default":true}`
→ `{"id":4,"ok":true,"plan":{...}}`. The target is opened read-only (S5). Fields the app uses:
```json
{"schema":"openbook-install-plan/1","plan_sha256":"9f2c...","layout":"whole",
 "target":{"by_id":"nvme-...","model":"SK hynix PVC10","size_bytes":1024209543168,"bus":"nvme"},
 "confirm_text":"SK hynix PVC10",
 "erases":[{"index":3,"name":"Basic data partition","fs":"ntfs","label":"Windows","os":"Windows","bytes":442381172736}],
 "keeps":[],
 "after":[{"kind":"openbook","bytes":1024209543168,"label":"OpenBook"}],
 "before":[{"kind":"windows","bytes":412000000000,"label":"Windows"},{"kind":"linux","bytes":541000000000,"label":"Linux"},
           {"kind":"efi","bytes":272629760,"label":"EFI"},{"kind":"free","bytes":69000000000,"label":""}],
 "bytes_to_write":1621098496,"estimated_seconds":95,
 "boot":{"entry":"loader/entries/openbook-a.conf","fallback_path":true,"nvram":"planned","boot_order":"first","set_default":true},
 "warnings":[],
 "operations":[{"op":"wipe_table","text":"Erase the partition table (primary, backup and protective MBR)"},
               {"op":"copy","text":"Copy boot_a (64.0 MiB) from the stick to partition 3 at 545259520","bytes":67108864,"sha256":"..."}]}
```
`before`/`after` segment kinds: `windows`, `linux`, `efi`, `openbook`, `other`, `free`. `operations[].text` is
English; "View the plan" shows it in a monospace list. `boot.nvram`: `planned` (efivarfs is mounted: one `Boot####`
"OpenBook" will be created after verification) or `unavailable`. `boot.boot_order`: `first` (with `set_default`, the
user's consent, S11), `last` (without it: OpenBook is in the firmware's boot menu and the system that starts now
stays the default; owner decision 2026-10-17) or `unchanged` (no efivarfs). `warnings` codes: `nvram_unavailable`
(no efivarfs: the whole-disk install boots through the fallback path; alongside needs a firmware boot entry the user
adds), `external`, `encrypted_kept`, `encrypted_erased`, `battery`;
with a Google apps package: `gapps_uncertified` (always), `privapp_allowlist_not_enforced` (this image does not set
`ro.control_privapp_permissions=enforce`).

**With a Google apps package** (ANAL-211): the request adds `"gapps":"<gapps_sha256 from gapps_check>"` and
`"gapps_confirmed":true` (the user ticked the uncertified-device warning; without it the plan is refused with
`gapps_not_confirmed`). The plan then has `request.gapps`, the operations `check_gapps`, `product` and `vbmeta`,
`vbmeta_a` with `content: "vbmeta_rebuilt"`, `openbook/a/bootconfig.img` with `"sha256": null, "after_product":
true` (its vbmeta digest is known once product is built), and two sections:
```json
"gapps":{"manifest_sha256":"4074e384...","package":{"file":"LiteGapps-x86_64-17.0-....zip","bytes":220000000,
  "sha256":"...","name":"LiteGapps","version":"..."},"files":120,"bytes":612000000,
  "apps":[{"dir":"priv-app/GmsCore","package":"com.google.android.gms","version_name":"...","version_code":0,
           "privileged":true,"native":"x86_64","signer_sha256":"...","signer":"CN=Android, OU=Android, O=Google Inc., ..."}]},
"product":{"partition":"product_a","stick_bytes":292503552,"stick_image_bytes":286937088,"bytes":905969664,
  "image_bytes":899000000,"hashtree_bytes":7090176,"fec_roots":0,"new_inodes":250,"rewritten_directories":5,
  "super_offset_before":830472192,"super_offset":1344274432,"super_metadata_sha256":"...","vbmeta":"unsigned"}
```
A plan without `gapps` is exactly what it was before this step existed.

## apply (writes; S3, S4)
`{"id":5,"cmd":"apply","plan_sha256":"9f2c...","target":"nvme-SK_hynix_PVC10_AN0BS4F2A","typed":"sk hynix pvc10","power":{"ac":true,"battery_pct":87}}`
(`power`: the app's reading, used for S8 when the daemon cannot read the supplies.)
The daemon re-computes the plan (same seeds), refuses with `plan_changed` if it differs, refuses with
`confirm_mismatch` unless `typed` equals `confirm_text` (case-insensitive, whitespace ignored), and with `power`
if S8 fails. Then it streams:
```json
{"id":5,"event":"step","step":"check_source","state":"running"}
{"id":5,"event":"progress","step":"check_source","done":104857600,"total":1584364036,"pct":2.2,"eta_s":88,"all_done":104857600,"all_total":4633294546}
{"id":5,"event":"step","step":"check_source","state":"done"}
{"id":5,"event":"log","line":"12:00:03 verify super: sha256 ok (1409286144 bytes)"}
...
{"id":5,"ok":true,"result":{"ok":true,"verified":true,"failed_step":null,"error":null,
  "boot_entry":"loader/entries/openbook-a.conf","nvram":"created","nvram_entry":"Boot0005","boot_order":"first",
  "nvram_error":null,"fallback_path":true,
  "report":"openbook/logs/install-20261017T120000Z.json","log":"openbook/logs/install-20261017T120000Z.log",
  "seconds":93}}
```
`nvram`: `created` (and `nvram_entry`; `boot_order` = `first`, `last`, or `failed` when the entry exists but
`BootOrder` could not be written, with `nvram_error`), `failed` (no entry; `nvram_error` says why; the
disk is installed and verified all the same), `unavailable` (no efivarfs) or `skipped` (the install did not verify).
Steps, in order: `check_source` (S10: the stick's partitions against its manifest), `prepare_disk` (S4 re-check,
wipe or add the partition table), `boot_images` (boot/init_boot/vendor_boot/vbmeta), `system` (super),
`boot_entry` (ESP/XBOOTLDR files, loader entry, NVRAM entry if possible), `verify` (read back every written
partition, S9), `report`. Step states: `pending`, `running`, `done`, `failed`, `skipped`. `pct` is overall
progress (0–100); `done`/`total` are the running step's own bytes, `all_done`/`all_total` the whole install's. If the client disconnects the install continues; reconnect and send `attach`.

With a package, the report adds `"gapps":{"manifest_sha256":..., "product":"product_a", "product_bytes":...,
"product_sha256":..., "root_digest":..., "super_offset":..., "vbmeta_digest":..., "vbmeta_size":..., "vbmeta":"unsigned"}`.

## gapps_check (ANAL-211)
A Google apps package the user picked (docs/gapps.md section 5). The request line is followed at once by exactly
`bytes` raw bytes, the file itself:
`{"id":10,"cmd":"gapps_check","name":"LiteGapps-....zip","bytes":220000000}` + the file. While it arrives the
daemon sends `{"id":10,"event":"progress","step":"upload","done":...,"total":...}`; no other request is read until
it is complete. The daemon saves it below `/data/misc/openbook_install/gapps/`, checks it and stages what it may
install (the earlier staged package is removed), deletes the upload, and answers:
```json
{"id":10,"ok":true,"gapps_sha256":"4074e384...","gapps":{"schema":"openbook-gapps/1",
  "package":{"file":"...","bytes":220000000,"sha256":"...","layout":"litegapps","payload":"files/files.tar.br",
             "name":"...","version":"...","author":"...","type":"litegapps"},
  "arch":"x86_64","sdk":37,"checked":"2026-10-18T06:00:00Z","bytes":612000000,
  "files":[{"path":"priv-app/GmsCore/GmsCore.apk","kind":"apk","bytes":...,"sha256":"...","stage":"files/00042"}],
  "apps":[{"dir":"priv-app/GmsCore","privileged":true,"apks":[{"path":"...","split":null}],
           "package":"com.google.android.gms","version_code":...,"version_name":"...","min_sdk":...,"target_sdk":...,
           "abis":["x86_64"],"native":"x86_64","requested_permissions":...,"signing_scheme":"v3",
           "signer_sha256":"...","signer":"CN=Android, OU=Android, O=Google Inc., L=Mountain View, ST=California, C=US"}],
  "xml":[{"path":"etc/permissions/privapp-permissions-google.xml","elements":{"privapp-permissions":20}}]},
 "warnings":["multi_abi:com.google.android.gms"]}
```
`gapps` is the install manifest; `gapps_sha256` is the sha256 of its exact bytes and names it in `plan`. It is
also written into the new system as `/product/etc/openbook/gapps-manifest.json`. `warnings`: `multi_abi:<package>`
(an APK also carries libraries for other ABIs, never loaded here), `no_privapp_allowlist` (no `etc/permissions`
file). A refusal is `{"id":10,"ok":false,"code":"refused","error":"3 paths cannot be installed","refused":[{"path":
"framework/com.google.android.maps.jar","rule":"framework","why":"touches the framework (framework libraries)"}],
"refused_more":0}`. Rules: `wrong_arch`, `wrong_sdk`, `outside_product`, `unexpected_path`, `unsafe_path`, `link`,
`special_file`, `framework`, `init`, `selinux`, `native_lib`, `native_abi`, `preopted`, `duplicate`, `too_big`,
`too_many_files`, `empty`, `apk_invalid`, `unsigned`, `platform_uid`, `needs_newer_sdk`, `split_mismatch`,
`duplicate_package`, `xml_root`, `xml_element`, `xml_doctype`, `xml_malformed`. Other failures: `not_a_package`
(not a zip, no `files/files.tar.*`, damaged data), `no_package` (unreadable), `io`. The CLI does the same:
`openbook-install gapps-check --package FILE`, then `plan ... --gapps <sha256>`.

## attach / status
`{"id":6,"cmd":"attach"}` replays the current job's step states, then streams like `apply` until it ends (or
answers at once with the final message if it already ended). `{"id":7,"cmd":"status"}` →
`{"id":7,"ok":true,"job":{"running":true,"pct":42.0,"step":"system","steps":{"check_source":"done",...},"result":null}}`
(`job` is null if no install ran in this boot).

## save_report
`{"id":8,"cmd":"save_report"}` writes the `hwinfo` JSON and a text version to the stick's ESP →
`{"id":8,"ok":true,"path":"openbook/logs/hwcheck-live-001.json"}`.

## log
`{"id":9,"cmd":"log","tail":200}` → `{"id":9,"ok":true,"lines":["..."]}`: the daemon's log (for "Show details").
