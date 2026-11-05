// SPDX-License-Identifier: Apache-2.0
// simd-bench: vector kernels for measuring ARM translation (ANAL-380, docs/arm-performance.md).
//
// One source for arm64 and x86_64. The baseline kernels use clang's 128-bit vector types, which lower to NEON on
// arm64 and SSE on x86_64, so both builds do the same work at the same width. check-isa.py confirms from the
// disassembly that every baseline kernel really uses vector instructions on both. The optional kernels (CRC32C,
// AES-128) use each architecture's own instructions and run only where the CPU reports them; their results are
// checked against a scalar reference, so the arm64 and x86_64 builds must print the same checksums.
//
// usage: simd-bench [-r REPEATS] [-s SCALE] [-k KERNEL]
// Output: one JSON object per line: a header (arch, hwcap, CPU), then one line per kernel with its checksum, the
// median and minimum time per element over REPEATS timed runs, and "ok" (checksum equals the scalar reference).
// Exit 0 if every kernel that ran is ok, 1 if any checksum is wrong, 2 on bad usage.
#define _GNU_SOURCE
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#if defined(__aarch64__)
#include <arm_neon.h>
#include <sys/auxv.h>
#define ARCH "aarch64"
#ifndef HWCAP_AES
#define HWCAP_AES (1 << 3)
#endif
#ifndef HWCAP_CRC32
#define HWCAP_CRC32 (1 << 7)
#endif
#elif defined(__x86_64__)
#include <immintrin.h>
#define ARCH "x86_64"
#else
#error "simd-bench is built for arm64 and x86_64"
#endif

typedef float f32x4 __attribute__((vector_size(16)));
typedef int32_t i32x4 __attribute__((vector_size(16)));
typedef int16_t i16x8 __attribute__((vector_size(16)));
typedef uint16_t u16x8 __attribute__((vector_size(16)));
typedef int8_t i8x16 __attribute__((vector_size(16)));
typedef uint8_t u8x16 __attribute__((vector_size(16)));
typedef int8_t i8x8 __attribute__((vector_size(8)));
typedef uint8_t u8x8 __attribute__((vector_size(8)));

#define BARRIER() __asm__ volatile("" ::: "memory")
#define KERNEL __attribute__((noinline))

static inline f32x4 ld_f32(const float *p) { f32x4 v; memcpy(&v, p, 16); return v; }
static inline void st_f32(float *p, f32x4 v) { memcpy(p, &v, 16); }
static inline i8x16 ld_i8(const int8_t *p) { i8x16 v; memcpy(&v, p, 16); return v; }
static inline u8x16 ld_u8(const uint8_t *p) { u8x16 v; memcpy(&v, p, 16); return v; }
static inline void st_u8(uint8_t *p, u8x16 v) { memcpy(p, &v, 16); }

// ---- baseline kernels (128-bit vectors on both architectures) ----

// a = b + s * c, separate multiply and add (built with -ffp-contract=off on both).
KERNEL void k_triad_f32(float *a, const float *b, const float *c, float s, size_t n) {
  f32x4 vs = {s, s, s, s};
  for (size_t i = 0; i < n; i += 4) st_f32(a + i, ld_f32(b + i) + vs * ld_f32(c + i));
}

// The same loop, scalar: the vectorizers are off for it, so it is the control for the vector speedup.
KERNEL void k_triad_scalar(float *a, const float *b, const float *c, float s, size_t n) {
#pragma clang loop vectorize(disable) interleave(disable)
  for (size_t i = 0; i < n; i++) a[i] = b[i] + s * c[i];
}

// Dot product with four 4-lane accumulators, reduced in a fixed order, so the sum is bit-identical everywhere.
KERNEL float k_dot_f32(const float *a, const float *b, size_t n) {
  f32x4 s0 = {0}, s1 = {0}, s2 = {0}, s3 = {0};
  for (size_t i = 0; i < n; i += 16) {
    s0 += ld_f32(a + i) * ld_f32(b + i);
    s1 += ld_f32(a + i + 4) * ld_f32(b + i + 4);
    s2 += ld_f32(a + i + 8) * ld_f32(b + i + 8);
    s3 += ld_f32(a + i + 12) * ld_f32(b + i + 12);
  }
  f32x4 s = (s0 + s1) + (s2 + s3);
  return (s[0] + s[1]) + (s[2] + s[3]);
}

