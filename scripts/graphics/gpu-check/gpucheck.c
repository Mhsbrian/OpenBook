// SPDX-License-Identifier: Apache-2.0
// GPU Check (ANAL-247): a small Android app that reports which graphics driver its own process loaded and how fast
// it presents, so a per-app driver choice can be checked without a game. Pure NDK (NativeActivity, no Java).
//
//   am start -n org.openbook.gpucheck/android.app.NativeActivity [--es mode info|gl|vk|all] [--ei seconds N]
//
// Every result is one logcat line, tag "gpucheck", "GPUCHECK key=value ...":
//   maps       the driver libraries mapped into this process (an updatable driver shows its APK's path)
//   vk.*       Vulkan instance and each physical device: name, IDs, driver ID/name/info, API version
//   egl.*      EGL and GLES strings from a 1x1 pbuffer context
//   gl.*       (mode gl/all) frames presented to the activity's window with swap interval 0: a light phase
//              (one clear per frame, present-bound) and a heavy phase (a full-window ALU-bound fragment shader),
//              each N seconds (default 5), as frames per second
//   vk.*       (mode vk) Vulkan straight to the window: the driver's own messages (debug utils), every failing call
//              with its VkResult, and the frames presented per second (FIFO)
//   done       the end; the activity then finishes itself
// Launched from the launcher (no extra), it runs "all".
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <android/input.h>
#include <android/log.h>
#include <android/looper.h>
#include <android/native_activity.h>
#include <jni.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#define VK_USE_PLATFORM_ANDROID_KHR
#include <vulkan/vulkan.h>

#define LOG(...) __android_log_print(ANDROID_LOG_INFO, "gpucheck", "GPUCHECK " __VA_ARGS__)

static ANativeActivity *g_activity;
static ANativeWindow *g_window;
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t g_cond = PTHREAD_COND_INITIALIZER;
static char g_mode[16] = "all";
static int g_seconds = 5;
static int g_stop;

static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

// The driver libraries in this process: Vulkan HALs, EGL/GLES drivers and anything from a driver package.
static void log_maps(void) {
    FILE *f = fopen("/proc/self/maps", "r");
    if (!f) return;
    char line[1024], seen[16][256];
    int n = 0;
    while (fgets(line, sizeof line, f) && n < 16) {
        char *path = strchr(line, '/');
        if (!path) continue;
        path[strcspn(path, "\n")] = 0;
        if (!strstr(path, "vulkan.") && !strstr(path, "_angle") && !strstr(path, "libEGL_") &&
            !strstr(path, "libGLES") && !strstr(path, ".apk")) continue;
        // A driver package's APK: the image's copy (OpenBookNvk.apk) or an update (/data/app/.../org.openbook.nvk-...).
        if (strstr(path, ".apk") && !strstr(path, "OpenBookNvk") && !strstr(path, "org.openbook.nvk")) continue;
        int dup = 0;
        for (int i = 0; i < n; i++) dup |= !strcmp(seen[i], path);
        if (dup) continue;
        snprintf(seen[n++], sizeof seen[0], "%s", path);
        LOG("maps %s", path);
    }
    fclose(f);
}

static void vk_info(void) {
    VkApplicationInfo app = {VK_STRUCTURE_TYPE_APPLICATION_INFO, .pApplicationName = "gpucheck",
                             .apiVersion = VK_API_VERSION_1_1};
    VkInstanceCreateInfo ci = {VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app};
    VkInstance inst;
    VkResult r = vkCreateInstance(&ci, NULL, &inst);
    LOG("vk.instance result=%d", r);
    if (r != VK_SUCCESS) return;
    uint32_t count = 0;
    r = vkEnumeratePhysicalDevices(inst, &count, NULL);
    LOG("vk.devices result=%d count=%u", r, count);
    VkPhysicalDevice devs[8];
    if (count > 8) count = 8;
    if (count) vkEnumeratePhysicalDevices(inst, &count, devs);
    for (uint32_t i = 0; i < count; i++) {
        VkPhysicalDeviceDriverProperties drv = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
        VkPhysicalDeviceProperties2 p2 = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, .pNext = &drv};
        vkGetPhysicalDeviceProperties2(devs[i], &p2);
        VkPhysicalDeviceProperties *p = &p2.properties;
        LOG("vk.device index=%u name=\"%s\" vendor=0x%04x device=0x%04x type=%d api=%u.%u.%u driver_id=%d "
            "driver_name=\"%s\" driver_info=\"%s\"", i, p->deviceName, p->vendorID, p->deviceID, p->deviceType,
            VK_API_VERSION_MAJOR(p->apiVersion), VK_API_VERSION_MINOR(p->apiVersion),
            VK_API_VERSION_PATCH(p->apiVersion), drv.driverID, drv.driverName, drv.driverInfo);
    }
    vkDestroyInstance(inst, NULL);
}

