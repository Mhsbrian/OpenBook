// SPDX-License-Identifier: Apache-2.0
// Vulkan compute microbenchmark (ANAL-296): FP32 FMA throughput and device-memory copy bandwidth, timed with GPU
// timestamps. One source builds for Android (bionic) and Linux (glibc), so one GPU can be measured under two
// drivers: e.g. NVK on NVIDIA's kernel module from Android, and NVIDIA's own driver on the Linux host.
// Shaders come from vk-compute-bench-{fma,copy}.comp through glslangValidator --vn (see vk-compute-bench.sh).
//
// usage: vk-compute-bench LIBRARY [DEVICE_SUBSTRING]
//   LIBRARY: a Vulkan loader or HAL shim exporting vkGetInstanceProcAddr (Linux: libvulkan.so.1; Android test:
//            libvk_hal_shim.so), or an ICD exporting vk_icdGetInstanceProcAddr.
//   DEVICE_SUBSTRING: pick the first physical device whose name contains it (default: the first device).
// Prints one key=value line per result. Not a game benchmark: it shows clocks, issue rate and memory bandwidth.
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>

#include "vk-compute-bench-fma.h"   // const uint32_t fma_spv[]
#include "vk-compute-bench-copy.h"  // const uint32_t copy_spv[]

#define CHECK(x) do { VkResult r_ = (x); if (r_ != VK_SUCCESS) { \
    fprintf(stderr, "%s:%d: %s = %d\n", __FILE__, __LINE__, #x, r_); exit(1); } } while (0)
#define FN(n) static PFN_##n n
FN(vkCreateInstance); FN(vkEnumeratePhysicalDevices); FN(vkGetPhysicalDeviceProperties);
FN(vkGetPhysicalDeviceProperties2); FN(vkGetPhysicalDeviceQueueFamilyProperties);
FN(vkGetPhysicalDeviceMemoryProperties); FN(vkCreateDevice); FN(vkGetDeviceProcAddr); FN(vkGetDeviceQueue);
FN(vkCreateBuffer); FN(vkGetBufferMemoryRequirements); FN(vkAllocateMemory); FN(vkBindBufferMemory);
FN(vkCreateShaderModule); FN(vkCreateDescriptorSetLayout); FN(vkCreatePipelineLayout);
FN(vkCreateComputePipelines); FN(vkCreateDescriptorPool); FN(vkAllocateDescriptorSets);
FN(vkUpdateDescriptorSets); FN(vkCreateCommandPool); FN(vkAllocateCommandBuffers); FN(vkBeginCommandBuffer);
FN(vkEndCommandBuffer); FN(vkResetCommandBuffer); FN(vkCmdBindPipeline); FN(vkCmdBindDescriptorSets);
FN(vkCmdPushConstants); FN(vkCmdDispatch); FN(vkCmdResetQueryPool); FN(vkCmdWriteTimestamp);
FN(vkQueueSubmit); FN(vkQueueWaitIdle); FN(vkCreateQueryPool); FN(vkGetQueryPoolResults);
FN(vkDestroyDevice); FN(vkDestroyInstance);

static VkDevice dev;
static VkPhysicalDeviceMemoryProperties memprops;

static VkBuffer buffer(VkDeviceSize size) {
    VkBufferCreateInfo bi = {VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = size,
                             .usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, .sharingMode = VK_SHARING_MODE_EXCLUSIVE};
    VkBuffer b; CHECK(vkCreateBuffer(dev, &bi, NULL, &b));
    VkMemoryRequirements mr; vkGetBufferMemoryRequirements(dev, b, &mr);
    uint32_t type = UINT32_MAX;
    for (uint32_t i = 0; i < memprops.memoryTypeCount && type == UINT32_MAX; i++)
        if ((mr.memoryTypeBits & (1u << i)) &&
            (memprops.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)) type = i;
    if (type == UINT32_MAX) { fprintf(stderr, "no device-local memory type\n"); exit(1); }
    VkMemoryAllocateInfo ai = {VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, .allocationSize = mr.size, .memoryTypeIndex = type};
    VkDeviceMemory m; CHECK(vkAllocateMemory(dev, &ai, NULL, &m));
    CHECK(vkBindBufferMemory(dev, b, m, 0));
    return b;
}

static VkPipeline pipeline(const uint32_t *spv, size_t bytes, uint32_t nbuf, VkPipelineLayout *layout,
                           VkDescriptorSetLayout *dsl) {
    VkDescriptorSetLayoutBinding b[2];
    for (uint32_t i = 0; i < nbuf; i++)
        b[i] = (VkDescriptorSetLayoutBinding){i, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, NULL};
    VkDescriptorSetLayoutCreateInfo di = {VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO, .bindingCount = nbuf,
                                          .pBindings = b};
    CHECK(vkCreateDescriptorSetLayout(dev, &di, NULL, dsl));
    VkPushConstantRange pc = {VK_SHADER_STAGE_COMPUTE_BIT, 0, 8};
    VkPipelineLayoutCreateInfo li = {VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO, .setLayoutCount = 1,
                                     .pSetLayouts = dsl, .pushConstantRangeCount = 1, .pPushConstantRanges = &pc};
    CHECK(vkCreatePipelineLayout(dev, &li, NULL, layout));
    VkShaderModuleCreateInfo si = {VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO, .codeSize = bytes, .pCode = spv};
    VkShaderModule mod; CHECK(vkCreateShaderModule(dev, &si, NULL, &mod));
    VkComputePipelineCreateInfo ci = {VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
        .stage = {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .stage = VK_SHADER_STAGE_COMPUTE_BIT,
                  .module = mod, .pName = "main"}, .layout = *layout};
    VkPipeline p; CHECK(vkCreateComputePipelines(dev, VK_NULL_HANDLE, 1, &ci, NULL, &p));
    return p;
}

static int cmp(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return (x > y) - (x < y); }

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: %s LIBRARY [DEVICE_SUBSTRING]\n", argv[0]); return 2; }
    void *lib = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!lib) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 1; }
    PFN_vkGetInstanceProcAddr gipa = (PFN_vkGetInstanceProcAddr)dlsym(lib, "vkGetInstanceProcAddr");
    if (!gipa) gipa = (PFN_vkGetInstanceProcAddr)dlsym(lib, "vk_icdGetInstanceProcAddr");
    if (!gipa) { fprintf(stderr, "no vkGetInstanceProcAddr in %s\n", argv[1]); return 1; }
