// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Checks minigbm's amdgpu backend (amdgpu.c + AnyBook's dri_gbm.c) on a real AMD GPU, on Linux.
// Built against AOSP's minigbm sources by scripts/minigbm-amdgpu-host-test.sh.
//
// Driver A plays the gralloc allocator, driver B (its own fd) plays a mapper in another process:
// buffers cross between them only as dma-buf fds plus the metadata gralloc would carry.
//   1. allocations for typical gralloc usages: modifier, planes, strides, kernel swizzle mode
//   2. GPU renders a quadrant pattern into a tiled buffer (EGL dma-buf import), B maps and reads it
//   3. B writes a pattern through a mapping of a tiled buffer, the GPU samples it back
//   4. CPU writes a linear (SW) buffer, the GPU reads it
//   5. a mapping still live when its buffer is destroyed, and a buffer imported twice
//   6. the same with debug.minigbm.amdgpu.linear_only=1
//
// usage: minigbm-amdgpu-host-test /dev/dri/renderDNNN
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <amdgpu_drm.h>
#include <drm_fourcc.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <xf86drm.h>

#include "drv.h"
#include "drv_priv.h"

static int failures;
#define CHECK(cond, ...)                                                                           \
	do {                                                                                       \
		if (!(cond)) {                                                                     \
			failures++;                                                                \
			printf("  FAIL %s:%d: ", __func__, __LINE__);                              \
			printf(__VA_ARGS__);                                                       \
			printf("\n");                                                              \
		}                                                                                  \
	} while (0)

static const char *node;

static struct driver *open_driver(void)
{
	int fd = open(node, O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		perror(node);
		exit(2);
	}
	struct driver *drv = drv_create(fd, NULL);
	if (!drv) {
		printf("drv_create(%s) failed\n", node);
		exit(2);
	}
	return drv;
}

static void close_driver(struct driver *drv)
{
	int fd = drv_get_fd(drv);
	drv_destroy(drv);
	close(fd);
}

// Kernel-side layout of a GEM handle: AMDGPU_TILING_SWIZZLE_MODE (0 = linear) on GFX9+.
static int swizzle_mode(struct driver *drv, uint32_t handle)
{
	struct drm_amdgpu_gem_metadata md = { .handle = handle,
					      .op = AMDGPU_GEM_METADATA_OP_GET_METADATA };
	if (drmCommandWriteRead(drv_get_fd(drv), DRM_AMDGPU_GEM_METADATA, &md, sizeof(md)))
		return -1;
	return (int)AMDGPU_TILING_GET(md.data.tiling_info, SWIZZLE_MODE);
}

static void describe(struct bo *bo, const char *name)
{
	printf("  %-26s %4ux%-4u %.4s mod=0x%016" PRIx64 " planes=%zu", name, drv_bo_get_width(bo),
	       drv_bo_get_height(bo), (const char *)&bo->meta.format,
	       drv_bo_get_format_modifier(bo), drv_bo_get_num_planes(bo));
	for (size_t p = 0; p < drv_bo_get_num_planes(bo); p++)
		printf(" [stride=%u off=%u]", drv_bo_get_plane_stride(bo, p),
		       drv_bo_get_plane_offset(bo, p));
	printf(" size=%zu swizzle=%d tiling=%u\n", drv_bo_get_total_size(bo),
	       swizzle_mode(bo->drv, bo->handle.u32), bo->meta.tiling);
}

// Hand a buffer to another driver as gralloc would: fds plus the recorded layout.
static struct bo *cross(struct driver *to, struct bo *bo)
{
	struct drv_import_fd_data d = { 0 };
	d.width = drv_bo_get_width(bo);
	d.height = drv_bo_get_height(bo);
	d.format = drv_bo_get_format(bo);
	d.format_modifier = drv_bo_get_format_modifier(bo);
	d.use_flags = drv_bo_get_use_flags(bo);
	d.tiling = drv_bo_get_tiling(bo);
	for (size_t p = 0; p < drv_bo_get_num_planes(bo); p++) {
		d.fds[p] = drv_bo_get_plane_fd(bo, p);
		d.strides[p] = drv_bo_get_plane_stride(bo, p);
		d.offsets[p] = drv_bo_get_plane_offset(bo, p);
	}
	struct bo *out = drv_bo_import(to, &d);
	for (size_t p = 0; p < drv_bo_get_num_planes(bo); p++)
		close(d.fds[p]);
	return out;
}

