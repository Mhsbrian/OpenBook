# SPDX-License-Identifier: GPL-2.0
# AnyBook (ANAL-297): NVIDIA's open kernel modules as external vendor modules (see BUILD.bazel). Kleaf's kernel_module
# runs `make -C <this directory> M=... O=... MO=... KERNEL_SRC=...`, then the same with modules_install. NVIDIA's
# build has two halves, and both run here:
#   1. nv-kernel.o and nv-modeset-kernel.o, the OS-independent cores, with NVIDIA's own makefiles (not Kbuild), into
#      their own _out/ directories. Kleaf runs this in a sandbox, so those are written into the sandbox's copy of the
#      source tree. (An absolute output directory under $(MO) makes the core's link command longer than the 128 KiB a
#      single shell argument may be: about 1,500 objects.)
#   2. kernel-open/ with Kbuild, which links those objects into nvidia.ko and nvidia-modeset.ko, and builds
#      nvidia-drm.ko.
NV_SRC     := $(CURDIR)/open-gpu-kernel-modules
CORE_O     := $(NV_SRC)/src/nvidia/_out/Linux_x86_64/nv-kernel.o
MODESET_O  := $(NV_SRC)/src/nvidia-modeset/_out/Linux_x86_64/nv-modeset-kernel.o
KOPEN      := $(M)/open-gpu-kernel-modules/kernel-open
KOPEN_MO   := $(MO)/open-gpu-kernel-modules/kernel-open
NV_MODULES := nvidia nvidia-modeset nvidia-drm

# The cores share the kernel's code generation where it matters for loading and calling them, read from the kernel's
# configuration (kernel/patches/nvidia-open/0005 hands them to NVIDIA's makefiles as NV_KERNEL_CORE_CFLAGS; Clang's
# retpoline and return-thunk flags come from that patch itself):
#   CONFIG_CFI           kCFI type hashes on the cores' functions, which the kernel and kernel-open call through
#                        pointers, without checks at the cores' own indirect calls (kcfi-hash-only.txt)
#   CONFIG_CALL_PADDING  the function padding the kernel patches into (FineIBT, call depth tracking)
#   CONFIG_MITIGATION_RETPOLINE  -mindirect-branch-cs-prefix, so every retpoline call site can be rewritten in place
#   CONFIG_ZERO_CALL_USED_REGS   zeroing of call-used registers on return
include $(O)/include/config/auto.conf
CORE_CFLAGS :=
ifeq ($(CONFIG_CFI),y)
CORE_CFLAGS += -fsanitize=kcfi -fsanitize-ignorelist=$(CURDIR)/kcfi-hash-only.txt
ifeq ($(CONFIG_CFI_ICALL_NORMALIZE_INTEGERS),y)
CORE_CFLAGS += -fsanitize-cfi-icall-experimental-normalize-integers
endif
endif
ifeq ($(CONFIG_CALL_PADDING),y)
CORE_CFLAGS += -fpatchable-function-entry=$(CONFIG_FUNCTION_PADDING_BYTES),$(CONFIG_FUNCTION_PADDING_BYTES)
endif
ifneq ($(CONFIG_FUNCTION_ALIGNMENT),)
CORE_CFLAGS += -falign-functions=$(CONFIG_FUNCTION_ALIGNMENT)
endif
ifeq ($(CONFIG_MITIGATION_RETPOLINE),y)
CORE_CFLAGS += -mindirect-branch-cs-prefix
endif
ifeq ($(CONFIG_ZERO_CALL_USED_REGS),y)
CORE_CFLAGS += -fzero-call-used-regs=used-gpr
endif

# NVIDIA's makefiles with the kernel's Clang and LLVM tools (on PATH under Kleaf; CXX for the C++ DisplayPort library
# in nv-modeset-kernel.o, which would otherwise be the host's g++), and a fixed build identity and date in the
# "nvidia id" string, so the objects are reproducible.
CORE_ARGS = TARGET_ARCH=x86_64 CC=clang CXX=clang++ LD=ld.lld AR=llvm-ar OBJCOPY=llvm-objcopy \
            NV_BUILD_USER=anybook NV_BUILD_HOST=kleaf DATE="echo 2026-10-26" NV_KERNEL_CORE_CFLAGS="$(CORE_CFLAGS)"

# What NVIDIA's kernel-open/Makefile would pass to Kbuild, without that wrapper (it calls uname and its own pahole
# script). The cores are linked from where NVIDIA's makefiles put them, without kernel-open's *.o_binary symlinks.
# NV_ANDROID_GKI_VFS_NAMESPACE: kernel/patches/nvidia-open/0003. IGNORE_CC_MISMATCH: NVIDIA's conftest compares
# compiler version strings, and the kernel's names LLD as well.
KOPEN_ARGS = M=$(KOPEN) MO=$(KOPEN_MO) NV_KERNEL_SOURCES=$(KERNEL_SRC) NV_KERNEL_OUTPUT=$(O) \
             NV_KERNEL_MODULES="$(NV_MODULES)" NV_SPECTRE_V2=0 \
             NVIDIA_BINARY_OBJECT=$(CORE_O) NVIDIA_MODESET_BINARY_OBJECT=$(MODESET_O) \
             NV_ANDROID_GKI_VFS_NAMESPACE=ANDROID_GKI_VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver
export IGNORE_CC_MISMATCH := 1

modules:
	$(MAKE) -C $(NV_SRC)/src/nvidia $(CORE_ARGS)
	$(MAKE) -C $(NV_SRC)/src/nvidia-modeset $(CORE_ARGS)
	$(MAKE) -C $(KERNEL_SRC) $(KBUILD_OPTIONS) $(KOPEN_ARGS) modules
	cp $(KOPEN_MO)/Module.symvers $(MO)/Module.symvers

modules_install:
	$(MAKE) -C $(KERNEL_SRC) $(KBUILD_OPTIONS) $(KOPEN_ARGS) modules_install

clean:
	$(MAKE) -C $(KERNEL_SRC) $(KOPEN_ARGS) clean
	rm -rf $(NV_SRC)/src/nvidia/_out $(NV_SRC)/src/nvidia-modeset/_out

.PHONY: modules modules_install clean
