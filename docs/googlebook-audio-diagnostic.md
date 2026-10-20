# Away-from-host Bluetooth audio investigation

2026-10-20: the owner reports intermittent call quality and use of the laptop
microphone with AirPods/Pixel Buds. Previous “Bluetooth works” acceptance covered
basic owner use, not headset microphone routing or call stability.

## Concrete finding and limits

The camera25/input27 vendor audio policy includes A2DP playback and LE Audio
ports, but **no classic SCO input or output ports/routes** in either primary or
Bluetooth modules. `audio-policy-audit.py` records the included file hashes and
route declarations. The retained Ruby system already sets
`bluetooth.hfp.software_datapath.enabled=true`; merely adding that property would
not repair this missing policy path.

This is a concrete integration gap consistent with classic Bluetooth earbuds
playing audio while the built-in microphone stays selected. It does not prove
which profile either named headset negotiated, nor that every dropout has the
same cause. LE Audio, HFP, controller/firmware resets, SCO transport, codec
negotiation, app routing and network-call quality must be distinguished.
The exact earbud generations, firmware and Teams client are not yet measured.

A2DP is a playback profile. A headset microphone requires a working communication
path such as classic HFP/SCO or supported LE Audio. Selecting a playback device
alone does not establish a microphone route. Android's communication-device API
selects a matching input for the chosen output; a Teams/browser call must also
request/use the route. Another app should not force its choice during a call.
[Android communication routing guide](https://developer.android.com/develop/connectivity/bluetooth/ble-audio/audio-manager).

The next platform correction is to add and validate compatible SCO input/output
policy and HAL routes, then verify the software HFP sessions with the retained
Ruby Bluetooth stack and MediaTek controller. AOSP's current AIDL audio modules
and provider factory implement HFP software encoding/decoding, but adding XML
alone is not an end-to-end acceptance test. Fresh28 deliberately carries no
unvalidated Bluetooth policy change.

## OpenBook Audio Check APK

The locally signed, open-source APK is built by
`bash scripts/googlebook/audio-diagnostic/build.sh`. It uses public APIs and has
no platform signature, root dependency, network permission or recording permission.
It does not capture microphone/call audio, device names/addresses, account data or
call contents. It does not change mode, audio focus or routing.

1. Install the attached `OpenBookAudioCheck.apk` and open it.
2. Start the diagnostic before connecting earbuds. Allow Nearby devices so it can
   inspect Bluetooth profile state; notification permission makes the running
   indicator easier to see. Denial still permits basic audio/storage observation.
3. Use the call app normally. When convenient, return and **Mark an audio problem**.
4. **Stop diagnostic**, then **Save report**. Attach the saved `.jsonl` file to the
   issue. Save a separate run for each headset and identify which was used in the
   accompanying message, since the app intentionally omits device names.

The foreground service samples every five seconds, records callbacks, and stops
after 30 minutes or its approximately 3 MiB budget. Starting another session
replaces the previous private report; export it first. Reports contain UTC and
elapsed times, connected audio device types/rates, available and selected
communication devices, audio mode, mute state, HFP/A2DP/LE profile state, and the
recording metadata Android makes visible to a normal app. The OS can anonymize or
withhold another app's recording information; an empty list is not proof that
Teams did not use a microphone.

It also records `/data` and system filesystem capacities plus Android's public
storage total. This separates the actual data capacity from Settings rounding.
Public API observation is not a full logcat/dumpsys/HCI capture. A sideloaded APK
does not gain system logging access just by requesting it.

For lower-level investigation away from the host, use **Developer options → Take
bug report** immediately after a short test call. Review it before sharing:
system reports may contain identifying information. If HCI capture becomes
necessary, enable Bluetooth HCI snoop logging before a test, reconnect Bluetooth,
capture the bug report afterward and turn logging off. Avoid recording a sensitive
work call for that purpose. The availability and placement of snoop files varies;
the Android bugreport route is preferred to guessing a file path.
[AOSP Bluetooth debugging](https://source.android.com/docs/core/connect/bluetooth/verifying_debugging).

## Validation and source provenance

Cuttlefish Android 17 runs the signed APK through launch, foreground capture,
background sampling, marker, stop, Storage Access Framework export and Bluetooth
permission denial. Exported report bytes equal the private report. No app crash
is observed. The interface screenshot is reviewed. There is no physical headset,
Teams call or controller-stability acceptance in this test.

The first harness attempt reached successful export, then failed to match the
permission dialog's curly apostrophe. The corrected harness reruns the complete
test successfully; this was a UI automation failure, not an APK crash.

- [AudioManager public API](https://developer.android.com/reference/android/media/AudioManager),
  checked 2026-10-20.
- AOSP frameworks/base revision `b5c6c45f5243c6f08ee3e21bf8a3a0aed4941fd6`.
- [AIDL Bluetooth audio port proxy](https://android.googlesource.com/platform/hardware/interfaces/+/d41643629491b67274c1c5092518adfab51a2ff9/audio/aidl/default/bluetooth/DevicePortProxy.cpp)
  and provider factory at the same hardware/interfaces revision.
- [HFP data-path selection](https://android.googlesource.com/platform/packages/modules/Bluetooth/+/c77db469de80f86660bc053bec4dee0c5d4b947c/system/stack/btm/btm_sco_hfp_hal.cc).

Only synthetic test reports and static policy summaries are committed. Raw owner
logs and any later system bug reports must stay private.
