// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// openbook-install: the OpenBook install engine (docs/installer.md section 3.5). The wizard app uses it through
// the daemon (PROTOCOL.md); test automation and the device agent use the CLI. Output is JSON on stdout, the log
// on stderr.
//
//   openbook-install [GLOBAL] disks                    the disks, their partitions, and whether each may be a target
//   openbook-install [GLOBAL] hwinfo                   the hardware check
//   openbook-install [GLOBAL] plan --target BY-ID --layout whole|alongside [--locale L] [--keyboard K]
//                              [--set-default] [--addon NAME]... [--gapps SHA256] [--out PLAN.json]
//                                                      the dry run: opens every disk read-only, prints every operation.
//                                                      --gapps: a package checked by gapps-check, by its manifest's
//                                                      sha256; naming it is the confirmation that the system will
//                                                      not be Play Protect certified (ANAL-211)
//   openbook-install [GLOBAL] gapps-check --package FILE  check a Google apps package the user supplied (LiteGapps
//                                                      layout) and stage what it may install (docs/gapps.md section 5)
//   openbook-install [GLOBAL] apply --plan PLAN.json --confirm-disk /dev/disk/by-id/BY-ID [--events]
//                                                      the install, unattended: OPENBOOK_INSTALL_ERASE must name the
//                                                      same /dev/disk/by-id/ path (S3). --events: progress as JSON
//                                                      lines on stdout before the report
//   openbook-install [GLOBAL] nvram                    the firmware's boot entries and BootOrder (read-only)
//   openbook-install [GLOBAL] addons                   the image's add-ons and whether the stick carries them
//   openbook-install [GLOBAL] daemon [--socket PATH]   openbook-installd (init passes its socket; PATH for tests)
// GLOBAL: --root DIR (host tests: sysfs, procfs and /dev/block below DIR) --boot-part-uuid UUID --log FILE
//         --efivars DIR (host tests: a plain directory in efivarfs's file format stands in for efivarfs)
#include "common.h"

#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void usage(void) {
    fprintf(stderr,
            "usage: openbook-install [--root DIR] [--boot-part-uuid UUID] [--log FILE] COMMAND ...\n"
            "  disks | hwinfo | nvram | addons\n"
            "  plan --target BY-ID --layout whole|alongside [--locale L] [--keyboard K] [--set-default]\n"
            "       [--addon NAME]... [--gapps SHA256] [--out FILE]\n"
            "  gapps-check --package FILE\n"
            "  apply --plan FILE --confirm-disk /dev/disk/by-id/BY-ID [--events]   (env OPENBOOK_INSTALL_ERASE)\n"
            "  daemon [--socket PATH]\n");
}

