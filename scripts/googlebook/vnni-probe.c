// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
// Execute the exact harmless VPDPWSSD encoding seen at Ruby's libz fault.
// Distinguish AVX-VNNI from AVX512-VNNI; catch SIGILL without a core dump.
#include <cpuid.h>
#include <setjmp.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>

static sigjmp_buf resume;
static void illegal(int signal_number) {
    (void)signal_number;
    siglongjmp(resume, 1);
}

int main(void) {
    unsigned a = 0, b = 0, c = 0, d = 0;
    volatile int advertised = __get_cpuid_count(7, 1, &a, &b, &c, &d) && (a & (1u << 4));
    struct sigaction action;
    memset(&action, 0, sizeof action);
    action.sa_handler = illegal;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGILL, &action, NULL) != 0) return 2;
    volatile int trapped = 0;
    if (sigsetjmp(resume, 1) == 0) {
        __asm__ volatile("vpxor %%xmm2, %%xmm2, %%xmm2\n\t"
                         "vpxor %%xmm9, %%xmm9, %%xmm9\n\t"
                         "vpxor %%xmm6, %%xmm6, %%xmm6\n\t"
                         ".byte 0xc4, 0xe2, 0x31, 0x52, 0xf2"
                         : : : "xmm2", "xmm9", "xmm6");
    } else {
        trapped = 1;
    }
    printf("{\"cpuid_avx_vnni\":%s,\"vpdpwssd_sigill\":%s,\"encoding\":\"c4e23152f2\"}\n",
           advertised ? "true" : "false", trapped ? "true" : "false");
    return 0;  // An observation, not a full CPU/platform compatibility result.
}
