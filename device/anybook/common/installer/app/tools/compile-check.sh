#!/usr/bin/env bash
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Compile-checks OpenBookInstaller outside Soong (ANAL-191): no lunch, no m, no lane lock.
#   1. Resolves the app's static_libs (read from ../Android.bp) and their transitive static_libs from the androidx
#      prebuilts' Android.bp files, and extracts classes.jar from each .aar.
#   2. aapt2 compile + link of res/ and AndroidManifest.xml against android.jar (validates resources and the
#      manifest, and generates R.java), then javac R.java.
#   3. kotlinc (external/kotlinc, with the Compose compiler plugin) over src/**/*.kt against the framework header
#      jar with hidden APIs (framework-minus-apex-headers turbine-combined) + android.jar + the androidx classes.
# Writes only under $OUT (default /tmp/ob191-app). Reads the AOSP tree at $AOSP (default ~/anybook/aosp/src).
#
# Usage: tools/compile-check.sh [--keep]   (--keep reuses the extracted library jars from a previous run)
set -euo pipefail

APP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AOSP="${AOSP:-$HOME/anybook/aosp/src}"
OUT="${OUT:-/tmp/ob191-app}"
KEEP=0
[[ "${1:-}" == "--keep" ]] && KEEP=1

export JAVA_HOME="$AOSP/prebuilts/jdk/jdk21/linux-x86"
export PATH="$JAVA_HOME/bin:$PATH"
KOTLINC="$AOSP/external/kotlinc"
COMPOSE_PLUGIN="$KOTLINC/lib/compose-compiler-plugin.jar"
ANDROID_JAR="$AOSP/prebuilts/sdk/current/system/android.jar"
M2="$AOSP/prebuilts/sdk/current/androidx/m2repository"

FRAMEWORK_JAR=""
for cand in \
    "$AOSP/out/soong/.intermediates/frameworks/base/framework-minus-apex-headers/android_common/turbine-combined/framework.jar" \
    "$AOSP/out/soong/.intermediates/frameworks/base/framework-minus-apex/android_common/combined/framework.jar"; do
  if [[ -f "$cand" ]]; then FRAMEWORK_JAR="$cand"; break; fi
done
if [[ -z "$FRAMEWORK_JAR" ]]; then
  echo "compile-check: no framework jar with hidden APIs under out/soong (build framework-minus-apex once)" >&2
  exit 2
fi

AAPT2=""
for cand in "$AOSP/out/host/linux-x86/bin/aapt2" "$AOSP/prebuilts/sdk/tools/linux/bin/aapt2"; do
  if [[ -x "$cand" ]]; then AAPT2="$cand"; break; fi
done

