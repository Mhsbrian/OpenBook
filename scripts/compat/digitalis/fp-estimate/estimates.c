// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// FRECPE / FRSQRTE / URECPE / URSQRTE on a fixed set of inputs and FPCR settings, one line per case:
//   <op> <fpcr hex> <input hex> <result hex> <fpsr hex>
// Built for arm64 and run on the reference (qemu-aarch64, or an Arm CPU) and under the translator; check.cc
// computes the same lines from guest_fp_estimate_arm64.h. Every input runs ITER times in a loop, so the lite
// and heavy tiers translate it, not only the interpreter (BERBERIS_MODE selects the tier).
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint64_t rng = 0x9e3779b97f4a7c15ull;
static uint64_t next(void) { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; return rng; }

static uint64_t get_fpcr(void) { uint64_t v; __asm__ volatile("mrs %0, fpcr" : "=r"(v)); return v; }
static void set_fpcr(uint64_t v) { __asm__ volatile("msr fpcr, %0" : : "r"(v)); }
static uint64_t get_fpsr(void) { uint64_t v; __asm__ volatile("mrs %0, fpsr" : "=r"(v)); return v; }
static void set_fpsr(uint64_t v) { __asm__ volatile("msr fpsr, %0" : : "r"(v)); }

enum { RECPE_S, RECPE_D, RSQRTE_S, RSQRTE_D, RECPE_4S, RSQRTE_4S, RECPE_2D, RSQRTE_2D, URECPE_4S, URSQRTE_4S, RECPE_H,
       RSQRTE_H, NUM_OPS };
static const char* const kNames[NUM_OPS] = {"frecpe_s",  "frecpe_d",  "frsqrte_s", "frsqrte_d",
                                            "frecpe_4s", "frsqrte_4s", "frecpe_2d", "frsqrte_2d",
                                            "urecpe_4s", "ursqrte_4s", "frecpe_h",  "frsqrte_h"};

// One op on one input; vector forms put the input in every lane and check that the lanes agree.
static __attribute__((noinline)) uint64_t run(int op, uint64_t in) {
  uint64_t r = 0, lanes[2];
  __uint128_t v;
  switch (op) {
    case RECPE_S: { uint32_t x = (uint32_t)in, y; __asm__ volatile("fmov s0, %w1\n frecpe s0, s0\n fmov %w0, s0" : "=r"(y) : "r"(x) : "v0"); r = y; break; }
    case RSQRTE_S: { uint32_t x = (uint32_t)in, y; __asm__ volatile("fmov s0, %w1\n frsqrte s0, s0\n fmov %w0, s0" : "=r"(y) : "r"(x) : "v0"); r = y; break; }
    case RECPE_D: __asm__ volatile("fmov d0, %1\n frecpe d0, d0\n fmov %0, d0" : "=r"(r) : "r"(in) : "v0"); break;
    case RSQRTE_D: __asm__ volatile("fmov d0, %1\n frsqrte d0, d0\n fmov %0, d0" : "=r"(r) : "r"(in) : "v0"); break;
    case RECPE_H: { uint32_t x = (uint32_t)in & 0xffff, y; __asm__ volatile(".arch_extension fp16\n fmov h0, %w1\n frecpe h0, h0\n fmov %w0, h0" : "=r"(y) : "r"(x) : "v0"); r = y; break; }
    case RSQRTE_H: { uint32_t x = (uint32_t)in & 0xffff, y; __asm__ volatile(".arch_extension fp16\n fmov h0, %w1\n frsqrte h0, h0\n fmov %w0, h0" : "=r"(y) : "r"(x) : "v0"); r = y; break; }
    case RECPE_4S: case RSQRTE_4S: case URECPE_4S: case URSQRTE_4S: {
      uint32_t x = (uint32_t)in;
      if (op == RECPE_4S) __asm__ volatile("dup v0.4s, %w1\n frecpe v0.4s, v0.4s\n str q0, %0" : "=m"(v) : "r"(x) : "v0");
      else if (op == RSQRTE_4S) __asm__ volatile("dup v0.4s, %w1\n frsqrte v0.4s, v0.4s\n str q0, %0" : "=m"(v) : "r"(x) : "v0");
      else if (op == URECPE_4S) __asm__ volatile("dup v0.4s, %w1\n urecpe v0.4s, v0.4s\n str q0, %0" : "=m"(v) : "r"(x) : "v0");
      else __asm__ volatile("dup v0.4s, %w1\n ursqrte v0.4s, v0.4s\n str q0, %0" : "=m"(v) : "r"(x) : "v0");
      uint32_t w[4];
      memcpy(w, &v, 16);
      r = w[0];
      if (w[1] != w[0] || w[2] != w[0] || w[3] != w[0]) r |= 1ull << 63;  // lanes disagree
      break;
    }
    case RECPE_2D: case RSQRTE_2D:
      if (op == RECPE_2D) __asm__ volatile("dup v0.2d, %1\n frecpe v0.2d, v0.2d\n str q0, %0" : "=m"(v) : "r"(in) : "v0");
      else __asm__ volatile("dup v0.2d, %1\n frsqrte v0.2d, v0.2d\n str q0, %0" : "=m"(v) : "r"(in) : "v0");
      memcpy(lanes, &v, 16);
      r = lanes[0];
      if (lanes[1] != lanes[0]) r ^= 1;  // lanes disagree: flip a bit so the check fails
      break;
  }
  return r;
}

