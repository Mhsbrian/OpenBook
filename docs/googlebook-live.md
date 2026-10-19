# Local Googlebook live-image research

2026-10-19, ANAL-228. This extends `googlebook-bringup.md` with a UEFI/USB
packager and an instruction-emulation lane. These are local research artifacts;
the installer Googlebook option remains unavailable. Generated images contain
retained recovery material and must stay local.

## Wi-Fi and audio follow-up

The owner now reports both fw10 entries reaching setup. The returned capture
confirms Radeon and network/amplifier firmware initialization. It ends at
66 seconds without a recorded connection attempt or completion marker.
Codec2 shared-buffer denials explain the captured failure to decode UI sounds;
the cause of the reported Wi-Fi join failure is not yet established.

The net18 vendor integration restores the existing OpenBook media queue policy
and overrides Ruby's unsupported MAC-randomization assumptions with a mutable
RRO. The activation service verifies the two effective values for system user
0; it does not change networks, credentials or the selected supplicant. Ruby's
system, system_ext and product image bytes remain unchanged. Strict SELinux
compilation and enforcing mode remain mandatory.

The final VM validation saves a complete 600.2-second capture, verifies both
Wi-Fi override values and the service's cached randomization setting, and
loads UI sounds without the previous Codec2 errors. ALSA inventory and service
dumps are readable through the corrected logger. It does not test a physical
Wi-Fi radio or audible speaker output. Earlier intermittent framework crashes
remain open. The final 660.6-second observation has one zygote exit and no
captured system-server fatal signal.

The owner's SanDisk now holds net18 (`74c5270b2c37b658…`), with matching full
12,766,412,800-byte readback and successful power-off. Prior logs and the used
image extent are preserved privately. See the latest `physical-write.json`.

Use **save detailed logs**, wait for setup, try connecting once, and note the
visible result. If setup becomes usable, test a media clip or sound preview;
the retained boot animation has no audio track, so silence there is inconclusive.
Keep this boot running for **12
minutes**, then shut down normally and return the stick. Diagnostics now include
Wi-Fi/connection state and effective resource values, ALSA inventory, audio
policy and AudioFlinger. No saved network XML or microphone samples are read.
Raw dumps still contain network identifiers and must remain private. See
`evidence/2026-10-19-googlebook-wifi-audio/` for evidence and validation limits.

## Black-screen capture on the USB

The owner reported a black screen after selecting the original live entry.
That candidate (`5b21c939…`) only had VM serial diagnostics; it did **not** save
logs to its ESP. Inspection found no saved reports. Its metadata partition was
initialized, but its bootstat and watchdog directories were empty. That is
evidence of Android initialization, not a diagnosis or successful desktop boot.
The complete used image extent was preserved privately before replacement.
The same SanDisk was first updated with diagnostic candidate
`19b9a9492f6b09bad04077378443d307f12ddd4a19f669e22486c88eb2b03f74`:
all 12,766,412,800 bytes read back correctly, and the stick was powered off.
The installed laptop and firmware were not updated. Validation and the exact
write/readback result are in `evidence/2026-10-19-googlebook-usb-logs/`.

The returned diagnostic capture now identifies the first physical blocker:
the research loader omitted `firmware_class.path=/vendor/firmware`. Radeon
initialization fails on firmware lookup before minigbm/EGL and SurfaceFlinger
fail. Wi-Fi, Bluetooth and XDNA firmware lookup fail too. The packagers now
preserve the actual `vendor_boot.img` command line, with a guard for that path.
After the owner's follow-up request, corrected candidate `048bacf5934bcd22…`
was written to the same SanDisk. All 12,766,412,800 bytes read back with matching
SHA-256; the stick was powered off and is ready for the next hardware trial.
The previous used image extent and all 160 reports are backed up privately.
See `evidence/2026-10-19-googlebook-g14-black-screen/physical-write.json`.

