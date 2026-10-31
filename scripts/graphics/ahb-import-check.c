// SPDX-License-Identifier: Apache-2.0
// Headless EGL import probe: no display surface, app launch, or user content.
#include <android/hardware_buffer.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static unsigned char clamp(float value) {
    return value < 0 ? 0 : value > 255 ? 255 : (unsigned char)(value + 0.5f);
}

static void expected(unsigned x, unsigned y, unsigned char rgb[3]) {
    float luma = y < 4 ? 64 : 192;
    float u = x < 4 ? -80 : 80;
    float v = -u;
    rgb[0] = clamp(luma + 1.402f * v);
    rgb[1] = clamp(luma - 0.344136f * u - 0.714136f * v);
    rgb[2] = clamp(luma + 1.772f * u);
}

static int fill(AHardwareBuffer *buffer, const AHardwareBuffer_Desc *desc) {
    AHardwareBuffer_Planes planes;
    int rc = AHardwareBuffer_lockPlanes(buffer, AHARDWAREBUFFER_USAGE_CPU_WRITE_OFTEN,
                                       -1, NULL, &planes);
    if (rc) return rc;
    for (unsigned p = 0; p < planes.planeCount; ++p) {
        unsigned width = desc->width, height = desc->height;
        if (p) { width /= 2; height /= 2; }
        for (unsigned y = 0; y < height; ++y) {
            unsigned char *row = (unsigned char *)planes.planes[p].data + y * planes.planes[p].rowStride;
            for (unsigned x = 0; x < width; ++x) {
                unsigned char *pixel = row + x * planes.planes[p].pixelStride;
                if (desc->format == AHARDWAREBUFFER_FORMAT_R8G8B8A8_UNORM) {
                    expected(x * 8 / width, y * 8 / height, pixel);
                    pixel[3] = 255;
                } else if (p == 0) {
                    *pixel = y < height / 2 ? 64 : 192;
                } else {
                    // lockPlanes exposes Y, Cb, Cr even when physical storage is Y, V, U.
                    *pixel = ((x < width / 2) == (p == 1)) ? 48 : 208;
                }
            }
        }
    }
    return AHardwareBuffer_unlock(buffer, NULL);
}

static GLuint shader(GLenum type, const char *source) {
    GLuint id = glCreateShader(type);
    glShaderSource(id, 1, &source, NULL);
    glCompileShader(id);
    GLint ok;
    glGetShaderiv(id, GL_COMPILE_STATUS, &ok);
    if (!ok) { fprintf(stderr, "shader compile failed\n"); exit(2); }
    return id;
}

static int check_pixels(void) {
    const char *vs = "attribute vec2 pos; varying vec2 uv; void main() {"
                     "uv=(pos+1.0)*0.5; gl_Position=vec4(pos,0.0,1.0);}";
    const char *fs = "#extension GL_OES_EGL_image_external : require\n"
                     "precision mediump float; varying vec2 uv; uniform samplerExternalOES tex;"
                     "void main() {gl_FragColor=texture2D(tex,uv);}";
    GLuint vertex = shader(GL_VERTEX_SHADER, vs), fragment = shader(GL_FRAGMENT_SHADER, fs);
    GLuint program = glCreateProgram();
    glAttachShader(program, vertex); glAttachShader(program, fragment);
    glBindAttribLocation(program, 0, "pos");
    glLinkProgram(program);
    GLint linked;
    glGetProgramiv(program, GL_LINK_STATUS, &linked);
    if (!linked) { fprintf(stderr, "shader link failed\n"); exit(2); }
    glUseProgram(program);
    glUniform1i(glGetUniformLocation(program, "tex"), 0);
    GLuint output, fbo;
    glGenTextures(1, &output); glBindTexture(GL_TEXTURE_2D, output);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 8, 8, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    glGenFramebuffers(1, &fbo); glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, output, 0);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) exit(2);
    glViewport(0, 0, 8, 8);
    const GLfloat vertices[] = {-1,-1, 1,-1, -1,1, 1,1};
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, vertices);
    glEnableVertexAttribArray(0);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    unsigned char pixels[8 * 8 * 4];
    glReadPixels(0, 0, 8, 8, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    int ok = glGetError() == GL_NO_ERROR;
    for (unsigned y = 1; y <= 6; y += 5) {
        for (unsigned x = 1; x <= 6; x += 5) {
            unsigned char rgb[3]; expected(x, y, rgb);
            const unsigned char *pixel = pixels + (y * 8 + x) * 4;
            printf(" pixel[%u,%u]=%u,%u,%u", x, y, pixel[0], pixel[1], pixel[2]);
            for (unsigned c = 0; c < 3; ++c) ok &= abs((int)pixel[c] - rgb[c]) <= 4;
        }
    }
    glDisableVertexAttribArray(0); glUseProgram(0);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glDeleteFramebuffers(1, &fbo); glDeleteTextures(1, &output);
    glDeleteProgram(program); glDeleteShader(vertex); glDeleteShader(fragment);
    printf(" pixels=%s\n", ok ? "PASS" : "FAIL");
    return ok;
}

