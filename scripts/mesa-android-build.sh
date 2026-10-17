#!/usr/bin/env bash
# Out-of-tree Android x86_64 build of Mesa radeonsi (EGL/GLES) + RADV (Vulkan) with the NDK,
# following https://docs.mesa3d.org/android.html. Resumable and version-pinned: every step is
# skipped when its output already exists, and `ninja` resumes, so just rerun after a timeout.
#
#   scripts/mesa-android-build.sh [step ...] [-- tree ...]
#     steps: fetch deps setup build install verify isa   (default: all, in that order)
#     trees: upstream ag                                  (default: both)
#
# Runs on the host and re-executes itself inside the anybook-mesa-android image
# (tools/Dockerfile.mesa-android); the `isa` step uses anybook-inspect (elfx86exts).
# Sources, builds and artifacts live in ~/anybook/mesa, logs in ~/anybook/logs/mesa.
# Env: STEP_TIMEOUT (s, per step, default 3000), JOBS (default nproc), API (default 37),
#      CCACHE_DISABLE=1 for a clean compile,
#      LIBELF=shared|static (default shared): how radeonsi gets libelf (LGPL-3.0+, docs/mesa.md).
#        shared ships it as lib64/libelf_mesa.so (the recommended option until the owner decides);
#        static links it into libgallium_dri.so as ANAL-173 did. Changing it re-runs setup.
#      ANDROID_STRICT=true|false (default true, Mesa's default): RADV reports Vulkan 1.1 on Android
#        when true (CTS-safe), 1.4 when false. Changing it re-runs setup.
set -euo pipefail

