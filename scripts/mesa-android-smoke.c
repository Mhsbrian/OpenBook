// Load test for the Mesa Android artifacts. Opens vulkan.radv.so through its HAL entry point
// (HMI -> hwvulkan_device_t, as Android's libvulkan does) and libEGL_mesa.so (dlopen + entry
// points, as Android's libEGL does), then calls what works without a GPU. Each part runs in a
// child process so a crash in one is reported instead of hiding the other.
//   mesa-smoke <path/vulkan.radv.so> <path/libEGL_mesa.so> <path/libGLESv2_mesa.so>
#include <EGL/egl.h>
#include <dlfcn.h>
#include <hardware/hwvulkan.h>
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>

static int vulkan(const char *path) {
  void *h = dlopen(path, RTLD_NOW | RTLD_LOCAL);
  if (!h) { printf("vulkan: dlopen FAILED: %s\n", dlerror()); return 1; }
  hwvulkan_module_t *m = dlsym(h, HAL_MODULE_INFO_SYM_AS_STR);
  if (!m) { printf("vulkan: no " HAL_MODULE_INFO_SYM_AS_STR ": %s\n", dlerror()); return 1; }
  printf("vulkan: HMI id=%s name=\"%s\" author=\"%s\" module_api=0x%x hal_api=0x%x\n", m->common.id,
         m->common.name, m->common.author, m->common.module_api_version, m->common.hal_api_version);
  hwvulkan_device_t *dev = NULL;
  int r = m->common.methods->open(&m->common, HWVULKAN_DEVICE_0, (hw_device_t **)&dev);
  printf("vulkan: open(%s) = %d\n", HWVULKAN_DEVICE_0, r);
  if (r || !dev) return 1;

  uint32_t n = 0;
  VkExtensionProperties ext[64];
  dev->EnumerateInstanceExtensionProperties(NULL, &n, NULL);
  if (n > 64) n = 64;
  dev->EnumerateInstanceExtensionProperties(NULL, &n, ext);
  printf("vulkan: %u instance extensions:", n);
  for (uint32_t i = 0; i < n; i++) printf(" %s", ext[i].extensionName);
  printf("\n");

  VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
                           .pApplicationName = "anybook-mesa-smoke", .apiVersion = VK_API_VERSION_1_3};
  VkInstanceCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app};
  VkInstance inst;
  VkResult vr = dev->CreateInstance(&ci, NULL, &inst);
  printf("vulkan: vkCreateInstance(1.3) = %d\n", vr);
  if (vr != VK_SUCCESS) return 1;

  PFN_vkEnumeratePhysicalDevices enum_pd =
      (PFN_vkEnumeratePhysicalDevices)dev->GetInstanceProcAddr(inst, "vkEnumeratePhysicalDevices");
  PFN_vkGetPhysicalDeviceProperties props =
      (PFN_vkGetPhysicalDeviceProperties)dev->GetInstanceProcAddr(inst, "vkGetPhysicalDeviceProperties");
  PFN_vkDestroyInstance destroy = (PFN_vkDestroyInstance)dev->GetInstanceProcAddr(inst, "vkDestroyInstance");
  VkPhysicalDevice pd[8];
  uint32_t pdn = 8;
  vr = enum_pd(inst, &pdn, pd);
  printf("vulkan: vkEnumeratePhysicalDevices = %d, %u device(s)\n", vr, pdn);
  for (uint32_t i = 0; i < pdn; i++) {
    VkPhysicalDeviceProperties p;
    props(pd[i], &p);
    printf("vulkan:   [%u] %s api %u.%u.%u driver 0x%x\n", i, p.deviceName, VK_API_VERSION_MAJOR(p.apiVersion),
           VK_API_VERSION_MINOR(p.apiVersion), VK_API_VERSION_PATCH(p.apiVersion), p.driverVersion);
  }
  destroy(inst, NULL);
  dev->common.close(&dev->common);
  printf("vulkan: OK\n");
  return 0;
}

static int egl(const char *path, const char *gles2) {
  void *h = dlopen(path, RTLD_NOW | RTLD_LOCAL);
  if (!h) { printf("egl: dlopen FAILED: %s\n", dlerror()); return 1; }
  const char *(*query)(EGLDisplay, EGLint) = dlsym(h, "eglQueryString");
  EGLDisplay (*get_display)(EGLNativeDisplayType) = dlsym(h, "eglGetDisplay");
  EGLBoolean (*init)(EGLDisplay, EGLint *, EGLint *) = dlsym(h, "eglInitialize");
  EGLBoolean (*term)(EGLDisplay) = dlsym(h, "eglTerminate");
  EGLint (*error)(void) = dlsym(h, "eglGetError");
  void *(*gpa)(const char *) = dlsym(h, "eglGetProcAddress");
  if (!query || !get_display || !init || !term || !error || !gpa) { printf("egl: missing entry point\n"); return 1; }
  printf("egl: client extensions: %s\n", query(EGL_NO_DISPLAY, EGL_EXTENSIONS));
  printf("egl: eglGetProcAddress(glGetString) = %p\n", gpa("glGetString"));
  EGLDisplay d = get_display(EGL_DEFAULT_DISPLAY);
  EGLint maj = 0, min = 0;
  EGLBoolean ok = init(d, &maj, &min);
  printf("egl: eglInitialize(EGL_DEFAULT_DISPLAY) = %d (EGL %d.%d), eglGetError = 0x%x\n", ok, maj, min, error());
  if (ok) {
    printf("egl: vendor=%s version=%s apis=%s\n", query(d, EGL_VENDOR), query(d, EGL_VERSION), query(d, EGL_CLIENT_APIS));
    term(d);
  }
  void *g = dlopen(gles2, RTLD_NOW | RTLD_LOCAL);
  printf("gles2: dlopen %s, glGetString=%p\n", g ? "ok" : dlerror(), g ? dlsym(g, "glGetString") : NULL);
  printf("egl: done\n");
  return 0;
}

static int in_child(int (*fn)(const char *, const char *), const char *a, const char *b, const char *name) {
  fflush(stdout);
  pid_t pid = fork();
  if (pid == 0) {
    int r = fn(a, b);
    fflush(stdout);
    _exit(r);
  }
  int st = 0;
  waitpid(pid, &st, 0);
  if (WIFSIGNALED(st)) printf("%s: CRASHED with signal %d\n", name, WTERMSIG(st));
  else printf("%s: exit %d\n", name, WEXITSTATUS(st));
  return WIFEXITED(st) ? WEXITSTATUS(st) : 128 + WTERMSIG(st);
}

static int vulkan2(const char *a, const char *b) { (void)b; return vulkan(a); }

int main(int argc, char **argv) {
  setvbuf(stdout, NULL, _IOLBF, 0);
  if (argc != 4) { fprintf(stderr, "usage: %s vulkan.radv.so libEGL_mesa.so libGLESv2_mesa.so\n", argv[0]); return 2; }
  int rv = in_child(vulkan2, argv[1], NULL, "vulkan");
  int re = in_child(egl, argv[2], argv[3], "egl");
  return rv || re;
}
