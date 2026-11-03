# Installing OpenBook

> **Developer previews only.** OpenBook images are `userdebug` builds signed with AOSP's public test keys, made for
> the ASUS ROG Zephyrus G14 (2025, GA403WR). They are not for daily use. `docs/STATUS.md` names the current release
> and what was checked on it.

OpenBook installs from a USB stick. The stick first boots OpenBook "live", without changing the laptop. You can try
it, then install it onto a whole disk or into free space next to Windows.

## 1. What you need

- A laptop with UEFI firmware and an x86-64 AMD CPU. Today that means the G14 (Ryzen AI 9 HX 370, Radeon 890M). Other
  machines are untested.
- A USB stick of 4 GB or more. **Writing the image erases it.**
- A target disk of **64 GB or more**. Smaller disks are refused.
- Mains power during the install, or a battery at 50 % or more. The installer refuses to install otherwise.
- To install next to Windows, about 64 GB of **unallocated** space on the same disk. OpenBook never shrinks or moves
  partitions, so free the space first in Windows Disk Management. Suspend BitLocker if it is on.
- **Secure Boot off.** The stick's loader is not signed for Secure Boot yet.

## 2. Get the image and write the stick

1. Download `openbook-<version>-x86_64-live.img.xz`, `SHA256SUMS` and `SHA256SUMS.sig` from the OpenBook release
   page (`docs/RELEASE.md` §1 and §2 describe the files).
2. Check them. `allowed_signers` is `keys/allowed_signers` in this repository; the release key's fingerprint is
   `SHA256:p2CHvoYmi9AsCB98uyBn4kp/rpc7eDWDeeL9rAKi8Ec`.
   ```bash
   ssh-keygen -Y verify -f allowed_signers -I release@openbook.page -n openbook-release -s SHA256SUMS.sig < SHA256SUMS
   sha256sum -c --ignore-missing SHA256SUMS
   ```
3. Write the image to the stick. USB writers such as balenaEtcher, Rufus, Raspberry Pi Imager, GNOME Disks and Fedora
   Media Writer read `.img.xz` directly. On Linux, name the stick by its `/dev/disk/by-id/usb-…` path:
   ```bash
   xz -dc openbook-<version>-x86_64-live.img.xz | sudo dd of=/dev/disk/by-id/usb-<your stick> bs=4M conv=fsync status=progress
   ```
   Don't use a multi-image boot tool such as Ventoy. It loop-mounts the image instead of writing it, so Android would
   not find its partitions on the stick.
4. **From your own build** (`scripts/installer-image.sh`), use `scripts/installer/write-stick.sh`. Name the stick by
   its `/dev/disk/by-id/usb-…` path, twice:
   ```bash
   OPENBOOK_WRITE_CONFIRM=/dev/disk/by-id/usb-<your stick> \
     scripts/installer/write-stick.sh openbook-live-<label>.img /dev/disk/by-id/usb-<your stick>
   ```
   It checks the image against its `.sha256` file and refuses anything that isn't a removable USB disk named by
   `by-id`. It copies any OpenBook logs from the stick before it writes, reads the stick back to verify, then powers
   it off. Unplug it when the script prints `stick powered off: safe to unplug`. Add `--dry-run` to run every check
   without writing.

Any tool that copies the raw image byte for byte should work, but `write-stick.sh` is the one the project tests, and
other tools neither check the target nor keep the stick's logs.

## 3. Boot the stick

1. Plug in the stick, then power on holding **Esc** to open the G14's firmware boot menu, and pick the USB stick.
2. The OpenBook menu is hidden, and **"OpenBook"** starts by itself. To pick another entry, keep pressing a key (Space,
   for example) as the stick starts. Test sticks show the menu for 10 seconds instead.

