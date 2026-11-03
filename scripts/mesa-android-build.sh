#!/usr/bin/env bash
# Out-of-tree Android x86_64 build of Mesa radeonsi (EGL/GLES) + RADV (Vulkan) with the NDK,
# following https://docs.mesa3d.org/android.html. Resumable and version-pinned: every step is
# skipped when its output already exists, and `ninja` resumes, so just rerun after a timeout.
#
#   scripts/mesa-android-build.sh [step ...] [-- tree ...]
#     steps: fetch deps clc rm setup build install verify isa   (default: all, in that order)
#     trees: upstream ag nvk-rm-clean                            (default: upstream ag)
#
# The nvk-rm-clean tree (ANAL-327, docs/nvk-openbook.md) is NVK, the Vulkan driver for NVIDIA GPUs, on NVIDIA's open
# kernel driver: upstream's pin with mesa/patches/{upstream,nvk,nvk-rm-clean}, and the RM backend NVK links,
# libnv_bionic_native.so, from mesa/nvk-rm-clean/backend. Both come from the clean-room tree of ANAL-324 (its
# provenance: mesa/nvk-rm-clean/PROVENANCE.md). Its two extra steps: clc builds Mesa's build-time compilers
# (mesa_clc, vtn_bindgen2) for the build host from the same source, and rm builds the backend. Both are no-ops for
# the other trees. The tree builds only after its provenance gate passes (scripts/nvk-provenance-check.sh). Its
# directories (src/, build/ and out/nvk-rm-clean) and patch commits are those of the clean-room build, so the same
# inputs give the same bytes as the 2b-tested build (ANAL-326).
#
# Runs on the host and re-executes itself inside the anybook-mesa-android image (anybook-mesa-android-rust for the
# nvk-rm-clean tree; both from tools/Dockerfile.mesa-android); the `isa` step uses anybook-inspect (elfx86exts).
# Sources, builds and artifacts live in ~/anybook/mesa, logs in ~/anybook/logs/mesa.
# Env: STEP_TIMEOUT (s, per step, default 3000), JOBS (default nproc), API (default 37),
#      CCACHE_DISABLE=1 for a clean compile,
#      LIBELF=shared|static (default shared): how radeonsi gets libelf (LGPL-3.0+, docs/mesa.md).
#        shared ships it as lib64/libelf_mesa.so (the recommended option until the owner decides);
#        static links it into libgallium_dri.so as ANAL-173 did. Changing it re-runs setup.
#      ANDROID_STRICT=true|false (default false since ANAL-177): RADV reports Vulkan 1.4 on Android when
#        false, 1.1 when true (Mesa's own default). On the G14's Radeon 890M, 1.4 passed 1,998 more dEQP-VK
#        cases than 1.1 with no new failure (docs/graphics-amd.md). Changing it re-runs setup.
#      MESA_VARIANT=-<name> (default empty): build, out and evidence go to <dir>/<tree><variant>, so a variant
#        (e.g. MESA_VARIANT=-strict ANDROID_STRICT=true, a Vulkan 1.1 build for comparison or fallback) never
#        replaces the default build. The source tree is shared; graphics-amd-stage-mesa.sh upstream-strict
#        stages a variant.
set -euo pipefail

