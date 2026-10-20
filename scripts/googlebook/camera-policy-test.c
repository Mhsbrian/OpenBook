// SPDX-License-Identifier: Apache-2.0
// Evaluate the compiled policy with libsepol's security server, including MLS
// constraints. TE-only allow queries cannot detect the camera24 category failure.
// Usage: camera-policy-test policy.bin broken|fixed
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sepol/policydb/services.h>

static int failures, checks;

static void check(const char *source, const char *target, const char *class_name,
                  const char *permission, int expected) {
    sepol_security_id_t ssid, tsid;
    sepol_security_class_t cls;
    sepol_access_vector_t bit;
    struct sepol_av_decision decision;
    unsigned int reason = 0;
    if (sepol_context_to_sid(source, strlen(source) + 1, &ssid) ||
        sepol_context_to_sid(target, strlen(target) + 1, &tsid) ||
        sepol_string_to_security_class(class_name, &cls) ||
        sepol_string_to_av_perm(cls, permission, &bit) ||
        sepol_compute_av_reason(ssid, tsid, cls, bit, &decision, &reason)) {
        fprintf(stderr, "Cannot evaluate %s -> %s %s:%s\n",
                source, target, class_name, permission);
        exit(2);
    }
    int allowed = (decision.allowed & bit) == bit;
    ++checks;
    failures += allowed != expected;
    printf("%s %s -> %s %s:%s allowed=%d expected=%d reason=0x%x\n",
           allowed == expected ? "PASS" : "FAIL", source, target, class_name,
           permission, allowed, expected, reason);
}

int main(int argc, char **argv) {
    if (argc != 3 || (strcmp(argv[2], "fixed") && strcmp(argv[2], "broken"))) {
        fprintf(stderr, "usage: %s policy.bin broken|fixed\n", argv[0]);
        return 2;
    }
    int fixed = !strcmp(argv[2], "fixed");
    FILE *file = fopen(argv[1], "rb");
    if (!file || fseek(file, 0, SEEK_END)) return 2;
    long size = ftell(file);
    if (size <= 0 || fseek(file, 0, SEEK_SET)) return 2;
    void *data = malloc((size_t)size);
    if (!data || fread(data, 1, (size_t)size, file) != (size_t)size) return 2;
    fclose(file);
    if (sepol_load_policy(data, (size_t)size)) return 2;
    free(data);

    const char *apps[] = {
        "u:r:untrusted_app:s0:c147,c256,c522,c768", // physical user 10 denial
        "u:r:untrusted_app:s0:c23,c256,c512,c768",  // different app, user 0
        "u:r:priv_app:s0:c512,c768",
    };
    const char *permissions[] = {"read", "write", "getattr", "map"};
    const char *queue = "u:object_r:cameraserver_tmpfs:s0";
    const char *hal_queue = "u:object_r:hal_camera_default_tmpfs:s0";
    const char *hal = "u:r:hal_camera_default:s0";
    const char *server = "u:r:cameraserver:s0";
    for (size_t a = 0; a < sizeof(apps) / sizeof(apps[0]); ++a) {
        check(apps[a], server, "fd", "use", 1);
        for (size_t p = 0; p < sizeof(permissions) / sizeof(permissions[0]); ++p)
            check(apps[a], queue, "file", permissions[p], fixed);
        check(apps[a], queue, "file", "execute", 0);
        check(apps[a], queue, "file", "setattr", 0);
        check(apps[a], hal_queue, "file", "read", 0);
        check(apps[a], hal_queue, "file", "write", 0);
        check(apps[a], "u:object_r:video_device:s0", "chr_file", "read", 0);
        check(apps[a], "u:object_r:video_device:s0", "chr_file", "write", 0);
    }
    for (size_t p = 0; p < sizeof(permissions) / sizeof(permissions[0]); ++p) {
        check("u:r:isolated_app:s0:c1,c2,c512,c768", queue, "file", permissions[p], 0);
        check(hal, hal_queue, "file", permissions[p], 1);
        check(server, hal_queue, "file", permissions[p], 1);
    }
    check(hal, "u:object_r:tmpfs:s0", "file", "write", 0);
    check(hal, "u:object_r:hal_graphics_allocator_service:s0", "service_manager", "find", fixed);
    check(hal, "u:r:hal_graphics_allocator_default:s0", "binder", "call", fixed);
    check(hal, "u:object_r:same_process_hal_file:s0", "file", "execute", 1);
    printf("RESULT mode=%s checks=%d failures=%d\n", argv[2], checks, failures);
    return failures ? 1 : 0;
}
