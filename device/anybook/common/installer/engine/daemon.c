// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// openbook-installd: the install engine as a daemon for the wizard app (PROTOCOL.md). init starts it on live
// boots only (ro.boot.openbook.live=1) and hands it the listening socket /dev/socket/openbook_installd; SELinux
// lets only platform_app connect. One client at a time; an install runs in a child process, so it continues if
// the app goes away, and a new connection can "attach" to it.
#include "common.h"

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

#define MAX_PLANS 8

static struct {
    char sha[65];
    struct plan_req req;
} plans[MAX_PLANS];
static int nplans;

static struct {
    pid_t pid;
    int fd;              // events from the child
    struct sb buf;       // partial line
    long long client_id; // request id to stamp events with, -1 if nobody is attached
    char steps[7][2][16];
    double pct;
    char step[24];
    struct sb result;    // the final report JSON once finished
    int finished, ok;
} job = {.pid = 0, .fd = -1, .client_id = -1};

static const char *const STEP_IDS[] = {"check_source", "prepare_disk", "boot_images", "system",
                                       "boot_entry",   "verify",       "report"};
static int client = -1;
static struct sb inbuf;

static void send_line(const char *s) {
    if (client < 0) return;
    size_t n = strlen(s);
    struct sb b = {0};
    sb_add(&b, s, n);
    sb_add(&b, "\n", 1);
    size_t done = 0;
    while (done < b.n) {
        ssize_t r = send(client, b.p + done, b.n - done, MSG_NOSIGNAL);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) break;
        done += r;
    }
    sb_free(&b);
}

static void reply_err(long long id, const char *code, const char *msg) {
    struct jw w = {0};
    jw_obj(&w, NULL);
    jw_int(&w, "id", id);
    jw_bool(&w, "ok", 0);
    jw_str(&w, "code", code);
    jw_str(&w, "error", msg);
    jw_endo(&w);
    send_line(w.b.p);
    LOG("request %lld: %s (%s)", id, code, msg);
    sb_free(&w.b);
}

// "{...}" -> "{"id":N,..."
static void send_with_id(long long id, const char *json) {
    struct sb b = {0};
    sb_printf(&b, "{\"id\":%lld,%s", id, json + 1);
    send_line(b.p);
    sb_free(&b);
}

static void job_json(struct jw *w, const char *key) {
    if (!job.pid && !job.finished) {
        jw_null(w, key);
        return;
    }
    jw_obj(w, key);
    jw_bool(w, "running", job.pid && !job.finished);
    jw_dbl(w, "pct", job.pct, 1);
    jw_str(w, "step", job.step);
    jw_obj(w, "steps");
    for (int i = 0; i < 7; i++) jw_str(w, STEP_IDS[i], job.steps[i][0][0] ? job.steps[i][0] : "pending");
    jw_endo(w);
    if (job.finished && job.result.p) jw_raw(w, "result", job.result.p);
    else jw_null(w, "result");
    jw_endo(w);
}

static void final_message(long long id) {
    struct jw w = {0};
    jw_obj(&w, NULL);
    jw_int(&w, "id", id);
    jw_bool(&w, "ok", job.ok);
    if (!job.ok) {
        struct jv *r = job.result.p ? json_parse(job.result.p, NULL, 0) : NULL;
        jw_str(&w, "code", r && jstr(r, "code") ? jstr(r, "code") : "io");
        jw_str(&w, "error", r && jstr(r, "error") ? jstr(r, "error") : "the install failed");
        json_free(r);
    }
    if (job.result.p) jw_raw(&w, "result", job.result.p);
    jw_endo(&w);
    send_line(w.b.p);
    sb_free(&w.b);
}

