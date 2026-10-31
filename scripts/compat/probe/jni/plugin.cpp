// Second library that libprobe.so dlopen()s at runtime (ANAL-180): symbol lookup, constructors,
// dynamic TLS, and C++ exceptions crossing a library boundary.
#include <stdexcept>

static int g_ctor_ran;
__attribute__((constructor)) static void plugin_init() { g_ctor_ran = 1; }

extern "C" __attribute__((visibility("default"))) int plugin_compute(int x) { return x * 3 + 1; }
extern "C" __attribute__((visibility("default"))) int plugin_ctor_ran() { return g_ctor_ran; }
extern "C" __attribute__((visibility("default"))) int plugin_tls_counter() {
  static thread_local int c;
  return ++c;
}
extern "C" __attribute__((visibility("default"))) void plugin_throw(const char* msg) { throw std::runtime_error(msg); }
