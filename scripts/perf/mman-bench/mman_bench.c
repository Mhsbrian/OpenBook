// SPDX-License-Identifier: Apache-2.0
// mman-bench: the address-space pattern of a JIT engine's heap (ANAL-379), timed.
//
// Each iteration reserves a large never-executable range (mmap PROT_NONE, MAP_NORESERVE), commits and
// decommits pages inside it (mprotect read-write, then back to PROT_NONE), and releases it (munmap). V8 and
// SpiderMonkey reserve gigabytes this way. Under a translator every one of these calls also updates the
// translator's view of which guest pages are executable, so this measures that bookkeeping; natively it
// measures the kernel alone.
//
// usage: mman-bench [iterations=200] [reserve_mib=4096] [commits=32]
// Prints one JSON line: ns per iteration (median of 5 batches), per call, and the parameters.
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>

static uint64_t now_ns(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint64_t)ts.tv_sec * 1000000000u + (uint64_t)ts.tv_nsec;
}

static int cmp_u64(const void* a, const void* b) {
  uint64_t x = *(const uint64_t*)a, y = *(const uint64_t*)b;
  return x < y ? -1 : x > y;
}

int main(int argc, char** argv) {
  long iterations = argc > 1 ? atol(argv[1]) : 200;
  size_t reserve = (size_t)(argc > 2 ? atol(argv[2]) : 4096) << 20;
  long commits = argc > 3 ? atol(argv[3]) : 32;
  const size_t chunk = 256 << 10;
  if (iterations < 1 || reserve < chunk * (size_t)commits || commits < 0) {
    fprintf(stderr, "usage: mman-bench [iterations] [reserve_mib] [commits]\n");
    return 2;
  }
  enum { kBatches = 5 };
  uint64_t batch_ns[kBatches];
  for (int b = 0; b < kBatches; b++) {
    uint64_t t0 = now_ns();
    for (long i = 0; i < iterations; i++) {
      char* p = mmap(NULL, reserve, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
      if (p == MAP_FAILED) {
        perror("mmap");
        return 1;
      }
      for (long c = 0; c < commits; c++) {
        char* q = p + (size_t)c * chunk;
        if (mprotect(q, chunk, PROT_READ | PROT_WRITE) != 0) {
          perror("mprotect");
          return 1;
        }
        q[0] = (char)c;  // touch one page
        if (mprotect(q, chunk, PROT_NONE) != 0) {
          perror("mprotect");
          return 1;
        }
      }
      if (munmap(p, reserve) != 0) {
        perror("munmap");
        return 1;
      }
    }
    batch_ns[b] = now_ns() - t0;
  }
  qsort(batch_ns, kBatches, sizeof(batch_ns[0]), cmp_u64);
  double per_iter = (double)batch_ns[kBatches / 2] / (double)iterations;
  long calls = 2 + 2 * commits;
  printf("{\"tool\":\"mman-bench\",\"version\":1,\"iterations\":%ld,\"reserve_mib\":%zu,\"commits\":%ld,"
         "\"ns_per_iteration_median\":%.0f,\"ns_per_call\":%.1f,\"batches_ns\":[%llu,%llu,%llu,%llu,%llu]}\n",
         iterations, reserve >> 20, commits, per_iter, per_iter / (double)calls,
         (unsigned long long)batch_ns[0], (unsigned long long)batch_ns[1], (unsigned long long)batch_ns[2],
         (unsigned long long)batch_ns[3], (unsigned long long)batch_ns[4]);
  return 0;
}