static void job_line(const char *line) {
    char err[64];
    struct jv *e = json_parse(line, err, sizeof err);
    if (!e) return;
    const char *ev = jstr(e, "event");
    if (ev && !strcmp(ev, "result")) {
        struct jv *r = jget(e, "result");
        // the raw text of the result: everything after "result":
        const char *p = strstr(line, "\"result\":");
        sb_free(&job.result);
        if (p) {
            sb_puts(&job.result, p + 9);
            if (job.result.n && job.result.p[job.result.n - 1] == '}') job.result.p[--job.result.n] = 0;
        }
        job.ok = r && jbool(r, "ok", 0);
        job.finished = 1;
        if (job.client_id >= 0) final_message(job.client_id);
        job.client_id = -1;
    } else {
        if (ev && !strcmp(ev, "step")) {
            const char *s = jstr(e, "step"), *st = jstr(e, "state");
            for (int i = 0; s && st && i < 7; i++)
                if (!strcmp(STEP_IDS[i], s)) snprintf(job.steps[i][0], sizeof job.steps[i][0], "%s", st);
            if (s && st && !strcmp(st, "running")) snprintf(job.step, sizeof job.step, "%s", s);
        } else if (ev && !strcmp(ev, "progress")) {
            job.pct = jnum(e, "pct", job.pct);
        } else if (ev && !strcmp(ev, "log")) {
            const char *l = jstr(e, "line");
            if (l) {
                sb_puts(&g_install_log, l);
                sb_puts(&g_install_log, "\n");
                if (g_logfile) {
                    fprintf(g_logfile, "%s\n", l);
                    fflush(g_logfile);
                }
            }
        }
        if (job.client_id >= 0) send_with_id(job.client_id, line);
    }
    json_free(e);
}

static void job_read(void) {
    char tmp[8192];
    ssize_t r = read(job.fd, tmp, sizeof tmp);
    if (r <= 0) {
        close(job.fd);
        job.fd = -1;
        return;
    }
    sb_add(&job.buf, tmp, r);
    char *nl;
    while (job.buf.p && (nl = memchr(job.buf.p, '\n', job.buf.n))) {
        *nl = 0;
        job_line(job.buf.p);
        size_t rest = job.buf.n - (nl + 1 - job.buf.p);
        memmove(job.buf.p, nl + 1, rest);
        job.buf.n = rest;
        job.buf.p[rest] = 0;
    }
}

static void job_reap(void) {
    if (!job.pid) return;
    int st;
    pid_t r = waitpid(job.pid, &st, WNOHANG);
    if (r != job.pid) return;
    while (job.fd >= 0) job_read();  // drain
    if (!job.finished) {
        job.finished = 1;
        job.ok = 0;
        sb_free(&job.result);
        sb_printf(&job.result, "{\"ok\":false,\"code\":\"internal\",\"error\":\"the install process ended (status %d)\"}",
                  st);
        if (job.client_id >= 0) final_message(job.client_id);
        job.client_id = -1;
    }
    LOG("install process %d ended: %s", job.pid, job.ok ? "ok" : "failed");
    job.pid = 0;
}

static int plan_cache_find(const char *sha) {
    for (int i = 0; i < nplans; i++)
        if (!strcmp(plans[i].sha, sha)) return i;
    return -1;
}

static void cmd_hello(long long id) {
    struct disk *d;
    int n = disks_scan(&d);
    struct source s;
    source_open(&s, d, n);
    struct power pw;
    power_read(&pw);
    struct jw w = {0};
    jw_obj(&w, NULL);
    jw_int(&w, "id", id);
    jw_bool(&w, "ok", 1);
    jw_int(&w, "version", 1);
    jw_bool(&w, "live", E.live);
    jw_str(&w, "selinux", E.selinux);
    if (s.disk) {
        jw_obj(&w, "boot_disk");
        jw_str(&w, "name", s.disk->name);
        jw_str(&w, "by_id", s.disk->by_id);
        jw_str(&w, "model", s.disk->model);
        jw_u64(&w, "size_bytes", s.disk->size);
        jw_endo(&w);
    } else {
        jw_null(&w, "boot_disk");
    }
    jw_obj(&w, "source");
    jw_str(&w, "label", s.label);
    jw_str(&w, "fingerprint", s.fingerprint);
    jw_bool(&w, "ok", s.ok);
    jw_str(&w, "why", s.ok ? NULL : s.why);
    jw_endo(&w);
    jw_bool(&w, "efivars", E.efivars);
    if (pw.known) {
        jw_obj(&w, "power");
        jw_bool(&w, "ac", pw.ac);
        if (pw.have_battery) jw_int(&w, "battery_pct", pw.battery_pct);
        else jw_null(&w, "battery_pct");
        jw_bool(&w, "ok", pw.ok);
        jw_endo(&w);
    } else {
        jw_null(&w, "power");  // the app reads it (BatteryManager) and sends it with apply
    }
    jw_bool(&w, "logs_on_stick", !E.logs_mode && s.disk != NULL);
    addons_json(&w, "addons", &s);
    job_json(&w, "job");
    jw_endo(&w);
    send_line(w.b.p);
    sb_free(&w.b);
    source_close(&s);
    disks_free(d, n);
}