// int8 dot product: widen to int16, multiply, widen the products to int32 and accumulate (quantized inference).
KERNEL int32_t k_dot_i8(const int8_t *a, const int8_t *b, size_t n) {
  i32x4 acc = {0};
  for (size_t i = 0; i < n; i += 16) {
    i8x16 va = ld_i8(a + i), vb = ld_i8(b + i);
    i16x8 lo = __builtin_convertvector(__builtin_shufflevector(va, va, 0, 1, 2, 3, 4, 5, 6, 7), i16x8) *
               __builtin_convertvector(__builtin_shufflevector(vb, vb, 0, 1, 2, 3, 4, 5, 6, 7), i16x8);
    i16x8 hi = __builtin_convertvector(__builtin_shufflevector(va, va, 8, 9, 10, 11, 12, 13, 14, 15), i16x8) *
               __builtin_convertvector(__builtin_shufflevector(vb, vb, 8, 9, 10, 11, 12, 13, 14, 15), i16x8);
    acc += __builtin_convertvector(__builtin_shufflevector(lo, lo, 0, 1, 2, 3), i32x4);
    acc += __builtin_convertvector(__builtin_shufflevector(lo, lo, 4, 5, 6, 7), i32x4);
    acc += __builtin_convertvector(__builtin_shufflevector(hi, hi, 0, 1, 2, 3), i32x4);
    acc += __builtin_convertvector(__builtin_shufflevector(hi, hi, 4, 5, 6, 7), i32x4);
  }
  return acc[0] + acc[1] + acc[2] + acc[3];
}

// Horizontal [1 2 1]/4 blur of 8-bit pixels, rounded: out[i] = (in[i-1] + 2 in[i] + in[i+1] + 2) >> 2, i in 1..n.
// The input has one pixel of padding on each side.
KERNEL void k_blur_u8(uint8_t *out, const uint8_t *in, size_t n) {
  const u16x8 two = {2, 2, 2, 2, 2, 2, 2, 2};
  for (size_t i = 1; i <= n; i += 16) {
    u8x16 l = ld_u8(in + i - 1), c = ld_u8(in + i), r = ld_u8(in + i + 1);
    u16x8 lo = __builtin_convertvector(__builtin_shufflevector(l, l, 0, 1, 2, 3, 4, 5, 6, 7), u16x8) +
               __builtin_convertvector(__builtin_shufflevector(c, c, 0, 1, 2, 3, 4, 5, 6, 7), u16x8) * two +
               __builtin_convertvector(__builtin_shufflevector(r, r, 0, 1, 2, 3, 4, 5, 6, 7), u16x8) + two;
    u16x8 hi = __builtin_convertvector(__builtin_shufflevector(l, l, 8, 9, 10, 11, 12, 13, 14, 15), u16x8) +
               __builtin_convertvector(__builtin_shufflevector(c, c, 8, 9, 10, 11, 12, 13, 14, 15), u16x8) * two +
               __builtin_convertvector(__builtin_shufflevector(r, r, 8, 9, 10, 11, 12, 13, 14, 15), u16x8) + two;
    lo >>= 2;
    hi >>= 2;
    u8x8 a = __builtin_convertvector(lo, u8x8), b = __builtin_convertvector(hi, u8x8);
    st_u8(out + i - 1, __builtin_shufflevector(a, b, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15));
  }
}

// Running minimum and maximum (no NaN or signed zeros in the data, so the architectures' min/max rules agree).
KERNEL void k_minmax_f32(const float *a, size_t n, float *mn, float *mx) {
  f32x4 lo = ld_f32(a), hi = lo;
  for (size_t i = 4; i < n; i += 4) {
    f32x4 v = ld_f32(a + i);
    lo = __builtin_elementwise_min(lo, v);
    hi = __builtin_elementwise_max(hi, v);
  }
  *mn = __builtin_fminf(__builtin_fminf(lo[0], lo[1]), __builtin_fminf(lo[2], lo[3]));
  *mx = __builtin_fmaxf(__builtin_fmaxf(hi[0], hi[1]), __builtin_fmaxf(hi[2], hi[3]));
}