# ---- pins -------------------------------------------------------------------------------
declare -A URL=([upstream]=https://gitlab.freedesktop.org/mesa/mesa.git
                [ag]=https://github.com/Android-Generic/external_mesa.git
                [nvk-rm-clean]=https://gitlab.freedesktop.org/mesa/mesa.git)
declare -A REF=([upstream]=mesa-26.2.5 [ag]=26.0/main [nvk-rm-clean]=mesa-26.2.5)
declare -A SHA=([upstream]=ddaf85e353442d9d7f192fdcf1823e652e3f2ee3   # tag mesa-26.2.5
                [ag]=b14bf42d23ef1f9625eddb005cd568ab3873f11d         # 26.0/main, 2026-09-30
                [nvk-rm-clean]=ddaf85e353442d9d7f192fdcf1823e652e3f2ee3)  # the same tag as upstream
# mesa/patches/<dir>/*.patch applied on top of the pin, directory by directory.
declare -A PATCHDIRS=([upstream]=upstream [ag]=ag [nvk-rm-clean]="upstream nvk nvk-rm-clean")
declare -A IMAGES=([upstream]=anybook-mesa-android [ag]=anybook-mesa-android [nvk-rm-clean]=anybook-mesa-android-rust)
has_rm(){ [[ $1 == nvk-rm-clean ]]; }   # NVK on NVIDIA's open kernel driver, with its RM backend
# The NVIDIA kernel driver release the backend is built for: the image pins NVIDIA's open kernel modules, their GSP
# firmware and this userspace to one release, and the backend's strict version check refuses any other module.
RM_DRIVER_VERSION=615.78.08
# The clean-room build's commit identity for the patch commits (scripts/build-clean.sh of ANAL-324's tree): Mesa
# compiles the patched HEAD's hash into the driver ("Mesa 26.2.5 (git-09036ef459)"), so the same identity and dates
# give the same bytes.
RM_COMMITTER_NAME='B Honey'; RM_COMMITTER_EMAIL='9922368+Mhsbrian@users.noreply.github.com'
RM_COMMITTER_DATE='2026-11-01T00:00:00Z'
AG_BASE=mesa-26.0.8   # upstream tag AG's 26.0/main is based on (merge-base 60e95b78)
# radeonsi needs libelf, which the NDK lacks: build AOSP's own elfutils (0.193) the way its
# Android.bp builds `libelf` (+ `libeu`), minus zstd. LGPL-3.0-or-later (docs/mesa.md): built both
# as libelf.a and as libelf_mesa.so (its own SONAME, so it can't clash with an AOSP libelf.so).
ELFUTILS_URL=https://android.googlesource.com/platform/external/elfutils
ELFUTILS_REF=android-17.0.0_r1; ELFUTILS_SHA=219c3a368b121307f2e05593cee89b8591cc40b9
API=${API:-37}; STEP_TIMEOUT=${STEP_TIMEOUT:-3000}; LIBELF=${LIBELF:-shared}; ANDROID_STRICT=${ANDROID_STRICT:-false}
V=${MESA_VARIANT:-}
[[ $V =~ ^(-[a-z0-9]+)?$ ]] || { echo "MESA_VARIANT must be empty or -<lowercase letters and digits>" >&2; exit 2; }

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

# The nvk-rm-clean tree builds NVK alone (no radeonsi, RADV, GL, EGL or GBM); mesa_clc and vtn_bindgen2 come from its
# clc step.
tree_opts(){ local o
  for o in "${MESON_OPTS[@]}"; do
    if has_rm "$1"; then
      case $o in -Dgallium-drivers=*) o=-Dgallium-drivers= ;; -Dvulkan-drivers=*) o=-Dvulkan-drivers=nouveau ;;
        -Degl=*|-Dgles1=*|-Dgles2=*|-Dgbm=*) o=${o%%=*}=disabled ;; esac
    fi
    printf '%s\n' "$o"
  done
  if has_rm "$1"; then printf '%s\n' -Dopengl=false -Dmesa-clc=system; fi
}

