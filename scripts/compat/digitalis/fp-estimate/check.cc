// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Reads estimates.c's output and checks every line against guest_fp_estimate_arm64.h (the translator's
// implementation of the Arm pseudocode). Prints a summary per op and the first mismatches; exits 1 on any.
//   check [--quiet] < estimates.txt
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>

#include "berberis/guest_state/guest_fp_estimate_arm64.h"

using namespace berberis::arm64;

static bool Expect(const std::string& op, uint32_t fpcr, uint64_t in, uint64_t* r, uint32_t* fpsr) {
  *fpsr = 0;
  if (op == "frecpe_s" || op == "frecpe_4s") *r = FpRecipEstimate<32>(in, fpcr, fpsr);
  else if (op == "frsqrte_s" || op == "frsqrte_4s") *r = FpRSqrtEstimate<32>(in, fpcr, fpsr);
  else if (op == "frecpe_d" || op == "frecpe_2d") *r = FpRecipEstimate<64>(in, fpcr, fpsr);
  else if (op == "frsqrte_d" || op == "frsqrte_2d") *r = FpRSqrtEstimate<64>(in, fpcr, fpsr);
  else if (op == "frecpe_h") *r = FpRecipEstimate<16>(in, fpcr, fpsr);
  else if (op == "frsqrte_h") *r = FpRSqrtEstimate<16>(in, fpcr, fpsr);
  else if (op == "urecpe_4s") *r = UnsignedRecipEstimate(static_cast<uint32_t>(in));
  else if (op == "ursqrte_4s") *r = UnsignedRSqrtEstimate(static_cast<uint32_t>(in));
  else return false;
  return true;
}

int main(int argc, char** argv) {
  bool quiet = argc > 1 && !strcmp(argv[1], "--quiet");
  char opbuf[32];
  unsigned long long fpcr, in, got, got_fpsr;
  std::map<std::string, std::pair<int, int>> stats;  // op -> (lines, mismatches)
  int shown = 0, bad = 0, lines = 0;
  while (scanf("%31s %llx %llx %llx %llx", opbuf, &fpcr, &in, &got, &got_fpsr) == 5) {
    std::string op = opbuf;
    uint64_t want;
    uint32_t want_fpsr;
    if (!Expect(op, static_cast<uint32_t>(fpcr), in, &want, &want_fpsr)) {
      fprintf(stderr, "unknown op %s\n", opbuf);
      return 2;
    }
    lines++;
    auto& s = stats[op];
    s.first++;
    if (want != got || want_fpsr != got_fpsr) {
      s.second++;
      bad++;
      if (!quiet && shown++ < 40) {
        printf("MISMATCH %s fpcr=%llx in=%llx got=%llx/fpsr %llx want=%llx/fpsr %x\n", opbuf, fpcr, in, got,
               got_fpsr, (unsigned long long)want, want_fpsr);
      }
    }
  }
  for (auto& [op, s] : stats) printf("%-11s %6d cases %6d mismatches\n", op.c_str(), s.first, s.second);
  printf("total %d cases, %d mismatches\n", lines, bad);
  return (bad || !lines) ? 1 : 0;
}