| Entry | Use it for |
|---|---|
| OpenBook | The normal live session. Changes stay on the stick |
| OpenBook - save logs to this USB stick | Same session, but it saves logs to the stick and powers off by itself |
| OpenBook - safe graphics (Mesa GL, no ANGLE) | If the screen stays black or garbled. There is also a "save logs" version |
| OpenBook - start fresh (erase this stick's saved data) | Throw away the live session's data and start again |
| OpenBook - serial console (virtual machines) | VMs only |
| Check entries ("power check", "ARM apps check", …) | Test sticks only. Each says how long it runs; they power off by themselves |

3. **The first boot after writing is slow** (about 30 s to the desktop on the G14, longer on a slow stick). Android
   unpacks itself onto the stick.

## 4. Try or install

The installer opens by itself on the live session. It has seven steps:
1. **Language.**
2. **Hardware check.** Shows what works on this laptop. **Save report to USB** writes it to the stick.
3. **Try or install.** *Try OpenBook* goes to the desktop and changes nothing. You can install later from the
   launcher's "Install OpenBook".
4. **Disk.** Every disk with its size, bus and current contents, plus its `by-id` name. The stick you booted from shows
   **In use** and can't be picked. Disks under 64 GB show **Can't be used**.
   - **Erase disk and install** uses the whole disk. Everything on it is erased.
   - **Install alongside** uses the largest free space. Existing partitions are not touched.
   - **View the plan** lists every write the install will make. The plan is read-only: nothing changes before step 5.
   - **Start OpenBook by default:** off for an alongside install, so the system you have keeps starting first. A
     whole-disk install always starts OpenBook by default.
   - Optional extras, off by default: **Google services compatibility (microG)**, when the stick carries it, and
     **Install a Google apps package you provide (advanced)**. What they mean: `docs/gapps.md`.
5. **Confirm.** Type the disk's name as shown, then press **Erase and install**.
6. **Install.** About 20 seconds in a VM; on real hardware it runs at the stick's read speed. **Show details** shows
   each step.
7. **Done.** Remove the stick and press **Restart now**.

**If the power fails or the stick is pulled during the install,** boot the stick again and run the install again. The
installer writes in an order that leaves the disk in one of three states: the old partition table (if the cut came
before anything was written), a blank disk, or a complete OpenBook. A half-written disk never boots: the boot entry
is written last, after every byte has been read back and checked. This was tested by cutting the power at six points
of the install (§7).

## 5. First start

- **Whole disk:** the installer adds an "OpenBook" entry to the firmware's boot menu and makes it the default. The
  disk also starts through the standard fallback path (`EFI/BOOT/BOOTX64.EFI`), so it boots even if the entry is
  lost.
- **Alongside Windows:** the installer adds "OpenBook" at the end of the firmware's boot order, so Windows keeps
  starting by default (unless you turned on **Start OpenBook by default**). To start OpenBook, either:
  - open the firmware's boot menu (**Esc** on the G14) and pick "OpenBook", or
  - move "OpenBook" up in the firmware setup.

  If your firmware doesn't list it (known issue 1), add a boot option once in the firmware setup, pointing at
  `\EFI\OpenBook\systemd-bootx64.efi` on the disk's EFI partition. OpenBook's own menu also lists Windows Boot
  Manager.
- **OpenBook setup** comes first: welcome, language and region, keyboard layout, internet, date and time, your name
  and a screen lock, a notice that OpenBook isn't Google-certified, optional extras, done. There is no account step,
  and **Skip setup** on the first page keeps the current settings (`docs/setup.md`). After that you get the desktop.

## 6. Update, reinstall or remove

- **Update:** OpenBook has no updater app yet. New builds go onto an installed system as A/B updates from a build host
  over adb, keeping your data (`docs/adb-debug.md` §7). Only whole-disk installs take them. Otherwise, reinstall.
- **Reinstall:** boot the stick and choose **Erase disk and install** on the OpenBook disk. It gets a new disk ID, new
  partition IDs and a new serial number, and setup runs again. Your data on that disk is erased.
- **Alongside, a second time:** refused while the earlier OpenBook partitions are on the disk ("This disk already has
  Android partitions"). Erase the disk, or delete the OpenBook partitions and `EFI/OpenBook/` from Windows first.
- **Remove an alongside install:** in Windows, delete the OpenBook partitions (`xbootldr`, `misc`, `boot_a` …
  `userdata`) and the folder `EFI\OpenBook` on the EFI partition, and remove the "OpenBook" firmware boot option.

## 7. What has been tested

**In virtual machines** (QEMU/KVM with OVMF UEFI firmware, on image files, SELinux enforcing), as of 2026-10-18:

| Test | What it shows |
|---|---|
| End-to-end matrix (`scripts/installer/e2e-qemu.sh`), 79 checks | All of the rows below pass |
| — Alongside a Windows-like disk | Windows' partitions are byte-identical afterwards, and its EFI partition gains one file and passes `fsck`. The firmware still starts "Windows" (a stand-in boot manager) by default. With a boot option added, OpenBook starts and reaches setup and the desktop |
| — A 32 GB disk | Refused (too small), in the wizard and on the command line |
| — Power cut at 6 points of the install, each followed by a restart from the stick | Every cut left the old table, a blank disk or a complete install. The firmware started nothing from the incomplete ones. Every restart completed and verified |
| — The installed disk alone, and with the stick still plugged in | Boots from its own disk both times; the stick is left unchanged |
| — Reinstall over a used OpenBook | New disk and partition IDs and a new serial number. The old data is gone and setup runs again |
| Wizard end to end (`wizard-qemu.sh`), 51 checks | All pass. With firmware boot entries: an alongside install adds OpenBook at the end of the boot order, Windows stays the default, the firmware's menu lists OpenBook, and picking it boots OpenBook |
| Live stick matrix (`live-qemu.sh`), 40 checks | All pass |
| A/B update and rollback (`scripts/ota/ota-qemu.py`), 55 checks | All pass: the data is kept, and a broken update falls back to the old slot |

**On the G14:** the installer put OpenBook on the internal NVMe disk (whole disk, 2026-10-18), and later builds arrived
over Wi-Fi as A/B updates.

Each release runs the VM install, update and rollback suite on the release build itself, then a smoke test on the
reference laptop (`CONTRIBUTING.md`). Details of the tests: `docs/installer.md` §13.

## 8. Known issues

1. **The firmware boot entry is tested only with VM firmware (OVMF).** If OpenBook doesn't show up in your firmware's
   boot menu after an alongside install, add the boot option by hand (§5). A whole-disk install also boots through
   the fallback path.
2. **An installed OpenBook offers to "set up" the installer stick if it's plugged in.** SystemUI shows "USB drive
   detected · Tap to set up", because Android can't read the stick's partition table. **Don't tap it**: setting it up
   formats the stick. The live session leaves its own stick alone; the installed system doesn't yet.
3. **The wizard calls an installed OpenBook "Linux".** On a disk that already holds OpenBook, the disk bar says
   "Linux" and the tip mentions "OpenBook and Linux". OpenBook's own ext4 and f2fs partitions are counted as Linux.
   The install itself is right: erase works and alongside is refused.
4. **Updates need a build host** (§6). Alongside installs can't take updates, and a Google apps package you installed
   is not carried across an update.
5. **Test keys.** Images are signed with AOSP's public test keys, so verified boot is "orange" (unlocked). They are
   not suitable for daily use.
6. **Only English** in the installer and setup.
7. **On the G14:** deep sleep (S0i3) isn't reached yet (`docs/power-input.md`). Apps can't render on the NVIDIA GPU.
   HDMI is wired to the NVIDIA GPU and stays dark in the default Hybrid mode until reverse PRIME lands (ANAL-249,
   `docs/nvidia-graphics-modes.md` §2). The full list is in `docs/STATUS.md`.

## 9. Release checklist (the owner approves before anything is published)

Status as of 2026-10-31. ✅ done, ⬜ open, 🔒 owner decision.

| # | Item | Status |
|---|---|---|
| 1 | **Image sha256** next to the image (`<label>.sha256`), and in the build record (`<label>.build.json`) with the repo commit, the inputs' hashes and the tool versions | ✅ `scripts/installer-image.sh` writes both; the release folder adds `SHA256SUMS` |
| 2 | **Reproducible image:** the same inputs, label and epoch give the same bytes | ✅ a live image was rebuilt from its input snapshot byte for byte (2026-10-17). The AOSP build itself is not checked for reproducibility |
| 3 | **Signature on the checksum file.** `SHA256SUMS` is signed with the OpenBook release key (`ssh-keygen -Y sign`); the public key is in the repo and on the release page. Users check with `ssh-keygen -Y verify` before `sha256sum -c` (§2) | ✅ the owner's key (2026-10-31, `SHA256:p2CHvoYm…`), public half in `keys/`; `make-release.sh --sign-pub` takes a signature made in the owner's terminal |
| 4 | **Install manifest signed** (S10 checks the stick's partitions against `MANIFEST.json`; the manifest itself isn't signed) | ⬜ needs the release key |
| 5 | **Firmware licences:** every linux-firmware file ships with its licence | ✅ the 6 licence files are in `/vendor/firmware` (amdgpu, amdnpu, mediatek, rtlwifi, cirrus, wireless-regdb), and the build reports 0 files without one. ⬜ `WHENCE` is not shipped yet. The plan (`docs/installer.md` §3.4) says it should be, next to the licences |
| 6 | **NOTICE** for the platform (Settings › Legal) | ✅ `system`, `vendor` and `product` each have `etc/NOTICE.xml.gz` |
| 7 | **GPL/LGPL source offer:** the kernel (GPL-2.0: the tree, our patches, the config, `kernel/devices/anybook`), e2fsprogs and f2fs-tools (GPL-2.0, in `system`), systemd-boot (LGPL-2.1+, on the ESP), libelf if Mesa links it (LGPL-3.0+). Ship a source tarball next to each image, or a written offer valid for 3 years | ✅ `scripts/release/make-sources.sh`: the kernel as built, every AOSP project whose binary carries a GPL/LGPL text (`notice-scan.py`), Mesa's libelf and Mesa, systemd-boot. First bundle: `0.1.0-preview.1`, 296 MB |
| 8 | **Nothing that may not be shipped:** no GMS, Google apps, SetupWizard, libhoudini, libndk_translation, Googlebook images, and no vendor blobs without a redistribution licence | ✅ none of these are in the build (`docs/installer.md` §6). The arm64 bridge is Digitalis, built from source (Apache-2.0) |
| 9 | **AVB release key and its custody:** who holds the key, and how images are signed with it | 🔒 open |
| 10 | **Repo licence** (Apache-2.0 suggested; our files already carry SPDX Apache-2.0) | 🔒 open |
| 11 | **"OpenBook" trademark check,** the use of "Android", and no "Googlebook" in names | 🔒 open |
| 12 | **Mesa libelf linkage** (shared library recommended, `docs/mesa.md`) | 🔒 open |
| 13 | **Known issues** listed with the release (§8) | ✅ draft |
| 14 | **Tested on the target hardware:** the live boot, the installer, and an install on the G14 | ✅ live boots and a whole-disk install on the G14's internal NVMe (2026-10-18). Each release adds its own smoke test on the laptop (`CONTRIBUTING.md`). An install to a spare drive needs the owner to name it by `/dev/disk/by-id` (`docs/installer.md` §13.7) |
| 15 | **User build:** a `user` (not `userdebug`) build signed with release keys | ⬜ after item 9 |
| 16 | **Distribution:** `scripts/release/make-release.sh` makes the `.img.xz` (xz -9), a hybrid torrent with web seeds, `SHA256SUMS(.sig)` and `release.json` with these gates; openbook.page's `publish-release.sh --from` and the seeder accept only releases whose gates pass ([`RELEASE.md`](RELEASE.md)) | ✅ tooling, tested on a 2026-10-18 live image; 🔒 the mirror (GitHub Releases or R2) and the router port forward for the seeder |
| 17 | **NVIDIA's GSP firmware under its distribution terms** (the Agreement's §1.1(d): unmodified, with the Agreement given to every recipient; the owner's decision of 2026-10-31, [`nvidia-open.md`](nvidia-open.md)) | ✅ `make-release.sh --nvidia-licence` checks every NVIDIA file against its pin and ships the Agreement with the download; openbook.page links it. `G14_NVIDIA_FIRMWARE=none` still builds an image without it. Apps on the RTX (NVK on NVIDIA's driver) stay out: GoodBook's `nvk-rm` needs a clean rewrite first |
| 18 | **The live stick boots to the end:** Android commits its checkpoint through the boot HAL when a boot completes | ✅ fixed 2026-10-31: live images built from 2026-10-18 until then restarted at the end of every boot |
| 19 | **adb asks before it lets a computer in** (`ro.adb.secure=1`): a debuggable PC build otherwise gives anyone on the network a root shell over tcp:5555 | ✅ 2026-10-31 (ANAL-320), and `make-release.sh` checks it (gate `adb_auth`, `docs/adb-debug.md` §5). `0.1.0-preview.1` shipped without it and was withdrawn the same day |
