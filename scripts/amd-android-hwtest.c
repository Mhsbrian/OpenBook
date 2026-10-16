// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Runs the AMD graphics stack of an AnyBook image (its own /system and /vendor binaries: bionic,
// Mesa RADV/radeonsi, minigbm with the amdgpu backend) on a real AMD GPU. Built with the NDK and
// started by scripts/amd-android-hwtest.sh in a container on a Linux host, with only the GPU's
// render node passed in. No Android framework, binder or property service is involved.
//   vulkan   vulkan.radv.so through its HAL entry point (as libvulkan opens it): instance, the GPU,
//            a device, and a vkCmdFillBuffer executed by the GPU and checked from the CPU
//   gles     libEGL_mesa.so (radeonsi) on the surfaceless platform: clear an FBO, read it back
//   gralloc  libminigbm_gralloc.so's driver API on the render node: tiled (GBM) and linear buffers,
//            written and read back through minigbm mappings
// Each part runs in a child process, so a crash is reported instead of ending the run.
//   amd-android-hwtest /dev/dri/renderDNNN /vendor/lib64
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <hardware/hwvulkan.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

#include "amdgpu_drm.h"
#include "drv_priv.h"

static const char *node, *libdir;

static void *must_dlopen(const char *name) {
  char path[512];
  snprintf(path, sizeof(path), "%s/%s", libdir, name);
  void *h = dlopen(path, RTLD_NOW | RTLD_LOCAL);
  if (!h) printf("dlopen %s FAILED: %s\n", path, dlerror());
  return h;
}

// ---- Vulkan (RADV) ---------------------------------------------------------------------------
#define VK(fn) PFN_vk##fn fn = (PFN_vk##fn)gipa(inst, "vk" #fn)
#define VKD(fn) PFN_vk##fn fn = (PFN_vk##fn)gdpa(dev, "vk" #fn)