int main(int argc, char **argv) {
    unsigned width = 384, height = 640;
    if (argc == 3) {
        char *end_w, *end_h;
        unsigned long w = strtoul(argv[1], &end_w, 10), h = strtoul(argv[2], &end_h, 10);
        if (*end_w || *end_h || w < 4 || h < 4 || w > 4096 || h > 4096 || (w % 2) || (h % 2)) {
            fprintf(stderr, "width and height must be even, between 4 and 4096\n");
            return 2;
        }
        width = (unsigned)w; height = (unsigned)h;
    } else if (argc != 1) {
        fprintf(stderr, "usage: ahb-import-check [WIDTH HEIGHT]\n");
        return 2;
    }
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    EGLint major, minor, count;
    EGLConfig config;
    const EGLint config_attrs[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE};
    const EGLint context_attrs[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    if (!eglInitialize(display, &major, &minor) ||
        !eglChooseConfig(display, config_attrs, &config, 1, &count) || count < 1) {
        fprintf(stderr, "EGL setup failed: 0x%x\n", eglGetError());
        return 2;
    }
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attrs);
    if (context == EGL_NO_CONTEXT ||
        !eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, context)) {
        fprintf(stderr, "EGL context failed: 0x%x\n", eglGetError());
        return 2;
    }
    PFNEGLGETNATIVECLIENTBUFFERANDROIDPROC client_buffer =
        (PFNEGLGETNATIVECLIENTBUFFERANDROIDPROC)eglGetProcAddress("eglGetNativeClientBufferANDROID");
    PFNEGLCREATEIMAGEKHRPROC create_image =
        (PFNEGLCREATEIMAGEKHRPROC)eglGetProcAddress("eglCreateImageKHR");
    PFNEGLDESTROYIMAGEKHRPROC destroy_image =
        (PFNEGLDESTROYIMAGEKHRPROC)eglGetProcAddress("eglDestroyImageKHR");
    PFNGLEGLIMAGETARGETTEXTURE2DOESPROC bind_image =
        (PFNGLEGLIMAGETARGETTEXTURE2DOESPROC)eglGetProcAddress("glEGLImageTargetTexture2DOES");
    if (!client_buffer || !create_image || !destroy_image || !bind_image) return 2;
    printf("renderer=%s\n", glGetString(GL_RENDERER));
    const struct { const char *name; uint32_t format; } formats[] = {
        {"RGBA8888", AHARDWAREBUFFER_FORMAT_R8G8B8A8_UNORM},
        {"YV12", 0x32315659},
        {"YUV420", AHARDWAREBUFFER_FORMAT_Y8Cb8Cr8_420},
    };
    int failures = 0;
    for (unsigned i = 0; i < sizeof(formats) / sizeof(formats[0]); ++i) {
        AHardwareBuffer_Desc desc = {.width = width, .height = height, .layers = 1,
            .format = formats[i].format,
            .usage = AHARDWAREBUFFER_USAGE_GPU_SAMPLED_IMAGE |
                     AHARDWAREBUFFER_USAGE_CPU_WRITE_OFTEN};
        AHardwareBuffer *buffer = NULL;
        int result = AHardwareBuffer_allocate(&desc, &buffer);
        if (result) {
            printf("%s allocate=%d FAIL\n", formats[i].name, result);
            ++failures;
            continue;
        }
        AHardwareBuffer_describe(buffer, &desc);
        if (fill(buffer, &desc)) {
            fprintf(stderr, "%s lock/fill failed\n", formats[i].name);
            AHardwareBuffer_release(buffer);
            ++failures;
            continue;
        }
        const EGLint image_attrs[] = {EGL_IMAGE_PRESERVED_KHR, EGL_TRUE, EGL_NONE};
        EGLImageKHR image = create_image(display, EGL_NO_CONTEXT, EGL_NATIVE_BUFFER_ANDROID,
                                         client_buffer(buffer), image_attrs);
        EGLint error = eglGetError();
        GLenum gl_error = GL_NO_ERROR;
        int pixels_ok = 0;
        if (image != EGL_NO_IMAGE_KHR) {
            GLuint texture;
            glGenTextures(1, &texture);
            glBindTexture(GL_TEXTURE_EXTERNAL_OES, texture);
            glTexParameteri(GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
            glTexParameteri(GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
            glTexParameteri(GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
            glTexParameteri(GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
            bind_image(GL_TEXTURE_EXTERNAL_OES, image);
            gl_error = glGetError();
            if (gl_error == GL_NO_ERROR) pixels_ok = check_pixels();
            glDeleteTextures(1, &texture);
            destroy_image(display, image);
        }
        int ok = image != EGL_NO_IMAGE_KHR && error == EGL_SUCCESS && gl_error == GL_NO_ERROR && pixels_ok;
        printf("%s %ux%u stride=%u image=%s egl=0x%x gl=0x%x %s\n",
               formats[i].name, desc.width, desc.height, desc.stride,
               image == EGL_NO_IMAGE_KHR ? "null" : "valid", error, gl_error, ok ? "PASS" : "FAIL");
        failures += !ok;
        AHardwareBuffer_release(buffer);
    }
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(display, context);
    eglTerminate(display);
    return failures ? 1 : 0;
}