// ---- EGL/GLES on the same GPU ------------------------------------------------------------
static EGLDisplay dpy;
static PFNGLEGLIMAGETARGETTEXTURE2DOESPROC image_target_texture;
static PFNEGLCREATEIMAGEKHRPROC create_image;

static void egl_init(void)
{
	PFNEGLGETPLATFORMDISPLAYEXTPROC get_display =
	    (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
	dpy = get_display(EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, NULL);
	EGLint major, minor;
	if (!eglInitialize(dpy, &major, &minor)) {
		printf("eglInitialize failed\n");
		exit(2);
	}
	eglBindAPI(EGL_OPENGL_ES_API);
	const EGLint ctx_attribs[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
	EGLContext ctx = eglCreateContext(dpy, EGL_NO_CONFIG_KHR, EGL_NO_CONTEXT, ctx_attribs);
	if (ctx == EGL_NO_CONTEXT || !eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx)) {
		printf("EGL context failed: 0x%x\n", eglGetError());
		exit(2);
	}
	image_target_texture = (PFNGLEGLIMAGETARGETTEXTURE2DOESPROC)eglGetProcAddress(
	    "glEGLImageTargetTexture2DOES");
	create_image = (PFNEGLCREATEIMAGEKHRPROC)eglGetProcAddress("eglCreateImageKHR");
	printf("EGL %d.%d, GL_RENDERER: %s\n", major, minor, glGetString(GL_RENDERER));
}

// Import a buffer as an FBO color attachment; returns the FBO (texture and image leak per test).
static GLuint fbo_for(struct bo *bo)
{
	static const EGLint fd_attr[] = { EGL_DMA_BUF_PLANE0_FD_EXT, EGL_DMA_BUF_PLANE1_FD_EXT,
					  EGL_DMA_BUF_PLANE2_FD_EXT, EGL_DMA_BUF_PLANE3_FD_EXT };
	static const EGLint off_attr[] = { EGL_DMA_BUF_PLANE0_OFFSET_EXT,
					   EGL_DMA_BUF_PLANE1_OFFSET_EXT,
					   EGL_DMA_BUF_PLANE2_OFFSET_EXT,
					   EGL_DMA_BUF_PLANE3_OFFSET_EXT };
	static const EGLint pitch_attr[] = { EGL_DMA_BUF_PLANE0_PITCH_EXT, EGL_DMA_BUF_PLANE1_PITCH_EXT,
					     EGL_DMA_BUF_PLANE2_PITCH_EXT,
					     EGL_DMA_BUF_PLANE3_PITCH_EXT };
	static const EGLint lo_attr[] = { EGL_DMA_BUF_PLANE0_MODIFIER_LO_EXT,
					  EGL_DMA_BUF_PLANE1_MODIFIER_LO_EXT,
					  EGL_DMA_BUF_PLANE2_MODIFIER_LO_EXT,
					  EGL_DMA_BUF_PLANE3_MODIFIER_LO_EXT };
	static const EGLint hi_attr[] = { EGL_DMA_BUF_PLANE0_MODIFIER_HI_EXT,
					  EGL_DMA_BUF_PLANE1_MODIFIER_HI_EXT,
					  EGL_DMA_BUF_PLANE2_MODIFIER_HI_EXT,
					  EGL_DMA_BUF_PLANE3_MODIFIER_HI_EXT };
	EGLint a[64];
	int n = 0, fds[DRV_MAX_PLANES];
	uint64_t mod = drv_bo_get_format_modifier(bo);
	a[n++] = EGL_WIDTH;
	a[n++] = drv_bo_get_width(bo);
	a[n++] = EGL_HEIGHT;
	a[n++] = drv_bo_get_height(bo);
	a[n++] = EGL_LINUX_DRM_FOURCC_EXT;
	a[n++] = drv_get_standard_fourcc(drv_bo_get_format(bo));
	for (size_t p = 0; p < drv_bo_get_num_planes(bo); p++) {
		fds[p] = drv_bo_get_plane_fd(bo, p);
		a[n++] = fd_attr[p];
		a[n++] = fds[p];
		a[n++] = off_attr[p];
		a[n++] = drv_bo_get_plane_offset(bo, p);
		a[n++] = pitch_attr[p];
		a[n++] = drv_bo_get_plane_stride(bo, p);
		if (mod != DRM_FORMAT_MOD_INVALID) {
			a[n++] = lo_attr[p];
			a[n++] = (EGLint)(mod & 0xffffffff);
			a[n++] = hi_attr[p];
			a[n++] = (EGLint)(mod >> 32);
		}
	}
	a[n++] = EGL_NONE;
	EGLImageKHR img = create_image(dpy, EGL_NO_CONTEXT, EGL_LINUX_DMA_BUF_EXT, NULL, a);
	for (size_t p = 0; p < drv_bo_get_num_planes(bo); p++)
		close(fds[p]);
	if (img == EGL_NO_IMAGE_KHR) {
		printf("  eglCreateImageKHR failed: 0x%x\n", eglGetError());
		return 0;
	}
	GLuint tex, fbo;
	glGenTextures(1, &tex);
	glBindTexture(GL_TEXTURE_2D, tex);
	image_target_texture(GL_TEXTURE_2D, img);
	glGenFramebuffers(1, &fbo);
	glBindFramebuffer(GL_FRAMEBUFFER, fbo);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
	if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
		printf("  FBO incomplete\n");
		return 0;
	}
	return fbo;
}

