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
//   swapchain gralloc buffers as libvulkan hands them to RADV for an ANGLE window surface: wrapped at
//            vkCreateImage (VkNativeBufferANDROID) and bound late at vkBindImageMemory2 (deferred
//            allocation, VK_EXT_swapchain_maintenance1). RADV writes a per-pixel pattern, radeonsi
//            reads it through a dma-buf import without modifiers (the layout amdgpu's display uses),
//            then radeonsi writes and RADV reads.
// Each part runs in a child process, so a crash is reported instead of ending the run.
//   amd-android-hwtest /dev/dri/renderDNNN /vendor/lib64 [part ...]
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <hardware/gralloc.h>
#include <hardware/hwvulkan.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <system/graphics.h>
#include <unistd.h>
#include <vulkan/vk_android_native_buffer.h>

#include "amdgpu_drm.h"
#include "drm_fourcc.h"
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

// ---- Swapchain images on gralloc buffers (VK_ANDROID_native_buffer) --------------------------
// The usage a window buffer gets: libvulkan asks RADV (render + texture), SurfaceFlinger as the
// consumer adds composer + texture.
#define SWAPCHAIN_USAGE (GRALLOC_USAGE_HW_RENDER | GRALLOC_USAGE_HW_TEXTURE | GRALLOC_USAGE_HW_COMPOSER)
// minigbm's gralloc0 perform() op behind Mesa's "cros" u_gralloc (cros_gralloc/gralloc0/gralloc0.cc).
#define CROS_GRALLOC_DRM_GET_BUFFER_INFO 4
struct cros_gralloc0_buffer_info {
  uint32_t drm_fourcc;
  int num_fds;
  int fds[4];
  uint64_t modifier;
  int offset[4];
  int stride[4];
};
// libvulkan passes its VkSwapchainKHR; RADV must not look inside it on Android.
#define FAKE_SWAPCHAIN ((VkSwapchainKHR)(uintptr_t)0x5ca1ab1e)

static struct { uint32_t w, h; int deferred; } sc;

static uint32_t sc_pattern(uint32_t x, uint32_t y, uint32_t salt) { return (y << 16) ^ x ^ salt; }

// The BO's swizzle mode as radeonsi wrote it into the kernel metadata (what amdgpu's display reads).
static int bo_swizzle(int dmabuf) {
  int fd = open(node, O_RDWR | O_CLOEXEC);
  struct drm_prime_handle ph = {.fd = dmabuf};
  int swz = -1;
  if (fd >= 0 && !ioctl(fd, DRM_IOCTL_PRIME_FD_TO_HANDLE, &ph)) {
    struct drm_amdgpu_gem_metadata md = {.handle = ph.handle, .op = AMDGPU_GEM_METADATA_OP_GET_METADATA};
    unsigned long req = DRM_IOWR(DRM_COMMAND_BASE + DRM_AMDGPU_GEM_METADATA, struct drm_amdgpu_gem_metadata);
    if (!ioctl(fd, req, &md)) swz = (int)AMDGPU_TILING_GET(md.data.tiling_info, SWIZZLE_MODE);
  }
  if (fd >= 0) close(fd);
  return swz;
}