static int vulkan(void) {
  void *h = must_dlopen("hw/vulkan.radv.so");
  if (!h) return 1;
  hwvulkan_module_t *m = dlsym(h, HAL_MODULE_INFO_SYM_AS_STR);
  hwvulkan_device_t *hal = NULL;
  if (!m || m->common.methods->open(&m->common, HWVULKAN_DEVICE_0, (hw_device_t **)&hal) || !hal) {
    printf("vulkan: HAL open failed\n");
    return 1;
  }
  printf("vulkan: HAL \"%s\" opened\n", m->common.name);
  VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
                           .pApplicationName = "anybook-amd-hwtest", .apiVersion = VK_API_VERSION_1_3};
  VkInstanceCreateInfo ici = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app};
  VkInstance inst;
  VkResult r = hal->CreateInstance(&ici, NULL, &inst);
  printf("vulkan: vkCreateInstance(1.3) = %d\n", r);
  if (r) return 1;
  PFN_vkGetInstanceProcAddr gipa = hal->GetInstanceProcAddr;
  VK(EnumeratePhysicalDevices);
  VK(GetPhysicalDeviceProperties2);
  VK(GetPhysicalDeviceQueueFamilyProperties);
  VK(GetPhysicalDeviceMemoryProperties);
  VK(CreateDevice);
  VK(GetDeviceProcAddr);
  VK(DestroyInstance);
  PFN_vkGetDeviceProcAddr gdpa = GetDeviceProcAddr;

  VkPhysicalDevice pds[8];
  uint32_t n = 8;
  r = EnumeratePhysicalDevices(inst, &n, pds);
  printf("vulkan: vkEnumeratePhysicalDevices = %d, %u device(s)\n", r, n);
  if (r || !n) return 1;
  for (uint32_t i = 0; i < n; i++) {
    VkPhysicalDeviceDriverProperties drv = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
    VkPhysicalDeviceProperties2 p = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, .pNext = &drv};
    GetPhysicalDeviceProperties2(pds[i], &p);
    printf("vulkan:   [%u] %s, Vulkan %u.%u.%u, %s %s, PCI %04x:%04x, type %d\n", i, p.properties.deviceName,
           VK_API_VERSION_MAJOR(p.properties.apiVersion), VK_API_VERSION_MINOR(p.properties.apiVersion),
           VK_API_VERSION_PATCH(p.properties.apiVersion), drv.driverName, drv.driverInfo,
           p.properties.vendorID, p.properties.deviceID, p.properties.deviceType);
  }

  VkPhysicalDevice pd = pds[0];
  VkQueueFamilyProperties qf[16];
  uint32_t nqf = 16, fam = UINT32_MAX;
  GetPhysicalDeviceQueueFamilyProperties(pd, &nqf, qf);
  for (uint32_t i = 0; i < nqf && fam == UINT32_MAX; i++)
    if (qf[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) fam = i;
  float prio = 1.0f;
  VkDeviceQueueCreateInfo qci = {.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
                                 .queueFamilyIndex = fam, .queueCount = 1, .pQueuePriorities = &prio};
  VkDeviceCreateInfo dci = {.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, .queueCreateInfoCount = 1,
                            .pQueueCreateInfos = &qci};
  VkDevice dev;
  r = CreateDevice(pd, &dci, NULL, &dev);
  printf("vulkan: vkCreateDevice (graphics queue family %u) = %d\n", fam, r);
  if (r) return 1;
  VKD(GetDeviceQueue); VKD(CreateBuffer); VKD(GetBufferMemoryRequirements); VKD(AllocateMemory);
  VKD(BindBufferMemory); VKD(MapMemory); VKD(CreateCommandPool); VKD(AllocateCommandBuffers);
  VKD(BeginCommandBuffer); VKD(CmdFillBuffer); VKD(EndCommandBuffer); VKD(CreateFence); VKD(QueueSubmit);
  VKD(WaitForFences); VKD(DestroyDevice);

  const VkDeviceSize size = 16 << 20;
  VkBufferCreateInfo bci = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = size,
                            .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT};
  VkBuffer buf;
  CreateBuffer(dev, &bci, NULL, &buf);
  VkMemoryRequirements req;
  GetBufferMemoryRequirements(dev, buf, &req);
  VkPhysicalDeviceMemoryProperties mp;
  GetPhysicalDeviceMemoryProperties(pd, &mp);
  uint32_t type = UINT32_MAX;
  const VkMemoryPropertyFlags want = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
  for (uint32_t i = 0; i < mp.memoryTypeCount && type == UINT32_MAX; i++)
    if ((req.memoryTypeBits & (1u << i)) && (mp.memoryTypes[i].propertyFlags & want) == want) type = i;
  VkMemoryAllocateInfo mai = {.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, .allocationSize = req.size,
                              .memoryTypeIndex = type};
  VkDeviceMemory mem;
  if (AllocateMemory(dev, &mai, NULL, &mem) || BindBufferMemory(dev, buf, mem, 0)) {
    printf("vulkan: memory allocation failed\n");
    return 1;
  }
  uint32_t *map;
  MapMemory(dev, mem, 0, size, 0, (void **)&map);
  memset(map, 0, size);

  VkQueue q;
  GetDeviceQueue(dev, fam, 0, &q);
  VkCommandPoolCreateInfo pci = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO, .queueFamilyIndex = fam};
  VkCommandPool pool;
  CreateCommandPool(dev, &pci, NULL, &pool);
  VkCommandBufferAllocateInfo cai = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
                                     .commandPool = pool, .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
                                     .commandBufferCount = 1};
  VkCommandBuffer cb;
  AllocateCommandBuffers(dev, &cai, &cb);
  VkCommandBufferBeginInfo bbi = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
  BeginCommandBuffer(cb, &bbi);
  CmdFillBuffer(cb, buf, 0, size, 0xa5a5a5a5u);
  EndCommandBuffer(cb);
  VkFenceCreateInfo fci = {.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
  VkFence fence;
  CreateFence(dev, &fci, NULL, &fence);
  VkSubmitInfo si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cb};
  r = QueueSubmit(q, 1, &si, fence);
  VkResult w = WaitForFences(dev, 1, &fence, VK_TRUE, 5000000000ull);
  size_t bad = 0;
  for (size_t i = 0; i < size / 4; i++) bad += map[i] != 0xa5a5a5a5u;
  printf("vulkan: vkQueueSubmit = %d, vkWaitForFences = %d, %zu of %" PRIu64 " words wrong after the GPU fill\n",
         r, w, bad, size / 4);
  DestroyDevice(dev, NULL);
  DestroyInstance(inst, NULL);
  return r || w || bad;
}

