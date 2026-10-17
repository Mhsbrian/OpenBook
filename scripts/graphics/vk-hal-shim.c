// SPDX-License-Identifier: Apache-2.0
// libvk_hal_shim.so: a stand-in for Android's Vulkan loader in ANAL-177's off-device pre-check
// (scripts/graphics/pre-check.sh). Off the device there is no property service, so Android's libvulkan finds no
// driver (ro.hardware.vulkan is unset), and RADV's Android build exports only its HAL module (HMI), not
// vkGetInstanceProcAddr. This library opens the HAL as libvulkan does and exports vkGetInstanceProcAddr, which is all
// dEQP's --deqp-vk-library-path needs: dEQP reaches every other entry point through it. The loader-only global
// queries (layers) answer "none". On the G14 the graphics check uses Android's real loader instead.
//   OPENBOOK_VK_HAL  the HAL to open (default /vendor/lib64/hw/vulkan.radv.so)
// Build (NDK): clang -shared -fPIC -O2 -I<frameworks/native/vulkan/include> -o libvk_hal_shim.so vk-hal-shim.c -ldl
#include <dlfcn.h>
#include <hardware/hwvulkan.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static hwvulkan_device_t *hal;
static pthread_once_t once = PTHREAD_ONCE_INIT;

static void init(void) {
    const char *path = getenv("OPENBOOK_VK_HAL");
    if (!path || !*path) path = "/vendor/lib64/hw/vulkan.radv.so";
    void *h = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    hwvulkan_module_t *m = h ? (hwvulkan_module_t *)dlsym(h, HAL_MODULE_INFO_SYM_AS_STR) : NULL;
    if (!m || m->common.methods->open(&m->common, HWVULKAN_DEVICE_0, (hw_device_t **)&hal)) {
        fprintf(stderr, "vk-hal-shim: cannot open the Vulkan HAL %s: %s\n", path, h ? "open failed" : dlerror());
        hal = NULL;
    }
}

static VKAPI_ATTR VkResult VKAPI_CALL no_layers(uint32_t *count, VkLayerProperties *props) {
    (void)props;
    *count = 0;
    return VK_SUCCESS;
}

static VKAPI_ATTR VkResult VKAPI_CALL no_device_layers(VkPhysicalDevice pd, uint32_t *count, VkLayerProperties *props) {
    (void)pd;
    (void)props;
    *count = 0;
    return VK_SUCCESS;
}

__attribute__((visibility("default"))) VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
vkGetInstanceProcAddr(VkInstance instance, const char *name) {
    pthread_once(&once, init);
    if (!hal) return NULL;
    if (!strcmp(name, "vkGetInstanceProcAddr")) return (PFN_vkVoidFunction)vkGetInstanceProcAddr;
    if (!strcmp(name, "vkEnumerateInstanceLayerProperties")) return (PFN_vkVoidFunction)no_layers;
    if (!strcmp(name, "vkEnumerateDeviceLayerProperties")) return (PFN_vkVoidFunction)no_device_layers;
    if (!instance) {
        if (!strcmp(name, "vkCreateInstance")) return (PFN_vkVoidFunction)hal->CreateInstance;
        if (!strcmp(name, "vkEnumerateInstanceExtensionProperties"))
            return (PFN_vkVoidFunction)hal->EnumerateInstanceExtensionProperties;
    }
    return hal->GetInstanceProcAddr(instance, name);
}
