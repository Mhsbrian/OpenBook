#!/bin/sh
# Print the GPUs in sysfs in anybook_gpu_probe's --list format, for machines that don't have the
# probe binary (a laptop's Linux install, the build host). POSIX sh: also runs under Android toybox.
# The output is a test fixture for device/anybook/common/graphics-amd/gpu_probe/testdata/.
#   scripts/gpu-probe-capture.sh [SYSFS]          (default /sys)
S=${1:-/sys}
ids(){ printf 'vendor=%s device=%s class=%s' "$(cat "$1/vendor" 2>/dev/null || echo 0x0000)" \
  "$(cat "$1/device" 2>/dev/null || echo 0x0000)" "$(cat "$1/class" 2>/dev/null || echo 0x000000)"; }
drv(){ d=$(readlink "$1/driver" 2>/dev/null) && basename "$d" || echo -; }
for c in "$S"/class/drm/card*; do
  n=${c##*/}; case $n in *-*|card) continue ;; esac
  dev=$(readlink -f "$c/device"); p=$dev
  while [ -n "$p" ] && [ "$p" != / ]; do
    case ${p##*/} in [0-9a-f][0-9a-f][0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f].[0-7]) break ;; esac
    p=${p%/*}
  done
  if [ -n "$p" ] && [ "$p" != / ]; then
    echo "drm $n driver=$(drv "$c/device") pci=${p##*/} $(ids "$p")"
  else
    echo "drm $n driver=$(drv "$c/device") pci=- vendor=0x0000 device=0x0000 class=0x000000"
  fi
done
for p in "$S"/bus/pci/devices/*; do
  case $(cat "$p/class") in 0x03*) echo "pci ${p##*/} driver=$(drv "$p") $(ids "$p")" ;; esac
done
