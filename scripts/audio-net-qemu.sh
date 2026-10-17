#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# QEMU checks of the G14 product's Wi-Fi, Bluetooth and audio stack (ANAL-179, docs/g14-audio-net.md), with no laptop
# hardware: a QEMU HDA sound card whose output is recorded to a WAV file, and two mac80211_hwsim radios, one of them
# an access point (hostapd, a DHCP server, iperf3) in its own network namespace. Android uses the other as wlan0,
# with the same supplicant, framework and policy as on the G14; only the driver differs.
#
# usage: audio-net-qemu.sh snapshot NAME  reflink PRODUCT_OUT's images into <data dir>/audio-net/product/NAME, for
#                                         g14-image.sh and installer-image.sh --product-out: run it in the same
#                                         lane-lock hold as the build, since other branches build into the same tree
#        audio-net-qemu.sh payload        test disk for the guest -> <data dir>/audio-net/qemu/payload.img:
#                                         mac80211_hwsim with the cfg80211/mac80211 it was built with (virtual-device
#                                         dist, checked against our vmlinux), AOSP's hostapd and the libraries the
#                                         image lacks, a shim that lets it skip its AIDL registration,
#                                         openbook-test-dhcpd (NDK, static), run-ap.sh, hostapd.conf
#        audio-net-qemu.sh run IMG RUN    boot IMG (scripts/g14-image.sh) from a fresh copy with the sound card and
#                                         the test disk, run expect-g14-audio-net.json, then summarise:
#                                         <boot dir>/audio-out-tones.json (what reached the "speaker"),
#                                         <boot dir>/hwtest.json (the guest's HWTEST results)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/.." && pwd)
T=$R/scripts/qemu-test
W=$A/audio-net/qemu
AOSP=${AOSP_SRC:-$A/aosp/src}
P=$AOSP/out/target/product/anybook_g14
VDEV=${OPENBOOK_VDEV_DIST:-$A/kernel/dist/anybook-vdev-gbos-16302624}
G14=${OPENBOOK_G14_DIST:-$A/kernel/dist/anybook-g14-gbos-16302624}
HOSTAPD=$AOSP/out/soong/.intermediates/external/wpa_supplicant_8/hostapd/hostapd/android_vendor_x86_64_silvermont_cfi/hostapd

payload() {
  local S=$W/payload/openbook-qemu-test
  rm -rf "$W/payload"; mkdir -p "$S/mods" "$S/lib"
  for m in cfg80211 mac80211 mac80211_hwsim; do cp "$VDEV/$m.ko" "$S/mods/"; done
  python3 "$T/modversions-check.py" "$S/mods/cfg80211.ko" "$G14/vmlinux.symvers" "$G14/rfkill.ko"
  python3 "$T/modversions-check.py" "$S/mods/mac80211.ko" "$G14/vmlinux.symvers" "$S/mods/cfg80211.ko" "$G14/libarc4.ko"
  python3 "$T/modversions-check.py" "$S/mods/mac80211_hwsim.ko" "$G14/vmlinux.symvers" "$S/mods/cfg80211.ko" "$S/mods/mac80211.ko"
  [ -f "$HOSTAPD" ] || { echo "$HOSTAPD missing: build it with the product (docs/g14-audio-net.md)" >&2; exit 1; }
  cp "$HOSTAPD" "$S/hostapd"
  for lib in $(readelf -d "$HOSTAPD" | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p'); do
    [ -e "$P/vendor/lib64/$lib" ] || [ -e "$P/system/lib64/$lib" ] || [ -e "$P/system/apex/com.android.runtime/lib64/bionic/$lib" ] && continue
    case $lib in libc.so|libm.so|libdl.so) continue ;; esac
    f=$(find "$AOSP/out/soong/.intermediates" -path "*android_vendor_x86_64_silvermont_shared*/$lib" -not -path "*unstripped*" 2>/dev/null | head -1)
    [ -n "$f" ] || { echo "no vendor build of $lib for hostapd" >&2; exit 1; }
    cp "$f" "$S/lib/"; echo "hostapd needs $lib: $f"
  done
  mkdir -p "$W/build"
  docker run --rm -u "$(id -u):$(id -g)" -v "$T:/s:ro" -v "$W/build:/o" anybook-mesa-android \
    /opt/android-ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android35-clang -static -O2 -Wall -Werror \
    -o /o/openbook-test-dhcpd /s/openbook-test-dhcpd.c
  docker run --rm -u "$(id -u):$(id -g)" -v "$T:/s:ro" -v "$W/build:/o" anybook-mesa-android \
    /opt/android-ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android35-clang -shared -fPIC -O2 -Wall \
    -Werror -o /o/libopenbook-test-noaidl.so /s/openbook-test-noaidl.c
  cp "$W/build/libopenbook-test-noaidl.so" "$S/lib/"
  cp "$W/build/openbook-test-dhcpd" "$T/run-ap.sh" "$T/guest-test.sh" "$T/hostapd.conf" "$S/"
  # A plain tar written straight to the disk: the guest reads it with toybox tar from the block device, and vold
  # finds no filesystem to mount.
  tar --owner=0 --group=0 --numeric-owner --format=ustar --mtime=@0 --sort=name -C "$W/payload" \
    -cf "$W/payload.img" openbook-qemu-test
  truncate -s "%1M" "$W/payload.img"
  sha256sum "$W/payload.img"; tar -tvf "$W/payload.img"
}

run() {
  local IMG=${1:?usage: audio-net-qemu.sh run IMG RUN} RUN=${2:?run name}
  [ -f "$W/payload.img" ] || payload
  set +e
  QEMU_AUDIO=1 QEMU_EXTRA_USB=$W/payload.img "$R/scripts/g14-qemu.sh" "$IMG" "$RUN" "$R/scripts/installer/expect-g14-audio-net.json"
  local rc=$?
  set -e
  local O; O=$(ls -d "$A/logs/installer/$RUN"/boot* | sort -V | tail -1)
  [ -f "$O/audio-out.wav" ] && python3 "$T/wav-tone.py" "$O/audio-out.wav" > "$O/audio-out-tones.json" && cat "$O/audio-out-tones.json"
  python3 - "$O/serial.log" "$O/hwtest.json" <<'PY'
import json, re, sys
out = {}
for line in open(sys.argv[1], "rb").read().decode("utf-8", "replace").splitlines():
    m = re.search(r"HWTEST (\{.*\})\s*$", line)
    if m:
        try:
            o = json.loads(m.group(1)); out[o.get("test")] = o
        except ValueError:
            pass
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(json.dumps(out, indent=1))
PY
  return $rc
}

snapshot() {
  local O=$A/audio-net/product/${1:?usage: audio-net-qemu.sh snapshot NAME}
  rm -rf "$O"; mkdir -p "$O/system" "$O/vendor"
  for f in boot.img init_boot.img vendor_boot.img vbmeta.img super.img android-info.txt; do
    cp --reflink=auto --preserve=timestamps "$P/$f" "$O/"
  done
  cp --reflink=auto --preserve=timestamps "$P"/build_fingerprint*.txt "$O/" 2>/dev/null || true
  cp "$P/system/build.prop" "$O/system/"; cp "$P/vendor/build.prop" "$O/vendor/"
  echo "snapshot: $O ($(sed -n 's/^ro.build.fingerprint=//p' "$O/system/build.prop"))"
}

case ${1:-} in
  snapshot) shift; snapshot "$@" ;;
  payload) payload ;;
  run) shift; run "$@" ;;
  *) sed -n '2,/^set -euo/p' "$0" | sed '$d'; exit 2 ;;
esac
