#!/usr/bin/env bash
# Boot our own Cuttlefish build in Google's cuttlefish-orchestration container (no sudo: docker group + /dev/kvm),
# wait for sys.boot_completed, capture evidence, tear down.
#
# usage: cf-boot.sh [all|up|wait|capture|down]      (default: all = up, wait, capture, down)
#   up       start the container and `cvd create` the device from our build (out/ is mounted read-only)
#   wait     block until sys.boot_completed=1 (CF_BOOT_TIMEOUT, default 900 s)
#   capture  getprop, pm list features, dmesg, logcat, screencap, cvd fleet, Cuttlefish host logs
#   down     cvd reset, then remove the container (the container name is the cleanup handle)
# Env (defaults): CF_OUT=~/anybook/aosp/src/out  CF_DEVICE=vsoc_x86_64_only  CF_NAME=anybook-cf
#   CF_STAGE=~/anybook/aosp/cf/product (writable reflink copy of the images; recreated by `up`)
#   CF_IMAGE=cuttlefish-orchestration:1.56.0 (pinned)  CF_ADB_PORT=16520  CF_WEBRTC_PORT=11443 (127.0.0.1 only)
#   CF_HOST_TOOLS=packaged (cvd's Debian host tools, Google's default) | build (our out/host tools)
#   CF_LOGS=~/anybook/logs/aosp/cf-<ts> (cf-latest links to it)  CF_ARGS (extra launch_cvd flags, appended)  CF_KEEP=1 skips `down` in `all`
# While it runs: WebRTC at https://localhost:$CF_WEBRTC_PORT; adb via
#   docker exec anybook-cf /root/cvd-host/bin/adb -s 127.0.0.1:6520 shell
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}
OUT=${CF_OUT:-$A/aosp/src/out}; DEV=${CF_DEVICE:-vsoc_x86_64_only}; NAME=${CF_NAME:-anybook-cf}
IMG=${CF_IMAGE:-us-docker.pkg.dev/android-cuttlefish-artifacts/cuttlefish-orchestration/cuttlefish-orchestration:1.56.0@sha256:ecdb337615c719ed62e12593f7931a313d7c15a99a919e69fd87510e14a249e6}
# `up`/`all` start a new log dir and point cf-latest at it; the other steps reuse cf-latest.
LA=$A/logs/aosp
case ${1:-all} in
  up|all) L=${CF_LOGS:-$LA/cf-$(date -u +%Y%m%dT%H%M%SZ)}; mkdir -p "$L"; ln -sfn "$L" "$LA/cf-latest" ;;
  *) L=${CF_LOGS:-$(readlink -f "$LA/cf-latest")}; mkdir -p "$L" ;;
esac
# Same path as in the build container, so absolute symlinks under out/ still resolve. cvd writes into
# --host_path, so the host tools come from our cvd-host_package.tar.gz unpacked inside the container, never
# from out/ itself. cvd always links its packaged cvdalloc over ours, and because AOSP's host package ships
# etc/debian_substitution_marker, cvd 1.57 links *all* its packaged host tools (run_cvd, crosvm, webRTC, ...)
# over ours. CF_HOST_TOOLS=build deletes the marker so our own build's host tools run (cvdalloc excepted).
C_OUT=/aosp/src/out; C_PKG=$C_OUT/host/linux-x86/cvd-host_package.tar.gz; C_HOST=/root/cvd-host
# assemble_cvd also rewrites images in place (it de-sparses super.img), so the product files are staged as
# reflink copies (instant and free on btrfs, a plain copy elsewhere) in CF_STAGE, mounted at /cf/product.
STAGE=${CF_STAGE:-$A/aosp/cf/product}; C_PROD=/cf/product
SERIAL=127.0.0.1:6520   # what cvd fleet reports as adb_serial
stamp(){ echo "=== $(date -u +%FT%TZ) $*" | tee -a "$L/cf-boot.log"; }
cx(){ docker exec "$NAME" "$@"; }
adb_(){ docker exec -e PATH="$C_HOST/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" "$NAME" adb -s "$SERIAL" "$@"; }

