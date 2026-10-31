#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Host test of openbook-live-init's disk logic (ANAL-190): grow, repair and reset on small GPT image files that
# have the live stick's layout. Runs in the openbook-installer container (sgdisk); image files only.
#
# usage: live-init-test.sh [BINARY]      default <data dir>/installer/build/openbook-live-init
# Prints one line per case and "N/N passed"; exits non-zero on any failure.
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
if [ -z "${OPENBOOK_IN_CONTAINER:-}" ]; then
  B=${1:-$A/installer/build/openbook-live-init}
  exec "$(dirname "$0")/inst-docker.sh" env OPENBOOK_IN_CONTAINER=1 bash "$(cd "$(dirname "$0")" && pwd)/live-init-test.sh" "$B"
fi
B=$1
T=$(mktemp -d -p "$A/installer/work" live-init-test.XXXXXX)
trap 'rm -rf "$T"' EXIT
ESP=0e1f4ac2-5d3c-4f7e-9a51-6f70656e6c69
pass=0; total=0
ok() { total=$((total + 1)); pass=$((pass + 1)); echo "PASS $1"; }
bad() { total=$((total + 1)); echo "FAIL $1"; }
mkimg() {  # mkimg FILE MiB: the live layout in miniature (EFI 8, misc 1, metadata 4, super 16, userdata rest)
  rm -f "$1"; truncate -s "$2M" "$1"
  sgdisk --clear -n 1:2048:+8M -t 1:ef00 -c 1:EFI -u 1:$ESP -n 2:0:+1M -c 2:misc -n 3:0:+4M -c 3:metadata \
    -n 4:0:+16M -c 4:super -n 5:0:0 -c 5:userdata "$1" >/dev/null
}
field() { python3 -c 'import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])' "$1" "$2"; }
ud_end() { sgdisk -i 5 "$1" | sed -n 's/^Last sector: \([0-9]*\).*/\1/p'; }

# 1. a stick 4x the image: backup GPT moves to the end, userdata grows to the last whole MiB
mkimg "$T/a.img" 64; truncate -s 256M "$T/a.img"
out=$("$B" --gpt-test "$T/a.img" $ESP)
if [ "$(field "$out" action)" = grow ] && sgdisk -v "$T/a.img" | grep -q 'No problems found' &&
   [ $(( ($(ud_end "$T/a.img") + 1) * 512 )) -le $((256 * 1048576 - 33 * 512)) ] &&
   [ $(( ($(ud_end "$T/a.img") + 1) * 512 )) -gt $((255 * 1048576 - 33 * 512)) ]; then ok "grow: $out"; else bad "grow: $out"; fi
# 2. the same stick again: nothing to do, image unchanged
h1=$(sha256sum < "$T/a.img"); out=$("$B" --gpt-test "$T/a.img" $ESP)
[ "$(field "$out" action)" = none ] && [ "$h1" = "$(sha256sum < "$T/a.img")" ] && ok "again: none" || bad "again: $out"
# 3. userdata in use on a larger stick: only the backup GPT moves
mkimg "$T/b.img" 64; s=$(sgdisk -i 5 "$T/b.img" | sed -n 's/^First sector: \([0-9]*\).*/\1/p')
printf 'not blank' | dd of="$T/b.img" bs=512 seek="$s" conv=notrunc status=none; truncate -s 128M "$T/b.img"
e0=$(ud_end "$T/b.img"); out=$("$B" --gpt-test "$T/b.img" $ESP)
[ "$(field "$out" action)" = repair ] && [ "$(ud_end "$T/b.img")" = "$e0" ] && sgdisk -v "$T/b.img" | grep -q 'No problems found' \
  && ok "repair: $out" || bad "repair: $out"