static int bits_of(int op) {
  switch (op) {
    case RECPE_D: case RSQRTE_D: case RECPE_2D: case RSQRTE_2D: return 64;
    case RECPE_H: case RSQRTE_H: return 16;
    default: return 32;
  }
}

// Inputs: every class (zeros, denormals at and around the overflow threshold, normals whose reciprocal is
// denormal, the largest normals, infinities, quiet and signalling NaNs, both signs) plus random values over the
// whole exponent range.
static int inputs(int bits, uint64_t* out, int max) {
  int n = 0;
  int ebits = bits == 16 ? 5 : bits == 32 ? 8 : 11, fbits = bits - 1 - ebits;
  uint64_t emax = (1ull << ebits) - 1, fmask = (1ull << fbits) - 1;
  uint64_t fr[] = {0, 1, fmask, 1ull << (fbits - 1), 1ull << (fbits - 2), (1ull << (fbits - 2)) - 1,
                   (1ull << (fbits - 2)) + 1, 3ull << (fbits - 2), 0x5555555555555555ull & fmask,
                   0x2aaaaaaaaaaaaaaaull & fmask};
  uint64_t ex[] = {0, 1, 2, emax / 2 - 1, emax / 2, emax / 2 + 1, emax - 3, emax - 2, emax - 1, emax};
  for (unsigned s = 0; s < 2; s++)
    for (unsigned e = 0; e < sizeof ex / sizeof *ex; e++)
      for (unsigned f = 0; f < sizeof fr / sizeof *fr; f++)
        if (n < max) out[n++] = ((uint64_t)s << (bits - 1)) | (ex[e] << fbits) | fr[f];
  while (n < max) {
    uint64_t x = next();
    if (bits < 64) x &= (1ull << bits) - 1;
    out[n++] = x;
  }
  return n;
}

int main(int argc, char** argv) {
  int nrand = argc > 1 ? atoi(argv[1]) : 2000, iter = argc > 2 ? atoi(argv[2]) : 50;
  int fp16 = argc > 3 ? atoi(argv[3]) : 1;
  // FPCR: 0, FZ, DN, FZ|DN, RP, RM, RZ, FZ16
  const uint64_t fpcrs[] = {0, 1u << 24, 1u << 25, 3u << 24, 1u << 22, 2u << 22, 3u << 22, 1u << 19};
  static uint64_t in[4096];
  uint64_t saved = get_fpcr();
  for (int op = 0; op < NUM_OPS; op++) {
    if (!fp16 && bits_of(op) == 16) continue;
    int n = inputs(bits_of(op), in, 200 + nrand < 4096 ? 200 + nrand : 4096);
    for (unsigned c = 0; c < sizeof fpcrs / sizeof *fpcrs; c++) {
      if (bits_of(op) != 16 && fpcrs[c] == (1u << 19)) continue;
      set_fpcr(fpcrs[c]);
      for (int i = 0; i < n; i++) {
        uint64_t r = 0, fpsr = 0;
        for (int k = 0; k < iter; k++) {
          set_fpsr(0);
          r = run(op, in[i]);
          fpsr = get_fpsr();
        }
        printf("%s %llx %llx %llx %llx\n", kNames[op], (unsigned long long)fpcrs[c], (unsigned long long)in[i],
               (unsigned long long)r, (unsigned long long)fpsr);
      }
    }
  }
  set_fpcr(saved);
  return 0;
}