up(){
  [ -f "$OUT/target/product/$DEV/boot.img" ] || { echo "no build at $OUT/target/product/$DEV" >&2; exit 1; }
  stamp "stage $OUT/target/product/$DEV -> $STAGE (top-level files, reflink)"
  rm -rf "$STAGE"; mkdir -p "$STAGE"
  find "$OUT/target/product/$DEV" -maxdepth 1 -type f -exec cp --reflink=auto -t "$STAGE" {} +
  stamp "up: $IMG"
  # seccomp=unconfined: Docker's default profile rejects socket(AF_VSOCK), and run_cvd's host-side vsock servers
  # (tombstones, adb, ...) need it ("Can't tombstone server socket"). No --privileged; only NET_ADMIN is added.
  docker run -d --name "$NAME" --hostname "$NAME" --security-opt seccomp=unconfined \
    --cap-add NET_ADMIN --device /dev/kvm --device /dev/net/tun --device /dev/vhost-net --device /dev/vhost-vsock \
    -p "127.0.0.1:${CF_ADB_PORT:-16520}:6520" -p "127.0.0.1:${CF_WEBRTC_PORT:-11443}:1443" \
    -v "$OUT:$C_OUT:ro" -v "$STAGE:$C_PROD" "$IMG" >/dev/null
  # run_services.sh starts host resources (bridges/taps) and the operator; wait for the operator.
  for _ in $(seq 60); do docker logs "$NAME" 2>&1 | grep -q 'Operator is listening' && break; sleep 1; done
  cx cvd version 2>&1 | tee -a "$L/cf-boot.log"
  stamp "unpack $(basename "$C_PKG") -> $C_HOST"
  cx sh -c "mkdir -p $C_HOST && tar -xzf $C_PKG -C $C_HOST"
  if [ "${CF_HOST_TOOLS:-packaged}" = build ]; then cx rm -f "$C_HOST/etc/debian_substitution_marker"; fi
  stamp "host tools: ${CF_HOST_TOOLS:-packaged}"
  # Defaults for the PC product: a laptop-sized display, software GPU (the container has no /dev/dri;
  # graphics are the next stage), 4 vCPUs, 8 GiB.
  # shellcheck disable=SC2206  # CF_ARGS is a flag list, split on purpose
  local args=(--x_res=1920 --y_res=1080 --dpi=160 --gpu_mode=guest_swiftshader --cpus=4 --memory_mb=8192
              --report_anonymous_usage_stats=n ${CF_ARGS:-})
  stamp "cvd create --host_path=$C_HOST --product_path=$C_PROD ${args[*]}"
  local t0; t0=$(date +%s)
  set +e
  timeout "${CF_BOOT_TIMEOUT:-900}" docker exec "$NAME" cvd create --host_path="$C_HOST" --product_path="$C_PROD" \
    "${args[@]}" 2>&1 | tee "$L/cvd-create.log"
  local rc=${PIPESTATUS[0]}; set -e
  stamp "cvd create exit $rc after $(( $(date +%s) - t0 )) s"
  echo "$t0" > "$L/.t0"
  return "$rc"
}

wait_boot(){
  local t0 deadline v=""; t0=$(cat "$L/.t0" 2>/dev/null || date +%s); deadline=$(( $(date +%s) + ${CF_BOOT_TIMEOUT:-900} ))
  stamp "wait for sys.boot_completed"
  cx sh -c "PATH=$C_HOST/bin:\$PATH adb connect $SERIAL" >/dev/null 2>&1 || true
  while [ "$(date +%s)" -lt "$deadline" ]; do
    v=$(adb_ shell getprop sys.boot_completed 2>/dev/null | tr -d '\r') || true
    [ "$v" = 1 ] && break
    sleep 5; cx sh -c "PATH=$C_HOST/bin:\$PATH adb connect $SERIAL" >/dev/null 2>&1 || true
  done
  stamp "sys.boot_completed=${v:-<none>} at +$(( $(date +%s) - t0 )) s from cvd create"
  [ "$v" = 1 ]
}

