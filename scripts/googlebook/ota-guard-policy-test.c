// SPDX-License-Identifier: Apache-2.0
// Compare full-context production and VM-harness access without loading policy.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sepol/policydb/services.h>

static unsigned failures;

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
    failures += allowed != expected;
    printf("%s %s -> %s %s:%s allowed=%d expected=%d\n",
           allowed == expected ? "PASS" : "FAIL", source, target, class_name,
           permission, allowed, expected);
}

int main(int argc, char **argv) {
    if (argc != 3 || (strcmp(argv[2], "baseline") && strcmp(argv[2], "harness")))
        return 2;
    FILE *file = fopen(argv[1], "rb");
    if (!file || fseek(file, 0, SEEK_END)) return 2;
    long size = ftell(file);
    if (size <= 0 || fseek(file, 0, SEEK_SET)) return 2;
    void *data = malloc((size_t)size);
    if (!data || fread(data, 1, (size_t)size, file) != (size_t)size) return 2;
    fclose(file);
    if (sepol_load_policy(data, (size_t)size)) return 2;
    free(data);
    int harness = !strcmp(argv[2], "harness");
    const char *shell = "u:r:shell:s0", *engine = "u:r:update_engine:s0";
    check(shell, engine, "binder", "call", harness);
    check(engine, shell, "binder", "call", harness);
    check(shell, engine, "fd", "use", harness);
    check(engine, shell, "fd", "use", harness);
    check("u:r:gmscore_app:s0:c512,c768", engine, "binder", "call", 1);
    check("u:r:system_app:s0", engine, "binder", "call", 1);
    check("u:r:system_server:s0", engine, "binder", "call", 1);
    check("u:r:untrusted_app:s0:c147,c256,c522,c768", engine, "binder", "call", 0);
    check(shell, "u:object_r:system_file:s0", "file", "entrypoint", 0);
    check(shell, "u:object_r:userdata_block_device:s0", "blk_file", "write", 0);
    return failures ? 1 : 0;
}