// RGBA -> BGRA: a constant byte shuffle (TBL on arm64, PSHUFB on x86_64).
KERNEL void k_swizzle_u8(uint8_t *out, const uint8_t *in, size_t n) {
  for (size_t i = 0; i < n; i += 16) {
    u8x16 v = ld_u8(in + i);
    st_u8(out + i, __builtin_shufflevector(v, v, 2, 1, 0, 3, 6, 5, 4, 7, 10, 9, 8, 11, 14, 13, 12, 15));
  }
}

// ---- optional kernels: each architecture's own instructions, run only if the CPU reports them ----

static const uint8_t SBOX[256] = {
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76, 0xca, 0x82, 0xc9,
    0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0, 0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f,
    0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15, 0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07,
    0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75, 0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3,
    0x29, 0xe3, 0x2f, 0x84, 0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58,
    0xcf, 0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8, 0x51, 0xa3,
    0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2, 0xcd, 0x0c, 0x13, 0xec, 0x5f,
    0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73, 0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88,
    0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb, 0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac,
    0x62, 0x91, 0x95, 0xe4, 0x79, 0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a,
    0xae, 0x08, 0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a, 0x70,
    0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e, 0xe1, 0xf8, 0x98, 0x11,
    0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf, 0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42,
    0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16};

static void aes128_expand(const uint8_t key[16], uint8_t rk[176]) {
  static const uint8_t rcon[10] = {0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36};
  memcpy(rk, key, 16);
  for (int i = 4; i < 44; i++) {
    uint8_t t[4];
    memcpy(t, rk + 4 * (i - 1), 4);
    if (i % 4 == 0) {
      uint8_t u = t[0];
      t[0] = SBOX[t[1]] ^ rcon[i / 4 - 1];
      t[1] = SBOX[t[2]];
      t[2] = SBOX[t[3]];
      t[3] = SBOX[u];
    }
    for (int j = 0; j < 4; j++) rk[4 * i + j] = rk[4 * (i - 4) + j] ^ t[j];
  }
}

static uint8_t xtime(uint8_t x) { return (uint8_t)((x << 1) ^ ((x >> 7) * 0x1b)); }

// FIPS-197 AES-128, one block, byte by byte: the reference.
static void aes128_ref_block(const uint8_t rk[176], const uint8_t in[16], uint8_t out[16]) {
  uint8_t s[16], t[16];
  for (int i = 0; i < 16; i++) s[i] = in[i] ^ rk[i];
  for (int r = 1; r <= 10; r++) {
    for (int i = 0; i < 16; i++) t[i] = SBOX[s[(i + 4 * (i % 4)) % 16]];  // SubBytes + ShiftRows
    if (r < 10) {
      for (int c = 0; c < 4; c++) {
        uint8_t *p = t + 4 * c, a0 = p[0], a1 = p[1], a2 = p[2], a3 = p[3], x = a0 ^ a1 ^ a2 ^ a3;
        p[0] ^= x ^ xtime(a0 ^ a1);
        p[1] ^= x ^ xtime(a1 ^ a2);
        p[2] ^= x ^ xtime(a2 ^ a3);
        p[3] ^= x ^ xtime(a3 ^ a0);
      }
    }
    for (int i = 0; i < 16; i++) s[i] = t[i] ^ rk[16 * r + i];
  }
  memcpy(out, s, 16);
}

static uint32_t crc32c_ref(uint32_t crc, const uint8_t *p, size_t n) {
  crc = ~crc;
  for (size_t i = 0; i < n; i++) {
    crc ^= p[i];
    for (int k = 0; k < 8; k++) crc = (crc >> 1) ^ (0x82f63b78u & (0u - (crc & 1)));
  }
  return ~crc;
}

#if defined(__aarch64__)
static int have_crc(void) { return (getauxval(AT_HWCAP) & HWCAP_CRC32) != 0; }
static int have_aes(void) { return (getauxval(AT_HWCAP) & HWCAP_AES) != 0; }