int main(int argc, char **argv) {
    const char *root = NULL, *uuid = NULL, *logpath = NULL, *efidir = NULL;
    int i = 1;
    for (; i < argc && argv[i][0] == '-'; i++) {
        if (!strcmp(argv[i], "--root") && i + 1 < argc) root = argv[++i];
        else if (!strcmp(argv[i], "--boot-part-uuid") && i + 1 < argc) uuid = argv[++i];
        else if (!strcmp(argv[i], "--log") && i + 1 < argc) logpath = argv[++i];
        else if (!strcmp(argv[i], "--efivars") && i + 1 < argc) efidir = argv[++i];
        else if (!strcmp(argv[i], "--version")) {
            puts("openbook-install 1");
            return 0;
        } else {
            usage();
            return 2;
        }
    }
    if (i >= argc) {
        usage();
        return 2;
    }
    env_init(root, uuid);
    if (efidir) env_set_efivars_dir(efidir);
    if (logpath) g_logfile = fopen(logpath, "ae");
    const char *cmd = argv[i++];
    if (!strcmp(cmd, "daemon")) {
        const char *sock = NULL;
        for (; i < argc; i++)
            if (!strcmp(argv[i], "--socket") && i + 1 < argc) sock = argv[++i];
        return daemon_main(sock);
    }
    if (!strcmp(cmd, "nvram")) {
        struct jw w = {0};
        jw_obj(&w, NULL);
        jw_bool(&w, "ok", 1);
        nvram_json(&w);
        jw_endo(&w);
        puts(w.b.p);
        return 0;
    }
    if (!strcmp(cmd, "addons")) {
        struct disk *d;
        int n = disks_scan(&d);
        struct source s;
        source_open(&s, d, n);
        struct jw w = {0};
        jw_obj(&w, NULL);
        jw_bool(&w, "ok", 1);
        addons_json(&w, "addons", &s);
        jw_endo(&w);
        puts(w.b.p);
        source_close(&s);
        disks_free(d, n);
        return 0;
    }
    if (!strcmp(cmd, "gapps-check")) {
        const char *pkg = NULL;
        for (; i < argc; i++)
            if (!strcmp(argv[i], "--package") && i + 1 < argc) pkg = argv[++i];
        if (!pkg) {
            usage();
            return 2;
        }
        const char *base = strrchr(pkg, '/') ? strrchr(pkg, '/') + 1 : pkg;
        struct jw w = {0};
        char sha[65];
        jw_obj(&w, NULL);
        int rc = gapps_check(pkg, base, &w, sha);
        jw_endo(&w);
        puts(w.b.p);
        return rc ? 1 : 0;
    }
    if (!strcmp(cmd, "disks") || !strcmp(cmd, "hwinfo")) {
        struct disk *d;
        int n = disks_scan(&d);
        struct jw w = {0};
        jw_obj(&w, NULL);
        jw_bool(&w, "ok", 1);
        if (!strcmp(cmd, "disks")) {
            struct source s;
            source_open(&s, d, n);
            uint64_t min = s.install ? (uint64_t)jnum(s.install, "min_disk_bytes", 64e9) : (uint64_t)64e9;
            jw_obj(&w, "source");
            jw_str(&w, "label", s.label);
            jw_bool(&w, "ok", s.ok);
            jw_str(&w, "why", s.ok ? NULL : s.why);
            jw_endo(&w);
            jw_arr(&w, "disks");
            for (int k = 0; k < n; k++) disk_json(&w, &d[k], min);
            jw_enda(&w);
            source_close(&s);
        } else {
            hwinfo_json(&w, d, n);
        }
        jw_endo(&w);
        puts(w.b.p);
        disks_free(d, n);
        return 0;
    }
    if (!strcmp(cmd, "plan")) {
        struct plan_req r = {0};
        const char *out = NULL;
        snprintf(r.layout, sizeof r.layout, "whole");
        for (; i < argc; i++) {
            if (!strcmp(argv[i], "--target") && i + 1 < argc) snprintf(r.target, sizeof r.target, "%s", argv[++i]);
            else if (!strcmp(argv[i], "--layout") && i + 1 < argc) snprintf(r.layout, sizeof r.layout, "%s", argv[++i]);
            else if (!strcmp(argv[i], "--locale") && i + 1 < argc) snprintf(r.locale, sizeof r.locale, "%s", argv[++i]);
            else if (!strcmp(argv[i], "--keyboard") && i + 1 < argc) snprintf(r.keyboard, sizeof r.keyboard, "%s", argv[++i]);
            else if (!strcmp(argv[i], "--set-default")) r.set_default = 1;
            else if (!strcmp(argv[i], "--addon") && i + 1 < argc) {
                if (plan_req_add_addon(&r, argv[++i])) {
                    fprintf(stderr, "--addon %s: not a valid add-on name, a duplicate, or more than %d\n", argv[i], ADDON_MAX);
                    return 2;
                }
            }
            else if (!strcmp(argv[i], "--gapps") && i + 1 < argc) {
                snprintf(r.gapps, sizeof r.gapps, "%s", argv[++i]);
                r.gapps_confirmed = 1;
            }
            else if (!strcmp(argv[i], "--out") && i + 1 < argc) out = argv[++i];
            else {
                usage();
                return 2;
            }
        }
        const char *t = r.target;
        if (!strncmp(t, "/dev/disk/by-id/", 16)) memmove(r.target, t + 16, strlen(t + 16) + 1);
        plan_seed(&r);
        struct disk *d;
        int n = disks_scan(&d);
        struct source s;
        source_open(&s, d, n);
        struct sb plan = {0};
        char sha[65], why[300];
        const char *code = "internal";
        int rc = plan_build(&r, d, n, &s, &plan, sha, &code, why, sizeof why);
        if (rc) {
            struct jw w = {0};
            jw_obj(&w, NULL);
            jw_bool(&w, "ok", 0);
            jw_str(&w, "code", code);
            jw_str(&w, "error", why);
            jw_endo(&w);
            puts(w.b.p);
            LOG("plan refused (%s): %s", code, why);
        } else {
            puts(plan.p);
            if (out && write_file(out, plan.p, plan.n)) {
                perror(out);
                rc = 1;
            }
            LOG("plan %s: %s on %s; nothing was written (the target was opened read-only)", sha, r.layout, r.target);
        }
        source_close(&s);
        disks_free(d, n);
        return rc ? 1 : 0;
    }
    if (!strcmp(cmd, "apply")) {
        const char *planpath = NULL, *confirm = NULL;
        int events = 0;
        for (; i < argc; i++) {
            if (!strcmp(argv[i], "--plan") && i + 1 < argc) planpath = argv[++i];
            else if (!strcmp(argv[i], "--confirm-disk") && i + 1 < argc) confirm = argv[++i];
            else if (!strcmp(argv[i], "--events")) events = 1;
            else {
                usage();
                return 2;
            }
        }
        if (!planpath || !confirm) {
            usage();
            return 2;
        }
        char *txt = read_file(planpath, NULL);
        char err[160];
        struct jv *p = txt ? json_parse(txt, err, sizeof err) : NULL;
        struct plan_req r;
        if (!p || plan_req_from_json(p, &r) || !jstr(p, "plan_sha256")) {
            fprintf(stderr, "%s: not a plan from `openbook-install plan`\n", planpath);
            return 2;
        }
        char sha[65];
        snprintf(sha, sizeof sha, "%s", jstr(p, "plan_sha256"));
        json_free(p);
        free(txt);
        if (events) g_event_fd = 1;
        struct sb result = {0};
        int rc = apply_run(&r, sha, NULL, confirm, &result);
        puts(result.p ? result.p : "{\"ok\":false}");
        return rc ? 1 : 0;
    }
    usage();
    return 2;
}