steps=(); trees=()
while (($#)); do [[ $1 == -- ]] && { shift; trees=("$@"); break; }; steps+=("$1"); shift; done
((${#steps[@]})) || steps=(fetch deps clc rm setup build install verify isa)
((${#trees[@]})) || trees=(upstream ag)

# ---- host side: the provenance gate and the rm step, then the container steps, then the isa step ------------
if [[ ! -d /opt/android-ndk ]]; then
  A=${ANYBOOK_HOME:-$HOME/anybook}; repo=$(cd "$(dirname "$0")/.." && pwd)
  mkdir -p "$A/mesa"/{src,build,out,ccache,evidence,home,cargo} "$A/logs/mesa"
  cstep=(); want_isa=0; want_rm=0
  for s in "${steps[@]}"; do
    case $s in isa) want_isa=1 ;; rm) want_rm=1 ;; *) cstep+=("$s") ;; esac
  done
  for t in "${trees[@]}"; do
    [[ -n ${IMAGES[$t]:-} ]] || { echo "unknown tree: $t" >&2; exit 2; }
    has_rm "$t" || continue
    # Nothing that ties behaviour to NVIDIA's closed userspace driver may enter the build (ANAL-324).
    "$repo/scripts/nvk-provenance-check.sh"
    if ((want_rm)); then
      # The RM backend, as a cdylib for x86_64-linux-android, offline, with the crate's own release profile (unwinding,
      # line tables; stripped at install). mesa/nvk-rm-clean is mounted as /repo, the clean-room tree's own layout:
      # the line tables, and with them the linker's build ID, name the directory the crate was built in.
      echo "== $t$V rm: RM backend (cargo, x86_64-linux-android, driver $RM_DRIVER_VERSION)" | tee -a "$A/logs/mesa/$t$V-rm.log"
      docker run --rm --network none -u "$(id -u):$(id -g)" -e CARGO_HOME=/a/mesa/cargo \
        -e NV_RM_DRIVER_VERSION=$RM_DRIVER_VERSION \
        -e CARGO_TARGET_X86_64_LINUX_ANDROID_LINKER=/opt/android-ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android${API}-clang \
        -v "$A/mesa:/a/mesa" -v "$repo/mesa/nvk-rm-clean:/repo:ro" "${IMAGES[$t]}" sh -c \
        "HOME=/tmp cargo build --offline --locked --release --lib --target x86_64-linux-android --target-dir /a/mesa/build/$t$V-rm --manifest-path /repo/backend/Cargo.toml" \
        2>&1 | tee -a "$A/logs/mesa/$t$V-rm.log"
      [[ ${PIPESTATUS[0]} == 0 && -f $A/mesa/build/$t$V-rm/x86_64-linux-android/release/libnv_bionic_native.so ]] ||
        { echo "rm: the backend build failed ($A/logs/mesa/$t$V-rm.log)" >&2; exit 1; }
    fi
  done
  if ((${#cstep[@]})); then
    for t in "${trees[@]}"; do
      docker run --rm -u "$(id -u):$(id -g)" -e HOME=/a/mesa/home -e CCACHE_DIR=/a/mesa/ccache \
        -e STEP_TIMEOUT -e JOBS -e API -e CCACHE_DISABLE -e LIBELF -e ANDROID_STRICT -e MESA_VARIANT -v "$A/mesa:/a/mesa" -v "$A/logs/mesa:/a/logs" -v "$repo:/repo:ro" \
        "${IMAGES[$t]}" /repo/scripts/mesa-android-build.sh "${cstep[@]}" -- "$t"
    done
  fi
  if ((want_isa)); then
    for t in "${trees[@]}"; do
      mkdir -p "$A/mesa/evidence/$t$V"
      docker run --rm -u "$(id -u):$(id -g)" -v "$A/mesa:/a/mesa" anybook-inspect sh -c '
        cd /a/mesa/out/'"$t$V"'/vendor && find . -name "*.so" | sort | while read -r f; do
          echo "== $f"; elfx86exts "$f" | sed -n "/^Instruction set extensions used/,\$p"; done' \
        > "$A/mesa/evidence/$t$V/isa-elfx86exts.txt"
      echo "isa: $t$V -> $A/mesa/evidence/$t$V/isa-elfx86exts.txt"
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
  if has_rm "$t" && [[ ! -d $d/.git && -d $M/src/upstream/.git ]]; then
    # The same Mesa as the upstream tree: share its objects (the relative path also resolves in the containers).
    git clone -q --shared --no-checkout "$M/src/upstream" "$d"
    echo '../../../upstream/.git/objects' > "$d/.git/objects/info/alternates"
    git -C "$d" remote set-url origin "${URL[$t]}"
  fi
  [[ -d $d/.git ]] || { git init -q "$d"; git -C "$d" remote add origin "${URL[$t]}"; }
  if ! git -C "$d" cat-file -e "${SHA[$t]}^{commit}" 2>/dev/null; then
    run "$t-fetch" git -C "$d" fetch --filter=blob:none origin "${REF[$t]}" ||
    run "$t-fetch" git -C "$d" fetch --filter=blob:none origin "${SHA[$t]}"
  fi
  # OpenBook's patches (mesa/patches/<dir>/*.patch for each of the tree's PATCHDIRS) on top of the pin, applied
  # with git am, a fixed committer and date, so the patched HEAD is reproducible. Skipped when HEAD already
  # carries them with that committer.
  local pd f patches=() want have who
  for pd in ${PATCHDIRS[$t]}; do
    for f in /repo/mesa/patches/"$pd"/*.patch; do [[ -e $f ]] && patches+=("$f"); done
  done
  local -a am=(env GIT_COMMITTER_NAME="OpenBook mesa-android-build.sh" GIT_COMMITTER_EMAIL=noreply@openbook.invalid
               GIT_COMMITTER_DATE=2026-10-17T00:00:00+00:00 git -C "$d" am -q)
  if has_rm "$t"; then
    am=(env GIT_COMMITTER_NAME="$RM_COMMITTER_NAME" GIT_COMMITTER_EMAIL="$RM_COMMITTER_EMAIL"
        GIT_COMMITTER_DATE="$RM_COMMITTER_DATE" git -C "$d" am -q --committer-date-is-author-date)
  fi
  want=$( ((${#patches[@]})) && cat "${patches[@]}" | git patch-id --stable | cut -d' ' -f1 || true)
  have=$(git -C "$d" log --reverse -p --format='commit %H' "${SHA[$t]}..HEAD" 2>/dev/null | git patch-id --stable | cut -d' ' -f1 || true)
  who=$(git -C "$d" log --format='%cn <%ce>' "${SHA[$t]}..HEAD" 2>/dev/null | sort -u)
  if has_rm "$t" && [[ -n $who && $who != "$RM_COMMITTER_NAME <$RM_COMMITTER_EMAIL>" ]]; then have=; fi
  if [[ $want != "$have" ]] || ! git -C "$d" diff --quiet HEAD 2>/dev/null; then
    git -C "$d" checkout -q -f --detach "${SHA[$t]}"
    for f in "${patches[@]}"; do "${am[@]}" "$f"; done
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

# NVK's build-time compilers: mesa_clc (OpenCL C -> SPIR-V, LLVM 18 + SPIRV-LLVM-Translator + libclc) and
# vtn_bindgen2, built for the build host from the tree's own source and installed into build/<tree>-clc/inst.
# Rebuilt when the source HEAD changes (anybook-src.txt). A no-op for trees without NVK.
clc(){ local t=$1 b=$M/build/$1-clc head
  has_rm "$t" || { log "clc: $t has no NVK, nothing to build"; return; }
  head=$(git -C "$M/src/$t" rev-parse HEAD)
  if [[ -x $b/inst/bin/mesa_clc && -x $b/inst/bin/vtn_bindgen2 && $(cat "$b/anybook-src.txt" 2>/dev/null) == "$head" ]]; then
    log "clc: $t mesa_clc already built for $head"; return
  fi
  rm -rf "$b"; : > "$L/$t-clc.log"
  ( unset PKG_CONFIG_LIBDIR   # a build-host compile: the build host's LLVM, SPIRV-Tools and zlib
  run "$t-clc" meson setup "$b" "$M/src/$t" --prefix="$b/inst" --libdir=lib --buildtype=release -Dstrip=true \
    -Dplatforms= -Dgallium-drivers= -Dvulkan-drivers= -Dmesa-clc=enabled -Dinstall-mesa-clc=true -Dllvm=enabled -Dshared-llvm=enabled \
    -Dglx=disabled -Degl=disabled -Dgbm=disabled -Dgles1=disabled -Dgles2=disabled -Dopengl=false -Dxmlconfig=disabled \
    -Dexpat=disabled -Dvalgrind=disabled -Dlibunwind=disabled -Dlmsensors=disabled -Dzstd=disabled -Dbuild-tests=false -Dtools=
  run "$t-clc" ninja -C "$b" -j "$JOBS" install )
  [[ -x $b/inst/bin/mesa_clc && -x $b/inst/bin/vtn_bindgen2 ]] || { log "clc: $t: mesa_clc or vtn_bindgen2 missing"; exit 1; }
  echo "$head" > "$b/anybook-src.txt"
  log "clc: $t mesa_clc and vtn_bindgen2 -> $b/inst/bin"
}

# Run a command with the tree's mesa_clc and vtn_bindgen2 first in PATH (the nvk-rm-clean tree only).
clc_path(){ local t=$1; shift
  if has_rm "$t"; then PATH=$M/build/$t-clc/inst/bin:$PATH "$@"; else "$@"; fi; }

# The nvk-rm-clean tree's cross file adds Rust: rustc for x86_64-linux-android with -C panic=abort (no unwinder in
# the driver), and bindgen on the NDK's libclang. Meson passes rustc's unversioned --target to bindgen unless the
# cross file names one, and bionic refuses unversioned Android triples, so name the API level here. libclang also
# needs the NDK clang's resource directory spelled out to find its own headers (stddef.h, float.h). NVK links the RM
# backend (-lnv_bionic_native, mesa/patches/nvk-rm-clean), the rm step's output.
cross_file(){ local f=$M/build/android-x86_64-api$API.ini
  has_rm "${1:-}" && f=$M/build/android-x86_64-api$API-$1$V.ini   # its own: other trees' cross files stay theirs
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
  if has_rm "${1:-}"; then
    local res; res=$("$TC/bin/clang" -print-resource-dir)
    sed -i "/^pkg-config = /i rust = ['rustc', '--target', 'x86_64-linux-android']" "$f"
    cat >> "$f" <<EOF
[properties]
bindgen_clang_arguments = ['--target=x86_64-linux-android$API', '--sysroot', '$TC/sysroot', '-resource-dir', '$res']
[built-in options]
rust_args = ['-C', 'panic=abort']
EOF
    printf "%s_link_args = ['-L$M/build/$1$V-rm/x86_64-linux-android/release']\n" c cpp >> "$f"   # NVK links as C++
  fi
  echo "$f"; }

# The build directory is kept only while its configuration (options + LIBELF) is unchanged.
setup(){ local t=$1 b=$M/build/$1$V opts cfg cf
  mapfile -t opts < <(tree_opts "$t"); cf=$(cross_file "$t"); cfg="LIBELF=$LIBELF ${opts[*]}"
  has_rm "$t" && cfg+=" cross-file=$(sha256sum < "$cf" | cut -c1-16)"   # its Rust and bindgen settings
  [[ -f $b/build.ninja && $(cat "$b/anybook-config.txt" 2>/dev/null) == "$cfg" ]] &&
    { log "setup: $t already configured ($b, LIBELF=$LIBELF)"; return; }
  rm -rf "$b"; : > "$L/$t$V-setup.log"; libelf_pc
  clc_path "$t" run "$t$V-setup" meson setup "$b" "$M/src/$t" --cross-file "$cf" "${opts[@]}"
  echo "$cfg" > "$b/anybook-config.txt"
}

build(){ local t=$1; clc_path "$t" run "$t$V-build" ninja -C "$M/build/$t$V" -j "$JOBS"; }

install_(){ local t=$1 b=$M/build/$1$V o=$M/out/$1$V
  rm -rf "$o"; mkdir -p "$o"
  run "$t$V-install" meson install -C "$b" --no-rebuild --strip --destdir "$o/staging"
  # Android vendor layout: EGL/GLES under lib64/egl (ro.hardware.egl=mesa), the gallium
  # megadriver, GBM and libdrm in lib64, GBM's DRI backend in lib64/gbm (libgbm_mesa's compiled-in
  # backends path), Vulkan HAL as lib64/hw/vulkan.radv.so (ro.hardware.vulkan=radv).
  # The nvk-rm-clean tree: NVK as lib64/hw/vulkan.nouveau.so, with the RM backend it links, Mesa's libdrm and
  # libelf_mesa next to it. The OpenBook NVK driver package (device/anybook/common/nvk) carries these four.
  local s=$o/staging/vendor/lib64 v=$o/vendor/lib64 f old
  mkdir -p "$v/hw"
  if ! has_rm "$t"; then
    mkdir -p "$v/egl" "$v/gbm"
    for f in libEGL_mesa libGLESv1_CM_mesa libGLESv2_mesa; do cp -L "$s/$f.so" "$v/egl/"; done
    for f in "$s"/libgallium*.so; do [[ -e $f ]] && cp -L "$f" "$v/"; done
    # libdrm_amdgpu becomes libdrm_amdgpu_mesa.so: AOSP's external/libdrm (2.4.124, too old for Mesa
    # 26.2) owns the libdrm_amdgpu.so name and install path. The SONAME loop below follows the rename.
    cp -L "$s/libgbm_mesa.so" "$v/"; cp -L "$s/libdrm_amdgpu.so" "$v/libdrm_amdgpu_mesa.so"
    cp -L "$s/gbm/dri_gbm.so" "$v/gbm/"
    cp -L "$s/libvulkan_radeon.so" "$v/hw/vulkan.radv.so"
  fi
  cp -L "$s/libdrm.so" "$v/"
  if has_rm "$t"; then
    cp -L "$s/libvulkan_nouveau.so" "$v/hw/vulkan.nouveau.so"
    cp "$M/build/$t$V-rm/x86_64-linux-android/release/libnv_bionic_native.so" "$v/"
    "$TC/bin/llvm-strip" --strip-unneeded "$v/libnv_bionic_native.so"
  fi
  if [[ $LIBELF == shared ]]; then cp -L "$DEPS/lib/libelf_mesa.so" "$v/"; "$TC/bin/llvm-strip" --strip-unneeded "$v/libelf_mesa.so"; fi
  # libdrm_amdgpu reads marketing names from its compiled-in ${datadir}: /vendor/etc/libdrm/amdgpu.ids
  if ! has_rm "$t"; then mkdir -p "$o/vendor/etc/libdrm"; cp "$o/staging/vendor/etc/libdrm/amdgpu.ids" "$o/vendor/etc/libdrm/"; fi
  # Android names libraries without version suffixes (AOSP's libdrm is "libdrm.so"): make every
  # SONAME equal its file name (the backend has none) and rewrite NEEDED entries that pointed at the old names.
  local -A ren=()
  for f in $(find "$v" -name '*.so' | sort); do
    old=$(patchelf --print-soname "$f"); [[ $old == "$(basename "$f")" ]] && continue
    patchelf --set-soname "$(basename "$f")" "$f"; [[ -n $old ]] && ren[$old]=$(basename "$f")
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

verify(){ local t=$1 b=$M/build/$1$V o=$M/out/$1$V e=$M/evidence/$1$V
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
  { for f in ./lib64/hw/vulkan.*.so; do echo "== $f (Vulkan HAL: HMI + loader ICD entry points)"
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
    echo "patches: $(git -C "$M/src/$t" rev-list --count "${SHA[$t]}..HEAD") (mesa/patches/{${PATCHDIRS[$t]// /,}}), HEAD $(git -C "$M/src/$t" rev-parse HEAD)"
    git -C "$M/src/$t" log --reverse --format='  %h %s' "${SHA[$t]}..HEAD"
    echo "ndk: $(grep Pkg.Revision "$NDK/source.properties" | cut -d' ' -f3) ($NDK_VERSION), api $API"
    echo "clang: $("$TC/bin/clang" --version | head -1)"
    echo "meson: $(meson --version)  ninja: $(ninja --version)  glslang: $(glslangValidator --version | head -1)"
    echo "libdrm: $(sed -n 's/^directory = //p' "$M/src/$t/subprojects/libdrm.wrap") (meson wrap, shared)"
    echo "libelf: elfutils $(cat "$DEPS/libelf.version") ($ELFUTILS_REF), LIBELF=$LIBELF"
    if has_rm "$t"; then
      echo "rust: $(rustc --version), x86_64-linux-android std, -C panic=abort"
      echo "mesa_clc: built for the build host from this tree (HEAD $(cat "$M/build/$t-clc/anybook-src.txt")), LLVM $(llvm-config-18 --version)"
      echo "rm: mesa/nvk-rm-clean/backend, cargo build --offline --locked --release --lib, driver $RM_DRIVER_VERSION"
    fi
    echo "options: $(tree_opts "$t" | tr '\n' ' ')"
    echo "variant: ${V:-(none)}"
  } > "$e/versions.txt"
  gzip -c "$L/$t$V-setup.log" > "$e/setup.log.gz"; gzip -c "$L/$t$V-build.log" > "$e/build.log.gz"
  gzip -c "$b/meson-logs/meson-log.txt" > "$e/meson-log.txt.gz"
  log "verify: $t -> $e"; tail -5 "$e/needed-check.txt"
}

for t in "${trees[@]}"; do
  [[ -n ${URL[$t]:-} ]] || { echo "unknown tree: $t" >&2; exit 2; }
  for s in "${steps[@]}"; do
    case $s in fetch|clc|setup|build|verify) "$s" "$t" ;; install) install_ "$t" ;; deps) deps ;;
      *) echo "unknown step: $s" >&2; exit 2 ;; esac
  done
done