// Quadrant pattern in ABGR8888 (bytes R,G,B,A in memory).
static const uint32_t quad_color[4] = { 0xff0000ffu, 0xff00ff00u, 0xffff0000u, 0x80ffffffu };
static int quadrant(uint32_t x, uint32_t y, uint32_t w, uint32_t h)
{
	return (x >= w / 2) + 2 * (y >= h / 2);
}

static void gl_draw_quadrants(uint32_t w, uint32_t h)
{
	glViewport(0, 0, w, h);
	glEnable(GL_SCISSOR_TEST);
	for (int q = 0; q < 4; q++) {
		uint32_t c = quad_color[q];
		// GL window y=0 is the first row in memory for an FBO texture.
		glScissor((q & 1) ? w / 2 : 0, (q & 2) ? h / 2 : 0, w / 2, h / 2);
		glClearColor((c & 0xff) / 255.f, ((c >> 8) & 0xff) / 255.f, ((c >> 16) & 0xff) / 255.f,
			     (c >> 24) / 255.f);
		glClear(GL_COLOR_BUFFER_BIT);
	}
	glDisable(GL_SCISSOR_TEST);
	glFinish();
}

static int check_rows(const uint8_t *base, uint32_t stride, uint32_t w, uint32_t h, const char *what)
{
	int bad = 0;
	for (uint32_t y = 0; y < h; y += 7)
		for (uint32_t x = 0; x < w; x += 5) {
			uint32_t v;
			memcpy(&v, base + (size_t)y * stride + x * 4, 4);
			if (v != quad_color[quadrant(x, y, w, h)] && bad++ < 3)
				printf("  %s: (%u,%u) = 0x%08x, want 0x%08x\n", what, x, y, v,
				       quad_color[quadrant(x, y, w, h)]);
		}
	return bad;
}

static void fill_rows(uint8_t *base, uint32_t stride, uint32_t w, uint32_t h)
{
	for (uint32_t y = 0; y < h; y++)
		for (uint32_t x = 0; x < w; x++)
			memcpy(base + (size_t)y * stride + x * 4, &quad_color[quadrant(x, y, w, h)], 4);
}

static int gl_check_quadrants(struct bo *bo)
{
	uint32_t w = drv_bo_get_width(bo), h = drv_bo_get_height(bo);
	GLuint fbo = fbo_for(bo);
	if (!fbo)
		return -1;
	uint8_t *px = malloc((size_t)w * h * 4);
	glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, px);
	int bad = check_rows(px, w * 4, w, h, "glReadPixels");
	free(px);
	return bad;
}

static void *map(struct bo *bo, uint32_t flags, struct mapping **m, uint32_t *stride)
{
	struct rectangle r = { 0, 0, drv_bo_get_width(bo), drv_bo_get_height(bo) };
	void *addr = drv_bo_map(bo, &r, flags, m, 0);
	if (addr != MAP_FAILED)
		*stride = (*m)->vma->map_strides[0];
	return addr;
}

// ---- tests -------------------------------------------------------------------------------
struct alloc_case {
	const char *name;
	uint32_t format, w, h;
	uint64_t use;
	int want_tiled; // 1: GPU-only usage, expect the driver's tiled layout unless linear-only
};

