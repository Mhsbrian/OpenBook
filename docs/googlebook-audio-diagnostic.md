# Away-from-host Bluetooth audio investigation

2026-10-20: the owner reports intermittent call quality and use of the laptop
microphone with AirPods/Pixel Buds. Previous “Bluetooth works” acceptance covered
basic owner use, not headset microphone routing or call stability.

## Concrete finding and limits

### Returned call report, 2026-10-20

The owner's 57.823-second report has 19 complete route snapshots, with Bluetooth
permission granted and no API access error. HFP and A2DP remain connected in
every sampled state; HFP `audio_connected_count` remains zero and LE Audio is
disconnected. The only available communication device is the built-in speaker.
Nine recording observations show the unsilenced built-in microphone at 48 kHz.
An A2DP-playing event occurs 13.670 seconds into the capture. These observations
support the owner's account of earbud playback with no earbud microphone.
They establish a system-visible routing limitation, rather than merely a missing
entry in the Teams device selector.

Audio mode stays `MODE_NORMAL`. This does **not** establish whether the client
was Teams for Android or Teams in desktop Chrome. Similarly, the communication
device remaining “speaker” is not evidence contradicting the earbud playback:
that API is distinct from a media output selected by an app. Recording-app
identity is unavailable, and stable sampled profiles cannot exclude a transient
between samples.

The same physical report confirms `StatFs(/data)=8,587,837,440` bytes and
Android's advertised total of `16,000,000,000` bytes. Available app data was
784,199,680 bytes (about 748 MiB). The earlier 16 GB Settings report and actual
roughly 8 GiB filesystem are both explained by this direct measurement.

The owner also reports severe stuttering on internal speakers that disappeared
when switching playback to the earbuds. The APK records no PCM, AudioFlinger
underruns, ALSA errors, scheduling traces or controller packet statistics.
Therefore **no speaker-stutter root cause or fix is established by this report**.
The retained audio APEX contains the device-clocked pacing patch, and the earlier
October 19 laptop bug report has `vendor.audio.primary.pacing=false`, card 2,
device 0. Its absence is not supported as the explanation. This is historical
configuration evidence, not a new measurement during the failing call.

For the speaker issue, collect **Developer options → Take bug report** directly
after a short, non-sensitive speaker-call reproduction. Include whether Teams
ran in Chrome or as an Android app and whether ordinary speaker media playback
also stutters. Inspect AudioFlinger playback/record threads, HAL drop/pad counters,
ALSA errors, audio mode/routes and timestamps around the change of output.
Do not reset data or change codec timing merely on the basis of this report.

`audio-report.py` emits only aggregate observations/capacity from the private
JSONL. Five synthetic tests cover unavailable permissions, missing observations,
route transitions and exclusion of arbitrary identifier fields. Raw owner
reports remain outside Git.

### SCO policy candidate and the remaining USB transport gap

The candidate at
`device/anybook/common/pc/audio/bluetooth_with_le_audio_policy_configuration_7_0.xml`
adds three classic SCO output device types, one headset input, and their mix
routes to the existing A2DP/LE policy. It uses the Bluetooth module, never the
HDA primary PCM. The retained `DevicePortProxy` resamples 8/16/32 kHz HFP to
32 kHz at the framework boundary, with stereo output and mono input.

**This candidate is deliberately not wired into `pc.mk` or fresh28.** The
`openbook-hfp-hal-test` explicit test target creates synthetic Bluetooth providers
in a disposable Cuttlefish VM. With the exact retained APEX
`dca81a647aa21f6d91f2d7250b00a775b6ab6403cd040a2ded3ce49bcca2fa03`:

- Baseline fails because `IModule/bluetooth.getBluetooth()` returns null.
- Candidate exposes that interface and passes 12 cases: 8, 16 and 32 kHz HFP
  sessions, each with three output device variants and one microphone input.
- Each case establishes a provider session/FMQ descriptor, connects the device,
  negotiates port configurations, creates an audio patch, opens/closes a stream,
  resets the patch/configuration and disconnects. SELinux stays enforcing.
- There is **no PCM transfer, codec-quality, Bluetooth-stack, RF, controller,
  real-headset, Teams or Ruby-framework acceptance** in this test.

The initial harness used `ro.boot.hardware` as its Cuttlefish guard; that failed
before any policy change. It now checks the actual Cuttlefish `ro.product.board`
and repeats the complete baseline/candidate test. The native probe also enforces
a Cuttlefish-only guard. No probe is added to product packages.

Source review found a second integration requirement. The selected AIDL Bluetooth
HAL opens the controller with `HCI_CHANNEL_USER`. In that mode the kernel passes
incoming events to userspace and does not maintain the ordinary SCO connection
state that normally drives `btusb` isochronous endpoint selection.
The retained kernel has `HCI_DRV_PKT` (`0xf1`), discovery and
`BTUSB_HCI_DRV_OP_SWITCH_ALTSETTING` commands; the current default HAL/H4 parser
does not implement those commands or driver-event packets. Without an active
isochronous TX endpoint, `btusb` rejects SCO writes with `ENODEV`.
This is a source-level transport gap; the returned APK report cannot observe an
attempted SCO transfer or demonstrate that specific errno on the laptop.

The next implementation must cover driver capability discovery, validated USB
alternate-setting selection for the negotiated voice mode, private driver-reply
parsing, connection/disconnection/reset cleanup and errors/timeouts. Test the
wire protocol with synthetic sockets and then the actual MediaTek controller.
Do not blindly send `0xf1` through the current H4 parser or enable the policy
alone and call it a completed microphone fix. Also retain the previously observed
MediaTek warning about Enhanced Setup Synchronous Connection as a negotiation
test item, not an established cause of this call's stutter.

Primary source checked 2026-10-20:
[kernel btusb driver commands](https://android.googlesource.com/kernel/common/+/a7cce099450f8fc597a6ac215440666610895fb7/drivers/bluetooth/btusb.c).
Local kernel tree `fbfdd65b0fd1d020a560c54988cdccaec73a6b0a` contains the same driver
command path. Local AOSP hardware/interfaces source provenance is listed below.
Evidence and test commands: `evidence/2026-10-20-googlebook-hfp29/README.md`.

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
The exact earbud generation, firmware and Teams client are not yet measured.

A2DP is a playback profile. A headset microphone requires a working communication
path such as classic HFP/SCO or supported LE Audio. Selecting a playback device
alone does not establish a microphone route. Android's communication-device API
selects a matching input for the chosen output; a Teams/browser call must also
request/use the route. Another app should not force its choice during a call.
[Android communication routing guide](https://developer.android.com/develop/connectivity/bluetooth/ble-audio/audio-manager).

The policy/provider boundary is now covered by the tests above; the retained
Ruby Bluetooth stack, USB transport and MediaTek controller still require
integration and validation. Fresh28 deliberately carries no Bluetooth change.

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