#define IFN(i, n) n = (PFN_##n)gipa(i, #n)
    IFN(NULL, vkCreateInstance);
    VkApplicationInfo app = {VK_STRUCTURE_TYPE_APPLICATION_INFO, .pApplicationName = "vk-compute-bench",
                             .apiVersion = VK_API_VERSION_1_2};
    VkInstanceCreateInfo ici = {VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app};
    VkInstance inst; CHECK(vkCreateInstance(&ici, NULL, &inst));
    IFN(inst, vkEnumeratePhysicalDevices); IFN(inst, vkGetPhysicalDeviceProperties);
    IFN(inst, vkGetPhysicalDeviceProperties2); IFN(inst, vkGetPhysicalDeviceQueueFamilyProperties);
    IFN(inst, vkGetPhysicalDeviceMemoryProperties); IFN(inst, vkCreateDevice); IFN(inst, vkGetDeviceProcAddr);
    IFN(inst, vkDestroyInstance);

    uint32_t n = 16; VkPhysicalDevice pds[16];
    CHECK(vkEnumeratePhysicalDevices(inst, &n, pds));
    VkPhysicalDevice pd = VK_NULL_HANDLE;
    VkPhysicalDeviceDriverProperties drv = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
    VkPhysicalDeviceProperties2 props = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, .pNext = &drv};
    for (uint32_t i = 0; i < n && pd == VK_NULL_HANDLE; i++) {
        vkGetPhysicalDeviceProperties2(pds[i], &props);
        if (argc < 3 || strstr(props.properties.deviceName, argv[2])) pd = pds[i];
    }
    if (pd == VK_NULL_HANDLE) { fprintf(stderr, "no matching device among %u\n", n); return 1; }
    printf("device=%s\ndriver=%s %s\n", props.properties.deviceName, drv.driverName, drv.driverInfo);
    double period = props.properties.limits.timestampPeriod;
    vkGetPhysicalDeviceMemoryProperties(pd, &memprops);

    uint32_t nq = 16; VkQueueFamilyProperties qf[16];
    vkGetPhysicalDeviceQueueFamilyProperties(pd, &nq, qf);
    uint32_t fam = UINT32_MAX;
    for (uint32_t i = 0; i < nq && fam == UINT32_MAX; i++)
        if ((qf[i].queueFlags & VK_QUEUE_COMPUTE_BIT) && qf[i].timestampValidBits) fam = i;
    if (fam == UINT32_MAX) { fprintf(stderr, "no compute queue with timestamps\n"); return 1; }
    float prio = 1.0f;
    VkDeviceQueueCreateInfo qi = {VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO, .queueFamilyIndex = fam,
                                  .queueCount = 1, .pQueuePriorities = &prio};
    VkDeviceCreateInfo dci = {VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, .queueCreateInfoCount = 1, .pQueueCreateInfos = &qi};
    CHECK(vkCreateDevice(pd, &dci, NULL, &dev));
