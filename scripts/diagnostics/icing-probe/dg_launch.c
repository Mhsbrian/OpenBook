// SPDX-License-Identifier: Apache-2.0
//
// ANAL-234: start an arm64 executable through a Digitalis libberberis_arm64.so
// with an explicit guest linker and vdso.
//
// Berberis' own program runner ignores -l/-s on x86_64 (upstream TODO
// b/276787135) and falls back to /system/bin/berberis/arm64/linker64. Ruby
// ships Google's guest linker there, so a Digitalis run on Ruby would mix two
// translators' guest environments. This launcher calls the same exported entry
// points as the runner's Run(), passing the paths explicitly.
//
// usage: dg_launch LIBBERBERIS GUEST_LINKER GUEST_VDSO EXECUTABLE [ARGS...]

#include <dlfcn.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>

typedef void (*init_fn)(void);
// berberis::GuestLoader::StartExecutable(const char*, const char*, const char*, size_t,
//                                        const char**, char**, std::string*)
typedef void (*start_fn)(const char*, const char*, const char*, size_t, const char**, char**, void*);

int main(int argc, char** argv, char** envp) {
  if (argc < 5) {
    fprintf(stderr, "usage: %s LIBBERBERIS GUEST_LINKER GUEST_VDSO EXECUTABLE [ARGS...]\n", argv[0]);
    return 2;
  }
  void* lib = dlopen(argv[1], RTLD_NOW | RTLD_GLOBAL);
  if (!lib) {
    fprintf(stderr, "dg_launch: %s\n", dlerror());
    return 2;
  }
  init_fn init = (init_fn)dlsym(lib, "_ZN8berberis12InitBerberisEv");
  start_fn start = (start_fn)dlsym(lib,
      "_ZN8berberis11GuestLoader15StartExecutableEPKcS2_S2_mPS2_PPcPNSt3__112basic_stringIcNS6_11"
      "char_traitsIcEENS6_9allocatorIcEEEE");
  if (!init || !start) {
    fprintf(stderr, "dg_launch: entry points not found\n");
    return 2;
  }
  char exe[PATH_MAX];
  if (!realpath(argv[4], exe)) {
    perror(argv[4]);
    return 2;
  }
  // A zeroed libc++ std::string is a valid empty string; only written on failure.
  static unsigned char error_msg[64];
  init();
  start(exe, argv[3], argv[2], (size_t)(argc - 4), (const char**)(argv + 4), envp, error_msg);
  fprintf(stderr, "dg_launch: guest did not start\n");
  return 1;
}