__attribute__((target("crc"))) KERNEL uint32_t k_crc32c(const uint8_t *p, size_t n) {
  uint32_t c = 0xffffffffu;
  for (size_t i = 0; i < n; i += 8) {
    uint64_t v;
    memcpy(&v, p + i, 8);
    c = __builtin_arm_crc32cd(c, v);
  }
  return ~c;
}

// ECB over n bytes; AESE does AddRoundKey + SubBytes + ShiftRows, AESMC MixColumns.
__attribute__((target("aes"))) KERNEL void k_aes128(uint8_t *out, const uint8_t *in, size_t n, const uint8_t rk[176]) {
  uint8x16_t k[11];
  for (int r = 0; r < 11; r++) k[r] = vld1q_u8(rk + 16 * r);
  for (size_t i = 0; i < n; i += 16) {
    uint8x16_t s = vld1q_u8(in + i);
    for (int r = 0; r < 9; r++) s = vaesmcq_u8(vaeseq_u8(s, k[r]));
    s = veorq_u8(vaeseq_u8(s, k[9]), k[10]);
    vst1q_u8(out + i, s);
  }
}
#else
static int have_crc(void) { return __builtin_cpu_supports("sse4.2"); }
static int have_aes(void) { return __builtin_cpu_supports("aes"); }

__attribute__((target("sse4.2"))) KERNEL uint32_t k_crc32c(const uint8_t *p, size_t n) {
  uint64_t c = 0xffffffffu;
  for (size_t i = 0; i < n; i += 8) {
    uint64_t v;
    memcpy(&v, p + i, 8);
    c = _mm_crc32_u64(c, v);
  }
  return ~(uint32_t)c;
}

// ECB over n bytes; AESENC does ShiftRows + SubBytes + MixColumns + AddRoundKey.
__attribute__((target("aes,sse2"))) KERNEL void k_aes128(uint8_t *out, const uint8_t *in, size_t n,
                                                       const uint8_t rk[176]) {
  __m128i k[11];
  for (int r = 0; r < 11; r++) k[r] = _mm_loadu_si128((const __m128i *)(rk + 16 * r));
  for (size_t i = 0; i < n; i += 16) {
    __m128i s = _mm_xor_si128(_mm_loadu_si128((const __m128i *)(in + i)), k[0]);
    for (int r = 1; r < 10; r++) s = _mm_aesenc_si128(s, k[r]);
    _mm_storeu_si128((__m128i *)(out + i), _mm_aesenclast_si128(s, k[10]));
  }
}
#endif

// ---- harness ----

static uint64_t fnv1a(const void *p, size_t n) {
  const uint8_t *b = p;
  uint64_t h = 0xcbf29ce484222325ull;
  for (size_t i = 0; i < n; i++) h = (h ^ b[i]) * 0x100000001b3ull;
  return h;
}

static uint64_t bits_f32(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }

static double now_ns(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec * 1e9 + ts.tv_nsec;
}

static int cmp_d(const void *a, const void *b) {
  double x = *(const double *)a, y = *(const double *)b;
  return (x > y) - (x < y);
}

// 16K elements: three float arrays of 64 KiB stay in L2 on both Zen 5 and Zen 5c, so the kernels measure code,
// not memory bandwidth.
#define N 16384
static float A[N], B[N], C[N];
static int8_t I8A[N], I8B[N];
static uint8_t U8IN[N + 32], U8OUT[N + 32];

static uint32_t lcg_state = 12345;
static uint32_t lcg(void) { return lcg_state = lcg_state * 1664525u + 1013904223u; }

static void fill(void) {
  for (int i = 0; i < N; i++) {
    B[i] = 0.5f + (lcg() >> 8) * (1.5f / 16777216.0f);  // [0.5, 2): no denormals, NaN or signed zeros
    C[i] = 0.5f + (lcg() >> 8) * (1.5f / 16777216.0f);
    I8A[i] = (int8_t)(lcg() >> 24);
    I8B[i] = (int8_t)(lcg() >> 24);
  }
  for (int i = 0; i < N + 32; i++) U8IN[i] = (uint8_t)(lcg() >> 24);
}