static const uint64_t GPU = BO_USE_RENDERING | BO_USE_TEXTURE;
static const uint64_t SW = BO_USE_SW_READ_OFTEN | BO_USE_SW_WRITE_OFTEN;
static const struct alloc_case cases[] = {
	{ "app window (GPU+scanout)", DRM_FORMAT_ABGR8888, 1920, 1080, GPU | BO_USE_SCANOUT, 1 },
	{ "client target 2880x1800", DRM_FORMAT_XBGR8888, 2880, 1800, GPU | BO_USE_SCANOUT, 1 },
	{ "texture RGB565", DRM_FORMAT_RGB565, 512, 512, GPU, 1 },
	{ "HDR ABGR2101010", DRM_FORMAT_ABGR2101010, 1920, 1080, GPU | BO_USE_SCANOUT, 1 },
	{ "FP16 ABGR16161616F", DRM_FORMAT_ABGR16161616F, 1920, 1080, GPU, 1 },
	{ "CPU-drawn ABGR8888", DRM_FORMAT_ABGR8888, 1280, 720, SW | BO_USE_TEXTURE, 0 },
	{ "camera NV12", DRM_FORMAT_NV12, 1920, 1080,
	  BO_USE_CAMERA_WRITE | BO_USE_CAMERA_READ | BO_USE_TEXTURE, 0 },
	{ "video decode P010", DRM_FORMAT_P010, 3840, 2160,
	  BO_USE_HW_VIDEO_DECODER | BO_USE_TEXTURE | BO_USE_SCANOUT, 0 },
	{ "YV12 (CPU)", DRM_FORMAT_YVU420_ANDROID, 640, 480, SW | BO_USE_TEXTURE, 0 },
	{ "BLOB R8 64 KiB", DRM_FORMAT_R8, 65536, 1, SW | BO_USE_GPU_DATA_BUFFER, 0 },
};

static void test_allocations(struct driver *a, int linear_only)
{
	printf("allocations (backend %s%s):\n", drv_get_name(a), linear_only ? ", linear-only" : "");
	for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
		const struct alloc_case *c = &cases[i];
		struct bo *bo = drv_bo_create(a, c->w, c->h, c->format, c->use);
		CHECK(bo, "%s: drv_bo_create failed", c->name);
		if (!bo)
			continue;
		describe(bo, c->name);
		int sw = swizzle_mode(a, bo->handle.u32);
		uint64_t mod = drv_bo_get_format_modifier(bo);
		if (c->want_tiled && !linear_only)
			CHECK(sw > 0 || (mod != DRM_FORMAT_MOD_LINEAR && mod != DRM_FORMAT_MOD_INVALID),
			      "%s: expected a tiled layout (swizzle %d, mod 0x%" PRIx64 ")", c->name, sw,
			      mod);
		else
			CHECK(mod == DRM_FORMAT_MOD_LINEAR && sw <= 0,
			      "%s: expected linear (swizzle %d, mod 0x%" PRIx64 ")", c->name, sw, mod);
		drv_bo_destroy(bo);
	}
}

// 2 + 3: GPU <-> CPU through a mapping of a GPU-only (tiled) buffer, mapped in driver B.
static void test_tiled_roundtrip(struct driver *a, struct driver *b)
{
	const uint32_t w = 1000, h = 600; // not a multiple of any tile size
	printf("tiled round trip %ux%u:\n", w, h);
	struct bo *bo = drv_bo_create(a, w, h, DRM_FORMAT_ABGR8888, GPU | BO_USE_SCANOUT);
	CHECK(bo, "create");
	if (!bo)
		return;
	describe(bo, "GPU buffer");
	GLuint fbo = fbo_for(bo);
	CHECK(fbo, "EGL import of the minigbm buffer");
	if (fbo)
		gl_draw_quadrants(w, h);

	struct bo *imp = cross(b, bo);
	CHECK(imp, "import into driver B");
	if (imp) {
		struct mapping *m;
		uint32_t stride = 0;
		uint8_t *p = map(imp, BO_MAP_READ, &m, &stride);
		CHECK(p != MAP_FAILED, "map READ in driver B");
		if (p != MAP_FAILED) {
			printf("  B mapped it: map stride %u (buffer stride %u)\n", stride,
			       drv_bo_get_plane_stride(imp, 0));
			CHECK(!check_rows(p, stride, w, h, "GPU->map"),
			      "GPU-rendered quadrants read back through the mapping");
			drv_bo_unmap(imp, m);
		}
		// Clear on the GPU first, so that a write-back that never lands can't pass on step 2's data.
		if (fbo) {
			glBindFramebuffer(GL_FRAMEBUFFER, fbo);
			glClearColor(0, 0, 0, 0);
			glClear(GL_COLOR_BUFFER_BIT);
			glFinish();
		}
		p = map(imp, BO_MAP_WRITE, &m, &stride);
		CHECK(p != MAP_FAILED, "map WRITE in driver B");
		if (p != MAP_FAILED) {
			fill_rows(p, stride, w, h);
			drv_bo_unmap(imp, m);
			CHECK(gl_check_quadrants(bo) == 0, "map->GPU: pattern written through the mapping");
		}
		drv_bo_destroy(imp);
	}
	drv_bo_destroy(bo);
}

