// AnyBook ARM-compat probe, native part (ANAL-180).
// The same source is built for arm64-v8a, armeabi-v7a and x86_64. Each test returns
// "PASS|FAIL|SKIP checks=N [failed=a,b] <info>". ARM-only semantics tests SKIP on x86_64; the x86_64
// build is the native control that validates the probe's own reference implementations.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <jni.h>
#include <android/log.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <fenv.h>
#include <link.h>
#include <math.h>
#include <pthread.h>
#include <sched.h>
#include <setjmp.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/auxv.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <sys/utsname.h>
#include <time.h>
#include <ucontext.h>
#include <unistd.h>
#include <unwind.h>
#include <alloca.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>

#include <atomic>
#include <condition_variable>
#include <exception>
#include <future>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#if defined(__aarch64__) || defined(__arm__)
#include <arm_neon.h>
#include <asm/hwcap.h>
#endif
#if defined(__aarch64__)
#include <arm_acle.h>
#endif
#if defined(__x86_64__)
#include <immintrin.h>
#endif

#if defined(__aarch64__)
#define ABI "arm64-v8a"
#elif defined(__arm__)
#define ABI "armeabi-v7a"
#elif defined(__x86_64__)
#define ABI "x86_64"
#else
#define ABI "unknown"
#endif

#define LOG(...) __android_log_print(ANDROID_LOG_INFO, "AnyBookProbe", __VA_ARGS__)
// Keep the compiler from constant-folding test inputs: the instruction under test must really run.
#define CLOBBER(p) asm volatile("" : : "r"(p) : "memory")

static std::string F(const char* fmt, ...) {
  char b[1024];
  va_list a;
  va_start(a, fmt);
  vsnprintf(b, sizeof b, fmt, a);
  va_end(a);
  return b;
}

struct Res {
  std::vector<std::string> failed;
  std::string info;
  int n = 0;
  bool check(bool ok, const char* name) {
    n++;
    if (!ok) failed.push_back(name);
    return ok;
  }
  void add(const std::string& s) {
    if (!info.empty()) info += ' ';
    info += s;
  }
  std::string str() const {
    std::string r = failed.empty() ? "PASS" : "FAIL";
    r += " checks=" + std::to_string(n);
    if (!failed.empty()) {
      r += " failed=";
      for (size_t i = 0; i < failed.size(); i++) r += (i ? "," : "") + failed[i];
    }
    if (!info.empty()) r += " " + info;
    for (auto& c : r)
      if (c == '\n' || c == '\r' || c == '\t') c = ' ';
    return r;
  }
};

static std::string read_file(const char* p, size_t max = 1 << 20) {
  int fd = open(p, O_RDONLY | O_CLOEXEC);
  if (fd < 0) return "";
  std::string s;
  char b[4096];
  ssize_t n;
  while (s.size() < max && (n = read(fd, b, sizeof b)) > 0) s.append(b, n);
  close(fd);
  return s;
}

static std::string line_with(const std::string& s, const char* key) {
  size_t p = s.find(key);
  if (p == std::string::npos) return "";
  size_t e = s.find('\n', p);
  return s.substr(p, e == std::string::npos ? std::string::npos : e - p);
}

static std::string clean(std::string s, size_t max = 160) {
  if (s.size() > max) s.resize(max);
  for (auto& c : s)
    if (c == '\n' || c == '\t' || c == ',' || c == '|') c = ' ';
  return s;
}

// Run fn; if it raises SIGILL/SIGSEGV/SIGBUS/SIGFPE/SIGTRAP, return the signal number instead of dying.
static sigjmp_buf g_guard_jb;
static volatile sig_atomic_t g_guard_sig;
static void guard_handler(int sig, siginfo_t*, void*) {
  g_guard_sig = sig;
  siglongjmp(g_guard_jb, 1);
}
template <class Fn>
static int guarded(Fn fn) {
  const int sigs[] = {SIGILL, SIGSEGV, SIGBUS, SIGFPE, SIGTRAP};
  struct sigaction sa = {}, old[5];
  sa.sa_sigaction = guard_handler;
  sa.sa_flags = SA_SIGINFO | SA_NODEFER;
  sigemptyset(&sa.sa_mask);
  for (int i = 0; i < 5; i++) sigaction(sigs[i], &sa, &old[i]);
  g_guard_sig = 0;
  int r = 0;
  if (sigsetjmp(g_guard_jb, 1) == 0)
    fn();
  else
    r = g_guard_sig;
  for (int i = 0; i < 5; i++) sigaction(sigs[i], &old[i], nullptr);
  return r;
}