mkdir -p "$OUT"
case "$OUT" in /tmp/*) ;; *) echo "compile-check: OUT must be under /tmp" >&2; exit 2 ;; esac

# ---------------------------------------------------------------------------------------------------------------
# 1. Library classpath
# ---------------------------------------------------------------------------------------------------------------
LIBS="$OUT/libs"
if [[ $KEEP -eq 0 || ! -s "$OUT/classpath.txt" ]]; then
  rm -rf "$LIBS"
  mkdir -p "$LIBS"
  python3 -I - "$APP/Android.bp" "$M2" "$LIBS" "$KOTLINC/lib" > "$OUT/classpath.txt" <<'PY'
import os, re, sys, zipfile

app_bp, m2, libs, kotlin_lib = sys.argv[1:5]

def strip_comments(text):
    return re.sub(r"//[^\n]*", "", text)

def modules(text):
    """Yields (type, body) for each top-level Blueprint module."""
    text = strip_comments(text)
    for m in re.finditer(r"(\w+)\s*\{", text):
        depth, i = 1, m.end()
        while depth and i < len(text):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        yield m.group(1), text[m.end():i - 1]

def prop_list(body, name):
    m = re.search(r"\b%s\s*:\s*\[(.*?)\]" % name, body, re.S)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []

def prop_str(body, name):
    m = re.search(r'\b%s\s*:\s*"([^"]+)"' % name, body)
    return m.group(1) if m else None

index = {}
for root, _, files in os.walk(m2):
    if "Android.bp" not in files:
        continue
    with open(os.path.join(root, "Android.bp"), encoding="utf-8") as f:
        for mtype, body in modules(f.read()):
            name = prop_str(body, "name")
            if not name or mtype not in ("android_library_import", "java_import"):
                continue
            files_ = [os.path.join(root, a) for a in prop_list(body, "aars") + prop_list(body, "jars")]
            index[name] = (files_, prop_list(body, "static_libs") + prop_list(body, "libs"))

# Libraries that are not androidx prebuilts: map them to jars shipped with external/kotlinc.
kotlin_jars = {
    "kotlin-stdlib": ["kotlin-stdlib.jar"],
    "kotlin-stdlib-jdk7": ["kotlin-stdlib-jdk7.jar"],
    "kotlin-stdlib-jdk8": ["kotlin-stdlib-jdk8.jar"],
    "kotlin-reflect": ["kotlin-reflect.jar"],
    "kotlin-annotations": ["annotations-13.0.jar"],
    "kotlinx_coroutines": ["kotlinx-coroutines-core-jvm.jar"],
    "kotlinx-coroutines-core": ["kotlinx-coroutines-core-jvm.jar"],
    "kotlinx-coroutines-core-jvm": ["kotlinx-coroutines-core-jvm.jar"],
    # Only Dispatchers.Main's Android implementation (runtime, loaded through ServiceLoader): nothing to compile.
    "kotlinx_coroutines_android": [],
    "kotlinx-coroutines-android": [],
}

with open(app_bp, encoding="utf-8") as f:
    roots = []
    for mtype, body in modules(f.read()):
        if mtype == "android_app":
            roots += prop_list(body, "static_libs")

seen, order, missing = set(), [], []
stack = list(reversed(roots))
while stack:
    name = stack.pop()
    if name in seen:
        continue
    seen.add(name)
    if name in index:
        order.append(name)
        stack.extend(reversed(index[name][1]))
    elif name in kotlin_jars:
        order.append(name)
    else:
        missing.append(name)

cp = []
for name in order:
    if name in kotlin_jars:
        for j in kotlin_jars[name]:
            p = os.path.join(kotlin_lib, j)
            if os.path.exists(p) and p not in cp:
                cp.append(p)
        continue
    for src in index[name][0]:
        if src.endswith(".jar"):
            cp.append(src)
            continue
        with zipfile.ZipFile(src) as z:
            for entry in z.namelist():
                if entry == "classes.jar" or (entry.startswith("libs/") and entry.endswith(".jar")):
                    dst = os.path.join(libs, name + ("" if entry == "classes.jar" else "-" + os.path.basename(entry)[:-4]) + ".jar")
                    with open(dst, "wb") as out:
                        out.write(z.read(entry))
                    cp.append(dst)

for name in roots:
    if name not in index and name not in kotlin_jars:
        sys.exit("compile-check: static_libs entry %r is not an androidx prebuilt or a known kotlin jar" % name)
for name in missing:
    print("compile-check: note: transitive %s not resolved (not needed to compile)" % name, file=sys.stderr)
print("\n".join(cp))
PY
fi
CP_LIBS="$(paste -sd: "$OUT/classpath.txt")"
echo "compile-check: $(wc -l < "$OUT/classpath.txt") library jars on the classpath"

# ---------------------------------------------------------------------------------------------------------------
# 2. Resources and manifest (aapt2), R.java
# ---------------------------------------------------------------------------------------------------------------
rm -rf "$OUT/res-flat" "$OUT/gen" "$OUT/r-classes" "$OUT/classes"
mkdir -p "$OUT/res-flat" "$OUT/gen" "$OUT/r-classes" "$OUT/classes"
if [[ -n "$AAPT2" ]]; then
  "$AAPT2" compile --dir "$APP/res" -o "$OUT/res-flat/res.zip"
  "$AAPT2" link -I "$ANDROID_JAR" --manifest "$APP/AndroidManifest.xml" \
      --min-sdk-version 36 --target-sdk-version 37 --auto-add-overlay \
      --java "$OUT/gen" -o "$OUT/res-only.apk" "$OUT/res-flat/res.zip"
  echo "compile-check: aapt2 compile+link OK"
else
  echo "compile-check: aapt2 not found; cannot generate R.java" >&2
  exit 2
fi
javac -nowarn -source 17 -target 17 -cp "$ANDROID_JAR" -d "$OUT/r-classes" $(find "$OUT/gen" -name '*.java')

# ---------------------------------------------------------------------------------------------------------------
# 3. Kotlin
# ---------------------------------------------------------------------------------------------------------------
mapfile -t SRCS < <(find "$APP/src" -name '*.kt' | sort)
CP="$FRAMEWORK_JAR:$ANDROID_JAR:$OUT/r-classes:$CP_LIBS"
set +e
"$KOTLINC/bin/kotlinc" -no-jdk -no-stdlib -jvm-target 17 -language-version 2.2 \
    -Xplugin="$COMPOSE_PLUGIN" \
    -cp "$CP" -d "$OUT/classes" "${SRCS[@]}" 2>&1 | tee "$OUT/kotlinc.log"
rc=${PIPESTATUS[0]}
set -e
errors=$(grep -c '^.*: error:\|^error:' "$OUT/kotlinc.log" || true)
warnings=$(grep -c ': warning:\|^warning:' "$OUT/kotlinc.log" || true)
if [[ $rc -ne 0 || $errors -ne 0 ]]; then
  echo "compile-check: FAILED (kotlinc exit $rc, $errors errors, $warnings warnings; log: $OUT/kotlinc.log)"
  exit 1
fi
echo "compile-check: OK (${#SRCS[@]} Kotlin files, $(find "$OUT/classes" -name '*.class' | wc -l) classes, $warnings warnings, 0 errors)"