static int swapchain_case(void) {
  const uint32_t w = sc.w, ht = sc.h;
  const char *path = sc.deferred ? "bound at vkBindImageMemory2 (deferred)" : "wrapped at vkCreateImage";
  char tag[64];
  snprintf(tag, sizeof(tag), "swapchain %ux%u %s", w, ht, sc.deferred ? "deferred" : "create");

  // gralloc0 from minigbm: the same module (and driver instance) Mesa's u_gralloc queries.
  void *gh = must_dlopen("hw/gralloc.minigbm.so");
  const gralloc_module_t *gm = gh ? dlsym(gh, HAL_MODULE_INFO_SYM_AS_STR) : NULL;
  alloc_device_t *ad = NULL;
  if (!gm || gm->common.methods->open(&gm->common, GRALLOC_HARDWARE_GPU0, (hw_device_t **)&ad) || !ad) {
    printf("%s: gralloc.minigbm open failed\n", tag);
    return 1;
  }
  buffer_handle_t handle = NULL;
  int stride = 0;
  if (ad->alloc(ad, (int)w, (int)ht, HAL_PIXEL_FORMAT_RGBA_8888, SWAPCHAIN_USAGE, &handle, &stride) || !handle) {
    printf("%s: gralloc alloc failed\n", tag);
    return 1;
  }
  struct cros_gralloc0_buffer_info bi = {0};
  int pr = gm->perform(gm, CROS_GRALLOC_DRM_GET_BUFFER_INFO, handle, &bi);
  printf("%s: gralloc RGBA_8888 usage 0x%x: stride %d px, perform(GET_BUFFER_INFO) = %d, modifier 0x%016" PRIx64
         ", plane stride %d B, BO swizzle mode %d\n",
         tag, SWAPCHAIN_USAGE, stride, pr, bi.modifier, bi.stride[0], bo_swizzle(handle->data[0]));

  // RADV, opened through its HAL entry point as libvulkan does.
  void *vh = must_dlopen("hw/vulkan.radv.so");
  hwvulkan_module_t *m = vh ? dlsym(vh, HAL_MODULE_INFO_SYM_AS_STR) : NULL;
  hwvulkan_device_t *hal = NULL;
  if (!m || m->common.methods->open(&m->common, HWVULKAN_DEVICE_0, (hw_device_t **)&hal) || !hal) return 1;
  VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO, .apiVersion = VK_API_VERSION_1_1};
  VkInstanceCreateInfo ici = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app};
  VkInstance inst;
  if (hal->CreateInstance(&ici, NULL, &inst)) return 1;
  PFN_vkGetInstanceProcAddr gipa = hal->GetInstanceProcAddr;
  VK(EnumeratePhysicalDevices); VK(GetPhysicalDeviceQueueFamilyProperties); VK(GetPhysicalDeviceMemoryProperties);
  VK(EnumerateDeviceExtensionProperties); VK(CreateDevice); VK(GetDeviceProcAddr);
  PFN_vkGetDeviceProcAddr gdpa = GetDeviceProcAddr;
  VkPhysicalDevice pd;
  uint32_t n = 1;
  if (EnumeratePhysicalDevices(inst, &n, &pd) < 0 || !n) return 1;
  VkQueueFamilyProperties qf[16];
  uint32_t nqf = 16, fam = UINT32_MAX;
  GetPhysicalDeviceQueueFamilyProperties(pd, &nqf, qf);
  for (uint32_t i = 0; i < nqf && fam == UINT32_MAX; i++)
    if (qf[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) fam = i;
  // libvulkan enables VK_ANDROID_native_buffer on the driver's device for every swapchain user.
  VkExtensionProperties exts[512];
  uint32_t next = 512;
  EnumerateDeviceExtensionProperties(pd, NULL, &next, exts);
  const char *anb_ext[] = {VK_ANDROID_NATIVE_BUFFER_EXTENSION_NAME};
  int have_anb = 0;
  for (uint32_t i = 0; i < next; i++) have_anb |= !strcmp(exts[i].extensionName, anb_ext[0]);
  float prio = 1.0f;
  VkDeviceQueueCreateInfo qci = {.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO, .queueFamilyIndex = fam,
                                 .queueCount = 1, .pQueuePriorities = &prio};
  VkDeviceCreateInfo dci = {.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, .queueCreateInfoCount = 1,
                            .pQueueCreateInfos = &qci, .enabledExtensionCount = have_anb ? 1 : 0,
                            .ppEnabledExtensionNames = anb_ext};
  VkDevice dev;
  VkResult r = CreateDevice(pd, &dci, NULL, &dev);
  if (r) {
    printf("%s: vkCreateDevice = %d (VK_ANDROID_native_buffer %s)\n", tag, r, have_anb ? "offered" : "missing");
    return 1;
  }
  VKD(CreateImage); VKD(BindImageMemory2); VKD(GetImageSubresourceLayout); VKD(GetDeviceQueue); VKD(CreateBuffer);
  VKD(GetBufferMemoryRequirements); VKD(AllocateMemory); VKD(BindBufferMemory); VKD(MapMemory);
  VKD(CreateCommandPool); VKD(AllocateCommandBuffers); VKD(BeginCommandBuffer); VKD(EndCommandBuffer);
  VKD(CmdPipelineBarrier); VKD(CmdCopyBufferToImage); VKD(CmdCopyImageToBuffer); VKD(QueueSubmit);
  VKD(QueueWaitIdle); VKD(ResetCommandBuffer); VKD(DestroyImage); VKD(DestroyDevice);

  // The swapchain image, as libvulkan's CreateSwapchainKHR / AcquireNextImageKHR make it.
  VkImageCreateInfo imci = {.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO, .imageType = VK_IMAGE_TYPE_2D,
                            .format = VK_FORMAT_R8G8B8A8_UNORM, .extent = {w, ht, 1}, .mipLevels = 1,
                            .arrayLayers = 1, .samples = VK_SAMPLE_COUNT_1_BIT, .tiling = VK_IMAGE_TILING_OPTIMAL,
                            .usage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT |
                                     VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT,
                            .sharingMode = VK_SHARING_MODE_EXCLUSIVE};
  VkSwapchainImageCreateInfoANDROID sic = {.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_IMAGE_CREATE_INFO_ANDROID};
  VkImageSwapchainCreateInfoKHR isci = {.sType = VK_STRUCTURE_TYPE_IMAGE_SWAPCHAIN_CREATE_INFO_KHR,
                                        .swapchain = FAKE_SWAPCHAIN};
  VkBindImageMemorySwapchainInfoKHR bimsi = {.sType = VK_STRUCTURE_TYPE_BIND_IMAGE_MEMORY_SWAPCHAIN_INFO_KHR,
                                             .swapchain = FAKE_SWAPCHAIN, .imageIndex = 0};
  VkNativeBufferANDROID nb = {.sType = VK_STRUCTURE_TYPE_NATIVE_BUFFER_ANDROID,
                              .pNext = sc.deferred ? (const void *)&bimsi : (const void *)&sic, .handle = handle,
                              .stride = stride, .format = HAL_PIXEL_FORMAT_RGBA_8888, .usage = SWAPCHAIN_USAGE,
                              .usage3 = SWAPCHAIN_USAGE};
  imci.pNext = sc.deferred ? (const void *)&isci : (const void *)&nb;
  VkImage img;
  r = CreateImage(dev, &imci, NULL, &img);
  printf("%s: vkCreateImage = %d\n", tag, r);
  if (r) return 1;
  if (sc.deferred) {
    VkBindImageMemoryInfo bimi = {.sType = VK_STRUCTURE_TYPE_BIND_IMAGE_MEMORY_INFO, .pNext = &nb, .image = img,
                                  .memory = VK_NULL_HANDLE};
    printf("%s: vkBindImageMemory2(memory = VK_NULL_HANDLE, VkNativeBufferANDROID) ...\n", tag);
    r = BindImageMemory2(dev, 1, &bimi);
    printf("%s: vkBindImageMemory2 = %d\n", tag, r);
    if (r) return 1;
  }
  VkImageSubresource sub = {.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT};
  VkSubresourceLayout lay;
  GetImageSubresourceLayout(dev, img, &sub, &lay);
  printf("%s: %s; RADV row pitch %" PRIu64 " B (gralloc %d B)\n", tag, path, (uint64_t)lay.rowPitch, stride * 4);

  // A host-visible staging buffer and one command buffer.
  const VkDeviceSize size = (VkDeviceSize)w * ht * 4;
  VkBufferCreateInfo bci = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = size,
                            .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT};
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
  uint32_t *map;
  if (AllocateMemory(dev, &mai, NULL, &mem) || BindBufferMemory(dev, buf, mem, 0) ||
      MapMemory(dev, mem, 0, size, 0, (void **)&map))
    return 1;
  VkQueue q;
  GetDeviceQueue(dev, fam, 0, &q);
  VkCommandPoolCreateInfo pci = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
                                 .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT, .queueFamilyIndex = fam};
  VkCommandPool pool;
  CreateCommandPool(dev, &pci, NULL, &pool);
  VkCommandBufferAllocateInfo cai = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .commandPool = pool,
                                     .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
  VkCommandBuffer cb;
  AllocateCommandBuffers(dev, &cai, &cb);
  VkCommandBufferBeginInfo cbbi = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
  VkBufferImageCopy region = {.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1}, .imageExtent = {w, ht, 1}};
  VkImageMemoryBarrier ib = {.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER, .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                             .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .image = img,
                             .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
  VkSubmitInfo si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cb};

  // 1) RADV writes: pattern A, buffer -> image, left in GENERAL for the other driver.
  for (uint32_t y = 0; y < ht; y++)
    for (uint32_t x = 0; x < w; x++) map[(size_t)y * w + x] = sc_pattern(x, y, 0x5a000000u);
  BeginCommandBuffer(cb, &cbbi);
  ib.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED;
  ib.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
  ib.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
  CmdPipelineBarrier(cb, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL, 1, &ib);
  CmdCopyBufferToImage(cb, buf, img, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region);
  ib.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
  ib.newLayout = VK_IMAGE_LAYOUT_GENERAL;
  ib.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
  ib.dstAccessMask = VK_ACCESS_MEMORY_READ_BIT;
  CmdPipelineBarrier(cb, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, 0, 0, NULL, 0, NULL, 1, &ib);
  EndCommandBuffer(cb);
  if (QueueSubmit(q, 1, &si, VK_NULL_HANDLE) || QueueWaitIdle(q)) return 1;

  // 2) radeonsi reads it through a dma-buf import without modifiers: the BO metadata decides the layout.
  void *h = must_dlopen("egl/libEGL_mesa.so");  // EGLF (gles() above) resolves through h and gpa
  if (!h) return 1;
  __eglMustCastToProperFunctionPointerType (*gpa)(const char *) = dlsym(h, "eglGetProcAddress");
  EGLF(PFNEGLGETPLATFORMDISPLAYEXTPROC, eglGetPlatformDisplayEXT);
  EGLF(EGLBoolean (*)(EGLDisplay, EGLint *, EGLint *), eglInitialize);
  EGLF(const char *(*)(EGLDisplay, EGLint), eglQueryString);
  EGLF(EGLBoolean (*)(EGLenum), eglBindAPI);
  EGLF(EGLContext (*)(EGLDisplay, EGLConfig, EGLContext, const EGLint *), eglCreateContext);
  EGLF(EGLBoolean (*)(EGLDisplay, EGLSurface, EGLSurface, EGLContext), eglMakeCurrent);
  EGLF(EGLint (*)(void), eglGetError);
  EGLF(PFNEGLCREATEIMAGEKHRPROC, eglCreateImageKHR);
  EGLF(PFNGLEGLIMAGETARGETTEXTURE2DOESPROC, glEGLImageTargetTexture2DOES);
  EGLF(void (*)(GLsizei, GLuint *), glGenTextures);
  EGLF(void (*)(GLenum, GLuint), glBindTexture);
  EGLF(void (*)(GLenum, GLint, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, const void *), glTexSubImage2D);
  EGLF(void (*)(GLsizei, GLuint *), glGenFramebuffers);
  EGLF(void (*)(GLenum, GLuint), glBindFramebuffer);
  EGLF(void (*)(GLenum, GLenum, GLenum, GLuint, GLint), glFramebufferTexture2D);
  EGLF(GLenum (*)(GLenum), glCheckFramebufferStatus);
  EGLF(void (*)(GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, void *), glReadPixels);
  EGLF(void (*)(GLenum, GLint), glPixelStorei);
  EGLF(void (*)(void), glFinish);
  EGLDisplay dpy = eglGetPlatformDisplayEXT(EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, NULL);
  EGLint maj, min;
  if (!eglInitialize(dpy, &maj, &min) || !strstr(eglQueryString(dpy, EGL_EXTENSIONS), "EGL_EXT_image_dma_buf_import")) {
    printf("%s: radeonsi EGL without dma-buf import\n", tag);
    return 1;
  }
  eglBindAPI(EGL_OPENGL_ES_API);
  const EGLint cattr[] = {EGL_CONTEXT_MAJOR_VERSION, 3, EGL_NONE};
  EGLContext ctx = eglCreateContext(dpy, EGL_NO_CONFIG_KHR, EGL_NO_CONTEXT, cattr);
  eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx);
  const EGLint iattr[] = {EGL_WIDTH, (EGLint)w, EGL_HEIGHT, (EGLint)ht, EGL_LINUX_DRM_FOURCC_EXT, DRM_FORMAT_ABGR8888,
                          EGL_DMA_BUF_PLANE0_FD_EXT, handle->data[0], EGL_DMA_BUF_PLANE0_OFFSET_EXT, 0,
                          EGL_DMA_BUF_PLANE0_PITCH_EXT, stride * 4, EGL_NONE};
  EGLImageKHR eimg = eglCreateImageKHR(dpy, EGL_NO_CONTEXT, EGL_LINUX_DMA_BUF_EXT, NULL, iattr);
  if (eimg == EGL_NO_IMAGE_KHR) {
    printf("%s: radeonsi dma-buf import failed: 0x%x\n", tag, eglGetError());
    return 1;
  }
  GLuint tex, fb;
  glGenTextures(1, &tex);
  glBindTexture(GL_TEXTURE_2D, tex);
  glEGLImageTargetTexture2DOES(GL_TEXTURE_2D, eimg);
  glGenFramebuffers(1, &fb);
  glBindFramebuffer(GL_FRAMEBUFFER, fb);
  glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
  if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
    printf("%s: FBO on the imported buffer incomplete\n", tag);
    return 1;
  }
  uint32_t *px = malloc(size);
  glPixelStorei(GL_PACK_ALIGNMENT, 4);
  glReadPixels(0, 0, (GLsizei)w, (GLsizei)ht, GL_RGBA, GL_UNSIGNED_BYTE, px);
  size_t bad_a = 0, first_a = SIZE_MAX;
  for (size_t i = 0; i < (size_t)w * ht; i++)
    if (px[i] != sc_pattern(i % w, i / w, 0x5a000000u)) {
      bad_a++;
      if (first_a == SIZE_MAX) first_a = i;
    }
  printf("%s: RADV wrote, radeonsi read: %zu of %zu pixels wrong", tag, bad_a, (size_t)w * ht);
  if (bad_a) printf(" (first at %zu,%zu: 0x%08x, want 0x%08x)", first_a % w, first_a / w, px[first_a],
                    sc_pattern(first_a % w, first_a / w, 0x5a000000u));
  printf("\n");

  // 3) radeonsi writes pattern B into the same buffer; RADV copies the image out.
  for (size_t i = 0; i < (size_t)w * ht; i++) px[i] = sc_pattern(i % w, i / w, 0xa5000000u);
  glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, (GLsizei)w, (GLsizei)ht, GL_RGBA, GL_UNSIGNED_BYTE, px);
  glFinish();
  memset(map, 0, size);
  ResetCommandBuffer(cb, 0);
  BeginCommandBuffer(cb, &cbbi);
  ib.oldLayout = VK_IMAGE_LAYOUT_GENERAL;
  ib.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
  ib.srcAccessMask = VK_ACCESS_MEMORY_WRITE_BIT;
  ib.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
  CmdPipelineBarrier(cb, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL, 1, &ib);
  CmdCopyImageToBuffer(cb, img, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, buf, 1, &region);
  EndCommandBuffer(cb);
  if (QueueSubmit(q, 1, &si, VK_NULL_HANDLE) || QueueWaitIdle(q)) return 1;
  size_t bad_b = 0;
  for (size_t i = 0; i < (size_t)w * ht; i++) bad_b += map[i] != sc_pattern(i % w, i / w, 0xa5000000u);
  printf("%s: radeonsi wrote, RADV read: %zu of %zu pixels wrong\n", tag, bad_b, (size_t)w * ht);

  DestroyImage(dev, img, NULL);
  DestroyDevice(dev, NULL);
  ad->free(ad, handle);
  return bad_a || bad_b;
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

