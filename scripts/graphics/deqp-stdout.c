// SPDX-License-Identifier: Apache-2.0
// libdeqp_stdout.so (ANAL-177): LD_PRELOAD for AOSP's deqp-binary64. On Android dEQP prints its console output
// ("Test case '...'..", "  Pass (...)") to logcat with the tag "dEQP" (framework/qphelper/qpDebugOut.c), where Mesa's
// deqp-runner cannot see it; deqp-runner reads it from stdout, as dEQP prints it on Linux. This sends that tag to
// stdout (fatal messages to stderr, as on Linux), line-buffered so a crash loses nothing, and passes every other
// tag on to liblog. The dEQP binary itself is unchanged.
// Build (NDK): clang -shared -fPIC -O2 -o libdeqp_stdout.so deqp-stdout.c -ldl
#define _GNU_SOURCE
#include <android/log.h>
#include <dlfcn.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

__attribute__((constructor)) static void line_buffered(void) { setvbuf(stdout, NULL, _IOLBF, 0); }

static int is_deqp(const char *tag) { return tag && !strcmp(tag, "dEQP"); }

__attribute__((visibility("default"))) int __android_log_write(int prio, const char *tag, const char *text) {
    if (is_deqp(tag)) {
        FILE *out = prio >= ANDROID_LOG_ERROR ? stderr : stdout;
        if (prio == ANDROID_LOG_FATAL) fputs("FATAL ERROR: ", out);
        fputs(text ? text : "", out);
        if (prio == ANDROID_LOG_FATAL) { fputc('\n', out); fflush(out); }
        return 1;
    }
    static int (*real)(int, const char *, const char *);
    if (!real) real = (int (*)(int, const char *, const char *))dlsym(RTLD_NEXT, "__android_log_write");
    return real ? real(prio, tag, text) : 0;
}

__attribute__((visibility("default"))) int __android_log_vprint(int prio, const char *tag, const char *fmt, va_list ap) {
    if (is_deqp(tag)) {
        FILE *out = prio >= ANDROID_LOG_ERROR ? stderr : stdout;
        if (prio == ANDROID_LOG_FATAL) fputs("FATAL ERROR: ", out);
        int n = vfprintf(out, fmt, ap);
        if (prio == ANDROID_LOG_FATAL) { fputc('\n', out); fflush(out); }
        return n;
    }
    static int (*real)(int, const char *, const char *, va_list);
    if (!real) real = (int (*)(int, const char *, const char *, va_list))dlsym(RTLD_NEXT, "__android_log_vprint");
    return real ? real(prio, tag, fmt, ap) : 0;
}

__attribute__((visibility("default"))) int __android_log_print(int prio, const char *tag, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int n = __android_log_vprint(prio, tag, fmt, ap);
    va_end(ap);
    return n;
}