static void cmd_hwinfo(long long id, int to_stick) {
    struct disk *d;
    int n = disks_scan(&d);
    struct jw w = {0};
    jw_obj(&w, NULL);
    jw_int(&w, "id", id);
    jw_bool(&w, "ok", 1);
    hwinfo_json(&w, d, n);
    jw_endo(&w);
    if (!to_stick) {
        send_line(w.b.p);
    } else {
        struct source s;
        source_open(&s, d, n);
        char path[96] = "";
        int ok = 0;
        if (s.disk && !E.logs_mode) {
            int fd = open(s.disk->dev, O_RDWR | O_CLOEXEC);
            struct fat f;
            uint64_t off = s.esp ? s.esp->first * s.disk->sector : 0;
            uint64_t size = s.esp ? (s.esp->last - s.esp->first + 1) * s.disk->sector : 0;
            if (fd >= 0) drop_cache(fd);
            if (fd >= 0 && s.esp && !fat_open(&f, fd, off, size)) {
                for (int k = 1; k < 1000; k++) {
                    snprintf(path, sizeof path, "openbook/logs/hwcheck-live-%03d.json", k);
                    if (!fat_exists(&f, path, NULL)) break;
                }
                // the hwinfo object alone, without the id/ok wrapper
                const char *hw = strstr(w.b.p, "\"hw\":");
                struct sb body = {0};
                if (hw) {
                    sb_puts(&body, hw + 5);
                    if (body.n) body.p[--body.n] = 0;  // the wrapper's closing brace
                }
                ok = !fat_write(&f, path, body.p ? body.p : "{}", body.n);
                sb_free(&body);
                fat_close(&f);
                fsync(fd);
            }
            if (fd >= 0) close(fd);
        }
        if (ok) {
            struct sb b = {0};
            sb_printf(&b, "{\"id\":%lld,\"ok\":true,\"path\":\"%s\"}", id, path);
            send_line(b.p);
            sb_free(&b);
            LOG("hardware report saved to the stick: %s", path);
        } else {
            reply_err(id, "io", E.logs_mode ? "this boot saves logs to the stick itself; use the default entry"
                                            : "could not write to the stick");
        }
        source_close(&s);
    }
    sb_free(&w.b);
    disks_free(d, n);
}

static void cmd_disks(long long id) {
    struct disk *d;
    int n = disks_scan(&d);
    struct source s;
    source_open(&s, d, n);
    uint64_t min = s.install ? (uint64_t)jnum(s.install, "min_disk_bytes", 64e9) : (uint64_t)64e9;
    struct jw w = {0};
    jw_obj(&w, NULL);
    jw_int(&w, "id", id);
    jw_bool(&w, "ok", 1);
    jw_arr(&w, "disks");
    for (int i = 0; i < n; i++) disk_json(&w, &d[i], min);
    jw_enda(&w);
    jw_endo(&w);
    send_line(w.b.p);
    sb_free(&w.b);
    source_close(&s);
    disks_free(d, n);
}