static EGLDisplay egl_display(void) {
    EGLDisplay d = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    EGLint major = 0, minor = 0;
    if (!eglInitialize(d, &major, &minor)) {
        LOG("egl.initialize ok=0 error=0x%x", eglGetError());
        return EGL_NO_DISPLAY;
    }
    return d;
}

static EGLConfig egl_config(EGLDisplay d, EGLint surface) {
    const EGLint attrs[] = {EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_SURFACE_TYPE, surface, EGL_RED_SIZE, 8,
                            EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
    EGLConfig c = NULL;
    EGLint n = 0;
    if (!eglChooseConfig(d, attrs, &c, 1, &n) || n < 1) return NULL;
    return c;
}

static void egl_info(void) {
    EGLDisplay d = egl_display();
    if (d == EGL_NO_DISPLAY) return;
    LOG("egl.display vendor=\"%s\" version=\"%s\"", eglQueryString(d, EGL_VENDOR), eglQueryString(d, EGL_VERSION));
    EGLConfig c = egl_config(d, EGL_PBUFFER_BIT);
    const EGLint pb[] = {EGL_WIDTH, 1, EGL_HEIGHT, 1, EGL_NONE}, ca[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
    EGLSurface s = c ? eglCreatePbufferSurface(d, c, pb) : EGL_NO_SURFACE;
    EGLContext x = c ? eglCreateContext(d, c, EGL_NO_CONTEXT, ca) : EGL_NO_CONTEXT;
    if (s == EGL_NO_SURFACE || x == EGL_NO_CONTEXT || !eglMakeCurrent(d, s, s, x)) {
        LOG("egl.context ok=0 error=0x%x", eglGetError());
    } else {
        LOG("egl.gles vendor=\"%s\" renderer=\"%s\" version=\"%s\"", glGetString(GL_VENDOR),
            glGetString(GL_RENDERER), glGetString(GL_VERSION));
        eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    }
    if (x != EGL_NO_CONTEXT) eglDestroyContext(d, x);
    if (s != EGL_NO_SURFACE) eglDestroySurface(d, s);
    eglTerminate(d);
}

static const char *VS =
    "#version 300 es\n"
    "void main() { vec2 p = vec2(gl_VertexID == 1 ? 3.0 : -1.0, gl_VertexID == 2 ? 3.0 : -1.0);"
    " gl_Position = vec4(p, 0.0, 1.0); }\n";
// About 6 FP32 operations per iteration and pixel; 256 iterations at 1920x1200 is ~3.5 GFLOP a frame.
static const char *FS =
    "#version 300 es\nprecision highp float;\nuniform float t;\nuniform int iters;\nout vec4 o;\n"
    "void main() { float a = gl_FragCoord.x * 0.001 + t, b = gl_FragCoord.y * 0.001;\n"
    " for (int i = 0; i < iters; i++) { a = fract(a * 1.0001 + b * 0.37); b = fract(b * 0.9999 + a * 0.61); }\n"
    " o = vec4(a, b, fract(t), 1.0); }\n";

static GLuint shader(GLenum kind, const char *src) {
    GLuint s = glCreateShader(kind);
    glShaderSource(s, 1, &src, NULL);
    glCompileShader(s);
    GLint ok = 0;
    glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char msg[512];
        glGetShaderInfoLog(s, sizeof msg, NULL, msg);
        LOG("gl.shader ok=0 log=\"%s\"", msg);
    }
    return s;
}

// Frames presented in `seconds`; heavy draws the ALU-bound shader over the window, light only clears.
static double gl_phase(EGLDisplay d, EGLSurface s, GLuint prog, int heavy, int seconds) {
    GLint ut = glGetUniformLocation(prog, "t"), ui = glGetUniformLocation(prog, "iters");
    int frames = 0;
    double start = now(), t;
    while ((t = now() - start) < seconds && !g_stop) {
        glClearColor((frames & 255) / 255.0f, 0.2f, 0.4f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        if (heavy) {
            glUniform1f(ut, (float)t);
            glUniform1i(ui, 256);
            glDrawArrays(GL_TRIANGLES, 0, 3);
        }
        if (!eglSwapBuffers(d, s)) {
            LOG("gl.swap ok=0 error=0x%x", eglGetError());
            break;
        }
        frames++;
    }
    return frames / (now() - start);
}

// The activity's window, acquired (NULL after 10 s without one).
static ANativeWindow *wait_window(void) {
    pthread_mutex_lock(&g_lock);
    for (int i = 0; i < 100 && !g_window && !g_stop; i++) {
        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        ts.tv_nsec += 100000000;
        if (ts.tv_nsec >= 1000000000) { ts.tv_sec++; ts.tv_nsec -= 1000000000; }
        pthread_cond_timedwait(&g_cond, &g_lock, &ts);
    }
    ANativeWindow *w = g_window;
    if (w) ANativeWindow_acquire(w);
    pthread_mutex_unlock(&g_lock);
    return w;
}

static void gl_present(void) {
    ANativeWindow *w = wait_window();
    if (!w) { LOG("gl.window ok=0"); return; }
    EGLDisplay d = egl_display();
    EGLConfig c = d != EGL_NO_DISPLAY ? egl_config(d, EGL_WINDOW_BIT) : NULL;
    const EGLint ca[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
    EGLSurface s = c ? eglCreateWindowSurface(d, c, w, NULL) : EGL_NO_SURFACE;
    EGLContext x = c ? eglCreateContext(d, c, EGL_NO_CONTEXT, ca) : EGL_NO_CONTEXT;
    if (s == EGL_NO_SURFACE || x == EGL_NO_CONTEXT || !eglMakeCurrent(d, s, s, x)) {
        LOG("gl.context ok=0 error=0x%x", eglGetError());
    } else {
        EGLint width = 0, height = 0;
        eglQuerySurface(d, s, EGL_WIDTH, &width);
        eglQuerySurface(d, s, EGL_HEIGHT, &height);
        eglSwapInterval(d, 0);
        GLuint prog = glCreateProgram();
        glAttachShader(prog, shader(GL_VERTEX_SHADER, VS));
        glAttachShader(prog, shader(GL_FRAGMENT_SHADER, FS));
        glLinkProgram(prog);
        glUseProgram(prog);
        glViewport(0, 0, width, height);
        LOG("gl.window width=%d height=%d renderer=\"%s\"", width, height, glGetString(GL_RENDERER));
        gl_phase(d, s, prog, 0, 1);   // warm-up
        double light = gl_phase(d, s, prog, 0, g_seconds);
        double heavy = gl_phase(d, s, prog, 1, g_seconds);
        LOG("gl.fps light=%.1f heavy=%.1f seconds=%d width=%d height=%d", light, heavy, g_seconds, width, height);
        eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    }
    if (x != EGL_NO_CONTEXT) eglDestroyContext(d, x);
    if (s != EGL_NO_SURFACE) eglDestroySurface(d, s);
    if (d != EGL_NO_DISPLAY) eglTerminate(d);
    ANativeWindow_release(w);
}

// Mode vk: Vulkan straight to the window through Android's swapchain, with a VK_EXT_debug_utils messenger so the
// driver's own error messages (Mesa's vk_errorf) reach logcat as vk.msg lines. Each frame clears the image to a new
// colour and presents it (FIFO: at most the panel's rate). Every failing call is logged with its VkResult.
static int g_vk_errors;

static VKAPI_ATTR VkBool32 VKAPI_CALL vk_message(VkDebugUtilsMessageSeverityFlagBitsEXT sev,
                                                 VkDebugUtilsMessageTypeFlagsEXT type,
                                                 const VkDebugUtilsMessengerCallbackDataEXT *data, void *user) {
    (void)type; (void)user;
    if (g_vk_errors++ < 40) LOG("vk.msg severity=0x%x %s", sev, data && data->pMessage ? data->pMessage : "");
    return VK_FALSE;
}

#define VKFAIL(call) do { VkResult r_ = (call); if (r_ != VK_SUCCESS) { \
    LOG("vk.fail call=\"%s\" result=%d", #call, r_); goto out; } } while (0)

static void vk_present(void) {
    ANativeWindow *w = wait_window();
    if (!w) { LOG("vk.window ok=0"); return; }
    VkInstance inst = VK_NULL_HANDLE;
    VkDebugUtilsMessengerEXT msgr = VK_NULL_HANDLE;
    VkSurfaceKHR surf = VK_NULL_HANDLE;
    VkDevice dev = VK_NULL_HANDLE;
    VkSwapchainKHR sc = VK_NULL_HANDLE;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkSemaphore acquired[3] = {0}, rendered[3] = {0};
    VkFence fences[3] = {0};
    VkCommandBuffer cmds[3] = {0};
    PFN_vkDestroyDebugUtilsMessengerEXT destroy_msgr = NULL;
    uint32_t n = 0, frames = 0;

    uint32_t next = 0;
    vkEnumerateInstanceExtensionProperties(NULL, &next, NULL);
    VkExtensionProperties exts[128];
    if (next > 128) next = 128;
    vkEnumerateInstanceExtensionProperties(NULL, &next, exts);
    int has_debug = 0;
    for (uint32_t i = 0; i < next; i++) has_debug |= !strcmp(exts[i].extensionName, VK_EXT_DEBUG_UTILS_EXTENSION_NAME);
    const char *iext[3] = {VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_ANDROID_SURFACE_EXTENSION_NAME,
                           VK_EXT_DEBUG_UTILS_EXTENSION_NAME};
    VkApplicationInfo app = {VK_STRUCTURE_TYPE_APPLICATION_INFO, .pApplicationName = "gpucheck",
                             .apiVersion = VK_API_VERSION_1_1};
    VkInstanceCreateInfo ici = {VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app,
                                .enabledExtensionCount = has_debug ? 3 : 2, .ppEnabledExtensionNames = iext};
    VKFAIL(vkCreateInstance(&ici, NULL, &inst));
    LOG("vk.debug_utils available=%d", has_debug);
    if (has_debug) {
        PFN_vkCreateDebugUtilsMessengerEXT create_msgr =
            (PFN_vkCreateDebugUtilsMessengerEXT)vkGetInstanceProcAddr(inst, "vkCreateDebugUtilsMessengerEXT");
        destroy_msgr = (PFN_vkDestroyDebugUtilsMessengerEXT)vkGetInstanceProcAddr(inst, "vkDestroyDebugUtilsMessengerEXT");
        VkDebugUtilsMessengerCreateInfoEXT mci = {VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT,
            .messageSeverity = VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT | VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT |
                               VK_DEBUG_UTILS_MESSAGE_SEVERITY_INFO_BIT_EXT,
            .messageType = VK_DEBUG_UTILS_MESSAGE_TYPE_GENERAL_BIT_EXT | VK_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT |
                           VK_DEBUG_UTILS_MESSAGE_TYPE_PERFORMANCE_BIT_EXT,
            .pfnUserCallback = vk_message};
        if (create_msgr) VKFAIL(create_msgr(inst, &mci, NULL, &msgr));
    }
    VkAndroidSurfaceCreateInfoKHR sci = {VK_STRUCTURE_TYPE_ANDROID_SURFACE_CREATE_INFO_KHR, .window = w};
    VKFAIL(vkCreateAndroidSurfaceKHR(inst, &sci, NULL, &surf));
    uint32_t count = 1;
    VkPhysicalDevice pd;
    VkResult er = vkEnumeratePhysicalDevices(inst, &count, &pd);
    if ((er != VK_SUCCESS && er != VK_INCOMPLETE) || count == 0) { LOG("vk.fail call=\"enumerate\" result=%d", er); goto out; }
    VkPhysicalDeviceProperties props;
    vkGetPhysicalDeviceProperties(pd, &props);
    uint32_t qf = 0, nq = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(pd, &nq, NULL);
    for (qf = 0; qf < nq; qf++) {
        VkBool32 ok = VK_FALSE;
        vkGetPhysicalDeviceSurfaceSupportKHR(pd, qf, surf, &ok);
        if (ok) break;
    }
    if (qf == nq) { LOG("vk.fail call=\"no queue family presents\" result=0"); goto out; }
    float prio = 1.0f;
    VkDeviceQueueCreateInfo qci = {VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO, .queueFamilyIndex = qf,
                                   .queueCount = 1, .pQueuePriorities = &prio};
    const char *dext[1] = {VK_KHR_SWAPCHAIN_EXTENSION_NAME};
    VkDeviceCreateInfo dci = {VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, .queueCreateInfoCount = 1, .pQueueCreateInfos = &qci,
                              .enabledExtensionCount = 1, .ppEnabledExtensionNames = dext};
    VKFAIL(vkCreateDevice(pd, &dci, NULL, &dev));
    VkQueue q;
    vkGetDeviceQueue(dev, qf, 0, &q);
    VkSurfaceCapabilitiesKHR caps;
    VKFAIL(vkGetPhysicalDeviceSurfaceCapabilitiesKHR(pd, surf, &caps));
    uint32_t nf = 1;
    VkSurfaceFormatKHR fmt;
    er = vkGetPhysicalDeviceSurfaceFormatsKHR(pd, surf, &nf, &fmt);
    if (er != VK_SUCCESS && er != VK_INCOMPLETE) { LOG("vk.fail call=\"surface formats\" result=%d", er); goto out; }
    LOG("vk.surface device=\"%s\" extent=%ux%u images=%u-%u format=%d usage=0x%x", props.deviceName,
        caps.currentExtent.width, caps.currentExtent.height, caps.minImageCount, caps.maxImageCount, fmt.format,
        caps.supportedUsageFlags);
    uint32_t want = caps.minImageCount + 1;
    if (caps.maxImageCount && want > caps.maxImageCount) want = caps.maxImageCount;
    VkSwapchainCreateInfoKHR swci = {VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR, .surface = surf, .minImageCount = want,
        .imageFormat = fmt.format, .imageColorSpace = fmt.colorSpace, .imageExtent = caps.currentExtent,
        .imageArrayLayers = 1, .imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT,
        .imageSharingMode = VK_SHARING_MODE_EXCLUSIVE, .preTransform = caps.currentTransform,
        .compositeAlpha = VK_COMPOSITE_ALPHA_INHERIT_BIT_KHR, .presentMode = VK_PRESENT_MODE_FIFO_KHR, .clipped = VK_TRUE};
    if (!(caps.supportedCompositeAlpha & VK_COMPOSITE_ALPHA_INHERIT_BIT_KHR))
        swci.compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
    VKFAIL(vkCreateSwapchainKHR(dev, &swci, NULL, &sc));
    VkImage images[8];
    n = 8;
    VKFAIL(vkGetSwapchainImagesKHR(dev, sc, &n, images));
    VkCommandPoolCreateInfo pci = {VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
                                   .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT, .queueFamilyIndex = qf};
    VKFAIL(vkCreateCommandPool(dev, &pci, NULL, &pool));
    VkCommandBufferAllocateInfo cai = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .commandPool = pool,
                                       .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 3};
    VKFAIL(vkAllocateCommandBuffers(dev, &cai, cmds));
    for (int i = 0; i < 3; i++) {
        VkSemaphoreCreateInfo semi = {VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};
        VkFenceCreateInfo fi = {VK_STRUCTURE_TYPE_FENCE_CREATE_INFO, .flags = VK_FENCE_CREATE_SIGNALED_BIT};
        VKFAIL(vkCreateSemaphore(dev, &semi, NULL, &acquired[i]));
        VKFAIL(vkCreateSemaphore(dev, &semi, NULL, &rendered[i]));
        VKFAIL(vkCreateFence(dev, &fi, NULL, &fences[i]));
    }
    LOG("vk.swapchain images=%u", n);
    double start = now();
    while (now() - start < g_seconds && !g_stop) {
        uint32_t f = frames % 3, idx = 0;
        VKFAIL(vkWaitForFences(dev, 1, &fences[f], VK_TRUE, 2000000000ull));
        VKFAIL(vkAcquireNextImageKHR(dev, sc, 2000000000ull, acquired[f], VK_NULL_HANDLE, &idx));
        VKFAIL(vkResetFences(dev, 1, &fences[f]));
        VkCommandBufferBeginInfo bi = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
                                       .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
        VKFAIL(vkBeginCommandBuffer(cmds[f], &bi));
        VkImageSubresourceRange range = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        VkImageMemoryBarrier b = {VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER, .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
            .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED, .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .image = images[idx], .subresourceRange = range};
        vkCmdPipelineBarrier(cmds[f], VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0,
                             NULL, 1, &b);
        VkClearColorValue c = {.float32 = {(frames & 255) / 255.0f, 0.3f, 0.6f, 1.0f}};
        vkCmdClearColorImage(cmds[f], images[idx], VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, &c, 1, &range);
        b.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        b.dstAccessMask = 0;
        b.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        b.newLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
        vkCmdPipelineBarrier(cmds[f], VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, 0, 0, NULL,
                             0, NULL, 1, &b);
        VKFAIL(vkEndCommandBuffer(cmds[f]));
        VkPipelineStageFlags stage = VK_PIPELINE_STAGE_TRANSFER_BIT;
        VkSubmitInfo si = {VK_STRUCTURE_TYPE_SUBMIT_INFO, .waitSemaphoreCount = 1, .pWaitSemaphores = &acquired[f],
                           .pWaitDstStageMask = &stage, .commandBufferCount = 1, .pCommandBuffers = &cmds[f],
                           .signalSemaphoreCount = 1, .pSignalSemaphores = &rendered[f]};
        VKFAIL(vkQueueSubmit(q, 1, &si, fences[f]));
        VkPresentInfoKHR pi = {VK_STRUCTURE_TYPE_PRESENT_INFO_KHR, .waitSemaphoreCount = 1,
                               .pWaitSemaphores = &rendered[f], .swapchainCount = 1, .pSwapchains = &sc,
                               .pImageIndices = &idx};
        VKFAIL(vkQueuePresentKHR(q, &pi));
        frames++;
    }
out:
    LOG("vk.fps frames=%u fps=%.1f messages=%d", frames, frames / (double)g_seconds, g_vk_errors);
    if (dev) {
        vkDeviceWaitIdle(dev);
        for (int i = 0; i < 3; i++) {
            if (acquired[i]) vkDestroySemaphore(dev, acquired[i], NULL);
            if (rendered[i]) vkDestroySemaphore(dev, rendered[i], NULL);
            if (fences[i]) vkDestroyFence(dev, fences[i], NULL);
        }
        if (pool) vkDestroyCommandPool(dev, pool, NULL);
        if (sc) vkDestroySwapchainKHR(dev, sc, NULL);
        vkDestroyDevice(dev, NULL);
    }
    if (surf) vkDestroySurfaceKHR(inst, surf, NULL);
    if (msgr && destroy_msgr) destroy_msgr(inst, msgr, NULL);
    if (inst) vkDestroyInstance(inst, NULL);
    ANativeWindow_release(w);
}

static void *worker(void *arg) {
    (void)arg;
    LOG("start mode=%s seconds=%d", g_mode, g_seconds);
    if (!strcmp(g_mode, "info") || !strcmp(g_mode, "all")) {
        vk_info();
        log_maps();   // before EGL too: a failing GLES driver may take the process down
        egl_info();
    }
    if (!strcmp(g_mode, "vk")) vk_present();
    if (!strcmp(g_mode, "gl") || !strcmp(g_mode, "all")) gl_present();
    log_maps();
    LOG("done");
    ANativeActivity_finish(g_activity);
    return NULL;
}

static void on_window_created(ANativeActivity *a, ANativeWindow *w) {
    (void)a;
    pthread_mutex_lock(&g_lock);
    g_window = w;
    pthread_cond_broadcast(&g_cond);
    pthread_mutex_unlock(&g_lock);
}

static void on_window_destroyed(ANativeActivity *a, ANativeWindow *w) {
    (void)a; (void)w;
    pthread_mutex_lock(&g_lock);
    g_window = NULL;
    g_stop = 1;
    pthread_mutex_unlock(&g_lock);
}

// Input: drained on a thread of its own and reported unhandled, so the window never stops answering ("not
// responding") while the GPU test runs.
static int drain_input(int fd, int events, void *data) {
    (void)fd; (void)events;
    AInputQueue *q = data;
    AInputEvent *e = NULL;
    while (AInputQueue_getEvent(q, &e) >= 0) {
        if (!AInputQueue_preDispatchEvent(q, e)) AInputQueue_finishEvent(q, e, 0);
    }
    return 1;
}

static void *input_thread(void *arg) {
    AInputQueue *q = arg;
    ALooper *l = ALooper_prepare(0);
    AInputQueue_attachLooper(q, l, 1, drain_input, q);
    while (!g_stop) ALooper_pollOnce(200, NULL, NULL, NULL);
    return NULL;
}

static void on_input_queue_destroyed(ANativeActivity *a, AInputQueue *q) {
    (void)a;
    AInputQueue_detachLooper(q);   // before the queue goes; the thread then only polls until the end
}

static void on_input_queue_created(ANativeActivity *a, AInputQueue *q) {
    (void)a;
    pthread_t t;
    pthread_create(&t, NULL, input_thread, q);
    pthread_detach(t);
}

// The intent's "mode" and "seconds" extras, through JNI (onCreate runs on the main thread, so activity->env holds).
static void read_extras(ANativeActivity *a) {
    JNIEnv *env = a->env;
    jobject intent = (*env)->CallObjectMethod(env, a->clazz,
        (*env)->GetMethodID(env, (*env)->GetObjectClass(env, a->clazz), "getIntent", "()Landroid/content/Intent;"));
    if (!intent) return;
    jclass ic = (*env)->GetObjectClass(env, intent);
    jstring mode = (*env)->CallObjectMethod(env, intent,
        (*env)->GetMethodID(env, ic, "getStringExtra", "(Ljava/lang/String;)Ljava/lang/String;"),
        (*env)->NewStringUTF(env, "mode"));
    if (mode) {
        const char *m = (*env)->GetStringUTFChars(env, mode, NULL);
        if (!strcmp(m, "info") || !strcmp(m, "gl") || !strcmp(m, "vk") || !strcmp(m, "all"))
            snprintf(g_mode, sizeof g_mode, "%s", m);
        (*env)->ReleaseStringUTFChars(env, mode, m);
    }
    jint s = (*env)->CallIntMethod(env, intent, (*env)->GetMethodID(env, ic, "getIntExtra", "(Ljava/lang/String;I)I"),
                                   (*env)->NewStringUTF(env, "seconds"), g_seconds);
    if (s > 0 && s <= 60) g_seconds = s;
}

JNIEXPORT void ANativeActivity_onCreate(ANativeActivity *a, void *state, size_t size) {
    (void)state; (void)size;
    g_activity = a;
    a->callbacks->onNativeWindowCreated = on_window_created;
    a->callbacks->onNativeWindowDestroyed = on_window_destroyed;
    a->callbacks->onInputQueueCreated = on_input_queue_created;
    a->callbacks->onInputQueueDestroyed = on_input_queue_destroyed;
    read_extras(a);
    pthread_t t;
    pthread_create(&t, NULL, worker, NULL);
    pthread_detach(t);
}