capture(){
  stamp "capture -> $L"
  cx cvd fleet > "$L/cvd-fleet.json" 2>&1 || true
  # Host tools cvd swapped for its own packaged ones (everything else is from our cvd-host_package).
  cx find "$C_HOST" -type l -lname '/usr/lib/cuttlefish-common/*' -printf '%P -> %l\n' > "$L/host-substitutions.txt" 2>&1 || true
  # Host-side Cuttlefish logs (launcher, kernel console, crosvm), wherever this cvd version put the instance.
  local d
  # shellcheck disable=SC2016  # expanded inside the container
  d=$(cx sh -c 'dirname "$(find / -xdev -name launcher.log -path "*cvd-1*" 2>/dev/null | head -1)"' || true)
  if [ -n "$d" ] && [ "$d" != . ]; then
    cx tar -C "$d" -czhf - . > "$L/cf-host-logs.tgz" 2>/dev/null || true
    cx sh -c "cat '$d/kernel.log'" > "$L/kernel.log" 2>/dev/null || true
  fi
  # Guest side, only if adb answers (a device that never booted would block wait-for-device forever).
  adb_ root >/dev/null 2>&1 || true; sleep 3
  if timeout 60 docker exec -e PATH="$C_HOST/bin:/usr/bin:/bin" "$NAME" adb -s "$SERIAL" wait-for-device; then
    adb_ shell getprop > "$L/getprop.txt"
    for p in sys.boot_completed ro.build.fingerprint ro.build.id ro.build.version.release ro.build.version.sdk \
             ro.build.type ro.build.characteristics ro.product.model ro.product.device ro.hardware \
             ro.product.cpu.abi ro.product.cpu.abilist ro.product.cpu.abilist64 ro.product.cpu.abilist32 \
             ro.dalvik.vm.native.bridge ro.enable.native.bridge.exec ro.dalvik.vm.isa.arm64 ro.dalvik.vm.isa.arm \
             ro.boot.hardware.gltransport ro.hardware.egl ro.hardware.vulkan ro.boot.verifiedbootstate \
             ro.kernel.version persist.sys.device_provisioned; do
      echo "[$p]: [$(adb_ shell getprop "$p" | tr -d '\r')]"
    done > "$L/props-summary.txt"
    adb_ shell uname -a > "$L/uname.txt"
    adb_ shell pm list features | sort > "$L/features.txt"
    adb_ shell 'wm size; wm density; dumpsys window displays | grep -iE "mDisplayId|init=|freeform|windowing" | head -20' \
      > "$L/display.txt" 2>&1 || true
    adb_ shell dmesg > "$L/dmesg.txt" 2>&1 || true
    adb_ logcat -d -b all > "$L/logcat.txt" 2>&1 || true
    adb_ logcat -d -b events -s boot_progress_start boot_progress_enable_screen sf_stop_bootanim wm_boot_animation_done \
      > "$L/boot-progress.txt" 2>&1 || true
    adb_ exec-out screencap -p > "$L/screen.png" 2>/dev/null || true
    file "$L/screen.png" | tee -a "$L/cf-boot.log"
    tee -a "$L/cf-boot.log" < "$L/props-summary.txt"
  else
    stamp "adb not reachable; host-side logs only"
  fi
}

down(){
  stamp "down"
  cx cvd reset -y > "$L/cvd-reset.log" 2>&1 || true
  docker rm -f "$NAME" >/dev/null 2>&1 || true
}

case ${1:-all} in
  up) up ;; wait) wait_boot ;; capture) capture ;; down) down ;;
  all) rc=0; up || rc=$?; [ "$rc" -ne 0 ] || wait_boot || rc=$?; capture || true; [ -n "${CF_KEEP:-}" ] || down
       stamp "all: exit $rc, logs in $L"; exit "$rc" ;;
  *) sed -n '2,16p' "$0"; exit 2 ;;
esac