static inline float f_of(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }
static inline uint32_t u_of(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static inline double d_of(uint64_t u) { double d; memcpy(&d, &u, 8); return d; }
static inline uint64_t u_of(double d) { uint64_t u; memcpy(&u, &d, 8); return u; }

// ---------------------------------------------------------------------------------------------
// abi: what the process looks like from the inside
static std::string hwcap_names() {
#if defined(__aarch64__)
  static const char* n[] = {"fp", "asimd", "evtstrm", "aes", "pmull", "sha1", "sha2", "crc32", "atomics", "fphp", "asimdhp",
                            "cpuid", "asimdrdm", "jscvt", "fcma", "lrcpc", "dcpop", "sha3", "sm3", "sm4", "asimddp", "sha512",
                            "sve", "asimdfhm", "dit", "uscat", "ilrcpc", "flagm", "ssbs", "sb", "paca", "pacg"};
  unsigned long h = getauxval(AT_HWCAP);
  std::string s;
  for (int i = 0; i < 32; i++)
    if (h & (1UL << i)) s += (s.empty() ? "" : "+") + std::string(n[i]);
  return s + F("(hwcap2=0x%lx)", getauxval(AT_HWCAP2));
#else
  return F("0x%lx/0x%lx", getauxval(AT_HWCAP), getauxval(AT_HWCAP2));
#endif
}

static std::string t_abi(const char*) {
  Res r;
  utsname u;
  uname(&u);
  char exe[256] = {};
  readlink("/proc/self/exe", exe, sizeof exe - 1);
  std::string ci = read_file("/proc/cpuinfo");
  std::string feat = line_with(ci, "Features");
  if (feat.empty()) feat = line_with(ci, "flags");
  std::string model = line_with(ci, "CPU implementer");
  if (model.empty()) model = line_with(ci, "model name");
  const char* plat = (const char*)getauxval(AT_PLATFORM);
  r.add(F("abi=%s uname.machine=%s at_platform=%s exe=%s pagesz=%lu hwcap=%s", ABI, u.machine, plat ? plat : "?", exe,
          getauxval(AT_PAGESZ), hwcap_names().c_str()));
  r.add("cpuinfo=[" + clean(model, 60) + " / " + clean(feat, 200) + "]");
  r.check(getauxval(AT_PAGESZ) == (unsigned long)sysconf(_SC_PAGESIZE), "pagesz_consistent");
  // Go's x/sys/cpu, cpu_features and others parse /proc/self/auxv instead of calling getauxval().
  std::string auxv = read_file("/proc/self/auxv");
  unsigned long file_hwcap = 0;
  bool found = false;
  for (size_t o = 0; o + 2 * sizeof(unsigned long) <= auxv.size(); o += 2 * sizeof(unsigned long)) {
    unsigned long kv[2];
    memcpy(kv, auxv.data() + o, sizeof kv);
    if (kv[0] == AT_HWCAP) { file_hwcap = kv[1]; found = true; break; }
  }
  // Info only: Android apps cannot read it on x86_64 either, which is what sends Go to the MRS fallback.
  r.add(found ? F("proc_auxv_hwcap=0x%lx(%s)", file_hwcap, file_hwcap == getauxval(AT_HWCAP) ? "matches" : "differs")
              : std::string("proc_auxv=unreadable"));
#if defined(__aarch64__)
  r.check(getauxval(AT_HWCAP) & HWCAP_ASIMD, "hwcap_asimd");
  r.check(!strcmp(u.machine, "aarch64"), "uname_aarch64");
#elif defined(__arm__)
  r.check(getauxval(AT_HWCAP) & HWCAP_NEON, "hwcap_neon");
#endif
  return r.str();
}

// ---------------------------------------------------------------------------------------------
// neon: Advanced SIMD integer/float ops checked against scalar references
static std::string t_neon(const char*) {
#if defined(__aarch64__) || defined(__arm__)
  Res r;
  float a[16], b[16], c[16];
  for (int i = 0; i < 16; i++) {
    a[i] = i * 1.25f - 3.0f;
    b[i] = 0.5f + i * 0.75f;
  }
  CLOBBER(a); CLOBBER(b);
  for (int i = 0; i < 16; i += 4) {
    float32x4_t x = vld1q_f32(a + i), y = vld1q_f32(b + i);
    vst1q_f32(c + i, vaddq_f32(vmulq_f32(x, y), x));
  }
  bool ok = true;
  for (int i = 0; i < 16; i++) {
    float ref = a[i] * b[i];
    ref = ref + a[i];
    ok &= u_of(ref) == u_of(c[i]);
  }
  r.check(ok, "f32_mul_add");

  int8_t s8[16]; uint8_t u8a[16], u8b[16]; int16_t s16[8], m16[8];
  for (int i = 0; i < 16; i++) { s8[i] = 100; u8a[i] = 10; u8b[i] = 20; }
  for (int i = 0; i < 8; i++) { s16[i] = 0x4000; m16[i] = -32768; }
  CLOBBER(s8); CLOBBER(u8a); CLOBBER(u8b); CLOBBER(s16); CLOBBER(m16);
  r.check(vgetq_lane_s8(vqaddq_s8(vld1q_s8(s8), vld1q_s8(s8)), 0) == 127, "sqadd_s8_saturate");
  r.check(vgetq_lane_u8(vqsubq_u8(vld1q_u8(u8a), vld1q_u8(u8b)), 3) == 0, "uqsub_u8_saturate");
  r.check(vgetq_lane_s16(vqrdmulhq_s16(vld1q_s16(s16), vld1q_s16(s16)), 0) == 0x2000, "sqrdmulh_s16");
  r.check(vgetq_lane_s16(vqdmulhq_s16(vld1q_s16(m16), vld1q_s16(m16)), 0) == 32767, "sqdmulh_saturate");

  uint8_t pin[16], pout[16];
  for (int i = 0; i < 16; i++) pin[i] = (uint8_t)(i * 37 + 11);
  CLOBBER(pin);
  vst1q_u8(pout, vcntq_u8(vld1q_u8(pin)));
  ok = true;
  for (int i = 0; i < 16; i++) ok &= pout[i] == __builtin_popcount(pin[i]);
  r.check(ok, "cnt_u8");

  uint8_t rgb[48], g[16];
  for (int i = 0; i < 48; i++) rgb[i] = (uint8_t)i;
  CLOBBER(rgb);
  uint8x16x3_t d = vld3q_u8(rgb);
  vst1q_u8(g, d.val[1]);
  ok = true;
  for (int i = 0; i < 16; i++) ok &= g[i] == 3 * i + 1;
  r.check(ok, "ld3_deinterleave");

  vst1q_u8(pout, vrev64q_u8(vld1q_u8(pin)));
  r.check(pout[0] == pin[7] && pout[8] == pin[15], "rev64_u8");

  uint8_t tbl[8] = {10, 11, 12, 13, 14, 15, 16, 17}, idx[8] = {0, 7, 3, 8, 255, 1, 2, 6}, tlo[8];
  CLOBBER(tbl); CLOBBER(idx);
  vst1_u8(tlo, vtbl1_u8(vld1_u8(tbl), vld1_u8(idx)));
  r.check(tlo[0] == 10 && tlo[1] == 17 && tlo[2] == 13 && tlo[3] == 0 && tlo[4] == 0, "tbl_out_of_range_zero");

  float cv[4] = {1e20f, -1e20f, NAN, 2.75f};
  int32_t co[4];
  CLOBBER(cv);
  vst1q_s32(co, vcvtq_s32_f32(vld1q_f32(cv)));
  r.check(co[0] == INT32_MAX && co[1] == INT32_MIN && co[2] == 0 && co[3] == 2, "fcvtzs_vector_saturate");
  r.add(F("cvt=[%d %d %d %d]", co[0], co[1], co[2], co[3]));

  float one[4] = {1.0f, 1.0f, 1.0f, 1.0f}, re[4];
  CLOBBER(one);
  vst1q_f32(re, vrecpeq_f32(vld1q_f32(one)));
  r.add(F("frecpe(1.0)=0x%08x", u_of(re[0])));
  r.check(u_of(re[0]) == 0x3f7f8000, "frecpe_bit_exact");

#if defined(__aarch64__)
  uint8_t qt[16], qi[16], qo[16];
  for (int i = 0; i < 16; i++) { qt[i] = (uint8_t)(200 + i); qi[i] = (uint8_t)(i == 5 ? 16 : 15 - i); }
  CLOBBER(qt); CLOBBER(qi);
  vst1q_u8(qo, vqtbl1q_u8(vld1q_u8(qt), vld1q_u8(qi)));
  r.check(qo[0] == 215 && qo[5] == 0 && qo[15] == 200, "tbl_q_u8");
  double dd[2] = {2.0, 9.0}, dr[2];
  CLOBBER(dd);
  vst1q_f64(dr, vsqrtq_f64(vld1q_f64(dd)));
  r.check(dr[0] == sqrt(2.0) && dr[1] == 3.0, "fsqrt_f64x2");
  uint32_t sv[4] = {1, 2, 3, 0xfffffff0u};
  CLOBBER(sv);
  r.check(vaddvq_u32(vld1q_u32(sv)) == 0xfffffff6u, "addv_u32");
  r.check(vmaxvq_u32(vld1q_u32(sv)) == 0xfffffff0u, "umaxv_u32");
  float fv[4] = {1.0f, -2.0f, NAN, 3.0f};
  CLOBBER(fv);
  r.check(vmaxnmvq_f32(vld1q_f32(fv)) == 3.0f, "fmaxnmv_ignores_nan");
#endif
  return r.str();
#else
  return "SKIP not an ARM build";
#endif
}

// ---------------------------------------------------------------------------------------------
// crypto: AES / PMULL / CRC32 / dot-product instructions vs software references.
// On x86_64 the same references are checked against AES-NI / PCLMUL / SSE4.2, which validates them.
static const uint8_t SBOX[256] = {
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76, 0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59,
    0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0, 0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1,
    0x71, 0xd8, 0x31, 0x15, 0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75, 0x09, 0x83,
    0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84, 0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b,
    0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf, 0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c,
    0x9f, 0xa8, 0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2, 0xcd, 0x0c, 0x13, 0xec,
    0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73, 0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee,
    0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb, 0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08, 0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6,
    0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a, 0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9,
    0x86, 0xc1, 0x1d, 0x9e, 0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf, 0x8c, 0xa1,
    0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16};
static uint8_t xt(uint8_t x) { return (uint8_t)((x << 1) ^ ((x & 0x80) ? 0x1b : 0)); }
// AESE: SubBytes(ShiftRows(state ^ key)); byte i of the vector is state[row i%4][col i/4].
static void ref_aese(uint8_t s[16], const uint8_t k[16]) {
  uint8_t t[16];
  for (int i = 0; i < 16; i++) t[i] = s[i] ^ k[i];
  for (int c = 0; c < 4; c++)
    for (int r = 0; r < 4; r++) s[r + 4 * c] = SBOX[t[r + 4 * ((c + r) & 3)]];
}
static void ref_aesmc(uint8_t s[16]) {
  for (int c = 0; c < 4; c++) {
    uint8_t* a = s + 4 * c;
    uint8_t a0 = a[0], a1 = a[1], a2 = a[2], a3 = a[3];
    a[0] = xt(a0) ^ (xt(a1) ^ a1) ^ a2 ^ a3;
    a[1] = a0 ^ xt(a1) ^ (xt(a2) ^ a2) ^ a3;
    a[2] = a0 ^ a1 ^ xt(a2) ^ (xt(a3) ^ a3);
    a[3] = (xt(a0) ^ a0) ^ a1 ^ a2 ^ xt(a3);
  }
}
static void ref_clmul(uint64_t a, uint64_t b, uint64_t* lo, uint64_t* hi) {
  uint64_t l = 0, h = 0;
  for (int i = 0; i < 64; i++)
    if ((b >> i) & 1) {
      l ^= a << i;
      if (i) h ^= a >> (64 - i);
    }
  *lo = l;
  *hi = h;
}
static uint32_t ref_crc32(const uint8_t* p, size_t n, uint32_t poly) {
  uint32_t c = 0xffffffffu;
  for (size_t i = 0; i < n; i++) {
    c ^= p[i];
    for (int k = 0; k < 8; k++) c = (c >> 1) ^ (poly & (0u - (c & 1)));
  }
  return ~c;
}

#if defined(__aarch64__)
__attribute__((target("aes"))) static void hw_aese_mc(uint8_t s[16], const uint8_t k[16]) {
  vst1q_u8(s, vaesmcq_u8(vaeseq_u8(vld1q_u8(s), vld1q_u8(k))));
}
__attribute__((target("aes"))) static void hw_pmull(uint64_t a, uint64_t b, uint64_t* lo, uint64_t* hi) {
  poly128_t p = vmull_p64((poly64_t)a, (poly64_t)b);
  *lo = (uint64_t)p;
  *hi = (uint64_t)(p >> 64);
}
__attribute__((target("crc"))) static uint32_t hw_crc32(const uint8_t* p, size_t n, bool castagnoli) {
  uint32_t c = 0xffffffffu;
  for (size_t i = 0; i < n; i++) c = castagnoli ? __crc32cb(c, p[i]) : __crc32b(c, p[i]);
  return ~c;
}
__attribute__((target("dotprod"))) static void hw_udot(const uint8_t* a, const uint8_t* b, uint32_t out[4]) {
  vst1q_u32(out, vdotq_u32(vdupq_n_u32(1), vld1q_u8(a), vld1q_u8(b)));
}
#elif defined(__x86_64__)
__attribute__((target("aes"))) static void hw_aesenc_zero(uint8_t s[16]) {
  // AESENC(s, 0) = MixColumns(SubBytes(ShiftRows(s)))
  _mm_storeu_si128((__m128i*)s, _mm_aesenc_si128(_mm_loadu_si128((const __m128i*)s), _mm_setzero_si128()));
}
__attribute__((target("pclmul,sse4.1"))) static void hw_pmull(uint64_t a, uint64_t b, uint64_t* lo, uint64_t* hi) {
  __m128i r = _mm_clmulepi64_si128(_mm_cvtsi64_si128((long long)a), _mm_cvtsi64_si128((long long)b), 0);
  *lo = (uint64_t)_mm_cvtsi128_si64(r);
  *hi = (uint64_t)_mm_extract_epi64(r, 1);
}
__attribute__((target("sse4.2"))) static uint32_t hw_crc32c(const uint8_t* p, size_t n) {
  uint32_t c = 0xffffffffu;
  for (size_t i = 0; i < n; i++) c = _mm_crc32_u8(c, p[i]);
  return ~c;
}
#endif

static std::string t_crypto(const char*) {
  Res r;
  const uint8_t* msg = (const uint8_t*)"123456789";
  // The references themselves must match the published check values.
  r.check(ref_crc32(msg, 9, 0xedb88320u) == 0xcbf43926u, "ref_crc32_check_value");
  r.check(ref_crc32(msg, 9, 0x82f63b78u) == 0xe3069283u, "ref_crc32c_check_value");
  [[maybe_unused]] uint8_t st[16], key[16], ref[16];
  for (int i = 0; i < 16; i++) { st[i] = (uint8_t)(i * 17 + 3); key[i] = (uint8_t)(0xa5 ^ (i * 29)); }
  [[maybe_unused]] uint64_t A = 0x8000000000000001ull, B = 0xd1b71758e219652cull, rl, rh, hl = 0, hh = 0;
  ref_clmul(A, B, &rl, &rh);
#if defined(__aarch64__)
  unsigned long h = getauxval(AT_HWCAP);
  std::string present;
  if (h & HWCAP_AES) {
    present += "aes ";
    memcpy(ref, st, 16);
    ref_aese(ref, key);
    ref_aesmc(ref);
    uint8_t hw[16];
    memcpy(hw, st, 16);
    CLOBBER(hw);
    int sig = guarded([&] { hw_aese_mc(hw, key); });
    r.check(sig == 0 && !memcmp(hw, ref, 16), "aese_aesmc");
  }
  if (h & HWCAP_PMULL) {
    present += "pmull ";
    int sig = guarded([&] { hw_pmull(A, B, &hl, &hh); });
    r.check(sig == 0 && hl == rl && hh == rh, "pmull_64");
  }
  if (h & HWCAP_CRC32) {
    present += "crc32 ";
    uint32_t c1 = 0, c2 = 0;
    int sig = guarded([&] { c1 = hw_crc32(msg, 9, false); c2 = hw_crc32(msg, 9, true); });
    r.check(sig == 0 && c1 == 0xcbf43926u && c2 == 0xe3069283u, "crc32_crc32c");
  }
  if (h & HWCAP_ASIMDDP) {
    present += "dotprod ";
    uint8_t a[16], b[16];
    uint32_t o[4] = {};
    for (int i = 0; i < 16; i++) { a[i] = (uint8_t)(250 - i); b[i] = (uint8_t)(i + 3); }
    int sig = guarded([&] { hw_udot(a, b, o); });
    bool ok = sig == 0;
    for (int l = 0; l < 4; l++) {
      uint32_t s = 1;
      for (int k = 0; k < 4; k++) s += (uint32_t)a[4 * l + k] * b[4 * l + k];
      ok &= o[l] == s;
    }
    r.check(ok, "udot");
  }
  r.add("present=[" + present + "]");
  return r.str();
#elif defined(__x86_64__)
  memcpy(ref, st, 16);
  ref_aese(ref, (const uint8_t*)"\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0");
  ref_aesmc(ref);
  if (__builtin_cpu_supports("aes")) {
    uint8_t hw[16];
    memcpy(hw, st, 16);
    hw_aesenc_zero(hw);
    r.check(!memcmp(hw, ref, 16), "aesenc_matches_reference");
  }
  if (__builtin_cpu_supports("pclmul")) {
    hw_pmull(A, B, &hl, &hh);
    r.check(hl == rl && hh == rh, "pclmul_matches_reference");
  }
  if (__builtin_cpu_supports("sse4.2")) r.check(hw_crc32c(msg, 9) == 0xe3069283u, "crc32c_sse42");
  return r.str();
#else
  return "SKIP no crypto test for this ABI";
#endif
}

// ---------------------------------------------------------------------------------------------
// isa: AArch64 semantics a translator must reproduce exactly (x86 behaves differently for each one)
#if defined(__aarch64__)
#define A64_F2(name, ins)                                                                    \
  static float name(float a, float b) {                                                      \
    float r;                                                                                 \
    asm volatile(ins " %s0, %s1, %s2" : "=w"(r) : "w"(a), "w"(b));                           \
    return r;                                                                                \
  }
A64_F2(a_fadd, "fadd")
A64_F2(a_fmul, "fmul")
A64_F2(a_fmax, "fmax")
A64_F2(a_fmaxnm, "fmaxnm")
A64_F2(a_fmin, "fmin")
static double a_dadd(double a, double b) { double r; asm volatile("fadd %d0, %d1, %d2" : "=w"(r) : "w"(a), "w"(b)); return r; }
static double a_fmadd(double a, double b, double c) {
  double r;
  asm volatile("fmadd %d0, %d1, %d2, %d3" : "=w"(r) : "w"(a), "w"(b), "w"(c));
  return r;
}
static int32_t a_fcvtzs(float f) { int32_t r; asm volatile("fcvtzs %w0, %s1" : "=r"(r) : "w"(f)); return r; }
static uint32_t a_fcvtzu(float f) { uint32_t r; asm volatile("fcvtzu %w0, %s1" : "=r"(r) : "w"(f)); return r; }
static int64_t a_fcvtzs_d(double d) { int64_t r; asm volatile("fcvtzs %x0, %d1" : "=r"(r) : "w"(d)); return r; }
static int32_t a_fcvtas(float f) { int32_t r; asm volatile("fcvtas %w0, %s1" : "=r"(r) : "w"(f)); return r; }
static float a_frinta(float f) { float r; asm volatile("frinta %s0, %s1" : "=w"(r) : "w"(f)); return r; }
static float a_frintn(float f) { float r; asm volatile("frintn %s0, %s1" : "=w"(r) : "w"(f)); return r; }
static uint16_t a_fcvt_h(float f) {
  uint16_t r;
  asm volatile("fcvt h0, %s1\n fmov %w0, s0" : "=r"(r) : "w"(f) : "v0");
  return r;
}
static int32_t a_sdiv(int32_t a, int32_t b) { int32_t r; asm volatile("sdiv %w0, %w1, %w2" : "=r"(r) : "r"(a), "r"(b)); return r; }
static int64_t a_sdiv64(int64_t a, int64_t b) { int64_t r; asm volatile("sdiv %x0, %x1, %x2" : "=r"(r) : "r"(a), "r"(b)); return r; }
static uint32_t a_udiv(uint32_t a, uint32_t b) { uint32_t r; asm volatile("udiv %w0, %w1, %w2" : "=r"(r) : "r"(a), "r"(b)); return r; }
static uint32_t a_clz(uint32_t x) { uint32_t r; asm volatile("clz %w0, %w1" : "=r"(r) : "r"(x)); return r; }
static uint32_t a_rbit(uint32_t x) { uint32_t r; asm volatile("rbit %w0, %w1" : "=r"(r) : "r"(x)); return r; }
static uint64_t a_umulh(uint64_t a, uint64_t b) { uint64_t r; asm volatile("umulh %0, %1, %2" : "=r"(r) : "r"(a), "r"(b)); return r; }
static uint32_t a_ubfx(uint32_t x) { uint32_t r; asm volatile("ubfx %w0, %w1, #8, #8" : "=r"(r) : "r"(x)); return r; }
static int32_t a_sbfx(int32_t x) { int32_t r; asm volatile("sbfx %w0, %w1, #15, #1" : "=r"(r) : "r"(x)); return r; }
// Flags: ARM C after SUBS means "no borrow" (inverted vs x86 CF); V is signed overflow.
static uint32_t a_subs_carry(uint32_t a, uint32_t b) {
  uint32_t r, t;
  asm volatile("subs %w1, %w2, %w3\n cset %w0, cs" : "=r"(r), "=&r"(t) : "r"(a), "r"(b) : "cc");
  return r;
}
static uint32_t a_adds_overflow(int32_t a, int32_t b) {
  uint32_t r, t;
  asm volatile("adds %w1, %w2, %w3\n cset %w0, vs" : "=r"(r), "=&r"(t) : "r"(a), "r"(b) : "cc");
  return r;
}
static void a_add128(uint64_t alo, uint64_t ahi, uint64_t blo, uint64_t bhi, uint64_t* lo, uint64_t* hi) {
  uint64_t l, h;
  asm volatile("adds %0, %2, %4\n adc %1, %3, %5" : "=&r"(l), "=&r"(h) : "r"(alo), "r"(ahi), "r"(blo), "r"(bhi) : "cc");
  *lo = l;
  *hi = h;
}
static void a_sub128(uint64_t alo, uint64_t ahi, uint64_t blo, uint64_t bhi, uint64_t* lo, uint64_t* hi) {
  uint64_t l, h;
  asm volatile("subs %0, %2, %4\n sbc %1, %3, %5" : "=&r"(l), "=&r"(h) : "r"(alo), "r"(ahi), "r"(blo), "r"(bhi) : "cc");
  *lo = l;
  *hi = h;
}
static uint64_t a_mrs_fpcr() { uint64_t v; asm volatile("mrs %0, fpcr" : "=r"(v)); return v; }
static void a_msr_fpcr(uint64_t v) { asm volatile("msr fpcr, %0" : : "r"(v)); }
static uint64_t a_cntvct() { uint64_t v; asm volatile("isb\n mrs %0, cntvct_el0" : "=r"(v)); return v; }
static uint64_t a_cntfrq() { uint64_t v; asm volatile("mrs %0, cntfrq_el0" : "=r"(v)); return v; }
static uint64_t a_tpidr() { uint64_t v; asm volatile("mrs %0, tpidr_el0" : "=r"(v)); return v; }
static uint64_t a_ctr() { uint64_t v; asm volatile("mrs %0, ctr_el0" : "=r"(v)); return v; }
static uint64_t a_dczid() { uint64_t v; asm volatile("mrs %0, dczid_el0" : "=r"(v)); return v; }
static uint64_t a_midr() { uint64_t v; asm volatile("mrs %0, midr_el1" : "=r"(v)); return v; }
static uint64_t a_isar0() { uint64_t v; asm volatile("mrs %0, id_aa64isar0_el1" : "=r"(v)); return v; }
static long a_svc_getpid() {
  register long x8 asm("x8") = __NR_getpid;
  register long x0 asm("x0");
  asm volatile("svc #0" : "=r"(x0) : "r"(x8) : "memory");
  return x0;
}
static uint64_t a_ldr_unaligned(const uint8_t* p) { uint64_t v; asm volatile("ldr %0, [%1]" : "=r"(v) : "r"(p) : "memory"); return v; }
#endif

static std::string t_isa(const char*) {
#if defined(__aarch64__)
  Res r;
  // integer division never traps on ARM
  r.check(a_sdiv(5, 0) == 0 && a_udiv(7, 0) == 0, "div_by_zero_is_zero");
  r.check(a_sdiv(INT32_MIN, -1) == INT32_MIN && a_sdiv64(INT64_MIN, -1) == INT64_MIN, "div_overflow_no_trap");
  // float -> int saturates; NaN -> 0
  r.check(a_fcvtzs(1e20f) == INT32_MAX && a_fcvtzs(-1e20f) == INT32_MIN, "fcvtzs_saturate");
  r.check(a_fcvtzs(f_of(0x7fc00000)) == 0 && a_fcvtzu(-5.0f) == 0 && a_fcvtzs_d(1e300) == INT64_MAX, "fcvt_nan_neg_large");
  r.check(a_fcvtas(2.5f) == 3 && a_fcvtas(-2.5f) == -3, "fcvtas_ties_away");
  r.check(a_frinta(2.5f) == 3.0f && a_frintn(2.5f) == 2.0f, "frinta_frintn");
  r.check(a_fcvt_h(1.5f) == 0x3e00 && a_fcvt_h(65520.0f) == 0x7c00, "fcvt_to_half");
  // NaN rules: SNaN operand wins and is quieted; otherwise first NaN; default NaN is positive 0x7fc00000
  const float qa = f_of(0x7fc0000a), qb = f_of(0x7fc0000b), sb = f_of(0x7f80000b), inf = f_of(0x7f800000);
  uint32_t n1 = u_of(a_fadd(qa, sb)), n2 = u_of(a_fadd(qa, qb)), n3 = u_of(a_fmul(0.0f, inf)), n4 = u_of(a_fadd(1.0f, qb));
  r.add(F("nan=[%08x %08x %08x %08x]", n1, n2, n3, n4));
  r.check(n1 == 0x7fc0000b, "nan_snan_priority");
  r.check(n2 == 0x7fc0000a, "nan_first_operand");
  r.check(n3 == 0x7fc00000, "default_nan_positive");
  r.check(n4 == 0x7fc0000b, "nan_propagates_op2");
  r.add(F("fmax(qNaN,1)=%08x fmaxnm(qNaN,1)=%08x fmin(+0,-0)=%08x fmin(-0,+0)=%08x", u_of(a_fmax(qa, 1.0f)),
          u_of(a_fmaxnm(qa, 1.0f)), u_of(a_fmin(0.0f, -0.0f)), u_of(a_fmin(-0.0f, 0.0f))));
  r.check(u_of(a_fmax(qa, 1.0f)) == 0x7fc0000a, "fmax_propagates_nan");
  r.check(a_fmaxnm(qa, 1.0f) == 1.0f, "fmaxnm_ignores_qnan");
  r.check(u_of(a_fmin(0.0f, -0.0f)) == 0x80000000 && u_of(a_fmin(-0.0f, 0.0f)) == 0x80000000 &&
              u_of(a_fmax(-0.0f, 0.0f)) == 0, "fmin_fmax_signed_zero");
  // fused multiply-add rounds once
  double x = d_of(0x3ff0000000000001ull), xx = x * x;
  CLOBBER(&xx);
  r.check(a_fmadd(x, x, -xx) == 0x1p-104, "fmadd_single_rounding");
  // rounding mode via FPCR
  fesetround(FE_UPWARD);
  bool up = a_dadd(1.0, 0x1p-60) == nextafter(1.0, 2.0) && ((a_mrs_fpcr() >> 22) & 3) == 1;
  fesetround(FE_DOWNWARD);
  bool down = a_dadd(1.0, -0x1p-60) == nextafter(1.0, 0.0);
  fesetround(FE_TONEAREST);
  r.check(up && down && a_dadd(1.0, 0x1p-60) == 1.0, "fpcr_rounding_modes");
  // cumulative exception flags in FPSR
  feclearexcept(FE_ALL_EXCEPT);
  a_fmul(0.0f, inf);
  bool inv = fetestexcept(FE_INVALID);
  feclearexcept(FE_ALL_EXCEPT);
  a_fadd(f_of(0x7f7fffff), f_of(0x7f7fffff));
  bool ovf = fetestexcept(FE_OVERFLOW);
  feclearexcept(FE_ALL_EXCEPT);
  r.check(inv && ovf, "fpsr_exception_flags");
  // subnormals kept by default, flushed with FPCR.FZ
  r.check(u_of(a_fmul(f_of(1), 1.0f)) == 1, "subnormal_preserved");
  uint64_t fpcr = a_mrs_fpcr();
  a_msr_fpcr(fpcr | (1u << 24));
  uint32_t fz = u_of(a_fmul(f_of(1), 1.0f));
  a_msr_fpcr(fpcr);
  r.check(fz == 0, "fpcr_fz_flushes");
  // integer odds and ends
  r.check(a_clz(0) == 32 && a_rbit(1) == 0x80000000u && a_umulh(1ull << 63, 4) == 2, "clz_rbit_umulh");
  r.check(a_ubfx(0xabcd1234u) == 0x12 && a_sbfx(0x8000) == -1, "bitfield_extract");
  r.check(a_subs_carry(5, 3) == 1 && a_subs_carry(3, 5) == 0, "subs_carry_inverted_borrow");
  r.check(a_adds_overflow(INT32_MAX, 1) == 1 && a_adds_overflow(1, 1) == 0, "adds_overflow_flag");
  uint64_t lo, hi;
  a_add128(~0ull, 0, 1, 0, &lo, &hi);
  bool c1 = lo == 0 && hi == 1;
  a_sub128(0, 0, 1, 0, &lo, &hi);
  r.check(c1 && lo == ~0ull && hi == ~0ull, "adc_sbc_carry_chain");
  uint8_t buf[16];
  for (int i = 0; i < 16; i++) buf[i] = (uint8_t)i;
  uint64_t ref;
  memcpy(&ref, buf + 3, 8);
  r.check(a_ldr_unaligned(buf + 3) == ref, "unaligned_ldr");
  // PAC/BTI hints must execute as NOPs on CPUs (or translators) without them
  int sig = guarded([] { asm volatile("hint #25\n hint #29\n hint #34" ::: "memory"); });
  r.check(sig == 0, "pac_bti_hints_nop");
  // system registers userspace may read
  uint64_t f = 0, v1 = 0, v2 = 0;
  timespec t1, t2;
  sig = guarded([&] {
    f = a_cntfrq();
    clock_gettime(CLOCK_MONOTONIC, &t1);
    v1 = a_cntvct();
    usleep(50000);
    v2 = a_cntvct();
    clock_gettime(CLOCK_MONOTONIC, &t2);
  });
  double wall = (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) * 1e-9;
  double cnt = f ? (double)(v2 - v1) / f : 0;
  r.add(F("cntfrq=%llu cnt/wall=%.3f", (unsigned long long)f, wall > 0 ? cnt / wall : 0));
  r.check(sig == 0 && f > 0 && cnt / wall > 0.9 && cnt / wall < 1.1, "cntvct_rate");
  uint64_t tp_main = 0, tp_thr = 0;
  sig = guarded([&] { tp_main = a_tpidr(); });
  std::thread([&] { guarded([&] { tp_thr = a_tpidr(); }); }).join();
  r.check(sig == 0 && tp_main && tp_thr && tp_main != tp_thr, "tpidr_el0_per_thread");
  uint64_t ctr = 0, dczid = 0, midr = 0, isar0 = 0;
  int s1 = guarded([&] { ctr = a_ctr(); });
  int s2 = guarded([&] { dczid = a_dczid(); });
  int s3 = guarded([&] { midr = a_midr(); });
  int s4 = guarded([&] { isar0 = a_isar0(); });
  r.add(F("ctr_el0=0x%llx(sig%d) dczid=0x%llx(sig%d) midr=0x%llx(sig%d) isar0=0x%llx(sig%d)", (unsigned long long)ctr, s1,
          (unsigned long long)dczid, s2, (unsigned long long)midr, s3, (unsigned long long)isar0, s4));
  r.check(s1 == 0 && ctr != 0, "ctr_el0_readable");
  r.check(s2 == 0, "dczid_el0_readable");
  // arm64 Linux traps and emulates MRS of MIDR_EL1/ID_AA64* for userspace (Go's x/sys/cpu falls back to it)
  r.check(s3 == 0 && s4 == 0, "mrs_cpuid_registers");
  long pid = 0;
  sig = guarded([&] { pid = a_svc_getpid(); });
  r.check(sig == 0 && pid == getpid(), "svc_getpid");
  return r.str();
#else
  return "SKIP AArch64-only semantics (x86_64 is the native control)";
#endif
}

// ---------------------------------------------------------------------------------------------
// atomics and memory ordering
struct SpinBarrier {
  std::atomic<int> count{0}, gen{0};
  int n;
  explicit SpinBarrier(int n_) : n(n_) {}
  void wait() {
    int g = gen.load(std::memory_order_acquire);
    if (count.fetch_add(1, std::memory_order_acq_rel) == n - 1) {
      count.store(0, std::memory_order_relaxed);
      gen.fetch_add(1, std::memory_order_acq_rel);
    } else {
      while (gen.load(std::memory_order_acquire) == g) {
      }
    }
  }
};

#if defined(__aarch64__)
static void llsc_inc(uint64_t* p) {
  uint64_t tmp;
  uint32_t st;
  asm volatile("1: ldaxr %0, [%2]\n add %0, %0, #1\n stlxr %w1, %0, [%2]\n cbnz %w1, 1b"
               : "=&r"(tmp), "=&r"(st) : "r"(p) : "memory");
}
static void lse_add(uint64_t* p, uint64_t v) {
  asm volatile(".arch_extension lse\n ldaddal %1, xzr, [%0]" : : "r"(p), "r"(v) : "memory");
}
#elif defined(__arm__)
static void llsc_inc(uint32_t* p) {
  uint32_t tmp, st;
  asm volatile("dmb ish\n 1: ldrex %0, [%2]\n add %0, %0, #1\n strex %1, %0, [%2]\n teq %1, #0\n bne 1b\n dmb ish"
               : "=&r"(tmp), "=&r"(st) : "r"(p) : "memory", "cc");
}
#endif

static std::string t_atomics(const char*) {
  Res r;
  const int T = 8;
  {
    std::atomic<int64_t> c{0};
    std::vector<std::thread> th;
    for (int i = 0; i < T; i++)
      th.emplace_back([&] { for (int k = 0; k < 200000; k++) c.fetch_add(1, std::memory_order_relaxed); });
    for (auto& t : th) t.join();
    r.check(c.load() == T * 200000LL, "fetch_add_8x200k");
  }
  {
    std::atomic<uint32_t> c{0};
    std::vector<std::thread> th;
    for (int i = 0; i < T; i++)
      th.emplace_back([&] {
        for (int k = 0; k < 100000; k++) {
          uint32_t v = c.load(std::memory_order_relaxed);
          while (!c.compare_exchange_weak(v, v + 1)) {
          }
        }
      });
    for (auto& t : th) t.join();
    r.check(c.load() == T * 100000u, "cas_loop_8x100k");
  }
  {
#if defined(__aarch64__) || defined(__x86_64__)
    typedef unsigned __int128 W;
    typedef uint64_t H;
#else
    typedef uint64_t W;
    typedef uint32_t H;
#endif
    const int HB = sizeof(H) * 8;
    alignas(16) static W w;
    w = (W)(H)~(H)0 << HB;  // lo = 0, hi = ~lo
    std::atomic<int> torn{0};
    std::vector<std::thread> th;
    for (int i = 0; i < 4; i++)
      th.emplace_back([&] {
        for (int k = 0; k < 50000; k++) {
          W o = __atomic_load_n(&w, __ATOMIC_SEQ_CST), n;
          do {
            H lo = (H)o, hi = (H)(o >> HB);
            if (hi != (H)~lo) torn++;
            lo++;
            n = ((W)(H)~lo << HB) | lo;
          } while (!__atomic_compare_exchange_n(&w, &o, n, false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST));
        }
      });
    for (auto& t : th) t.join();
    r.check(torn == 0 && (H)w == 200000 && (H)(w >> HB) == (H)~(H)200000, "wide_cas_no_tearing");
    r.add(F("wide_cas_bits=%d", (int)sizeof(W) * 8));
  }
#if defined(__aarch64__) || defined(__arm__)
  {
#if defined(__aarch64__)
    alignas(8) static uint64_t v;
#else
    alignas(8) static uint32_t v;
#endif
    v = 0;
    std::vector<std::thread> th;
    for (int i = 0; i < 4; i++) th.emplace_back([&] { for (int k = 0; k < 100000; k++) llsc_inc(&v); });
    for (auto& t : th) t.join();
    r.check(v == 400000, "ldxr_stxr_exclusive_4x100k");
  }
#endif
#if defined(__aarch64__)
  if (getauxval(AT_HWCAP) & HWCAP_ATOMICS) {
    alignas(8) static uint64_t v;
    v = 0;
    std::vector<std::thread> th;
    for (int i = 0; i < 4; i++) th.emplace_back([&] { for (int k = 0; k < 100000; k++) lse_add(&v, 1); });
    for (auto& t : th) t.join();
    r.check(v == 400000, "lse_ldaddal_4x100k");
  } else {
    r.add("lse=absent");
  }
#endif
  {
    // message passing with release/acquire
    std::atomic<uint32_t> flag{0}, ack{0};
    volatile uint32_t data = 0;
    std::atomic<int> bad{0};
    const uint32_t N = 100000;
    std::thread rd([&] {
      for (uint32_t i = 1; i <= N; i++) {
        while (flag.load(std::memory_order_acquire) != i) {
        }
        if (data != i * 3) bad++;
        ack.store(i, std::memory_order_release);
      }
    });
    for (uint32_t i = 1; i <= N; i++) {
      data = i * 3;
      flag.store(i, std::memory_order_release);
      while (ack.load(std::memory_order_acquire) != i) {
      }
    }
    rd.join();
    r.check(bad == 0, "message_passing_acq_rel");
  }
  {
    // store buffering (Dekker): with seq_cst both loads may not read 0. A translator that maps
    // STLR/LDAR to plain x86 MOVs breaks this. The relaxed variant may legally show it (info only).
    for (int pass = 0; pass < 2; pass++) {
      const bool sc = pass == 0;
      std::atomic<int> x{0}, y{0};
      int r1 = 0, r2 = 0;
      long both0 = 0;
      const int N = 200000;  // violations under translation can be rare (1 in 20k seen), so run many
      SpinBarrier b(2);
      std::thread tb([&] {
        for (int i = 0; i < N; i++) {
          b.wait();
          y.store(1, sc ? std::memory_order_seq_cst : std::memory_order_relaxed);
          r2 = x.load(sc ? std::memory_order_seq_cst : std::memory_order_relaxed);
          b.wait();
          b.wait();
        }
      });
      for (int i = 0; i < N; i++) {
        b.wait();
        x.store(1, sc ? std::memory_order_seq_cst : std::memory_order_relaxed);
        r1 = y.load(sc ? std::memory_order_seq_cst : std::memory_order_relaxed);
        b.wait();
        if (r1 == 0 && r2 == 0) both0++;
        x.store(0);
        y.store(0);
        b.wait();
      }
      tb.join();
      if (sc) {
        r.check(both0 == 0, "store_buffering_seq_cst");
        r.add(F("sb_seqcst_violations=%ld/%d", both0, N));
      } else {
        r.add(F("sb_relaxed_reorders=%ld/%d", both0, N));
      }
    }
  }
  return r.str();
}

// ---------------------------------------------------------------------------------------------
// tls
static std::atomic<int> g_tls_dtors{0}, g_key_dtors{0};
struct TlsObj {
  int v = 42;
  std::string s = "tls-object-with-heap-storage-xxxxxxxxxxxxxxxx";
  ~TlsObj() { g_tls_dtors++; }
};
static thread_local TlsObj t_obj;
static thread_local int t_counter = 5;

static std::string t_tls(const char*) {
  Res r;
  g_tls_dtors = 0;
  g_key_dtors = 0;
  std::atomic<int> bad{0};
  pthread_key_t key;
  pthread_key_create(&key, [](void*) { g_key_dtors++; });
  std::vector<std::thread> th;
  for (int i = 0; i < 8; i++)
    th.emplace_back([&, i] {
      if (t_counter != 5 || t_obj.v != 42) bad++;
      for (int k = 0; k < 100000; k++) t_counter++;
      t_obj.v = i;
      errno = 1000 + i;
      pthread_setspecific(key, (void*)1);
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
      if (t_counter != 100005 || t_obj.v != i || errno != 1000 + i) bad++;
    });
  for (auto& t : th) t.join();
  r.check(bad == 0, "thread_local_isolation");
  r.check(g_tls_dtors == 8, "thread_local_dtors_run");
  r.check(g_key_dtors == 8, "pthread_key_dtors_run");
  pthread_key_delete(key);
  return r.str();
}

// ---------------------------------------------------------------------------------------------
// signals
static sigjmp_buf g_jb;
static void* volatile g_si_addr;
static volatile int g_si_code, g_si_signo, g_h1_tid, g_h2_tid, g_alarm, g_nest;
[[maybe_unused]] static volatile uintptr_t g_fault_pc, g_resume_pc;
static volatile uintptr_t g_local_addr;
[[maybe_unused]] static volatile int g_uc_ok;

static void jump_handler(int s, siginfo_t* si, void*) {
  g_si_signo = s;
  g_si_addr = si->si_addr;
  g_si_code = si->si_code;
  siglongjmp(g_jb, 1);
}
static void tid_handler(int, siginfo_t*, void*) {
  int local;
  g_h1_tid = gettid();
  g_local_addr = (uintptr_t)&local;
}
// ART blocks SIGUSR1 (and SIGQUIT) in every thread and consumes it in its Signal Catcher thread, so the
// tests use SIGUSR2 and SIGWINCH.
#define SIG_A SIGUSR2
#define SIG_B SIGWINCH
static void b_handler(int, siginfo_t*, void*) { g_h2_tid = gettid(); g_nest = g_nest * 10 + 2; }
static void nest_handler(int, siginfo_t*, void*) { g_nest = 1; raise(SIG_B); g_nest = g_nest * 10 + 3; }
static void alarm_handler(int, siginfo_t*, void*) { g_alarm = gettid(); }
static void uc_handler(int, siginfo_t*, void* ctx) {
  ucontext_t* uc = (ucontext_t*)ctx;
#if defined(__aarch64__)
  g_uc_ok = uc->uc_mcontext.pc == g_fault_pc ? 1 : 2;
  uc->uc_mcontext.pc = g_resume_pc;
#elif defined(__x86_64__)
  g_uc_ok = (uintptr_t)uc->uc_mcontext.gregs[REG_RIP] == g_fault_pc ? 1 : 2;
  uc->uc_mcontext.gregs[REG_RIP] = g_resume_pc;
#else
  (void)uc;
  siglongjmp(g_jb, 1);
#endif
}
__attribute__((noinline)) static int fault_and_skip(void* bad) {
  int v = 7;
#if defined(__aarch64__)
  asm volatile("adr x9, 1f\n str x9, [%1]\n adr x9, 2f\n str x9, [%2]\n 1: ldr %w0, [%3]\n 2:\n"
               : "+r"(v) : "r"(&g_fault_pc), "r"(&g_resume_pc), "r"(bad) : "x9", "memory");
#elif defined(__x86_64__)
  asm volatile("lea 1f(%%rip), %%r11\n mov %%r11, (%1)\n lea 2f(%%rip), %%r11\n mov %%r11, (%2)\n 1: movl (%3), %0\n 2:\n"
               : "+r"(v) : "r"(&g_fault_pc), "r"(&g_resume_pc), "r"(bad) : "r11", "memory");
#endif
  return v;
}
__attribute__((noinline)) static void raise_sigill() {
#if defined(__aarch64__)
  asm volatile("udf #0");
#elif defined(__arm__)
  asm volatile("udf #0");
#elif defined(__x86_64__)
  asm volatile("ud2");
#endif
}

static void set_handler(int sig, void (*h)(int, siginfo_t*, void*), int flags, struct sigaction* old) {
  struct sigaction sa = {};
  sa.sa_sigaction = h;
  sa.sa_flags = SA_SIGINFO | flags;
  sigemptyset(&sa.sa_mask);
  sigaction(sig, &sa, old);
}

static std::string t_signals(const char*) {
  Res r;
  struct sigaction o_segv, o_bus, o_ill, o_a, o_b, o_alrm;
  sigset_t unblock, saved_mask;
  sigemptyset(&unblock);
  sigaddset(&unblock, SIG_A);
  sigaddset(&unblock, SIG_B);
  sigaddset(&unblock, SIGALRM);
  pthread_sigmask(SIG_UNBLOCK, &unblock, &saved_mask);
  set_handler(SIGSEGV, jump_handler, SA_NODEFER, &o_segv);
  set_handler(SIGBUS, jump_handler, SA_NODEFER, &o_bus);
  set_handler(SIGILL, jump_handler, SA_NODEFER, &o_ill);
  // (a) unmapped address -> SEGV_MAPERR with the right si_addr, recovered with siglongjmp
  g_si_signo = 0;
  if (!sigsetjmp(g_jb, 1)) *(volatile int*)0x10 = 1;
  r.check(g_si_signo == SIGSEGV && g_si_addr == (void*)0x10 && g_si_code == SEGV_MAPERR, "segv_maperr_siginfo");
  // (b) write to a read-only page -> SEGV_ACCERR
  char* page = (char*)mmap(nullptr, 4096, PROT_READ, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  g_si_signo = 0;
  if (!sigsetjmp(g_jb, 1)) *(volatile char*)(page + 8) = 1;
  r.check(g_si_signo == SIGSEGV && g_si_addr == page + 8 && g_si_code == SEGV_ACCERR, "segv_accerr_siginfo");
  // (c) undefined instruction -> SIGILL
  g_si_signo = 0;
  if (!sigsetjmp(g_jb, 1)) raise_sigill();
  r.add(F("sigill_signo=%d sigill_code=%d", g_si_signo, g_si_code));
  r.check(g_si_signo == SIGILL, "sigill_delivered");
  r.check(g_si_code == ILL_ILLOPC || g_si_code == ILL_ILLOPN, "sigill_si_code_kernel");
  // (d) handler reads the faulting PC from ucontext and resumes after the instruction (JIT/ART pattern)
#if defined(__aarch64__) || defined(__x86_64__)
  struct sigaction tmp;
  set_handler(SIGSEGV, uc_handler, 0, &tmp);
  g_uc_ok = 0;
  int v = fault_and_skip((void*)0x18);
  sigaction(SIGSEGV, &tmp, nullptr);
  r.check(g_uc_ok == 1 && v == 7, "ucontext_pc_resume");
#endif
  munmap(page, 4096);
  sigaction(SIGSEGV, &o_segv, nullptr);
  sigaction(SIGBUS, &o_bus, nullptr);
  sigaction(SIGILL, &o_ill, nullptr);
  // (e) raise() runs the handler synchronously on this thread
  set_handler(SIG_A, tid_handler, 0, &o_a);
  g_h1_tid = 0;
  raise(SIG_A);
  r.check(g_h1_tid == gettid(), "raise_sync_same_thread");
  // (f) pthread_kill reaches the target thread
  set_handler(SIG_B, b_handler, 0, &o_b);
  {
    std::atomic<int> started{0}, wtid{0};
    g_h2_tid = 0;
    std::thread w([&] {
      wtid = gettid();
      started = 1;
      timespec t0, t;
      clock_gettime(CLOCK_MONOTONIC, &t0);
      while (!g_h2_tid) {
        clock_gettime(CLOCK_MONOTONIC, &t);
        if (t.tv_sec - t0.tv_sec > 3) break;
      }
    });
    while (!started) {
    }
    pthread_kill(w.native_handle(), SIG_B);
    w.join();
    r.check(g_h2_tid == wtid, "pthread_kill_targets_thread");
  }
  // (g) SA_ONSTACK runs on the alternate stack
  {
    const size_t sz = 64 * 1024;
    void* mem = malloc(sz);
    stack_t ss = {}, old = {};
    ss.ss_sp = mem;
    ss.ss_size = sz;
    sigaltstack(&ss, &old);
    struct sigaction t2;
    set_handler(SIG_A, tid_handler, SA_ONSTACK, &t2);
    g_local_addr = 0;
    raise(SIG_A);
    sigaltstack(&old, nullptr);
    r.check(g_local_addr >= (uintptr_t)mem && g_local_addr < (uintptr_t)mem + sz, "sigaltstack_used");
    free(mem);
    set_handler(SIG_A, tid_handler, 0, nullptr);
  }
  // (h) asynchronous SIGALRM interrupts a busy loop
  {
    set_handler(SIGALRM, alarm_handler, 0, &o_alrm);
    g_alarm = 0;
    itimerval it = {};
    it.it_value.tv_usec = 30000;
    setitimer(ITIMER_REAL, &it, nullptr);
    timespec t0, t;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    uint64_t spin = 0;
    while (!g_alarm) {
      CLOBBER(&spin);
      if ((++spin & 0xfffff) == 0) {
        clock_gettime(CLOCK_MONOTONIC, &t);
        if (t.tv_sec - t0.tv_sec > 3) break;
      }
    }
    itimerval zero = {};
    setitimer(ITIMER_REAL, &zero, nullptr);
    r.add(F("alarm_on_this_thread=%d", g_alarm == gettid()));
    r.check(g_alarm != 0, "sigalrm_async_delivery");
    sigaction(SIGALRM, &o_alrm, nullptr);
  }
  // (i) blocked signal stays pending until unblocked
  {
    sigset_t s, old, pend;
    sigemptyset(&s);
    sigaddset(&s, SIG_A);
    pthread_sigmask(SIG_BLOCK, &s, &old);
    g_h1_tid = 0;
    raise(SIG_A);
    sigpending(&pend);
    bool pending = sigismember(&pend, SIG_A) && g_h1_tid == 0;
    pthread_sigmask(SIG_SETMASK, &old, nullptr);
    r.check(pending && g_h1_tid == gettid(), "sigmask_pending_then_delivered");
  }
  // (j) a handler without SA_RESTART makes a blocking read fail with EINTR; with SA_RESTART it resumes
  for (int restart = 0; restart < 2; restart++) {
    set_handler(SIG_A, tid_handler, restart ? SA_RESTART : 0, nullptr);
    int p[2];
    pipe(p);
    pthread_t self = pthread_self();
    std::thread k([&] {
      usleep(50000);
      pthread_kill(self, SIG_A);
      usleep(50000);
      char c = 'x';
      write(p[1], &c, 1);
    });
    char c;
    ssize_t n = read(p[0], &c, 1);
    int e = errno;
    k.join();
    close(p[0]);
    close(p[1]);
    if (restart)
      r.check(n == 1 && c == 'x', "sa_restart_resumes_read");
    else
      r.check(n == -1 && e == EINTR, "eintr_without_sa_restart");
  }
  // (k) nested: the SIG_A handler raises SIG_B
  set_handler(SIG_A, nest_handler, 0, nullptr);
  g_nest = 0;
  raise(SIG_A);
  r.check(g_nest == 123, "nested_handlers");
  sigaction(SIG_A, &o_a, nullptr);
  sigaction(SIG_B, &o_b, nullptr);
  pthread_sigmask(SIG_SETMASK, &saved_mask, nullptr);
  return r.str();
}

// ---------------------------------------------------------------------------------------------
// dlopen
static JavaVM* g_vm;
static int phdr_cb(dl_phdr_info* info, size_t, void* arg) {
  auto* v = (std::pair<int, int>*)arg;
  v->first++;
  if (info->dlpi_name && strstr(info->dlpi_name, "libprobe.so")) v->second = 1;
  return 0;
}
static std::string t_dlopen(const char* libdir) {
  Res r;
  // Other ways native code looks for the JavaVM (info only: both also fail for x86_64 code on this image).
  r.add(F("rtld_default_JNI_GetCreatedJavaVMs=%s dlopen(libart.so)=%s",
          dlsym(RTLD_DEFAULT, "JNI_GetCreatedJavaVMs") ? "found" : "absent", dlopen("libart.so", RTLD_NOW) ? "ok" : "fail"));
  void* h = dlopen("libprobeplugin.so", RTLD_NOW);
  r.check(h != nullptr, "dlopen_plugin_by_name");
  if (h) {
    auto fn = (int (*)(int))dlsym(h, "plugin_compute");
    auto ctor = (int (*)())dlsym(h, "plugin_ctor_ran");
    r.check(fn && fn(14) == 43, "dlsym_call");
    r.check(ctor && ctor() == 1, "plugin_constructor_ran");
    r.check(dlopen("libprobeplugin.so", RTLD_NOW | RTLD_NOLOAD) == h, "rtld_noload");
    auto tls = (int (*)())dlsym(h, "plugin_tls_counter");
    std::atomic<int> bad{0};
    std::vector<std::thread> th;
    for (int i = 0; i < 4; i++)
      th.emplace_back([&] { for (int k = 1; k <= 3; k++) if (tls() != k) bad++; });
    for (auto& t : th) t.join();
    r.check(tls && bad == 0, "plugin_dynamic_tls");
  }
  std::string full = std::string(libdir) + "/libprobeplugin.so";
  void* h2 = dlopen(full.c_str(), RTLD_NOW);
  r.check(h2 != nullptr && (h == nullptr || h2 == h), "dlopen_full_path");
  void* none = dlopen("libanybook_does_not_exist.so", RTLD_NOW);
  const char* err = dlerror();
  r.check(none == nullptr && err && strstr(err, "not found"), "dlerror_not_found");
  r.check(dlsym(RTLD_DEFAULT, "malloc") != nullptr, "dlsym_rtld_default");
  Dl_info di = {};
  r.check(dladdr((void*)&t_dlopen, &di) && di.dli_fname && strstr(di.dli_fname, "libprobe.so"), "dladdr_self");
  std::pair<int, int> ph(0, 0);
  dl_iterate_phdr(phdr_cb, &ph);
  r.check(ph.second == 1, "dl_iterate_phdr_finds_self");
  r.add(F("loaded_objects=%d", ph.first));
  // Every NDK-stable library must load for this ABI.
  static const char* kNdk[] = {"libandroid.so", "libc.so", "libm.so", "libdl.so", "liblog.so", "libz.so", "libEGL.so",
                               "libGLESv1_CM.so", "libGLESv2.so", "libGLESv3.so", "libvulkan.so", "libjnigraphics.so",
                               "libOpenSLES.so", "libOpenMAXAL.so", "libmediandk.so", "libcamera2ndk.so", "libaaudio.so",
                               "libneuralnetworks.so", "libnativewindow.so", "libsync.so", "libbinder_ndk.so", "libicu.so",
                               "libamidi.so", "libnativehelper.so"};
  std::string missing;
  for (const char* n : kNdk)
    if (!dlopen(n, RTLD_NOW)) {
      const char* e = dlerror();
      missing += std::string(n) + "(" + clean(e ? e : "?", 60) + ") ";
    }
  r.check(missing.empty(), "ndk_stable_libs_load");
  if (!missing.empty()) r.add("missing=[" + missing + "]");
  // JNI_GetCreatedJavaVMs (NDK API 31, libnativehelper.so) is how Rust's jni/ndk-context crates find the VM.
  void* nh = dlopen("libnativehelper.so", RTLD_NOW);
  auto gcv = (jint(*)(JavaVM**, jsize, jsize*))(nh ? dlsym(nh, "JNI_GetCreatedJavaVMs") : dlsym(RTLD_DEFAULT, "JNI_GetCreatedJavaVMs"));
  JavaVM* vms[2] = {};
  jsize nvm = 0;
  r.check(gcv && gcv(vms, 2, &nvm) == JNI_OK && nvm == 1 && vms[0] == g_vm, "jni_get_created_java_vms");
  // Platform-private libraries must stay hidden from apps.
  void* priv = dlopen("libutils.so", RTLD_NOW);
  r.check(priv == nullptr, "private_lib_blocked");
  void* wrong = dlopen("/system/lib64/libc.so", RTLD_NOW);
  r.add(F("dlopen(/system/lib64/libc.so)=%s", wrong ? "ok" : "fail"));
  return r.str();
}

// ---------------------------------------------------------------------------------------------
// C++ exceptions
static std::atomic<int> g_dtors{0};
struct D {
  ~D() { g_dtors++; }
};
struct Base : std::exception {
  const char* what() const noexcept override { return "base"; }
};
struct Derived : Base {
  int v;
  explicit Derived(int x) : v(x) {}
};
__attribute__((noinline)) static void thrower(int depth, int v) {
  D d;
  if (depth == 0) throw Derived(v);
  thrower(depth - 1, v);
  asm volatile("");
}
static int cmp_throw(const void* a, const void* b) {
  int x = *(const int*)a, y = *(const int*)b;
  if (x == 13 || y == 13) throw std::runtime_error("from-qsort");
  return x - y;
}
static _Unwind_Reason_Code bt_cb(_Unwind_Context*, void* arg) {
  (*(int*)arg)++;
  return _URC_NO_REASON;
}
__attribute__((noinline)) static int bt_depth(int d) {
  if (d == 0) {
    int frames = 0;
    _Unwind_Backtrace(bt_cb, &frames);
    return frames;
  }
  int r = bt_depth(d - 1);
  asm volatile("");
  return r;
}

static std::string t_cxx(const char*) {
  Res r;
  {
    g_dtors = 0;
    int got = -1;
    try {
      thrower(20, 77);
    } catch (const Base& b) {
      got = static_cast<const Derived&>(b).v;
    }
    r.check(got == 77 && g_dtors == 21, "throw_catch_base_runs_dtors");
  }
  {
    bool ok = false;
    try {
      try {
        throw std::logic_error("x");
      } catch (...) {
        throw;
      }
    } catch (const std::logic_error& e) {
      ok = !strcmp(e.what(), "x");
    }
    r.check(ok, "rethrow");
  }
  {
    bool ok = false;
    try {
      throw 42;
    } catch (int x) {
      ok = x == 42;
    }
    r.check(ok, "throw_int");
  }
  {
    std::exception_ptr ep;
    std::thread t([&] {
      try {
        throw std::out_of_range("thr");
      } catch (...) {
        ep = std::current_exception();
      }
    });
    t.join();
    bool ok = false;
    try {
      std::rethrow_exception(ep);
    } catch (const std::out_of_range& e) {
      ok = !strcmp(e.what(), "thr");
    }
    r.check(ok, "exception_ptr_across_threads");
  }
  {
    std::promise<int> p;
    auto f = p.get_future();
    std::thread t([&] { p.set_exception(std::make_exception_ptr(std::runtime_error("fut"))); });
    t.join();
    bool ok = false;
    try {
      f.get();
    } catch (const std::runtime_error&) {
      ok = true;
    }
    r.check(ok, "future_exception");
  }
  {
    bool ok = false;
    try {
      std::vector<int> v;
      CLOBBER(&v);
      (void)v.at(5);
    } catch (const std::out_of_range&) {
      ok = true;
    }
    r.check(ok, "stl_out_of_range");
  }
  {
    bool ok = false;
    try {
      volatile size_t n = SIZE_MAX / 2;
      char* p = new char[n];
      CLOBBER(p);
      delete[] p;
    } catch (const std::bad_alloc&) {
      ok = true;
    }
    r.check(ok, "bad_alloc");
  }
  {
    std::vector<int> v(64);
    for (int i = 0; i < 64; i++) v[i] = 64 - i;
    bool ok = false;
    try {
      qsort(v.data(), v.size(), sizeof(int), cmp_throw);
    } catch (const std::runtime_error&) {
      ok = true;
    }
    r.check(ok, "unwind_through_libc_qsort");
  }
  {
    void* h = dlopen("libprobeplugin.so", RTLD_NOW);
    bool ok = false;
    auto fn = h ? (void (*)(const char*))dlsym(h, "plugin_throw") : nullptr;
    if (fn) {
      try {
        fn("plug");
      } catch (const std::runtime_error& e) {
        ok = !strcmp(e.what(), "plug");
      }
    }
    r.check(ok, "throw_across_dlopen_boundary");
  }
  {
    int frames = bt_depth(8);
    r.add(F("backtrace_frames=%d", frames));
    r.check(frames >= 10, "unwind_backtrace_depth");
  }
  return r.str();
}

// ---------------------------------------------------------------------------------------------
// threads
static void* big_stack_fn(void* arg) {
  const size_t n = 6 << 20;
  volatile char* p = (volatile char*)alloca(n);
  for (size_t i = 0; i < n; i += 4096) p[i] = (char)(i >> 12);
  *(int*)arg = p[4096 * 7] == 7 && p[n - 4096] == (char)((n - 4096) >> 12) ? 1 : 0;
  return nullptr;
}
static std::string t_threads(const char*) {
  Res r;
  {
    std::atomic<int> n{0};
    std::vector<std::thread> th;
    for (int i = 0; i < 64; i++) th.emplace_back([&] { n++; });
    for (auto& t : th) t.join();
    r.check(n == 64, "spawn_join_64");
  }
  {
    std::mutex m;
    long counter = 0;
    std::vector<std::thread> th;
    for (int i = 0; i < 8; i++)
      th.emplace_back([&] {
        for (int k = 0; k < 50000; k++) {
          std::lock_guard<std::mutex> g(m);
          counter++;
        }
      });
    for (auto& t : th) t.join();
    r.check(counter == 400000, "mutex_contention");
  }
  {
    std::mutex m;
    std::condition_variable cv;
    int turn = 0;
    const int N = 5000;
    std::thread t([&] {
      for (int i = 0; i < N; i++) {
        std::unique_lock<std::mutex> l(m);
        cv.wait(l, [&] { return turn % 2 == 1; });
        turn++;
        cv.notify_all();
      }
    });
    for (int i = 0; i < N; i++) {
      std::unique_lock<std::mutex> l(m);
      cv.wait(l, [&] { return turn % 2 == 0; });
      turn++;
      cv.notify_all();
    }
    t.join();
    r.check(turn == 2 * N, "condvar_pingpong");
  }
  {
    pthread_attr_t a;
    pthread_attr_init(&a);
    pthread_attr_setstacksize(&a, 16 << 20);
    pthread_t t;
    int ok = 0;
    r.check(pthread_create(&t, &a, big_stack_fn, &ok) == 0 && pthread_join(t, nullptr) == 0 && ok == 1, "16mb_stack_thread");
    pthread_attr_destroy(&a);
  }
  {
    char old[32] = {}, nm[32] = {};
    prctl(PR_GET_NAME, old);
    prctl(PR_SET_NAME, "probe-named");
    prctl(PR_GET_NAME, nm);
    std::string comm = read_file(F("/proc/self/task/%d/comm", gettid()).c_str());
    prctl(PR_SET_NAME, old);
    r.check(!strcmp(nm, "probe-named") && comm.rfind("probe-named", 0) == 0, "pr_set_name");
  }
  cpu_set_t s;
  CPU_ZERO(&s);
  sched_getaffinity(0, sizeof s, &s);
  r.add(F("affinity=%d online=%ld hwconc=%u", CPU_COUNT(&s), sysconf(_SC_NPROCESSORS_ONLN), std::thread::hardware_concurrency()));
  r.check(CPU_COUNT(&s) > 0 && sysconf(_SC_NPROCESSORS_ONLN) > 0, "cpu_count");
  return r.str();
}

// ---------------------------------------------------------------------------------------------
// jit: generate code at runtime, patch it, and make sure the new code runs
typedef int (*IntFn)();
static void emit_ret_imm(uint8_t* p, int v) {
#if defined(__aarch64__)
  uint32_t ins[2] = {0x52800000u | ((uint32_t)(v & 0xffff) << 5), 0xd65f03c0u};  // mov w0,#v ; ret
  memcpy(p, ins, 8);
#elif defined(__x86_64__)
  p[0] = 0xb8;  // mov eax, imm32 ; ret
  memcpy(p + 1, &v, 4);
  p[5] = 0xc3;
#elif defined(__arm__)
  uint32_t ins[2] = {0xe3000000u | ((uint32_t)(v & 0xf000) << 4) | (uint32_t)(v & 0xfff), 0xe12fff1eu};  // movw r0,#v ; bx lr
  memcpy(p, ins, 8);
#endif
}
static void flush(void* p, size_t n) { __builtin___clear_cache((char*)p, (char*)p + n); }
static int call_hot(void* p, int times) {
  IntFn f = (IntFn)p;
  int v = 0;
  for (int i = 0; i < times; i++) v = f();
  return v;
}
static std::string t_jit(const char*) {
  Res r;
  const size_t PG = sysconf(_SC_PAGESIZE);
  // W^X with mprotect
  uint8_t* p = (uint8_t*)mmap(nullptr, PG, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  emit_ret_imm(p, 42);
  mprotect(p, PG, PROT_READ | PROT_EXEC);
  flush(p, 16);
  int v1 = 0, v2 = 0;
  int sig = guarded([&] { v1 = call_hot(p, 1000); });
  mprotect(p, PG, PROT_READ | PROT_WRITE);
  emit_ret_imm(p, 7);
  mprotect(p, PG, PROT_READ | PROT_EXEC);
  flush(p, 16);
  int sig2 = guarded([&] { v2 = call_hot(p, 1); });
  r.check(sig == 0 && v1 == 42, "mprotect_rx_call");
  r.check(sig2 == 0 && v2 == 7, "mprotect_repatch");
  munmap(p, PG);
  // RWX page patched in place after the old code got hot
  uint8_t* q = (uint8_t*)mmap(nullptr, PG, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (q == MAP_FAILED) {
    r.add(F("rwx_mmap=denied(%d)", errno));
  } else {
    emit_ret_imm(q, 11);
    flush(q, 16);
    v1 = v2 = 0;
    sig = guarded([&] { v1 = call_hot(q, 200000); });
    emit_ret_imm(q, 12);
    flush(q, 16);
    sig2 = guarded([&] { v2 = call_hot(q, 1); });
    r.check(sig == 0 && sig2 == 0 && v1 == 11 && v2 == 12, "rwx_hot_patch");
    munmap(q, PG);
  }
  // dual mapping of one memfd: write through the RW view, execute through the RX view (V8/SpiderMonkey style)
  int fd = (int)syscall(__NR_memfd_create, "anybook-jit", 0);
  if (fd < 0 || ftruncate(fd, PG) != 0) {
    r.check(false, "memfd_create");
  } else {
    uint8_t* rw = (uint8_t*)mmap(nullptr, PG, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    uint8_t* rx = (uint8_t*)mmap(nullptr, PG, PROT_READ | PROT_EXEC, MAP_SHARED, fd, 0);
    emit_ret_imm(rw, 21);
    flush(rx, 16);
    v1 = v2 = 0;
    sig = guarded([&] { v1 = call_hot(rx, 200000); });
    emit_ret_imm(rw, 22);
    flush(rx, 16);
    sig2 = guarded([&] { v2 = call_hot(rx, 1); });
    r.check(sig == 0 && sig2 == 0 && v1 == 21 && v2 == 22, "dual_map_patch_with_flush");
    // Without a cache flush ARM gives no guarantee; record what happens.
    emit_ret_imm(rw, 23);
    int v3 = 0;
    guarded([&] { v3 = call_hot(rx, 1); });
    r.add(F("dual_map_no_flush_sees=%d", v3));
    munmap(rw, PG);
    munmap(rx, PG);
    close(fd);
  }
  return r.str();
}

// ---------------------------------------------------------------------------------------------
// syscalls
static std::string t_syscalls(const char*) {
  Res r;
  r.check(syscall(__NR_getpid) == getpid() && syscall(__NR_gettid) == gettid(), "syscall_getpid_gettid");
  uint8_t rnd[32] = {};
  long n = syscall(__NR_getrandom, rnd, sizeof rnd, 0);
  int nz = 0;
  for (uint8_t b : rnd) nz += b != 0;
  r.check(n == 32 && nz > 16, "getrandom");
  int fd = (int)syscall(__NR_openat, AT_FDCWD, "/proc/self/status", O_RDONLY | O_CLOEXEC);
  char buf[256] = {};
  r.check(fd >= 0 && syscall(__NR_read, fd, buf, sizeof buf - 1) > 0 && strstr(buf, "Name:"), "raw_openat_read");
  if (fd >= 0) close(fd);
  timespec m1, m2, b1;
  clock_gettime(CLOCK_MONOTONIC, &m1);
  clock_gettime(CLOCK_BOOTTIME, &b1);
  usleep(10000);
  clock_gettime(CLOCK_MONOTONIC, &m2);
  double dt = (m2.tv_sec - m1.tv_sec) + (m2.tv_nsec - m1.tv_nsec) * 1e-9;
  r.check(dt >= 0.009 && dt < 1.0 && b1.tv_sec >= m1.tv_sec, "clock_gettime_monotonic_boottime");
  int efd = (int)syscall(__NR_eventfd2, 0, 0);
  uint64_t one = 1, got = 0;
  r.check(efd >= 0 && write(efd, &one, 8) == 8 && read(efd, &got, 8) == 8 && got == 1, "eventfd");
  if (efd >= 0) close(efd);
  void* hint = mmap(nullptr, 1 << 20, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  munmap(hint, 1 << 20);
  void* fixed = mmap(hint, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
  r.check(fixed == hint, "mmap_fixed");
  munmap(fixed, 4096);
  void* big = mmap(nullptr, 512u << 20, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
  bool bigok = big != MAP_FAILED;
  if (bigok) {
    for (size_t i = 0; i < (512u << 20); i += 1 << 20) ((volatile char*)big)[i] = 1;
    munmap(big, 512u << 20);
  }
  r.check(bigok, "mmap_512mb");
  utsname u;
  uname(&u);
  r.add(F("uname=%s/%s personality=0x%x", u.sysname, u.machine, (unsigned)syscall(__NR_personality, 0xffffffff)));
  return r.str();
}

// ---------------------------------------------------------------------------------------------
// gles: EGL pbuffer + ES 3.0 shader draw + readback
static GLuint compile(GLenum type, const char* src, std::string* log) {
  GLuint s = glCreateShader(type);
  glShaderSource(s, 1, &src, nullptr);
  glCompileShader(s);
  GLint ok = 0;
  glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
  if (!ok) {
    char b[256] = {};
    glGetShaderInfoLog(s, sizeof b, nullptr, b);
    *log += b;
  }
  return s;
}
static std::string t_gles(const char*) {
  Res r;
  EGLDisplay d = eglGetDisplay(EGL_DEFAULT_DISPLAY);
  EGLint ma = 0, mi = 0;
  if (!r.check(eglInitialize(d, &ma, &mi), "egl_initialize")) return r.str() + F(" egl_err=0x%x", eglGetError());
  const EGLint ca[] = {EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT_KHR, EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RED_SIZE, 8,
                       EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
  EGLConfig cfg;
  EGLint n = 0;
  eglChooseConfig(d, ca, &cfg, 1, &n);
  if (!r.check(n > 0, "egl_config")) return r.str();
  const EGLint pb[] = {EGL_WIDTH, 64, EGL_HEIGHT, 64, EGL_NONE};
  EGLSurface s = eglCreatePbufferSurface(d, cfg, pb);
  const EGLint xa[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
  EGLContext c = eglCreateContext(d, cfg, EGL_NO_CONTEXT, xa);
  if (!r.check(s != EGL_NO_SURFACE && c != EGL_NO_CONTEXT && eglMakeCurrent(d, s, s, c), "egl_context_current"))
    return r.str() + F(" egl_err=0x%x", eglGetError());
  r.add(F("egl=%d.%d renderer=[%s] version=[%s]", ma, mi, clean((const char*)glGetString(GL_RENDERER), 60).c_str(),
          clean((const char*)glGetString(GL_VERSION), 60).c_str()));
  std::string log;
  const char* vs = "#version 300 es\nlayout(location=0) in vec2 p;\nvoid main(){ gl_Position = vec4(p, 0.0, 1.0); }\n";
  const char* fs = "#version 300 es\nprecision mediump float;\nuniform vec4 col;\nout vec4 o;\nvoid main(){ o = col; }\n";
  GLuint prog = glCreateProgram();
  GLuint v = compile(GL_VERTEX_SHADER, vs, &log), f = compile(GL_FRAGMENT_SHADER, fs, &log);
  glAttachShader(prog, v);
  glAttachShader(prog, f);
  glLinkProgram(prog);
  GLint linked = 0;
  glGetProgramiv(prog, GL_LINK_STATUS, &linked);
  r.check(linked && log.empty(), "shader_compile_link");
  GLuint tex, fbo;
  glGenTextures(1, &tex);
  glBindTexture(GL_TEXTURE_2D, tex);
  glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, 64, 64, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
  glGenFramebuffers(1, &fbo);
  glBindFramebuffer(GL_FRAMEBUFFER, fbo);
  glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
  r.check(glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE, "fbo_complete");
  glViewport(0, 0, 64, 64);
  glClearColor(0, 0, 1, 1);
  glClear(GL_COLOR_BUFFER_BIT);
  const float tri[] = {-1, -1, 3, -1, -1, 3};
  GLuint vbo;
  glGenBuffers(1, &vbo);
  glBindBuffer(GL_ARRAY_BUFFER, vbo);
  glBufferData(GL_ARRAY_BUFFER, sizeof tri, tri, GL_STATIC_DRAW);
  glUseProgram(prog);
  glUniform4f(glGetUniformLocation(prog, "col"), 1.0f, 0.5f, 0.0f, 1.0f);
  glEnableVertexAttribArray(0);
  glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, nullptr);
  glDrawArrays(GL_TRIANGLES, 0, 3);
  uint8_t px[4] = {};
  glReadPixels(32, 32, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
  r.add(F("pixel=%d,%d,%d,%d", px[0], px[1], px[2], px[3]));
  r.check(px[0] == 255 && abs(px[1] - 128) <= 2 && px[2] == 0 && px[3] == 255, "draw_readback");
  r.check(glGetError() == GL_NO_ERROR, "no_gl_error");
  glDeleteBuffers(1, &vbo);
  glDeleteFramebuffers(1, &fbo);
  glDeleteTextures(1, &tex);
  glDeleteProgram(prog);
  eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
  eglDestroyContext(d, c);
  eglDestroySurface(d, s);
  return r.str();
}

// ---------------------------------------------------------------------------------------------
// vulkan: instance/device through the loader, then a transfer job (vkCmdFillBuffer) and readback
static std::string t_vulkan(const char*) {
  Res r;
  void* lib = dlopen("libvulkan.so", RTLD_NOW);
  if (!r.check(lib != nullptr, "dlopen_libvulkan")) return r.str();
  auto gipa = (PFN_vkGetInstanceProcAddr)dlsym(lib, "vkGetInstanceProcAddr");
  if (!r.check(gipa != nullptr, "vkGetInstanceProcAddr")) return r.str();
  auto vkCreateInstance = (PFN_vkCreateInstance)gipa(nullptr, "vkCreateInstance");
  auto vkEnumerateInstanceVersion = (PFN_vkEnumerateInstanceVersion)gipa(nullptr, "vkEnumerateInstanceVersion");
  uint32_t iv = 0;
  if (vkEnumerateInstanceVersion) vkEnumerateInstanceVersion(&iv);
  VkApplicationInfo ai = {VK_STRUCTURE_TYPE_APPLICATION_INFO};
  ai.pApplicationName = "anybook-probe";
  ai.apiVersion = VK_API_VERSION_1_1;
  VkInstanceCreateInfo ici = {VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
  ici.pApplicationInfo = &ai;
  VkInstance inst;
  VkResult res = vkCreateInstance(&ici, nullptr, &inst);
  if (!r.check(res == VK_SUCCESS, "create_instance")) return r.str() + F(" vkres=%d", res);
#define IP(name) auto name = (PFN_##name)gipa(inst, #name)
  IP(vkEnumeratePhysicalDevices);
  IP(vkGetPhysicalDeviceProperties);
  IP(vkGetPhysicalDeviceQueueFamilyProperties);
  IP(vkGetPhysicalDeviceMemoryProperties);
  IP(vkCreateDevice);
  IP(vkGetDeviceProcAddr);
  IP(vkDestroyInstance);
  uint32_t n = 0;
  vkEnumeratePhysicalDevices(inst, &n, nullptr);
  if (!r.check(n > 0, "physical_device")) {
    vkDestroyInstance(inst, nullptr);
    return r.str();
  }
  VkPhysicalDevice pd;
  n = 1;
  vkEnumeratePhysicalDevices(inst, &n, &pd);
  VkPhysicalDeviceProperties pr;
  vkGetPhysicalDeviceProperties(pd, &pr);
  r.add(F("loader=%u.%u device=[%s] api=%u.%u.%u", VK_VERSION_MAJOR(iv), VK_VERSION_MINOR(iv), clean(pr.deviceName, 60).c_str(),
          VK_VERSION_MAJOR(pr.apiVersion), VK_VERSION_MINOR(pr.apiVersion), VK_VERSION_PATCH(pr.apiVersion)));
  uint32_t qn = 0;
  vkGetPhysicalDeviceQueueFamilyProperties(pd, &qn, nullptr);
  std::vector<VkQueueFamilyProperties> qf(qn);
  vkGetPhysicalDeviceQueueFamilyProperties(pd, &qn, qf.data());
  uint32_t fam = UINT32_MAX;
  for (uint32_t i = 0; i < qn; i++)
    if (qf[i].queueFlags & (VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_COMPUTE_BIT)) {
      fam = i;
      break;
    }
  float prio = 1.0f;
  VkDeviceQueueCreateInfo qci = {VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
  qci.queueFamilyIndex = fam;
  qci.queueCount = 1;
  qci.pQueuePriorities = &prio;
  VkDeviceCreateInfo dci = {VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
  dci.queueCreateInfoCount = 1;
  dci.pQueueCreateInfos = &qci;
  VkDevice dev;
  if (!r.check(fam != UINT32_MAX && vkCreateDevice(pd, &dci, nullptr, &dev) == VK_SUCCESS, "create_device")) {
    vkDestroyInstance(inst, nullptr);
    return r.str();
  }
#define DP(name) auto name = (PFN_##name)vkGetDeviceProcAddr(dev, #name)
  DP(vkGetDeviceQueue);
  DP(vkCreateBuffer);
  DP(vkGetBufferMemoryRequirements);
  DP(vkAllocateMemory);
  DP(vkBindBufferMemory);
  DP(vkMapMemory);
  DP(vkCreateCommandPool);
  DP(vkAllocateCommandBuffers);
  DP(vkBeginCommandBuffer);
  DP(vkCmdFillBuffer);
  DP(vkEndCommandBuffer);
  DP(vkCreateFence);
  DP(vkQueueSubmit);
  DP(vkWaitForFences);
  DP(vkDestroyFence);
  DP(vkDestroyCommandPool);
  DP(vkFreeMemory);
  DP(vkDestroyBuffer);
  DP(vkDestroyDevice);
  VkQueue q;
  vkGetDeviceQueue(dev, fam, 0, &q);
  const VkDeviceSize SZ = 1 << 20;
  VkBufferCreateInfo bci = {VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
  bci.size = SZ;
  bci.usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT;
  VkBuffer buf;
  vkCreateBuffer(dev, &bci, nullptr, &buf);
  VkMemoryRequirements mr;
  vkGetBufferMemoryRequirements(dev, buf, &mr);
  VkPhysicalDeviceMemoryProperties mp;
  vkGetPhysicalDeviceMemoryProperties(pd, &mp);
  uint32_t mt = UINT32_MAX;
  const VkMemoryPropertyFlags want = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
  for (uint32_t i = 0; i < mp.memoryTypeCount; i++)
    if ((mr.memoryTypeBits & (1u << i)) && (mp.memoryTypes[i].propertyFlags & want) == want) {
      mt = i;
      break;
    }
  VkMemoryAllocateInfo mai = {VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
  mai.allocationSize = mr.size;
  mai.memoryTypeIndex = mt;
  VkDeviceMemory mem;
  bool ok = mt != UINT32_MAX && vkAllocateMemory(dev, &mai, nullptr, &mem) == VK_SUCCESS &&
            vkBindBufferMemory(dev, buf, mem, 0) == VK_SUCCESS;
  r.check(ok, "host_visible_buffer");
  uint32_t* ptr = nullptr;
  if (ok) ok = vkMapMemory(dev, mem, 0, SZ, 0, (void**)&ptr) == VK_SUCCESS;
  if (ok) {
    memset(ptr, 0, SZ);
    VkCommandPoolCreateInfo pci = {VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    pci.queueFamilyIndex = fam;
    VkCommandPool pool;
    vkCreateCommandPool(dev, &pci, nullptr, &pool);
    VkCommandBufferAllocateInfo cai = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    cai.commandPool = pool;
    cai.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    cai.commandBufferCount = 1;
    VkCommandBuffer cb;
    vkAllocateCommandBuffers(dev, &cai, &cb);
    VkCommandBufferBeginInfo bi = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    vkBeginCommandBuffer(cb, &bi);
    vkCmdFillBuffer(cb, buf, 0, VK_WHOLE_SIZE, 0xa5a5a5a5u);
    vkEndCommandBuffer(cb);
    VkFenceCreateInfo fci = {VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    VkFence fence;
    vkCreateFence(dev, &fci, nullptr, &fence);
    VkSubmitInfo si = {VK_STRUCTURE_TYPE_SUBMIT_INFO};
    si.commandBufferCount = 1;
    si.pCommandBuffers = &cb;
    VkResult sr = vkQueueSubmit(q, 1, &si, fence);
    VkResult wr = sr == VK_SUCCESS ? vkWaitForFences(dev, 1, &fence, VK_TRUE, 5000000000ull) : sr;
    r.check(wr == VK_SUCCESS, "submit_and_wait");
    size_t badw = 0;
    for (size_t i = 0; i < SZ / 4; i++) badw += ptr[i] != 0xa5a5a5a5u;
    r.check(wr == VK_SUCCESS && badw == 0, "fill_buffer_readback");
    vkDestroyFence(dev, fence, nullptr);
    vkDestroyCommandPool(dev, pool, nullptr);
  }
  vkDestroyBuffer(dev, buf, nullptr);
  if (mt != UINT32_MAX) vkFreeMemory(dev, mem, nullptr);
  vkDestroyDevice(dev, nullptr);
  vkDestroyInstance(inst, nullptr);
  return r.str();
}

// ---------------------------------------------------------------------------------------------
// regress: regressions for the translator bugs OpenBook fixed in Digitalis (ANAL-200), checked against the
// architecture rather than against one bridge:
//   - MRS of the ID registers works, as the Linux kernel emulates it, and agrees with AT_HWCAP (Go's x/sys/cpu
//     falls back to ID_AA64ISAR0/ISAR1/PFR0 when /proc/self/auxv is unreadable, which it is for apps);
//   - FRECPE / FRSQRTE give the Arm estimates bit for bit, with FPSR, under FPCR 0 / FZ / DN (golden values from
//     QEMU, scripts/compat/digitalis/fp-estimate/golden.c), scalar and vector, in a loop the JIT tiers translate;
//   - the libxul.so pattern that crashed Fennec: (see fennec_* below).
#if defined(__aarch64__)
struct EstGolden32 {
  uint32_t in, fpcr, recpe, recpe_fpsr, rsqrte, rsqrte_fpsr;
};
struct EstGolden64 {
  uint64_t in;
  uint32_t fpcr;
  uint64_t recpe;
  uint32_t recpe_fpsr;
  uint64_t rsqrte;
  uint32_t rsqrte_fpsr;
};
// Generated by scripts/compat/digitalis/fp-estimate/golden.c under qemu-aarch64 -cpu max. {input, fpcr, frecpe, fpsr, frsqrte, fpsr}
static const EstGolden32 kEstGolden32[] = {
    {0x3f800000, 0x0, 0x3f7f8000, 0x0, 0x3f7f8000, 0x0},
    {0x40000000, 0x0, 0x3eff8000, 0x0, 0x3f348000, 0x0},
    {0x40400000, 0x0, 0x3eaa8000, 0x0, 0x3f138000, 0x0},
    {0x3dcccccd, 0x0, 0x41200000, 0x0, 0x404a8000, 0x0},
    {0x3fc00000, 0x0, 0x3f2a8000, 0x0, 0x3f510000, 0x0},
    {0x447a0000, 0x0, 0x3a830000, 0x0, 0x3d018000, 0x0},
    {0x00800000, 0x0, 0x7e7f8000, 0x0, 0x5eff8000, 0x0},
    {0x00ffffff, 0x0, 0x7e000000, 0x0, 0x5eb50000, 0x0},
    {0x00400000, 0x0, 0x7eff8000, 0x0, 0x5f348000, 0x0},
    {0x00200000, 0x0, 0x7f7f8000, 0x0, 0x5f7f8000, 0x0},
    {0x001fffff, 0x0, 0x7f800000, 0x14, 0x5f800000, 0x0},
    {0x00000001, 0x0, 0x7f800000, 0x14, 0x64b48000, 0x0},
    {0x7e800000, 0x0, 0x007fc000, 0x0, 0x1fff8000, 0x0},
    {0x7f000000, 0x0, 0x003fe000, 0x0, 0x1fb48000, 0x0},
    {0x7f7fffff, 0x0, 0x00200000, 0x0, 0x1f800000, 0x0},
    {0x00000000, 0x0, 0x7f800000, 0x2, 0x7f800000, 0x2},
    {0x80000000, 0x0, 0xff800000, 0x2, 0xff800000, 0x2},
    {0x7f800000, 0x0, 0x00000000, 0x0, 0x00000000, 0x0},
    {0xff800000, 0x0, 0x80000000, 0x0, 0x7fc00000, 0x1},
    {0x7fc12345, 0x0, 0x7fc12345, 0x0, 0x7fc12345, 0x0},
    {0x7f812345, 0x0, 0x7fc12345, 0x1, 0x7fc12345, 0x1},
    {0xbfc00000, 0x0, 0xbf2a8000, 0x0, 0x7fc00000, 0x1},
    {0xb8d1b717, 0x0, 0xc61c0000, 0x0, 0x7fc00000, 0x1},
    {0x40800000, 0x0, 0x3e7f8000, 0x0, 0x3eff8000, 0x0},
    {0x41800000, 0x0, 0x3d7f8000, 0x0, 0x3e7f8000, 0x0},
    {0x3e800000, 0x0, 0x407f8000, 0x0, 0x3fff8000, 0x0},
    {0x3f800000, 0x1000000, 0x3f7f8000, 0x0, 0x3f7f8000, 0x0},
    {0x40000000, 0x1000000, 0x3eff8000, 0x0, 0x3f348000, 0x0},
    {0x40400000, 0x1000000, 0x3eaa8000, 0x0, 0x3f138000, 0x0},
    {0x3dcccccd, 0x1000000, 0x41200000, 0x0, 0x404a8000, 0x0},
    {0x3fc00000, 0x1000000, 0x3f2a8000, 0x0, 0x3f510000, 0x0},
    {0x447a0000, 0x1000000, 0x3a830000, 0x0, 0x3d018000, 0x0},
    {0x00800000, 0x1000000, 0x7e7f8000, 0x0, 0x5eff8000, 0x0},
    {0x00ffffff, 0x1000000, 0x7e000000, 0x0, 0x5eb50000, 0x0},
    {0x00400000, 0x1000000, 0x7f800000, 0x82, 0x7f800000, 0x82},
    {0x00200000, 0x1000000, 0x7f800000, 0x82, 0x7f800000, 0x82},
    {0x001fffff, 0x1000000, 0x7f800000, 0x82, 0x7f800000, 0x82},
    {0x00000001, 0x1000000, 0x7f800000, 0x82, 0x7f800000, 0x82},
    {0x7e800000, 0x1000000, 0x00000000, 0x8, 0x1fff8000, 0x0},
    {0x7f000000, 0x1000000, 0x00000000, 0x8, 0x1fb48000, 0x0},
    {0x7f7fffff, 0x1000000, 0x00000000, 0x8, 0x1f800000, 0x0},
    {0x00000000, 0x1000000, 0x7f800000, 0x2, 0x7f800000, 0x2},
    {0x80000000, 0x1000000, 0xff800000, 0x2, 0xff800000, 0x2},
    {0x7f800000, 0x1000000, 0x00000000, 0x0, 0x00000000, 0x0},
    {0xff800000, 0x1000000, 0x80000000, 0x0, 0x7fc00000, 0x1},
    {0x7fc12345, 0x1000000, 0x7fc12345, 0x0, 0x7fc12345, 0x0},
    {0x7f812345, 0x1000000, 0x7fc12345, 0x1, 0x7fc12345, 0x1},
    {0xbfc00000, 0x1000000, 0xbf2a8000, 0x0, 0x7fc00000, 0x1},
    {0xb8d1b717, 0x1000000, 0xc61c0000, 0x0, 0x7fc00000, 0x1},
    {0x40800000, 0x1000000, 0x3e7f8000, 0x0, 0x3eff8000, 0x0},
    {0x41800000, 0x1000000, 0x3d7f8000, 0x0, 0x3e7f8000, 0x0},
    {0x3e800000, 0x1000000, 0x407f8000, 0x0, 0x3fff8000, 0x0},
    {0x3f800000, 0x2000000, 0x3f7f8000, 0x0, 0x3f7f8000, 0x0},
    {0x40000000, 0x2000000, 0x3eff8000, 0x0, 0x3f348000, 0x0},
    {0x40400000, 0x2000000, 0x3eaa8000, 0x0, 0x3f138000, 0x0},
    {0x3dcccccd, 0x2000000, 0x41200000, 0x0, 0x404a8000, 0x0},
    {0x3fc00000, 0x2000000, 0x3f2a8000, 0x0, 0x3f510000, 0x0},
    {0x447a0000, 0x2000000, 0x3a830000, 0x0, 0x3d018000, 0x0},
    {0x00800000, 0x2000000, 0x7e7f8000, 0x0, 0x5eff8000, 0x0},
    {0x00ffffff, 0x2000000, 0x7e000000, 0x0, 0x5eb50000, 0x0},
    {0x00400000, 0x2000000, 0x7eff8000, 0x0, 0x5f348000, 0x0},
    {0x00200000, 0x2000000, 0x7f7f8000, 0x0, 0x5f7f8000, 0x0},
    {0x001fffff, 0x2000000, 0x7f800000, 0x14, 0x5f800000, 0x0},
    {0x00000001, 0x2000000, 0x7f800000, 0x14, 0x64b48000, 0x0},
    {0x7e800000, 0x2000000, 0x007fc000, 0x0, 0x1fff8000, 0x0},
    {0x7f000000, 0x2000000, 0x003fe000, 0x0, 0x1fb48000, 0x0},
    {0x7f7fffff, 0x2000000, 0x00200000, 0x0, 0x1f800000, 0x0},
    {0x00000000, 0x2000000, 0x7f800000, 0x2, 0x7f800000, 0x2},
    {0x80000000, 0x2000000, 0xff800000, 0x2, 0xff800000, 0x2},
    {0x7f800000, 0x2000000, 0x00000000, 0x0, 0x00000000, 0x0},
    {0xff800000, 0x2000000, 0x80000000, 0x0, 0x7fc00000, 0x1},
    {0x7fc12345, 0x2000000, 0x7fc00000, 0x0, 0x7fc00000, 0x0},
    {0x7f812345, 0x2000000, 0x7fc00000, 0x1, 0x7fc00000, 0x1},
    {0xbfc00000, 0x2000000, 0xbf2a8000, 0x0, 0x7fc00000, 0x1},
    {0xb8d1b717, 0x2000000, 0xc61c0000, 0x0, 0x7fc00000, 0x1},
    {0x40800000, 0x2000000, 0x3e7f8000, 0x0, 0x3eff8000, 0x0},
    {0x41800000, 0x2000000, 0x3d7f8000, 0x0, 0x3e7f8000, 0x0},
    {0x3e800000, 0x2000000, 0x407f8000, 0x0, 0x3fff8000, 0x0},
};
static const EstGolden64 kEstGolden64[] = {
    {0x3ff0000000000000ull, 0x0, 0x3feff00000000000ull, 0x0, 0x3feff00000000000ull, 0x0},
    {0x4000000000000000ull, 0x0, 0x3fdff00000000000ull, 0x0, 0x3fe6900000000000ull, 0x0},
    {0x4008000000000000ull, 0x0, 0x3fd5500000000000ull, 0x0, 0x3fe2700000000000ull, 0x0},
    {0x3fb999999999999aull, 0x0, 0x4024000000000000ull, 0x0, 0x4009500000000000ull, 0x0},
    {0x0010000000000000ull, 0x0, 0x7fcff00000000000ull, 0x0, 0x5fdff00000000000ull, 0x0},
    {0x0008000000000000ull, 0x0, 0x7fdff00000000000ull, 0x0, 0x5fe6900000000000ull, 0x0},
    {0x0004000000000000ull, 0x0, 0x7feff00000000000ull, 0x0, 0x5feff00000000000ull, 0x0},
    {0x0003ffffffffffffull, 0x0, 0x7ff0000000000000ull, 0x14, 0x5ff0000000000000ull, 0x0},
    {0x0000000000000001ull, 0x0, 0x7ff0000000000000ull, 0x14, 0x617ff00000000000ull, 0x0},
    {0x7fd0000000000000ull, 0x0, 0x000ff80000000000ull, 0x0, 0x1ffff00000000000ull, 0x0},
    {0x7fe0000000000000ull, 0x0, 0x0007fc0000000000ull, 0x0, 0x1ff6900000000000ull, 0x0},
    {0x7fefffffffffffffull, 0x0, 0x0004000000000000ull, 0x0, 0x1ff0000000000000ull, 0x0},
    {0x0000000000000000ull, 0x0, 0x7ff0000000000000ull, 0x2, 0x7ff0000000000000ull, 0x2},
    {0x8000000000000000ull, 0x0, 0xfff0000000000000ull, 0x2, 0xfff0000000000000ull, 0x2},
    {0x7ff0000000000000ull, 0x0, 0x0000000000000000ull, 0x0, 0x0000000000000000ull, 0x0},
    {0xfff0000000000000ull, 0x0, 0x8000000000000000ull, 0x0, 0x7ff8000000000000ull, 0x1},
    {0x7ff8000000012345ull, 0x0, 0x7ff8000000012345ull, 0x0, 0x7ff8000000012345ull, 0x0},
    {0x7ff0000000012345ull, 0x0, 0x7ff8000000012345ull, 0x1, 0x7ff8000000012345ull, 0x1},
    {0xbff8000000000000ull, 0x0, 0xbfe5500000000000ull, 0x0, 0x7ff8000000000000ull, 0x1},
    {0x4010000000000000ull, 0x0, 0x3fcff00000000000ull, 0x0, 0x3fdff00000000000ull, 0x0},
    {0x3ff0000000000000ull, 0x1000000, 0x3feff00000000000ull, 0x0, 0x3feff00000000000ull, 0x0},
    {0x4000000000000000ull, 0x1000000, 0x3fdff00000000000ull, 0x0, 0x3fe6900000000000ull, 0x0},
    {0x4008000000000000ull, 0x1000000, 0x3fd5500000000000ull, 0x0, 0x3fe2700000000000ull, 0x0},
    {0x3fb999999999999aull, 0x1000000, 0x4024000000000000ull, 0x0, 0x4009500000000000ull, 0x0},
    {0x0010000000000000ull, 0x1000000, 0x7fcff00000000000ull, 0x0, 0x5fdff00000000000ull, 0x0},
    {0x0008000000000000ull, 0x1000000, 0x7ff0000000000000ull, 0x82, 0x7ff0000000000000ull, 0x82},
    {0x0004000000000000ull, 0x1000000, 0x7ff0000000000000ull, 0x82, 0x7ff0000000000000ull, 0x82},
    {0x0003ffffffffffffull, 0x1000000, 0x7ff0000000000000ull, 0x82, 0x7ff0000000000000ull, 0x82},
    {0x0000000000000001ull, 0x1000000, 0x7ff0000000000000ull, 0x82, 0x7ff0000000000000ull, 0x82},
    {0x7fd0000000000000ull, 0x1000000, 0x0000000000000000ull, 0x8, 0x1ffff00000000000ull, 0x0},
    {0x7fe0000000000000ull, 0x1000000, 0x0000000000000000ull, 0x8, 0x1ff6900000000000ull, 0x0},
    {0x7fefffffffffffffull, 0x1000000, 0x0000000000000000ull, 0x8, 0x1ff0000000000000ull, 0x0},
    {0x0000000000000000ull, 0x1000000, 0x7ff0000000000000ull, 0x2, 0x7ff0000000000000ull, 0x2},
    {0x8000000000000000ull, 0x1000000, 0xfff0000000000000ull, 0x2, 0xfff0000000000000ull, 0x2},
    {0x7ff0000000000000ull, 0x1000000, 0x0000000000000000ull, 0x0, 0x0000000000000000ull, 0x0},
    {0xfff0000000000000ull, 0x1000000, 0x8000000000000000ull, 0x0, 0x7ff8000000000000ull, 0x1},
    {0x7ff8000000012345ull, 0x1000000, 0x7ff8000000012345ull, 0x0, 0x7ff8000000012345ull, 0x0},
    {0x7ff0000000012345ull, 0x1000000, 0x7ff8000000012345ull, 0x1, 0x7ff8000000012345ull, 0x1},
    {0xbff8000000000000ull, 0x1000000, 0xbfe5500000000000ull, 0x0, 0x7ff8000000000000ull, 0x1},
    {0x4010000000000000ull, 0x1000000, 0x3fcff00000000000ull, 0x0, 0x3fdff00000000000ull, 0x0},
    {0x3ff0000000000000ull, 0x2000000, 0x3feff00000000000ull, 0x0, 0x3feff00000000000ull, 0x0},
    {0x4000000000000000ull, 0x2000000, 0x3fdff00000000000ull, 0x0, 0x3fe6900000000000ull, 0x0},
    {0x4008000000000000ull, 0x2000000, 0x3fd5500000000000ull, 0x0, 0x3fe2700000000000ull, 0x0},
    {0x3fb999999999999aull, 0x2000000, 0x4024000000000000ull, 0x0, 0x4009500000000000ull, 0x0},
    {0x0010000000000000ull, 0x2000000, 0x7fcff00000000000ull, 0x0, 0x5fdff00000000000ull, 0x0},
    {0x0008000000000000ull, 0x2000000, 0x7fdff00000000000ull, 0x0, 0x5fe6900000000000ull, 0x0},
    {0x0004000000000000ull, 0x2000000, 0x7feff00000000000ull, 0x0, 0x5feff00000000000ull, 0x0},
    {0x0003ffffffffffffull, 0x2000000, 0x7ff0000000000000ull, 0x14, 0x5ff0000000000000ull, 0x0},
    {0x0000000000000001ull, 0x2000000, 0x7ff0000000000000ull, 0x14, 0x617ff00000000000ull, 0x0},
    {0x7fd0000000000000ull, 0x2000000, 0x000ff80000000000ull, 0x0, 0x1ffff00000000000ull, 0x0},
    {0x7fe0000000000000ull, 0x2000000, 0x0007fc0000000000ull, 0x0, 0x1ff6900000000000ull, 0x0},
    {0x7fefffffffffffffull, 0x2000000, 0x0004000000000000ull, 0x0, 0x1ff0000000000000ull, 0x0},
    {0x0000000000000000ull, 0x2000000, 0x7ff0000000000000ull, 0x2, 0x7ff0000000000000ull, 0x2},
    {0x8000000000000000ull, 0x2000000, 0xfff0000000000000ull, 0x2, 0xfff0000000000000ull, 0x2},
    {0x7ff0000000000000ull, 0x2000000, 0x0000000000000000ull, 0x0, 0x0000000000000000ull, 0x0},
    {0xfff0000000000000ull, 0x2000000, 0x8000000000000000ull, 0x0, 0x7ff8000000000000ull, 0x1},
    {0x7ff8000000012345ull, 0x2000000, 0x7ff8000000000000ull, 0x0, 0x7ff8000000000000ull, 0x0},
    {0x7ff0000000012345ull, 0x2000000, 0x7ff8000000000000ull, 0x1, 0x7ff8000000000000ull, 0x1},
    {0xbff8000000000000ull, 0x2000000, 0xbfe5500000000000ull, 0x0, 0x7ff8000000000000ull, 0x1},
    {0x4010000000000000ull, 0x2000000, 0x3fcff00000000000ull, 0x0, 0x3fdff00000000000ull, 0x0},
};

#define MRS_ID(fn, reg) \
  static uint64_t fn() { uint64_t v; asm volatile("mrs %0, " reg : "=r"(v)); return v; }
MRS_ID(r_midr, "s3_0_c0_c0_0") MRS_ID(r_mpidr, "s3_0_c0_c0_5") MRS_ID(r_revidr, "s3_0_c0_c0_6")
MRS_ID(r_pfr0, "s3_0_c0_c4_0") MRS_ID(r_pfr1, "s3_0_c0_c4_1") MRS_ID(r_zfr0, "s3_0_c0_c4_4")
MRS_ID(r_dfr0, "s3_0_c0_c5_0") MRS_ID(r_isar0, "s3_0_c0_c6_0") MRS_ID(r_isar1, "s3_0_c0_c6_1")
MRS_ID(r_isar2, "s3_0_c0_c6_2") MRS_ID(r_mmfr0, "s3_0_c0_c7_0") MRS_ID(r_mmfr1, "s3_0_c0_c7_1")
MRS_ID(r_mmfr2, "s3_0_c0_c7_2") MRS_ID(r_idraz, "s3_0_c0_c7_7")
#undef MRS_ID

// The FP operations under test are asm volatile too: an intrinsic is pure to the compiler, which may move it
// across the FPSR accesses.
static uint64_t fpsr_get() { uint64_t v; asm volatile("mrs %0, fpsr" : "=r"(v) : : "memory"); return v; }
static void fpsr_clear() { asm volatile("msr fpsr, xzr" : : : "memory"); }
static unsigned field(uint64_t r, int shift) { return (r >> shift) & 0xf; }
#endif

static std::string t_regress(const char*) {
#if defined(__aarch64__)
  Res r;
  // --- MRS of the ID registers (Linux: op0=3, op1=0, CRn=0, CRm 0 or 2..7; unknown ones read as zero)
  static uint64_t (*const kRegs[])() = {r_midr, r_mpidr, r_revidr, r_pfr0, r_pfr1, r_zfr0, r_dfr0,
                                        r_isar0, r_isar1, r_isar2, r_mmfr0, r_mmfr1, r_mmfr2, r_idraz};
  uint64_t v[14] = {};
  int sigs = 0, first_sig = -1;
  for (int i = 0; i < 14; i++) {
    int s = guarded([&] { v[i] = kRegs[i](); });
    if (s) { sigs++; if (first_sig < 0) first_sig = i; }
  }
  const uint64_t pfr0 = v[3], isar0 = v[7];
  r.add(F("id: midr=0x%llx mpidr=0x%llx pfr0=0x%llx isar0=0x%llx isar1=0x%llx mmfr0=0x%llx sigill=%d(first #%d)",
          (unsigned long long)v[0], (unsigned long long)v[1], (unsigned long long)pfr0, (unsigned long long)isar0,
          (unsigned long long)v[8], (unsigned long long)v[10], sigs, first_sig));
  r.check(sigs == 0, "mrs_id_registers_no_sigill");
  const unsigned long hw = getauxval(AT_HWCAP), hw2 = getauxval(AT_HWCAP2);
  r.check(hw & HWCAP_CPUID, "hwcap_cpuid");
  if (sigs == 0) {
    auto has = [&](unsigned long bit) { return (hw & bit) != 0; };
    // The kernel derives these HWCAPs from the same fields (arch/arm64/kernel/cpufeature.c arm64_elf_hwcaps).
    bool isar0_ok = (field(isar0, 4) >= 1) == has(HWCAP_AES) && (field(isar0, 4) >= 2) == has(HWCAP_PMULL) &&
                    (field(isar0, 8) >= 1) == has(HWCAP_SHA1) && (field(isar0, 12) >= 1) == has(HWCAP_SHA2) &&
                    (field(isar0, 12) >= 2) == has(HWCAP_SHA512) && (field(isar0, 16) >= 1) == has(HWCAP_CRC32) &&
                    (field(isar0, 20) >= 2) == has(HWCAP_ATOMICS) && (field(isar0, 28) >= 1) == has(HWCAP_ASIMDRDM) &&
                    (field(isar0, 32) >= 1) == has(HWCAP_SHA3) && (field(isar0, 36) >= 1) == has(HWCAP_SM3) &&
                    (field(isar0, 40) >= 1) == has(HWCAP_SM4) && (field(isar0, 44) >= 1) == has(HWCAP_ASIMDDP) &&
                    (field(isar0, 48) >= 1) == has(HWCAP_ASIMDFHM) && (field(isar0, 52) >= 1) == has(HWCAP_FLAGM) &&
                    (field(isar0, 60) >= 1) == ((hw2 & HWCAP2_RNG) != 0);
    r.check(isar0_ok, "id_isar0_matches_hwcap");
    bool pfr0_ok = (field(pfr0, 16) != 0xf) == has(HWCAP_FP) && (field(pfr0, 16) == 1) == has(HWCAP_FPHP) &&
                   (field(pfr0, 20) != 0xf) == has(HWCAP_ASIMD) && (field(pfr0, 20) == 1) == has(HWCAP_ASIMDHP) &&
                   (field(pfr0, 32) >= 1) == has(HWCAP_SVE) && (field(pfr0, 48) >= 1) == has(HWCAP_DIT);
    r.check(pfr0_ok, "id_pfr0_matches_hwcap");
    r.check((v[1] >> 31) & 1, "mpidr_el1_bit31");
    r.check(v[13] == 0, "unallocated_id_register_raz");
  }

  // --- FRECPE / FRSQRTE, golden values, 200 rounds so the JIT tiers translate the loop
  uint64_t saved_fpcr = a_mrs_fpcr();
  int bad32 = 0, bad64 = 0, badv = 0;
  std::string first_bad;
  for (int round = 0; round < 200; round++) {
    for (const EstGolden32& g : kEstGolden32) {
      a_msr_fpcr(g.fpcr);
      uint32_t x = g.in, y, z;
      CLOBBER(&x);
      fpsr_clear();
      asm volatile("fmov s0, %w1\n frecpe s0, s0\n fmov %w0, s0" : "=r"(y) : "r"(x) : "v0");
      uint32_t f1 = (uint32_t)fpsr_get() & 0x9f;
      fpsr_clear();
      asm volatile("fmov s0, %w1\n frsqrte s0, s0\n fmov %w0, s0" : "=r"(z) : "r"(x) : "v0");
      uint32_t f2 = (uint32_t)fpsr_get() & 0x9f;
      a_msr_fpcr(saved_fpcr);
      if (y != g.recpe || f1 != g.recpe_fpsr || z != g.rsqrte || f2 != g.rsqrte_fpsr) {
        if (!bad32++ && first_bad.empty())
          first_bad = F("s(0x%08x,fpcr 0x%x)=0x%08x/%x,0x%08x/%x want 0x%08x/%x,0x%08x/%x", x, g.fpcr, y, f1, z, f2,
                        g.recpe, g.recpe_fpsr, g.rsqrte, g.rsqrte_fpsr);
      }
    }
    for (const EstGolden64& g : kEstGolden64) {
      a_msr_fpcr(g.fpcr);
      uint64_t x = g.in, y, z;
      CLOBBER(&x);
      fpsr_clear();
      asm volatile("fmov d0, %1\n frecpe d0, d0\n fmov %0, d0" : "=r"(y) : "r"(x) : "v0");
      uint32_t f1 = (uint32_t)fpsr_get() & 0x9f;
      fpsr_clear();
      asm volatile("fmov d0, %1\n frsqrte d0, d0\n fmov %0, d0" : "=r"(z) : "r"(x) : "v0");
      uint32_t f2 = (uint32_t)fpsr_get() & 0x9f;
      a_msr_fpcr(saved_fpcr);
      if (y != g.recpe || f1 != g.recpe_fpsr || z != g.rsqrte || f2 != g.rsqrte_fpsr) {
        if (!bad64++ && first_bad.empty())
          first_bad = F("d(0x%llx,fpcr 0x%x)=0x%llx/%x,0x%llx/%x", (unsigned long long)x, g.fpcr,
                        (unsigned long long)y, f1, (unsigned long long)z, f2);
      }
    }
    // Vector .4S: four consecutive table rows with the same FPCR per lane group; FPSR is the OR of the lanes'.
    const size_t n32 = sizeof kEstGolden32 / sizeof *kEstGolden32;
    for (size_t i = 0; i + 3 < n32; i++) {
      const EstGolden32* g = &kEstGolden32[i];
      if (g[0].fpcr != g[3].fpcr) continue;
      uint32_t in[4] = {g[0].in, g[1].in, g[2].in, g[3].in}, o1[4], o2[4];
      CLOBBER(in);
      a_msr_fpcr(g[0].fpcr);
      fpsr_clear();
      asm volatile("ld1 {v0.4s}, [%1]\n frecpe v0.4s, v0.4s\n st1 {v0.4s}, [%0]" : : "r"(o1), "r"(in) : "v0", "memory");
      uint32_t f1 = (uint32_t)fpsr_get() & 0x9f;
      fpsr_clear();
      asm volatile("ld1 {v0.4s}, [%1]\n frsqrte v0.4s, v0.4s\n st1 {v0.4s}, [%0]" : : "r"(o2), "r"(in) : "v0", "memory");
      uint32_t f2 = (uint32_t)fpsr_get() & 0x9f;
      a_msr_fpcr(saved_fpcr);
      bool ok = f1 == (g[0].recpe_fpsr | g[1].recpe_fpsr | g[2].recpe_fpsr | g[3].recpe_fpsr) &&
                f2 == (g[0].rsqrte_fpsr | g[1].rsqrte_fpsr | g[2].rsqrte_fpsr | g[3].rsqrte_fpsr);
      for (int l = 0; l < 4; l++) ok &= o1[l] == g[l].recpe && o2[l] == g[l].rsqrte;
      if (!ok && !badv++ && first_bad.empty())
        first_bad = F("4s(0x%08x..)=0x%08x.. want 0x%08x..", in[0], o1[0], g[0].recpe);
    }
  }
  a_msr_fpcr(saved_fpcr);
  r.add(F("frecpe(1.0)=0x%08x bad: s=%d d=%d 4s=%d %s", kEstGolden32[0].recpe, bad32, bad64, badv, first_bad.c_str()));
  r.check(bad32 == 0, "frecpe_frsqrte_f32_exact");
  r.check(bad64 == 0, "frecpe_frsqrte_f64_exact");
  r.check(badv == 0, "frecpe_frsqrte_vector_exact");
  return r.str();
#else
  return "SKIP AArch64-only regressions (x86_64 is the native control)";
#endif
}

// ---------------------------------------------------------------------------------------------
struct Test {
  const char* name;
  std::string (*fn)(const char*);
};
static const Test kTests[] = {
    {"abi", t_abi},         {"neon", t_neon},         {"crypto", t_crypto}, {"isa", t_isa},   {"atomics", t_atomics},
    {"tls", t_tls},         {"threads", t_threads},   {"syscalls", t_syscalls}, {"dlopen", t_dlopen}, {"cxx_exceptions", t_cxx},
    {"jit", t_jit},         {"signals", t_signals},   {"gles", t_gles},     {"vulkan", t_vulkan},
    {"regress", t_regress},
};

// ---- JNI ----
static jclass g_cls;

static jint registered_add(JNIEnv*, jclass, jint a, jint b) { return a + b; }

extern "C" JNIEXPORT jint JNI_OnLoad(JavaVM* vm, void*) {
  g_vm = vm;
  JNIEnv* env;
  if (vm->GetEnv((void**)&env, JNI_VERSION_1_6) != JNI_OK) return JNI_ERR;
  jclass c = env->FindClass("dev/anybook/probe/MainActivity");
  g_cls = (jclass)env->NewGlobalRef(c);
  static const JNINativeMethod m[] = {{"registeredAdd", "(II)I", (void*)registered_add}};
  if (env->RegisterNatives(c, m, 1) != 0) return JNI_ERR;
  return JNI_VERSION_1_6;
}

extern "C" JNIEXPORT jstring JNICALL Java_dev_anybook_probe_MainActivity_nativeInfo(JNIEnv* env, jclass) {
  return env->NewStringUTF(F("abi=%s compiler=[clang %s]", ABI, __clang_version__).c_str());
}

extern "C" JNIEXPORT jobjectArray JNICALL Java_dev_anybook_probe_MainActivity_listTests(JNIEnv* env, jclass) {
  const int n = sizeof kTests / sizeof kTests[0];
  jobjectArray a = env->NewObjectArray(n, env->FindClass("java/lang/String"), nullptr);
  for (int i = 0; i < n; i++) env->SetObjectArrayElement(a, i, env->NewStringUTF(kTests[i].name));
  return a;
}

extern "C" JNIEXPORT jstring JNICALL Java_dev_anybook_probe_MainActivity_runTest(JNIEnv* env, jclass, jstring jname, jstring jdir) {
  const char* name = env->GetStringUTFChars(jname, nullptr);
  const char* dir = env->GetStringUTFChars(jdir, nullptr);
  std::string res = "FAIL unknown test";
  for (const Test& t : kTests)
    if (!strcmp(t.name, name)) {
      try {
        res = t.fn(dir);
      } catch (const std::exception& e) {
        res = std::string("FAIL uncaught C++ exception: ") + e.what();
      }
    }
  env->ReleaseStringUTFChars(jname, name);
  env->ReleaseStringUTFChars(jdir, dir);
  return env->NewStringUTF(res.c_str());
}

extern "C" JNIEXPORT jstring JNICALL Java_dev_anybook_probe_MainActivity_nativeArgs(
    JNIEnv* env, jclass, jint a, jlong b, jfloat c, jdouble d, jboolean e, jbyte f, jchar g, jshort h, jint i, jlong j, jfloat k,
    jdouble l, jstring m, jintArray n, jfloat o, jdouble p, jint q, jlong r, jfloat s, jdouble t) {
  const char* ms = env->GetStringUTFChars(m, nullptr);
  jint len = env->GetArrayLength(n), sum = 0;
  jint* el = env->GetIntArrayElements(n, nullptr);
  for (jint x = 0; x < len; x++) sum += el[x];
  env->ReleaseIntArrayElements(n, el, JNI_ABORT);
  std::string out = F("%d|%lld|%08x|%016llx|%d|%d|%d|%d|%d|%lld|%08x|%016llx|%s|%d|%08x|%016llx|%d|%lld|%08x|%016llx", a,
                      (long long)b, u_of(c), (unsigned long long)u_of(d), e ? 1 : 0, f, (int)g, h, i, (long long)j, u_of(k),
                      (unsigned long long)u_of(l), ms, sum, u_of(o), (unsigned long long)u_of(p), q, (long long)r, u_of(s),
                      (unsigned long long)u_of(t));
  env->ReleaseStringUTFChars(m, ms);
  return env->NewStringUTF(out.c_str());
}

extern "C" JNIEXPORT void JNICALL Java_dev_anybook_probe_MainActivity_nativeThrow(JNIEnv* env, jclass, jstring msg) {
  const char* s = env->GetStringUTFChars(msg, nullptr);
  env->ThrowNew(env->FindClass("java/lang/IllegalStateException"), s);
  env->ReleaseStringUTFChars(msg, s);
}

static std::string fmt_floats(float a, double b, float c, double d, int e, float f, double g, float h, double i, float j,
                              long long k, float l, double m) {
  return F("%08x|%016llx|%08x|%016llx|%d|%08x|%016llx|%08x|%016llx|%08x|%lld|%08x|%016llx", u_of(a), (unsigned long long)u_of(b),
           u_of(c), (unsigned long long)u_of(d), e, u_of(f), (unsigned long long)u_of(g), u_of(h), (unsigned long long)u_of(i),
           u_of(j), k, u_of(l), (unsigned long long)u_of(m));
}

extern "C" JNIEXPORT jstring JNICALL Java_dev_anybook_probe_MainActivity_nativeCallbacks(JNIEnv* env, jobject self) {
  Res r;
  jclass c = env->GetObjectClass(self);
  jmethodID cb = env->GetMethodID(c, "callback", "(ILjava/lang/String;)I");
  jstring s = env->NewStringUTF("h\xc3\xa9llo");
  long long sum = 0;
  for (int i = 0; i < 10000; i++) sum += env->CallIntMethod(self, cb, i, s);
  r.check(sum == 100040000LL, "call_int_method_10k");
  jfieldID fid = env->GetFieldID(c, "field", "I");
  env->SetIntField(self, fid, env->GetIntField(self, fid) + 35);
  r.check(env->GetIntField(self, fid) == 42, "int_field_get_set");
  jclass math = env->FindClass("java/lang/Math");
  jmethodID sq = env->GetStaticMethodID(math, "sqrt", "(D)D");
  r.check(env->CallStaticDoubleMethod(math, sq, 2.0) == sqrt(2.0), "static_double_method");
  // 13 arguments, 11 of them floating point: more than the FP argument registers, so varargs and stack paths are used.
  jmethodID ff = env->GetStaticMethodID(g_cls, "fmtFloats", "(FDFDIFDFDFJFD)Ljava/lang/String;");
  const float fa = 1.5f, fc = -0.0f, ff1 = f_of(0x00000001), fh = 3.4e38f, fj = -2.25f, fl = f_of(0x7fc00123);
  const double db = 1e-310, dd = -7.75, dg = M_PI, di = 1e300, dm = d_of(0x7ff8000000000abcull);
  std::string want = fmt_floats(fa, db, fc, dd, -9, ff1, dg, fh, di, fj, -123456789012LL, fl, dm);
  jstring g1 = (jstring)env->CallStaticObjectMethod(g_cls, ff, fa, db, fc, dd, -9, ff1, dg, fh, di, fj, (jlong)-123456789012LL, fl, dm);
  jvalue av[13];
  av[0].f = fa; av[1].d = db; av[2].f = fc; av[3].d = dd; av[4].i = -9; av[5].f = ff1; av[6].d = dg;
  av[7].f = fh; av[8].d = di; av[9].f = fj; av[10].j = -123456789012LL; av[11].f = fl; av[12].d = dm;
  jstring g2 = (jstring)env->CallStaticObjectMethodA(g_cls, ff, av);
  const char* s1 = g1 ? env->GetStringUTFChars(g1, nullptr) : "";
  const char* s2 = g2 ? env->GetStringUTFChars(g2, nullptr) : "";
  r.check(want == s1, "fp_args_varargs");
  r.check(want == s2, "fp_args_jvalue_array");
  if (want != s1 || want != s2) r.add("want=[" + want + "] varargs=[" + s1 + "] jvalue=[" + s2 + "]");
  if (g1) env->ReleaseStringUTFChars(g1, s1);
  if (g2) env->ReleaseStringUTFChars(g2, s2);
  jintArray arr = env->NewIntArray(1000);
  std::vector<jint> v(1000);
  for (int i = 0; i < 1000; i++) v[i] = i;
  env->SetIntArrayRegion(arr, 0, 1000, v.data());
  jint* p = (jint*)env->GetPrimitiveArrayCritical(arr, nullptr);
  long long s3 = 0;
  for (int i = 0; i < 1000; i++) s3 += p[i];
  env->ReleasePrimitiveArrayCritical(arr, p, JNI_ABORT);
  r.check(s3 == 499500, "array_critical");
  const char* u = env->GetStringUTFChars(s, nullptr);
  r.check(!strcmp(u, "h\xc3\xa9llo") && env->GetStringLength(s) == 5, "string_utf");
  env->ReleaseStringUTFChars(s, u);
  jmethodID th = env->GetMethodID(c, "throwingCallback", "()V");
  env->CallVoidMethod(self, th);
  bool ex = env->ExceptionCheck();
  jthrowable t = env->ExceptionOccurred();
  env->ExceptionClear();
  r.check(ex && t != nullptr, "java_exception_check_clear");
  jclass sb = env->FindClass("java/lang/StringBuilder");
  jobject o = env->NewObject(sb, env->GetMethodID(sb, "<init>", "(Ljava/lang/String;)V"), env->NewStringUTF("ab"));
  jstring os = (jstring)env->CallObjectMethod(o, env->GetMethodID(sb, "toString", "()Ljava/lang/String;"));
  const char* osc = env->GetStringUTFChars(os, nullptr);
  r.check(!strcmp(osc, "ab"), "new_object");
  env->ReleaseStringUTFChars(os, osc);
  bool frame = env->PushLocalFrame(2000) == 0;
  for (int i = 0; i < 1500; i++) env->NewStringUTF("x");
  env->PopLocalFrame(nullptr);
  r.check(frame, "local_frame_1500_refs");
  std::atomic<int> att{-1};
  std::thread([&] {
    JNIEnv* e2;
    JavaVMAttachArgs aa = {JNI_VERSION_1_6, (char*)"probe-native", nullptr};
    if (g_vm->AttachCurrentThread(&e2, &aa) != JNI_OK) return;
    jmethodID scb = e2->GetStaticMethodID(g_cls, "staticCallback", "(I)I");
    att = e2->CallStaticIntMethod(g_cls, scb, 20);
    g_vm->DetachCurrentThread();
  }).join();
  r.check(att == 41, "attach_native_thread");
  char nb[64];
  jobject bb = env->NewDirectByteBuffer(nb, 64);
  r.check(env->GetDirectBufferAddress(bb) == nb && env->GetDirectBufferCapacity(bb) == 64, "direct_bytebuffer");
  return env->NewStringUTF(r.str().c_str());
}