# 4. exact-size stick: nothing to do
mkimg "$T/c.img" 64; h1=$(sha256sum < "$T/c.img"); out=$("$B" --gpt-test "$T/c.img" $ESP)
[ "$(field "$out" action)" = none ] && [ "$h1" = "$(sha256sum < "$T/c.img")" ] && ok "exact: none" || bad "exact: $out"
# 5. a different ESP PARTUUID: refuse, unchanged
mkimg "$T/d.img" 64; truncate -s 128M "$T/d.img"; h1=$(sha256sum < "$T/d.img")
out=$("$B" --gpt-test "$T/d.img" 11111111-2222-3333-4444-555555555555 || true)
[ "$(field "$out" action)" = error ] && [ "$h1" = "$(sha256sum < "$T/d.img")" ] && ok "wrong ESP: refused" || bad "wrong ESP: $out"
# 6. userdata not last: refuse, unchanged
rm -f "$T/e.img"; truncate -s 64M "$T/e.img"
sgdisk --clear -n 1:2048:+8M -t 1:ef00 -c 1:EFI -u 1:$ESP -n 2:0:+4M -c 2:metadata -n 3:0:+16M -c 3:userdata \
  -n 4:0:0 -c 4:super "$T/e.img" >/dev/null; truncate -s 128M "$T/e.img"; h1=$(sha256sum < "$T/e.img")
out=$("$B" --gpt-test "$T/e.img" $ESP || true)
[ "$(field "$out" action)" = error ] && [ "$h1" = "$(sha256sum < "$T/e.img")" ] && ok "userdata not last: refused" || bad "not last: $out"
# 7. a stick smaller than the image (truncated write): refuse, unchanged
mkimg "$T/f.img" 64; truncate -s 48M "$T/f.img"; h1=$(sha256sum < "$T/f.img")
out=$("$B" --gpt-test "$T/f.img" $ESP || true)
[ "$(field "$out" action)" = error ] && [ "$h1" = "$(sha256sum < "$T/f.img")" ] && ok "short stick: refused" || bad "short: $out"
# 8. a corrupt primary GPT header: refuse, unchanged
mkimg "$T/g.img" 64; truncate -s 128M "$T/g.img"; printf 'X' | dd of="$T/g.img" bs=1 seek=$((512 + 40)) conv=notrunc status=none
h1=$(sha256sum < "$T/g.img"); out=$("$B" --gpt-test "$T/g.img" $ESP || true)
[ "$(field "$out" action)" = error ] && [ "$h1" = "$(sha256sum < "$T/g.img")" ] && ok "bad CRC: refused" || bad "bad CRC: $out"
# 9. reset: the first MiB of metadata and userdata is zeroed, nothing else changes
mkimg "$T/h.img" 64; truncate -s 128M "$T/h.img"; "$B" --gpt-test "$T/h.img" $ESP >/dev/null
python3 - "$T/h.img" <<'EOF'
import sys
f = open(sys.argv[1], "r+b"); f.seek(0, 2); n = f.tell()
for off in range(0, n, 1 << 20):  # fill every MiB that holds no GPT with 0xA5
    if off == 0 or off >= n - (1 << 20): continue
    f.seek(off); f.write(b"\xa5" * (1 << 20))
EOF
cp "$T/h.img" "$T/h0.img"; out=$("$B" --reset-test "$T/h.img")
python3 - "$T/h0.img" "$T/h.img" <<'EOF' && ok "reset: $out" || bad "reset: $out"
import subprocess, sys
a, b = open(sys.argv[1], "rb").read(), open(sys.argv[2], "rb").read()
def part(i):
    o = subprocess.run(["sgdisk", "-i", str(i), sys.argv[2]], capture_output=True, text=True).stdout
    return int(o.split("First sector: ")[1].split()[0]) * 512
zeroed = [(part(3), part(3) + (1 << 20)), (part(5), part(5) + (1 << 20))]
diff = [i for i in range(0, len(a), 4096) if a[i:i + 4096] != b[i:i + 4096]]
inside = all(any(s <= i < e for s, e in zeroed) for i in diff)
assert inside and all(b[s:e] == bytes(e - s) for s, e in zeroed), (len(diff), inside)
EOF
echo "$pass/$total passed"
[ "$pass" = "$total" ]
