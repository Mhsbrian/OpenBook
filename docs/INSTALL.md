# Installing OpenBook

> **Draft, 2026-10-17. Not a public release.** OpenBook images are test builds: `userdebug`, signed with AOSP's public test keys, for the owner's ASUS ROG Zephyrus G14 (GA403WR). Nothing is published until the owner approves the release checklist below. The install has run only in virtual machines so far (`evidence/2026-10-17-installer-e2e/`). It has not run on the G14 yet.

OpenBook installs from a USB stick. The stick first boots OpenBook "live", without changing the laptop. You can try it, then install it onto the whole disk or into free space next to Windows.

## 1. What you need
- A laptop with UEFI firmware and an x86-64 AMD CPU. Today that means the G14 (Ryzen AI 9 HX 370, Radeon 890M). Other machines are untested.
- A USB stick of 4 GB or more. **Writing the image erases it.**
- A target disk of **64 GB or more**. Smaller disks are refused.
- Mains power during the install, or a battery at 50 % or more.
- To install next to Windows, about 64 GB of **unallocated** space on the same disk. OpenBook never shrinks or moves partitions, so free the space first in Windows Disk Management. Suspend BitLocker if it is on.
- **Secure Boot off.** The stick's loader is not signed for Secure Boot yet.

## 2. Write the stick
1. Check the download: `sha256sum -c openbook-live-<label>.sha256`.
2. Write it with `scripts/installer/write-stick.sh`. Name the stick by its `/dev/disk/by-id/usb-…` path, twice:
   ```bash
   OPENBOOK_WRITE_CONFIRM=/dev/disk/by-id/usb-<your stick> \
     scripts/installer/write-stick.sh openbook-live-<label>.img /dev/disk/by-id/usb-<your stick>
   ```
   The script refuses anything that isn't a removable USB disk named by `by-id`. It copies any OpenBook logs from the stick before it writes. It reads the stick back to verify, then powers it off. Unplug it when the script prints `stick powered off: safe to unplug`. Add `--dry-run` to run every check without writing.
3. Any tool that copies a raw image byte for byte should work, but only `write-stick.sh` has been tested, and other tools neither check the target nor keep the stick's logs.

## 3. Boot the stick
1. Plug in the stick, then power on holding **Esc** to open the G14's firmware boot menu, and pick the USB stick.
2. The OpenBook menu waits 10 seconds, then starts **"OpenBook"**:

