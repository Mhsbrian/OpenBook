# QEMU run b (image openbook-g14-anal179-b, AnyBook b82282e): what failed, and the fixes in later commits

## 1. Every AudioTrack/AudioRecord got NO_INIT: the audio HAL may not write its own stream message queues (memfd, tmpfs type)
10-17 03:04:27.560   664   664 I auditd  : type=1400 audit(0.0:7): avc:  denied  { write } for  comm="android.hardwar" name="memfd:MessageQueue" dev="tmpfs" ino=7168 scontext=u:r:hal_audio_default:s0 tcontext=u:object_r:tmpfs:s0 tclass=file permissive=0
10-17 03:04:27.560   664   664 I auditd  : type=1400 audit(0.0:8): avc:  denied  { write } for  comm="android.hardwar" name="memfd:MessageQueue" dev="tmpfs" ino=7169 scontext=u:r:hal_audio_default:s0 tcontext=u:object_r:tmpfs:s0 tclass=file permissive=0
10-17 03:04:27.560   664   664 I auditd  : type=1400 audit(0.0:9): avc:  denied  { write } for  comm="android.hardwar" name="memfd:MessageQueue" dev="tmpfs" ino=7170 scontext=u:r:hal_audio_default:s0 tcontext=u:object_r:tmpfs:s0 tclass=file permissive=0
10-17 03:05:14.271   671   746 E AudioSystem: getInputForAttr error: Status(-8, EX_SERVICE_SPECIFIC): '-19: '
10-17 03:05:14.271   671   746 E AudioFlinger: createTrack() getOutputForAttr() return error -19 or invalid output handle
10-17 03:05:14.271  3896  3896 E AudioTrack: createTrack_l(0): AudioFlinger could not create track, status: -19 output 0

## 2. cfg80211's regulatory keyring: the kernel may not search it (labelled vendor_modprobe), so the signed database is rejected
[    3.305968] cfg80211: Loading compiled-in X.509 certificates for regulatory database
[    3.309853] cfg80211: loaded regulatory.db is malformed or signature is missing/invalid
[    3.309860] audit: type=1400 audit(1792206257.160:4): avc:  denied  { search } for  pid=27 comm="kworker/1:0" scontext=u:r:kernel:s0 tcontext=u:r:vendor_modprobe:s0 tclass=key permissive=0
[   62.263800] cfg80211: Loading compiled-in X.509 certificates for regulatory database

## 3. QEMU-only: the framework resolved nl80211's family before the test reloaded cfg80211 (fixed in the test by restarting the framework)
10-17 03:05:21.391   833  2603 I Nl80211Proxy: Received NLMSG_ERROR with error 2 for message GenericNetlinkMsg{ nlHeader{StructNlMsgHdr{ nlmsg_len{20}, nlmsg_type{30()}, nlmsg_flags{769(NLM_F_REQUEST|NLM_F_DUMP)}, nlmsg_seq{2}, nlmsg_pid{0} }}, genNlHeader{StructGenNlMsgHdr{ command{5}, version{1}, reserved{0} }}, attributes{[]} }
10-17 03:05:21.391   833  2603 E Nl80211Native: Failed to get interface info for wlan0

## 4. openbook-audio-setup could not write to /dev/kmsg_debug (userdebug stdio_to_kmsg)
[    3.865432] type=1400 audit(1792206257.716:5): avc:  denied  { write } for  comm="openbook-audio-" path="/dev/kmsg_debug" dev="tmpfs" ino=6 scontext=u:r:openbook_audio_setup:s0 tcontext=u:object_r:kmsg_debug_device:s0 tclass=chr_file permissive=0

## 5. HDA mixer at boot, before openbook-audio-setup ran (run a; QEMU HDA codec): master muted at 0
card 0 mixer 'HDA Intel':
  Master Playback Volume [INT] 0 0 (0..74)
  Master Playback Switch [BOOL] 0 0
  Capture Volume [INT] 0 0 (0..74)
  Capture Switch [BOOL] 0 0
