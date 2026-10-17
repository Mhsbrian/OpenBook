// SPDX-License-Identifier: Apache-2.0
// QEMU test only (scripts/audio-net-qemu.sh): preloaded into AOSP's hostapd when it runs from a root shell as the
// test access point. hostapd registers its AIDL service before its event loop, and from a shell (not init) that
// registration retries forever, so the access point never answers an authentication. The access point needs no
// AIDL: report success without registering anything.
#include <stdint.h>

typedef struct AIBinder AIBinder;

int32_t AServiceManager_addService(AIBinder *binder, const char *instance) {
    (void)binder;
    (void)instance;
    return 0;  // STATUS_OK
}