| Entry | Use it for |
|---|---|
| OpenBook | The normal live session. Changes stay on the stick |
| OpenBook - save logs to this USB stick | Same session, but it saves logs to the stick and powers off by itself |
| OpenBook - safe graphics (Mesa GL, no ANGLE) | If the screen stays black or garbled |
| OpenBook - start fresh (erase this stick's saved data) | Throw away the live session's data and start again |
| OpenBook - serial console (virtual machines) | VMs only |
| Check entries ("power check", "ARM apps check", …) | Test sticks only. Each says how long it runs; they power off by themselves |

3. **The first boot after writing is slow** (about 30 s to the desktop on the G14, longer on a slow stick). Android unpacks itself onto the stick.

## 4. Try or install
The installer opens by itself on the live session. It has seven steps:
1. **Language.**
2. **Hardware check.** Shows what works on this laptop. **Save report to USB** writes it to the stick.
3. **Try or install.** *Try OpenBook* goes to the desktop and changes nothing. You can install later from the launcher's "Install OpenBook".
4. **Disk.** Every disk with its size, bus and current contents, plus its `by-id` name. The stick you booted from shows **In use** and can't be picked. Disks under 64 GB show **Can't be used**.
   - **Erase disk and install** uses the whole disk. Everything on it is erased.
   - **Install alongside** uses the largest free space. Existing partitions are not touched.
   - **View the plan** lists every write the install will make. The plan is read-only: nothing changes before step 5.
5. **Confirm.** Type the disk's name as shown, then press **Erase and install**.
6. **Install.** About 20 seconds in a VM; on real hardware it runs at the stick's read speed. **Show details** shows each step.
7. **Done.** Remove the stick and press **Restart now**.

**If the power fails or the stick is pulled during the install,** boot the stick again and run the install again. The installer writes in an order that leaves the disk in one of three states. You get the old partition table (if the cut came before anything was written), a blank disk, or a complete OpenBook. A half-written disk never boots: the boot entry is written last, after every byte has been read back and checked. This was tested by cutting the power at six points in every install step (§7).

## 5. First start
- **Whole disk:** the firmware finds OpenBook by itself through the standard fallback path (`EFI/BOOT/BOOTX64.EFI`).
- **Alongside Windows:** **OpenBook adds no entry to the firmware's boot menu** (known issue 1). Windows keeps booting by default. To start OpenBook, either:
  - open the firmware's boot menu and pick the disk's "OpenBook" file, or
  - add a boot option once in the firmware setup, pointing at `\EFI\OpenBook\systemd-bootx64.efi` on the disk's EFI partition. From then on, OpenBook's menu also lists Windows Boot Manager.
- **OpenBook setup** comes first: language, Wi-Fi, then a screen lock. There is no account step. After that you get the desktop.

## 6. Reinstall or remove
- **Reinstall:** boot the stick and choose **Erase disk and install** on the OpenBook disk. It gets a new disk ID, new partition IDs and a new serial number, and setup runs again. Your data on that disk is erased.
- **Alongside, a second time:** refused while the earlier OpenBook partitions are on the disk ("This disk already has Android partitions"). Erase the disk, or delete the OpenBook partitions and `EFI/OpenBook/` from Windows first.
- **Remove an alongside install:** in Windows, delete the OpenBook partitions (`xbootldr`, `misc`, `boot_a` … `userdata`) and the folder `EFI\OpenBook` on the EFI partition, and remove the firmware boot option if you added one.

## 7. What has been tested (2026-10-17)
All of this ran in QEMU/KVM with OVMF UEFI firmware, on image files, SELinux enforcing. Image `openbook-live-20261017-anal192c` (`main` at `3908b14`):

| Test | Result |
|---|---|
| End-to-end matrix (`scripts/installer/e2e-qemu.sh`) | **79/79** |
| — Alongside a Windows-like disk | Windows' partitions are byte-identical afterwards, and its EFI partition gains one file and passes `fsck`. The firmware still starts "Windows" (a stand-in boot manager) by default. With a boot option added, OpenBook starts and reaches setup and the desktop |
| — A 32 GB disk | Refused (too small), in the wizard and on the command line |
| — Power cut at 6 points of the install, each followed by a restart from the stick | Every cut left the old table, a blank disk or a complete install. The firmware started nothing from the incomplete ones. Every restart completed and verified |
| — The installed disk alone, and with the stick still plugged in | Boots from its own disk both times; the stick is left unchanged |
| — Reinstall over a used OpenBook | New disk and partition IDs and a new serial number. The old data is gone and setup runs again |
| Wizard end to end (`wizard-qemu.sh`) | **25/25** |
| Live stick matrix (`live-qemu.sh`) | **40/40** |

Details: `docs/installer.md` §13.

## 8. Known issues
1. **No firmware boot entry is created.** Our kernel lacks `CONFIG_EFIVAR_FS`. Whole-disk installs boot through the fallback path; alongside installs need the firmware step in §5. This is a decision for the kernel lane.
2. **An installed OpenBook offers to "set up" the installer stick if it's plugged in.** SystemUI shows "USB drive detected · Tap to set up", because Android can't read the stick's partition table. **Don't tap it**: setting it up formats the stick. The live session leaves its own stick alone (PR #52); the installed system doesn't yet.
3. **The wizard calls an installed OpenBook "Linux".** On a disk that already holds OpenBook, the disk bar says "Linux" and the tip mentions "OpenBook and Linux". OpenBook's own ext4 and f2fs partitions are counted as Linux. The install itself is right: erase works and alongside is refused.
4. **Slot B is blank** (`openbook-bootsync` isn't built yet). There are no over-the-air updates. To get a newer OpenBook, reinstall, which erases your data.
5. **Test keys.** Images are signed with AOSP's public test keys, so verified boot is "orange" (unlocked). They are not suitable for daily use or for anyone but the owner.
6. **Only English** in the installer and setup.
7. **On the G14:** deep sleep (S0i3) isn't reached yet (`docs/power-input.md`), and the dGPU is kept off (`dgpu_disable=1`; HDMI is dark).

## 9. Release checklist (draft; the owner approves before anything is published)

Status for `openbook-live-20261017-anal192c`. ✅ done, ⬜ open, 🔒 owner decision.

| # | Item | Status |
|---|---|---|
| 1 | **Image sha256** next to the image (`<label>.sha256`), and in the build record (`<label>.build.json`) with the repo commit, the inputs' hashes and the tool versions | ✅ `dd1ebe20…` (final, with the check add-ons); `ab0c5726…` before them. Build record: `evidence/2026-10-17-installer-e2e/image/` |
| 2 | **Reproducible image:** the same inputs, label and epoch give the same bytes | ✅ `anal192b` was rebuilt from its input snapshot byte for byte (`aba999e2…`, `image/reproducible-anal192b.txt`). The AOSP build itself is not checked for reproducibility |
| 3 | **Signature on the checksum file.** Plan: sign `<label>.sha256` with the OpenBook release key (`ssh-keygen -Y sign`, or minisign); publish the public key in the repo and on the release page. Users check with `ssh-keygen -Y verify` before `sha256sum -c` | ⬜ the plan is ready; there is no key yet (item 9) |
| 4 | **Install manifest signed** (S10 checks the stick's partitions against `MANIFEST.json`; the manifest itself isn't signed) | ⬜ needs the release key |
| 5 | **Firmware licences:** every linux-firmware file ships with its licence | ✅ the 6 licence files are in `/vendor/firmware` (amdgpu, amdnpu, mediatek, rtlwifi, cirrus, wireless-regdb), and the build reports 0 files without one. ⬜ `WHENCE` is not shipped yet. The plan (`docs/installer.md` §3.4) says it should be, next to the licences |
| 6 | **NOTICE** for the platform (Settings › Legal) | ✅ `system`, `vendor` and `product` each have `etc/NOTICE.xml.gz` |
| 7 | **GPL/LGPL source offer:** the kernel (GPL-2.0: the tree, our patches, the config, `kernel/devices/anybook`), e2fsprogs and f2fs-tools (GPL-2.0, in `system`), systemd-boot (LGPL-2.1+, on the ESP), libelf if Mesa links it (LGPL-3.0+). Ship a source tarball next to each image, or a written offer valid for 3 years | ⬜ needs a source-bundle script: exact commits, the tarball and its sha256 |
| 8 | **Nothing that may not be shipped:** no GMS, Google apps, SetupWizard, libhoudini, libndk_translation, Googlebook images, and no vendor blobs without a redistribution licence | ✅ none of these are in the build (`docs/installer.md` §6). The arm64 bridge is Digitalis, built from source (Apache-2.0) |
| 9 | **AVB release key and its custody:** who holds the key, and how images are signed with it | 🔒 open |
| 10 | **Repo licence** (Apache-2.0 suggested; our files already carry SPDX Apache-2.0) | 🔒 open |
| 11 | **"OpenBook" trademark check,** the use of "Android", and no "Googlebook" in names | 🔒 open |
| 12 | **Mesa libelf linkage** (shared library recommended, `docs/mesa.md`) | 🔒 open |
| 13 | **Known issues** listed with the release (§8) | ✅ draft |
| 14 | **Tested on the target hardware:** the live boot, the installer's dry run, and an install to a spare drive on the G14 | ⬜ the owner's checklist (`docs/installer.md` §13.6); the spare drive needs the owner to name it by `/dev/disk/by-id` |
| 15 | **User build:** a `user` (not `userdebug`) build signed with release keys | ⬜ after item 9 |
| 16 | **Distribution:** `scripts/release/make-release.sh` makes the `.img.xz` (xz -9), a hybrid torrent with web seeds, `SHA256SUMS(.sig)` and `release.json` with these gates; the seeder and the site index list only releases whose gates pass ([`RELEASE.md`](RELEASE.md)) | ✅ tooling, tested on `anal191i` (`evidence/2026-10-31-release-pipeline/`); 🔒 the mirror (GitHub Releases or R2) and the router port forward for the seeder |
| 17 | **No NVIDIA GSP firmware** in a public image (own-use terms, [`nvidia-open.md`](nvidia-open.md)); `make-release.sh` refuses an image that carries it | ⬜ needs a G14 product variant without it |