The new **Googlebook - save detailed logs to USB (10 minutes)** entry runs a
static PID 1 helper before Android, saving `early.txt` and `early-kernel.txt`.
An early-init vendor service then streams kernel records, and an Android shell
service supplies all logcat buffers plus repeated selected properties, processes,
mounts, memory, network and audio snapshots, with occasional display snapshots.
The collector also records the kernel command line and DRM nodes, and
keeps logcat alive independently of the snapshots. On the returned failing G14 boot,
the previous script stopped logcat normally at 272 seconds when those snapshots
finished; kernel records continued through 526 seconds without a completion
marker. That missing marker does not establish why the session ended.
No desktop interaction or network connection is needed. The alternate
**Googlebook - Mesa GL, save detailed logs to USB** entry changes the EGL path
and captures the same evidence. Neither entry changes the installed laptop.

Select the normal save-logs entry first, leave it running for **12 minutes**
even if the screen stays black, then shut down and return the stick to the
build host. It does not power off automatically. Files are on the readable FAT
partition under `openbook/logs/ruby-<boot-id>/`; `complete.txt` marks the end of
the timed capture and records any unsaved bytes or failed write attempts.
Early shutdown can leave an incomplete session. Keep each session together;
raw diagnostics can include device identifiers and should not be published
without review.

For the firmware-path regression, use the named **save detailed logs** entry;
the default experimental live entry does not persist diagnostics. Check the
welcome screen and keyboard/touchpad if they become available, then return the
stick after the full capture window. The next review must establish:

- The saved command line contains `firmware_class.path=/vendor/firmware`.
- Radeon firmware loads and amdgpu initializes instead of repeating the
  `-2` lookup failures; also check MT7925 and XDNA separately.
- Minigbm, EGL and SurfaceFlinger initialize, with no recurring graphics
  service crashes throughout the captured interval.
- Boot completion and the visible welcome screen agree; neither alone
  qualifies setup, accounts, applications or long-term stability.
- `complete.txt` records the capture's duration, overruns and write failures.
  If it is absent, retain the partial session and diagnose its stopping point.

The helper selects exactly one physical bootconfig PARTUUID, requires the EFI
partition on USB and the research-image marker, and opens only that partition.
It uses the existing crash-ordered FAT writer with short exclusive opens,
flushing chunks every five seconds. It never mounts the ESP, edits partitions,
grows or resets userdata, writes firmware variables, or prunes previous logs.
Sessions are capped at 48 MiB including the early-checkpoint allowance, with
32 MiB of free ESP space reserved. SELinux, neverallow checks and dm-verity stay
enforcing. The sink has its own vendor domain; diagnostic commands retain
shell-user permissions. The old permissive AOSP live logger is not reused.

An early checkpoint alone means the Android collector did not run successfully;
failure between that checkpoint and early-init can escape continuous capture.
No session can mean failure before PID 1, missing USB enumeration, insufficient
space or another logging failure. These files cannot capture firmware failures
before the kernel starts. Logs establish a boot stage and failure evidence;
they do not by themselves prove the desktop works.

