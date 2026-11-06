#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Write a release's SOURCES.md for scripts/release/make-sources.sh (ANAL-341).

SOURCES.md stands alone: what each file holds, and how to build the copyleft parts from these files and public
sources only. It never points at OpenBook's development repository, which is private.
"""
import argparse
import json
import os


def main():
    ap = argparse.ArgumentParser()
    for o in ("version", "kernel-release", "loader", "kernel-revisions", "userspace-revisions", "notice-scan",
              "build-files", "tree", "home", "contact", "mesa-provenance", "out"):
        ap.add_argument("--" + o, required=True)
    ap.add_argument("--mesa-note")
    ap.add_argument("--install-note")
    ap.add_argument("--commit", help="the OpenBook commit the build files were packed from (make-sources.sh --commit)")
    ap.add_argument("--installer-tools", default="the packages its Dockerfile names")
    a = ap.parse_args()
    v = a.version
    s = json.load(open(a.notice_scan))
    krev = open(a.kernel_revisions).read().rstrip()
    urev = open(a.userspace_revisions).read().rstrip()
    mprov = open(a.mesa_provenance).read()
    bcmd = next((l.split(": ", 1)[1] for l in krev.splitlines() if l.startswith("build command")), "")
    target = next((w for w in bcmd.split() if w.startswith("//")), "//devices/anybook:anybook_g14_dist")
    files = sorted(os.path.relpath(os.path.join(d, f), a.build_files)
                   for d, _, fs in os.walk(a.build_files) for f in fs if f != "SOURCES.md")
    msha = next((l.split()[1] for l in urev.splitlines() if l.startswith("mesa-build/mesa ")), "<Mesa commit>")
    pv = lambda key: next((l.split(": ", 1)[1] for l in mprov.splitlines() if l.startswith(key + ":")), "")
    K, U, B, SB = (f"openbook-{v}-source-{x}" for x in ("kernel", "userspace", "build", "systemd-boot"))

    L = [f"# Source for OpenBook {v}", "",
         "OpenBook's image contains software under the GNU GPL and LGPL. These files are its complete corresponding",
         "source, with OpenBook's scripts and configuration that compiled those parts and put them into the image.",
         "Everything below builds from these files and from public sources at the URLs given. OpenBook's development",
         "repository is not needed and is not public.", "",
         "| File | What it is |", "|---|---|",
         f"| `{K}.tar.xz` | Linux {a.kernel_release}: Google's Android common kernel with OpenBook's commits, the Kleaf "
         "build files with OpenBook's commit, OpenBook's kernel modules, nouveau and NVIDIA's open modules "
         "(Dual MIT/GPL), the pinned manifest, the patch series and the build command |",
         f"| `{U}.tar.xz` | the Android projects listed below, as built, and Mesa's libelf (elfutils, LGPL-3.0+) with "
         "Mesa itself |",
         f"| `{SB}.tar.xz` | {a.loader} (LGPL-2.1+): systemd's upstream source and Arch Linux's packaging |",
         f"| `{B}.tar.xz` | OpenBook's scripts and configuration that built and installed the parts above, as they "
         + (f"were when the image was built: the files of OpenBook commit `{a.commit}` (git tree `{a.tree}`), and a "
            "copy of this file |" if a.commit else
            f"were in the commit that built the image (git tree `{a.tree}`), and a copy of this file |"),
         "| `aosp-manifest.xml` | every Android project in the build, at its exact revision (all public at "
         "android.googlesource.com) |", "",
         "OpenBook's own files are under the Apache License 2.0, as their SPDX headers say. Every other file keeps",
         "its own licence.", "",
         "## The kernel", "",
         "The kernel is Google's Android Common Kernel (GKI), built with Kleaf, Google's Bazel-based kernel build.",
         "Kleaf brings its own clang, Rust and build tools from the pinned prebuilts, so the host needs only Linux",
         "x86_64, `repo`, `git` and Python 3. OpenBook built it in an Ubuntu 24.04 container (`tools/Dockerfile.kernel`",
         f"in `{B}.tar.xz`). OpenBook's synced workspace and its build output take about 50 GB, and the build below is",
         "limited to 16 GB of RAM. `git am` needs a git identity (`git config user.name` and `user.email`).", "",
         "```", krev, "```", "",
         "**1. The public projects, at the pinned revisions.**", "",
         "```bash",
         f"tar -xJf {K}.tar.xz",
         f"mkdir pin && cp {K}/provenance/manifest-pinned.xml pin/default.xml",
         "git -C pin init -q && git -C pin add default.xml && git -C pin -c user.name=pin -c user.email=pin@invalid commit -qm pin",
         "mkdir ws && cd ws",
         "repo init -u ../pin -m default.xml && repo sync -c -j4",
         "```", "",
         "googlesource sometimes fails a busy sync with network errors: run `repo sync -c -j2` again. Don't use shallow",
         "clones (`--depth`); Kleaf's version stamp reads each project's history.", "",
         "**2. OpenBook's changes.** Apply the patch series to `common` and `build/kernel`, and add OpenBook's module",
         "tree. The trees then equal the shipped ones; `git rev-parse HEAD^{tree}` prints the tree ids above. The",
         "commit ids differ, and with them the `-g<id>` suffix of the release string, because the author lines were",
         "rewritten for publication.", "",
         "```bash",
         f"(cd common && git am ../../{K}/provenance/patches/common/*.patch)",
         f"(cd build/kernel && git am ../../../{K}/provenance/patches/build-kernel/*.patch)",
         f"mkdir -p devices && cp -a ../{K}/devices/anybook devices/",
         "git -C common rev-parse HEAD^{tree}; git -C build/kernel rev-parse HEAD^{tree}",
         "```", "",
         f"The `common`, `build/kernel` and `devices/anybook` directories in `{K}.tar.xz` are the same trees, as checked",
         "out when the kernel was built; use them instead of the patches if you don't need git history.", "",
         "**3. Build.** The command OpenBook ran, in the workspace root:", "",
         "```bash", bcmd.replace("--destdir=<dist dir>", "--destdir=$PWD/out/dist") if bcmd else
         f"tools/bazel run --config=stamp {target} -- --destdir=$PWD/out/dist", "```", "",
         "`out/dist/` then holds `bzImage`, the GKI `system_dlkm` image, the vendor modules, `vendor_dlkm`, the",
         "`vendor_boot` ramdisk fragment and their module lists.", "",
         "## Installing a changed kernel", "",
         "**Where the kernel lives.** The live image is a GPT disk. `boot_a` holds the kernel (`bzImage`) in an",
         "Android boot image, header version 4. `vendor_boot_a` holds the vendor ramdisk; its `dlkm` fragment is",
         "Kleaf's `vendor_boot-ramdisk.lz4`. `super` holds the logical partitions `system_dlkm_a` (the GKI modules) and",
         "`vendor_dlkm_a` (OpenBook's modules), and `vbmeta_a` describes them all. `boot-images.txt` in",
         f"`{B}.tar.xz` lists the exact `mkbootimg` arguments, AVB footers, vbmeta and `super` layout, read back from",
         "the shipped image. The image is signed with AOSP's public test keys (`external/avb/test/data` in AOSP), so",
         "images you build can be signed the same way.", "",
         "**How OpenBook did it.** `scripts/kernel-g14-package.sh` took the Kleaf dist's bare-metal files",
         "(`bzImage`, `system_dlkm.flatten.erofs.img`, `bm/vendor_dlkm.img`, `bm/initramfs.img`), and",
         "`scripts/g14-stage-kernel.sh` copied them into the Android tree. There OpenBook's Android product build",
         "(`device/anybook/g14/kernel.mk` and the two `BoardConfig.mk` files set its parameters) made `boot.img`,",
         "`vendor_boot.img`, `super.img` and `vbmeta.img`. `scripts/installer-image.sh` then assembled the live",
         "image from those images in the `tools/Dockerfile.installer` container, which had",
         f"{a.installer_tools}. The Dockerfile takes the current Arch Linux packages; the Arch Linux Archive",
         "(archive.archlinux.org) keeps these versions. The rest of OpenBook's Android product tree is not part of",
         "this offer: `EXCLUDED.txt` lists what the packed files refer to but leave out, and why, and `CLOSURE.txt` is",
         "the check that nothing else is missing.", "",
         "**From public inputs only.** `scripts/release/kernel-into-image.sh` (written for this source offer, not",
         "used to build the image) does the product build's kernel steps with AOSP's host tools. It starts from the",
         "published image's own partitions and a Kleaf dist, and signs with AOSP's public test key",
         "(`external/avb/test/data/testkey_rsa4096.pem` in AOSP at `aosp-manifest.xml`). It checks that the",
         "`bzImage` and every module name the same kernel release, and has avbtool verify the new vbmeta against all",
         "the images. `installer-image.sh` then writes a live image from its output:", "",
         "```bash",
         f"tar -xJf {B}.tar.xz",
         "export OPENBOOK_HOME=$PWD/home      # the scripts' data directory",
         "# AOSP's host tools (avbtool, fsck.erofs, lpdump, lpmake, mkbootimg, unpack_bootimg), built from AOSP at",
         "# aosp-manifest.xml with `m avbtool fsck.erofs lpdump lpmake mkbootimg unpack_bootimg`, go in",
         "# $OPENBOOK_HOME/aosp/src/out/host/linux-x86/{bin,lib64}, and AOSP's external/avb/test/data/testkey_rsa4096.pem",
         "# in $OPENBOOK_HOME/aosp/src/external/avb/test/data/. The firmware manifests go where installer-image.sh reads them:",
         "mkdir -p $OPENBOOK_HOME/aosp/src/vendor/anybook/g14-kernel/{firmware,firmware-nvidia-open}",
         f"cp {B}/inputs/firmware-manifest.tsv $OPENBOOK_HOME/aosp/src/vendor/anybook/g14-kernel/firmware/",
         f"cp {B}/inputs/firmware-manifest-nvidia-open.json $OPENBOOK_HOME/aosp/src/vendor/anybook/g14-kernel/firmware-nvidia-open/",
         f"{B}/scripts/release/kernel-into-image.sh --image openbook-{v}-x86_64-live.img --kernel ws/out/dist --out $OPENBOOK_HOME/installer/new",
         f"{B}/scripts/installer-image.sh --inputs $OPENBOOK_HOME/installer/new --label my-kernel --out $OPENBOOK_HOME/installer/out --no-xz",
         "```", "",
         "Write the result to a USB stick as in the install guide (or with "
         f"`{B}/scripts/installer/write-stick.sh`). `boot-images.txt` lists what the tool reads from the image: the",
         "`mkbootimg` arguments, AVB footers, vbmeta and `super` layout.", "",
] + ([open(a.install_note).read().rstrip(), ""] if a.install_note else []) + [
         "## Mesa's libelf (LGPL-3.0+)", "",
         "Mesa's radeonsi driver needs libelf, which the Android NDK lacks. OpenBook builds AOSP's own elfutils as a",
         "shared library, `/vendor/lib64/libelf_mesa.so`, that Mesa's libraries load, so it can be replaced on its",
         f"own. The build is the `deps` step of `scripts/mesa-android-build.sh`, run in the container from",
         f"`tools/Dockerfile.mesa-android` (NDK {pv('ndk')}); both are in `{B}.tar.xz`.", "",
         "```bash",
         f"tar -xJf {B}.tar.xz && tar -xJf {U}.tar.xz",
         f"docker build -t openbook-mesa-android -f {B}/tools/Dockerfile.mesa-android {B}/tools",
         "mkdir -p mesa logs",
         "docker run --rm -u $(id -u):$(id -g) -e HOME=/a/mesa -v $PWD/mesa:/a/mesa -v $PWD/logs:/a/logs \\",
         f"  -v $PWD/{B}:/repo:ro openbook-mesa-android /repo/scripts/mesa-android-build.sh deps -- upstream",
         f"diff -r --no-dereference -x .git mesa/src/deps/elfutils {U}/mesa-build/elfutils && echo same source",
         "```", "",
         "The `deps` step fetches elfutils at the pinned commit from android.googlesource.com; the `diff` shows it is",
         f"the tree in `{U}.tar.xz`. The library is `mesa/deps/x86_64-api37/lib/libelf_mesa.so`; the image's copy is",
         "the same file stripped with the NDK's `llvm-strip --strip-unneeded`.", "",
         "**Installing a rebuilt libelf.** The image loads it as `/vendor/lib64/libelf_mesa.so` in the `vendor`",
         "partition. OpenBook put it there with `scripts/graphics-amd-stage-mesa.sh`, which copies the Mesa build's",
         "`vendor/` output into the Android tree with a generated `Android.bp` (one prebuilt module per library, its",
         "dependencies taken from the library's own `DT_NEEDED`), and `device/anybook/common/graphics-amd/graphics-amd.mk`,",
         "which adds those modules to the product. On a running OpenBook, which is a `userdebug` build, Android's usual",
         "developer route replaces it in place: `adb root`, `adb disable-verity`, reboot, then `adb root`, `adb remount`,",
         "`adb push libelf_mesa.so /vendor/lib64/` and reboot. OpenBook has not tested that route.", "",
         "Mesa (MIT) is in the userspace tarball as built, with OpenBook's patches applied, for rebuilding it against",
         "a changed libelf. Copy it in and run the script's other steps the same way; Meson downloads libdrm through",
         "its wrap. The tarball has no git history, so pass Mesa's commit for the version string the libraries carry:",
         "",
         "```bash",
         f"cp -a {U}/mesa-build/mesa mesa/src/upstream",
         f"docker run --rm -u $(id -u):$(id -g) -e HOME=/a/mesa -e MESA_GIT_SHA1_OVERRIDE={msha} \\",
         "  -v $PWD/mesa:/a/mesa -v $PWD/logs:/a/logs \\",
         f"  -v $PWD/{B}:/repo:ro openbook-mesa-android /repo/scripts/mesa-android-build.sh setup build install -- upstream",
         "```", "",
         f"OpenBook's Mesa patches are in `{B}.tar.xz` under `mesa/patches/upstream/`.", ""] + \
        ([open(a.mesa_note).read().rstrip(), ""] if a.mesa_note else []) + [
         "```"] + [l for l in mprov.split("\n\n")[0].splitlines() if not l.startswith(("from:", "staged:"))] + ["```", "",
         "## The Android projects", "",
         "These are built by AOSP's own build system from their `Android.bp` files, for OpenBook's",
         "`anybook_g14_x86_64` product (`userdebug`). The product and board files that set the compile options",
         f"(`TARGET_ARCH := x86_64`, `TARGET_ARCH_VARIANT := silvermont`) are in `{B}.tar.xz` under",
         "`device/anybook/`. To rebuild one of them, check out AOSP at `aosp-manifest.xml`, replace the project with",
         "the tree from the userspace tarball, and build its module for an x86_64 target with the same architecture",
         "variant, for example `m iptables`.", "",
         "From the image's own NOTICE files.", "",
         "| Source | Licence texts | Binaries in the image |", "|---|---|---|"]
    for p in s["included"]:
        L.append(f"| `{p['project']}` | {p['kinds']} | {', '.join('`' + f + '`' for f in p['files'][:6])}"
                 f"{' …' if len(p['files']) > 6 else ''} |")
    L += ["", "```", urev, "```", "",
          "### Licence texts that name the GPL but need no source here", "",
          "These binaries' notices carry a GPL or LGPL text for a component that is not under it in the binary, so",
          "the source is not included above. All of the Android ones are public at the revisions in",
          "`aosp-manifest.xml`.", "",
          "| Source | Binaries | Why |", "|---|---|---|"]
    for p in s["not_included"]:
        L.append(f"| `{p['project']}` | {len(p['files'])}: {', '.join('`' + f + '`' for f in p['files'][:3])}"
                 f"{' …' if len(p['files']) > 3 else ''} | {p['why']} |")
    L += ["", "## systemd-boot", "",
          f"The loader on the image's EFI partition is Arch Linux's build of {a.loader}. `{SB}.tar.xz` holds systemd's",
          "upstream source at that tag and Arch's packaging (PKGBUILD and patches), with their hashes and URLs in",
          "`README.txt` and `SHA256SUMS.download`. Build it with Arch's `makepkg` from the packaging.", "",
          f"## Files in `{B}.tar.xz`", "", "```"] + files + ["```", "",
          f"If something here is missing or wrong, tell us at {a.contact} and we will publish it. This offer is valid",
          f"for three years from the release date, for anyone who has the image. The release files are at {a.home}."]
    open(a.out, "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