// The G14's panel and the default desktop size, an unaligned size, and a cursor-sized buffer; each
// through both of libvulkan's paths.
static int swapchain(void) {
  static const uint32_t sizes[][2] = {{2880, 1800}, {1920, 1200}, {1000, 600}, {64, 64}};
  int fails = 0;
  for (size_t s = 0; s < sizeof(sizes) / sizeof(sizes[0]); s++)
    for (int d = 0; d < 2; d++) {
      char name[64];
      sc.w = sizes[s][0];
      sc.h = sizes[s][1];
      sc.deferred = d;
      snprintf(name, sizeof(name), "swapchain %ux%u %s", sc.w, sc.h, d ? "deferred" : "create");
      fails += in_child(swapchain_case, name) != 0;
    }
  return fails;
}

int main(int argc, char **argv) {
  setvbuf(stdout, NULL, _IOLBF, 0);
  if (argc < 3) {
    fprintf(stderr, "usage: %s /dev/dri/renderDNNN /vendor/lib64 [vulkan|gles|gralloc|swapchain ...]\n", argv[0]);
    return 2;
  }
  node = argv[1];
  libdir = argv[2];
  static const struct { const char *name; int (*fn)(void); } parts[] = {
      {"vulkan", vulkan}, {"gles", gles}, {"gralloc", gralloc}, {"swapchain", swapchain}};
  int rc = 0;
  for (size_t i = 0; i < sizeof(parts) / sizeof(parts[0]); i++) {
    int want = argc == 3;
    for (int a = 3; a < argc; a++) want |= !strcmp(argv[a], parts[i].name);
    // swapchain runs its cases in children of its own.
    if (want) rc |= ((parts[i].fn == swapchain ? parts[i].fn() : in_child(parts[i].fn, parts[i].name)) != 0) << i;
  }
  printf("result: %s\n", rc ? "FAIL" : "PASS");
  return rc;
}