static void cmd_plan(long long id, struct jv *q) {
    struct plan_req r = {0};
    snprintf(r.target, sizeof r.target, "%s", jstr(q, "target") ? jstr(q, "target") : "");
    snprintf(r.layout, sizeof r.layout, "%s", jstr(q, "layout") ? jstr(q, "layout") : "whole");
    snprintf(r.locale, sizeof r.locale, "%s", jstr(q, "locale") ? jstr(q, "locale") : "");
    snprintf(r.keyboard, sizeof r.keyboard, "%s", jstr(q, "keyboard") ? jstr(q, "keyboard") : "");
    r.set_default = jbool(q, "set_default", 0);
    struct jv *ad = jget(q, "addons");
    for (int i = 0; ad && ad->t == J_ARR && i < ad->len; i++)
        if (ad->items[i]->t != J_STR || plan_req_add_addon(&r, ad->items[i]->s)) {
            reply_err(id, "bad_request", "addons: names of add-ons, each once");
            return;
        }
    for (const char *p = r.locale; *p; p++)
        if (!(isalnum((unsigned char)*p) || *p == '-' || *p == '_')) r.locale[0] = 0;
    for (const char *p = r.keyboard; *p; p++)
        if (!(isalnum((unsigned char)*p) || *p == '-' || *p == '_')) r.keyboard[0] = 0;
    plan_seed(&r);
    struct disk *d;
    int n = disks_scan(&d);
    struct source s;
    source_open(&s, d, n);
    struct sb out = {0};
    char sha[65], why[300];
    const char *code = "internal";
    if (plan_build(&r, d, n, &s, &out, sha, &code, why, sizeof why)) {
        reply_err(id, code, why);
    } else {
        int slot = nplans < MAX_PLANS ? nplans++ : (memmove(plans, plans + 1, sizeof plans[0] * (MAX_PLANS - 1)), MAX_PLANS - 1);
        snprintf(plans[slot].sha, sizeof plans[slot].sha, "%s", sha);
        plans[slot].req = r;
        struct sb b = {0};
        sb_printf(&b, "{\"id\":%lld,\"ok\":true,\"plan\":%s}", id, out.p);
        send_line(b.p);
        sb_free(&b);
        LOG("plan %.16s: %s on %s (dry run, read-only)", sha, r.layout, r.target);
        LOG("%s", out.p);
    }
    sb_free(&out);
    source_close(&s);
    disks_free(d, n);
}

static void cmd_apply(long long id, struct jv *q) {
    const char *sha = jstr(q, "plan_sha256"), *target = jstr(q, "target"), *typed = jstr(q, "typed");
    if (job.pid && !job.finished) {
        reply_err(id, "busy", "an install is already running");
        return;
    }
    int k = sha ? plan_cache_find(sha) : -1;
    if (k < 0) {
        reply_err(id, "plan_changed", "unknown plan: view the plan again");
        return;
    }
    if (!target || strcmp(target, plans[k].req.target)) {
        reply_err(id, "bad_request", "the target does not match the plan");
        return;
    }
    if (!typed) {
        reply_err(id, "confirm_mismatch", "type the disk's name to confirm");
        return;
    }
    int pfd[2];
    if (pipe2(pfd, O_CLOEXEC)) {
        reply_err(id, "internal", strerror(errno));
        return;
    }
    struct plan_req req = plans[k].req;
    struct jv *pw = jget(q, "power");
    g_power_override_set = pw && pw->t == J_OBJ;
    if (g_power_override_set) {
        struct jv *b = jget(pw, "battery_pct");
        memset(&g_power_override, 0, sizeof g_power_override);
        g_power_override.known = 1;
        g_power_override.ac = jbool(pw, "ac", 0);
        g_power_override.have_battery = b && b->t == J_NUM;
        g_power_override.battery_pct = g_power_override.have_battery ? (int)b->n : -1;
        g_power_override.ok = g_power_override.ac || !g_power_override.have_battery || g_power_override.battery_pct >= 50;
    }
    char shacopy[65];
    snprintf(shacopy, sizeof shacopy, "%s", sha);
    char typedcopy[256];
    snprintf(typedcopy, sizeof typedcopy, "%s", typed);
    pid_t pid = fork();
    if (pid < 0) {
        close(pfd[0]);
        close(pfd[1]);
        reply_err(id, "internal", strerror(errno));
        return;
    }
    if (pid == 0) {
        close(pfd[0]);
        if (client >= 0) close(client);
        g_event_fd = pfd[1];
        g_logfile = NULL;  // the parent logs the child's lines
        sb_free(&g_install_log);
        struct sb result = {0};
        int rc = apply_run(&req, shacopy, typedcopy, NULL, &result);
        struct sb e = {0};
        sb_printf(&e, "{\"event\":\"result\",\"result\":%s}", result.p ? result.p : "{\"ok\":false}");
        emit_event(e.p);
        _exit(rc ? 1 : 0);
    }
    close(pfd[1]);
    sb_free(&job.result);
    sb_free(&job.buf);
    memset(job.steps, 0, sizeof job.steps);
    job.pid = pid;
    job.fd = pfd[0];
    job.client_id = id;
    job.finished = job.ok = 0;
    job.pct = 0;
    job.step[0] = 0;
    LOG("install %d started: plan %.16s, %s on %s", pid, sha, req.layout, req.target);
}