// ---- GLES (radeonsi through libEGL_mesa) -----------------------------------------------------
static int gles(void) {
  void *h = must_dlopen("egl/libEGL_mesa.so");
  if (!h) return 1;
  __eglMustCastToProperFunctionPointerType (*gpa)(const char *) = dlsym(h, "eglGetProcAddress");
  if (!gpa) return 1;
  // EGL entry points are exported by libEGL_mesa.so; GL ones come from eglGetProcAddress.
#define EGLF(type, name) __typeof__(type) name = dlsym(h, #name) ? (__typeof__(type))dlsym(h, #name) : (__typeof__(type))gpa(#name)
  EGLF(PFNEGLGETPLATFORMDISPLAYEXTPROC, eglGetPlatformDisplayEXT);
  EGLF(EGLBoolean (*)(EGLDisplay, EGLint *, EGLint *), eglInitialize);
  EGLF(EGLBoolean (*)(EGLenum), eglBindAPI);
  EGLF(EGLContext (*)(EGLDisplay, EGLConfig, EGLContext, const EGLint *), eglCreateContext);
  EGLF(EGLBoolean (*)(EGLDisplay, EGLSurface, EGLSurface, EGLContext), eglMakeCurrent);
  EGLF(EGLint (*)(void), eglGetError);
  EGLF(const GLubyte *(*)(GLenum), glGetString);
  EGLF(void (*)(GLsizei, GLuint *), glGenRenderbuffers);
  EGLF(void (*)(GLenum, GLuint), glBindRenderbuffer);
  EGLF(void (*)(GLenum, GLenum, GLsizei, GLsizei), glRenderbufferStorage);
  EGLF(void (*)(GLsizei, GLuint *), glGenFramebuffers);
  EGLF(void (*)(GLenum, GLuint), glBindFramebuffer);
  EGLF(void (*)(GLenum, GLenum, GLenum, GLuint), glFramebufferRenderbuffer);
  EGLF(GLenum (*)(GLenum), glCheckFramebufferStatus);
  EGLF(void (*)(GLfloat, GLfloat, GLfloat, GLfloat), glClearColor);
  EGLF(void (*)(GLbitfield), glClear);
  EGLF(void (*)(GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, void *), glReadPixels);
  if (!eglGetPlatformDisplayEXT || !glReadPixels) {
    printf("gles: missing entry points\n");
    return 1;
  }
  EGLDisplay dpy = eglGetPlatformDisplayEXT(EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, NULL);
  EGLint maj = 0, min = 0;
  if (!eglInitialize(dpy, &maj, &min)) {
    printf("gles: eglInitialize(surfaceless) failed: 0x%x\n", eglGetError());
    return 1;
  }
  eglBindAPI(EGL_OPENGL_ES_API);
  const EGLint attr[] = {EGL_CONTEXT_MAJOR_VERSION, 3, EGL_NONE};
  EGLContext ctx = eglCreateContext(dpy, EGL_NO_CONFIG_KHR, EGL_NO_CONTEXT, attr);
  if (ctx == EGL_NO_CONTEXT || !eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx)) {
    printf("gles: context failed: 0x%x\n", eglGetError());
    return 1;
  }
  printf("gles: EGL %d.%d, GL_RENDERER %s, GL_VERSION %s\n", maj, min, glGetString(GL_RENDERER),
         glGetString(GL_VERSION));
  GLuint rb, fb;
  glGenRenderbuffers(1, &rb);
  glBindRenderbuffer(GL_RENDERBUFFER, rb);
  glRenderbufferStorage(GL_RENDERBUFFER, 0x8058 /* GL_RGBA8 */, 256, 256);
  glGenFramebuffers(1, &fb);
  glBindFramebuffer(GL_FRAMEBUFFER, fb);
  glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, rb);
  if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
    printf("gles: FBO incomplete\n");
    return 1;
  }
  glClearColor(0.0f, 1.0f, 0.0f, 1.0f);
  glClear(GL_COLOR_BUFFER_BIT);
  static uint32_t px[256 * 256];
  glReadPixels(0, 0, 256, 256, GL_RGBA, GL_UNSIGNED_BYTE, px);
  size_t bad = 0;
  for (size_t i = 0; i < 256 * 256; i++) bad += px[i] != 0xff00ff00u;
  printf("gles: cleared a 256x256 FBO to green on the GPU, %zu pixels wrong on read-back\n", bad);
  return bad != 0;
}