enum { TRIAD, TRIAD_SCALAR, DOT_F32, DOT_I8, BLUR_U8, MINMAX_F32, SWIZZLE_U8, CRC32C, AES128, NKERNELS };
static const char *NAMES[NKERNELS] = {"triad_f32", "triad_scalar", "dot_f32",   "dot_i8", "blur_u8",
                                      "minmax_f32", "swizzle_u8",  "crc32c",    "aes128"};
static const char *CLASS[NKERNELS] = {"baseline", "scalar", "baseline", "baseline", "baseline",
                                      "baseline", "baseline", "optional", "optional"};
static uint8_t RK[176];
static float F_MN, F_MX, F_DOT;
static int32_t I_DOT;
static uint32_t U_CRC;

// One call of a kernel over the whole data set. Only this is timed.
static void run_once(int k) {
  switch (k) {
    case TRIAD: k_triad_f32(A, B, C, 1.25f, N); break;
    case TRIAD_SCALAR: k_triad_scalar(A, B, C, 1.25f, N); break;
    case DOT_F32: F_DOT = k_dot_f32(B, C, N); break;
    case DOT_I8: I_DOT = k_dot_i8(I8A, I8B, N); break;
    case BLUR_U8: k_blur_u8(U8OUT, U8IN, N); break;
    case MINMAX_F32: k_minmax_f32(B, N, &F_MN, &F_MX); break;
    case SWIZZLE_U8: k_swizzle_u8(U8OUT, U8IN, N); break;
    case CRC32C: U_CRC = k_crc32c(U8IN, N); break;
    case AES128: k_aes128(U8OUT, U8IN, N, RK); break;
  }
}

// The checksum of what the last call produced.
static uint64_t result(int k) {
  switch (k) {
    case TRIAD:
    case TRIAD_SCALAR: return fnv1a(A, sizeof A);
    case DOT_F32: return bits_f32(F_DOT);
    case DOT_I8: return (uint32_t)I_DOT;
    case MINMAX_F32: return bits_f32(F_MN) << 32 | bits_f32(F_MX);
    case CRC32C: return U_CRC;
    default: return fnv1a(U8OUT, N);
  }
}

// The same results, computed one element at a time in plain C.
static uint64_t reference(int k) {
  static float ra[N];
  static uint8_t rb[N];
  switch (k) {
    case TRIAD:
    case TRIAD_SCALAR:
      for (int i = 0; i < N; i++) { volatile float p = 1.25f * C[i]; ra[i] = B[i] + p; }
      return fnv1a(ra, sizeof ra);
    case DOT_F32: {
      float s[16] = {0};
      for (int i = 0; i < N; i += 16)
        for (int l = 0; l < 16; l++) { volatile float p = B[i + l] * C[i + l]; s[l] = s[l] + p; }
      float v[4];
      for (int l = 0; l < 4; l++) v[l] = (s[l] + s[l + 4]) + (s[l + 8] + s[l + 12]);
      return bits_f32((v[0] + v[1]) + (v[2] + v[3]));
    }
    case DOT_I8: {
      int32_t s = 0;
      for (int i = 0; i < N; i++) s += (int16_t)(I8A[i] * I8B[i]);
      return (uint32_t)s;
    }
    case BLUR_U8:
      for (int i = 1; i <= N; i++) rb[i - 1] = (uint8_t)((U8IN[i - 1] + 2 * U8IN[i] + U8IN[i + 1] + 2) >> 2);
      return fnv1a(rb, N);
    case MINMAX_F32: {
      float mn = B[0], mx = B[0];
      for (int i = 1; i < N; i++) { if (B[i] < mn) mn = B[i]; if (B[i] > mx) mx = B[i]; }
      return bits_f32(mn) << 32 | bits_f32(mx);
    }
    case SWIZZLE_U8:
      for (int i = 0; i < N; i += 4) { rb[i] = U8IN[i + 2]; rb[i + 1] = U8IN[i + 1]; rb[i + 2] = U8IN[i]; rb[i + 3] = U8IN[i + 3]; }
      return fnv1a(rb, N);
    case CRC32C: return crc32c_ref(0, U8IN, N);
    case AES128:
      for (int i = 0; i < N; i += 16) aes128_ref_block(RK, U8IN + i, rb + i);
      return fnv1a(rb, N);
  }
  return 0;
}

