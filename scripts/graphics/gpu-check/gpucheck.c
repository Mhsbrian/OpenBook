// SPDX-License-Identifier: Apache-2.0
// GPU Check (ANAL-247): a small Android app that reports which graphics driver its own process loaded and how fast
// it presents, so a per-app driver choice can be checked without a game. Pure NDK (NativeActivity, no Java).
//
//   am start -n org.openbook.gpucheck/android.app.NativeActivity [--es mode info|gl|all] [--ei seconds N]
//
// Every result is one logcat line, tag "gpucheck", "GPUCHECK key=value ...":
//   maps       the driver libraries mapped into this process (an updatable driver shows its APK's path)
//   vk.*       Vulkan instance and each physical device: name, IDs, driver ID/name/info, API version
//   egl.*      EGL and GLES strings from a 1x1 pbuffer context
//   gl.*       (mode gl/all) frames presented to the activity's window with swap interval 0: a light phase
//              (one clear per frame, present-bound) and a heavy phase (a full-window ALU-bound fragment shader),
//              each N seconds (default 5), as frames per second
//   done       the end; the activity then finishes itself
// Launched from the launcher (no extra), it runs "all".
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <android/log.h>
#include <android/native_activity.h>
#include <jni.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
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
        if (strstr(path, ".apk") && !strstr(path, "OpenBookNvk")) continue;   // this app's own APK
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

static void gl_present(void) {
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

static void *worker(void *arg) {
    (void)arg;
    LOG("start mode=%s seconds=%d", g_mode, g_seconds);
    if (!strcmp(g_mode, "info") || !strcmp(g_mode, "all")) {
        vk_info();
        egl_info();
    }
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
        if (!strcmp(m, "info") || !strcmp(m, "gl") || !strcmp(m, "all")) snprintf(g_mode, sizeof g_mode, "%s", m);
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
    read_extras(a);
    pthread_t t;
    pthread_create(&t, NULL, worker, NULL);
    pthread_detach(t);
}