// 4: CPU-written linear buffer sampled by the GPU.
static void test_linear_roundtrip(struct driver *a, struct driver *b)
{
	const uint32_t w = 777, h = 333;
	printf("linear round trip %ux%u:\n", w, h);
	struct bo *bo = drv_bo_create(a, w, h, DRM_FORMAT_ABGR8888, SW | BO_USE_TEXTURE);
	CHECK(bo, "create");
	if (!bo)
		return;
	describe(bo, "CPU buffer");
	struct bo *imp = cross(b, bo);
	CHECK(imp, "import into driver B");
	if (imp) {
		struct mapping *m;
		uint32_t stride = 0;
		uint8_t *p = map(imp, BO_MAP_WRITE, &m, &stride);
		CHECK(p != MAP_FAILED, "map WRITE");
		if (p != MAP_FAILED) {
			CHECK(stride == drv_bo_get_plane_stride(imp, 0), "linear map stride %u", stride);
			fill_rows(p, stride, w, h);
			drv_bo_flush_or_unmap(imp, m);
			CHECK(gl_check_quadrants(bo) == 0, "CPU->GPU on the linear buffer");
		}
		drv_bo_destroy(imp);
	}
	drv_bo_destroy(bo);
}

// 5: lifetimes.
static void test_lifetimes(struct driver *a, struct driver *b)
{
	printf("lifetimes:\n");
	struct bo *bo = drv_bo_create(a, 256, 256, DRM_FORMAT_ABGR8888, GPU);
	CHECK(bo, "create");
	if (!bo)
		return;
	struct bo *i1 = cross(b, bo), *i2 = cross(b, bo);
	CHECK(i1 && i2 && i1->handle.u32 == i2->handle.u32, "double import shares the handle");
	if (i1 && i2) {
		struct mapping *m;
		uint32_t stride;
		CHECK(map(i1, BO_MAP_READ, &m, &stride) != MAP_FAILED, "map first import");
		drv_bo_destroy(i1); // mapping still live: drv_bo_mapping_destroy must not touch freed state
		void *p = map(i2, BO_MAP_READ, &m, &stride);
		CHECK(p != MAP_FAILED, "map second import after the first is destroyed");
		if (p != MAP_FAILED)
			drv_bo_unmap(i2, m);
		drv_bo_destroy(i2); // closes the shared handle
		printf("  ok: double import, destroy with a live mapping\n");
	}
	drv_bo_destroy(bo);
}

int main(int argc, char **argv)
{
	if (argc != 2) {
		fprintf(stderr, "usage: %s /dev/dri/renderDNNN\n", argv[0]);
		return 2;
	}
	node = argv[1];
	setvbuf(stdout, NULL, _IOLBF, 0);
	egl_init();

	for (int linear_only = 0; linear_only < 2; linear_only++) {
		if (linear_only) {
			setenv("debug.minigbm.amdgpu.linear_only", "1", 1);
			printf("\n== debug.minigbm.amdgpu.linear_only=1\n");
		}
		struct driver *a = open_driver(), *b = open_driver();
		CHECK(!strcmp(drv_get_name(a), "amdgpu"), "backend is %s", drv_get_name(a));
		test_allocations(a, linear_only);
		test_tiled_roundtrip(a, b);
		test_linear_roundtrip(a, b);
		test_lifetimes(a, b);
		close_driver(b);
		close_driver(a);
	}

	printf("\nresult: %s (%d failure%s)\n", failures ? "FAIL" : "PASS", failures,
	       failures == 1 ? "" : "s");
	return failures ? 1 : 0;
}
