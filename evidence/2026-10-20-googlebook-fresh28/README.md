# Fresh28 installation and audio diagnostic evidence

All disks, TPM states, reports and screenshots here are disposable VM fixtures.
No physical USB/SSD write, owner data or headset call is represented.
Google system images and encryption-key blobs stay private.

- `install.json`: actual offline UI installs the reviewed image to a 1 TB NVMe
  fixture, boots Android, creates four metadata-encryption files and observes
  eight minutes. Source/decoy remain unchanged. The known VM system-server
  SIGSEGV/execmem class recurs; this is not a clean stability result.
- `storage.json`: the actual F2FS checker sees 949,692 MiB, matching the
  995,824,238,592-byte userdata partition. Separately, the diagnostic on
  Cuttlefish reproduces about 8 GiB StatFs data capacity alongside a 16 GB Android
  storage total. The actual absent laptop has not been measured.
- `reboot.json`: instrumented second boot without the USB, retaining newly
  generated encryption keys, disk-bound boot identity and the original fixture.
- `initial-reboot-missing-serial.json` and `normal-reboot-setup.png`: the initial
  serial detector reports no boot marker, but its screenshot shows Android setup.
  Boot-control correctly selected the existing normal `openbook-a.conf`, which
  disables serial output. The missing-entry hypothesis was wrong. The corrected
  test changes only that entry in a private clone to use the existing serial
  initrd; production boot files remain unchanged.
- `cancel.json`, `console.json`, `installer-console.png`: incorrect confirmation
  and ordinary keyboard cancellation leave the source, target and decoy unchanged.
  The console screenshot was visually reviewed.
- `unit-tests.log`: 15 migration/reset/integrity/power/interruption tests pass.
- `audio-app.json`, `audio-app.png`: signed APK tests cover foreground/background
  metadata capture, marker, stop, identical SAF export, denied Bluetooth
  permission and absence of an app crash. No physical radio or Teams test.
- `audio-policy.json`: policy extracted from the actual vendor image includes
  A2DP and LE Audio, lacks classic SCO routes, and the retained system already
  enables software HFP. This is a configuration gap, not a measured negotiation.
- `artifacts.json`: image, APK and embedded-installer source identities.

An intermediate proposed installer change based on the incorrect missing-entry
hypothesis was rejected by its source-pin guard before any target write. It is
not the delivered image. The final `migrate.py` hash matches the embedded source
in the original reviewed fresh28 artifact exactly.

See `docs/googlebook-fresh-install.md` and `docs/googlebook-audio-diagnostic.md`
for reproduction, primary sources, user flow and limitations.