# ---- pins -------------------------------------------------------------------------------
declare -A URL=([upstream]=https://gitlab.freedesktop.org/mesa/mesa.git
                [ag]=https://github.com/Android-Generic/external_mesa.git)
declare -A REF=([upstream]=mesa-26.2.5 [ag]=26.0/main)
declare -A SHA=([upstream]=ddaf85e353442d9d7f192fdcf1823e652e3f2ee3   # tag mesa-26.2.5
                [ag]=b14bf42d23ef1f9625eddb005cd568ab3873f11d)        # 26.0/main, 2026-09-30
AG_BASE=mesa-26.0.8   # upstream tag AG's 26.0/main is based on (merge-base 60e95b78)
# radeonsi needs libelf, which the NDK lacks: build AOSP's own elfutils (0.193) the way its
# Android.bp builds `libelf` (+ `libeu`), minus zstd. LGPL-3.0-or-later (docs/mesa.md): built both
# as libelf.a and as libelf_mesa.so (its own SONAME, so it can't clash with an AOSP libelf.so).
ELFUTILS_URL=https://android.googlesource.com/platform/external/elfutils
ELFUTILS_REF=android-17.0.0_r1; ELFUTILS_SHA=219c3a368b121307f2e05593cee89b8591cc40b9
API=${API:-37}; STEP_TIMEOUT=${STEP_TIMEOUT:-3000}; LIBELF=${LIBELF:-shared}; ANDROID_STRICT=${ANDROID_STRICT:-true}
IMAGE=anybook-mesa-android

# --datadir=etc: libdrm_amdgpu's compiled-in marketing-name table becomes /vendor/etc/libdrm/amdgpu.ids
# (AOSP keeps vendor data under /vendor/etc; Soong has no module type that installs to /vendor/share).
MESON_OPTS=(
  --buildtype=release -Db_ndebug=true --prefix=/vendor --libdir=lib64 --datadir=etc
  -Dplatforms=android -Dplatform-sdk-version="$API" -Dandroid-stub=true
  -Dandroid-libbacktrace=disabled -Dandroid-strict="$ANDROID_STRICT"
  -Dgallium-drivers=radeonsi -Dvulkan-drivers=amd
  -Dllvm=disabled -Damd-use-llvm=false          # ACO for both radeonsi and RADV; no Android LLVM
  -Degl=enabled -Dgles1=enabled -Dgles2=enabled -Degl-lib-suffix=_mesa -Dgles-lib-suffix=_mesa
  -Dgbm=enabled                                  # libgbm_mesa.so + gbm/dri_gbm.so: minigbm's amdgpu backend allocates through it
  -Dglx=disabled -Dgallium-va=disabled -Dvideo-codecs=
  -Dallow-fallback-for=libdrm
  -Dxmlconfig=disabled -Dexpat=disabled -Dzstd=disabled -Dvalgrind=disabled -Dlibunwind=disabled -Dlmsensors=disabled
  -Dbuild-tests=false -Dtools=
)

steps=(); trees=()
while (($#)); do [[ $1 == -- ]] && { shift; trees=("$@"); break; }; steps+=("$1"); shift; done
((${#steps[@]})) || steps=(fetch deps setup build install verify isa)
((${#trees[@]})) || trees=(upstream ag)

# ---- host side: run container steps, then the isa step --------------------------------
if [[ ! -d /opt/android-ndk ]]; then
  A=${ANYBOOK_HOME:-$HOME/anybook}; repo=$(cd "$(dirname "$0")/.." && pwd)
  mkdir -p "$A/mesa"/{src,build,out,ccache,evidence,home} "$A/logs/mesa"
  cstep=(); want_isa=0
  for s in "${steps[@]}"; do [[ $s == isa ]] && want_isa=1 || cstep+=("$s"); done
  if ((${#cstep[@]})); then
    docker run --rm -u "$(id -u):$(id -g)" -e HOME=/a/mesa/home -e CCACHE_DIR=/a/mesa/ccache \
      -e STEP_TIMEOUT -e JOBS -e API -e CCACHE_DISABLE -e LIBELF -e ANDROID_STRICT -v "$A/mesa:/a/mesa" -v "$A/logs/mesa:/a/logs" -v "$repo:/repo:ro" \
      "$IMAGE" /repo/scripts/mesa-android-build.sh "${cstep[@]}" -- "${trees[@]}"
  fi
  if ((want_isa)); then
    for t in "${trees[@]}"; do
      mkdir -p "$A/mesa/evidence/$t"
      docker run --rm -u "$(id -u):$(id -g)" -v "$A/mesa:/a/mesa" anybook-inspect sh -c '
        cd /a/mesa/out/'"$t"'/vendor && find . -name "*.so" | sort | while read -r f; do
          echo "== $f"; elfx86exts "$f" | sed -n "/^Instruction set extensions used/,\$p"; done' \
        > "$A/mesa/evidence/$t/isa-elfx86exts.txt"
      echo "isa: $t -> $A/mesa/evidence/$t/isa-elfx86exts.txt"
    done
  fi
  exit 0
fi

# ---- container side ---------------------------------------------------------------------
M=/a/mesa; L=/a/logs; NDK=/opt/android-ndk; TC=$NDK/toolchains/llvm/prebuilt/linux-x86_64
SYSLIB=$TC/sysroot/usr/lib/x86_64-linux-android/$API
JOBS=${JOBS:-$(nproc)}; DEPS=$M/deps/x86_64-api$API
export PKG_CONFIG_LIBDIR=$DEPS/lib/pkgconfig   # only our cross-built deps, never build-host .pc files
log(){ echo "[$(date -u +%FT%TZ)] $*"; }
run(){ local name=$1; shift; log "$name: $*" | tee -a "$L/$name.log"
       timeout "$STEP_TIMEOUT" "$@" 2>&1 | tee -a "$L/$name.log"; }

fetch(){ local t=$1 d=$M/src/$1
  [[ -d $d/.git ]] || { git init -q "$d"; git -C "$d" remote add origin "${URL[$t]}"; }
  if ! git -C "$d" cat-file -e "${SHA[$t]}^{commit}" 2>/dev/null; then
    run "$t-fetch" git -C "$d" fetch --filter=blob:none origin "${REF[$t]}" ||
    run "$t-fetch" git -C "$d" fetch --filter=blob:none origin "${SHA[$t]}"
  fi
  # OpenBook's patches (mesa/patches/<tree>/*.patch) on top of the pin, applied with git am, a fixed
  # committer and date, so the patched HEAD is reproducible. Skipped when HEAD already carries them.
  local p=/repo/mesa/patches/$t want have
  want=$(cat "$p"/*.patch 2>/dev/null | git patch-id --stable | cut -d' ' -f1)
  have=$(git -C "$d" log --reverse -p --format='commit %H' "${SHA[$t]}..HEAD" 2>/dev/null | git patch-id --stable | cut -d' ' -f1)
  if [[ $want != "$have" ]] || ! git -C "$d" diff --quiet HEAD; then
    git -C "$d" checkout -q -f --detach "${SHA[$t]}"
    for f in "$p"/*.patch; do
      [[ -e $f ]] || continue
      GIT_COMMITTER_NAME="OpenBook mesa-android-build.sh" GIT_COMMITTER_EMAIL=noreply@openbook.invalid \
        GIT_COMMITTER_DATE=2026-10-17T00:00:00+00:00 git -C "$d" am -q "$f"
    done
  fi
  log "fetch: $t at $(git -C "$d" rev-parse HEAD) ($(cat "$d/VERSION")), ${SHA[$t]:0:12} + $(git -C "$d" rev-list --count "${SHA[$t]}..HEAD") patches"
  if [[ $t == ag ]]; then   # record what AG carries on top of upstream
    git -C "$d" cat-file -e "$AG_BASE^{commit}" 2>/dev/null ||
      run ag-fetch git -C "$d" fetch --filter=blob:none "${URL[upstream]}" tag "$AG_BASE"
    mkdir -p "$M/evidence/ag"
    { echo "# Android-Generic external_mesa ${REF[ag]} ${SHA[ag]} vs upstream $AG_BASE"
      echo "# merge-base: $(git -C "$d" merge-base HEAD "$AG_BASE")"
      git -C "$d" log --reverse --no-merges --format='%h %ad %an: %s' --date=short "$AG_BASE..HEAD"
      echo; git -C "$d" diff --stat=120 "$AG_BASE" HEAD | tail -1
    } > "$M/evidence/ag/ag-patches.txt"
  fi
}

deps(){ local d=$M/src/deps/elfutils o=$M/build/deps/elfutils
  [[ -f $DEPS/lib/libelf.a && -f $DEPS/lib/libelf_mesa.so ]] && { log "deps: libelf already built ($DEPS)"; return; }
  [[ -d $d/.git ]] || { git init -q "$d"; git -C "$d" remote add origin "$ELFUTILS_URL"; }
  git -C "$d" cat-file -e "$ELFUTILS_SHA^{commit}" 2>/dev/null ||
    run deps-fetch git -C "$d" fetch --depth 1 origin tag "$ELFUTILS_REF"
  git -C "$d" checkout -q --detach "$ELFUTILS_SHA"
  rm -rf "$o"; mkdir -p "$o/obj" "$DEPS"/{include,lib/pkgconfig}
  sed '/USE_ZSTD/d' "$d/config.h" > "$o/config.h"   # NDK has no libzstd; zlib stays on
  local cc=("$TC/bin/x86_64-linux-android$API-clang" -O2 -fPIC -DHAVE_CONFIG_H -D_GNU_SOURCE -DNMNES=1000
            -std=gnu99 -D_FILE_OFFSET_BITS=64 -Wno-pointer-arith -Wno-typedef-redefinition
            -include AndroidFixup.h -I"$o" -I"$d" -I"$d/include" -I"$d/lib" -I"$d/bionic-fixup" -I"$d/libelf")
  local f
  for f in "$d"/libelf/*.c "$d"/lib/{crc32_file,error,eu-search,next_prime,xasprintf,xmalloc,xstrdup,xstrndup}.c; do
    echo "${cc[*]} -c $f -o $o/obj/$(basename "$f" .c).o"
  done > "$o/commands.sh"
  run deps-build xargs -P "$JOBS" -d '\n' -I{} sh -c '{}' < "$o/commands.sh"
  rm -f "$DEPS/lib/libelf.a"; "$TC/bin/llvm-ar" rcs "$DEPS/lib/libelf.a" "$o"/obj/*.o
  "$TC/bin/x86_64-linux-android$API-clang" -shared -fuse-ld=lld -Wl,-soname,libelf_mesa.so -Wl,--no-undefined \
    -o "$DEPS/lib/libelf_mesa.so" "$o"/obj/*.o -lz
  cp "$d"/libelf/{libelf.h,gelf.h,nlist.h,elf.h} "$DEPS/include/"
  sed -n 's/^#define VERSION "\(.*\)"/\1/p' "$d/config.h" > "$DEPS/libelf.version"
  log "deps: libelf $(cat "$DEPS/libelf.version"), $(ls "$o"/obj | wc -l) objects -> $DEPS/lib/libelf.a, libelf_mesa.so"
}

# libelf.pc for the selected LIBELF mode (static: libelf.a + zlib; shared: libelf_mesa.so).
libelf_pc(){ local lib; case $LIBELF in static) lib='-lelf -lz' ;; shared) lib='-lelf_mesa' ;;
    *) echo "LIBELF must be shared or static, not '$LIBELF'" >&2; exit 2 ;; esac
  printf '%s\n' "prefix=$DEPS" "Name: libelf" "Description: elfutils libelf ($ELFUTILS_REF), $LIBELF" \
    "Version: $(cat "$DEPS/libelf.version")" "Libs: -L\${prefix}/lib $lib" 'Cflags: -I${prefix}/include' \
    > "$DEPS/lib/pkgconfig/libelf.pc"
}

cross_file(){ local f=$M/build/android-x86_64-api$API.ini
  cat > "$f" <<EOF
[constants]
toolchain = '$TC/bin'
[binaries]
ar = toolchain / 'llvm-ar'
c = ['ccache', toolchain / 'x86_64-linux-android$API-clang']
cpp = ['ccache', toolchain / 'x86_64-linux-android$API-clang++', '-fno-exceptions', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-static-libstdc++']
c_ld = 'lld'
cpp_ld = 'lld'
strip = toolchain / 'llvm-strip'
pkg-config = 'pkg-config'
[host_machine]
system = 'android'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
EOF
  echo "$f"; }

# The build directory is kept only while its configuration (options + LIBELF) is unchanged.
setup(){ local t=$1 b=$M/build/$1 cfg="LIBELF=$LIBELF ${MESON_OPTS[*]}"
  [[ -f $b/build.ninja && $(cat "$b/anybook-config.txt" 2>/dev/null) == "$cfg" ]] &&
    { log "setup: $t already configured ($b, LIBELF=$LIBELF)"; return; }
  rm -rf "$b"; : > "$L/$t-setup.log"; local cf; cf=$(cross_file); libelf_pc
  run "$t-setup" meson setup "$b" "$M/src/$t" --cross-file "$cf" "${MESON_OPTS[@]}"
  echo "$cfg" > "$b/anybook-config.txt"
}

build(){ local t=$1; run "$t-build" ninja -C "$M/build/$t" -j "$JOBS"; }

install_(){ local t=$1 b=$M/build/$1 o=$M/out/$1
  rm -rf "$o"; mkdir -p "$o"
  run "$t-install" meson install -C "$b" --no-rebuild --strip --destdir "$o/staging"
  # Android vendor layout: EGL/GLES under lib64/egl (ro.hardware.egl=mesa), the gallium
  # megadriver, GBM and libdrm in lib64, GBM's DRI backend in lib64/gbm (libgbm_mesa's compiled-in
  # backends path), Vulkan HAL as lib64/hw/vulkan.radv.so (ro.hardware.vulkan=radv).
  local s=$o/staging/vendor/lib64 v=$o/vendor/lib64 f old
  mkdir -p "$v/egl" "$v/hw" "$v/gbm"
  for f in libEGL_mesa libGLESv1_CM_mesa libGLESv2_mesa; do cp -L "$s/$f.so" "$v/egl/"; done
  for f in "$s"/libgallium*.so; do [[ -e $f ]] && cp -L "$f" "$v/"; done
  # libdrm_amdgpu becomes libdrm_amdgpu_mesa.so: AOSP's external/libdrm (2.4.124, too old for Mesa
  # 26.2) owns the libdrm_amdgpu.so name and install path. The SONAME loop below follows the rename.
  cp -L "$s/libdrm.so" "$s/libgbm_mesa.so" "$v/"; cp -L "$s/libdrm_amdgpu.so" "$v/libdrm_amdgpu_mesa.so"
  cp -L "$s/gbm/dri_gbm.so" "$v/gbm/"
  cp -L "$s/libvulkan_radeon.so" "$v/hw/vulkan.radv.so"
  if [[ $LIBELF == shared ]]; then cp -L "$DEPS/lib/libelf_mesa.so" "$v/"; "$TC/bin/llvm-strip" --strip-unneeded "$v/libelf_mesa.so"; fi
  # libdrm_amdgpu reads marketing names from its compiled-in ${datadir}: /vendor/etc/libdrm/amdgpu.ids
  mkdir -p "$o/vendor/etc/libdrm"; cp "$o/staging/vendor/etc/libdrm/amdgpu.ids" "$o/vendor/etc/libdrm/"
  # Android names libraries without version suffixes (AOSP's libdrm is "libdrm.so"): make every
  # SONAME equal its file name and rewrite NEEDED entries that pointed at the old names.
  local -A ren=()
  for f in $(find "$v" -name '*.so' | sort); do
    old=$(patchelf --print-soname "$f"); [[ $old == "$(basename "$f")" ]] && continue
    ren[$old]=$(basename "$f"); patchelf --set-soname "$(basename "$f")" "$f"
  done
  for f in $(find "$v" -name '*.so' | sort); do
    for old in "${!ren[@]}"; do
      patchelf --print-needed "$f" | grep -qxF "$old" && patchelf --replace-needed "$old" "${ren[$old]}" "$f"
    done
  done
  for old in "${!ren[@]}"; do echo "$old -> ${ren[$old]}"; done | sort > "$o/renamed-sonames.txt"
  (cd "$o/staging" && find . \( -type f -o -type l \) -printf '%10s %y %p\n' | sort -k3) > "$o/staging-listing.txt"
  log "install: $t -> $o/vendor"
}

verify(){ local t=$1 b=$M/build/$1 o=$M/out/$1 e=$M/evidence/$1
  mkdir -p "$e"; cd "$o/vendor"
  local libs; mapfile -t libs < <(find . -name '*.so' | sort)
  sha256sum "${libs[@]}" > "$e/sha256sums.txt"
  { echo "# bytes (stripped)  file"; for f in "${libs[@]}"; do printf '%10s  %s\n' "$(stat -c %s "$f")" "$f"; done
    echo; echo "# total: $(du -cb "${libs[@]}" | tail -1 | cut -f1) bytes"
    echo; for f in "${libs[@]}"; do echo "== $f"; "$TC/bin/llvm-size" -A "$f" | grep -E '^\.(text|rodata|data|bss)'; done
  } > "$e/sizes.txt"
  cp "$o/staging-listing.txt" "$o/renamed-sonames.txt" "$e/"
  for f in "${libs[@]}"; do echo "== $f"; "$TC/bin/llvm-readelf" -d "$f"; done > "$e/readelf-d.txt"
  python3 /repo/scripts/elf-needed-check.py --nm "$TC/bin/llvm-nm" --readelf "$TC/bin/llvm-readelf" \
    --sysroot "$SYSLIB" --stub "$b/src/android_stub" "${libs[@]}" > "$e/needed-check.txt" || true
  { for f in ./lib64/hw/vulkan.radv.so; do echo "== $f (Vulkan HAL: HMI + loader ICD entry points)"
      "$TC/bin/llvm-nm" -D --defined-only "$f" | grep -E ' (HMI|vk_icd[A-Za-z]*|vkGetInstanceProcAddr|vkGetDeviceProcAddr)$'
      echo "exported symbols: $("$TC/bin/llvm-nm" -D --defined-only "$f" | wc -l)"; done
    for f in ./lib64/egl/*.so ./lib64/libgallium*.so ./lib64/libdrm*.so ./lib64/libgbm_mesa.so ./lib64/gbm/*.so ./lib64/libelf_mesa.so; do [[ -f $f ]] || continue
      echo "== $f"; echo "exported symbols: $("$TC/bin/llvm-nm" -D --defined-only "$f" | wc -l)"
      "$TC/bin/llvm-nm" -D --defined-only "$f" | grep -E ' (eglGetProcAddress|eglGetDisplay|eglInitialize|glDrawArrays|glGetString|__driDriverGetExtensions_radeonsi|ddebug_screen_create)$' || true
    done
    echo; echo "== emutls imports (must be none: ELF TLS is forced for API >= 29)"
    "$TC/bin/llvm-nm" -D --undefined-only "${libs[@]}" | grep -c __emutls || true
  } > "$e/hal-symbols.txt"
  { echo "# explicit -march/-mcpu/-mtune/-m<isa> flags in compile_commands.json (count flag)"
    grep -oE -- '-m(arch|cpu|tune)=[^ "]+|-m(sse|avx|popcnt|f16c|fma|bmi)[0-9a-z.]*' "$b/compile_commands.json" | sort | uniq -c || echo "(none)"
    echo; echo "# clang driver defaults for x86_64-linux-android$API"
    "$TC/bin/x86_64-linux-android$API-clang" -### -c -x c /dev/null -o /dev/null 2>&1 | tr ' ' '\n' |
      grep -A1 -E '^"-target-(cpu|feature)"$' | grep -v -- -- | paste - - | sed 's/"//g'
    echo; echo "# predefined ISA macros"
    "$TC/bin/x86_64-linux-android$API-clang" -dM -E -x c /dev/null | grep -E '__(SSE[0-9_]*|AVX[0-9A-Z_]*|POPCNT|FMA|F16C|BMI2?)__ ' | sort
  } > "$e/march.txt"
  { echo "# Functions that touch ymm/zmm registers (AVX/AVX2/AVX-512), per unstripped build output:"
    echo "# <instructions> <function>. The baseline is the NDK default above; anything wider must sit"
    echo "# behind a runtime CPU check (util_cpu_caps / blake3 dispatch)."
    for f in $(find "$b" -name '*.so' -not -path '*/android_stub/*' -not -path '*.p/*' | sort); do
      echo "== ${f#"$b"/}"
      "$TC/bin/llvm-objdump" -d --no-show-raw-insn "$f" |
        awk '/^[0-9a-f]+ <.*>:$/{fn=$2} /%[yz]mm[0-9]/{print fn}' | sort | uniq -c | sort -rn
    done
  } > "$e/isa-wide-vector-functions.txt"
  { echo "tree: $t ${REF[$t]} ${SHA[$t]} ($(cat "$M/src/$t/VERSION"))"
    echo "patches: $(git -C "$M/src/$t" rev-list --count "${SHA[$t]}..HEAD") (mesa/patches/$t), HEAD $(git -C "$M/src/$t" rev-parse HEAD)"
    git -C "$M/src/$t" log --reverse --format='  %h %s' "${SHA[$t]}..HEAD"
    echo "ndk: $(grep Pkg.Revision "$NDK/source.properties" | cut -d' ' -f3) ($NDK_VERSION), api $API"
    echo "clang: $("$TC/bin/clang" --version | head -1)"
    echo "meson: $(meson --version)  ninja: $(ninja --version)  glslang: $(glslangValidator --version | head -1)"
    echo "libdrm: $(sed -n 's/^directory = //p' "$M/src/$t/subprojects/libdrm.wrap") (meson wrap, shared)"
    echo "libelf: elfutils $(cat "$DEPS/libelf.version") ($ELFUTILS_REF), LIBELF=$LIBELF"
    echo "options: ${MESON_OPTS[*]}"
  } > "$e/versions.txt"
  gzip -c "$L/$t-setup.log" > "$e/setup.log.gz"; gzip -c "$L/$t-build.log" > "$e/build.log.gz"
  gzip -c "$b/meson-logs/meson-log.txt" > "$e/meson-log.txt.gz"
  log "verify: $t -> $e"; tail -5 "$e/needed-check.txt"
}

for t in "${trees[@]}"; do
  [[ -n ${URL[$t]:-} ]] || { echo "unknown tree: $t" >&2; exit 2; }
  for s in "${steps[@]}"; do
    case $s in fetch|setup|build|verify) "$s" "$t" ;; install) install_ "$t" ;; deps) deps ;;
      *) echo "unknown step: $s" >&2; exit 2 ;; esac
  done
done