// Calls per timed run at SCALE 1: about 100 ms per kernel natively on the build host's Zen 4.
static const int CALLS[NKERNELS] = {80000, 30000, 120000, 90000, 100000, 40000, 500000, 90000, 90000};

static int self_check_aes(void) {
  // FIPS-197 appendix C.1.
  static const uint8_t key[16] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15};
  static const uint8_t pt[16] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
                                 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff};
  static const uint8_t ct[16] = {0x69, 0xc4, 0xe0, 0xd8, 0x6a, 0x7b, 0x04, 0x30,
                                 0xd8, 0xcd, 0xb7, 0x80, 0x70, 0xb4, 0xc5, 0x5a};
  uint8_t rk[176], out[16];
  aes128_expand(key, rk);
  aes128_ref_block(rk, pt, out);
  return memcmp(out, ct, 16) == 0;
}

int main(int argc, char **argv) {
  int repeats = 5;
  double scale = 1.0;
  const char *only = NULL;
  int opt;
  while ((opt = getopt(argc, argv, "r:s:k:")) != -1) {
    if (opt == 'r') repeats = atoi(optarg);
    else if (opt == 's') scale = atof(optarg);
    else if (opt == 'k') only = optarg;
    else { fprintf(stderr, "usage: simd-bench [-r REPEATS] [-s SCALE] [-k KERNEL]\n"); return 2; }
  }
  if (repeats < 1 || repeats > 99 || !(scale > 0)) { fprintf(stderr, "simd-bench: bad -r or -s\n"); return 2; }

  fill();
  static const uint8_t key[16] = {0x2b, 0x7e, 0x15, 0x16, 0x28, 0xae, 0xd2, 0xa6,
                                  0xab, 0xf7, 0x15, 0x88, 0x09, 0xcf, 0x4f, 0x3c};
  aes128_expand(key, RK);
  cpu_set_t set;
  CPU_ZERO(&set);
  sched_getaffinity(0, sizeof set, &set);
  unsigned long hwcap = 0;
#if defined(__aarch64__)
  hwcap = getauxval(AT_HWCAP);
#endif
  printf("{\"tool\":\"simd-bench\",\"version\":1,\"arch\":\"" ARCH "\",\"hwcap\":\"0x%lx\",\"cpu\":%d,"
         "\"allowed_cpus\":%d,\"crc\":%d,\"aes\":%d,\"repeats\":%d,\"scale\":%g,\"elements\":%d,"
         "\"aes_reference_ok\":%d}\n",
         hwcap, sched_getcpu(), CPU_COUNT(&set), have_crc(), have_aes(), repeats, scale, N, self_check_aes());
  fflush(stdout);

  int bad = !self_check_aes();
  for (int k = 0; k < NKERNELS; k++) {
    if (only && strcmp(only, NAMES[k])) continue;
    if ((k == CRC32C && !have_crc()) || (k == AES128 && !have_aes())) {
      printf("{\"kernel\":\"%s\",\"class\":\"%s\",\"skipped\":\"the CPU doesn't report it\"}\n", NAMES[k], CLASS[k]);
      continue;
    }
    uint64_t want = reference(k);
    run_once(k);  // the first call warms up (and, translated, gets translated)
    int calls = (int)(CALLS[k] * scale);
    if (calls < 1) calls = 1;
    double t[99];
    for (int r = 0; r < repeats; r++) {
      double t0 = now_ns();
      for (int c = 0; c < calls; c++) { run_once(k); BARRIER(); }
      t[r] = (now_ns() - t0) / ((double)calls * N);
    }
    qsort(t, repeats, sizeof t[0], cmp_d);
    uint64_t got = result(k);
    int ok = got == want;
    bad |= !ok;
    printf("{\"kernel\":\"%s\",\"class\":\"%s\",\"checksum\":\"0x%016llx\",\"ok\":%s,\"calls\":%d,"
           "\"ns_per_elem_median\":%.6f,\"ns_per_elem_min\":%.6f,\"cpu\":%d}\n",
           NAMES[k], CLASS[k], (unsigned long long)got, ok ? "true" : "false", calls, t[repeats / 2], t[0],
           sched_getcpu());
    fflush(stdout);
  }
  return bad ? 1 : 0;
}