Implementation follows the device-specific domain and file-label model in
[AOSP's SELinux implementation guide](https://source.android.com/docs/security/features/selinux/implement)
(checked 2026-10-19). Native policy and file-context checks remain mandatory.
The vendor packer retains applicable original platform defaults, including
`vendor_apex_file`, and checks critical labels to prevent an early APEX failure.

## Execution baseline

The 7950X cannot execute Ruby's VEX AVX-VNNI instructions. A separate container
builds QEMU v11.1.2 at `4fc49f46dc95d4a27de2509e7fceb2931e91faeb` with the
reviewed GBRUNCH patch from `a8936fd33e50efda3f1b36e332ab30b67b709ab1`.
The patch and its arithmetic tests are retained under `third_party/gbrunch/`
with their notices. It changes the emulator, not Google libraries or self-tests.

The exact formerly faulting instruction executes under TCG. The GFNI and
VPCLMULQDQ test digest matches the native host; the AVX-VNNI test digest matches
equivalent native AVX512-VNNI/VL operations. Each upstream arithmetic test uses
10,000 iterations. This validates those tests, not every instruction or a
physical AMD platform.

The existing OpenBook `tpm.ko` and `tpm_crb.ko` are retained. The probe restores
Ruby's exact `/dev/tpm* 0660 hsm hsm` ownership rule for its `gscd` service.
The audit now inventories `ueventd.rc` as well. A disposable software TPM can
exercise this interface in QEMU; it is not Google's security chip or a hardware
attestation result. Both QEMU and the TPM process are reaped before return.

Ruby's original `gscd_service` mapping is restored from its vendor service
contexts. Its type and permissions already exist in the retained framework.
`checkfc -s` validates the merged contexts against the strict compiled policy.
Seven other desktop service types exist only in Ruby's replaced vendor policy;
the check rejected those mappings, and they are deliberately excluded from this
profile. Their service registration remains an integration gap. No new policy
allow is added for these services.

## Live artifact contract

`live-image.py` takes a newly built **bare-metal** probe and creates a new regular
disk file. It verifies the six logical image hashes, kernel hash and AVB digest
against the probe recipe, then reads back every populated GPT partition. Its
ESP contains systemd-boot, normal and serial entries, and persistent logging
entries for normal graphics, Mesa GL, and VM serial diagnostics. The
normal entry is named `openbook-a.conf`, as required by the existing OpenBook
boot-control helper when Android marks slot A successful.

The bootconfig selects this disk by its ESP PARTUUID. It removes the VM's PCI
device path and keeps SELinux and dm-verity enforcing. Metadata and 8 GiB
encrypted userdata start blank on the image. There is no automatic partition
growth, reset menu, installer source manifest or physical disk writer here.
The research manifest uses its own schema and records `installable: false`.

`run-probe.py --uefi-usb` boots a private copy through OVMF and emulated USB3.
Only its menu default changes to the shipped serial entry. It attaches a
separate writable synthetic NVMe with identical Android partition names and
different UUIDs. Original input, test image and decoy hashes are checked after
the run. Guest writes to the USB normally use QEMU's disposable snapshot. With
`--usb-logs`, the harness selects the shipped serial+USB entry and retains writes
in its private copy, then extracts saved files after QEMU stops. The source
image and internal decoy must still remain unchanged. No physical
disk or host firmware variables enter the container, and the guest has no
network. USB keyboard and tablet match the existing OpenBook VM setup.
`--wake-display` records the screen before and after a wake key, so an idle
display is not mistaken for a rendering failure.

The probe emits periodic read-only diagnostics as Android's shell user. These
include boot completion, process/service lists, by-name links, mounts and logs.
Service-list queries can generate denied Binder calls; they do not grant access
to those services. A successful harness exit means the observation completed,
including an early guest reboot; it is not a desktop pass.

An earlier 495.4-second observation rendered the welcome screen and responded to
input, then `system_server` faulted with SIGSEGV/SEGV_ACCERR and zygote restarted.
Earlier RenderThread `execmem` denials implicate the VM's SwiftShader JIT path,
whose debug-only grant the strict Ruby user policy forbids. This is a hypothesis
pending a complete crash trace, not proof of a physical Radeon failure. Do not
restore the forbidden grant or disable neverallow checks. `mmd_setup` also aborts
because its expected zram disk-size node is absent. These remain stability gates.

## Reproduction

Use the retained Ruby tree, current G14 PRODUCT_OUT, matched G14 kernel dist,
AOSP host tools and public AVB test key described in `googlebook-bringup.md`.
Allow roughly 40 GiB scratch space per retained candidate plus the QEMU build,
8 GiB guest RAM and four vCPUs. Every output/run directory below must be new.
Set `REPO` to this checkout, `DATA` to the existing OpenBook data directory,
and `RUBY`, `PRODUCT`, `KERNEL`, `TOOLS`, `AOSP` to the existing build inputs.

```sh
docker build -t openbook-googlebook-tcg -f tools/Dockerfile.googlebook-tcg tools
export OPENBOOK_INSTALLER_IMAGE=openbook-googlebook-tcg
scripts/installer/inst-docker.sh bash "$REPO/scripts/googlebook/build-tcg.sh" \
  "$DATA/installer/work/ruby-tcg"

python3 scripts/googlebook/compat-test.py -v
python3 scripts/googlebook/live-test.py -v
scripts/installer/inst-docker.sh bash "$REPO/scripts/googlebook/usb-log-test.sh" \
  "$DATA/installer/work/ruby-log-unit-new"
python3 scripts/googlebook/compat-audit.py \
  --ruby "$RUBY" --product "$PRODUCT" --kernel "$KERNEL" --tools "$TOOLS" \
  --out "$AUDIT"
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/hybrid-probe.py" \
  --ruby "$RUBY" --product "$PRODUCT" --kernel "$KERNEL" --tools "$TOOLS" \
  --audit "$AUDIT" --key "$AOSP/external/avb/test/data/testkey_rsa4096.pem" \
  --out "$PROBE" --variant bm --prepare-only
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/live-image.py" \
  --probe "$PROBE" --out "$LIVE" --label ruby-live-local
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/run-probe.py" \
  --input "$LIVE" --out "$RUN" --uefi-usb --accel tcg --tpm --wake-display --timeout 480 \
  --qemu "$DATA/installer/work/ruby-tcg/build/qemu-system-x86_64"
```

For persistent capture, add `--usb-logs --usb-log-entry logs` and use a fresh
run directory with `--timeout 760`. This exercises the physical save-logs entry
without relying on a serial console. `--usb-log-entry safe-logs` tests the Mesa
GL alternative. Inspect the extracted session, including `complete.txt`, and
the recorded runtime failures; harness completion is not desktop qualification.

The native arithmetic oracle requires GFNI, VPCLMULQDQ and AVX512-VNNI/VL.
The 7950X has these; do not run that oracle on a host missing them. For the KVM
negative control, use the regular installer image, omit `--qemu`, select
`--accel kvm` and expect the known SIGILL failure on this host.

## Physical USB gate

The last recorded owner stick is a 62 GB SanDisk Ultra. No USB block device was
attached to the build host when this work began. A generated image is not an
updated stick, and an emulated USB boot is not a G14 test.

The owner subsequently attached that stick and explicitly requested its update
after the stability findings. The guarded writer backed up three old reports,
wrote the same tested candidate and verified all 12,766,412,800 bytes against
SHA-256 `5b21c93932dc39deb46b4462ebafcf17a943de93dbfd2d005d5233e142e66e1e`.
The stick was powered off successfully. This is a limited diagnostic trial,
not qualification or an installed-laptop update. The physical-write evidence
is in `evidence/2026-10-19-googlebook-usb/`.

The candidate reaches the graphical welcome screen in the enforcing VM but
fails the subsequent stability observation. It is not ready for a routine
live-USB handoff or a claim of working desktop/credential persistence. Before replacing
the stick, identify the connected whole device by `/dev/disk/by-id/usb-…`,
confirm recovery-use permission and obtain the exact-device confirmation
required by the workspace. Resolve the stability gate or explicitly agree on a
limited hardware diagnostic trial with these known failures. Reuse `scripts/installer/write-stick.sh`
for its identity checks, old-log backup and full readback; do not substitute an
unguarded `dd`. Its dry run does not write the device. No installed-laptop or
firmware update belongs to this USB workflow.

After the approved write and full readback, the first hardware trial should use
the firmware's one-time USB boot selection and the normal experimental live
entry. Do not install to internal storage. Capture whether the welcome screen
renders and whether keyboard/touchpad work before attempting setup. The
physical TPM, Radeon path, Wi-Fi and credential behavior remain unqualified.

### Original trial on the G14

These steps describe the original trial. For the reported black screen, use
the save-logs procedure at the top of this document.

1. Insert the verified stick and select its UEFI entry from the firmware's
   one-time boot menu. Select **Googlebook on OpenBook - experimental live boot**
   in the stick's menu (the default). The serial entry is for VM diagnostics.
2. Check the welcome screen, keyboard and touchpad first. A welcome screen is
   not evidence that setup, accounts or applications work. Record any black
   screen, restart or freeze, including roughly how long after boot it happened.
3. This image has fixed 8 GiB encrypted userdata on the stick and no OpenBook
   installer. The remaining stick capacity is not automatically allocated.
4. Shut the live system down before removing the stick. Select the laptop's
   existing OpenBook firmware entry on the next boot to return to its installed
   system. This procedure does not stage an OTA or select a different internal
   slot.

Evidence and current limitations are recorded in
`evidence/2026-10-19-googlebook-live/`. No recovery image or software-TPM state is
part of the repository or PR.
