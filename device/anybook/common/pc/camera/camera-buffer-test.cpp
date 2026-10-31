// SPDX-License-Identifier: Apache-2.0
// Disposable VM only: exercise the production HAL domain's allocator/mapper.
// No camera frames, video device access or test-specific SELinux allow rules.
#include <cstdio>
#include <cstring>
#include <hardware/gralloc.h>
#include <ui/GraphicBuffer.h>
#include <utils/StrongPointer.h>

int main() {
    char context[128] = {};
    FILE* file = fopen("/proc/self/attr/current", "r");
    if (!file || !fgets(context, sizeof(context), file)) return 10;
    fclose(file);
    context[strcspn(context, "\n")] = 0;
    if (strcmp(context, "u:r:hal_camera_default:s0")) return 11;
    constexpr uint32_t width = 640, height = 480;
    constexpr uint64_t usage = GRALLOC_USAGE_SW_WRITE_OFTEN | GRALLOC_USAGE_SW_READ_OFTEN;
    auto buffer = android::sp<android::GraphicBuffer>::make(
        width, height, HAL_PIXEL_FORMAT_YCbCr_420_888, 1, usage, "OpenBookCameraBufferTest");
    if (buffer->initCheck() != android::OK) return 20;
    auto imported = android::sp<android::GraphicBuffer>::make(
        buffer->handle, android::GraphicBuffer::CLONE_HANDLE, width, height,
        HAL_PIXEL_FORMAT_YCbCr_420_888, 1, usage, buffer->getStride());
    if (imported->initCheck() != android::OK) return 21;
    android_ycbcr planes = {};
    if (imported->lockYCbCr(GRALLOC_USAGE_SW_WRITE_OFTEN, &planes) != android::OK) return 22;
    if (!planes.y || !planes.cb || !planes.cr || planes.ystride < width ||
        !planes.chroma_step || planes.cstride < (width / 2) * planes.chroma_step) return 23;
    for (uint32_t y = 0; y < height; ++y)
        for (uint32_t x = 0; x < width; ++x)
            static_cast<unsigned char*>(planes.y)[y * planes.ystride + x] = (x + y) % 251;
    for (uint32_t y = 0; y < height / 2; ++y)
        for (uint32_t x = 0; x < width / 2; ++x) {
            static_cast<unsigned char*>(planes.cb)[y * planes.cstride + x * planes.chroma_step] = 97;
            static_cast<unsigned char*>(planes.cr)[y * planes.cstride + x * planes.chroma_step] = 143;
        }
    if (imported->unlock() != android::OK) return 24;
    if (buffer->lockYCbCr(GRALLOC_USAGE_SW_READ_OFTEN, &planes) != android::OK) return 25;
    if (!planes.y || !planes.cb || !planes.cr || planes.ystride < width ||
        !planes.chroma_step || planes.cstride < (width / 2) * planes.chroma_step) return 26;
    for (uint32_t y = 0; y < height; ++y)
        for (uint32_t x = 0; x < width; ++x)
            if (static_cast<unsigned char*>(planes.y)[y * planes.ystride + x] != (x + y) % 251)
                return 27;
    for (uint32_t y = 0; y < height / 2; ++y)
        for (uint32_t x = 0; x < width / 2; ++x)
            if (static_cast<unsigned char*>(planes.cb)[y * planes.cstride + x * planes.chroma_step] != 97 ||
                static_cast<unsigned char*>(planes.cr)[y * planes.cstride + x * planes.chroma_step] != 143)
                return 28;
    if (buffer->unlock() != android::OK) return 29;
    return 0;
}
