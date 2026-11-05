#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build Godot's TPS demo (code MIT, assets CC-BY 3.0, github.com/godotengine/tps-demo) as one Android APK carrying
# both arm64-v8a and x86_64 engine libraries, with an unattended benchmark (tps-demo/bench.gd, an autoload), for the
# ARM-translation corpus (ANAL-380, docs/arm-performance.md): a demanding 3D game, installed with --abi arm64-v8a
# (translated) and --abi x86_64 (native), the same bytes. Godot 4.7.2 (editor and export templates, checked against
# the release's SHA512-SUMS.txt) runs self-contained under ~/anybook/perf/godot, so nothing goes to the host's own
# Godot settings. Signed with a throwaway local key: a test package, never distributed.
#
# usage: build-tps-demo.sh      -> ~/anybook/perf/arm-corpus/tps-demo-fat.apk and its .sha256
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
HERE=$(cd "$(dirname "$0")" && pwd)
GV=4.7.2-stable
DEMO_COMMIT=a82f15448e9b015440d3bbdf5e10801b260c4e9f
G=$A/perf/godot
EDITOR=$G/editor/Godot_v${GV}_linux.x86_64
SRC=$G/tps-demo
W=$G/build
O=$A/perf/arm-corpus
SDK=$A/toolchain/openbook-update-sdk  # Godot wants build-tools and platform-tools in one SDK root
export JAVA_HOME=$A/toolchain/jdk-17.0.21
KS=$A/perf/keys/throwaway.jks

# Godot, self-contained (._sc_: its settings and export templates live in editor/editor_data).
if [ ! -x "$EDITOR" ]; then
  mkdir -p "$G/dl" "$G/editor/editor_data/export_templates"
  ( cd "$G/dl" && gh release download "$GV" -R godotengine/godot -p "Godot_v${GV}_linux.x86_64.zip" \
      -p "Godot_v${GV}_export_templates.tpz" -p SHA512-SUMS.txt --clobber &&
    grep -E "Godot_v${GV}_(linux.x86_64.zip|export_templates.tpz)$" SHA512-SUMS.txt | sha512sum -c - )
  ( cd "$G/editor" && unzip -o -q "../dl/Godot_v${GV}_linux.x86_64.zip" && touch ._sc_ )
  ( cd "$G/editor/editor_data/export_templates" && unzip -o -q "../../../dl/Godot_v${GV}_export_templates.tpz" &&
    mv templates "${GV/-/.}" )
fi
[ -d "$SRC/.git" ] || git clone -q https://github.com/godotengine/tps-demo.git "$SRC"
git -C "$SRC" -c advice.detachedHead=false checkout -q "$DEMO_COMMIT"
[ -z "$(git -C "$SRC" status --porcelain)" ] || { echo "build-tps-demo: $SRC has local changes" >&2; exit 2; }

# A copy of the demo with the benchmark: the autoload, ETC2/ASTC textures (Android needs them), no mouse capture while
# benchmarking, and an export preset.
rm -rf "$W"; mkdir -p "$W" "$O" "$(dirname "$KS")"
git -C "$SRC" archive HEAD | tar -x -C "$W"
cp "$HERE/tps-demo/bench.gd" "$W/bench.gd"
python3 - "$W/project.godot" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p).read()
s = s.replace('[autoload]\n\nSettings="*res://menu/settings.gd"\n',
              '[autoload]\n\nSettings="*res://menu/settings.gd"\nBench="*res://bench.gd"\n')
assert 'Bench="*res://bench.gd"' in s, "autoload section not as expected"
s = s.replace('[rendering]\n', '[rendering]\n\ntextures/vram_compression/import_etc2_astc=true\n', 1)
open(p, "w").write(s)
PY
# The player captures the mouse when it spawns. On real hardware pointer capture resets the input devices, which
# Android counts as user activity: the idle gate would stop every run. The benchmark flies its own camera and reads no
# input, so the capture is skipped while the Bench autoload is present.
python3 - "$W/player/player_input.gd" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
old = "\t\tInput.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)\n"
assert s.count(old) == 1, "player_input.gd's mouse capture not as expected"
s = s.replace(old, "\t\tif not has_node(^\"/root/Bench\"):  # OpenBook benchmark: no pointer capture\n"
                   "\t\t\tInput.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)\n")
open(p, "w").write(s)
PY
[ -f "$KS" ] || "$JAVA_HOME/bin/keytool" -genkeypair -keystore "$KS" -storepass android -keypass android \
  -alias test -keyalg RSA -keysize 2048 -validity 3650 -dname "CN=OpenBook ARM corpus local test build" >/dev/null 2>&1
# app_category 9 is "Undefined": not a game, so Android's default frame-rate override for games (60 fps on this
# image, ro.surface_flinger.game_default_frame_rate_override) doesn't cap the benchmark.
cat > "$W/export_presets.cfg" <<CFG
[preset.0]

name="Android"
platform="Android"
runnable=true
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path="$O/tps-demo-fat.apk"

[preset.0.options]

gradle_build/use_gradle_build=false
architectures/armeabi-v7a=false
architectures/arm64-v8a=true
architectures/x86=false
architectures/x86_64=true
keystore/release="$KS"
keystore/release_user="test"
keystore/release_password="android"
version/code=1
version/name="1.0"
package/unique_name="org.openbook.bench.tpsdemo"
package/app_category=9
package/name="TPS demo (OpenBook bench)"
screen/immersive_mode=true
CFG
cat > "$G/editor/editor_data/editor_settings-4.7.tres" <<CFG
[gd_resource type="EditorSettings" format=3]

[resource]
export/android/android_sdk_path = "$SDK"
export/android/java_sdk_path = "$JAVA_HOME"
CFG

"$EDITOR" --headless --path "$W" --import > "$W/import.log" 2>&1 || { tail -30 "$W/import.log" >&2; exit 1; }
"$EDITOR" --headless --path "$W" --export-release "Android" "$O/tps-demo-fat.apk" > "$W/export.log" 2>&1 ||
  { tail -40 "$W/export.log" >&2; exit 1; }
unzip -l "$O/tps-demo-fat.apk" | awk '{print $NF}' | grep '^lib/' | sort
( cd "$O" && sha256sum tps-demo-fat.apk | tee tps-demo-fat.apk.sha256 )