static void cmd_attach(long long id) {
    if (!job.pid && !job.finished) {
        reply_err(id, "bad_request", "no install in this boot");
        return;
    }
    for (int i = 0; i < 7; i++) {
        char e[160];
        snprintf(e, sizeof e, "{\"id\":%lld,\"event\":\"step\",\"step\":\"%s\",\"state\":\"%s\"}", id, STEP_IDS[i],
                 job.steps[i][0][0] ? job.steps[i][0] : "pending");
        send_line(e);
    }
    char e[160];
    snprintf(e, sizeof e, "{\"id\":%lld,\"event\":\"progress\",\"step\":\"%s\",\"pct\":%.1f}", id, job.step, job.pct);
    send_line(e);
    if (job.finished) final_message(id);
    else job.client_id = id;
}

static void cmd_status(long long id) {
    struct jw w = {0};
    jw_obj(&w, NULL);
    jw_int(&w, "id", id);
    jw_bool(&w, "ok", 1);
    job_json(&w, "job");
    jw_endo(&w);
    send_line(w.b.p);
    sb_free(&w.b);
}

static void cmd_log(long long id, int tail) {
    if (tail <= 0 || tail > 2000) tail = 200;
    const char *s = g_install_log.p ? g_install_log.p : "";
    const char *start = s + strlen(s);
    int lines = 0;
    while (start > s && lines <= tail) {
        start--;
        if (*start == '\n') lines++;
    }
    if (*start == '\n') start++;
    struct jw w = {0};
    jw_obj(&w, NULL);
    jw_int(&w, "id", id);
    jw_bool(&w, "ok", 1);
    jw_arr(&w, "lines");
    char *copy = strdup(start), *save = NULL;
    for (char *l = strtok_r(copy, "\n", &save); l; l = strtok_r(NULL, "\n", &save)) jw_str(&w, NULL, l);
    free(copy);
    jw_enda(&w);
    jw_endo(&w);
    send_line(w.b.p);
    sb_free(&w.b);
}

static void handle(const char *line) {
    char err[128];
    struct jv *q = json_parse(line, err, sizeof err);
    long long id = q ? (long long)jnum(q, "id", 0) : 0;
    const char *cmd = q ? jstr(q, "cmd") : NULL;
    if (!q || !cmd) {
        reply_err(id, "bad_request", q ? "no cmd" : err);
        json_free(q);
        return;
    }
    // Re-read the environment for every request (properties do not change, the boot disk might not be found yet).
    if (!strcmp(cmd, "hello")) cmd_hello(id);
    else if (!strcmp(cmd, "hwinfo")) cmd_hwinfo(id, 0);
    else if (!strcmp(cmd, "save_report")) cmd_hwinfo(id, 1);
    else if (!strcmp(cmd, "disks")) cmd_disks(id);
    else if (!strcmp(cmd, "plan")) cmd_plan(id, q);
    else if (!strcmp(cmd, "apply")) cmd_apply(id, q);
    else if (!strcmp(cmd, "attach")) cmd_attach(id);
    else if (!strcmp(cmd, "status")) cmd_status(id);
    else if (!strcmp(cmd, "log")) cmd_log(id, (int)jnum(q, "tail", 200));
    else reply_err(id, "bad_request", "unknown cmd");
    json_free(q);
}

