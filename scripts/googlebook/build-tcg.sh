#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run in the googlebook-tcg container through inst-docker.sh. Output is local.
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
W=${1:?usage: build-tcg.sh NEW_OR_EXISTING_BUILD_DIRECTORY}
COMMIT=4fc49f46dc95d4a27de2509e7fceb2931e91faeb
test -f /.dockerenv
for feature in gfni vpclmulqdq avx512_vnni avx512vl; do
  if ! grep -qw "$feature" /proc/cpuinfo; then
    echo "Native arithmetic oracle requires $feature; use a supported host." >&2
    exit 2
  fi
done
mkdir -p "$W"
if [ ! -d "$W/source" ]; then
  git clone --depth 1 --branch v11.1.2 https://github.com/qemu/qemu.git "$W/source"
fi
test "$(git -C "$W/source" rev-parse HEAD)" = "$COMMIT"
PATCH=$R/third_party/gbrunch/qemu11-gfni.patch
if git -C "$W/source" apply --check "$PATCH"; then
  git -C "$W/source" apply "$PATCH"
else
  git -C "$W/source" apply --reverse --check "$PATCH"
fi
# Check all tracked source bytes against HEAD plus exactly the reviewed patch.
# A reusable build directory must not silently incorporate unrelated local edits.
python3 - "$W/source" "$PATCH" <<'PY'
import os
from pathlib import Path
import subprocess
import sys
import tempfile
source, patch = map(lambda p: Path(p).resolve(), sys.argv[1:])
with tempfile.TemporaryDirectory(prefix="qemu-index-", dir=source.parent) as tmp:
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
    def git(*args):
        subprocess.run(["git", "-C", str(source), *args], env=env, check=True)
    git("read-tree", "HEAD")
    git("apply", "--cached", str(patch))
    git("diff", "--exit-code", "--quiet")
PY
mkdir -p "$W/build"
cd "$W/build"
"$W/source/configure" --target-list=x86_64-softmmu,x86_64-linux-user \
    --without-default-features --enable-tcg --enable-tools --disable-docs \
    --disable-rust --disable-werror --enable-pixman --enable-tpm
ninja -j8 qemu-system-x86_64 qemu-x86_64
gcc -O2 -static -mavx "$R/scripts/googlebook/vnni-probe.c" -o "$W/vnni-probe"
"$W/vnni-probe" > "$W/vnni-host.json"
"$W/build/qemu-x86_64" -cpu max "$W/vnni-probe" > "$W/vnni-tcg.json"
for name in gfni; do
  gcc -O2 -static "$R/third_party/gbrunch/test_$name.c" -o "$W/$name-test"
  "$W/$name-test" > "$W/$name-host.txt"
  "$W/build/qemu-x86_64" -cpu max "$W/$name-test" > "$W/$name-tcg.txt"
  diff -u "$W/$name-host.txt" "$W/$name-tcg.txt"
done
gcc -O2 -static "$R/third_party/gbrunch/test_vnni.c" -o "$W/vnni-native"
gcc -O2 -static -DEMULATED_AVX "$R/third_party/gbrunch/test_vnni.c" -o "$W/vnni-emulated"
"$W/vnni-native" > "$W/vnni-native.txt"
"$W/build/qemu-x86_64" -cpu max "$W/vnni-emulated" > "$W/vnni-emulated.txt"
diff -u "$W/vnni-native.txt" "$W/vnni-emulated.txt"
cat "$W/vnni-host.json" "$W/vnni-tcg.json"
