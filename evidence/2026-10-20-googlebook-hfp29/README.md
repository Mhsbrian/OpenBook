# Call-route investigation and HFP policy boundary

2026-10-20, ANAL-228. No image or physical device changed. Fresh28 is still the
latest prepared installer candidate; it contains no HFP change.

`call-summary.json` is an allowlisted aggregate of the owner-supplied report.
Raw JSONL, wall-clock timestamps, build identifiers, device IDs and prior private
bug reports are excluded. This report captures connected HFP without SCO audio,
no Bluetooth communication route and built-in microphone recording. It does not
measure speaker underruns or radio packet loss.

`before.txt` / `after.txt` and `hal-test.json` are from synthetic Cuttlefish.
The audio APEX SHA matches camera25/input27/fresh28 exactly. The native client
uses real provider and audio-module Binder services with a fake Bluetooth stack:
it opens FMQ sessions and audio streams but never transfers PCM or accesses a
real controller. All 12 cases pass with enforcing SELinux after binding the
candidate XML; the original policy fails the SCO-interface check.

The XML is **not selected by pc.mk**. Source review found a further transport
requirement: HCI user-channel operation does not update the kernel connection
state normally used to select USB voice endpoints. Kernel driver commands exist,
but the current Bluetooth HAL/H4 parser does not implement their protocol.
`source-provenance.json` identifies the inspected files/binaries. This is not
proof of an observed radio error during the owner's call.

`report-tests.txt` contains five synthetic analysis/privacy regression checks.
`policy-regression.json` checks that every existing non-SCO policy element remains
identical when the new SCO nodes are removed. The actual parser and connection
tests are in the VM result.

Build/run outline (all commands from the repository; no physical adb address):

```bash
AOSP_JOBS=20 scripts/aosp-docker.sh /repo/scripts/aosp-build.sh \
  anybook_g14_x86_64-cp2a-userdebug openbook-hfp-hal-test
python3 scripts/googlebook/audio-report-test.py
python3 scripts/googlebook/audio-report.py /private/path/to/report.jsonl

export CF_NAME=openbook-audio-test-hfp-candidate
export CF_DEVICE=anybook_vsoc_x86_64
export CF_STAGE="$HOME/anybook/installer/work/unique-hfp-cf-product"
export CF_LOGS="$HOME/anybook/logs/aosp/unique-hfp-cf"
export CF_ADB_PORT=18529 CF_WEBRTC_PORT=11429 CF_ARGS=--vhost_user_vsock=true
trap 'scripts/cf-boot.sh down' EXIT
scripts/cf-boot.sh up
scripts/cf-boot.sh wait
python3 scripts/googlebook/audio-hal-cf.py --container "$CF_NAME" \
  --probe "$HOME/anybook/aosp/src/out/target/product/anybook_g14/data/nativetest64/vendor/openbook-hfp-hal-test/openbook-hfp-hal-test" \
  --policy device/anybook/common/pc/audio/bluetooth_with_le_audio_policy_configuration_7_0.xml \
  --out "$HOME/anybook/installer/work/unique-hfp-hal-result"
```

Use new private output/stage directories. The runner checks Cuttlefish's board,
the exact audio APEX and enforcing SELinux. It restores the policy bind in a
`finally` block; the outer trap stops/removes the owned VM container.

Validation history: two native-test link attempts identified missing transitive
static AIDL dependencies; the final explicit target builds successfully. The
first VM guard checked `ro.boot.hardware` rather than `ro.product.board` and
stopped before policy mutation. The corrected full baseline/candidate run passes.
These test-harness failures are not hardware results.