static int listen_socket(const char *path) {
    if (!path) {
        const char *env = getenv("ANDROID_SOCKET_openbook_installd");  // created by init (the rc's socket option)
        if (env) {
            int fd = atoi(env);
            fcntl(fd, F_SETFD, FD_CLOEXEC);
            return fd;
        }
        return -1;
    }
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    struct sockaddr_un a = {.sun_family = AF_UNIX};
    snprintf(a.sun_path, sizeof a.sun_path, "%s", path);
    unlink(path);
    if (fd < 0 || bind(fd, (struct sockaddr *)&a, sizeof a) || listen(fd, 4)) return -1;
    chmod(path, 0660);
    return fd;
}

int daemon_main(const char *socket_path) {
    signal(SIGPIPE, SIG_IGN);
    int lfd = listen_socket(socket_path);
    if (lfd < 0) {
        LOG("openbook-installd: no listening socket (%s)", strerror(errno));
        return 1;
    }
    if (!socket_path) {
        mkdir("/data/misc/openbook_install", 0770);
        g_logfile = fopen("/data/misc/openbook_install/installd.log", "ae");
    }
    if (listen(lfd, 4) && errno != EINVAL) LOG("listen: %s", strerror(errno));
    LOG("openbook-installd ready (live=%d, SELinux %s, boot_part_uuid %s)", E.live, E.selinux,
        E.boot_part_uuid[0] ? E.boot_part_uuid : "-");
    for (;;) {
        struct pollfd p[3];
        int np = 0;
        int il = -1, ic = -1, ij = -1;
        if (client < 0) {
            il = np;
            p[np++] = (struct pollfd){.fd = lfd, .events = POLLIN};
        } else {
            ic = np;
            p[np++] = (struct pollfd){.fd = client, .events = POLLIN};
        }
        if (job.fd >= 0) {
            ij = np;
            p[np++] = (struct pollfd){.fd = job.fd, .events = POLLIN};
        }
        int r = poll(p, np, 500);
        job_reap();
        if (r <= 0) continue;
        if (il >= 0 && (p[il].revents & POLLIN)) {
            client = accept4(lfd, NULL, NULL, SOCK_CLOEXEC);
            if (client >= 0) {
                struct ucred cr;
                socklen_t cl = sizeof cr;
                if (!getsockopt(client, SOL_SOCKET, SO_PEERCRED, &cr, &cl))
                    LOG("client connected: pid %d uid %d", cr.pid, cr.uid);
                sb_free(&inbuf);
            }
        }
        if (ij >= 0 && (p[ij].revents & (POLLIN | POLLHUP))) job_read();
        if (ic >= 0 && (p[ic].revents & (POLLIN | POLLHUP | POLLERR))) {
            char tmp[8192];
            ssize_t n = recv(client, tmp, sizeof tmp, 0);
            if (n <= 0) {
                close(client);
                client = -1;
                job.client_id = -1;
                LOG("client disconnected");
                continue;
            }
            sb_add(&inbuf, tmp, n);
            if (inbuf.n > 65536) {
                close(client);
                client = -1;
                job.client_id = -1;
                continue;
            }
            char *nl;
            while (client >= 0 && inbuf.p && (nl = memchr(inbuf.p, '\n', inbuf.n))) {
                *nl = 0;
                char *line = strdup(inbuf.p);
                size_t rest = inbuf.n - (nl + 1 - inbuf.p);
                memmove(inbuf.p, nl + 1, rest);
                inbuf.n = rest;
                inbuf.p[rest] = 0;
                if (line[0]) handle(line);
                free(line);
            }
        }
    }
}