#define DFN(n) n = (PFN_##n)vkGetDeviceProcAddr(dev, #n)
    DFN(vkGetDeviceQueue); DFN(vkCreateBuffer); DFN(vkGetBufferMemoryRequirements); DFN(vkAllocateMemory);
    DFN(vkBindBufferMemory); DFN(vkCreateShaderModule); DFN(vkCreateDescriptorSetLayout);
    DFN(vkCreatePipelineLayout); DFN(vkCreateComputePipelines); DFN(vkCreateDescriptorPool);
    DFN(vkAllocateDescriptorSets); DFN(vkUpdateDescriptorSets); DFN(vkCreateCommandPool);
    DFN(vkAllocateCommandBuffers); DFN(vkBeginCommandBuffer); DFN(vkEndCommandBuffer); DFN(vkResetCommandBuffer);
    DFN(vkCmdBindPipeline); DFN(vkCmdBindDescriptorSets); DFN(vkCmdPushConstants); DFN(vkCmdDispatch);
    DFN(vkCmdResetQueryPool); DFN(vkCmdWriteTimestamp); DFN(vkQueueSubmit); DFN(vkQueueWaitIdle);
    DFN(vkCreateQueryPool); DFN(vkGetQueryPoolResults); DFN(vkDestroyDevice);
    VkQueue q; vkGetDeviceQueue(dev, fam, 0, &q);

    // FMA: 2D grid of 256-thread groups (X stays under the 65,535 minimum limit); 64 FLOP per thread-iteration.
    const uint32_t gx = 4096, gy = 16, iters = 2048;
    const double threads = (double)gx * gy * 256;
    VkBuffer fbuf = buffer((VkDeviceSize)threads * 4);
    // Copy: 256 MiB read plus 256 MiB written per dispatch, vec4 per thread.
    const VkDeviceSize cbytes = 256ull << 20;
    VkBuffer src = buffer(cbytes), dst = buffer(cbytes);
    const uint32_t cx = 4096, cy = (uint32_t)(cbytes / 16 / 256 / cx);

    VkPipelineLayout fl, cl; VkDescriptorSetLayout fd, cd;
    VkPipeline fp = pipeline(fma_spv, sizeof(fma_spv), 1, &fl, &fd);
    VkPipeline cp = pipeline(copy_spv, sizeof(copy_spv), 2, &cl, &cd);
    VkDescriptorPoolSize ps = {VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 3};
    VkDescriptorPoolCreateInfo pi = {VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO, .maxSets = 2, .poolSizeCount = 1,
                                     .pPoolSizes = &ps};
    VkDescriptorPool pool; CHECK(vkCreateDescriptorPool(dev, &pi, NULL, &pool));
    VkDescriptorSet fs, cs;
    VkDescriptorSetAllocateInfo dai = {VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO, .descriptorPool = pool,
                                       .descriptorSetCount = 1, .pSetLayouts = &fd};
    CHECK(vkAllocateDescriptorSets(dev, &dai, &fs));
    dai.pSetLayouts = &cd; CHECK(vkAllocateDescriptorSets(dev, &dai, &cs));
    VkDescriptorBufferInfo bf = {fbuf, 0, VK_WHOLE_SIZE}, bs = {src, 0, VK_WHOLE_SIZE}, bd = {dst, 0, VK_WHOLE_SIZE};
    VkWriteDescriptorSet w[3] = {
        {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstSet = fs, .dstBinding = 0, .descriptorCount = 1,
         .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, .pBufferInfo = &bf},
        {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstSet = cs, .dstBinding = 0, .descriptorCount = 1,
         .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, .pBufferInfo = &bs},
        {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstSet = cs, .dstBinding = 1, .descriptorCount = 1,
         .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, .pBufferInfo = &bd}};
    vkUpdateDescriptorSets(dev, 3, w, 0, NULL);

    VkCommandPoolCreateInfo cpi = {VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT, .queueFamilyIndex = fam};
    VkCommandPool cpool; CHECK(vkCreateCommandPool(dev, &cpi, NULL, &cpool));
    VkCommandBufferAllocateInfo cai = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .commandPool = cpool,
                                       .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
    VkCommandBuffer cb; CHECK(vkAllocateCommandBuffers(dev, &cai, &cb));
    VkQueryPoolCreateInfo qpi = {VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO, .queryType = VK_QUERY_TYPE_TIMESTAMP,
                                 .queryCount = 2};
    VkQueryPool qp; CHECK(vkCreateQueryPool(dev, &qpi, NULL, &qp));

    enum { WARMUP = 20, RUNS = 30 };
    for (int test = 0; test < 2; test++) {
        double ns[RUNS];
        for (int r = 0; r < WARMUP + RUNS; r++) {
            CHECK(vkResetCommandBuffer(cb, 0));
            VkCommandBufferBeginInfo bi = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
                                           .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
            CHECK(vkBeginCommandBuffer(cb, &bi));
            vkCmdResetQueryPool(cb, qp, 0, 2);
            uint32_t pcv[2] = {iters, cx};
            if (test == 0) {
                vkCmdBindPipeline(cb, VK_PIPELINE_BIND_POINT_COMPUTE, fp);
                vkCmdBindDescriptorSets(cb, VK_PIPELINE_BIND_POINT_COMPUTE, fl, 0, 1, &fs, 0, NULL);
                vkCmdPushConstants(cb, fl, VK_SHADER_STAGE_COMPUTE_BIT, 0, 8, pcv);
            } else {
                vkCmdBindPipeline(cb, VK_PIPELINE_BIND_POINT_COMPUTE, cp);
                vkCmdBindDescriptorSets(cb, VK_PIPELINE_BIND_POINT_COMPUTE, cl, 0, 1, &cs, 0, NULL);
                vkCmdPushConstants(cb, cl, VK_SHADER_STAGE_COMPUTE_BIT, 0, 8, pcv);
            }
            vkCmdWriteTimestamp(cb, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, qp, 0);
            if (test == 0) vkCmdDispatch(cb, gx, gy, 1); else vkCmdDispatch(cb, cx, cy, 1);
            vkCmdWriteTimestamp(cb, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, qp, 1);
            CHECK(vkEndCommandBuffer(cb));
            VkSubmitInfo si = {VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cb};
            CHECK(vkQueueSubmit(q, 1, &si, VK_NULL_HANDLE));
            CHECK(vkQueueWaitIdle(q));
            uint64_t ts[2];
            CHECK(vkGetQueryPoolResults(dev, qp, 0, 2, sizeof ts, ts, 8,
                                        VK_QUERY_RESULT_64_BIT | VK_QUERY_RESULT_WAIT_BIT));
            if (r >= WARMUP) ns[r - WARMUP] = (double)(ts[1] - ts[0]) * period;
        }
        qsort(ns, RUNS, sizeof ns[0], cmp);
        if (test == 0) {
            double flop = threads * iters * 64.0;
            printf("fp32_tflops_best=%.2f\nfp32_tflops_median=%.2f\nfma_ms_median=%.3f\n",
                   flop / ns[0] / 1e3, flop / ns[RUNS / 2] / 1e3, ns[RUNS / 2] / 1e6);
        } else {
            double bytes = 2.0 * (double)cbytes;
            printf("copy_gbps_best=%.1f\ncopy_gbps_median=%.1f\ncopy_ms_median=%.3f\n",
                   bytes / ns[0], bytes / ns[RUNS / 2], ns[RUNS / 2] / 1e6);
        }
    }
    vkDestroyDevice(dev, NULL);
    vkDestroyInstance(inst, NULL);
    return 0;
}
