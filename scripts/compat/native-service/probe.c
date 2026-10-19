// SPDX-License-Identifier: Apache-2.0
#include <jni.h>
JNIEXPORT jint JNICALL Java_dev_openbook_nativefallback_ManagedService_answer(
        JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;
    volatile int value = 6;
    return value * 7;
}