// ---- gralloc (minigbm's driver API, amdgpu backend) ------------------------------------------
static int gralloc(void) {
  void *h = must_dlopen("libminigbm_gralloc.so");
  if (!h) return 1;
#define SYM(name) __typeof__(name) *p_##name = dlsym(h, #name)
  SYM(drv_create); SYM(drv_destroy); SYM(drv_get_name); SYM(drv_bo_create); SYM(drv_bo_destroy);
  SYM(drv_bo_map); SYM(drv_bo_unmap); SYM(drv_bo_get_format_modifier); SYM(drv_bo_get_plane_stride);
  SYM(drv_bo_get_num_planes); SYM(drv_bo_get_total_size);
  if (!p_drv_create || !p_drv_bo_unmap || !p_drv_bo_get_total_size) {
    printf("gralloc: minigbm driver API not exported\n");
    return 1;
  }
  int fd = open(node, O_RDWR | O_CLOEXEC);
  struct driver *drv = fd >= 0 ? p_drv_create(fd, NULL) : NULL;
  if (!drv) {
    printf("gralloc: drv_create(%s) failed\n", node);
    return 1;
  }
  printf("gralloc: minigbm backend \"%s\"\n", p_drv_get_name(drv));
  int fails = strcmp(p_drv_get_name(drv), "amdgpu") != 0;
  const struct { const char *name; uint64_t use; } cases[] = {
      {"GPU-only (tiled via GBM)", BO_USE_RENDERING | BO_USE_TEXTURE | BO_USE_SCANOUT},
      {"CPU (linear)", BO_USE_SW_READ_OFTEN | BO_USE_SW_WRITE_OFTEN | BO_USE_TEXTURE},
  };
  for (size_t c = 0; c < 2; c++) {
    const uint32_t w = 1000, hgt = 600;
    struct bo *bo = p_drv_bo_create(drv, w, hgt, DRM_FORMAT_ABGR8888, cases[c].use);
    if (!bo) {
      printf("gralloc: %s: allocation failed\n", cases[c].name);
      fails++;
      continue;
    }
    struct drm_amdgpu_gem_metadata md = {.handle = bo->handle.u32, .op = AMDGPU_GEM_METADATA_OP_GET_METADATA};
    struct drm_amdgpu_gem_metadata *mdp = &md;
    unsigned long req = DRM_IOWR(DRM_COMMAND_BASE + DRM_AMDGPU_GEM_METADATA, struct drm_amdgpu_gem_metadata);
    int swz = ioctl(fd, req, mdp) ? -1 : (int)AMDGPU_TILING_GET(md.data.tiling_info, SWIZZLE_MODE);
    printf("gralloc: %s: %ux%u modifier 0x%016" PRIx64 " planes %zu stride %u size %zu swizzle mode %d\n",
           cases[c].name, w, hgt, p_drv_bo_get_format_modifier(bo), p_drv_bo_get_num_planes(bo),
           p_drv_bo_get_plane_stride(bo, 0), p_drv_bo_get_total_size(bo), swz);
    struct rectangle rect = {0, 0, w, hgt};
    struct mapping *m;
    uint8_t *p = p_drv_bo_map(bo, &rect, BO_MAP_WRITE, &m, 0);
    size_t bad = 0;
    if (p == MAP_FAILED) {
      printf("gralloc: %s: map WRITE failed\n", cases[c].name);
      fails++;
    } else {
      uint32_t stride = m->vma->map_strides[0];
      for (uint32_t y = 0; y < hgt; y++)
        for (uint32_t x = 0; x < w; x++) ((uint32_t *)(p + (size_t)y * stride))[x] = (y << 16) ^ x ^ 0x5a000000u;
      p_drv_bo_unmap(bo, m);
      p = p_drv_bo_map(bo, &rect, BO_MAP_READ, &m, 0);
      if (p == MAP_FAILED) {
        printf("gralloc: %s: map READ failed\n", cases[c].name);
        fails++;
      } else {
        stride = m->vma->map_strides[0];
        for (uint32_t y = 0; y < hgt; y++)
          for (uint32_t x = 0; x < w; x++)
            bad += ((uint32_t *)(p + (size_t)y * stride))[x] != ((y << 16) ^ x ^ 0x5a000000u);
        p_drv_bo_unmap(bo, m);
        printf("gralloc: %s: wrote a pattern through one mapping, %zu pixels wrong through a second\n",
               cases[c].name, bad);
        fails += bad != 0;
      }
    }
    p_drv_bo_destroy(bo);
  }
  p_drv_destroy(drv);
  close(fd);
  return fails;
}

static int in_child(int (*fn)(void), const char *name) {
  fflush(stdout);
  pid_t pid = fork();
  if (pid == 0) _exit(fn());
  int st = 0;
  waitpid(pid, &st, 0);
  int rc = WIFEXITED(st) ? WEXITSTATUS(st) : 128 + WTERMSIG(st);
  if (WIFSIGNALED(st)) printf("%s: CRASHED with signal %d\n", name, WTERMSIG(st));
  printf("%s: %s\n", name, rc ? "FAIL" : "PASS");
  return rc;
}

int main(int argc, char **argv) {
  setvbuf(stdout, NULL, _IOLBF, 0);
  if (argc != 3) {
    fprintf(stderr, "usage: %s /dev/dri/renderDNNN /vendor/lib64\n", argv[0]);
    return 2;
  }
  node = argv[1];
  libdir = argv[2];
  int rc = 0;
  rc |= in_child(vulkan, "vulkan") != 0;
  rc |= (in_child(gles, "gles") != 0) << 1;
  rc |= (in_child(gralloc, "gralloc") != 0) << 2;
  printf("result: %s\n", rc ? "FAIL" : "PASS");
  return rc;
}
